"""Team endpoints (P6.T2): profile + active roster, recent matches."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_conn

router = APIRouter()


@router.get("/api/teams/{team_id}")
def get_team(team_id: int, conn=Depends(get_conn)):
    """Team profile + current active roster (roster_history where left_date IS NULL)."""
    t = conn.execute(
        "SELECT team_id, name, tag, country, region, logo_url FROM teams WHERE team_id = ?",
        (team_id,),
    ).fetchone()
    if t is None:
        raise HTTPException(status_code=404, detail=f"team {team_id} not found")
    roster = conn.execute(
        """
        SELECT DISTINCT p.player_id, p.handle, p.real_name, p.country, r.role
        FROM roster_history r JOIN players p ON p.player_id = r.player_id
        WHERE r.team_id = ? AND r.left_date IS NULL
        ORDER BY p.handle
        """,
        (team_id,),
    ).fetchall()
    return {"team": dict(t), "active_roster": [dict(r) for r in roster]}


@router.get("/api/teams/{team_id}/matches")
def get_team_matches(team_id: int, limit: int = 20, conn=Depends(get_conn)):
    """Most recent matches involving the team (completed; warehouse holds completed only)."""
    rows = conn.execute(
        """
        SELECT match_id, event_id, series_name, team1_id, team2_id,
               team1_score, team2_score, winner_id, date_utc, format
        FROM matches
        WHERE team1_id = ? OR team2_id = ?
        ORDER BY date_utc DESC, match_id DESC
        LIMIT ?
        """,
        (team_id, team_id, limit),
    ).fetchall()
    return {"team_id": team_id, "matches": [dict(r) for r in rows]}
