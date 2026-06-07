"""Re-ingest /v2/match/details for every match to populate the tier-2 scouting
tables (map_player_duels, map_player_advanced, match_veto). Uses the disk cache, so
no new network calls for already-fetched matches. Idempotent (upserts).

Usage:
    python -m scripts.reingest_details --db data/prx.db
"""

import argparse
import asyncio
import sqlite3

import structlog

from ingestion.match_details import ingest_detail_into_db
from ingestion.vlr_client import VlrApiError, VlrClient

logger = structlog.get_logger()


def _backfill_veto_team_ids(conn) -> None:
    """The veto string uses team **tags**, but teams.tag is unset and the detail's
    tag is empty — so derive each team's tag as the modal veto tag across its matches,
    then resolve match_veto.team_id per match (only the match's two teams considered)."""
    conn.execute(
        """UPDATE teams SET tag = (
               SELECT mv.team_tag FROM match_veto mv JOIN matches m ON m.match_id = mv.match_id
               WHERE (m.team1_id = teams.team_id OR m.team2_id = teams.team_id)
                 AND mv.team_tag IS NOT NULL
               GROUP BY mv.team_tag ORDER BY COUNT(*) DESC LIMIT 1)
           WHERE EXISTS (SELECT 1 FROM match_veto mv JOIN matches m ON m.match_id = mv.match_id
               WHERE (m.team1_id = teams.team_id OR m.team2_id = teams.team_id)
                 AND mv.team_tag IS NOT NULL)""")
    conn.execute(
        """UPDATE match_veto SET team_id = (
               SELECT t.team_id FROM matches m JOIN teams t ON t.team_id IN (m.team1_id, m.team2_id)
               WHERE m.match_id = match_veto.match_id AND t.tag = match_veto.team_tag)
           WHERE action != 'decider'""")
    conn.commit()


async def run(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    match_ids = [r[0] for r in conn.execute("SELECT match_id FROM matches ORDER BY match_id")]
    ok = fail = duels = veto = 0
    # Fail-fast: cache hits return instantly; a cache miss must NOT block the loop on
    # the live container (retries/backoff) — fail fast and skip.
    async with VlrClient(max_retries=0, timeout=15.0) as client:
        for i, mid in enumerate(match_ids, 1):
            try:
                segs = await client.get_segments("/v2/match/details", match_id=str(mid))
                if not segs:
                    fail += 1
                    continue
                # Per-match savepoint: a bad match (e.g. a player with no agent, which
                # violates map_player_stats.agent NOT NULL — same matches that failed in
                # P2) rolls back cleanly and the run continues.
                conn.execute("SAVEPOINT m")
                try:
                    c = ingest_detail_into_db(conn, segs[0])
                    conn.execute("RELEASE m")
                except Exception:
                    conn.execute("ROLLBACK TO m")
                    conn.execute("RELEASE m")
                    raise
                ok += 1
                duels += c["duels"]
                veto += c["veto"]
            except Exception as e:  # noqa: BLE001 - skip a bad match, keep the run going
                fail += 1
                logger.warning("reingest_failed", match_id=mid, error=repr(e)[:120])
            if i % 100 == 0:
                conn.commit()
                logger.info("reingest_progress", done=i, total=len(match_ids), ok=ok, fail=fail)
    conn.commit()
    _backfill_veto_team_ids(conn)
    conn.close()
    summary = {"ok": ok, "fail": fail, "duels": duels, "veto": veto, "total": len(match_ids)}
    logger.info("reingest_done", **summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    args = ap.parse_args()
    print(asyncio.run(run(args.db)))


if __name__ == "__main__":
    main()
