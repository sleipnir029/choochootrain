"""
Ad-hoc smoke test for the self-hosted vlrggapi (P1.T3).

Hits the four endpoints the ingestion pipeline (Phase 2) will rely on and checks
that the fields we depend on are present. Dependency-free (stdlib only) so it runs
against a bare Python; P2.T2 will re-express these calls through ingestion.vlr_client.

Usage:
    python scripts/smoke_vlrggapi.py
    VLRGGAPI_URL=http://localhost:3001 MATCH_ID=666493 python scripts/smoke_vlrggapi.py

Exit code 0 = all checks passed, 1 = at least one failed.

Note on routes: in the pinned upstream (a6075fe), team match history and roster
transactions are q-variants on /v2/team (e.g. /v2/team?id=624&q=matches), not the
separate /v2/team/matches path some docs assume. See docs/DEVIATIONS.md.
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("VLRGGAPI_URL", "http://localhost:3001").rstrip("/")
PRX_TEAM_ID = "624"
MATCH_ID = os.environ.get("MATCH_ID", "666493")  # PRX vs FULL SENSE, 2026 Pacific Stage 1 GF (completed)


def get(path: str) -> dict:
    """GET BASE+path, return parsed JSON, raising on transport/HTTP error."""
    with urllib.request.urlopen(BASE + path, timeout=60) as resp:
        return json.load(resp)


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def check_team_profile() -> str:
    d = get(f"/v2/team?id={PRX_TEAM_ID}")
    require(d.get("status") == "success", "envelope status != success")
    seg = d["data"]["segments"][0]
    require(seg.get("id") == PRX_TEAM_ID, f"team id mismatch: {seg.get('id')}")
    require(seg.get("name") == "Paper Rex", f"expected Paper Rex, got {seg.get('name')}")
    require(bool(seg.get("tag")), "missing team tag")
    return f"PRX profile: {seg['name']} ({seg.get('tag')}), country={seg.get('country')}"


def check_team_matches() -> str:
    d = get(f"/v2/team?id={PRX_TEAM_ID}&q=matches&page=1")
    require(d.get("status") == "success", "envelope status != success")
    segs = d["data"]["segments"]
    require(isinstance(segs, list) and len(segs) > 0, "no match-history segments")
    m = segs[0]
    for f in ("match_id", "team1", "team2", "score"):
        require(f in m, f"match history missing field: {f}")
    return f"team matches: {len(segs)} rows, latest match_id={m['match_id']}"


def check_match_details() -> str:
    d = get(f"/v2/match/details?match_id={MATCH_ID}")
    require(d.get("status") == "success", "envelope status != success")
    seg = d["data"]["segments"][0]
    require(seg.get("match_id") == MATCH_ID, f"match_id mismatch: {seg.get('match_id')}")
    for f in ("teams", "maps", "head_to_head", "economy"):
        require(f in seg, f"match details missing field: {f}")
    require(isinstance(seg["maps"], list) and len(seg["maps"]) > 0, "no maps in match details")
    return f"match {MATCH_ID}: {len(seg['maps'])} map(s), economy+h2h present"


def check_live_score() -> str:
    d = get("/v2/match?q=live_score")
    require(d.get("status") == "success", "envelope status != success")
    segs = d["data"]["segments"]
    require(isinstance(segs, list), "live_score segments is not a list")
    if not segs:
        return "live_score: endpoint healthy, no matches live right now"
    s = segs[0]
    for f in ("match_id", "score1", "score2", "current_map", "team1_round_ct", "team2_round_t"):
        require(f in s, f"live segment missing field: {f}")
    return f"live_score: {len(segs)} live, e.g. {s['team1']} {s['score1']}:{s['score2']} {s['team2']} on {s['current_map']}"


CHECKS = [
    ("GET /v2/team?id=624                (PRX profile)", check_team_profile),
    ("GET /v2/team?id=624&q=matches      (team matches)", check_team_matches),
    (f"GET /v2/match/details?match_id={MATCH_ID} (detail)", check_match_details),
    ("GET /v2/match?q=live_score         (live state)", check_live_score),
]


def main() -> int:
    print(f"Smoke-testing vlrggapi at {BASE}\n")
    failures = 0
    for label, fn in CHECKS:
        try:
            detail = fn()
            print(f"  PASS  {label}\n        -> {detail}")
        except Exception as e:  # noqa: BLE001 - smoke test wants the message, not a trace
            failures += 1
            print(f"  FAIL  {label}\n        -> {type(e).__name__}: {e}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
