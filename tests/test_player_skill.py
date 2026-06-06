"""Tests for models.player_skill — TrueSkill update logic (P4.T1). No DB, no network."""

from models.player_skill import DEFAULT_MU, DEFAULT_SIGMA, new_rating, update_skill


def test_new_rating_defaults():
    r = new_rating()
    assert r.mu == DEFAULT_MU
    assert abs(r.sigma - DEFAULT_SIGMA) < 1e-9


def test_outperform_raises_mu_and_lowers_sigma():
    cur = new_rating()
    opp = new_rating()
    after = update_skill(1, "Jett", "Bind", performance_score=1.0,
                         opponent_skill=opp, current=cur)
    assert after.mu > cur.mu          # winning raises skill estimate
    assert after.sigma < cur.sigma    # any game reduces uncertainty


def test_underperform_lowers_mu():
    cur = new_rating()
    opp = new_rating()
    after = update_skill(1, "Jett", "Bind", performance_score=-1.0,
                         opponent_skill=opp, current=cur)
    assert after.mu < cur.mu
    assert after.sigma < cur.sigma


def test_draw_keeps_mu_roughly_and_lowers_sigma():
    cur = new_rating()
    opp = new_rating()  # equal opponent
    after = update_skill(1, "Jett", "Bind", performance_score=0.0,
                         opponent_skill=opp, current=cur)
    assert abs(after.mu - cur.mu) < 1e-6   # draw vs equal -> no mean shift
    assert after.sigma < cur.sigma


def test_beating_stronger_opponent_gains_more():
    cur = new_rating()
    weak = new_rating(mu=15.0)
    strong = new_rating(mu=35.0)
    gain_vs_weak = update_skill(1, None, None, 1.0, weak, current=cur).mu - cur.mu
    gain_vs_strong = update_skill(1, None, None, 1.0, strong, current=cur).mu - cur.mu
    assert gain_vs_strong > gain_vs_weak > 0


def test_unseen_player_starts_from_default():
    # No `current` -> fresh rating; a win should push mu above the default.
    after = update_skill(99, None, None, 1.0, new_rating())
    assert after.mu > DEFAULT_MU
    assert after.sigma < DEFAULT_SIGMA


def test_sigma_monotonically_decreases_over_games():
    r = new_rating()
    opp = new_rating()
    sigmas = [r.sigma]
    for _ in range(5):
        r = update_skill(1, "Jett", "Bind", 1.0, opp, current=r)
        sigmas.append(r.sigma)
    assert all(b < a for a, b in zip(sigmas, sigmas[1:]))
