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
    # Map pool: win rates are probabilities; CT/T present.
    for m in s["map_pool"]:
        assert 0.0 <= (m["win_rate"] or 0) <= 1.0
        assert 0.0 <= (m["ct_win_rate"] or 0) <= 1.0
    # Comps are exactly 5 agents.
    for c in s["agents"]["comps_by_map"]:
        assert len(c["comp"]) == 5
    # Opening-duel win rate = fk / (fk + fd) per player.
    for d in s["opening_duels"]["by_player"]:
        if d["fk"] + d["fd"] > 0:
            assert abs(d["win_rate"] - d["fk"] / (d["fk"] + d["fd"])) < 1e-3  # stored rounded to 3dp


@needs_db
def test_window_limits_maps(conn):
    small = scouting.team_scouting(conn, 624, window=5)
    assert small["window_maps"] <= 5
