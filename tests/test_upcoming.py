"""Tests for models.upcoming — the as-of-now upcoming-match feature builder (P6.T2).

Feature-building is pure pandas+sqlite (runs wherever data/prx.db exists); the
predict smoke needs bambi + the saved posterior, so it is guarded.
"""

import sqlite3
from pathlib import Path

import pytest

from models import upcoming

_DB = "data/prx.db"
_NC = "models/saved/bayes_logistic.nc"
_FORMULA_COLS = {
    "elo_diff", "map_elo_diff", "skill_diff", "team1_starts_atk_or_def",
    "recent_form_team1", "recent_form_team2", "h2h_team1_win_rate", "tier", "patch_id",
}

needs_db = pytest.mark.skipif(not Path(_DB).exists(), reason="needs data/prx.db")
needs_model = pytest.mark.skipif(
    not (Path(_DB).exists() and Path(_NC).exists()),
    reason="needs data/prx.db + models/saved/bayes_logistic.nc",
)


@pytest.fixture
def conn():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@needs_db
def test_single_row_all_columns_no_nan(conn):
    df = upcoming.build_upcoming_features(conn, 624, 188)
    assert len(df) == 1
    assert _FORMULA_COLS.issubset(df.columns)
    assert int(df.isna().sum().sum()) == 0


@needs_db
def test_elo_diff_sign_matches_ratings(conn):
    e1 = upcoming._latest_elo(conn, 624)
    e2 = upcoming._latest_elo(conn, 188)
    df = upcoming.build_upcoming_features(conn, 624, 188)
    # elo_diff is team1 - team2, and map_elo_diff mirrors it pre-veto.
    assert df["elo_diff"].iloc[0] == pytest.approx(e1 - e2)
    assert df["map_elo_diff"].iloc[0] == pytest.approx(e1 - e2)


@needs_db
def test_features_are_antisymmetric_in_team_order(conn):
    a = upcoming.build_upcoming_features(conn, 624, 188).iloc[0]
    b = upcoming.build_upcoming_features(conn, 188, 624).iloc[0]
    assert a["elo_diff"] == pytest.approx(-b["elo_diff"])
    assert a["skill_diff"] == pytest.approx(-b["skill_diff"])
    # H2H rate for team1 flips around 0.5 when the teams swap roles.
    assert a["h2h_team1_win_rate"] == pytest.approx(1 - b["h2h_team1_win_rate"])


@needs_db
def test_tier_defaults_and_override(conn):
    df = upcoming.build_upcoming_features(conn, 624, 188, tier="Masters")
    assert df["tier"].iloc[0] == "Masters"
    df2 = upcoming.build_upcoming_features(conn, 624, 188)
    assert df2["tier"].iloc[0] == upcoming.DEFAULT_TIER


@needs_model
def test_predict_upcoming_smoke():
    pytest.importorskip("bambi")
    out = upcoming.predict_upcoming_win_prob(624, 188, db_path=_DB)
    assert 0.0 < out["team1_win_prob"] < 1.0
    lo, hi = out["hdi"]
    assert lo <= out["team1_win_prob"] <= hi
    assert out["top_factors"] and "favors" in out["top_factors"][0]
