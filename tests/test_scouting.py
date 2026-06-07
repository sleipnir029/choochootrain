"""Tests for models.scouting — invariants against the warehouse (needs data/prx.db)."""

import sqlite3
from pathlib import Path

import pytest

from models import scouting

_DB = "data/prx.db"
needs_db = pytest.mark.skipif(not Path(_DB).exists(), reason="needs data/prx.db")


@pytest.fixture
def conn():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@needs_db
def test_team_scouting_shape_and_ranges(conn):
    s = scouting.team_scouting(conn, 624, window=30)
    assert 0 < s["window_maps"] <= 30
    # Map pool: win rates are probabilities; CT/T present; shrunk rate also in range.
    for m in s["map_pool"]:
        assert 0.0 <= (m["win_rate"] or 0) <= 1.0
        assert 0.0 <= (m["win_rate_adj"] or 0) <= 1.0
        assert 0.0 <= (m["ct_win_rate"] or 0) <= 1.0
    # Comps are exactly 5 agents, with a role composition that sums to 5.
    for c in s["agents"]["comps_by_map"]:
        assert len(c["comp"]) == 5
        assert sum(r["n"] for r in c["roles"]) == 5
    # Every player carries a role profile with a known label.
    for p in s["agents"]["by_player"]:
        assert p["profile"]["label"] in {"one-trick", "flex", "specialist"}
    # Opening-duel win rate = fk / (fk + fd) per player (NOT shrunk).
    for d in s["opening_duels"]["by_player"]:
        if d["fk"] + d["fd"] > 0:
            assert abs(d["win_rate"] - d["fk"] / (d["fk"] + d["fd"])) < 1e-3  # stored rounded to 3dp


def test_shrinkage_pulls_small_samples_toward_half():
    # A perfect-but-tiny record is pulled well below 1.0; a 0-of-1 well above 0.0.
    assert 0.5 < scouting._shrunk_wr(5, 5) < 1.0
    assert 0.0 < scouting._shrunk_wr(0, 1) < 0.5
    # A large sample is barely moved; empty is None.
    assert abs(scouting._shrunk_wr(80, 100) - 0.8) < 0.03
    assert scouting._shrunk_wr(0, 0) is None


def test_role_profile_classifies_one_trick_and_flex():
    from collections import Counter
    one_trick = scouting._role_profile(Counter({"Jett": 20, "Raze": 1}))
    assert one_trick["label"] == "one-trick" and one_trick["main_role"] == "Duelist"
    flex = scouting._role_profile(Counter({"Omen": 10, "Killjoy": 10}))  # Controller + Sentinel
    assert flex["label"] == "flex" and len(flex["roles"]) == 2


@needs_db
def test_meta_shift_shape(conn):
    ms = scouting.meta_shift(conn, 624)
    assert set(ms) == {"recent", "prior", "movers"}
    for mv in ms["movers"]:
        assert mv["recent_n"] >= 2 and mv["prior_n"] >= 2
        assert abs(mv["delta"]) >= 0.12


@needs_db
def test_window_limits_maps(conn):
    small = scouting.team_scouting(conn, 624, window=5)
    assert small["window_maps"] <= 5
