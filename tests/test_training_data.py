"""Tests for models.training_data — point-in-time per-map feature builder. No network."""

import sqlite3

from ingestion.schema import init_db
from models.training_data import build_training_data


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


def _match(conn, t1, t2, date, maps, series=None):
    """maps: list of (map_name, winner_id, t1_side[, with_round=True])."""
    _MID[0] += 1
    mid = _MID[0]
    s1 = sum(1 for m in maps if m[1] == t1)
    s2 = len(maps) - s1
    conn.execute(
        "INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id, "
        "team1_score, team2_score, winner_id, date_utc, format, patch_id) "
        "VALUES (?,1,?,?,?,?,?,?,?,'Bo3','8.04')",
        (mid, series, t1, t2, s1, s2, t1 if s1 > s2 else t2, date),
    )
    for idx, m in enumerate(maps):
        name, winner, side = m[0], m[1], m[2]
        with_round = m[3] if len(m) > 3 else True
        cur = conn.execute(
            "INSERT INTO maps (match_id, map_index, map_name, team1_score, team2_score, winner_id) "
            "VALUES (?,?,?,?,?,?)",
            (mid, idx, name, 13 if winner == t1 else 5, 13 if winner == t2 else 5, winner),
        )
        if with_round:
            map_id = cur.lastrowid
            opp = "ct" if side == "t" else "t"
            conn.execute(
                "INSERT INTO rounds (map_id, round_number, half, team1_side, team2_side, winner_id) "
                "VALUES (?,1,'first',?,?,?)",
                (map_id, side, opp, winner),
            )
    return mid


def test_row_count_no_nan_and_columns(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t"), ("Haven", 20, "ct")])
    _match(conn, 10, 30, "2024-01-02", [("Split", 10, "t")])
    df = build_training_data(conn)
    assert len(df) == 3  # one row per competitive map
    assert df.isna().sum().sum() == 0
    for col in ["elo_diff", "map_elo_diff", "skill_diff", "team1_starts_atk_or_def",
                "recent_form_team1", "recent_form_team2", "h2h_team1_win_rate",
                "patch_id", "tier", "team1_won"]:
        assert col in df.columns
    # no map_player_stats in this synthetic DB -> skill_diff falls back to 0.0 (no NaN)
    assert (df["skill_diff"] == 0.0).all()


def test_first_match_is_neutral(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t")])
    row = build_training_data(conn).iloc[0]
    assert row["elo_diff"] == 0.0          # both start at 1500
    assert row["map_elo_diff"] == 0.0      # no prior map history -> zero offsets
    assert row["recent_form_team1"] == 0.5
    assert row["recent_form_team2"] == 0.5
    assert row["h2h_team1_win_rate"] == 0.5


def test_target_and_side_encoding(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t"), ("Haven", 20, "ct")])
    df = build_training_data(conn)
    bind = df[df["map_name"] == "Bind"].iloc[0]
    haven = df[df["map_name"] == "Haven"].iloc[0]
    assert bind["team1_won"] == 1 and bind["team1_starts_atk_or_def"] == 1   # T = attack
    assert haven["team1_won"] == 0 and haven["team1_starts_atk_or_def"] == 0  # CT = defense


def test_elo_updates_between_matches(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t"), ("Haven", 10, "ct")])  # 10 sweeps
    _match(conn, 10, 20, "2024-02-01", [("Split", 10, "t")])
    df = build_training_data(conn)
    later = df[df["match_id"] == 2].iloc[0]
    assert later["elo_diff"] > 0  # team 10 gained rating from the earlier win


def test_map_offset_is_applied_pretmatch(tmp_path):
    conn = _conn(tmp_path)
    # team 10 wins Bind repeatedly, loses Haven repeatedly (overall_wr < 1),
    # so its pre-match Bind offset is positive by a later match.
    for d, opp in enumerate([20, 30, 40], start=1):
        _match(conn, 10, opp, f"2024-01-0{d}", [("Bind", 10, "t"), ("Haven", opp, "ct")])
    _match(conn, 10, 50, "2024-02-01", [("Bind", 10, "t")])  # fresh opponent
    df = build_training_data(conn)
    final = df[df["match_id"] == 4].iloc[0]
    # opponent 50 has no map history -> off2 = 0, so the gap is team 10's Bind offset.
    assert final["map_elo_diff"] - final["elo_diff"] > 0


def test_h2h_shrinks_then_moves(tmp_path):
    conn = _conn(tmp_path)
    for d in range(1, 4):
        _match(conn, 10, 20, f"2024-01-0{d}", [("Bind", 10, "t"), ("Haven", 10, "ct")])
    _match(conn, 10, 20, "2024-02-01", [("Split", 10, "t")])
    df = build_training_data(conn)
    final = df[df["match_id"] == 4].iloc[0]
    assert final["h2h_team1_win_rate"] > 0.5   # 10 keeps beating 20
    assert final["h2h_team1_win_rate"] < 1.0   # but EB-shrunk toward 0.5


def test_showmatch_excluded(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t")])
    _match(conn, 15315, 15316, "2024-01-02", [("Haven", 15315, "t")],
           series="Showmatch: Showmatch")
    df = build_training_data(conn)
    assert len(df) == 1
    assert set(df["match_id"]) == {1}


def test_side_fallback_when_no_rounds(tmp_path):
    conn = _conn(tmp_path)
    _match(conn, 10, 20, "2024-01-01", [("Bind", 10, "t", False)])  # no round-1 row
    df = build_training_data(conn)
    assert df.isna().sum().sum() == 0
    assert df.iloc[0]["team1_starts_atk_or_def"] == 0  # fallback
    assert df.attrs.get("side_fallbacks") == 1
