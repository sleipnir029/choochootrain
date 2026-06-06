"""Prediction endpoints (P6.T2): pre-match, replay, live.

- **pre-match** has two modes: ``match_id`` (ingested map-by-map) or
  ``team1_id``+``team2_id`` (upcoming, via ``models.upcoming``). See ARCHITECTURE
  §3.1.
- **replay** walks a completed match round-by-round, re-running the score-state
  update to produce a probability trace.
- **live** reads the ``live_state`` / ``live_predictions`` tables the P5 poller
  writes; if nothing is live, returns the next PRX match.

Model functions are imported lazily inside handlers so the MCMC stack loads only
when a prediction is actually requested (cached per db path thereafter).
"""

import math

from fastapi import APIRouter, Depends, HTTPException

from api.deps import db_path, get_conn

router = APIRouter()

PRX_TEAM_ID = 624
_FORMAT_MAPS = {"Bo1": 1, "Bo3": 3, "Bo5": 5}


def _series_win_prob(p_map: float, fmt: str) -> float:
    """P(team1 wins a best-of-N series) given a single per-map win prob (independent)."""
    n = _FORMAT_MAPS.get(fmt, 3)
    need = n // 2 + 1
    return sum(math.comb(n, i) * p_map ** i * (1 - p_map) ** (n - i)
               for i in range(need, n + 1))


def _team_brief(conn, team_id: int) -> dict:
    r = conn.execute(
        "SELECT team_id AS id, name, logo_url AS logo FROM teams WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    return dict(r) if r else {"id": team_id, "name": None, "logo": None}


@router.get("/api/predict/pre-match")
def pre_match(match_id: int | None = None, team1_id: int | None = None,
              team2_id: int | None = None, event_id: int | None = None,
              conn=Depends(get_conn)):
    """Pre-match prediction. Provide ``match_id`` (ingested) OR ``team1_id``+``team2_id``."""
    if match_id is not None:
        return _pre_match_ingested(conn, match_id)
    if team1_id is not None and team2_id is not None:
        return _pre_match_upcoming(conn, team1_id, team2_id, event_id)
    raise HTTPException(status_code=400,
                        detail="provide match_id, or team1_id and team2_id")


def _pre_match_ingested(conn, match_id: int):
    from models.predict import predict_map_win_prob_detailed

    m = conn.execute(
        "SELECT team1_id, team2_id, format FROM matches WHERE match_id = ?",
        (match_id,),
    ).fetchone()
    if m is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} not in warehouse")
    maps = conn.execute(
        "SELECT map_index, map_name, picked_by_team_id FROM maps "
        "WHERE match_id = ? ORDER BY map_index",
        (match_id,),
    ).fetchall()
    if not maps:
        raise HTTPException(status_code=404, detail=f"match {match_id} has no ingested maps")

    map_predictions, probs, top_factors = [], [], []
    for mp in maps:
        try:
            d = predict_map_win_prob_detailed(match_id, mp["map_index"], db_path=db_path())
        except ValueError:
            continue  # showmatch / missing feature row
        probs.append(d["team1_win_prob"])
        if not top_factors:
            top_factors = d["top_factors"]
        map_predictions.append({
            "map_name": mp["map_name"],
            "team1_win_prob": round(d["team1_win_prob"], 4),
            "team1_win_prob_hdi": [round(x, 4) for x in d["hdi"]],
            "picked_by": mp["picked_by_team_id"],
        })

    p_mean = sum(probs) / len(probs) if probs else 0.5
    p_series = _series_win_prob(p_mean, m["format"])
    return {
        "mode": "ingested",
        "match_id": match_id,
        "team1": _team_brief(conn, m["team1_id"]),
        "team2": _team_brief(conn, m["team2_id"]),
        "series_format": m["format"],
        "series_win_prob": {"team1": round(p_series, 4), "team2": round(1 - p_series, 4)},
        "team1_win_prob": round(p_mean, 4),
        "map_predictions": map_predictions,
        "top_factors": top_factors,
    }


def _pre_match_upcoming(conn, team1_id: int, team2_id: int, event_id):
    from models.upcoming import predict_upcoming_win_prob

    d = predict_upcoming_win_prob(team1_id, team2_id, event_id=event_id, db_path=db_path())
    p = d["team1_win_prob"]
    p_series = _series_win_prob(p, "Bo3")
    return {
        "mode": "upcoming",
        "team1": _team_brief(conn, team1_id),
        "team2": _team_brief(conn, team2_id),
        "series_format": "Bo3",
        "series_win_prob": {"team1": round(p_series, 4), "team2": round(1 - p_series, 4)},
        "team1_win_prob": round(p, 4),
        "team1_win_prob_hdi": [round(x, 4) for x in d["hdi"]],
        "map_predictions": [],
        "top_factors": d["top_factors"],
    }


@router.get("/api/predict/replay")
def replay(match_id: int, conn=Depends(get_conn)):
    """Round-by-round pre-round probability trace for a completed match."""
    from models.predict import combine_prior_and_state, predict_map_win_prob, score_state_prob

    m = conn.execute(
        "SELECT team1_id FROM matches WHERE match_id = ?", (match_id,)
    ).fetchone()
    if m is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} not in warehouse")
    team1_id = m["team1_id"]

    maps = conn.execute(
        "SELECT map_id, map_index, map_name FROM maps WHERE match_id = ? ORDER BY map_index",
        (match_id,),
    ).fetchall()
    if not maps:
        raise HTTPException(status_code=404, detail=f"match {match_id} has no ingested maps")

    out_maps = []
    for mp in maps:
        # The pre-match prior is identical for every round of a map (a Bambi
        # posterior-predictive); compute it ONCE, then apply the cheap score-state
        # combine per round. Avoids re-running the model ~once per round.
        try:
            prior = predict_map_win_prob(match_id, mp["map_index"], db_path=db_path())
        except ValueError:
            prior = None

        rounds = conn.execute(
            "SELECT round_number, half, team1_side, winner_id FROM rounds "
            "WHERE map_id = ? ORDER BY round_number",
            (mp["map_id"],),
        ).fetchall()
        t1, t2, trace = 0, 0, []
        for rd in rounds:
            if prior is None:
                p = None
            else:
                p_state = score_state_prob({
                    "half": rd["half"], "team1_score": t1, "team2_score": t2,
                    "team1_side": rd["team1_side"],
                }, db_path=db_path())
                p = combine_prior_and_state(prior, p_state)
            trace.append({
                "round": rd["round_number"],
                "team1_side": rd["team1_side"],
                "pre_round_prob_team1": None if p is None else round(p, 4),
                "winner": "team1" if rd["winner_id"] == team1_id else "team2",
            })
            if rd["winner_id"] == team1_id:
                t1 += 1
            else:
                t2 += 1
        out_maps.append({"map_index": mp["map_index"], "map_name": mp["map_name"], "rounds": trace})

    return {"match_id": match_id, "maps": out_maps}


@router.get("/api/predict/live")
async def live(conn=Depends(get_conn)):
    """Current live prediction from the poller's tables; else the next PRX match."""
    state = conn.execute(
        "SELECT match_id, team1_score, team2_score, team1_round_ct, team1_round_t, "
        "team2_round_ct, team2_round_t, map_number, current_map, last_updated "
        "FROM live_state LIMIT 1"
    ).fetchone()

    if state is None:
        from api.routes.matches import fetch_upcoming
        prx = conn.execute("SELECT name FROM teams WHERE team_id = ?", (PRX_TEAM_ID,)).fetchone()
        matches, source = await fetch_upcoming(prx["name"] if prx else None)
        return {"mode": "no_live",
                "next_prx_match": matches[0] if matches else None,
                "source": source}

    map_index = (state["map_number"] or 1) - 1
    history = conn.execute(
        "SELECT team1_win_prob, computed_at FROM live_predictions "
        "WHERE match_id = ? AND map_index = ? ORDER BY computed_at",
        (state["match_id"], map_index),
    ).fetchall()
    current = history[-1]["team1_win_prob"] if history else None

    return {
        "mode": "live",
        "match_id": state["match_id"],
        "current_map_index": map_index,
        "current_map": state["current_map"],
        "team1_score": state["team1_score"],
        "team2_score": state["team2_score"],
        "team1_round_ct": state["team1_round_ct"],
        "team1_round_t": state["team1_round_t"],
        "team2_round_ct": state["team2_round_ct"],
        "team2_round_t": state["team2_round_t"],
        "team1_win_prob_current_map": current,
        "team1_win_prob_series": None,  # not stored by the poller; derived view is Phase 8
        "probability_history": [
            {"prob": round(h["team1_win_prob"], 4), "computed_at": h["computed_at"]}
            for h in history
        ],
        "last_updated": state["last_updated"],
    }
