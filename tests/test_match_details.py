"""Tests for ingestion.match_details — parsers + DB write of the 4 tables."""

import asyncio
import sqlite3

from ingestion.match_details import (
    ingest_detail_into_db,
    ingest_match_details,
    parse_duration,
    parse_economy,
    parse_map,
    parse_player_stats,
    parse_rounds,
    round_half,
)
from ingestion.schema import init_db

T1, T2 = 8877, 11328  # team ids


def _player(name, agent="Jett"):
    return {"name": name, "agent": agent, "rating": "1.20", "acs": "250", "kills": "18",
            "deaths": "14", "assists": "5", "kast": "70%", "adr": "160", "hs_pct": "28%",
            "fk": "3", "fd": "2"}


def _make_detail(n_valid_rounds=21):
    rounds = []
    for i in range(1, n_valid_rounds + 1):
        side = "ct" if i <= 12 else "t"
        rounds.append({"round_num": i, "winner": "team1" if i % 3 else "team2", "side": side})
    rounds += [{"round_num": 99, "winner": "", "side": ""}]  # placeholder, filtered out
    return {
        "match_id": "312765",
        "teams": [{"id": str(T1), "name": "Karmine Corp"}, {"id": str(T2), "name": "FunPlus Phoenix"}],
        "maps": [{
            "map_name": "Icebox",
            "picked_by": "PICK",
            "duration": "59:51",
            "score": {"team1": 13, "team2": 8},
            "score_ct": {"team1": "7", "team2": "3"},
            "score_t": {"team1": "6", "team2": "5"},
            "score_ot": {"team1": "", "team2": ""},
            "players": {
                "team1": [_player(f"KC{i}") for i in range(5)],
                "team2": [_player(f"FPX{i}") for i in range(5)],
            },
            "rounds": rounds,
            "economy": [
                {"0": "KC", "1": "1", "2": "3 (1)", "3": "0 (0)", "4": "5 (2)", "5": "13 (10)"},
                {"0": "FPX", "1": "1", "2": "3 (1)", "3": "1 (0)", "4": "8 (3)", "5": "9 (4)"},
            ],
        }],
    }


def test_parse_duration():
    assert parse_duration("59:51") == 3591
    assert parse_duration("1:02:03") == 3723
    assert parse_duration("") is None


def test_round_half():
    assert round_half(1) == "first" and round_half(12) == "first"
    assert round_half(13) == "second" and round_half(24) == "second"
    assert round_half(25) == "ot"


def test_parse_map():
    m = _make_detail()["maps"][0]
    row = parse_map(m, 312765, 0, (T1, T2))
    assert row["map_name"] == "Icebox"
    assert row["team1_score"] == 13 and row["team2_score"] == 8
    assert row["team1_ct_score"] == 7 and row["team1_t_score"] == 6
    assert row["duration_seconds"] == 3591
    assert row["winner_id"] == T1
    assert row["picked_by_team_id"] is None


def test_parse_rounds_filters_and_sides():
    m = _make_detail(21)["maps"][0]
    rows = parse_rounds(m["rounds"], map_id=5, team_ids=(T1, T2))
    assert len(rows) == 21  # placeholder filtered
    r1 = rows[0]
    assert r1["team1_side"] == "ct" and r1["team2_side"] == "t" and r1["half"] == "first"
    assert rows[12]["team1_side"] == "t" and rows[12]["half"] == "second"
    assert set(r["winner_id"] for r in rows) <= {T1, T2}


def test_parse_player_stats():
    m = _make_detail()["maps"][0]
    rows = parse_player_stats(m["players"], map_id=5, team_ids=(T1, T2))
    assert len(rows) == 10
    kc = [r for r in rows if r["team_id_at_match"] == T1]
    assert len(kc) == 5 and kc[0]["player_id"] is None
    assert kc[0]["kast_pct"] == 70 and kc[0]["hs_pct"] == 28 and kc[0]["rating"] == 1.20
    assert kc[0]["acs"] == 250 and kc[0]["agent"] == "Jett"


def test_parse_economy():
    m = _make_detail()["maps"][0]
    rows = parse_economy(m["economy"], map_id=5, team_ids=(T1, T2))
    kc = rows[0]
    assert kc["pistol_win_pct"] == 50           # 1 of 2
    assert kc["eco_win_pct"] == 33              # 1 of 3
    assert kc["semi_buy_win_pct"] == 40         # 2 of 5  ('$$')
    assert kc["full_buy_win_pct"] == 77         # 10 of 13 ('$$$')


def _setup_db(tmp_path) -> str:
    db = str(tmp_path / "prx.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO events (event_id,name,tier,region,start_date,end_date) "
                 "VALUES (1921,'Masters Madrid 2024','Masters','global','2024-03-14','2024-03-24')")
    for tid, name in ((T1, "Karmine Corp"), (T2, "FunPlus Phoenix")):
        conn.execute("INSERT INTO teams (team_id,name,last_updated) VALUES (?,?,?)",
                     (tid, name, "2026-06-04T00:00:00+00:00"))
    conn.execute("INSERT INTO matches (match_id,event_id,team1_id,team2_id,team1_score,team2_score,"
                 "date_utc,format) VALUES (312765,1921,?,?,1,0,'2024-03-14','Bo3')", (T1, T2))
    conn.commit()
    conn.close()
    return db


def _count(db, table):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_ingest_into_db_complete_and_idempotent(tmp_path):
    db = _setup_db(tmp_path)
    detail = _make_detail(21)  # 13+8 = 21 valid rounds -> complete

    conn = sqlite3.connect(db)
    counts = ingest_detail_into_db(conn, detail)
    conn.commit()
    conn.close()
    assert counts == {"maps": 1, "rounds": 21, "player_stats": 10, "economy": 2, "maps_complete": 1}
    assert _count(db, "maps") == 1 and _count(db, "rounds") == 21
    assert _count(db, "map_player_stats") == 10 and _count(db, "map_team_economy") == 2

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    is_complete = conn.execute("SELECT is_rounds_complete FROM maps").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    assert is_complete == 1 and fk == []

    # Idempotent: re-ingest, no duplicate rows.
    conn = sqlite3.connect(db)
    ingest_detail_into_db(conn, detail)
    conn.commit()
    conn.close()
    assert _count(db, "rounds") == 21 and _count(db, "map_player_stats") == 10


def test_incomplete_rounds_flagged(tmp_path):
    db = _setup_db(tmp_path)
    detail = _make_detail(10)  # only 10 valid rounds vs score 21 -> incomplete
    conn = sqlite3.connect(db)
    counts = ingest_detail_into_db(conn, detail)
    conn.commit()
    is_complete = conn.execute("SELECT is_rounds_complete FROM maps").fetchone()[0]
    conn.close()
    assert counts["maps_complete"] == 0 and is_complete == 0


class _FakeClient:
    def __init__(self, detail):
        self._detail = detail

    async def get_segments(self, path, **params):
        assert path == "/v2/match/details"
        return [self._detail]


def test_ingest_match_details_via_client(tmp_path):
    db = _setup_db(tmp_path)
    counts = asyncio.run(ingest_match_details(312765, db, client=_FakeClient(_make_detail(21))))
    assert counts["maps"] == 1 and counts["rounds"] == 21 and _count(db, "map_player_stats") == 10
