"""Opponent scouting analytics (Wave B — analyst scouting, tier-1, no re-ingestion).

Everything here is derived from data already in the warehouse — `maps` (side
scores), `map_team_economy`, `map_player_stats` (agent, fk, fd) — over a team's most
recent N maps (recent meta is what an analyst scouting an upcoming match wants):

- **map pool + side tendencies**: per map, played / win-rate / CT-win% / T-win%
- **economy efficiency**: pistol / eco / semi-buy / full-buy win%
- **agent comps**: the team's most-run 5-agent comp per map (+ win-rate), and each
  player's agent pool
- **opening duels**: first-kill vs first-death (entry win-rate), team + per player

Pure: takes a sqlite connection, returns plain dicts. Window defaults to the last
30 maps. Reused by GET /api/teams/{id}/scouting.
"""

import sqlite3
from collections import Counter, defaultdict

DB_DEFAULT = "data/prx.db"
WINDOW = 30
_NOT_SHOW = "(m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')"


def _recent_map_ids(conn, team_id, n):
    rows = conn.execute(
        f"""SELECT mp.map_id FROM maps mp JOIN matches m ON m.match_id = mp.match_id
            WHERE (m.team1_id = ? OR m.team2_id = ?) AND {_NOT_SHOW}
              AND mp.winner_id IS NOT NULL
            ORDER BY m.date_utc DESC, mp.map_index DESC LIMIT ?""",
        (team_id, team_id, n),
    ).fetchall()
    return [r[0] for r in rows]


def _wr(w, n):
    return round(w / n, 3) if n else None


def map_pool(conn, team_id, map_ids):
    """Per map_name: n, win-rate, and the team's CT/T side win-rates."""
    if not map_ids:
        return []
    q = ",".join("?" * len(map_ids))
    rows = conn.execute(
        f"""SELECT mp.map_name, m.team1_id, mp.winner_id,
                   mp.team1_ct_score, mp.team1_t_score, mp.team2_ct_score, mp.team2_t_score
            FROM maps mp JOIN matches m ON m.match_id = mp.match_id
            WHERE mp.map_id IN ({q})""",
        map_ids,
    ).fetchall()
    agg = defaultdict(lambda: {"n": 0, "wins": 0, "ct_w": 0, "ct_tot": 0, "t_w": 0, "t_tot": 0})
    for r in rows:
        is_t1 = r["team1_id"] == team_id
        team_ct = r["team1_ct_score"] if is_t1 else r["team2_ct_score"]
        team_t = r["team1_t_score"] if is_t1 else r["team2_t_score"]
        opp_ct = r["team2_ct_score"] if is_t1 else r["team1_ct_score"]
        opp_t = r["team2_t_score"] if is_t1 else r["team1_t_score"]
        if None in (team_ct, team_t, opp_ct, opp_t):
            continue
        a = agg[r["map_name"]]
        a["n"] += 1
        a["wins"] += 1 if r["winner_id"] == team_id else 0
        # On the team's CT half the opponent is on T, so CT rounds = team_ct + opp_t.
        a["ct_w"] += team_ct
        a["ct_tot"] += team_ct + opp_t
        a["t_w"] += team_t
        a["t_tot"] += team_t + opp_ct
    out = [{"map_name": k, "n": v["n"], "win_rate": _wr(v["wins"], v["n"]),
            "ct_win_rate": _wr(v["ct_w"], v["ct_tot"]), "t_win_rate": _wr(v["t_w"], v["t_tot"])}
           for k, v in agg.items()]
    return sorted(out, key=lambda d: -d["n"])


def economy(conn, team_id, map_ids):
    """Average buy-type win% over the window (stored as win% per map already)."""
    if not map_ids:
        return None
    q = ",".join("?" * len(map_ids))
    r = conn.execute(
        f"""SELECT ROUND(AVG(pistol_win_pct), 1) pistol, ROUND(AVG(eco_win_pct), 1) eco,
                   ROUND(AVG(semi_buy_win_pct), 1) semi_buy, ROUND(AVG(full_buy_win_pct), 1) full_buy
            FROM map_team_economy
            WHERE team_id_at_match = ? AND map_id IN ({q})""",
        [team_id, *map_ids],
    ).fetchone()
    return dict(r) if r else None


def _player_rows(conn, team_id, map_ids):
    q = ",".join("?" * len(map_ids))
    return conn.execute(
        f"""SELECT mps.map_id, mps.player_handle AS handle, mps.agent, mps.fk, mps.fd,
                   mp.map_name, mp.winner_id, mps.team_id_at_match
            FROM map_player_stats mps JOIN maps mp ON mp.map_id = mps.map_id
            WHERE mps.team_id_at_match = ? AND mps.map_id IN ({q})""",
        [team_id, *map_ids],
    ).fetchall()


def agents_and_duels(conn, team_id, map_ids):
    """Agent pools per player, most-run comp per map, and opening-duel win rates."""
    if not map_ids:
        return {"by_player": [], "comps_by_map": []}, {"team": None, "by_player": []}
    rows = _player_rows(conn, team_id, map_ids)

    pool = defaultdict(Counter)                 # handle -> agent counts
    duel = defaultdict(lambda: [0, 0])          # handle -> [fk, fd]
    comp_per_map = defaultdict(list)            # map_id -> [agents]
    map_meta = {}                               # map_id -> (map_name, won)
    for r in rows:
        pool[r["handle"]][r["agent"]] += 1
        duel[r["handle"]][0] += r["fk"] or 0
        duel[r["handle"]][1] += r["fd"] or 0
        comp_per_map[r["map_id"]].append(r["agent"])
        map_meta[r["map_id"]] = (r["map_name"], r["winner_id"] == team_id)

    # Most common comp per map_name (a comp = the sorted 5-agent set).
    comp_stats = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # map_name -> comp -> [n, wins]
    for map_id, agents in comp_per_map.items():
        if len(agents) != 5:
            continue
        comp = tuple(sorted(agents))
        name, won = map_meta[map_id]
        comp_stats[name][comp][0] += 1
        comp_stats[name][comp][1] += 1 if won else 0
    comps_by_map = []
    for name, comps in comp_stats.items():
        comp, (n, wins) = max(comps.items(), key=lambda kv: kv[1][0])
        comps_by_map.append({"map_name": name, "comp": list(comp), "n": n, "win_rate": _wr(wins, n)})
    comps_by_map.sort(key=lambda d: -d["n"])

    by_player = [{"handle": h, "agents": [{"agent": a, "n": c} for a, c in cnt.most_common()]}
                 for h, cnt in sorted(pool.items())]

    team_fk = sum(v[0] for v in duel.values())
    team_fd = sum(v[1] for v in duel.values())
    duels_by_player = sorted(
        ({"handle": h, "fk": fk, "fd": fd, "win_rate": _wr(fk, fk + fd)}
         for h, (fk, fd) in duel.items()),
        key=lambda d: -(d["win_rate"] or 0))
    duels = {"team": {"fk": team_fk, "fd": team_fd, "win_rate": _wr(team_fk, team_fk + team_fd)},
             "by_player": duels_by_player}
    return {"by_player": by_player, "comps_by_map": comps_by_map}, duels


def veto_tendencies(conn, team_id, n_matches=20):
    """Most-banned / most-picked maps over the team's recent matches (tier-2)."""
    matches = [r[0] for r in conn.execute(
        f"""SELECT m.match_id FROM matches m
            WHERE (m.team1_id = ? OR m.team2_id = ?) AND {_NOT_SHOW}
            ORDER BY m.date_utc DESC LIMIT ?""", (team_id, team_id, n_matches)).fetchall()]
    if not matches:
        return {"bans": [], "picks": [], "n_matches": 0}
    q = ",".join("?" * len(matches))
    rows = conn.execute(
        f"SELECT action, map_name FROM match_veto WHERE team_id = ? AND match_id IN ({q})",
        [team_id, *matches]).fetchall()
    bans, picks = Counter(), Counter()
    for r in rows:
        (bans if r["action"] == "ban" else picks if r["action"] == "pick" else Counter())[r["map_name"]] += 1
    return {"n_matches": len(matches),
            "bans": [{"map_name": k, "n": v} for k, v in bans.most_common()],
            "picks": [{"map_name": k, "n": v} for k, v in picks.most_common()]}


def _recent_match_ids(conn, team_id, n):
    return [r[0] for r in conn.execute(
        f"""SELECT m.match_id FROM matches m
            WHERE (m.team1_id = ? OR m.team2_id = ?) AND {_NOT_SHOW}
            ORDER BY m.date_utc DESC LIMIT ?""", (team_id, team_id, n)).fetchall()]


def impact(conn, team_id, n_matches=20):
    """Per-player clutches / multikills / plants / defuses over recent matches (tier-2).

    match_player_advanced is match-level (vlr's performance tab), so aggregate over
    matches, not maps.
    """
    matches = _recent_match_ids(conn, team_id, n_matches)
    if not matches:
        return []
    q = ",".join("?" * len(matches))
    rows = conn.execute(
        f"""SELECT a.player_handle,
                   SUM(a.cl1 + a.cl2 + a.cl3 + a.cl4 + a.cl5) AS clutches,
                   SUM(a.cl3 + a.cl4 + a.cl5) AS big_clutches,
                   SUM(a.mk2 + a.mk3 + a.mk4 + a.mk5) AS multikills,
                   SUM(a.mk4 + a.mk5) AS big_multikills,
                   SUM(a.plants) AS plants, SUM(a.defuses) AS defuses
            FROM match_player_advanced a
            WHERE a.match_id IN ({q}) AND a.player_handle IN (
                SELECT DISTINCT mps.player_handle FROM map_player_stats mps
                JOIN maps mp ON mp.map_id = mps.map_id
                WHERE mp.match_id IN ({q}) AND mps.team_id_at_match = ?)
            GROUP BY a.player_handle ORDER BY clutches DESC""",
        [*matches, *matches, team_id]).fetchall()
    return [dict(r) for r in rows]


def player_duels(conn, player_handle, *, n_matches=25, min_duels=12, top=5):
    """A player's best/worst head-to-head opponents over recent matches (tier-2)."""
    matches = [r[0] for r in conn.execute(
        f"""SELECT DISTINCT mp.match_id FROM map_player_stats mps
            JOIN maps mp ON mp.map_id = mps.map_id JOIN matches m ON m.match_id = mp.match_id
            WHERE mps.player_handle = ? AND {_NOT_SHOW}
            ORDER BY mp.match_id DESC LIMIT ?""", (player_handle, n_matches)).fetchall()]
    if not matches:
        return {"best": [], "worst": []}
    q = ",".join("?" * len(matches))
    rows = conn.execute(
        f"""SELECT opponent_handle, SUM(kills) k, SUM(deaths) d
            FROM match_player_duels WHERE player_handle = ? AND match_id IN ({q})
            GROUP BY opponent_handle HAVING (k + d) >= ?
            ORDER BY (k - d) DESC""", [player_handle, *matches, min_duels]).fetchall()
    duels = [{"opponent": r["opponent_handle"], "kills": r["k"], "deaths": r["d"], "net": r["k"] - r["d"]}
             for r in rows]
    return {"best": duels[:top], "worst": list(reversed(duels[-top:])) if len(duels) > top else []}


def team_scouting(conn, team_id, *, window=WINDOW):
    """Full scouting report for a team over its most recent ``window`` maps."""
    map_ids = _recent_map_ids(conn, team_id, window)
    agents, duels = agents_and_duels(conn, team_id, map_ids)
    return {
        "team_id": team_id,
        "window_maps": len(map_ids),
        "map_pool": map_pool(conn, team_id, map_ids),
        "economy": economy(conn, team_id, map_ids),
        "agents": agents,
        "opening_duels": duels,
        "veto": veto_tendencies(conn, team_id),
        "impact": impact(conn, team_id),
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--team", type=int, default=624)
    ap.add_argument("--window", type=int, default=WINDOW)
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    s = team_scouting(conn, args.team, window=args.window)
    conn.close()
    print(f"team {args.team} | window {s['window_maps']} maps")
    print("map pool:")
    for m in s["map_pool"]:
        print(f"  {m['map_name']:10} n={m['n']:2} wr={m['win_rate']} ct={m['ct_win_rate']} t={m['t_win_rate']}")
    print("economy:", s["economy"])
    print("comps by map:")
    for c in s["agents"]["comps_by_map"]:
        print(f"  {c['map_name']:10} {c['comp']} n={c['n']} wr={c['win_rate']}")
    print("opening duels (team):", s["opening_duels"]["team"])
    for d in s["opening_duels"]["by_player"]:
        print(f"  {d['handle']:12} fk={d['fk']} fd={d['fd']} odwr={d['win_rate']}")


if __name__ == "__main__":
    main()
