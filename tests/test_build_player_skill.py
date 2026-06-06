"""Tests for scripts.build_player_skill — chronological player-skill replay. No network."""

import sqlite3

from ingestion.schema import init_db
from models.player_skill import DEFAULT_MU
from scripts.build_player_skill import build, replay


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


def _map(conn, date, team_a, team_b, series=None):
    """team_a / team_b: list of (player_id, acs). Teams 10 and 20."""
    _MID[0] += 1
    mid = _MID[0]
    conn.execute(
        "INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id, "
        "team1_score, team2_score, winner_id, date_utc, format) "
        "VALUES (?,1,?,10,20,1,0,10,?,'Bo1')",
        (mid, series, date),
    )
    cur = conn.execute(
        "INSERT INTO maps (match_id, map_index, map_name, team1_score, team2_score, winner_id) "
        "VALUES (?,0,'Bind',13,5,10)", (mid,))
    map_id = cur.lastrowid
    for tid, players in [(10, team_a), (20, team_b)]:
        for pid, acs in players:
            conn.execute(
                "INSERT INTO map_player_stats "
                "(map_id, player_handle, player_id, team_id_at_match, agent, acs) "
                "VALUES (?,?,?,?,'Jett',?)",
                (map_id, f"p{pid}", pid, tid, acs),
            )
    return mid


def test_populates_one_row_per_player(tmp_path):
    conn = _conn(tmp_path)
    _map(conn, "2024-01-01", [(1, 250), (2, 240)], [(3, 150), (4, 140)])
    build(conn)
    rows = conn.execute("SELECT player_id, agent, map_name, mu, sigma FROM player_skill").fetchall()
    assert {r["player_id"] for r in rows} == {1, 2, 3, 4}
    assert all(r["agent"] is None and r["map_name"] is None for r in rows)


def test_consistent_outperformer_rises_underperformer_falls(tmp_path):
    conn = _conn(tmp_path)
    # Player 1 always tops the lobby; player 3 always trails. 12 maps.
    for d in range(1, 13):
        _map(conn, f"2024-02-{d:02d}", [(1, 280), (2, 200)], [(3, 120), (4, 200)])
    ratings, maps_played = build(conn)
    assert maps_played[1] == 12
    assert ratings[1].mu > DEFAULT_MU      # consistent over-performer
    assert ratings[3].mu < DEFAULT_MU      # consistent under-performer
    assert ratings[1].mu > ratings[3].mu


def test_as_of_date_is_players_last_map(tmp_path):
    conn = _conn(tmp_path)
    _map(conn, "2024-01-01", [(1, 250)], [(3, 150)])
    _map(conn, "2024-03-15", [(1, 250)], [(5, 150)])  # player 1 plays again later
    build(conn)
    d1 = conn.execute("SELECT as_of_date FROM player_skill WHERE player_id=1").fetchone()[0]
    d3 = conn.execute("SELECT as_of_date FROM player_skill WHERE player_id=3").fetchone()[0]
    assert d1 == "2024-03-15"   # player 1's latest map
    assert d3 == "2024-01-01"   # player 3 only played the first


def test_showmatch_excluded(tmp_path):
    conn = _conn(tmp_path)
    _map(conn, "2024-01-01", [(1, 250)], [(3, 150)])
    _map(conn, "2024-01-02", [(9, 250)], [(8, 150)], series="Showmatch: Showmatch")
    ratings, _last, _maps = replay(conn)
    assert set(ratings) == {1, 3}   # showmatch players 9/8 not rated


def test_idempotent_rebuild(tmp_path):
    conn = _conn(tmp_path)
    for d in range(1, 6):
        _map(conn, f"2024-02-{d:02d}", [(1, 250), (2, 240)], [(3, 150), (4, 160)])
    r1, _ = build(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM player_skill").fetchone()[0]
    r2, _ = build(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM player_skill").fetchone()[0]
    assert n1 == n2 == 4
    assert {p: round(r1[p].mu, 6) for p in r1} == {p: round(r2[p].mu, 6) for p in r2}
