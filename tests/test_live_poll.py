"""Tests for scheduler.jobs.live_poll — parse / diff / persist / poll. No network.

A FakeClient returns queued canned live_score segment lists; async functions are
driven with asyncio.run (no pytest-asyncio), mirroring the ingestion tests.
"""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from ingestion.schema import init_db
from scheduler.jobs.live_poll import (
    classify_tier,
    make_prediction_callback,
    parse_live_segment,
    poll_once,
    select_match,
    state_changed,
    to_predict_live_state,
    write_live_prediction,
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


def test_classify_tier():
    assert classify_tier("Valorant Champions 2025") == "Champions"
    assert classify_tier("Valorant Masters Toronto 2025") == "Masters"
    assert classify_tier("Champions Tour 2024: Pacific Kickoff") == "Kickoff"  # brand, not the tournament
    assert classify_tier("Champions Tour 2024: Pacific Stage 1") == "RegionalLeague"
    assert classify_tier("VCT 2025: Pacific Stage 2") == "RegionalLeague"
    assert classify_tier(None) == "RegionalLeague"


def test_priority_prx_beats_higher_tier():
    champ = _seg(1, "0", "0", team1="NRG", team2="SEN", match_event="Valorant Champions 2025")
    prx = _seg(2, "0", "0", team1="Paper Rex", team2="DRX", match_event="Valorant Masters Toronto 2025")
    assert select_match([champ, prx])["match_id"] == 2   # PRX > higher tier


def test_priority_tier_order_no_prx():
    champ = _seg(1, "0", "0", team1="A", team2="B", match_event="Valorant Champions 2025")
    masters = _seg(2, "0", "0", team1="C", team2="D", match_event="Masters Madrid")
    regional = _seg(3, "0", "0", team1="E", team2="F", match_event="Pacific Stage 1")
    assert select_match([regional, masters, champ])["match_id"] == 1   # Champions wins
    assert select_match([regional, masters])["match_id"] == 2          # Masters > Regional


def test_priority_same_tier_earliest_start():
    early = _seg(1, "0", "0", team1="A", team2="B", match_event="Pacific Stage 1", unix_timestamp="1000")
    late = _seg(2, "0", "0", team1="C", team2="D", match_event="EMEA Stage 1", unix_timestamp="2000")
    assert select_match([late, early])["match_id"] == 1   # earliest start wins the tie


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


def test_on_change_fires_once_per_change(tmp_path):
    conn = _conn(tmp_path)
    # Same match across 5 polls: baseline, repeat, change, repeat, change.
    states = [_seg(7, "0", "0"), _seg(7, "0", "0"), _seg(7, "1", "0"),
              _seg(7, "1", "0"), _seg(7, "1", "1")]
    client = FakeClient([[s] for s in states])
    calls = []

    last = None
    for _ in states:
        last = asyncio.run(poll_once(client, conn, last, on_change=lambda s, c: calls.append(c)))

    assert len(calls) == 2                     # only the two transitions, not baseline/repeats
    assert calls[0] == ["team1_score"]
    assert calls[1] == ["team2_score"]


def test_on_change_not_fired_on_baseline_or_match_switch(tmp_path):
    conn = _conn(tmp_path)
    calls = []
    cb = lambda s, c: calls.append(c)  # noqa: E731
    s1 = asyncio.run(poll_once(FakeClient([[_seg(1, "0", "0")]]), conn, None, on_change=cb))
    # different match next -> new track, not a change
    asyncio.run(poll_once(FakeClient([[_seg(2, "5", "5")]]), conn, s1, on_change=cb))
    assert calls == []


def test_on_change_exception_is_swallowed(tmp_path):
    conn = _conn(tmp_path)
    def boom(state, changed):
        raise RuntimeError("prediction blew up")
    a = asyncio.run(poll_once(FakeClient([[_seg(3, "0", "0")]]), conn, None, on_change=boom))
    # a change with a raising callback must not propagate
    b = asyncio.run(poll_once(FakeClient([[_seg(3, "1", "0")]]), conn, a, on_change=boom))
    assert b["team1_score"] == 1               # poll completed despite the callback error


def test_to_predict_live_state_maps_rounds_and_half():
    # round counts (not the 0/0 map score) drive the score-state lookup
    s = parse_live_segment(_seg(1, "0", "0", team1_round_ct="7", team1_round_t="0",
                                team2_round_ct="0", team2_round_t="5", map_number="2"))
    ls = to_predict_live_state(s)
    assert ls["team1_score"] == 7 and ls["team2_score"] == 5
    assert ls["half"] == "second"              # 7+5 = 12 rounds played -> second half
    assert ls["team1_side"] in ("ct", "t")


def test_to_predict_live_state_half_boundaries():
    def half_for(t1ct, t1t, t2ct, t2t):
        s = {"team1_round_ct": t1ct, "team1_round_t": t1t,
             "team2_round_ct": t2ct, "team2_round_t": t2t}
        return to_predict_live_state(s)["half"]
    assert half_for(0, 0, 0, 0) == "first"     # 0 rounds
    assert half_for(6, 0, 0, 5) == "first"     # 11
    assert half_for(7, 0, 0, 6) == "second"    # 13
    assert half_for(13, 0, 0, 12) == "ot"      # 25


def test_write_live_prediction_inserts_row(tmp_path):
    conn = _conn(tmp_path)
    write_live_prediction(conn, 42, 1, 0.73)
    row = conn.execute("SELECT match_id, map_index, team1_win_prob, computed_at "
                       "FROM live_predictions").fetchone()
    assert row["match_id"] == 42 and row["map_index"] == 1
    assert abs(row["team1_win_prob"] - 0.73) < 1e-9 and row["computed_at"]


@pytest.mark.skipif(
    not (Path("data/prx.db").exists() and Path("models/saved/bayes_logistic.nc").exists()),
    reason="needs data/prx.db + trained posterior",
)
def test_prediction_callback_stores_per_change(tmp_path):
    pytest.importorskip("bambi")
    conn = _conn(tmp_path)  # temp db holds live_state; predictions go to the real db
    # Use the real warehouse for both prediction and live_predictions writes.
    cb = make_prediction_callback("data/prx.db")
    # Clear any prior live_predictions for this ingested match, then simulate 2 changes.
    real = sqlite3.connect("data/prx.db")
    real.execute("DELETE FROM live_predictions WHERE match_id = 666493")
    real.commit()
    states = [_seg(666493, "0", "0", map_number="1", team1_round_ct="5", team1_round_t="0",
                   team2_round_ct="0", team2_round_t="3"),
              _seg(666493, "0", "0", map_number="1", team1_round_ct="6", team1_round_t="0",
                   team2_round_ct="0", team2_round_t="3")]
    client = FakeClient([[s] for s in states])
    last = None
    for _ in states:
        last = asyncio.run(poll_once(client, conn, last, on_change=cb))
    rows = real.execute("SELECT team1_win_prob FROM live_predictions "
                        "WHERE match_id = 666493").fetchall()
    real.close()
    assert len(rows) == 1                       # one change (round 5->6) -> one stored prediction
    assert 0.0 < rows[0][0] < 1.0
