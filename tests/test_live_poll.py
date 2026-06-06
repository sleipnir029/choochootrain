"""Tests for scheduler.jobs.live_poll — parse / diff / persist / poll. No network.

A FakeClient returns queued canned live_score segment lists; async functions are
driven with asyncio.run (no pytest-asyncio), mirroring the ingestion tests.
"""

import asyncio
import sqlite3

from ingestion.schema import init_db
from scheduler.jobs.live_poll import (
    parse_live_segment,
    poll_once,
    select_match,
    state_changed,
    write_live_state,
)


def _seg(match_id, score1, score2, **over):
    seg = {"match_id": match_id, "team1": "Team A", "team2": "Team B",
           "score1": score1, "score2": score2, "current_map": "Bind",
           "team1_round_ct": "6", "team1_round_t": "5",
           "team2_round_ct": "4", "team2_round_t": "3", "map_number": "2"}
    seg.update(over)
    return seg


class FakeClient:
    def __init__(self, queue):
        self._queue = list(queue)  # list of segment-lists, one per call

    async def get_segments(self, path, **params):
        return self._queue.pop(0) if self._queue else []


def _conn(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def test_parse_handles_strings_and_na():
    s = parse_live_segment(_seg(123, "13", "7", team1_round_ct="N/A", map_number=""))
    assert s["match_id"] == 123
    assert s["team1_score"] == 13 and s["team2_score"] == 7
    assert s["team1_round_ct"] is None   # "N/A" -> None
    assert s["map_number"] is None       # "" -> None
    assert s["current_map"] == "Bind"


def test_state_changed():
    a = parse_live_segment(_seg(1, "0", "0"))
    b = parse_live_segment(_seg(1, "1", "0"))
    assert state_changed(a, b) == ["team1_score"]
    assert state_changed(a, a) == []
    assert state_changed(None, b) == []                      # no baseline
    assert state_changed(a, parse_live_segment(_seg(2, "0", "0"))) == []  # different match


def test_select_match_prefers_prx():
    segs = [_seg(1, "0", "0"), _seg(2, "0", "0", team1="Paper Rex", team2="NRG")]
    assert select_match(segs)["match_id"] == 2
    assert select_match([]) is None


def test_write_live_state_is_singleton(tmp_path):
    conn = _conn(tmp_path)
    write_live_state(conn, parse_live_segment(_seg(1, "0", "0")))
    write_live_state(conn, parse_live_segment(_seg(2, "5", "3")))
    rows = conn.execute("SELECT match_id, team1_score FROM live_state").fetchall()
    assert len(rows) == 1
    assert rows[0]["match_id"] == 2 and rows[0]["team1_score"] == 5
    assert conn.execute("SELECT last_updated FROM live_state").fetchone()[0]


def test_poll_once_tracks_and_persists_change(tmp_path):
    conn = _conn(tmp_path)
    client = FakeClient([[_seg(99, "0", "0")], [_seg(99, "1", "0")]])

    s1 = asyncio.run(poll_once(client, conn, None))      # baseline
    assert s1["match_id"] == 99 and s1["team1_score"] == 0
    s2 = asyncio.run(poll_once(client, conn, s1))        # score ticks up
    assert state_changed(s1, s2) == ["team1_score"]
    row = conn.execute("SELECT match_id, team1_score FROM live_state").fetchone()
    assert row["match_id"] == 99 and row["team1_score"] == 1


def test_poll_once_no_live_match(tmp_path):
    conn = _conn(tmp_path)
    assert asyncio.run(poll_once(FakeClient([[]]), conn, None)) is None
    assert conn.execute("SELECT COUNT(*) FROM live_state").fetchone()[0] == 0
