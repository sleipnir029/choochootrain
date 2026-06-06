"""Build the per-map training table for the Bayesian regression (P3.T4).

A single chronological pass over matches (oldest first), so every feature is
*point-in-time*: computed from state strictly BEFORE the match it describes, with
no leakage into the later holdout window (P3.T8). State is snapshotted before a
match, one row is emitted per map, and only then is the state advanced with that
match's results. Reuses ``models.elo.update_elo`` and the map-offset constants
from ``models.elo_map_offsets``; computes Elo inline rather than reading the
``elo_ratings`` snapshot table (avoids the daily-snapshot off-by-one and keeps
this builder self-contained).

Features per map row (target = ``team1_won``):
    elo_diff                 team1 - team2 base Elo, pre-match
    map_elo_diff             (elo + map offset) diff on this map, pre-match
    team1_starts_atk_or_def  1 if team1 starts round 1 on attack (T), else 0
    recent_form_team1        win fraction over team1's last 5 maps (0.5 if none)
    recent_form_team2        same for team2
    h2h_team1_win_rate       map-level H2H win rate, EB-shrunk toward 0.5
    patch_id, tier           from the match / event

Showmatches are excluded. Maps are point-in-time so the first appearance of any
team carries neutral priors (Elo 1500, form/H2H 0.5, zero map offset).

Usage:
    python -m models.training_data --db data/prx.db
"""

import argparse
import sqlite3
from collections import defaultdict, deque

import pandas as pd

from models.elo import DEFAULT_K, update_elo
from models.elo_map_offsets import ELO_PER_WINRATE, PRIOR_GAMES
from models.elo_replay import INITIAL_RATING
# Point-in-time team player-skill diff (the Phase-3 revisit feature). models->scripts
# import is intentional: build_player_skill imports only models.player_skill, no cycle.
from scripts.build_player_skill import replay_skill_diffs

FORM_WINDOW = 5      # rolling window for recent form, in maps
H2H_PRIOR = 4.0      # empirical-Bayes shrinkage strength for H2H, toward 0.5

# One row per map, oldest first, with the round-1 side and the event tier.
_MAPS_SQL = """
    SELECT m.match_id, m.date_utc, m.team1_id, m.team2_id,
           m.team1_score, m.team2_score, m.patch_id, e.tier,
           mp.map_id, mp.map_index, mp.map_name, mp.winner_id AS map_winner,
           (SELECT r.team1_side FROM rounds r
            WHERE r.map_id = mp.map_id AND r.round_number = 1) AS t1_side
    FROM maps mp
    JOIN matches m ON m.match_id = mp.match_id
    JOIN events e ON e.event_id = m.event_id
    WHERE m.series_name IS NULL OR m.series_name NOT LIKE 'Showmatch%'
    ORDER BY m.date_utc, m.match_id, mp.map_index
"""


def _map_offset(counts, totals, team, map_name):
    """Pre-match map Elo offset from running win counts (same formula as P3.T3)."""
    games, wins = counts[(team, map_name)]
    tg, tw = totals[team]
    if games == 0 or tg == 0:
        return 0.0
    raw_dev = wins / games - tw / tg
    return ELO_PER_WINRATE * raw_dev * games / (games + PRIOR_GAMES)


def _form(window):
    return sum(window) / len(window) if window else 0.5


def build_training_data(conn, *, k=DEFAULT_K, initial_rating=INITIAL_RATING):
    """Return a per-map training DataFrame with point-in-time features.

    One row per competitive map; no NaN; row count equals the competitive map
    count in the warehouse.
    """
    elo = defaultdict(lambda: initial_rating)
    map_counts = defaultdict(lambda: [0, 0])      # (team, map) -> [games, wins]
    totals = defaultdict(lambda: [0, 0])          # team -> [games, wins]
    form = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    h2h = defaultdict(lambda: [0, 0])             # (lo, hi) -> [wins_by_lo, total]

    rows = []
    side_fallbacks = 0

    cur_match = None
    pending = None  # (t1, t2, s1, s2, [(map_winner, map_name), ...])
    e1 = e2 = f1 = f2 = None

    def flush(p):
        """Advance state with a finished match's results."""
        t1, t2, s1, s2, maps = p
        elo[t1], elo[t2] = update_elo(elo[t1], elo[t2], s1, s2, k)
        lo, hi = (t1, t2) if t1 < t2 else (t2, t1)
        for winner, map_name in maps:
            for team in (t1, t2):
                map_counts[(team, map_name)][0] += 1
                totals[team][0] += 1
            map_counts[(winner, map_name)][1] += 1
            totals[winner][1] += 1
            form[t1].append(1 if winner == t1 else 0)
            form[t2].append(1 if winner == t2 else 0)
            h2h[(lo, hi)][1] += 1
            if winner == lo:
                h2h[(lo, hi)][0] += 1

    for r in conn.execute(_MAPS_SQL):
        if r["match_id"] != cur_match:
            if pending is not None:
                flush(pending)
            cur_match = r["match_id"]
            t1, t2 = r["team1_id"], r["team2_id"]
            e1, e2 = elo[t1], elo[t2]                 # pre-match Elo snapshot
            f1, f2 = _form(form[t1]), _form(form[t2])  # pre-match form snapshot
            pending = (t1, t2, r["team1_score"], r["team2_score"], [])

        t1, t2 = r["team1_id"], r["team2_id"]
        mn = r["map_name"]
        off1 = _map_offset(map_counts, totals, t1, mn)
        off2 = _map_offset(map_counts, totals, t2, mn)

        lo, hi = (t1, t2) if t1 < t2 else (t2, t1)
        wins_lo, total = h2h[(lo, hi)]
        t1_wins = wins_lo if t1 == lo else total - wins_lo
        h2h_rate = (t1_wins + H2H_PRIOR * 0.5) / (total + H2H_PRIOR)

        side = r["t1_side"]
        if side is None:
            side_fallbacks += 1
        starts_atk = 1 if side == "t" else 0  # T side = attack; None -> 0 (fallback)

        rows.append({
            "match_id": r["match_id"],
            "map_id": r["map_id"],
            "date_utc": r["date_utc"],
            "map_name": mn,
            "team1_id": t1,
            "team2_id": t2,
            "elo_diff": e1 - e2,
            "map_elo_diff": (e1 + off1) - (e2 + off2),
            "team1_starts_atk_or_def": starts_atk,
            "recent_form_team1": f1,
            "recent_form_team2": f2,
            "h2h_team1_win_rate": h2h_rate,
            "patch_id": r["patch_id"],
            "tier": r["tier"],
            "team1_won": 1 if r["map_winner"] == t1 else 0,
        })
        pending[4].append((r["map_winner"], mn))

    if pending is not None:
        flush(pending)

    df = pd.DataFrame(rows)
    # Team player-skill diff (mean TrueSkill mu, team1 - team2, pre-map). Maps without
    # two identifiable lineups (~3) get 0.0 (neutral) so the no-NaN invariant holds.
    skill = replay_skill_diffs(conn)
    df["skill_diff"] = df["map_id"].map(skill).fillna(0.0)
    if side_fallbacks:
        df.attrs["side_fallbacks"] = side_fallbacks
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    df = build_training_data(conn)
    conn.close()

    print(f"shape: {df.shape}")
    print(f"NaN cells: {int(df.isna().sum().sum())}")
    print(f"team1_won balance: {df['team1_won'].mean():.3f}")
    print(f"side fallbacks (no round-1 data): {df.attrs.get('side_fallbacks', 0)}")
    feats = ["elo_diff", "map_elo_diff", "team1_starts_atk_or_def",
             "recent_form_team1", "recent_form_team2", "h2h_team1_win_rate"]
    print(df[feats].describe().round(3).to_string())


if __name__ == "__main__":
    main()
