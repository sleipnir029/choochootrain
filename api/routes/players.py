"""Player endpoints (P6.T2): profile + per-team-stint stats (SPEC D2).

D2: player stats must NOT pool across teams — every aggregate view is broken down
by the team the player was on at the time (``map_player_stats.team_id_at_match``).
"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import db_path, get_conn

router = APIRouter()


@router.get("/api/players/{player_id}")
def get_player(player_id: int, conn=Depends(get_conn)):
    """Full player view: profile + skill percentile + per-stint stats + exp-vs-actual trend."""
    from api.compute import player_view

    view = player_view(conn, db_path(), player_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"player {player_id} not found")
    return view


@router.get("/api/players/{player_id}/stats")
def get_player_stats(player_id: int, group_by: str = "team_stint", conn=Depends(get_conn)):
    """Aggregate stats partitioned by team stint (D2 — no cross-team pooling).

    Each stint: team context, map count, date range, average rating/ACS/K/D/A.
    """
    if group_by != "team_stint":
        raise HTTPException(status_code=400, detail="only group_by=team_stint is supported")
    rows = conn.execute(
        """
        SELECT s.team_id_at_match AS team_id, t.name AS team_name, t.tag AS team_tag,
               COUNT(*) AS n_maps,
               ROUND(AVG(s.rating), 3) AS avg_rating,
               ROUND(AVG(s.acs), 1)   AS avg_acs,
               ROUND(AVG(s.kills), 2) AS avg_kills,
               ROUND(AVG(s.deaths), 2) AS avg_deaths,
               ROUND(AVG(s.assists), 2) AS avg_assists,
               MIN(m.date_utc) AS first_date, MAX(m.date_utc) AS last_date
        FROM map_player_stats s
        JOIN maps mp   ON mp.map_id = s.map_id
        JOIN matches m ON m.match_id = mp.match_id
        LEFT JOIN teams t ON t.team_id = s.team_id_at_match
        WHERE s.player_id = ?
        GROUP BY s.team_id_at_match
        ORDER BY last_date DESC
        """,
        (player_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no stats for player {player_id}")
    return {"player_id": player_id, "group_by": "team_stint", "stints": [dict(r) for r in rows]}
