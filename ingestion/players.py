"""Player ingestion: resolve handles in map_player_stats -> player_id, backfill.

/v2/match/details has no player IDs, so map_player_stats was captured by handle
(P2.T6). This module takes each distinct unresolved handle, resolves it to a
vlr player_id via /v2/search, upserts the /v2/player profile into `players`, and
backfills `map_player_stats.player_id`.

Disambiguation: /v2/search can return several exact-name hits (alt/fan accounts).
- exactly one exact (case-insensitive) name match  -> use it
- several                                          -> pick the candidate whose
  /v2/player team history (current + past teams) matches a team the handle
  actually played for (from map_player_stats.team_id_at_match); if none/many
  match, leave unresolved (player_id stays NULL) and log it. Correctness > recall.

`current_team_id` is best-effort: /v2/player gives the current team's name but no
ID, so it's matched against the `teams` table (NULL if not found / ambiguous).

Usage:
    python -m ingestion.players --db data/prx.db
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


def _profile_team_strings(profile: dict) -> list[str]:
    """Lowercased team-name strings from a /v2/player profile (current + past).

    vlrggapi sometimes glues the date range onto a past-team name
    (e.g. 'Karmine CorpDecember 2023 – November 2024'), so these are returned raw
    and matched by substring rather than equality.
    """
    out = []
    ct = profile.get("current_team") or {}
    if ct.get("name"):
        out.append(ct["name"].strip().lower())
    for pt in profile.get("past_teams") or []:
        name = pt.get("name") if isinstance(pt, dict) else pt
        if name:
            out.append(str(name).strip().lower())
    return out


def _team_matches(known_team_names: set[str], profile: dict) -> bool:
    """True if any known team name is a substring of any profile team string."""
    strings = _profile_team_strings(profile)
    return any(known in s for known in known_team_names for s in strings)


def parse_player(profile: dict, team_name_to_id: dict[str, int]) -> dict:
    ct = profile.get("current_team") or {}
    ct_name = (ct.get("name") or "").strip().lower()
    return {
        "player_id": int(profile["id"]),
        "handle": profile["name"],
        "real_name": profile.get("real_name") or None,
        "country": profile.get("country") or None,
        "current_team_id": team_name_to_id.get(ct_name),
        "last_updated": _utc_now_iso(),
    }


def upsert_player(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO players (player_id, handle, real_name, country, current_team_id, last_updated)
        VALUES (:player_id, :handle, :real_name, :country, :current_team_id, :last_updated)
        ON CONFLICT(player_id) DO UPDATE SET
            handle = excluded.handle,
            real_name = excluded.real_name,
            country = excluded.country,
            current_team_id = excluded.current_team_id,
            last_updated = excluded.last_updated
        """,
        row,
    )


async def resolve_handle(client, handle: str, known_team_names: set[str]) -> tuple[int | None, dict | None]:
    """Resolve a handle -> (player_id, profile). Returns (None, None) if unresolved."""
    payload = await client.get_json("/v2/search", q=handle)
    players = payload["data"]["segments"]["results"]["players"]
    exact = [p for p in players if (p.get("name") or "").lower() == handle.lower()]
    if not exact:
        return None, None

    if len(exact) == 1:
        profile = (await client.get_segments("/v2/player", id=str(exact[0]["id"])))[0]
        return int(exact[0]["id"]), profile

    # Ambiguous: disambiguate by team history.
    matches = []
    for cand in exact:
        profile = (await client.get_segments("/v2/player", id=str(cand["id"])))[0]
        if _team_matches(known_team_names, profile):
            matches.append((int(cand["id"]), profile))
    if len(matches) == 1:
        return matches[0]
    logger.warning("handle_ambiguous", handle=handle, exact=len(exact), team_matches=len(matches))
    return None, None


def _pending_handles(conn: sqlite3.Connection) -> dict[str, set[int]]:
    """Distinct unresolved handles -> set of team_ids they played for."""
    out: dict[str, set[int]] = {}
    for handle, team_id in conn.execute(
        "SELECT DISTINCT player_handle, team_id_at_match FROM map_player_stats WHERE player_id IS NULL"
    ):
        out.setdefault(handle, set()).add(team_id)
    return out


def _team_maps(conn: sqlite3.Connection):
    """(team_id->name lower, name lower->team_id with unique names only)."""
    id_to_name, name_count, name_to_id = {}, {}, {}
    for tid, name in conn.execute("SELECT team_id, name FROM teams"):
        low = (name or "").strip().lower()
        id_to_name[tid] = low
        name_count[low] = name_count.get(low, 0) + 1
        name_to_id[low] = tid
    name_to_id = {n: i for n, i in name_to_id.items() if name_count[n] == 1}
    return id_to_name, name_to_id


async def ingest_players(db_path: str, *, client: VlrClient | None = None) -> dict:
    if client is None:
        async with VlrClient() as owned:
            return await _ingest(db_path, owned)
    return await _ingest(db_path, client)


async def _ingest(db_path: str, client) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        pending = _pending_handles(conn)
        id_to_name, name_to_id = _team_maps(conn)
    finally:
        conn.close()

    resolved, unresolved, backfilled = 0, [], 0
    for handle, team_ids in pending.items():
        known = {id_to_name[t] for t in team_ids if t in id_to_name}
        try:
            pid, profile = await resolve_handle(client, handle, known)
        except Exception as e:  # noqa: BLE001
            logger.warning("handle_resolve_error", handle=handle, error=repr(e))
            pid, profile = None, None
        if pid is None or profile is None:
            unresolved.append(handle)
            continue

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            upsert_player(conn, parse_player(profile, name_to_id))
            cur = conn.execute(
                "UPDATE map_player_stats SET player_id = ? WHERE player_handle = ?", (pid, handle)
            )
            backfilled += cur.rowcount
            conn.commit()
        finally:
            conn.close()
        resolved += 1

    summary = {"resolved": resolved, "unresolved": unresolved, "stat_rows_backfilled": backfilled}
    logger.info("players_ingested", **{**summary, "unresolved": len(unresolved)})
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Resolve player handles and backfill player_id.")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    args = parser.parse_args(argv)
    s = asyncio.run(ingest_players(args.db))
    print(f"Resolved {s['resolved']} player(s), backfilled {s['stat_rows_backfilled']} stat rows; "
          f"{len(s['unresolved'])} unresolved.")
    if s["unresolved"]:
        print("  unresolved handles:", ", ".join(s["unresolved"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
