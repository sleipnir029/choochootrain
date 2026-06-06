"""Tests for models.score_state — pre-round score-state -> P(win map) lookup. No network."""

import sqlite3

from ingestion.schema import init_db
from models.score_state import LAPLACE_DEN, LAPLACE_NUM, compute_score_state


def _conn(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute(
        "INSERT INTO events (event_id, name, tier, region, start_date, end_date) "
        "VALUES (1, 'E', 'Masters', 'global', '2024-01-01', '2024-12-31')"
    )
    return c


_MID = [0]


def setup_function():
    _MID[0] = 0


def _map_with_rounds(conn, t1, t2, round_winners, t1_side="ct", series=None):
    """One map; round_winners is a list of team_ids (first half, t1 on t1_side).

    Map winner = whoever won more rounds.
    """
    _MID[0] += 1
    mid = _MID[0]
    t1w = sum(1 for w in round_winners if w == t1)
    t2w = len(round_winners) - t1w
    map_winner = t1 if t1w > t2w else t2
    conn.execute(
        "INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id, "
        "team1_score, team2_score, winner_id, date_utc, format) "
        "VALUES (?,1,?,?,?,1,0,?,'2024-01-01','Bo1')",
        (mid, series, t1, t2, map_winner),
    )
    cur = conn.execute(
        "INSERT INTO maps (match_id, map_index, map_name, team1_score, team2_score, winner_id) "
        "VALUES (?,0,'Bind',?,?,?)",
        (mid, t1w, t2w, map_winner),
    )
    map_id = cur.lastrowid
    opp = "t" if t1_side == "ct" else "ct"
    for i, w in enumerate(round_winners, start=1):
        conn.execute(
            "INSERT INTO rounds (map_id, round_number, half, team1_side, team2_side, winner_id) "
            "VALUES (?,?,'first',?,?,?)",
            (map_id, i, t1_side, opp, w),
        )
    return mid, map_winner


def test_basic_counts_and_symmetry(tmp_path):
    conn = _conn(tmp_path)
    # team 10 wins both rounds (and the map); t1 on ct.
    _map_with_rounds(conn, 10, 20, [10, 10], t1_side="ct")
    agg = compute_score_state(conn)
    # Round 1 pre-state 0-0: team1 (ct) won map, team2 (t) lost.
    assert agg[("first", 0, 0, "ct")] == [1, 1]
    assert agg[("first", 0, 0, "t")] == [1, 0]
    # Round 2 pre-state: team1 1-0 (ct), team2 0-1 (t).
    assert agg[("first", 1, 0, "ct")] == [1, 1]
    assert agg[("first", 0, 1, "t")] == [1, 0]


def test_smoothing_formula(tmp_path):
    conn = _conn(tmp_path)
    _map_with_rounds(conn, 10, 20, [10, 10], t1_side="ct")
    compute_score_state(conn)
    row = conn.execute(
        "SELECT n_wins, n_observations, smoothed_win_pct FROM score_state_lookup "
        "WHERE half='first' AND team_score=0 AND opp_score=0 AND side='ct'"
    ).fetchone()
    expected = (row["n_wins"] + LAPLACE_NUM) / (row["n_observations"] + LAPLACE_DEN)
    assert abs(row["smoothed_win_pct"] - expected) < 1e-12
    assert row["n_wins"] == 1 and row["n_observations"] == 1


def test_states_accumulate_across_maps(tmp_path):
    conn = _conn(tmp_path)
    # Two maps, same opening state (0-0, ct), different map outcomes.
    _map_with_rounds(conn, 10, 20, [10, 10], t1_side="ct")  # ct team wins
    _map_with_rounds(conn, 30, 40, [40, 40], t1_side="ct")  # ct team loses
    agg = compute_score_state(conn)
    assert agg[("first", 0, 0, "ct")] == [2, 1]  # 2 obs, 1 map win


def test_big_lead_has_high_win_pct(tmp_path):
    conn = _conn(tmp_path)
    # The team that builds a big lead almost always wins -> high smoothed pct
    # at the lead state; the trailing mirror state is low.
    for _ in range(20):
        _map_with_rounds(conn, 10, 20, [10, 10, 10, 20], t1_side="ct")  # 10 leads 3-0 then wins
    compute_score_state(conn)
    lead = conn.execute(
        "SELECT smoothed_win_pct FROM score_state_lookup "
        "WHERE half='first' AND team_score=3 AND opp_score=0 AND side='ct'"
    ).fetchone()["smoothed_win_pct"]
    trail = conn.execute(
        "SELECT smoothed_win_pct FROM score_state_lookup "
        "WHERE half='first' AND team_score=0 AND opp_score=3 AND side='t'"
    ).fetchone()["smoothed_win_pct"]
    assert lead > 0.8
    assert trail < 0.2


def test_showmatch_excluded(tmp_path):
    conn = _conn(tmp_path)
    _map_with_rounds(conn, 10, 20, [10, 10], t1_side="ct")
    _map_with_rounds(conn, 15315, 15316, [15315, 15315], t1_side="ct",
                     series="Showmatch: Showmatch")
    agg = compute_score_state(conn)
    # Only the non-showmatch map contributes (2 obs at the 0-0 ct state, not 4).
    assert agg[("first", 0, 0, "ct")] == [1, 1]


def test_idempotent_rebuild(tmp_path):
    conn = _conn(tmp_path)
    _map_with_rounds(conn, 10, 20, [10, 10], t1_side="ct")
    compute_score_state(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM score_state_lookup").fetchone()[0]
    compute_score_state(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM score_state_lookup").fetchone()[0]
    assert n1 == n2
