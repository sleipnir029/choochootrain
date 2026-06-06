"""Build the elo_ratings table by replaying all matches chronologically.

Rebuilds elo_ratings from scratch (idempotent) and prints a summary plus the
top-N teams by final Elo for a plausibility check.

Usage:
    python -m scripts.build_elo --db data/prx.db [--k 24] [--initial 1500] [--top 15]
"""

import argparse
import sqlite3

from models.elo import DEFAULT_K
from models.elo_replay import INITIAL_RATING, replay_elo


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    ap.add_argument("--k", type=float, default=DEFAULT_K)
    ap.add_argument("--initial", type=float, default=INITIAL_RATING)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    ratings, n = replay_elo(conn, k=args.k, initial_rating=args.initial)

    print(f"Replayed {n} matches; {len(ratings)} teams rated "
          f"(K={args.k}, init={args.initial}).")
    names = {r["team_id"]: r["name"] for r in conn.execute("SELECT team_id, name FROM teams")}
    top = sorted(ratings.items(), key=lambda kv: kv[1], reverse=True)[: args.top]
    print(f"-- Top {args.top} by final Elo --")
    for rank, (tid, rating) in enumerate(top, 1):
        print(f"  {rank:2}. {names.get(tid, f'team {tid}'):24} {rating:7.1f}")
    conn.close()


if __name__ == "__main__":
    main()
