"""Event endpoints (P6.T2): tier-1 events from the warehouse, status-classified.

Served from the curated ``events`` table (P2.T4). ``status`` is derived from the
event's date range vs today: ``upcoming`` (starts after today), ``live`` (today in
[start, end]), ``completed`` (ended before today).
"""

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_conn

router = APIRouter()

_STATUSES = {"upcoming", "live", "completed"}


def _classify(start_date: str, end_date: str, today: str) -> str:
    if start_date > today:
        return "upcoming"
    if end_date < today:
        return "completed"
    return "live"


@router.get("/api/events")
def list_events(status: str | None = None, conn=Depends(get_conn)):
    """Tier-1 events; optionally filtered by derived status."""
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_STATUSES)}")
    today = _dt.date.today().isoformat()
    rows = conn.execute(
        "SELECT event_id, name, tier, region, start_date, end_date, prize_usd "
        "FROM events ORDER BY start_date DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["status"] = _classify(r["start_date"], r["end_date"], today)
        if status is None or d["status"] == status:
            out.append(d)
    return {"status": status, "events": out}
