"""Match-details ingestion: maps, rounds, map_player_stats, map_team_economy.

For a match_id, fetches `/v2/match/details` and populates the four downstream
tables. Player stats are keyed by **handle** (the detail has no player IDs);
P2.T7 resolves handles -> player_id later. `is_rounds_complete=1` only when the
count of valid rounds equals the map's total score.

The match row itself must already exist (ingestion.matches, P2.T5) — this module
reads team IDs from the detail's `teams` block and assumes those teams + the
match are present.

Usage:
    python -m ingestion.match_details --db data/prx.db --match-id 312765
"""

import argparse
import asyncio
import re
import sqlite3

import structlog

from ingestion.vlr_client import VlrClient

logger = structlog.get_logger(__name__)


# ---- small value parsers -------------------------------------------------
def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _float(v) -> float | None:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _pct(v) -> int | None:
    """'67%' -> 67; '' -> None."""
    return _int(str(v).replace("%", "")) if v not in (None, "") else None


def parse_duration(text: str) -> int | None:
    """'59:51' -> 3591; '1:02:03' -> 3723; '' -> None."""
    if not text:
        return None
    parts = text.split(":")
    if not all(p.isdigit() for p in parts):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs


def round_half(round_num: int) -> str:
    """Valorant: rounds 1-12 first half, 13-24 second, 25+ overtime."""
    if round_num <= 12:
        return "first"
    if round_num <= 24:
        return "second"
    return "ot"


def _won_total(cell: str) -> tuple[int, int] | None:
    """'3 (1)' -> (total=3, won=1); '0 (0)' -> (0,0); '' -> None."""
    if not cell:
        return None
    m = re.match(r"\s*(\d+)\s*\((\d+)\)", str(cell))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _win_pct(cell: str) -> int | None:
    wt = _won_total(cell)
    if wt is None or wt[0] == 0:
        return None
    total, won = wt
    return round(won / total * 100)


# ---- row builders --------------------------------------------------------
def parse_map(m: dict, match_id: int, map_index: int, team_ids: tuple[int, int]) -> dict:
    t1_id, t2_id = team_ids
    s1 = _int(m["score"]["team1"])
    s2 = _int(m["score"]["team2"])
    winner_id = None
    if s1 is not None and s2 is not None and s1 != s2:
        winner_id = t1_id if s1 > s2 else t2_id
    return {
        "match_id": match_id,
        "map_index": map_index,
        "map_name": m["map_name"],
        "picked_by_team_id": None,  # /v2 'picked_by' is just 'PICK', no team
        "team1_score": s1,
        "team2_score": s2,
        "team1_ct_score": _int(m.get("score_ct", {}).get("team1")),
        "team1_t_score": _int(m.get("score_t", {}).get("team1")),
        "team2_ct_score": _int(m.get("score_ct", {}).get("team2")),
        "team2_t_score": _int(m.get("score_t", {}).get("team2")),
        "duration_seconds": parse_duration(m.get("duration", "")),
        "winner_id": winner_id,
    }


def parse_rounds(rounds: list, map_id: int, team_ids: tuple[int, int]) -> list[dict]:
    """Valid rounds only (winner in team1/team2, side in ct/t)."""
    t1_id, t2_id = team_ids
    out = []
    for r in rounds:
        winner, side = r.get("winner"), r.get("side")
        if winner not in ("team1", "team2") or side not in ("ct", "t"):
            continue
        rnum = _int(r.get("round_num"))
        if rnum is None:
            continue
        out.append({
            "map_id": map_id,
            "round_number": rnum,
            "half": round_half(rnum),
            "team1_side": side,
            "team2_side": "t" if side == "ct" else "ct",
            "winner_id": t1_id if winner == "team1" else t2_id,
        })
    return out


def parse_player_stats(players: dict, map_id: int, team_ids: tuple[int, int]) -> list[dict]:
    t1_id, t2_id = team_ids
    rows = []
    for key, team_id in (("team1", t1_id), ("team2", t2_id)):
        for p in players.get(key, []):
            handle = p.get("name")
            if not handle:
                continue
            rows.append({
                "map_id": map_id,
                "player_handle": handle,
                "player_id": None,  # resolved in P2.T7
                "team_id_at_match": team_id,
                "agent": p.get("agent") or None,
                "rating": _float(p.get("rating")),
                "acs": _int(p.get("acs")),
                "kills": _int(p.get("kills")),
                "deaths": _int(p.get("deaths")),
                "assists": _int(p.get("assists")),
                "kast_pct": _pct(p.get("kast")),
                "adr": _float(p.get("adr")),
                "hs_pct": _pct(p.get("hs_pct")),
                "fk": _int(p.get("fk")),
                "fd": _int(p.get("fd")),
            })
    return rows


def parse_economy(economy: list, map_id: int, team_ids: tuple[int, int]) -> list[dict]:
    """economy[i] = {0: tag, 1: pistols_won, 2: eco '(won)', 3: $, 4: $$, 5: $$$}.

    vlr has 5 buy buckets (pistol + eco/$/$$/$$$); the schema has 4 pct columns,
    so the '$' (semi-eco, index 3) bucket is dropped. pistol % is won/2.
    """
    t1_id, t2_id = team_ids
    rows = []
    for row, team_id in zip(economy, (t1_id, t2_id)):
        pistols_won = _int(row.get("1"))
        rows.append({
            "map_id": map_id,
            "team_id_at_match": team_id,
            "pistol_win_pct": round(pistols_won / 2 * 100) if pistols_won is not None else None,
            "eco_win_pct": _win_pct(row.get("2")),
            "semi_buy_win_pct": _win_pct(row.get("4")),  # '$$' bucket
            "full_buy_win_pct": _win_pct(row.get("5")),  # '$$$' bucket
        })
    return rows


# ---- DB writes -----------------------------------------------------------
def _upsert_map(conn: sqlite3.Connection, row: dict, is_complete: int) -> int:
    conn.execute(
        """
        INSERT INTO maps (match_id, map_index, map_name, picked_by_team_id,
                          team1_score, team2_score, team1_ct_score, team1_t_score,
                          team2_ct_score, team2_t_score, duration_seconds, winner_id,
                          is_rounds_complete)
        VALUES (:match_id, :map_index, :map_name, :picked_by_team_id,
                :team1_score, :team2_score, :team1_ct_score, :team1_t_score,
                :team2_ct_score, :team2_t_score, :duration_seconds, :winner_id,
                :is_rounds_complete)
        ON CONFLICT(match_id, map_index) DO UPDATE SET
            map_name=excluded.map_name, team1_score=excluded.team1_score,
            team2_score=excluded.team2_score, team1_ct_score=excluded.team1_ct_score,
            team1_t_score=excluded.team1_t_score, team2_ct_score=excluded.team2_ct_score,
            team2_t_score=excluded.team2_t_score, duration_seconds=excluded.duration_seconds,
            winner_id=excluded.winner_id, is_rounds_complete=excluded.is_rounds_complete
        """,
        {**row, "is_rounds_complete": is_complete},
    )
    return conn.execute(
        "SELECT map_id FROM maps WHERE match_id=? AND map_index=?",
        (row["match_id"], row["map_index"]),
    ).fetchone()[0]


def _upsert_round(conn, r: dict) -> None:
    conn.execute(
        """
        INSERT INTO rounds (map_id, round_number, half, team1_side, team2_side, winner_id)
        VALUES (:map_id, :round_number, :half, :team1_side, :team2_side, :winner_id)
        ON CONFLICT(map_id, round_number) DO UPDATE SET
            half=excluded.half, team1_side=excluded.team1_side,
            team2_side=excluded.team2_side, winner_id=excluded.winner_id
        """,
        r,
    )


def _upsert_player_stat(conn, p: dict) -> None:
    conn.execute(
        """
        INSERT INTO map_player_stats (map_id, player_handle, player_id, team_id_at_match,
            agent, rating, acs, kills, deaths, assists, kast_pct, adr, hs_pct, fk, fd)
        VALUES (:map_id, :player_handle, :player_id, :team_id_at_match,
            :agent, :rating, :acs, :kills, :deaths, :assists, :kast_pct, :adr, :hs_pct, :fk, :fd)
        ON CONFLICT(map_id, player_handle) DO UPDATE SET
            team_id_at_match=excluded.team_id_at_match, agent=excluded.agent,
            rating=excluded.rating, acs=excluded.acs, kills=excluded.kills,
            deaths=excluded.deaths, assists=excluded.assists, kast_pct=excluded.kast_pct,
            adr=excluded.adr, hs_pct=excluded.hs_pct, fk=excluded.fk, fd=excluded.fd
        """,
        p,
    )


def _upsert_economy(conn, e: dict) -> None:
    conn.execute(
        """
        INSERT INTO map_team_economy (map_id, team_id_at_match, pistol_win_pct,
            eco_win_pct, semi_buy_win_pct, full_buy_win_pct)
        VALUES (:map_id, :team_id_at_match, :pistol_win_pct, :eco_win_pct,
            :semi_buy_win_pct, :full_buy_win_pct)
        ON CONFLICT(map_id, team_id_at_match) DO UPDATE SET
            pistol_win_pct=excluded.pistol_win_pct, eco_win_pct=excluded.eco_win_pct,
            semi_buy_win_pct=excluded.semi_buy_win_pct, full_buy_win_pct=excluded.full_buy_win_pct
        """,
        e,
    )


def ingest_detail_into_db(conn: sqlite3.Connection, detail: dict) -> dict:
    """Parse a /v2/match/details segment and write maps/rounds/stats/economy.

    Returns a small summary dict. Skips maps with no name (unplayed).
    """
    match_id = int(detail["match_id"])
    team_ids = (int(detail["teams"][0]["id"]), int(detail["teams"][1]["id"]))
    counts = {"maps": 0, "rounds": 0, "player_stats": 0, "economy": 0, "maps_complete": 0}

    for idx, m in enumerate(detail.get("maps", [])):
        if not m.get("map_name"):
            continue
        map_row = parse_map(m, match_id, idx, team_ids)
        round_rows = parse_rounds(m.get("rounds", []), map_id=-1, team_ids=team_ids)
        total_score = (map_row["team1_score"] or 0) + (map_row["team2_score"] or 0)
        is_complete = 1 if total_score and len(round_rows) == total_score else 0

        map_id = _upsert_map(conn, map_row, is_complete)
        counts["maps"] += 1
        counts["maps_complete"] += is_complete

        for r in parse_rounds(m.get("rounds", []), map_id, team_ids):
            _upsert_round(conn, r)
            counts["rounds"] += 1
        for p in parse_player_stats(m.get("players", {}), map_id, team_ids):
            _upsert_player_stat(conn, p)
            counts["player_stats"] += 1
        for e in parse_economy(m.get("economy", []), map_id, team_ids):
            _upsert_economy(conn, e)
            counts["economy"] += 1

    return counts


async def ingest_match_details(match_id: int, db_path: str, *, client: VlrClient | None = None) -> dict:
    if client is None:
        async with VlrClient() as owned:
            return await _ingest_one(match_id, db_path, owned)
    return await _ingest_one(match_id, db_path, client)


async def _ingest_one(match_id: int, db_path: str, client: VlrClient) -> dict:
    detail = (await client.get_segments("/v2/match/details", match_id=str(match_id)))[0]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        counts = ingest_detail_into_db(conn, detail)
        conn.commit()
    finally:
        conn.close()
    logger.info("match_details_ingested", match_id=match_id, **counts)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest map/round/player/economy detail for a match.")
    parser.add_argument("--db", default="data/prx.db", help="SQLite warehouse path")
    parser.add_argument("--match-id", type=int, required=True, help="vlr.gg match ID")
    args = parser.parse_args(argv)
    counts = asyncio.run(ingest_match_details(args.match_id, args.db))
    print(f"match {args.match_id}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
