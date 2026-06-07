"""Pure unit tests for models.backtest helpers (no model/bambi needed)."""

from models import backtest


def test_confidence_tier_by_elo_gap():
    # Big Elo gap on a regional match -> sharp; moderate -> lean; tiny -> coinflip.
    assert backtest.confidence_tier(200, "RegionalLeague") == "sharp"
    assert backtest.confidence_tier(-200, "RegionalLeague") == "sharp"   # sign-agnostic
    assert backtest.confidence_tier(100, "RegionalLeague") == "lean"
    assert backtest.confidence_tier(30, "RegionalLeague") == "coinflip"


def test_confidence_tier_elite_downgrade():
    # Elite events (top, evenly-matched) are coinflips even at a moderate gap.
    assert backtest.confidence_tier(100, "Masters") == "lean"
    assert backtest.confidence_tier(60, "Masters") == "coinflip"
    assert backtest.confidence_tier(200, "Masters") == "sharp"          # huge gap still sharp


def test_logloss_and_metrics():
    # A confident correct call has low log-loss; a confident wrong call, high.
    assert backtest._logloss([0.9, 0.9], [1, 1]) < 0.2
    assert backtest._logloss([0.9, 0.9], [0, 0]) > 2.0
    m = backtest._metrics([0.8, 0.3], [1, 0], [100, -100])
    assert m["n"] == 2 and m["acc"] == 1.0 and m["elo_sign_acc"] == 1.0
