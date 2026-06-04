"""Events ingestion: upsert the curated tier-1 VCT events into `events`.

For each entry in ingestion.tier1_events.TIER1_EVENTS, fetches
`/v2/event/{id}` (whose `data.segments` is a dict with an `event` block holding
name/dates/prize/location), combines it with the registry's tier/region, and
upserts keyed on event_id. Idempotent.

Why a registry instead of filtering /v2/events: see docs/DEVIATIONS.md.

Usage:
    python -m ingestion.events --db data/prx.db
"""

import argparse
import asyncio
import re
import sqlite3
from datetime import datetime

import structlog

from ingestion.tier1_events import TIER1_EVENTS
from ingestion.vlr_client import VlrClient

logger = structlog.get_logger(__name__)

_MONTH = "%b %d %Y"


def parse_prize(prize: str | None) -> int | None:
    """'$500,000 USD' -> 500000; '' / 'TBD' -> None."""
    digits = re.sub(r"[^\d]", "", prize or "")
    return int(digits) if digits else None


def parse_dates(dates: str) -> tuple[str, str]:
    """Parse a vlr event `dates` string into (start_iso, end_iso) dates.

    Handles the observed formats (commas optional, year may appear on one or
    both sides; cross-year supported):
        'Mar 14 - 24, 2024'             (compact: start has no year; end no month)
        'May 23 - Jun 9, 2024'          (compact, cross-month)
        'Feb 16, 2024 - Apr 6, 2024'    (full: both sides Mon D, YYYY)
        'Dec 28, 2024 - Jan 5, 2025'    (full, cross-year)

    Raises ValueError for unscheduled events (e.g. 'Jun 30 – TBD') so the caller
    skips them; they get picked up on a later re-ingest once vlr posts dates.
    The separator may be a hyphen, en-dash, or em-dash.
    """
    parts = re.split(r"\s[-–—]\s", dates, maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"unparseable dates: {dates!r}")
    left, right = parts[0].strip(), parts[1].strip()

    rm = re.search(r"(\d{4})$", right)
    if not rm:
        raise ValueError(f"no year in dates: {dates!r}")
    end_year = rm.group(1)
    right_core = right[: rm.start()].strip().rstrip(",").strip()  # 'Apr 6' | '24' | 'Jun 9'

    lm = re.search(r"(\d{4})$", left)
    if lm:  # left carries its own (possibly different) year
        start_year = lm.group(1)
        left_core = left[: lm.start()].strip().rstrip(",").strip()  # 'Feb 16'
    else:
        start_year = end_year
        left_core = left.rstrip(",").strip()  # 'Mar 14'

    start_month, start_day = left_core.split()[:2]
    rparts = right_core.split()
    if len(rparts) == 2:
        end_month, end_day = rparts
    else:  # end is just a day -> inherit the start month
        end_month, end_day = start_month, rparts[0]

    start = datetime.strptime(f"{start_month} {start_day} {start_year}", _MONTH).date().isoformat()
    end = datetime.strptime(f"{end_month} {end_day} {end_year}", _MONTH).date().isoformat()
    return start, end


def parse_event(event_block: dict, entry: dict) -> dict:
    """Combine a /v2/event detail `event` block with a registry entry -> row."""
    start, end = parse_dates(event_block["dates"])
    return {
        "event_id": entry["event_id"],
        "name": event_block.get("name") or entry["label"],
        "tier": entry["tier"],
        "region": entry["region"],
        "start_date": start,
        "end_date": end,
        "prize_usd": parse_prize(event_block.get("prize")),
    }


def upsert_event(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO events (event_id, name, tier, region, start_date, end_date, prize_usd)
        VALUES (:event_id, :name, :tier, :region, :start_date, :end_date, :prize_usd)
        ON CONFLICT(event_id) DO UPDATE SET
            name = excluded.name,
            tier = excluded.tier,
            region = excluded.region,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            prize_usd = excluded.prize_usd
        """,
        row,
    )


async def ingest_events(db_path: str, *, client: VlrClient | None = None, events=TIER1_EVENTS) -> int:
    """Fetch + upsert every tier-1 event. Returns the count upserted."""
    if client is None:
        async with VlrClient() as owned:
            return await _ingest(db_path, owned, events)
    return await _ingest(db_path, client, events)


async def _ingest(db_path: str, client: VlrClient, events) -> int:
    rows = []
    for entry in events:
        eid = entry["event_id"]
        try:
            payload = await client.get_json(f"/v2/event/{eid}")
            block = payload["data"]["segments"]["event"]
            rows.append(parse_event(block, entry))
        except Exception as e:  # noqa: BLE001 - skip a bad/missing event, keep going
            logger.warning("event_skipped", event_id=eid, label=entry.get("label"), error=repr(e))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in rows:
            upsert_event(conn, row)
        conn.commit()
    finally:
        conn.close()

    logger.info("events_ingested", requested=len(events), upserted=len(rows))
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest curated tier-1 VCT events.")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    args = parser.parse_args(argv)
    n = asyncio.run(ingest_events(args.db))
    print(f"Upserted {n}/{len(TIER1_EVENTS)} tier-1 events into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
