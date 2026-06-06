"""Expected player stats for a match — ACS/K/D/A (P4.T3).

Predicts each player's expected per-map stats for a match, for the "expected vs
actual" panel (SPEC §6.2 Layer 5). A feasibility check showed per-map ACS is
irreducibly noisy (MAE ~43), but **match-level** expected stats from a player's
**recent-form mean** hit the ±30 done-when (MAE ~29). So:

- core = recent-form mean of each stat over the player's last ``FORM_MAPS`` maps
  strictly before the match (fallback: career mean, then league per-stat mean);
- a mild **opponent** adjustment scales expected ACS by the opposing team's
  pre-match Elo (tougher opponent -> slightly lower), kept because it reduces
  validation MAE; ``opponent_coef=0`` disables it;
- the **map** term is dropped (it increased error in testing).

Point-in-time: only data with ``date_utc <`` the match date feeds the baseline,
and opponent Elo is read from ``elo_ratings`` as-of before the match (run
``python -m scripts.build_elo`` first). See DEVIATIONS 2026-06-06.

Usage:
    python -m models.expected_stats --db data/prx.db [--match-id N]
"""

import argparse
import sqlite3

import pandas as pd

DB_DEFAULT = "data/prx.db"
FORM_MAPS = 30          # recent-form window (maps)
DEFAULT_OPP_COEF = 0.06  # ACS multiplier sensitivity to opponent Elo (per 400 pts)
_STATS = ["acs", "kills", "deaths", "assists"]

_CACHE = {}


def _recent_form(values, n=FORM_MAPS):
    """Mean of the last n values (all if fewer); None if empty."""
    if not values:
        return None
    window = values[-n:]
    return sum(window) / len(window)


def _resources(db_path):
    if db_path not in _CACHE:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        hist = pd.read_sql(
            """SELECT mps.player_id, mps.acs, mps.kills, mps.deaths, mps.assists,
                      m.date_utc
               FROM map_player_stats mps
               JOIN maps mp ON mp.map_id = mps.map_id
               JOIN matches m ON m.match_id = mp.match_id
               WHERE mps.player_id IS NOT NULL AND mps.acs IS NOT NULL
                 AND (m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')
               ORDER BY m.date_utc, mps.map_id""",
            conn,
        )
        league = {s: float(hist[s].mean()) for s in _STATS}
        conn.close()
        _CACHE[db_path] = (hist, league)
    return _CACHE[db_path]


def _opponent_elo(conn, team_id, before_date):
    """Opposing team's latest Elo strictly before the match date (1500 if none)."""
    row = conn.execute(
        "SELECT rating FROM elo_ratings WHERE team_id = ? AND as_of_date < ? "
        "ORDER BY as_of_date DESC LIMIT 1",
        (team_id, before_date),
    ).fetchone()
    return row[0] if row else 1500.0


def predict_expected_stats(match_id, *, db_path=DB_DEFAULT, opponent_coef=DEFAULT_OPP_COEF):
    """Return a DataFrame of expected (and, for a known match, actual) stats per player."""
    hist, league = _resources(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    meta = conn.execute(
        "SELECT date_utc, team1_id, team2_id FROM matches WHERE match_id = ?",
        (match_id,),
    ).fetchone()
    if meta is None:
        conn.close()
        raise ValueError(f"no match {match_id}")
    date = meta["date_utc"]

    parts = conn.execute(
        """SELECT DISTINCT mps.player_id, mps.team_id_at_match AS team_id
           FROM map_player_stats mps JOIN maps mp ON mp.map_id = mps.map_id
           WHERE mp.match_id = ? AND mps.player_id IS NOT NULL""",
        (match_id,),
    ).fetchall()
    names = {r["player_id"]: r["handle"] for r in conn.execute("SELECT player_id, handle FROM players")}

    # Actuals for a known match: each player's mean stat over this match's maps.
    actual = pd.read_sql(
        """SELECT mps.player_id, AVG(mps.acs) a_acs, AVG(mps.kills) a_kills,
                  AVG(mps.deaths) a_deaths, AVG(mps.assists) a_assists
           FROM map_player_stats mps JOIN maps mp ON mp.map_id = mps.map_id
           WHERE mp.match_id = ? AND mps.player_id IS NOT NULL
           GROUP BY mps.player_id""",
        conn, params=(match_id,),
    ).set_index("player_id")

    opp_elo = {meta["team1_id"]: _opponent_elo(conn, meta["team2_id"], date),
               meta["team2_id"]: _opponent_elo(conn, meta["team1_id"], date)}
    conn.close()

    prior = hist[hist["date_utc"] < date]
    rows = []
    for p in parts:
        pid, tid = p["player_id"], p["team_id"]
        h = prior[prior["player_id"] == pid]
        exp = {}
        for s in _STATS:
            exp[s] = _recent_form(h[s].tolist()) if len(h) else None
            if exp[s] is None:
                exp[s] = league[s]
        # Opponent adjustment on ACS: tougher opponent (higher Elo) -> lower ACS.
        factor = 1.0 - opponent_coef * (opp_elo.get(tid, 1500.0) - 1500.0) / 400.0
        exp_acs = exp["acs"] * factor
        row = {"player_id": pid, "handle": names.get(pid, str(pid)), "team_id": tid,
               "n_history": int(len(h)),
               "expected_acs": exp_acs, "expected_kills": exp["kills"],
               "expected_deaths": exp["deaths"], "expected_assists": exp["assists"]}
        if pid in actual.index:
            row.update(actual_acs=float(actual.loc[pid, "a_acs"]),
                       actual_kills=float(actual.loc[pid, "a_kills"]),
                       actual_deaths=float(actual.loc[pid, "a_deaths"]),
                       actual_assists=float(actual.loc[pid, "a_assists"]))
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--match-id", type=int)
    args = ap.parse_args()

    match_id = args.match_id
    if match_id is None:
        conn = sqlite3.connect(args.db)
        match_id = conn.execute(
            "SELECT m.match_id FROM matches m "
            "WHERE (m.team1_id = 624 OR m.team2_id = 624) "
            "ORDER BY m.date_utc DESC LIMIT 1").fetchone()[0]
        conn.close()
        print(f"(sample) latest PRX match: {match_id}")

    df = predict_expected_stats(match_id, db_path=args.db)
    cols = ["handle", "team_id", "n_history", "expected_acs", "actual_acs"]
    have = [c for c in cols if c in df.columns]
    print(df[have].round(1).to_string(index=False))
    if "actual_acs" in df.columns:
        mae = (df["expected_acs"] - df["actual_acs"]).abs().mean()
        print(f"\nMAE(ACS) across {len(df)} players = {mae:.1f}")


if __name__ == "__main__":
    main()
