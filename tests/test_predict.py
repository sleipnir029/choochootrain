"""Tests for models.predict — log-odds pooling (pure) + a guarded integration test.

The pure combination tests run everywhere (models.predict imports bambi/arviz
lazily). The integration test needs the warehouse + trained posterior, so it is
skipped when either is absent (e.g. in CI).
"""

from pathlib import Path

import pytest

import models.predict as P

_DB = "data/prx.db"
_NC = "models/saved/bayes_logistic.nc"


# --- pure combination logic -------------------------------------------------

def test_logit_expit_roundtrip():
    for p in [0.05, 0.3, 0.5, 0.7, 0.95]:
        assert abs(P._expit(P._logit(p)) - p) < 1e-9


def test_neutral_state_returns_prior():
    for p in [0.2, 0.5, 0.8]:
        assert abs(P.combine_prior_and_state(p, 0.5) - p) < 1e-9


def test_neutral_prior_returns_state():
    for s in [0.2, 0.5, 0.8]:
        assert abs(P.combine_prior_and_state(0.5, s) - s) < 1e-9


def test_combine_directions_and_monotonic():
    assert P.combine_prior_and_state(0.6, 0.9) > 0.6   # good state raises
    assert P.combine_prior_and_state(0.6, 0.1) < 0.6   # bad state lowers
    assert (P.combine_prior_and_state(0.6, 0.9)
            > P.combine_prior_and_state(0.6, 0.7))     # monotonic in state


def test_combine_is_symmetric():
    # Log-odds pooling is symmetric in prior and state.
    assert abs(P.combine_prior_and_state(0.3, 0.8)
               - P.combine_prior_and_state(0.8, 0.3)) < 1e-12


# --- integration (local only) ----------------------------------------------

integration = pytest.mark.skipif(
    not (Path(_DB).exists() and Path(_NC).exists()),
    reason="needs data/prx.db + models/saved/bayes_logistic.nc",
)


@integration
def test_prediction_on_real_map():
    pytest.importorskip("bambi")
    df, _, _, map_idx, _ = P._resources(_DB)
    row = df.iloc[0]
    mid, target = int(row["match_id"]), int(row["map_id"])
    mi = next(idx for (m, idx), mp in map_idx.items() if m == mid and mp == target)

    pre = P.predict_map_win_prob(mid, mi, db_path=_DB)
    assert 0.0 < pre < 1.0

    up = P.predict_map_win_prob(mid, mi, db_path=_DB, live_state={
        "half": "second", "team1_score": 11, "team2_score": 1, "team1_side": "t"})
    down = P.predict_map_win_prob(mid, mi, db_path=_DB, live_state={
        "half": "second", "team1_score": 1, "team2_score": 11, "team1_side": "t"})
    assert up > pre > down


@integration
def test_unknown_map_raises():
    pytest.importorskip("bambi")
    P._resources(_DB)  # warm cache
    with pytest.raises(ValueError):
        P.predict_map_win_prob(-1, 0, db_path=_DB)


@integration
def test_live_win_prob_unintested_falls_back_to_upcoming():
    pytest.importorskip("bambi")
    ls = {"half": "first", "team1_score": 3, "team2_score": 8, "team1_side": "ct"}
    # Fake (un-ingested) match id; with team_ids it predicts via the upcoming builder.
    p = P.predict_live_win_prob(99999999, 0, ls, team_ids=(188, 624), db_path=_DB)
    assert 0.0 < p < 1.0
    # PRX (team2) up 8-3 -> team1's win prob should be low.
    assert p < 0.5
    # Without resolvable team_ids and no ingested features, it raises (poll_once swallows).
    with pytest.raises(ValueError):
        P.predict_live_win_prob(99999999, 0, ls, db_path=_DB)
