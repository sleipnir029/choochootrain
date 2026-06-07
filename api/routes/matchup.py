"""Head-to-head matchup endpoint (analyst pre-match prep view): the model's
prediction + narrative, plus a scouting overlay of both teams (map edge, veto
tendencies, comps, and marquee cross-roster player duels)."""

from fastapi import APIRouter, Depends

from api.deps import db_path, get_conn
from api.routes.predict import PRX_TEAM_ID, _series_win_prob, _team_brief  # noqa: F401

router = APIRouter()


@router.get("/api/matchup")
def matchup(team1_id: int, team2_id: int, conn=Depends(get_conn)):
    from api import compute, insight
    from models.scouting import head_to_head
    from models.upcoming import predict_upcoming_win_prob

    d = predict_upcoming_win_prob(team1_id, team2_id, db_path=db_path())
    p = d["team1_win_prob"]
    ps = _series_win_prob(p, "Bo3")
    pred = {
        "mode": "upcoming",
        "team1": _team_brief(conn, team1_id), "team2": _team_brief(conn, team2_id),
        "series_format": "Bo3",
        "series_win_prob": {"team1": round(ps, 4), "team2": round(1 - ps, 4)},
        "team1_win_prob": round(p, 4),
        "team1_win_prob_hdi": [round(x, 4) for x in d["hdi"]],
        "confidence": d.get("confidence"),
        "map_predictions": [], "top_factors": d["top_factors"],
    }
    side = compute.prx_side(team1_id, team2_id)
    return {
        "team1": pred["team1"], "team2": pred["team2"],
        "prediction": pred,
        "prx_side": side,
        "prematch_insight": insight.prematch_insight(pred, side or "team1"),
        **head_to_head(conn, team1_id, team2_id),
    }
