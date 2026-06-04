"""Bulk-ingest a full year of tier-1 events through the whole pipeline.

Orchestrates, over one shared VlrClient (connection pool + rate-limit handling):
  events (optional) -> per event: matches -> match_details for each match
  -> resolve players (handles -> player_id) -> roster_history.

Progress, per-event counts, retries, and skips are logged via structlog at INFO.
Run with stdout/stderr redirected to capture the log, e.g.:

    python -m scripts.bulk_ingest --year 2024 --db data/prx.db > logs/bulk_ingest_2024.log 2>&1

Flags: --only-event <id> (one event), --skip-events (don't re-ingest the
event registry first), --skip-matches (resume: skip events/matches/details and
run only the players + roster stages — the match data is already in the DB).
All fetches are cached on disk (see ingestion.vlr_client), so a resumed run
re-uses anything already downloaded instead of re-fetching it.
"""

import argparse
import asyncio
import logging
import sqlite3
import sys

import structlog

from ingestion.events import ingest_events
from ingestion.match_details import ingest_match_details
from ingestion.matches import ingest_event_matches
from ingestion.players import ingest_players
from ingestion.roster_history import ingest_roster_history
from ingestion.vlr_client import VlrClient

logger = structlog.get_logger("bulk_ingest")


def _events_for_year(db_path: str, year: int, only_event: int | None):
    conn = sqlite3.connect(db_path)
    try:
        if only_event is not None:
            rows = conn.execute(
                "SELECT event_id, name FROM events WHERE event_id = ?", (only_event,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT event_id, name FROM events WHERE start_date LIKE ? ORDER BY start_date",
                (f"{year}-%",),
            ).fetchall()
    finally:
        conn.close()
    return rows


def _match_ids_for_event(db_path: str, event_id: int) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute(
            "SELECT match_id FROM matches WHERE event_id = ?", (event_id,)
        )]
    finally:
        conn.close()


async def run(year: int, db_path: str, *, only_event=None, skip_events=False, skip_matches=False) -> dict:
    totals = {"events": 0, "matches": 0, "maps": 0, "rounds": 0, "player_stats": 0,
              "economy": 0, "detail_failures": 0}
    async with VlrClient() as client:
        if not skip_events:
            logger.info("events_ingest_start")
            n = await ingest_events(db_path, client=client)
            logger.info("events_ingest_done", upserted=n)

        events = _events_for_year(db_path, year, only_event)
        logger.info("bulk_start", year=year, events=len(events), skip_matches=skip_matches)

        for event_id, name in [] if skip_matches else events:
            logger.info("event_start", event_id=event_id, name=name)
            n_matches = await ingest_event_matches(event_id, db_path, client=client)
            ev = {"maps": 0, "rounds": 0, "player_stats": 0, "economy": 0}
            for mid in _match_ids_for_event(db_path, event_id):
                try:
                    c = await ingest_match_details(mid, db_path, client=client)
                    for k in ev:
                        ev[k] += c.get(k, 0)
                except Exception as e:  # noqa: BLE001
                    totals["detail_failures"] += 1
                    logger.warning("detail_failed", match_id=mid, error=repr(e))
            totals["events"] += 1
            totals["matches"] += n_matches
            for k, v in ev.items():
                totals[k] += v
            logger.info("event_done", event_id=event_id, matches=n_matches, **ev)

        logger.info("players_resolve_start")
        ps = await ingest_players(db_path, client=client)
        logger.info("players_resolve_done", resolved=ps["resolved"], unresolved=len(ps["unresolved"]))

        logger.info("roster_history_start")
        rr = await ingest_roster_history(db_path, client=client)
        logger.info("roster_history_done", rows=rr)

    summary = {**totals, "players_resolved": ps["resolved"],
               "players_unresolved": len(ps["unresolved"]), "roster_rows": rr}
    logger.info("bulk_done", **summary)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bulk-ingest a year of tier-1 events.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--db", default="data/prx.db")
    parser.add_argument("--only-event", type=int, default=None)
    parser.add_argument("--skip-events", action="store_true")
    parser.add_argument("--skip-matches", action="store_true",
                        help="Resume: skip the events/matches/details phases, run only players + roster.")
    args = parser.parse_args(argv)

    # INFO-level structlog (suppresses per-request DEBUG noise from vlr_client).
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

    summary = asyncio.run(run(args.year, args.db, only_event=args.only_event,
                              skip_events=args.skip_events, skip_matches=args.skip_matches))
    print(f"bulk_ingest {args.year}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
