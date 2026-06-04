"""Teams ingestion: fetch /v2/team for given team IDs and upsert into `teams`.

Idempotent — re-running with the same IDs updates rows in place (keyed on
team_id), so row counts don't grow. The vlrggapi team profile does not expose a
region, so `teams.region` is left NULL here and backfilled later from
region-scoped endpoints (see docs/DEVIATIONS.md).

Usage:
    python -m ingestion.teams 624 1001 --db data/prx.db
"""

import argparse
import asyncio
import sqlite3
from datetime import datetime, timezone

import structlog

from ingestion.vlr_client import VlrClient

logger = structlog.get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_team(segment: dict) -> dict:
    """Map a /v2/team profile segment to a `teams` table row.

    region is absent from the profile endpoint, so it is set to None.
    """
    return {
        "team_id": int(segment["id"]),
        "name": segment["name"],
        "tag": segment.get("tag") or None,
        "country": segment.get("country") or None,
        "region": segment.get("region") or None,  # not exposed by /v2/team
        "logo_url": segment.get("logo") or None,
        "last_updated": _utc_now_iso(),
    }


def upsert_team(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or update a single team row (keyed on team_id)."""
    conn.execute(
        """
        INSERT INTO teams (team_id, name, tag, country, region, logo_url, last_updated)
        VALUES (:team_id, :name, :tag, :country, :region, :logo_url, :last_updated)
        ON CONFLICT(team_id) DO UPDATE SET
            name = excluded.name,
            tag = excluded.tag,
            country = excluded.country,
            region = excluded.region,
            logo_url = excluded.logo_url,
            last_updated = excluded.last_updated
        """,
        row,
    )


async def ingest_teams(team_ids, db_path: str, *, client: VlrClient | None = None) -> int:
    """Fetch each team in `team_ids` and upsert into the DB at `db_path`.

    Returns the number of teams successfully upserted. If `client` is None, a
    VlrClient is created/closed internally; otherwise the caller's client is
    reused (and left open).
    """
    if client is None:
        async with VlrClient() as owned:
            return await _ingest(team_ids, db_path, owned)
    return await _ingest(team_ids, db_path, client)


async def _ingest(team_ids, db_path: str, client: VlrClient) -> int:
    rows = []
    for tid in team_ids:
        segments = await client.get_segments("/v2/team", id=str(tid))
        if not segments:
            logger.warning("team_not_found", team_id=tid)
            continue
        rows.append(parse_team(segments[0]))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in rows:
            upsert_team(conn, row)
        conn.commit()
    finally:
        conn.close()

    logger.info("teams_ingested", requested=len(list(team_ids)), upserted=len(rows))
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest vlr.gg teams into the warehouse.")
    parser.add_argument("team_ids", nargs="+", type=int, help="vlr.gg team IDs")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    args = parser.parse_args(argv)
    n = asyncio.run(ingest_teams(args.team_ids, args.db))
    print(f"Upserted {n} team(s) into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
