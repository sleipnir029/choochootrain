"""Tests for models.bayes_logistic — split + model construction (no MCMC). No network.

Guarded with importorskip: bambi/pymc are heavy and not installed in CI, so these
run locally only. Model *convergence* is verified by the live fit (logged to
logs/bayes_logistic_fit.txt), not in the unit suite.
"""

import pandas as pd
import pytest

pytest.importorskip("bambi")

from models.bayes_logistic import TRAIN_CUTOFF, build_model, split_train  # noqa: E402


def _df():
    return pd.DataFrame({
        "team1_won": [1, 0, 1, 0, 1, 0],
        "elo_diff": [50.0, -30.0, 10.0, -5.0, 80.0, -60.0],
        "map_elo_diff": [60.0, -20.0, 15.0, 0.0, 90.0, -50.0],
        "skill_diff": [1.5, -1.0, 0.4, -0.2, 2.0, -1.8],
        "team1_starts_atk_or_def": [1, 0, 1, 0, 1, 0],
        "recent_form_team1": [0.6, 0.4, 0.5, 0.5, 0.7, 0.3],
        "recent_form_team2": [0.4, 0.6, 0.5, 0.5, 0.3, 0.7],
        "h2h_team1_win_rate": [0.55, 0.45, 0.5, 0.5, 0.6, 0.4],
        "patch_id": ["8.04", "8.04", "8.05", "8.05", "9.0", "9.0"],
        "tier": ["Masters", "Masters", "RegionalLeague", "RegionalLeague", "Kickoff", "Kickoff"],
        "date_utc": ["2025-01-01", "2025-02-01", "2025-04-01",
                     "2025-07-01", "2024-12-01", "2026-01-01"],
    })


def test_split_train_respects_cutoff():
    df = _df()
    tr = split_train(df)
    assert (tr["date_utc"] <= TRAIN_CUTOFF).all()
    assert len(tr) == (df["date_utc"] <= TRAIN_CUTOFF).sum()


def test_build_model_constructs():
    import bambi as bmb
    # Construction parses the formula (scale()/C()/random-effect terms) without
    # sampling — no PyTensor compilation, so it's fast and toolchain-independent.
    model = build_model(_df())
    assert isinstance(model, bmb.Model)
    assert "team1_won" in str(model)
