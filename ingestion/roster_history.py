"""Roster history ingestion — built from player-profile team tenures.

/v2/team?q=transactions is broken in the pinned upstream (no dates/roles), so
roster_history is reconstructed from each player's /v2/player profile:
`current_team` (active tenure, left_date NULL) + `past_teams[].dates`. Only
tenures whose team resolves to a team in our `teams` table (the tier-1 teams we
track) are kept. Dates are month-granularity → joined = first of month, left =
last of month. `role` defaults to 'player' (profiles give no per-tenure role).

Idempotent: each player's rows are deleted and rebuilt.
See docs/DEVIATIONS.md (2026-06-04, P2.T8).

Usage:
    python -m ingestion.roster_history --db data/prx.db [--player-id 13744]
"""

import argparse
import asyncio
import calendar
import re
import sqlite3

import structlog

from ingestion.vlr_client import VlrClient

logger = structlog.get_logger(__name__)

# Anchor on real month names (full + abbrev) so a team name glued to a month
# (e.g. 'Karmine CorpDecember 2023') still splits/parses correctly.
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MONTH_ALT = "(?:" + "|".join(sorted((m for m in _MONTHS), key=len, reverse=True)) + ")"
_MONTH_RE = re.compile(rf"({_MONTH_ALT})\s+(\d{{4}})", re.IGNORECASE)
_RANGE_RE = re.compile(
    rf"({_MONTH_ALT}\s+\d{{4}})\s*[–—-]\s*({_MONTH_ALT}\s+\d{{4}})", re.IGNORECASE
)


def _month_start(text: str) -> str | None:
    """'March 2025' -> '2025-03-01'; falls back to 'YYYY' -> 'YYYY-01-01'."""
    m = _MONTH_RE.search(text or "")
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            return f"{int(m.group(2)):04d}-{mon:02d}-01"
    y = re.search(r"(\d{4})", text or "")
    return f"{int(y.group(1)):04d}-01-01" if y else None


def _month_end(text: str) -> str | None:
    """'December 2025' -> '2025-12-31'."""
    m = _MONTH_RE.search(text or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    year = int(m.group(2))
    return f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"


def _match_team(raw_name: str, name_to_id: dict[str, int]) -> int | None:
    """Resolve a (possibly date-glued) team string to a tracked team_id.

    Substring match (like the T7 resolver); prefers the longest matching name to
    avoid short-name collisions.
    """
    low = (raw_name or "").lower()
    best_len, best_id = 0, None
    for tname, tid in name_to_id.items():
        if tname in low and len(tname) > best_len:
            best_len, best_id = len(tname), tid
    return best_id


def extract_tenures(profile: dict, name_to_id: dict[str, int]) -> list[dict]:
    """Return roster_history rows (team_id/role/joined_date/left_date) for a player.

    Only tenures whose team maps to a tracked team are kept; undated tenures are
    skipped (joined_date is NOT NULL).
    """
    rows = []

    ct = profile.get("current_team") or {}
    if ct.get("name"):
        tid = _match_team(ct["name"], name_to_id)
        joined = _month_start(ct.get("joined", ""))
        if tid and joined:
            rows.append({"team_id": tid, "role": "player", "joined_date": joined, "left_date": None})

    for pt in profile.get("past_teams") or []:
        name = pt.get("name") if isinstance(pt, dict) else pt
        if not name:
            continue
        tid = _match_team(name, name_to_id)
        if not tid:
            continue
        source = (pt.get("dates") if isinstance(pt, dict) else "") or name
        rng = _RANGE_RE.search(source)
        if rng:
            joined, left = _month_start(rng.group(1)), _month_end(rng.group(2))
        else:
            joined, left = _month_start(source), None
        if not joined:
            continue
        rows.append({"team_id": tid, "role": "player", "joined_date": joined, "left_date": left})

    return rows


def _team_name_to_id(conn: sqlite3.Connection) -> dict[str, int]:
    counts, mapping = {}, {}
    for tid, name in conn.execute("SELECT team_id, name FROM teams"):
        low = (name or "").strip().lower()
        counts[low] = counts.get(low, 0) + 1
        mapping[low] = tid
    return {n: i for n, i in mapping.items() if counts[n] == 1}


def players_on_team_at(conn: sqlite3.Connection, team_id: int, date_iso: str) -> list[str]:
    """Handles of players on `team_id` on `date_iso` (joined <= date < or = left)."""
    rows = conn.execute(
        """
        SELECT DISTINCT p.handle
        FROM roster_history r JOIN players p ON p.player_id = r.player_id
        WHERE r.team_id = ? AND r.joined_date <= ?
          AND (r.left_date IS NULL OR r.left_date >= ?)
        ORDER BY p.handle
        """,
        (team_id, date_iso, date_iso),
    ).fetchall()
    return [r[0] for r in rows]


async def ingest_roster_history(db_path: str, *, client: VlrClient | None = None, player_ids=None) -> int:
    if client is None:
        async with VlrClient() as owned:
            return await _ingest(db_path, owned, player_ids)
    return await _ingest(db_path, client, player_ids)


async def _ingest(db_path: str, client, player_ids) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if player_ids is None:
            player_ids = [r[0] for r in conn.execute("SELECT player_id FROM players")]
        name_to_id = _team_name_to_id(conn)
    finally:
        conn.close()

    total_rows = 0
    for pid in player_ids:
        try:
            profile = (await client.get_segments("/v2/player", id=str(pid)))[0]
        except Exception as e:  # noqa: BLE001
            logger.warning("roster_player_skipped", player_id=pid, error=repr(e))
            continue
        tenures = extract_tenures(profile, name_to_id)

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM roster_history WHERE player_id = ?", (pid,))  # idempotent rebuild
            for t in tenures:
                conn.execute(
                    "INSERT INTO roster_history (player_id, team_id, role, joined_date, left_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, t["team_id"], t["role"], t["joined_date"], t["left_date"]),
                )
            conn.commit()
        finally:
            conn.close()
        total_rows += len(tenures)

    logger.info("roster_history_ingested", players=len(player_ids), rows=total_rows)
    return total_rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build roster_history from player profiles.")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    parser.add_argument("--player-id", type=int, default=None, help="Only this player (default: all in DB)")
    args = parser.parse_args(argv)
    ids = [args.player_id] if args.player_id is not None else None
    n = asyncio.run(ingest_roster_history(args.db, player_ids=ids))
    print(f"Wrote {n} roster_history row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
