"""Score-state empirical lookup — P(win map | score state) (P3.T6).

For every pre-round score state we count how often the team in that state went on
to win the **map**, then Laplace-smooth. Each historical round yields two
observations (one per team's perspective): the state is
``(half, team_score, opp_score, side)`` from a team's point of view, labelled 1 if
that team won the map. Smoothing: ``(wins + 5) / (observations + 10)``.

Showmatches are excluded. OT states ('ot' half) are included alongside first/second
— they are real states the live predictor (P3.T7/Phase 5) will hit. The table is
fully rebuilt (idempotent).

Usage:
    python -m models.score_state --db data/prx.db
"""

import argparse
import sqlite3
from collections import defaultdict

LAPLACE_NUM = 5
LAPLACE_DEN = 10

# All rounds of completed, non-showmatch maps, ordered so we can walk the score.
_ROUNDS_SQL = """
    SELECT mp.map_id, mp.winner_id AS map_winner,
           m.team1_id, m.team2_id,
           r.round_number, r.half, r.team1_side, r.team2_side,
           r.winner_id AS round_winner
    FROM rounds r
    JOIN maps mp ON mp.map_id = r.map_id
    JOIN matches m ON m.match_id = mp.match_id
    WHERE mp.winner_id IS NOT NULL
      AND (m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')
    ORDER BY mp.map_id, r.round_number
"""


def compute_score_state(conn, *, laplace_num=LAPLACE_NUM, laplace_den=LAPLACE_DEN):
    """Rebuild score_state_lookup; return {(half, team_score, opp_score, side): (obs, wins)}."""
    agg = defaultdict(lambda: [0, 0])  # -> [n_observations, n_wins]

    cur_map = None
    t1 = t2 = 0
    t1_id = t2_id = map_winner = None
    for r in conn.execute(_ROUNDS_SQL):
        if r["map_id"] != cur_map:
            cur_map = r["map_id"]
            t1 = t2 = 0
            t1_id, t2_id, map_winner = r["team1_id"], r["team2_id"], r["map_winner"]

        half = r["half"]
        # Pre-round state, both perspectives. win = this team won the MAP.
        k1 = (half, t1, t2, r["team1_side"])
        agg[k1][0] += 1
        if map_winner == t1_id:
            agg[k1][1] += 1
        k2 = (half, t2, t1, r["team2_side"])
        agg[k2][0] += 1
        if map_winner == t2_id:
            agg[k2][1] += 1

        # Advance the running score by this round's winner.
        if r["round_winner"] == t1_id:
            t1 += 1
        elif r["round_winner"] == t2_id:
            t2 += 1

    rows = [
        (half, ts, op, side, obs, wins, (wins + laplace_num) / (obs + laplace_den))
        for (half, ts, op, side), (obs, wins) in agg.items()
    ]
    conn.execute("DELETE FROM score_state_lookup")
    conn.executemany(
        "INSERT INTO score_state_lookup "
        "(half, team_score, opp_score, side, n_observations, n_wins, smoothed_win_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    agg = compute_score_state(conn)

    total_obs = sum(o for o, _ in agg.values())
    print(f"states: {len(agg)}; observations: {total_obs}")

    print("-- spot checks (smoothed P(win map)) --")
    checks = [
        ("first", 0, 0, "ct"), ("first", 0, 0, "t"),
        ("second", 9, 3, "ct"), ("second", 3, 9, "ct"),
        ("second", 11, 1, "t"), ("second", 1, 11, "t"),
    ]
    for half, ts, op, side in checks:
        row = conn.execute(
            "SELECT n_wins, n_observations, smoothed_win_pct FROM score_state_lookup "
            "WHERE half=? AND team_score=? AND opp_score=? AND side=?",
            (half, ts, op, side),
        ).fetchone()
        if row:
            print(f"  {half:6} {ts:2}-{op:<2} {side:2}: "
                  f"{row['smoothed_win_pct']:.3f}  ({row['n_wins']}/{row['n_observations']})")
        else:
            print(f"  {half:6} {ts:2}-{op:<2} {side:2}: (no data)")
    conn.close()


if __name__ == "__main__":
    main()
