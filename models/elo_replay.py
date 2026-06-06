"""Replay all matches chronologically to compute team Elo (P3.T2).

Reads completed competitive matches in date order, applies
``models.elo.update_elo`` after each, and writes a daily snapshot per team to the
``elo_ratings`` table. Showmatches (ad-hoc all-star teams) are excluded, per the
Phase 2 guidance. Full rebuild: ``elo_ratings`` is cleared first, so the replay
is idempotent.

Every team starts at ``INITIAL_RATING``. SPEC §6.2 calls for region-based priors,
but ``teams.region`` is NULL for every team (see DEVIATIONS 2026-06-06), so a flat
prior is used as TASKS P3.T2 specifies ("Initial rating per region: 1500").

No CLI here — ``scripts/build_elo.py`` drives this and prints the summary.
"""

from models.elo import DEFAULT_K, update_elo

INITIAL_RATING = 1500.0

# Exclude showmatches; series_name may be NULL, so guard for that explicitly.
_MATCHES_SQL = """
    SELECT match_id, team1_id, team2_id, team1_score, team2_score, date_utc
    FROM matches
    WHERE series_name IS NULL OR series_name NOT LIKE 'Showmatch%'
    ORDER BY date_utc, match_id
"""

_UPSERT_SQL = (
    "INSERT INTO elo_ratings (team_id, as_of_date, rating) VALUES (?, ?, ?) "
    "ON CONFLICT(team_id, as_of_date) DO UPDATE SET rating = excluded.rating"
)


def replay_elo(conn, *, k=DEFAULT_K, initial_rating=INITIAL_RATING):
    """Replay matches and rebuild the elo_ratings table.

    Maintains current ratings in memory (new teams start at ``initial_rating``),
    applies each match's MOV update in chronological order, and upserts a daily
    snapshot per team (last match on a date wins for that date's row).

    Returns ``(final_ratings, n_matches)`` where ``final_ratings`` is
    ``{team_id: rating}``.
    """
    conn.execute("DELETE FROM elo_ratings")
    ratings = {}
    n = 0
    for m in conn.execute(_MATCHES_SQL):
        t1, t2 = m["team1_id"], m["team2_id"]
        r1 = ratings.get(t1, initial_rating)
        r2 = ratings.get(t2, initial_rating)
        new1, new2 = update_elo(r1, r2, m["team1_score"], m["team2_score"], k)
        ratings[t1], ratings[t2] = new1, new2
        date = m["date_utc"][:10]
        conn.execute(_UPSERT_SQL, (t1, date, new1))
        conn.execute(_UPSERT_SQL, (t2, date, new2))
        n += 1
    conn.commit()
    return ratings, n
