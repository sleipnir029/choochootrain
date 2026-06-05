"""Tests for ingestion.matches — format/date parsing, FK-safe team upsert,
idempotency, completed-only filter. No network (FakeClient)."""

import asyncio
import sqlite3

import pytest

from ingestion.matches import infer_format, ingest_matches, parse_match, parse_match_date
from ingestion.schema import init_db


def _detail(match_id, t1, t2, date="March 14, 2024 4:00 PM CET Patch 8.04", series="Round 1"):
    """A /v2/match/details segment. t1/t2 are (id, name, score, is_winner)."""
    def team(t):
        return {"id": t[0], "name": t[1], "tag": "", "logo": f"https://logo/{t[0]}.png",
                "score": t[2], "is_winner": t[3]}
    return {"match_id": match_id, "event": {"series": series}, "date": date,
            "teams": [team(t1), team(t2)]}


class FakeClient:
    def __init__(self, listings: dict, details: dict):
        self._listings = listings   # {event_id_str: [list entries]}
        self._details = details     # {match_id_str: detail seg}

    async def get_segments(self, path: str, **params: object) -> list:
        if path == "/v2/events/matches":
            return self._listings.get(str(params["event_id"]), [])
        if path == "/v2/match/details":
            mid = str(params["match_id"])
            if mid not in self._details:
                raise KeyError(mid)
            return [self._details[mid]]
        raise ValueError(path)


def test_infer_format():
    assert infer_format(2, 0) == "Bo3"
    assert infer_format(2, 1) == "Bo3"
    assert infer_format(3, 2) == "Bo5"
    assert infer_format(1, 0) == "Bo1"
    with pytest.raises(ValueError):
        infer_format(0, 0)


def test_parse_match_date():
    assert parse_match_date("March 14, 2024 4:00 PM CET Patch 8.04") == "2024-03-14"
    assert parse_match_date("Jun 7, 2025") == "2025-06-07"
    with pytest.raises(ValueError):
        parse_match_date("TBD")


def test_parse_match_builds_row():
    seg = _detail("312765", ("8877", "Karmine Corp", "2", True), ("11328", "FunPlus Phoenix", "0", False))
    row = parse_match(seg, 1921, match_url="https://www.vlr.gg/312765/...")
    assert row["match_id"] == 312765 and row["event_id"] == 1921
    assert row["team1_id"] == 8877 and row["team2_id"] == 11328
    assert row["team1_score"] == 2 and row["team2_score"] == 0
    assert row["winner_id"] == 8877
    assert row["format"] == "Bo3" and row["date_utc"] == "2024-03-14"
    assert row["patch_id"] is None
    assert row["series_name"] == "Round 1"


def test_parse_match_prefers_listing_date_with_year():
    # vlr omits the year in the detail date for current-year matches; the
    # /v2/events/matches listing date carries it -> must be preferred.
    seg = _detail("9", ("1", "A", "2", True), ("2", "B", "0", False),
                  date="Thursday, January 15 11:00 PM CET Patch 12.0")
    row = parse_match(seg, 1, match_date="Thu, January 15, 2026")
    assert row["date_utc"] == "2026-01-15"


def _setup_db(tmp_path) -> str:
    db = str(tmp_path / "prx.db")
    init_db(db)
    conn = sqlite3.connect(db)
    # event row required by matches.event_id FK
    conn.execute(
        "INSERT INTO events (event_id, name, tier, region, start_date, end_date) "
        "VALUES (1921, 'Masters Madrid 2024', 'Masters', 'global', '2024-03-14', '2024-03-24')"
    )
    conn.commit()
    conn.close()
    return db


LISTING = [
    {"match_id": "312765", "status": "Completed", "url": "https://www.vlr.gg/312765/x"},
    {"match_id": "312766", "status": "Completed", "url": "https://www.vlr.gg/312766/y"},
    {"match_id": "999999", "status": "Upcoming", "url": "https://www.vlr.gg/999999/z"},  # skipped
]
DETAILS = {
    "312765": _detail("312765", ("8877", "Karmine Corp", "2", True), ("11328", "FunPlus Phoenix", "0", False)),
    "312766": _detail("312766", ("624", "Paper Rex", "1", False), ("8877", "Karmine Corp", "2", True)),
    # 999999 intentionally absent (and Upcoming) -> not fetched
}


def _count(db, table):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_ingest_idempotent_and_completed_only(tmp_path):
    db = _setup_db(tmp_path)
    client = FakeClient({"1921": LISTING}, DETAILS)

    n1 = asyncio.run(ingest_matches(db, client=client, event_ids=[1921]))
    assert n1 == 2  # the Upcoming match is skipped
    assert _count(db, "matches") == 2
    # teams referenced (8877, 11328, 624) auto-upserted
    assert _count(db, "teams") == 3

    n2 = asyncio.run(ingest_matches(db, client=client, event_ids=[1921]))
    assert n2 == 2 and _count(db, "matches") == 2  # idempotent

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        m = dict(conn.execute("SELECT * FROM matches WHERE match_id=312766").fetchone())
    finally:
        conn.close()
    assert m["winner_id"] == 8877 and m["format"] == "Bo3"


def test_team_country_preserved_on_match_upsert(tmp_path):
    db = _setup_db(tmp_path)
    # PRX already ingested by T3 with country='sg'
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO teams (team_id, name, tag, country, region, logo_url, last_updated) "
        "VALUES (624, 'Paper Rex', 'PRX', 'sg', 'pac', 'https://logo/624.png', '2026-06-04T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    client = FakeClient({"1921": LISTING}, DETAILS)
    asyncio.run(ingest_matches(db, client=client, event_ids=[1921]))

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        prx = dict(conn.execute("SELECT * FROM teams WHERE team_id=624").fetchone())
    finally:
        conn.close()
    assert prx["country"] == "sg" and prx["region"] == "pac"  # not clobbered by match upsert
