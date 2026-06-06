"""Tests for models.elo_map_offsets — win-rate deviation + partial pooling. No network."""

import sqlite3

from ingestion.schema import init_db
from models.elo_map_offsets import compute_map_offsets


def _conn(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


_MID = [0]  # monotonic match-id source for the helper


def _game(conn, t1, t2, map_name, winner, date="2024-01-01", series=None):
    """One Bo1-style match with a single map; winner is a team_id."""
    _MID[0] += 1
    mid = _MID[0]
    s1, s2 = (1, 0) if winner == t1 else (0, 1)
    conn.execute(
        "INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id, "
        "team1_score, team2_score, winner_id, date_utc, format) "
        "VALUES (?,1,?,?,?,?,?,?,?,'Bo1')",
        (mid, series, t1, t2, s1, s2, winner, date),
    )
    conn.execute(
        "INSERT INTO maps (match_id, map_index, map_name, team1_score, team2_score, winner_id) "
        "VALUES (?,0,?,?,?,?)",
        (mid, map_name, 13 if winner == t1 else 5, 13 if winner == t2 else 5, winner),
    )


def setup_function():
    _MID[0] = 0


def test_offset_sign_and_zero_sum(tmp_path):
    conn = _conn(tmp_path)
    # Team 10 wins all of Bind, loses all of Haven, equal games each.
    for _ in range(10):
        _game(conn, 10, 20, "Bind", winner=10)
        _game(conn, 10, 30, "Haven", winner=30)
    offsets = compute_map_offsets(conn)
    assert offsets[(10, "Bind")] > 0   # over-performs on Bind
    assert offsets[(10, "Haven")] < 0  # under-performs on Haven
    # Equal games + symmetric deviations -> sums to ~0 per team.
    team10 = sum(o for (tid, _), o in offsets.items() if tid == 10)
    assert abs(team10) < 1e-9


def test_partial_pooling_shrinks_small_samples(tmp_path):
    conn = _conn(tmp_path)
    # Same 100% map win rate, but Bind has many games and Split has few.
    # Bind's offset should be larger in magnitude (less shrinkage).
    for _ in range(30):
        _game(conn, 10, 20, "Bind", winner=10)
    for _ in range(2):
        _game(conn, 10, 30, "Split", winner=10)
    # Give team 10 some losses so overall_wr < 1 and deviations are non-zero.
    for _ in range(10):
        _game(conn, 10, 40, "Haven", winner=40)
    offsets = compute_map_offsets(conn)
    assert offsets[(10, "Bind")] > offsets[(10, "Split")] > 0


def test_as_of_date_is_latest_match(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 10, 20, "Bind", winner=10, date="2024-01-01")
    _game(conn, 10, 20, "Haven", winner=20, date="2025-12-31")
    compute_map_offsets(conn)
    dates = {r["as_of_date"] for r in conn.execute("SELECT as_of_date FROM elo_map_offsets")}
    assert dates == {"2025-12-31"}


def test_showmatch_excluded(tmp_path):
    conn = _conn(tmp_path)
    _game(conn, 15315, 15316, "Bind", winner=15315, series="Showmatch: Showmatch")
    offsets = compute_map_offsets(conn)
    assert offsets == {}
    assert conn.execute("SELECT COUNT(*) FROM elo_map_offsets").fetchone()[0] == 0


def test_idempotent_rebuild(tmp_path):
    conn = _conn(tmp_path)
    for _ in range(5):
        _game(conn, 10, 20, "Bind", winner=10)
        _game(conn, 10, 30, "Haven", winner=30)
    o1 = compute_map_offsets(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM elo_map_offsets").fetchone()[0]
    o2 = compute_map_offsets(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM elo_map_offsets").fetchone()[0]
    assert o1 == o2
    assert n1 == n2
