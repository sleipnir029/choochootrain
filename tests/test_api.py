"""API endpoint shape tests (P6.T2), via FastAPI TestClient against data/prx.db.

Reference-data routes (teams/players/events/matches/live no-live branch) run
wherever the warehouse exists. Prediction routes need bambi + the saved posterior,
so they are guarded with importorskip + skipif, mirroring tests/test_predict.py.
"""

import sqlite3
from pathlib import Path

import pytest

_DB = "data/prx.db"
_NC = "models/saved/bayes_logistic.nc"

needs_db = pytest.mark.skipif(not Path(_DB).exists(), reason="needs data/prx.db")
needs_model = pytest.mark.skipif(
    not (Path(_DB).exists() and Path(_NC).exists()),
    reason="needs data/prx.db + models/saved/bayes_logistic.nc",
)

pytestmark = needs_db


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _multi_stint_player_id():
    conn = sqlite3.connect(_DB)
    row = conn.execute(
        "SELECT player_id FROM map_player_stats WHERE player_id IS NOT NULL "
        "GROUP BY player_id ORDER BY COUNT(DISTINCT team_id_at_match) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0]


# --- reference data ---------------------------------------------------------

def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_team_profile_has_roster(client):
    r = client.get("/api/teams/624")
    assert r.status_code == 200
    body = r.json()
    assert body["team"]["name"] == "Paper Rex"
    assert isinstance(body["active_roster"], list)


def test_team_not_found(client):
    assert client.get("/api/teams/99999999").status_code == 404


def test_team_matches(client):
    r = client.get("/api/teams/624/matches?limit=5")
    assert r.status_code == 200
    assert len(r.json()["matches"]) <= 5


def test_player_stats_partitioned_by_stint(client):
    pid = _multi_stint_player_id()
    r = client.get(f"/api/players/{pid}/stats")
    assert r.status_code == 200
    stints = r.json()["stints"]
    # D2: no cross-team pooling -> one row per distinct team, all distinct.
    team_ids = [s["team_id"] for s in stints]
    assert len(team_ids) == len(set(team_ids))
    assert len(stints) >= 2


def test_player_not_found(client):
    assert client.get("/api/players/99999999/stats").status_code == 404


def test_events_status_filter(client):
    r = client.get("/api/events?status=completed")
    assert r.status_code == 200
    assert all(e["status"] == "completed" for e in r.json()["events"])
    assert client.get("/api/events?status=bogus").status_code == 400


def test_matches_upcoming_graceful(client):
    # vlrggapi isn't running under test -> graceful empty, not a 500.
    r = client.get("/api/matches/upcoming?team_id=624")
    assert r.status_code == 200
    assert isinstance(r.json()["matches"], list)


def test_live_returns_a_mode(client):
    r = client.get("/api/predict/live")
    assert r.status_code == 200
    assert r.json()["mode"] in {"live", "no_live"}


def test_pre_match_requires_args(client):
    # Light: 400 is returned before any model import.
    assert client.get("/api/predict/pre-match").status_code == 400


# --- prediction (local only) ------------------------------------------------

def _prx_match_id():
    conn = sqlite3.connect(_DB)
    row = conn.execute(
        "SELECT m.match_id FROM matches m JOIN maps mp ON mp.match_id = m.match_id "
        "WHERE (m.team1_id = 624 OR m.team2_id = 624) "
        "AND (m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%') "
        "GROUP BY m.match_id ORDER BY m.date_utc DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0]


@needs_model
def test_pre_match_ingested(client):
    pytest.importorskip("bambi")
    mid = _prx_match_id()
    body = client.get(f"/api/predict/pre-match?match_id={mid}").json()
    assert body["mode"] == "ingested"
    sp = body["series_win_prob"]
    assert sp["team1"] + sp["team2"] == pytest.approx(1.0, abs=1e-3)
    assert body["map_predictions"] and 0.0 < body["map_predictions"][0]["team1_win_prob"] < 1.0
    assert body["top_factors"]


@needs_model
def test_pre_match_upcoming(client):
    pytest.importorskip("bambi")
    body = client.get("/api/predict/pre-match?team1_id=624&team2_id=188").json()
    assert body["mode"] == "upcoming"
    assert 0.0 < body["team1_win_prob"] < 1.0
    lo, hi = body["team1_win_prob_hdi"]
    assert lo <= body["team1_win_prob"] <= hi
    assert body["map_predictions"] == []


@needs_model
def test_replay_trace(client):
    pytest.importorskip("bambi")
    mid = _prx_match_id()
    body = client.get(f"/api/predict/replay?match_id={mid}").json()
    assert body["maps"]
    rounds = body["maps"][0]["rounds"]
    assert rounds and rounds[0]["round"] == 1
    assert all(0.0 < r["pre_round_prob_team1"] < 1.0 for r in rounds)


# --- P6 revision: view-shaped insight endpoints -----------------------------

def _prx_player_id():
    conn = sqlite3.connect(_DB)
    row = conn.execute("SELECT player_id FROM players WHERE handle = 'f0rsakeN'").fetchone()
    conn.close()
    return row[0] if row else None


def test_player_view(client):
    # Light: player_view needs pandas/elo, not bambi.
    pid = _prx_player_id()
    body = client.get(f"/api/players/{pid}").json()
    assert body["handle"] == "f0rsakeN"
    assert body["skill"] and 0 <= body["skill"]["percentile"] <= 100
    assert body["stints"]
    # recent_form rows carry expected vs actual + a delta.
    if body["recent_form"]:
        assert "delta_acs" in body["recent_form"][0]


@needs_model
def test_home(client):
    pytest.importorskip("bambi")
    body = client.get("/api/home").json()
    assert body["prx"]["rank"]["rank"] >= 1
    assert body["prx"]["roster"]
    assert body["hero"] is not None
    # recent results carry the model-vs-result verdict.
    assert all("model_correct" in r for r in body["recent"])


@needs_model
def test_match_view_insight(client):
    pytest.importorskip("bambi")
    mid = _prx_match_id()
    body = client.get(f"/api/matches/{mid}").json()
    assert body["prematch_insight"]["headline"]
    assert isinstance(body["prematch_insight"]["points"], list)
    if body["completed"]:
        assert body["postmatch_insight"]["headline"]
        assert body["expected_stats"]
