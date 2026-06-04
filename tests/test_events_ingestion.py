"""Tests for ingestion.events — date/prize parsing, idempotent upsert, skips.

No network: a FakeClient returns canned /v2/event/{id} detail payloads.
"""

import asyncio
import sqlite3

import pytest

from ingestion.events import (
    ingest_events,
    parse_dates,
    parse_event,
    parse_prize,
)
from ingestion.schema import init_db


def _detail(name: str, dates: str, prize: str) -> dict:
    """Build a /v2/event detail envelope (data.segments is a dict)."""
    return {
        "status": "success",
        "data": {"status": 200, "segments": {"event": {"name": name, "dates": dates, "prize": prize}}},
    }


class FakeClient:
    def __init__(self, by_path: dict[str, dict]):
        self._by_path = by_path

    async def get_json(self, path: str, **params: object) -> dict:
        if path not in self._by_path:
            raise KeyError(path)  # mimics a missing/failed fetch; _ingest skips it
        return self._by_path[path]


def test_parse_prize():
    assert parse_prize("$500,000 USD") == 500000
    assert parse_prize("$2,250,000 USD") == 2250000
    assert parse_prize("$0") == 0
    assert parse_prize("") is None
    assert parse_prize(None) is None
    assert parse_prize("TBD") is None


def test_parse_dates_same_month():
    assert parse_dates("Mar 14 - 24, 2024") == ("2024-03-14", "2024-03-24")
    assert parse_dates("Aug 1 - 25, 2024") == ("2024-08-01", "2024-08-25")


def test_parse_dates_cross_month():
    assert parse_dates("May 23 - Jun 9, 2024") == ("2024-05-23", "2024-06-09")


def test_parse_dates_full_both_sides():
    # Regional leagues span months and carry a year on both sides.
    assert parse_dates("Feb 16, 2024 - Apr 6, 2024") == ("2024-02-16", "2024-04-06")


def test_parse_dates_cross_year():
    assert parse_dates("Dec 28, 2024 - Jan 5, 2025") == ("2024-12-28", "2025-01-05")


def test_parse_dates_no_year_raises():
    with pytest.raises(ValueError):
        parse_dates("Mar 14 - 24")


def test_parse_dates_tbd_raises():
    # Unscheduled future events (en-dash separator, TBD end) must be skippable.
    with pytest.raises(ValueError):
        parse_dates("Jun 30 – TBD")


def test_parse_event_combines_block_and_registry():
    entry = {"event_id": 1921, "tier": "Masters", "region": "global", "label": "Masters Madrid 2024"}
    block = {"name": "Champions Tour 2024: Masters Madrid", "dates": "Mar 14 - 24, 2024", "prize": "$500,000 USD"}
    row = parse_event(block, entry)
    assert row == {
        "event_id": 1921,
        "name": "Champions Tour 2024: Masters Madrid",
        "tier": "Masters",
        "region": "global",
        "start_date": "2024-03-14",
        "end_date": "2024-03-24",
        "prize_usd": 500000,
    }


EVENTS = [
    {"event_id": 1921, "tier": "Masters", "region": "global", "label": "Masters Madrid 2024"},
    {"event_id": 2002, "tier": "RegionalLeague", "region": "pac", "label": "VCT 2024: Pacific Stage 1"},
]
PAYLOADS = {
    "/v2/event/1921": _detail("Champions Tour 2024: Masters Madrid", "Mar 14 - 24, 2024", "$500,000 USD"),
    "/v2/event/2002": _detail("Champions Tour 2024: Pacific Stage 1", "Apr 4 - Jun 16, 2024", "$250,000 USD"),
}


def _count(db: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


def test_ingest_is_idempotent_and_classifies(tmp_path):
    db = str(tmp_path / "prx.db")
    init_db(db)
    client = FakeClient(PAYLOADS)

    n1 = asyncio.run(ingest_events(db, client=client, events=EVENTS))
    assert n1 == 2 and _count(db) == 2

    n2 = asyncio.run(ingest_events(db, client=client, events=EVENTS))
    assert n2 == 2 and _count(db) == 2  # upsert, no duplicates

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        madrid = dict(conn.execute("SELECT * FROM events WHERE event_id=1921").fetchone())
        pac = dict(conn.execute("SELECT * FROM events WHERE event_id=2002").fetchone())
    finally:
        conn.close()
    assert madrid["tier"] == "Masters" and madrid["region"] == "global"
    assert madrid["start_date"] == "2024-03-14" and madrid["prize_usd"] == 500000
    assert pac["tier"] == "RegionalLeague" and pac["region"] == "pac"


def test_missing_event_is_skipped(tmp_path):
    db = str(tmp_path / "prx.db")
    init_db(db)
    # 2002 has no payload -> fetch raises -> skipped; only 1921 lands.
    client = FakeClient({"/v2/event/1921": PAYLOADS["/v2/event/1921"]})

    n = asyncio.run(ingest_events(db, client=client, events=EVENTS))
    assert n == 1 and _count(db) == 1
