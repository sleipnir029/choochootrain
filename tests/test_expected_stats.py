"""Tests for models.expected_stats — recent-form expected stats (P4.T3). No network."""

import sqlite3
from pathlib import Path

import pytest

import models.expected_stats as es
from ingestion.schema import init_db

# --- pure recent-form logic -------------------------------------------------

def test_recent_form_empty_is_none():
    assert es._recent_form([]) is None


def test_recent_form_uses_last_n():
    assert es._recent_form([100, 200, 300], n=2) == 250.0   # last 2


def test_recent_form_all_when_fewer_than_n():
    assert es._recent_form([100, 200], n=5) == 150.0


# --- point-in-time end-to-end on a synthetic DB (opponent term off) ----------

def _seed(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    c = sqlite3.connect(db)
    c.execute("INSERT INTO events (event_id,name,tier,region,start_date,end_date) "
              "VALUES (1,'E','Masters','global','2024-01-01','2024-12-31')")
    return db, c


def _map(c, mid, date, rows):
    """rows: list of (player_id, team_id, acs). One map per match."""
    c.execute("INSERT INTO matches (match_id,event_id,team1_id,team2_id,team1_score,"
              "team2_score,winner_id,date_utc,format) VALUES (?,1,10,20,1,0,10,?,'Bo1')",
              (mid, date))
    cur = c.execute("INSERT INTO maps (match_id,map_index,map_name,team1_score,"
                    "team2_score,winner_id) VALUES (?,0,'Bind',13,5,10)", (mid,))
    map_id = cur.lastrowid
    for pid, tid, acs in rows:
        c.execute("INSERT INTO map_player_stats (map_id,player_handle,player_id,"
                  "team_id_at_match,agent,acs,kills,deaths,assists) "
                  "VALUES (?,?,?,?,'Jett',?,?,?,?)",
                  (map_id, f"p{pid}", pid, tid, acs, 15, 12, 4))


def test_point_in_time_recent_form(tmp_path):
    es._CACHE.clear()
    db, c = _seed(tmp_path)
    # Player 1's prior maps -> mean ACS 150; the target match's own ACS (250) and a
    # later map (400) must NOT leak into the expectation.
    _map(c, 1, "2024-01-01", [(1, 10, 100), (3, 20, 150)])
    _map(c, 2, "2024-02-01", [(1, 10, 200), (3, 20, 150)])
    _map(c, 3, "2024-03-01", [(1, 10, 250), (3, 20, 150)])   # target match
    _map(c, 4, "2024-04-01", [(1, 10, 400), (3, 20, 150)])   # future
    c.commit()

    df = es.predict_expected_stats(3, db_path=db, opponent_coef=0.0)
    row = df[df["player_id"] == 1].iloc[0]
    assert row["expected_acs"] == pytest.approx(150.0)   # mean of prior 100, 200
    assert row["actual_acs"] == pytest.approx(250.0)     # this match's actual
    assert row["n_history"] == 2


def test_unknown_match_raises(tmp_path):
    es._CACHE.clear()
    db, c = _seed(tmp_path)
    _map(c, 1, "2024-01-01", [(1, 10, 100), (3, 20, 150)])
    c.commit()
    with pytest.raises(ValueError):
        es.predict_expected_stats(999, db_path=db)


# --- integration on the real warehouse (skipped if absent) ------------------

@pytest.mark.skipif(not Path("data/prx.db").exists(), reason="needs data/prx.db")
def test_real_match_sane():
    es._CACHE.clear()
    df = es.predict_expected_stats(666493, db_path="data/prx.db")
    assert len(df) >= 10
    assert ((df["expected_acs"] > 0) & (df["expected_acs"] < 400)).all()
    if "actual_acs" in df.columns:
        mae = (df["expected_acs"] - df["actual_acs"]).abs().mean()
        assert mae < 45   # loose guardrail; ~25 in practice for this match
