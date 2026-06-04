"""Tests for ingestion.roster_history — tenure parsing + roster-on-date query.

No network. The end-to-end test mirrors the P2.T8 done-when: PRX's roster on
2025-06-22 (Masters Toronto final) = f0rsakeN, Jinggg, d4v41, something, PatMen.
"""

import asyncio
import sqlite3

from ingestion.roster_history import (
    _month_end,
    _month_start,
    extract_tenures,
    ingest_roster_history,
    players_on_team_at,
)
from ingestion.schema import init_db

NAME_TO_ID = {"paper rex": 624}


def test_month_helpers():
    assert _month_start("March 2025") == "2025-03-01"
    assert _month_start("joined in 2020") == "2020-01-01"  # year-only fallback
    assert _month_start("") is None
    assert _month_end("December 2025") == "2025-12-31"
    assert _month_end("February 2024") == "2024-02-29"  # leap year


def test_extract_tenures_current_and_past():
    profile = {
        "current_team": {"name": "Paper Rex", "joined": "joined in April 2020"},
        "past_teams": [{"name": "Some Other Team", "dates": "January 2019 – March 2020"}],
    }
    rows = extract_tenures(profile, NAME_TO_ID)
    assert len(rows) == 1  # the non-tracked team is dropped
    assert rows[0] == {"team_id": 624, "role": "player", "joined_date": "2020-04-01", "left_date": None}


def test_extract_tenures_glued_name():
    # past_teams with the date range glued onto the name and empty 'dates'
    profile = {"past_teams": [{"name": "Paper RexMarch 2025 – December 2025", "dates": ""}]}
    rows = extract_tenures(profile, NAME_TO_ID)
    assert rows == [{"team_id": 624, "role": "player", "joined_date": "2025-03-01", "left_date": "2025-12-31"}]


# --- end-to-end: PRX roster on 2025-06-22 ---------------------------------
PROFILES = {
    "9801": {"name": "f0rsakeN", "current_team": {"name": "Paper Rex", "joined": "joined in April 2020"}, "past_teams": []},
    "7378": {"name": "Jinggg", "current_team": {"name": "Paper Rex", "joined": "joined in 2020"}, "past_teams": []},
    "16986": {"name": "d4v41", "current_team": {"name": "Paper Rex", "joined": "joined in August 2021"}, "past_teams": []},
    "17086": {"name": "something", "current_team": {"name": "Paper Rex", "joined": "joined in February 2020"}, "past_teams": []},
    "13744": {"name": "PatMen", "current_team": {"name": "Global Esports", "joined": "joined in December 2025"},
              "past_teams": [{"name": "Paper Rex", "dates": "March 2025 – December 2025"}]},
    "9800": {"name": "mindfreak", "current_team": {"name": "Talon", "joined": "joined in 2024"},
             "past_teams": [{"name": "Paper Rex", "dates": "January 2020 – August 2022"}]},  # left before 2025
}


class FakeClient:
    async def get_segments(self, path, **params):
        assert path == "/v2/player"
        return [PROFILES[str(params["id"])]]


def _setup_db(tmp_path) -> str:
    db = str(tmp_path / "prx.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO teams (team_id,name,last_updated) VALUES (624,'Paper Rex','2026-06-04T00:00:00+00:00')")
    for pid, prof in PROFILES.items():
        conn.execute("INSERT INTO players (player_id,handle,last_updated) VALUES (?,?,?)",
                     (int(pid), prof["name"], "2026-06-04T00:00:00+00:00"))
    conn.commit()
    conn.close()
    return db


def test_prx_roster_on_masters_toronto_final(tmp_path):
    db = _setup_db(tmp_path)
    asyncio.run(ingest_roster_history(db, client=FakeClient()))

    conn = sqlite3.connect(db)
    try:
        roster = players_on_team_at(conn, 624, "2025-06-22")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    assert roster == ["Jinggg", "PatMen", "d4v41", "f0rsakeN", "something"]  # sorted; mindfreak excluded


def test_idempotent_rebuild(tmp_path):
    db = _setup_db(tmp_path)
    asyncio.run(ingest_roster_history(db, client=FakeClient()))
    asyncio.run(ingest_roster_history(db, client=FakeClient()))  # rerun must not duplicate
    conn = sqlite3.connect(db)
    try:
        # f0rsakeN has exactly one PRX tenure row, not two
        n = conn.execute("SELECT COUNT(*) FROM roster_history WHERE player_id=9801").fetchone()[0]
    finally:
        conn.close()
    assert n == 1
