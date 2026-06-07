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

# Static agent -> role map (the 29 agents present in the warehouse, 2026). valorant-api
# carries the canonical roles (the Phase B manifest); this static map keeps the pure
# scouting layer free of any external fetch. Roles cross-checked against the manifest —
# `Miks` (Controller) and `Veto` (Sentinel) are real newer agents, not artifacts.
AGENT_ROLES = {
    "Jett": "Duelist", "Raze": "Duelist", "Reyna": "Duelist", "Phoenix": "Duelist",
    "Yoru": "Duelist", "Neon": "Duelist", "Iso": "Duelist", "Waylay": "Duelist",
    "Brimstone": "Controller", "Omen": "Controller", "Viper": "Controller",
    "Astra": "Controller", "Harbor": "Controller", "Clove": "Controller", "Miks": "Controller",
    "Sova": "Initiator", "Breach": "Initiator", "Skye": "Initiator", "Kayo": "Initiator",
    "Fade": "Initiator", "Gekko": "Initiator", "Tejo": "Initiator",
    "Killjoy": "Sentinel", "Cypher": "Sentinel", "Sage": "Sentinel",
    "Chamber": "Sentinel", "Deadlock": "Sentinel", "Vyse": "Sentinel", "Veto": "Sentinel",
}


def agent_role(agent):
    return AGENT_ROLES.get(agent, "Unknown")


def _role_profile(counter):
    """Classify a player's agent pool from its composition alone (one-trick / flex /
    specialist) + the role they anchor. No agent-specific skill is used — none exists in
    the warehouse (DEVIATIONS 2026-06-07). ``counter`` = agent -> map count."""
    total = sum(counter.values())
    if not total:
        return None
    main_agent, main_n = counter.most_common(1)[0]
    role_n = Counter()
    for ag, c in counter.items():
        role_n[agent_role(ag)] += c
    main_share = main_n / total
    # Roles the player spends a meaningful share on (>=20% of maps), Unknown excluded.
    sig_roles = [r for r, c in role_n.items() if r != "Unknown" and c / total >= 0.20]
    label = "one-trick" if main_share >= 0.75 else "flex" if len(sig_roles) >= 2 else "specialist"
    return {
        "label": label,
        "main_agent": main_agent,
        "main_role": role_n.most_common(1)[0][0],
        "main_share": round(main_share, 2),
        "distinct_agents": len(counter),
        "roles": [{"role": r, "n": c} for r, c in role_n.most_common()],
    }


def _comp_roles(comp):
    """Role composition of a 5-agent comp, e.g. [{role: Controller, n: 2}, ...]."""
    rc = Counter(agent_role(a) for a in comp)
    return [{"role": r, "n": n} for r, n in rc.most_common()]


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


# Empirical-Bayes shrinkage toward 0.5 so a thin sample (e.g. a 5-map map pool) isn't read
# as hard truth. Same EB form as models.training_data.H2H_PRIOR; maps are the unit here.
SCOUT_PRIOR = 6.0


def _shrunk_wr(w, n, prior=SCOUT_PRIOR):
    """Sample-size-aware win rate: pulls small-n rates toward 0.5. Raw ``win_rate`` (+ n)
    is kept alongside for transparency; this drives ranking / edge / colour."""
    return round((w + prior * 0.5) / (n + prior), 3) if n else None


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
            "win_rate_adj": _shrunk_wr(v["wins"], v["n"]),
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
        comps_by_map.append({"map_name": name, "comp": list(comp), "roles": _comp_roles(comp),
                             "n": n, "win_rate": _wr(wins, n), "win_rate_adj": _shrunk_wr(wins, n)})
    comps_by_map.sort(key=lambda d: -d["n"])

    by_player = [{"handle": h, "agents": [{"agent": a, "n": c} for a, c in cnt.most_common()],
                  "profile": _role_profile(cnt)}
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


# Player-profile axes: (display label, map_player_stats column). All are per-map averages so
# no per-round normalization is needed; percentiled vs role peers (StatsBomb/HLTV method).
_PROFILE_AXES = [("ACS", "acs"), ("KAST%", "kast_pct"), ("ADR", "adr"),
                 ("HS%", "hs_pct"), ("Kills/map", "kills"), ("First kills", "fk")]


def _player_aggs(conn, min_maps):
    rows = conn.execute(
        """SELECT player_id, COUNT(*) n, AVG(acs) acs, AVG(kast_pct) kast_pct, AVG(adr) adr,
                  AVG(hs_pct) hs_pct, AVG(kills) kills, AVG(fk) fk
           FROM map_player_stats WHERE player_id IS NOT NULL
           GROUP BY player_id HAVING n >= ?""", (min_maps,)).fetchall()
    return {r["player_id"]: dict(r) for r in rows}


def _player_roles(conn):
    pool = defaultdict(Counter)
    for r in conn.execute(
        """SELECT player_id, agent, COUNT(*) c FROM map_player_stats
           WHERE player_id IS NOT NULL AND agent IS NOT NULL GROUP BY player_id, agent"""):
        pool[r["player_id"]][agent_role(r["agent"])] += r["c"]
    return {pid: cnt.most_common(1)[0][0] for pid, cnt in pool.items()}


def player_profile(conn, player_id, *, min_maps=15):
    """A player's stat profile as percentiles vs same-role peers (the pizza/percentile card).
    Role = the player's most-played role; peers = players with >= ``min_maps`` sharing it."""
    aggs = _player_aggs(conn, min_maps)
    if player_id not in aggs:
        return None
    roles = _player_roles(conn)
    role = roles.get(player_id, "Unknown")
    peers = [p for p in aggs if roles.get(p) == role]
    me = aggs[player_id]
    axes = []
    for label, col in _PROFILE_AXES:
        mine = me[col]
        vals = [aggs[p][col] for p in peers if aggs[p][col] is not None]
        if mine is None or len(vals) < 5:
            continue
        pct = round(100 * sum(1 for v in vals if v < mine) / len(vals))
        axes.append({"label": label, "value": round(mine, 1), "pct": pct})
    overall = round(sum(a["pct"] for a in axes) / len(axes)) if axes else None
    return {"role": role, "n_peers": len(peers), "n_maps": me["n"],
            "axes": axes, "overall_pct": overall}


def _recent_handles(conn, team_id, map_ids):
    if not map_ids:
        return []
    q = ",".join("?" * len(map_ids))
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT player_handle FROM map_player_stats "
        f"WHERE team_id_at_match = ? AND map_id IN ({q})", [team_id, *map_ids]).fetchall()]


def head_to_head(conn, team1_id, team2_id, *, window=WINDOW):
    """Analyst pre-match overlay: map edge, veto tendencies, comps, and the marquee
    cross-roster player duels (from the kill matrix) between the two teams (tier-2)."""
    s1 = team_scouting(conn, team1_id, window=window)
    s2 = team_scouting(conn, team2_id, window=window)
    p1 = {m["map_name"]: m for m in s1["map_pool"]}
    p2 = {m["map_name"]: m for m in s2["map_pool"]}
    map_edge = []
    for name in sorted(set(p1) | set(p2), key=lambda m: -(p1.get(m, {}).get("n", 0) + p2.get(m, {}).get("n", 0))):
        a, b = p1.get(name, {}), p2.get(name, {})
        map_edge.append({"map_name": name,
                         "t1_win_rate": a.get("win_rate"), "t1_win_rate_adj": a.get("win_rate_adj"), "t1_n": a.get("n", 0),
                         "t2_win_rate": b.get("win_rate"), "t2_win_rate_adj": b.get("win_rate_adj"), "t2_n": b.get("n", 0)})

    # Marquee duels: every time a team1 player has faced a team2 player (any match).
    h1 = _recent_handles(conn, team1_id, _recent_map_ids(conn, team1_id, window))
    h2 = _recent_handles(conn, team2_id, _recent_map_ids(conn, team2_id, window))
    key_duels = []
    if h1 and h2:
        q1, q2 = ",".join("?" * len(h1)), ",".join("?" * len(h2))
        rows = conn.execute(
            f"""SELECT player_handle, opponent_handle, SUM(kills) k, SUM(deaths) d
                FROM match_player_duels
                WHERE player_handle IN ({q1}) AND opponent_handle IN ({q2})
                GROUP BY player_handle, opponent_handle HAVING (k + d) >= 10
                ORDER BY ABS(k - d) DESC""", [*h1, *h2]).fetchall()
        key_duels = [{"t1_player": r["player_handle"], "t2_player": r["opponent_handle"],
                      "kills": r["k"], "deaths": r["d"], "net": r["k"] - r["d"]} for r in rows[:12]]

    # Head-to-head metric pairs (0..1) for the dumbbell, from the scouting we already built.
    def _form_wr(s):
        f = s.get("recent_form") or []
        return (f.count("W") / len(f)) if f else None

    def _econ(s, k):
        e = s.get("economy")
        return (e[k] / 100) if e and e.get(k) is not None else None

    pairs = [
        ("Recent win rate", _form_wr(s1), _form_wr(s2)),
        ("Opening-duel win%", (s1["opening_duels"]["team"] or {}).get("win_rate"),
         (s2["opening_duels"]["team"] or {}).get("win_rate")),
        ("Pistol win%", _econ(s1, "pistol"), _econ(s2, "pistol")),
        ("Full-buy win%", _econ(s1, "full_buy"), _econ(s2, "full_buy")),
    ]
    dumbbell = [{"label": lbl, "t1": a, "t2": b} for lbl, a, b in pairs if a is not None and b is not None]

    return {
        "map_edge": map_edge,
        "dumbbell": dumbbell,
        "form1": s1.get("recent_form", []), "form2": s2.get("recent_form", []),
        "veto1": s1["veto"], "veto2": s2["veto"],
        "comps1": s1["agents"]["comps_by_map"], "comps2": s2["agents"]["comps_by_map"],
        "key_duels": key_duels,
    }


def meta_shift(conn, team_id, *, recent_n=40, prior_n=40, min_each=2, move=0.12):
    """Per-map win-rate shift, recent window vs the prior window — surfaces maps a team has
    got better/worse on as the meta moved (e.g. "30% on Lotus, now 60%"). Shrunk rates so a
    thin per-map sample doesn't manufacture a shift; each window is anchored to its patch span.
    Per-patch splits are too thin to be meaningful here (DEVIATIONS 2026-06-07)."""
    rows = conn.execute(
        f"""SELECT mp.map_name, mp.winner_id, m.patch_id
            FROM maps mp JOIN matches m ON m.match_id = mp.match_id
            WHERE (m.team1_id = ? OR m.team2_id = ?) AND {_NOT_SHOW} AND mp.winner_id IS NOT NULL
            ORDER BY m.date_utc DESC, mp.map_index DESC LIMIT ?""",
        (team_id, team_id, recent_n + prior_n)).fetchall()
    if len(rows) < recent_n + min_each:
        return {"recent": None, "prior": None, "movers": []}

    def agg(rs):
        d = defaultdict(lambda: [0, 0])             # map_name -> [wins, n]
        patches = set()
        for r in rs:
            d[r["map_name"]][0] += 1 if r["winner_id"] == team_id else 0
            d[r["map_name"]][1] += 1
            if r["patch_id"]:
                patches.add(r["patch_id"])
        return d, patches

    rd, rp = agg(rows[:recent_n])
    pd_, pp = agg(rows[recent_n:recent_n + prior_n])
    movers = []
    for name in set(rd) | set(pd_):
        rw, rn = rd.get(name, [0, 0])
        pw, pn = pd_.get(name, [0, 0])
        if rn < min_each or pn < min_each:
            continue
        delta = _shrunk_wr(rw, rn) - _shrunk_wr(pw, pn)
        if abs(delta) >= move:
            movers.append({"map_name": name,
                           "recent_win_rate": _wr(rw, rn), "recent_n": rn,
                           "prior_win_rate": _wr(pw, pn), "prior_n": pn,
                           "delta": round(delta, 3)})
    movers.sort(key=lambda d: -abs(d["delta"]))

    def span(patches):
        return {"from": min(patches), "to": max(patches)} if patches else None
    return {"recent": {"n": min(recent_n, len(rows)), "patches": span(rp)},
            "prior": {"n": max(0, len(rows) - recent_n), "patches": span(pp)},
            "movers": movers}


def recent_form(conn, team_id, *, n=10):
    """Last ``n`` match results as 'W'/'L', oldest → newest (for a form sparkline)."""
    rows = conn.execute(
        f"""SELECT m.winner_id FROM matches m
            WHERE (m.team1_id = ? OR m.team2_id = ?) AND m.winner_id IS NOT NULL AND {_NOT_SHOW}
            ORDER BY m.date_utc DESC, m.match_id DESC LIMIT ?""",
        (team_id, team_id, n)).fetchall()
    return ["W" if r["winner_id"] == team_id else "L" for r in reversed(rows)]


def team_scouting(conn, team_id, *, window=WINDOW):
    """Full scouting report for a team over its most recent ``window`` maps."""
    map_ids = _recent_map_ids(conn, team_id, window)
    agents, duels = agents_and_duels(conn, team_id, map_ids)
    return {
        "team_id": team_id,
        "window_maps": len(map_ids),
        "recent_form": recent_form(conn, team_id),
        "map_pool": map_pool(conn, team_id, map_ids),
        "economy": economy(conn, team_id, map_ids),
        "agents": agents,
        "opening_duels": duels,
        "veto": veto_tendencies(conn, team_id),
        "impact": impact(conn, team_id),
        "meta_shift": meta_shift(conn, team_id),
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
