"""Replay map_player_stats chronologically to compute current player TrueSkill (P4.T2).

Walks every resolved per-map player stat in date order. Each map is one
TrueSkill round: a player's performance is their ACS minus the opposing team's
average ACS (sign = out/under-performed), and their opponent is the aggregate
(mean mu, mean sigma) of the five opposing players' *current* ratings. All ten
players on a map update from pre-map ratings (no within-map leakage), then the
state advances. Writes the current **overall** rating per player (agent/map_name
NULL) to player_skill, stamped with that player's last-played date. Per-(agent,
map) ratings are deferred until a consumer needs them (P4.T3). Showmatches and
rows without a resolved player_id or ACS are excluded.

Usage:
    python -m scripts.build_player_skill --db data/prx.db [--min-maps 10]
"""

import argparse
import sqlite3
from collections import defaultdict

from models.player_skill import new_rating, update_skill

_STATS_SQL = """
    SELECT mps.map_id, mps.player_id, mps.team_id_at_match, mps.acs,
           m.date_utc, m.team1_id
    FROM map_player_stats mps
    JOIN maps mp ON mp.map_id = mps.map_id
    JOIN matches m ON m.match_id = mp.match_id
    WHERE mps.player_id IS NOT NULL AND mps.acs IS NOT NULL
      AND (m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')
    ORDER BY m.date_utc, mps.map_id
"""


def _aggregate(players, ratings):
    """A notional opponent Rating: mean mu and mean sigma of `players` (player_id, acs)."""
    rs = [ratings.get(pid, new_rating()) for pid, _ in players]
    return new_rating(sum(r.mu for r in rs) / len(rs),
                      sum(r.sigma for r in rs) / len(rs))


def _update_map_ratings(teams, ratings):
    """Apply one map's TrueSkill update to `ratings` in place; return updated player_ids.

    `teams`: {team_id: [(player_id, acs)]}. Each player's performance is their ACS
    minus the opposing team's average ACS, vs the aggregate opposing rating. Uses
    pre-map ratings for everyone (no within-map leakage).
    """
    (ta, pa), (tb, pb) = list(teams.items())
    avg_a = sum(a for _, a in pa) / len(pa)
    avg_b = sum(a for _, a in pb) / len(pb)
    opp_for_a = _aggregate(pb, ratings)       # team A's opponent = team B
    opp_for_b = _aggregate(pa, ratings)
    updated = {}
    for pid, acs in pa:
        updated[pid] = update_skill(pid, None, None, acs - avg_b, opp_for_a,
                                    current=ratings.get(pid, new_rating()))
    for pid, acs in pb:
        updated[pid] = update_skill(pid, None, None, acs - avg_a, opp_for_b,
                                    current=ratings.get(pid, new_rating()))
    ratings.update(updated)
    return updated.keys()


def _iter_maps(conn):
    """Yield (map_id, team1_id, date, [(player_id, team_id, acs), ...]) per map, in order."""
    cur_map, buf, date, t1 = None, [], None, None
    for row in conn.execute(_STATS_SQL):
        if row["map_id"] != cur_map:
            if buf:
                yield cur_map, t1, date, buf
            cur_map, buf = row["map_id"], []
            date, t1 = row["date_utc"][:10], row["team1_id"]
        buf.append((row["player_id"], row["team_id_at_match"], row["acs"]))
    if buf:
        yield cur_map, t1, date, buf


def replay(conn):
    """Return (ratings, last_date, maps_played) after the chronological replay."""
    ratings = {}            # player_id -> Rating
    last_date = {}          # player_id -> ISO date of last map
    maps_played = defaultdict(int)
    for _map_id, _t1, date, rows in _iter_maps(conn):
        teams = defaultdict(list)
        for pid, tid, acs in rows:
            teams[tid].append((pid, acs))
        if len(teams) != 2:
            continue
        for pid in _update_map_ratings(teams, ratings):
            last_date[pid] = date
            maps_played[pid] += 1
    return ratings, last_date, maps_played


def replay_skill_diffs(conn):
    """Return {map_id: skill_diff} where skill_diff = mean mu(team1) - mean mu(team2).

    Point-in-time team-skill feature for the map-prediction lift experiment: the
    diff uses **pre-map** ratings (oriented to the match's team1), then the map
    advances the ratings. No leakage.
    """
    ratings = {}
    diffs = {}

    def _team_mu(players):
        return sum(ratings.get(pid, new_rating()).mu for pid, _ in players) / len(players)

    for map_id, t1, _date, rows in _iter_maps(conn):
        teams = defaultdict(list)
        for pid, tid, acs in rows:
            teams[tid].append((pid, acs))
        if len(teams) != 2 or t1 not in teams:
            continue
        t2 = next(tid for tid in teams if tid != t1)
        diffs[map_id] = _team_mu(teams[t1]) - _team_mu(teams[t2])  # pre-map
        _update_map_ratings(teams, ratings)
    return diffs


def build(conn):
    ratings, last_date, maps_played = replay(conn)
    conn.execute("DELETE FROM player_skill")
    conn.executemany(
        "INSERT INTO player_skill (player_id, agent, map_name, as_of_date, mu, sigma) "
        "VALUES (?, NULL, NULL, ?, ?, ?)",
        [(pid, last_date[pid], r.mu, r.sigma) for pid, r in ratings.items()],
    )
    conn.commit()
    return ratings, maps_played


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    ap.add_argument("--min-maps", type=int, default=10)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    ratings, maps_played = build(conn)

    eligible = [pid for pid in ratings if maps_played[pid] >= args.min_maps]
    print(f"players rated: {len(ratings)}; with >={args.min_maps} maps: {len(eligible)}")

    names = {r["player_id"]: r["handle"] for r in conn.execute(
        "SELECT player_id, handle FROM players")}
    # Conservative skill estimate (mu - 3*sigma) ranks players who have proven it.
    top = sorted(eligible, key=lambda p: ratings[p].mu - 3 * ratings[p].sigma, reverse=True)[:15]
    print(f"-- top {len(top)} by conservative skill (mu - 3*sigma) --")
    for rank, pid in enumerate(top, 1):
        r = ratings[pid]
        print(f"  {rank:2}. {names.get(pid, f'id {pid}'):16} "
              f"mu={r.mu:5.2f} sigma={r.sigma:4.2f} maps={maps_played[pid]}")
    conn.close()


if __name__ == "__main__":
    main()
