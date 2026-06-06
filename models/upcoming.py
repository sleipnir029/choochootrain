"""As-of-now feature builder for an UPCOMING (unplayed) match (P6.T2).

``models.training_data.build_training_data`` only emits rows for maps already in
the warehouse, and the ``matches`` table holds completed matches only (P2.T5). So
D3's default view — "pre-match panel for PRX's next scheduled match" — has no row
to predict. This module closes that long-standing gap (flagged since P3.T7/P5.T3).

``build_upcoming_features(conn, team1_id, team2_id)`` returns a one-row DataFrame
with the same feature columns the Bambi ``FORMULA`` expects, computed *as of now*
from the snapshot/history tables rather than point-in-time replay (no leakage —
"now" is genuinely after all ingested data):

    elo_diff                 latest elo_ratings, team1 - team2
    map_elo_diff             = elo_diff (map unknown until veto -> zero offsets)
    skill_diff               mean player_skill.mu over each team's active roster
    team1_starts_atk_or_def  0 (side unknown until veto; matches the training fallback)
    recent_form_team1/2      win fraction over each team's last 5 completed maps
    h2h_team1_win_rate       map-level H2H, EB-shrunk toward 0.5 (same as training)
    tier, patch_id           event tier (or default) + latest patch

``predict_upcoming_win_prob`` runs that row through ``models.predict``'s cached
Bambi model and returns ``{team1_win_prob, hdi, top_factors}`` (same shape as
``models.predict.predict_map_win_prob_detailed``).

Usage:
    python -m models.upcoming --db data/prx.db --team1 624 --team2 188
"""

import argparse
import datetime as _dt
import sqlite3

import pandas as pd

from models.training_data import FORM_WINDOW, H2H_PRIOR

DB_DEFAULT = "data/prx.db"
DEFAULT_TIER = "RegionalLeague"   # most common trained level; overridden if event known

_NOT_SHOWMATCH = "(m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')"


def _today():
    return _dt.date.today().isoformat()


def _latest_elo(conn, team_id, initial=1500.0):
    row = conn.execute(
        "SELECT rating FROM elo_ratings WHERE team_id = ? "
        "ORDER BY as_of_date DESC LIMIT 1",
        (team_id,),
    ).fetchone()
    return float(row[0]) if row else initial


def _roster_skill(conn, team_id, as_of_date):
    """Mean TrueSkill mu over the team's active roster as of ``as_of_date``.

    Returns None if no rostered player has a skill rating (caller -> neutral).
    """
    row = conn.execute(
        """
        SELECT AVG(ps.mu)
        FROM roster_history r
        JOIN (
            SELECT player_id, mu,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY as_of_date DESC) AS rn
            FROM player_skill
            WHERE agent IS NULL AND map_name IS NULL
        ) ps ON ps.player_id = r.player_id AND ps.rn = 1
        WHERE r.team_id = ? AND r.role = 'player'
          AND r.joined_date <= ?
          AND (r.left_date IS NULL OR r.left_date >= ?)
        """,
        (team_id, as_of_date, as_of_date),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _recent_form(conn, team_id, as_of_date):
    """Win fraction over the team's last FORM_WINDOW completed maps before the date."""
    rows = conn.execute(
        f"""
        SELECT mp.winner_id
        FROM maps mp JOIN matches m ON m.match_id = mp.match_id
        WHERE (m.team1_id = ? OR m.team2_id = ?) AND {_NOT_SHOWMATCH}
          AND mp.winner_id IS NOT NULL AND m.date_utc < ?
        ORDER BY m.date_utc DESC, mp.map_index DESC
        LIMIT ?
        """,
        (team_id, team_id, as_of_date, FORM_WINDOW),
    ).fetchall()
    if not rows:
        return 0.5
    return sum(1 for r in rows if r[0] == team_id) / len(rows)


def _h2h_rate(conn, team1_id, team2_id, as_of_date):
    """Map-level H2H win rate for team1, EB-shrunk toward 0.5 (training formula)."""
    rows = conn.execute(
        f"""
        SELECT mp.winner_id
        FROM maps mp JOIN matches m ON m.match_id = mp.match_id
        WHERE {_NOT_SHOWMATCH} AND mp.winner_id IS NOT NULL AND m.date_utc < ?
          AND ((m.team1_id = ? AND m.team2_id = ?)
               OR (m.team1_id = ? AND m.team2_id = ?))
        """,
        (as_of_date, team1_id, team2_id, team2_id, team1_id),
    ).fetchall()
    total = len(rows)
    t1_wins = sum(1 for r in rows if r[0] == team1_id)
    return (t1_wins + H2H_PRIOR * 0.5) / (total + H2H_PRIOR)


def _latest_patch(conn):
    row = conn.execute(
        "SELECT patch_id FROM patches ORDER BY release_date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _event_tier(conn, event_id):
    row = conn.execute(
        "SELECT tier FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return row[0] if row else None


def build_upcoming_features(conn, team1_id, team2_id, *, as_of_date=None,
                            tier=None, patch_id=None):
    """One-row DataFrame of as-of-now features for an unplayed team1-vs-team2 match."""
    as_of_date = as_of_date or _today()

    e1, e2 = _latest_elo(conn, team1_id), _latest_elo(conn, team2_id)
    s1 = _roster_skill(conn, team1_id, as_of_date)
    s2 = _roster_skill(conn, team2_id, as_of_date)
    skill_diff = (s1 - s2) if (s1 is not None and s2 is not None) else 0.0

    tier = tier or DEFAULT_TIER
    patch_id = patch_id or _latest_patch(conn)

    row = {
        "elo_diff": e1 - e2,
        "map_elo_diff": e1 - e2,            # no map offset until veto
        "skill_diff": skill_diff,
        "team1_starts_atk_or_def": 0,        # side unknown until veto (training fallback)
        "recent_form_team1": _recent_form(conn, team1_id, as_of_date),
        "recent_form_team2": _recent_form(conn, team2_id, as_of_date),
        "h2h_team1_win_rate": _h2h_rate(conn, team1_id, team2_id, as_of_date),
        "tier": tier,
        "patch_id": patch_id,
    }
    return pd.DataFrame([row])


def predict_upcoming_win_prob(team1_id, team2_id, *, as_of_date=None, tier=None,
                              event_id=None, db_path=DB_DEFAULT):
    """As-of-now P(team1 wins a map) + HDI + top factors for an unplayed match."""
    import models.predict as predict

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if tier is None and event_id is not None:
            tier = _event_tier(conn, event_id)
        df_train, model, idata, _, _ = predict._resources(db_path)
        # Clamp tier to a level the model was trained on (C(tier) is a fixed effect).
        known_tiers = set(df_train["tier"].unique())
        if tier not in known_tiers:
            tier = DEFAULT_TIER if DEFAULT_TIER in known_tiers else df_train["tier"].mode()[0]
        row = build_upcoming_features(conn, team1_id, team2_id,
                                      as_of_date=as_of_date, tier=tier)
    finally:
        conn.close()

    return predict.detailed_from_row(model, idata, row, df_train)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--team1", type=int, default=624)   # Paper Rex
    ap.add_argument("--team2", type=int, default=188)   # Sentinels
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    feats = build_upcoming_features(conn, args.team1, args.team2)
    conn.close()
    print("features:")
    print(feats.T.to_string())
    print(f"NaN cells: {int(feats.isna().sum().sum())}")

    out = predict_upcoming_win_prob(args.team1, args.team2, db_path=args.db)
    print(f"\nP(team{args.team1} wins a map): {out['team1_win_prob']:.3f} "
          f"HDI {out['hdi'][0]:.3f}-{out['hdi'][1]:.3f}")
    print("top factors:")
    for f in out["top_factors"]:
        print(f"  {f['factor']:<24} weight {f['weight']:.2f}  favors {f['favors']}")


if __name__ == "__main__":
    main()
