"""Match endpoints (P6.T2): upcoming matches for a team (via vlrggapi).

Upcoming matches are NOT in the warehouse (it holds completed matches only), so
this proxies vlrggapi ``/v2/match?q=upcoming`` and filters by the team's name.
Best-effort: if vlrggapi is unreachable (e.g. the container isn't running), returns
an empty list with ``source: "unavailable"`` rather than erroring.
"""

from fastapi import APIRouter, Depends

from api.deps import get_conn

router = APIRouter()


def _involves(segment: dict, name: str) -> bool:
    blob = f"{segment.get('team1', '')} {segment.get('team2', '')}".lower()
    return name.lower() in blob


async def fetch_upcoming(team_name: str | None) -> tuple[list, str]:
    """Return (matches, source). Isolated for testing/mocking."""
    from ingestion.vlr_client import VlrApiError, VlrClient

    try:
        # Fail fast (no retries, short timeout): live/upcoming is best-effort and
        # must not stall the request when vlrggapi is down.
        async with VlrClient(max_retries=0, timeout=5.0) as client:
            segments = await client.get_segments("/v2/match", q="upcoming")
    except (VlrApiError, OSError, RuntimeError):
        return [], "unavailable"
    if team_name:
        segments = [s for s in segments if _involves(s, team_name)]
    return segments, "vlrggapi"


@router.get("/api/matches/upcoming")
async def upcoming_matches(team_id: int, conn=Depends(get_conn)):
    """Next scheduled match(es) for a team, sourced live from vlrggapi."""
    row = conn.execute("SELECT name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    team_name = row["name"] if row else None
    matches, source = await fetch_upcoming(team_name)
    return {"team_id": team_id, "team_name": team_name, "matches": matches, "source": source}
