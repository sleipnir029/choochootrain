"""PRX home aggregate (P6 revision): one call for the landing page.

Hero priority (SPEC D3, warehouse-first so it works without vlrggapi):
live PRX match -> next scheduled PRX match (if the opponent resolves to a team_id)
-> most-recent completed PRX match with its outcome story.
"""

from fastapi import APIRouter, Depends

from api import compute, insight
from api.deps import db_path, get_conn
from api.routes.predict import PRX_TEAM_ID, _series_win_prob, _team_brief

router = APIRouter()


def _live_hero(conn):
    state = conn.execute(
        "SELECT match_id, team1_id, team2_id, team1_round_ct, team1_round_t, "
        "team2_round_ct, team2_round_t, map_number, current_map FROM live_state LIMIT 1"
    ).fetchone()
    if state is None:
        return None
    # Prefer the live_state team ids (set by the poller, work for un-ingested matches);
    # fall back to the matches table for an ingested live match.
    t1id, t2id = state["team1_id"], state["team2_id"]
    if t1id is None or t2id is None:
        m = conn.execute("SELECT team1_id, team2_id FROM matches WHERE match_id = ?",
                         (state["match_id"],)).fetchone()
        if m:
            t1id, t2id = m["team1_id"], m["team2_id"]
    # Frame around PRX when PRX is playing; otherwise the actual team1 (D3 can track a
    # non-PRX tier-1 match — don't mislabel it as PRX).
    prx_side = compute.prx_side(t1id, t2id) if t1id is not None else None
    subject_side = prx_side or "team1"
    name_of = lambda tid: (conn.execute("SELECT name FROM teams WHERE team_id = ?", (tid,)).fetchone() or [None])[0]
    subject = "PRX" if prx_side else (name_of(t1id) or "Team 1")
    opp_id = t2id if subject_side == "team1" else t1id
    opponent = name_of(opp_id) if opp_id else None

    mi = (state["map_number"] or 1) - 1
    last = conn.execute(
        "SELECT team1_win_prob FROM live_predictions WHERE match_id = ? AND map_index = ? "
        "ORDER BY computed_at DESC LIMIT 1", (state["match_id"], mi)).fetchone()
    cur = last["team1_win_prob"] if last else None
    payload = {**dict(state), "team1_win_prob_current_map": cur}
    sub_p = None if cur is None else (cur if subject_side == "team1" else 1 - cur)
    return {"kind": "live", "match_id": state["match_id"], "current_map": state["current_map"],
            "subject": subject, "subject_win_prob": round(sub_p, 4) if sub_p is not None else None,
            "opponent": opponent,
            "insight": insight.live_insight(payload, subject_side, subject=subject)}


def _next_hero(conn, segment):
    """Build a predicted next-match hero from a vlrggapi upcoming segment, if the
    opponent name resolves to a known team_id; else a schedule-only hero."""
    names = [segment.get("team1"), segment.get("team2")]
    opp_name = next((n for n in names if n and "paper rex" not in n.lower()), None)
    opp = conn.execute("SELECT team_id FROM teams WHERE name = ? COLLATE NOCASE",
                       (opp_name,)).fetchone() if opp_name else None
    if not opp:
        return {"kind": "next", "schedule": segment, "insight": None}
    from models.upcoming import predict_upcoming_win_prob
    d = predict_upcoming_win_prob(PRX_TEAM_ID, opp["team_id"], db_path=db_path())
    ps = _series_win_prob(d["team1_win_prob"], "Bo3")
    pred = {"mode": "upcoming", "team1": _team_brief(conn, PRX_TEAM_ID),
            "team2": _team_brief(conn, opp["team_id"]),
            "series_format": "Bo3",
            "series_win_prob": {"team1": round(ps, 4), "team2": round(1 - ps, 4)},
            "team1_win_prob": round(d["team1_win_prob"], 4),
            "team1_win_prob_hdi": [round(x, 4) for x in d["hdi"]],
            "map_predictions": [], "top_factors": d["top_factors"]}
    return {"kind": "next", "schedule": segment, "prediction": pred,
            "insight": insight.prematch_insight(pred, "team1")}


def _recent_hero(conn):
    last = conn.execute(
        """SELECT match_id FROM matches
           WHERE (team1_id = ? OR team2_id = ?) AND winner_id IS NOT NULL
             AND (series_name IS NULL OR series_name NOT LIKE 'Showmatch%')
           ORDER BY date_utc DESC, match_id DESC LIMIT 1""",
        (PRX_TEAM_ID, PRX_TEAM_ID),
    ).fetchone()
    if last is None:
        return None
    mv = compute.match_view(conn, last["match_id"], db_path())
    return {"kind": "recent", "match_id": mv["match_id"],
            "team1": mv["team1"], "team2": mv["team2"],
            "team1_score": mv["team1_score"], "team2_score": mv["team2_score"],
            "winner_id": mv["winner_id"], "prx_side": mv["prx_side"],
            "prediction": mv["prediction"],
            "insight": mv.get("postmatch_insight") or mv.get("prematch_insight")}


@router.get("/api/home")
async def home(conn=Depends(get_conn)):
    prx_team = conn.execute(
        "SELECT team_id, name, tag, country, region, logo_url FROM teams WHERE team_id = ?",
        (PRX_TEAM_ID,)).fetchone()

    hero = _live_hero(conn)
    if hero is None:
        from api.routes.matches import fetch_upcoming
        matches, _ = await fetch_upcoming(prx_team["name"] if prx_team else None)
        hero = _next_hero(conn, matches[0]) if matches else _recent_hero(conn)

    return {
        "prx": {
            "team": dict(prx_team) if prx_team else {"team_id": PRX_TEAM_ID, "name": "Paper Rex"},
            "rank": compute.prx_rank(conn),
            "roster": compute.roster_with_skill(conn, PRX_TEAM_ID),
        },
        "hero": hero,
        "recent": compute.recent_prx_results(conn, db_path()),
    }
