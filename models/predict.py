"""Combined map win-probability prediction (P3.T7).

``predict_map_win_prob(match_id, map_index, live_state=None)`` returns
P(match.team1 wins this map):

- **pre-match** (``live_state is None``): the posterior-mean probability from the
  Bambi logistic (Layer 3), on the point-in-time feature row for that map.
- **live** (``live_state`` given): the pre-match prior combined with the empirical
  score-state lookup (Layer 4) by **log-odds pooling** —
  ``logit(post) = logit(prior) + logit(p_state)`` — i.e. posterior odds ∝ prior
  odds × score-state likelihood (SPEC §6.2 Layer 4, "posterior ∝ prior ×
  likelihood-from-score"). The score-state table's implicit prior is the
  league-average matchup (~0.5), so its odds act as the likelihood ratio; at the
  0-0 start ``p_state ≈ 0.5`` and the posterior equals the prior.

``live_state`` is a dict from **team1's** perspective:
``{"half": "second", "team1_score": 9, "team2_score": 3, "team1_side": "ct"}``.

Resources (training data, Bambi model, posterior trace, score-state table) are
loaded once per db path and cached. Requires ``models/saved/bayes_logistic.nc``
(build it with ``python -m models.bayes_logistic``).

Usage:
    python -m models.predict --db data/prx.db [--match-id N --map-index 0]
"""

import argparse
import math
import sqlite3

# arviz / bambi (via models.bayes_logistic) are imported lazily inside _resources()
# so the pure combination logic below stays importable without the heavy MCMC stack.

DB_DEFAULT = "data/prx.db"
_EPS = 1e-6

_CACHE = {}


def _logit(p):
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _expit(x):
    return 1.0 / (1.0 + math.exp(-x))


def combine_prior_and_state(p_prior, p_state):
    """Log-odds pool the pre-match prior with the score-state probability.

    posterior odds = prior odds × score-state odds (SPEC Layer 4). A neutral
    score state (p_state == 0.5) returns the prior unchanged.
    """
    return _expit(_logit(p_prior) + _logit(p_state))


def _resources(db_path):
    if db_path not in _CACHE:
        import arviz as az
        # Importing bayes_logistic sets PYTENSOR_FLAGS (numba backend) before bambi.
        import models.bayes_logistic as bl
        from models.training_data import build_training_data

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        df = build_training_data(conn)
        model = bl.build_model(bl.split_train(df))
        idata = az.from_netcdf(bl.SAVE_PATH)
        map_index = {
            (r["match_id"], r["map_index"]): r["map_id"]
            for r in conn.execute("SELECT match_id, map_index, map_id FROM maps")
        }
        score_state = {
            (r["half"], r["team_score"], r["opp_score"], r["side"]): r["smoothed_win_pct"]
            for r in conn.execute(
                "SELECT half, team_score, opp_score, side, smoothed_win_pct "
                "FROM score_state_lookup"
            )
        }
        conn.close()
        _CACHE[db_path] = (df, model, idata, map_index, score_state)
    return _CACHE[db_path]


def _prematch_prob(model, idata, row_df):
    pred = model.predict(idata, data=row_df, inplace=False, sample_new_groups=True)
    return float(pred.posterior["p"].mean())


def predict_map_win_prob(match_id, map_index, live_state=None, *, db_path=DB_DEFAULT):
    """P(team1 wins the map). See module docstring for live_state shape."""
    df, model, idata, map_idx, score_state = _resources(db_path)

    map_id = map_idx.get((match_id, map_index))
    if map_id is None:
        raise ValueError(f"no map for match {match_id} map_index {map_index}")
    sel = df[df["map_id"] == map_id]
    if sel.empty:
        raise ValueError(f"no feature row for map_id {map_id} "
                         f"(match {match_id} map_index {map_index}) — showmatch?")

    p_prior = _prematch_prob(model, idata, sel.iloc[[0]].copy())
    if live_state is None:
        return p_prior

    key = (live_state["half"], live_state["team1_score"],
           live_state["team2_score"], live_state["team1_side"])
    p_state = score_state.get(key, 0.5)
    return combine_prior_and_state(p_prior, p_state)


# --- Detailed prediction (P6.T2): mean + credible interval + factor attribution ---
# Used by the API/dashboard, not by the P5 live poller. The natural-language
# explanation is a separate Phase-7 LLM call.

_FACTOR_LABELS = {
    "elo_diff": "Elo difference",
    "skill_diff": "Player skill",
    "map_elo_diff": "Map advantage",
    "recent_form_team1": "Recent form (team1)",
    "recent_form_team2": "Recent form (team2)",
    "h2h_team1_win_rate": "Head-to-head",
    "team1_starts_atk_or_def": "Starting side",
}
# feature column -> (Bambi posterior variable name, is the term wrapped in scale())
_FACTOR_TERMS = {
    "elo_diff": ("scale(elo_diff)", True),
    "map_elo_diff": ("scale(map_elo_diff)", True),
    "skill_diff": ("scale(skill_diff)", True),
    "recent_form_team1": ("scale(recent_form_team1)", True),
    "recent_form_team2": ("scale(recent_form_team2)", True),
    "h2h_team1_win_rate": ("scale(h2h_team1_win_rate)", True),
    "team1_starts_atk_or_def": ("team1_starts_atk_or_def", False),
}


def _top_factors(idata, row_df, df_train, *, n=4):
    """Interpretable attribution: posterior-mean coef × standardized feature value.

    Ranked by magnitude; ``favors`` = sign relative to team1; ``weight`` =
    normalized share among the returned factors. Not exact Shapley.
    """
    post = idata.posterior
    row = row_df.iloc[0]
    contribs = []
    for col, (var, scaled) in _FACTOR_TERMS.items():
        if var not in post or col not in row_df.columns:
            continue
        coef = float(post[var].mean())
        x = float(row[col])
        if scaled:
            mu = float(df_train[col].mean())
            sd = float(df_train[col].std(ddof=0))
            contrib = coef * ((x - mu) / sd if sd > 0 else 0.0)
        else:
            contrib = coef * x
        if abs(contrib) > 1e-9:
            contribs.append((col, contrib))

    contribs.sort(key=lambda c: abs(c[1]), reverse=True)
    top = contribs[:n]
    total = sum(abs(c) for _, c in top) or 1.0
    return [
        {"factor": _FACTOR_LABELS.get(col, col),
         "weight": round(abs(contrib) / total, 3),
         "favors": "team1" if contrib > 0 else "team2"}
        for col, contrib in top
    ]


def detailed_from_row(model, idata, row_df, df_train, *, n_factors=4, hdi_prob=0.94):
    """{'team1_win_prob', 'hdi': [lo, hi], 'top_factors'} for a single feature row."""
    import arviz as az

    pred = model.predict(idata, data=row_df, inplace=False, sample_new_groups=True)
    samples = pred.posterior["p"].values.reshape(-1)
    lo, hi = az.hdi(samples, hdi_prob=hdi_prob)
    return {
        "team1_win_prob": float(samples.mean()),
        "hdi": [float(lo), float(hi)],
        "top_factors": _top_factors(idata, row_df, df_train, n=n_factors),
    }


def predict_map_win_prob_detailed(match_id, map_index, *, db_path=DB_DEFAULT, n_factors=4):
    """Pre-match ``predict_map_win_prob`` plus an HDI and a factor breakdown."""
    df, model, idata, map_idx, _ = _resources(db_path)
    map_id = map_idx.get((match_id, map_index))
    if map_id is None:
        raise ValueError(f"no map for match {match_id} map_index {map_index}")
    sel = df[df["map_id"] == map_id]
    if sel.empty:
        raise ValueError(f"no feature row for map_id {map_id} "
                         f"(match {match_id} map_index {map_index}) — showmatch?")
    return detailed_from_row(model, idata, sel.iloc[[0]].copy(), df, n_factors=n_factors)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--match-id", type=int)
    ap.add_argument("--map-index", type=int, default=0)
    args = ap.parse_args()

    df, _, _, map_idx, _ = _resources(args.db)
    match_id, map_index = args.match_id, args.map_index
    if match_id is None:
        # Default sample: the most recent map involving Paper Rex (team 624).
        prx = df[(df["team1_id"] == 624) | (df["team2_id"] == 624)]
        row = prx.sort_values("date_utc").iloc[-1]
        match_id = int(row["match_id"])
        # map_index for that map_id:
        map_index = next(mi for (m, mi), mid in map_idx.items()
                         if m == match_id and mid == int(row["map_id"]))
        print(f"(sample) latest PRX map: match {match_id} map_index {map_index} "
              f"({row['map_name']}, {row['date_utc']})")

    p_pre = predict_map_win_prob(match_id, map_index, db_path=args.db)
    print(f"pre-match P(team1 wins map): {p_pre:.3f}")
    for desc, ls in [
        ("team1 up 9-3 at half, defense", {"half": "second", "team1_score": 9, "team2_score": 3, "team1_side": "ct"}),
        ("team1 down 3-9 at half, defense", {"half": "second", "team1_score": 3, "team2_score": 9, "team1_side": "ct"}),
        ("level 0-0 start, attack", {"half": "first", "team1_score": 0, "team2_score": 0, "team1_side": "t"}),
    ]:
        p = predict_map_win_prob(match_id, map_index, live_state=ls, db_path=args.db)
        print(f"  live [{desc}]: {p:.3f}")


if __name__ == "__main__":
    main()
