"""Tests for ingestion.teams — parsing, idempotent upsert, missing teams.

No network: a FakeClient returns canned /v2/team segments. Async functions are
driven with asyncio.run so we don't depend on pytest-asyncio.
"""

import asyncio
import sqlite3

from ingestion.schema import init_db
from ingestion.teams import ingest_teams, parse_team

# Trimmed real /v2/team segments (region is intentionally absent).
PRX = {
    "id": "624",
    "name": "Paper Rex",
    "tag": "PRX",
    "logo": "https://owcdn.net/img/62bbeba74d5cb.png",
    "country": "sg",
    "country_name": "Singapore",
}
SEN = {
    "id": "2",
    "name": "Sentinels",
    "tag": "SEN",
    "logo": "https://owcdn.net/img/sen.png",
    "country": "us",
    "country_name": "United States",
}


class FakeClient:
    """Stand-in for VlrClient.get_segments, keyed by the `id` query param."""

    def __init__(self, segments_by_id: dict[str, list]):
        self._by_id = segments_by_id

    async def get_segments(self, path: str, **params: object) -> list:
        return self._by_id.get(str(params.get("id")), [])


def _count_teams(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    finally:
        conn.close()


def _get_team(db_path: str, team_id: int) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_parse_team_maps_fields():
    row = parse_team(PRX)
    assert row["team_id"] == 624 and isinstance(row["team_id"], int)
    assert row["name"] == "Paper Rex"
    assert row["tag"] == "PRX"
    assert row["country"] == "sg"
    assert row["region"] is None  # not exposed by /v2/team
    assert row["logo_url"].startswith("https://")
    assert row["last_updated"]  # ISO timestamp present


def test_ingest_is_idempotent(tmp_path):
    db = str(tmp_path / "prx.db")
    init_db(db)
    client = FakeClient({"624": [PRX], "2": [SEN]})

    n1 = asyncio.run(ingest_teams([624, 2], db, client=client))
    assert n1 == 2
    assert _count_teams(db) == 2

    # Running again must not create duplicate rows (upsert keyed on team_id).
    n2 = asyncio.run(ingest_teams([624, 2], db, client=client))
    assert n2 == 2
    assert _count_teams(db) == 2

    prx = _get_team(db, 624)
    assert prx is not None
    assert prx["name"] == "Paper Rex"
    assert prx["tag"] == "PRX"
    assert prx["country"] == "sg"


def test_missing_team_is_skipped(tmp_path):
    db = str(tmp_path / "prx.db")
    init_db(db)
    client = FakeClient({"624": [PRX]})  # 999 returns no segments

    n = asyncio.run(ingest_teams([624, 999], db, client=client))
    assert n == 1
    assert _count_teams(db) == 1
    assert _get_team(db, 999) is None
