"""Map-specific Elo offsets via win-rate deviation + partial pooling (P3.T3).

For each (team, map) we compute the team's win rate on that map minus its overall
win rate, shrink that deviation toward 0 in proportion to sample size (partial
pooling — a team with few maps played is pulled hard toward 0), and express it in
Elo points so it can be added to the team's base Elo downstream (SPEC §6.2 Layer
2; the "map-specific Elo difference" feature in Layer 3).

    raw_dev   = map_win_rate - overall_win_rate
    shrunk    = raw_dev * games / (games + PRIOR_GAMES)
    offset    = ELO_PER_WINRATE * shrunk        # stored in elo_map_offsets

Both constants are tunable knobs (like the Elo K-factor, SPEC §6.2 Layer 1) with
conservative defaults; see DEVIATIONS 2026-06-06. Showmatches are excluded. The
offset is a single current snapshot stamped with the latest match date; the table
is fully rebuilt (idempotent).

Usage:
    python -m models.elo_map_offsets --db data/prx.db
"""

import argparse
import sqlite3

PRIOR_GAMES = 10.0       # partial-pooling strength; n maps gets weight n/(n+PRIOR)
ELO_PER_WINRATE = 400.0  # Elo points per 1.0 of (shrunk) win-rate deviation

# Per (team, map): games played and maps won, counting the team on either side,
# excluding showmatches.
_AGG_SQL = """
    SELECT team_id, map_name, COUNT(*) AS games, SUM(won) AS wins FROM (
        SELECT m.team1_id AS team_id, mp.map_name AS map_name,
               (mp.winner_id = m.team1_id) AS won
        FROM maps mp JOIN matches m ON m.match_id = mp.match_id
        WHERE m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%'
        UNION ALL
        SELECT m.team2_id, mp.map_name, (mp.winner_id = m.team2_id)
        FROM maps mp JOIN matches m ON m.match_id = mp.match_id
        WHERE m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%'
    )
    GROUP BY team_id, map_name
"""


def compute_map_offsets(conn, *, prior_games=PRIOR_GAMES, elo_per_winrate=ELO_PER_WINRATE):
    """Rebuild the elo_map_offsets table; return {(team_id, map_name): offset}.

    Full DELETE-then-insert, so it is idempotent. Rows are stamped with the
    latest match date in the warehouse (a single current snapshot).
    """
    as_of_date = conn.execute("SELECT MAX(date_utc) FROM matches").fetchone()[0]
    if as_of_date is not None:
        as_of_date = as_of_date[:10]

    # Group the per-(team, map) aggregate by team so we can form each team's
    # overall win rate from its own map totals.
    by_team = {}
    for r in conn.execute(_AGG_SQL):
        by_team.setdefault(r["team_id"], []).append(
            (r["map_name"], r["games"], r["wins"])
        )

    offsets = {}
    rows = []
    for team_id, maps in by_team.items():
        total_games = sum(g for _, g, _ in maps)
        total_wins = sum(w for _, _, w in maps)
        overall_wr = total_wins / total_games  # total_games >= 1 (team is in by_team)
        for map_name, games, wins in maps:
            raw_dev = wins / games - overall_wr
            shrunk = raw_dev * games / (games + prior_games)
            offset = elo_per_winrate * shrunk
            offsets[(team_id, map_name)] = offset
            rows.append((team_id, map_name, as_of_date, offset))

    conn.execute("DELETE FROM elo_map_offsets")
    conn.executemany(
        "INSERT INTO elo_map_offsets (team_id, map_name, as_of_date, rating_offset) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return offsets


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    ap.add_argument("--prior", type=float, default=PRIOR_GAMES)
    ap.add_argument("--scale", type=float, default=ELO_PER_WINRATE)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    offsets = compute_map_offsets(conn, prior_games=args.prior, elo_per_winrate=args.scale)
    print(f"Wrote {len(offsets)} (team, map) offsets "
          f"(prior={args.prior}, scale={args.scale}).")

    # PRX (team_id 624) spot-check — the done-when target.
    names = {r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")}
    prx = sorted(((mn, off) for (tid, mn), off in offsets.items() if tid == 624),
                 key=lambda x: x[1], reverse=True)
    if prx:
        print(f"-- Paper Rex map offsets ({len(prx)} maps, sum={sum(o for _, o in prx):+.2f}) --")
        for mn, off in prx:
            print(f"  {mn:10} {off:+7.2f}")
    conn.close()


if __name__ == "__main__":
    main()
