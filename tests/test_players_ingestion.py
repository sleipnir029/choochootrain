"""Tests for ingestion.players — handle resolution (incl. disambiguation),
profile upsert, player_id backfill, idempotency. No network."""

import asyncio
import sqlite3

from ingestion.players import _team_matches, ingest_players, parse_player
from ingestion.schema import init_db


def test_team_matches_handles_glued_dates():
    # vlrggapi glues the date range onto past-team names; substring match must cope.
    prof = {"current_team": {"name": "Enterprise Esports"},
            "past_teams": [{"name": "Karmine CorpDecember 2023 – November 2024"}]}
    assert _team_matches({"karmine corp"}, prof) is True
    assert _team_matches({"paper rex"}, prof) is False
    # plain-string past_teams entry also tolerated
    assert _team_matches({"fnatic"}, {"past_teams": ["FNATIC"]}) is True

# search results keyed by lowercased query
SEARCH = {
    "jinggg": [{"id": "7378", "name": "Jinggg"}],
    "f0rsaken": [  # two exact matches -> disambiguate by team
        {"id": "9801", "name": "f0rsakeN"},
        {"id": "50001", "name": "f0rsakeN"},
        {"id": "60205", "name": "Xatas"},
    ],
    "dup": [{"id": "111", "name": "dup"}, {"id": "222", "name": "dup"}],  # ambiguous, no team match
    "ghost": [{"id": "333", "name": "Ghosty"}],  # no exact match
}
PROFILES = {
    "7378": {"id": "7378", "name": "Jinggg", "real_name": "Wang Jing Jie", "country": "sg",
             "current_team": {"name": "Paper Rex"}, "past_teams": []},
    "9801": {"id": "9801", "name": "f0rsakeN", "real_name": "Jason Susanto", "country": "id",
             "current_team": {"name": "Paper Rex"}, "past_teams": []},
    "50001": {"id": "50001", "name": "f0rsakeN", "real_name": "Fan Acct", "country": "us",
              "current_team": {"name": "Some FC"}, "past_teams": []},
    "111": {"id": "111", "name": "dup", "current_team": {"name": "Team X"}, "past_teams": []},
    "222": {"id": "222", "name": "dup", "current_team": {"name": "Team Y"}, "past_teams": []},
}


class FakeClient:
    async def get_json(self, path, **params):
        assert path == "/v2/search"
        return {"data": {"segments": {"results": {"players": SEARCH.get(params["q"].lower(), [])}}}}

    async def get_segments(self, path, **params):
        assert path == "/v2/player"
        return [PROFILES[str(params["id"])]]


def test_parse_player_maps_current_team_by_name():
    row = parse_player(PROFILES["7378"], {"paper rex": 624})
    assert row["player_id"] == 7378 and row["handle"] == "Jinggg"
    assert row["real_name"] == "Wang Jing Jie" and row["country"] == "sg"
    assert row["current_team_id"] == 624
    # team not in map -> NULL
    assert parse_player(PROFILES["7378"], {})["current_team_id"] is None


def _setup_db(tmp_path) -> str:
    db = str(tmp_path / "prx.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO events (event_id,name,tier,region,start_date,end_date) "
                 "VALUES (1921,'Masters Madrid 2024','Masters','global','2024-03-14','2024-03-24')")
    for tid, name in ((624, "Paper Rex"), (2, "Sentinels")):
        conn.execute("INSERT INTO teams (team_id,name,last_updated) VALUES (?,?,?)",
                     (tid, name, "2026-06-04T00:00:00+00:00"))
    conn.execute("INSERT INTO matches (match_id,event_id,team1_id,team2_id,team1_score,team2_score,"
                 "date_utc,format) VALUES (1,1921,624,2,2,0,'2024-03-14','Bo3')")
    conn.execute("INSERT INTO maps (match_id,map_index,map_name,team1_score,team2_score) "
                 "VALUES (1,0,'Bind',13,8)")
    map_id = conn.execute("SELECT map_id FROM maps").fetchone()[0]
    rows = [("Jinggg", 624), ("f0rsakeN", 624), ("dup", 2), ("ghost", 2)]
    for handle, team in rows:
        conn.execute("INSERT INTO map_player_stats (map_id,player_handle,team_id_at_match,agent) "
                     "VALUES (?,?,?,?)", (map_id, handle, team, "Jett"))
    conn.commit()
    conn.close()
    return db


def _pid(db, handle):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT player_id FROM map_player_stats WHERE player_handle=?", (handle,)).fetchone()[0]
    finally:
        conn.close()


def test_resolve_disambiguate_and_backfill(tmp_path):
    db = _setup_db(tmp_path)
    s = asyncio.run(ingest_players(db, client=FakeClient()))

    assert s["resolved"] == 2                       # Jinggg + f0rsakeN
    assert set(s["unresolved"]) == {"dup", "ghost"}  # ambiguous / no exact match
    assert s["stat_rows_backfilled"] == 2

    assert _pid(db, "Jinggg") == 7378
    assert _pid(db, "f0rsakeN") == 9801              # picked PRX account, not the fan acct
    assert _pid(db, "dup") is None and _pid(db, "ghost") is None

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 2
        jg = dict(conn.execute("SELECT * FROM players WHERE player_id=7378").fetchone())
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    assert jg["real_name"] == "Wang Jing Jie" and jg["current_team_id"] == 624


def test_idempotent(tmp_path):
    db = _setup_db(tmp_path)
    asyncio.run(ingest_players(db, client=FakeClient()))
    s2 = asyncio.run(ingest_players(db, client=FakeClient()))
    # already-resolved handles are no longer pending; only dup/ghost retried (still unresolved)
    assert s2["resolved"] == 0
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 2
    finally:
        conn.close()
