"""TrueSkill player-rating wrapper — pure update logic, no DB I/O (P4.T1).

Wraps the `trueskill` library so the Phase 4 replay (P4.T2) can rate each player's
per-map performance. SPEC §6.2 Layer 5: a TrueSkill-style rating per
(player_id, agent, map) capturing whether a player over- or under-performs
expectation.

A map is modelled as a 1v1 TrueSkill match between the player and a notional
opponent (``opponent_skill`` — e.g. the opposing side's aggregate rating, supplied
by the replay). The outcome is taken from the **sign** of ``performance_score``
relative to ``baseline`` (a player's performance vs expectation):

    performance_score > baseline  -> player won  (out-performed)
    performance_score < baseline  -> player lost (under-performed)
    performance_score == baseline -> draw

Binary win/loss/draw is the standard, minimal TrueSkill usage; margin-aware
("how much" they over-performed) is a deferred refinement — see DEVIATIONS
2026-06-06. The replay decides how ``performance_score`` is computed (P4.T2,
"normalized ACS vs opponent average").
"""

import trueskill

DEFAULT_MU = 25.0
DEFAULT_SIGMA = 25.0 / 3.0  # trueskill's default; ~99% CI is mu +/- 3*sigma

# Library-default environment (mu=25, sigma=25/3, draw_probability=0.10). Exact
# ties are rare for a continuous performance score but handled via drawn=True.
_ENV = trueskill.TrueSkill(mu=DEFAULT_MU, sigma=DEFAULT_SIGMA)


def new_rating(mu=DEFAULT_MU, sigma=DEFAULT_SIGMA):
    """A fresh rating for an unseen player (or (player, agent, map))."""
    return _ENV.create_rating(mu, sigma)


def update_skill(player_id, agent, map_name, performance_score, opponent_skill,
                 *, current=None, baseline=0.0):
    """Return the player's updated TrueSkill ``Rating`` after one map.

    ``player_id``/``agent``/``map_name`` identify which rating is being updated
    (the replay keys its store by them); they do not enter the math. ``current``
    is the player's rating going in (a fresh ``new_rating()`` if omitted, i.e. an
    unseen player). ``opponent_skill`` is the opposing rating for this map.
    """
    cur = current if current is not None else new_rating()
    if performance_score > baseline:
        new_cur, _ = trueskill.rate_1vs1(cur, opponent_skill, env=_ENV)
    elif performance_score < baseline:
        _, new_cur = trueskill.rate_1vs1(opponent_skill, cur, env=_ENV)
    else:
        new_cur, _ = trueskill.rate_1vs1(cur, opponent_skill, drawn=True, env=_ENV)
    return new_cur
