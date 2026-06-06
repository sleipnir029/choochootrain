"""Tests for models.elo_replay — chronological replay into elo_ratings. No network."""

import sqlite3

from ingestion.schema import init_db
from models.elo_replay import INITIAL_RATING, replay_elo


def _conn(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def _match(conn, mid, t1, t2, s1, s2, date, series=None):
    conn.execute(
        "INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id, "
        "team1_score, team2_score, winner_id, date_utc, format) "
        "VALUES (?,1,?,?,?,?,?,?,?,'Bo3')",
        (mid, series, t1, t2, s1, s2, t1 if s1 > s2 else t2, date),
    )


def test_replay_basic_zero_sum(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 1, 10, 20, 2, 0, "2024-01-01")
    ratings, n = replay_elo(conn)
    assert n == 1
    assert ratings[10] > INITIAL_RATING > ratings[20]
    assert ratings[10] + ratings[20] == 2 * INITIAL_RATING  # zero-sum
    # one snapshot row per team
    assert conn.execute("SELECT COUNT(*) FROM elo_ratings").fetchone()[0] == 2


def test_new_team_starts_at_initial(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 1, 10, 20, 2, 0, "2024-01-01")
    _match(conn, 2, 10, 30, 2, 1, "2024-01-02")  # 30 appears fresh
    ratings, _ = replay_elo(conn)
    # team 30 entered at 1500 and lost a close game -> below initial but not too far
    assert ratings[30] < INITIAL_RATING
    assert ratings[30] > 1480  # 2-1 loss moves less than a sweep


def test_showmatch_excluded(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 1, 15315, 15316, 0, 1, "2024-01-01", series="Showmatch: Showmatch")
    ratings, n = replay_elo(conn)
    assert n == 0
    assert ratings == {}
    assert conn.execute("SELECT COUNT(*) FROM elo_ratings").fetchone()[0] == 0


def test_daily_snapshot_collapses_same_day(tmp_path):
    conn = _conn(tmp_path)
    # team 10 plays twice on the same date -> one elo_ratings row holding the
    # end-of-day rating (PK is (team_id, as_of_date)).
    _match(conn, 1, 10, 20, 2, 0, "2024-01-01")
    _match(conn, 2, 10, 30, 2, 0, "2024-01-01")
    ratings, _ = replay_elo(conn)
    rows = conn.execute(
        "SELECT rating FROM elo_ratings WHERE team_id=10 AND as_of_date='2024-01-01'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["rating"] == ratings[10]  # final, post-second-match


def test_replay_idempotent(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 1, 10, 20, 2, 0, "2024-01-01")
    _match(conn, 2, 20, 30, 2, 1, "2024-01-02")
    r1, n1 = replay_elo(conn)
    r2, n2 = replay_elo(conn)
    assert n1 == n2 == 2
    assert r1 == r2
    # rebuild does not accumulate rows: team 20 plays on two dates (2 rows),
    # teams 10 and 30 once each -> 4 snapshot rows, stable across rebuilds.
    assert conn.execute("SELECT COUNT(*) FROM elo_ratings").fetchone()[0] == 4
