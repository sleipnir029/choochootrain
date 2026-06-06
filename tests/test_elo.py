"""Tests for models.elo — pure Elo update math (P3.T1). No DB, no network."""

import pytest

from models.elo import DEFAULT_K, expected_score, update_elo


def test_expected_score_equal_ratings():
    assert expected_score(1500, 1500) == 0.5


def test_expected_score_higher_rated_favored():
    assert expected_score(1600, 1400) > 0.5
    assert expected_score(1400, 1600) < 0.5


def test_win_from_equal_ratings():
    # actual_a = 1.0, expected = 0.5 -> delta = 24 * 0.5 = 12
    new_a, new_b = update_elo(1500, 1500, 2, 0)
    assert new_a == 1512.0
    assert new_b == 1488.0


def test_loss_from_equal_ratings():
    new_a, new_b = update_elo(1500, 1500, 0, 2)
    assert new_a == 1488.0
    assert new_b == 1512.0


def test_draw_no_change():
    # actual_a == expected -> no movement
    new_a, new_b = update_elo(1500, 1500, 1, 1)
    assert new_a == 1500.0
    assert new_b == 1500.0


def test_margin_of_victory_matters():
    # From equal ratings, a 2-0 sweep moves more than a 2-1 win.
    sweep_a, _ = update_elo(1500, 1500, 2, 0)
    close_a, _ = update_elo(1500, 1500, 2, 1)
    assert sweep_a > close_a > 1500.0


def test_zero_sum_invariant():
    for ra, rb, sa, sb in [(1500, 1500, 2, 0), (1620, 1480, 2, 1), (1400, 1700, 0, 2)]:
        new_a, new_b = update_elo(ra, rb, sa, sb)
        assert new_a + new_b == pytest.approx(ra + rb)


def test_k_factor_default_and_override():
    assert DEFAULT_K == 24
    # Larger K -> larger movement for the same result.
    big_a, _ = update_elo(1500, 1500, 2, 0, k=48)
    small_a, _ = update_elo(1500, 1500, 2, 0, k=12)
    assert (big_a - 1500) > (small_a - 1500) > 0


def test_zero_zero_raises():
    with pytest.raises(ValueError):
        update_elo(1500, 1500, 0, 0)
