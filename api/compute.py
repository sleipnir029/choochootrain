"""View-shaped composition for the PRX-centric dashboard (P6 revision).

Aggregates the existing model outputs (pre-match prediction, replay trace,
expected-vs-actual) + warehouse reads into one payload per screen, and attaches
the templated narrative from ``api.insight``. Heavy model imports stay lazy.
"""

from api import insight
from api.routes.predict import _pre_match_ingested, build_replay, PRX_TEAM_ID

_STATS = ["acs", "kills", "deaths", "assists"]
_RECENT_CACHE = {}  # recent-results is static between restarts -> cache per (db, limit)


def prx_side(team1_id, team2_id):
    return "team1" if team1_id == PRX_TEAM_ID else "team2" if team2_id == PRX_TEAM_ID else None


def prx_rank(conn):
    """PRX's rank among tier-1 teams by latest Elo (None if unrated)."""
    rows = conn.execute(
        """SELECT team_id, rating FROM elo_ratings e
           WHERE as_of_date = (SELECT MAX(as_of_date) FROM elo_ratings WHERE team_id = e.team_id)"""
    ).fetchall()
    ranked = sorted(((r["team_id"], r["rating"]) for r in rows), key=lambda x: -x[1])
    for i, (tid, rating) in enumerate(ranked, 1):
        if tid == PRX_TEAM_ID:
            return {"rank": i, "of": len(ranked), "rating": round(rating)}
    return None


def roster_with_skill(conn, team_id):
    """Active roster (left_date IS NULL, role=player) with conservative skill (mu-3σ)."""
    rows = conn.execute(
        """SELECT p.player_id, p.handle, p.real_name, p.country, ps.mu, ps.sigma
           FROM roster_history r JOIN players p ON p.player_id = r.player_id
           LEFT JOIN (
               SELECT player_id, mu, sigma,
                      ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY as_of_date DESC) rn
               FROM player_skill WHERE agent IS NULL AND map_name IS NULL
           ) ps ON ps.player_id = p.player_id AND ps.rn = 1
           WHERE r.team_id = ? AND r.left_date IS NULL AND r.role = 'player'
           GROUP BY p.player_id
           ORDER BY ps.mu DESC""",
        (team_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = {k: r[k] for k in ("player_id", "handle", "real_name", "country")}
        d["skill"] = round(r["mu"] - 3 * r["sigma"], 1) if r["mu"] is not None else None
        out.append(d)
    return out


def expected_records(match_id, db_path):
    """predict_expected_stats(match_id) -> list of dicts (rounded; delta_acs if actual present)."""
    try:
        from models.expected_stats import predict_expected_stats
        df = predict_expected_stats(match_id, db_path=db_path)
    except Exception:
        return []
    out = []
    for r in df.to_dict("records"):
        rec = {"player_id": int(r["player_id"]), "handle": r["handle"],
               "team_id": int(r["team_id"]), "n_history": int(r["n_history"])}
        for s in _STATS:
            rec[f"expected_{s}"] = round(r[f"expected_{s}"], 1)
            if f"actual_{s}" in r and r[f"actual_{s}"] is not None:
                rec[f"actual_{s}"] = round(r[f"actual_{s}"], 1)
        if "actual_acs" in rec:
            rec["delta_acs"] = round(rec["actual_acs"] - rec["expected_acs"], 1)
        out.append(rec)
    return out


def recent_prx_results(conn, db_path, limit=6):
    """Recent completed PRX matches with the model's pre-match call vs the result."""
    key = (db_path, limit)
    if key in _RECENT_CACHE:
        return _RECENT_CACHE[key]
    from models.predict import predict_map_win_prob

    rows = conn.execute(
        """SELECT match_id, team1_id, team2_id, team1_score, team2_score, winner_id, date_utc
           FROM matches
           WHERE (team1_id = ? OR team2_id = ?) AND winner_id IS NOT NULL
             AND (series_name IS NULL OR series_name NOT LIKE 'Showmatch%')
           ORDER BY date_utc DESC, match_id DESC LIMIT ?""",
        (PRX_TEAM_ID, PRX_TEAM_ID, limit),
    ).fetchall()

    out = []
    for r in rows:
        side = prx_side(r["team1_id"], r["team2_id"])
        maps = conn.execute(
            "SELECT map_index FROM maps WHERE match_id = ? ORDER BY map_index", (r["match_id"],)
        ).fetchall()
        probs = []
        for mp in maps:
            try:
                probs.append(predict_map_win_prob(r["match_id"], mp["map_index"], db_path=db_path))
            except ValueError:
                pass
        if not probs:
            continue
        p1 = sum(probs) / len(probs)
        prx_p = p1 if side == "team1" else 1 - p1
        prx_won = r["winner_id"] == PRX_TEAM_ID
        opp_id = r["team2_id"] if side == "team1" else r["team1_id"]
        opp = conn.execute("SELECT name FROM teams WHERE team_id = ?", (opp_id,)).fetchone()
        out.append({
            "match_id": r["match_id"], "date": r["date_utc"][:10],
            "opponent": opp["name"] if opp else None, "opponent_id": opp_id,
            "prx_score": r["team1_score"] if side == "team1" else r["team2_score"],
            "opp_score": r["team2_score"] if side == "team1" else r["team1_score"],
            "prx_won": prx_won,
            "predicted_prx_win_prob": round(prx_p, 4),
            "model_correct": (prx_p > 0.5) == prx_won,
        })
    _RECENT_CACHE[key] = out
    return out


def _event_name(conn, event_id):
    r = conn.execute("SELECT name FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return r["name"] if r else None


def match_view(conn, match_id, db_path):
    """Full match-view payload: meta + prediction + insight (+ replay/outcome if done)."""
    m = conn.execute(
        """SELECT match_id, event_id, series_name, team1_id, team2_id,
                  team1_score, team2_score, winner_id, date_utc, format
           FROM matches WHERE match_id = ?""",
        (match_id,),
    ).fetchone()
    if m is None:
        return None

    side = prx_side(m["team1_id"], m["team2_id"])
    pred = _pre_match_ingested(conn, match_id)        # team briefs, prob, HDI, maps, factors
    expected = expected_records(match_id, db_path)
    completed = m["winner_id"] is not None

    # Frame around PRX when PRX is playing; otherwise the actual team1 (a non-PRX tier-1
    # match shouldn't be narrated as PRX). subject_side is never None.
    subject_side = side or "team1"
    subject = "PRX" if side else (pred["team1"].get("name") or "Team 1")
    subject_team_id = PRX_TEAM_ID if side else m["team1_id"]

    out = {
        "match_id": match_id,
        "completed": completed,
        "event": _event_name(conn, m["event_id"]),
        "series_name": m["series_name"],
        "date": m["date_utc"][:10],
        "format": m["format"],
        "team1": pred["team1"], "team2": pred["team2"],
        "team1_score": m["team1_score"], "team2_score": m["team2_score"],
        "winner_id": m["winner_id"],
        "prx_side": side,
        "prediction": {
            "team1_win_prob": pred["team1_win_prob"],
            "team1_win_prob_hdi": pred.get("team1_win_prob_hdi"),
            "series_win_prob": pred["series_win_prob"],
            "map_predictions": pred["map_predictions"],
            "top_factors": pred["top_factors"],
        },
        "prematch_insight": insight.prematch_insight(
            pred, subject_side, subject=subject, subject_team_id=subject_team_id,
            expected=expected),
        "expected_stats": expected,
    }

    if completed:
        maps = build_replay(conn, match_id, m["team1_id"], db_path)
        swing = insight.biggest_swing(maps, subject_side)
        subject_p = pred["team1_win_prob"] if subject_side == "team1" else 1 - pred["team1_win_prob"]
        out["replay"] = maps
        out["biggest_swing"] = swing
        out["postmatch_insight"] = insight.postmatch_insight(
            subject_p, m["winner_id"] == subject_team_id,
            subject=subject, subject_team_id=subject_team_id, expected=expected, swing=swing)
    return out


def player_view(conn, db_path, player_id):
    """Full player-view payload: profile + skill percentile + stints + exp-vs-actual trend."""
    p = conn.execute(
        """SELECT p.player_id, p.handle, p.real_name, p.country,
                  p.current_team_id, t.name AS current_team_name, t.tag AS current_team_tag
           FROM players p LEFT JOIN teams t ON t.team_id = p.current_team_id
           WHERE p.player_id = ?""",
        (player_id,),
    ).fetchone()
    if p is None:
        return None
    out = dict(p)

    # Skill rating + percentile among all rated players (conservative mu-3σ).
    skills = conn.execute(
        """SELECT player_id, mu - 3 * sigma AS cons FROM player_skill ps
           WHERE agent IS NULL AND map_name IS NULL
             AND as_of_date = (SELECT MAX(as_of_date) FROM player_skill
                               WHERE player_id = ps.player_id AND agent IS NULL AND map_name IS NULL)"""
    ).fetchall()
    me = next((s["cons"] for s in skills if s["player_id"] == player_id), None)
    if me is not None and skills:
        below = sum(1 for s in skills if s["cons"] < me)
        out["skill"] = {"rating": round(me, 1), "percentile": round(100 * below / len(skills)),
                        "rated_players": len(skills)}
    else:
        out["skill"] = None

    out["stints"] = [dict(r) for r in conn.execute(
        """SELECT s.team_id_at_match AS team_id, t.name AS team_name, t.tag AS team_tag,
                  COUNT(*) AS n_maps, ROUND(AVG(s.rating), 3) AS avg_rating,
                  ROUND(AVG(s.acs), 1) AS avg_acs, ROUND(AVG(s.kills), 2) AS avg_kills,
                  ROUND(AVG(s.deaths), 2) AS avg_deaths, ROUND(AVG(s.assists), 2) AS avg_assists,
                  MIN(m.date_utc) AS first_date, MAX(m.date_utc) AS last_date
           FROM map_player_stats s JOIN maps mp ON mp.map_id = s.map_id
           JOIN matches m ON m.match_id = mp.match_id
           LEFT JOIN teams t ON t.team_id = s.team_id_at_match
           WHERE s.player_id = ? GROUP BY s.team_id_at_match ORDER BY last_date DESC""",
        (player_id,),
    ).fetchall()]

    # Expected-vs-actual over the player's last few matches (over/under his baseline).
    recent = conn.execute(
        """SELECT DISTINCT m.match_id, m.date_utc, m.team1_id, m.team2_id
           FROM map_player_stats mps JOIN maps mp ON mp.map_id = mps.map_id
           JOIN matches m ON m.match_id = mp.match_id
           WHERE mps.player_id = ? AND m.winner_id IS NOT NULL
             AND (m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%')
           ORDER BY m.date_utc DESC LIMIT 5""",
        (player_id,),
    ).fetchall()
    trend = []
    for rm in recent:
        rec = next((e for e in expected_records(rm["match_id"], db_path)
                    if e["player_id"] == player_id and "actual_acs" in e), None)
        if rec:
            opp_id = rm["team2_id"] if rm["team1_id"] == out.get("current_team_id") else rm["team1_id"]
            opp = conn.execute("SELECT name FROM teams WHERE team_id = ?", (opp_id,)).fetchone()
            trend.append({"match_id": rm["match_id"], "date": rm["date_utc"][:10],
                          "opponent": opp["name"] if opp else None,
                          "expected_acs": rec["expected_acs"], "actual_acs": rec["actual_acs"],
                          "delta_acs": rec["delta_acs"]})
    out["recent_form"] = trend

    # Head-to-head duel matrix (tier-2): best/worst recent matchups.
    from models.scouting import player_duels, player_profile
    out["duels"] = player_duels(conn, out["handle"])
    # Stat profile as percentiles vs same-role peers (pizza / percentile card).
    out["profile"] = player_profile(conn, player_id)
    return out
