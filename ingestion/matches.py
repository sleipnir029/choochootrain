"""Matches ingestion: populate `matches` for events in the warehouse.

For each event, `/v2/events/matches` enumerates its matches (names + scores, but
NO numeric team IDs and NO format). For every *completed* match we then fetch
`/v2/match/details`, which carries `teams[].id` (numeric), scores, winner, and a
date. Format is inferred from the winning score (2→Bo3, 3→Bo5, 1→Bo1). Teams
referenced by a match are upserted first so the FK holds — without clobbering
the richer country/region that ingestion.teams may already have set.

`patch_id` is left NULL here; P2.T13 backfills it from the match date.
See docs/DEVIATIONS.md for why match/details is required.

Usage:
    python -m ingestion.matches --db data/prx.db            # all events in the DB
    python -m ingestion.matches --db data/prx.db --event-id 1921
"""

import argparse
import asyncio
import re
import sqlite3
from datetime import datetime, timezone

import structlog

from ingestion.vlr_client import VlrClient

logger = structlog.get_logger(__name__)

_FORMAT_BY_WINS = {1: "Bo1", 2: "Bo3", 3: "Bo5"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def infer_format(score1: int, score2: int) -> str:
    """Bo-format from the winner's map wins (2→Bo3, 3→Bo5, 1→Bo1)."""
    wins = max(score1, score2)
    fmt = _FORMAT_BY_WINS.get(wins)
    if fmt is None:
        raise ValueError(f"cannot infer format from score {score1}-{score2}")
    return fmt


def parse_match_date(date_str: str) -> str:
    """Extract the date from a match-detail date string -> ISO date.

    e.g. 'March 14, 2024 4:00 PM CET Patch 8.04' -> '2024-03-14'.
    Time-of-day/timezone are dropped (not needed for daily-grain modelling).
    """
    m = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", date_str or "")
    if not m:
        raise ValueError(f"no date in {date_str!r}")
    token = m.group(1)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {token!r}")


def parse_match(detail: dict, event_id: int, *, match_url: str | None = None,
                match_date: str | None = None) -> dict:
    """Build a `matches` row from a /v2/match/details segment.

    `match_date` (from the /v2/events/matches listing) is preferred for the date:
    it reliably carries the year (e.g. 'Sat, February 28, 2026'), whereas the
    match-detail date omits the year for current-year matches
    ('Thursday, January 15 11:00 PM CET Patch 12.0'). Falls back to the detail date.
    """
    teams = detail["teams"]
    t1, t2 = teams[0], teams[1]
    s1, s2 = int(t1["score"]), int(t2["score"])

    winner_id = None
    if t1.get("is_winner"):
        winner_id = int(t1["id"])
    elif t2.get("is_winner"):
        winner_id = int(t2["id"])

    return {
        "match_id": int(detail["match_id"]),
        "event_id": event_id,
        "series_name": (detail.get("event") or {}).get("series"),
        "team1_id": int(t1["id"]),
        "team2_id": int(t2["id"]),
        "team1_score": s1,
        "team2_score": s2,
        "winner_id": winner_id,
        "date_utc": parse_match_date(match_date or detail.get("date", "")),
        "format": infer_format(s1, s2),
        "patch_id": None,  # backfilled in P2.T13
        "match_url": match_url,
    }


def upsert_team_from_match(conn: sqlite3.Connection, team: dict) -> None:
    """Upsert a team seen in a match (id/name/tag/logo only).

    On conflict, country/region are intentionally NOT touched so values set by
    ingestion.teams (e.g. PRX country='sg') survive.
    """
    conn.execute(
        """
        INSERT INTO teams (team_id, name, tag, country, region, logo_url, last_updated)
        VALUES (:team_id, :name, :tag, NULL, NULL, :logo_url, :last_updated)
        ON CONFLICT(team_id) DO UPDATE SET
            name = excluded.name,
            tag = excluded.tag,
            logo_url = excluded.logo_url,
            last_updated = excluded.last_updated
        """,
        {
            "team_id": int(team["id"]),
            "name": team["name"],
            "tag": team.get("tag") or None,
            "logo_url": team.get("logo") or None,
            "last_updated": _utc_now_iso(),
        },
    )


def upsert_match(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO matches (match_id, event_id, series_name, team1_id, team2_id,
                             team1_score, team2_score, winner_id, date_utc, format,
                             patch_id, match_url)
        VALUES (:match_id, :event_id, :series_name, :team1_id, :team2_id,
                :team1_score, :team2_score, :winner_id, :date_utc, :format,
                :patch_id, :match_url)
        ON CONFLICT(match_id) DO UPDATE SET
            event_id = excluded.event_id,
            series_name = excluded.series_name,
            team1_id = excluded.team1_id,
            team2_id = excluded.team2_id,
            team1_score = excluded.team1_score,
            team2_score = excluded.team2_score,
            winner_id = excluded.winner_id,
            date_utc = excluded.date_utc,
            format = excluded.format,
            match_url = excluded.match_url
        """,
        row,
    )


async def ingest_event_matches(event_id: int, db_path: str, *, client: VlrClient) -> int:
    """Ingest all completed matches for a single event. Returns count upserted."""
    listing = await client.get_segments("/v2/events/matches", event_id=str(event_id))
    conn = sqlite3.connect(db_path)
    upserted = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for entry in listing:
            if entry.get("status") != "Completed":
                continue
            mid = entry.get("match_id")
            try:
                detail = await client.get_segments("/v2/match/details", match_id=str(mid))
                seg = detail[0]
                row = parse_match(seg, event_id, match_url=entry.get("url"), match_date=entry.get("date"))
                for team in seg["teams"]:
                    upsert_team_from_match(conn, team)
                upsert_match(conn, row)
                upserted += 1
            except Exception as e:  # noqa: BLE001 - skip a bad match, keep going
                logger.warning("match_skipped", match_id=mid, event_id=event_id, error=repr(e))
        conn.commit()
    finally:
        conn.close()
    logger.info("event_matches_ingested", event_id=event_id, matches=upserted)
    return upserted


def _event_ids_in_db(db_path: str) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT event_id FROM events ORDER BY start_date")]
    finally:
        conn.close()


async def ingest_matches(db_path: str, *, client: VlrClient | None = None, event_ids=None) -> int:
    """Ingest matches for the given events (default: every event in the DB)."""
    ids = event_ids if event_ids is not None else _event_ids_in_db(db_path)
    if client is None:
        async with VlrClient() as owned:
            return await _ingest_all(ids, db_path, owned)
    return await _ingest_all(ids, db_path, client)


async def _ingest_all(ids, db_path: str, client: VlrClient) -> int:
    total = 0
    for eid in ids:
        total += await ingest_event_matches(int(eid), db_path, client=client)
    logger.info("matches_ingested", events=len(list(ids)), matches=total)
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest matches for warehouse events.")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    parser.add_argument("--event-id", type=int, default=None, help="Only this event (default: all in DB)")
    args = parser.parse_args(argv)
    ids = [args.event_id] if args.event_id is not None else None
    n = asyncio.run(ingest_matches(args.db, event_ids=ids))
    print(f"Upserted {n} match(es) into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
