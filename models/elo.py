"""Team Elo update logic — pure functions, no DB I/O (P3.T1)."""

DEFAULT_K = 24


def expected_score(rating_a, rating_b):
    """Logistic expected score for A vs B (400-point scale)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(rating_a, rating_b, score_a, score_b, k=DEFAULT_K):
    """Return (new_rating_a, new_rating_b) after a match.

    Actual outcome is margin-of-victory: score_a / (score_a + score_b),
    so a 2-0 sweep moves Elo more than a 2-1. Update is zero-sum
    (delta_b = -delta_a). Raises ValueError if both scores are zero
    (no valid result).
    """
    total = score_a + score_b
    if total == 0:
        raise ValueError("score_a and score_b cannot both be zero")
    actual_a = score_a / total
    exp_a = expected_score(rating_a, rating_b)
    delta = k * (actual_a - exp_a)
    return rating_a + delta, rating_b - delta
