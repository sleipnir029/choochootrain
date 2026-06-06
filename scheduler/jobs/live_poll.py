"""Live score poller — track a live tier-1 match and log score changes (P5.T1).

Polls `/v2/match?q=live_score` and persists the current state of the tracked match
to the `live_state` table (singleton), logging every score change. State machine
(SCHEDULER.md): IDLE polls every `idle_interval` (60s) for any live match; POLLING
polls the tracked match every `poll_interval` (30s) and writes state; back to IDLE
when nothing is live.

Match selection here is minimal — prefer a Paper Rex match, else the first live
segment. Full tier-1 detection + multi-match priority (PRX > Champions > Masters >
Regional > earliest) is P5.T4. Uses `VlrClient(cache=False)` (volatile endpoint).

Note: `live_state.match_id` FKs `matches(match_id)`, but a live match may not be
ingested yet; SQLite FK enforcement is off by default, so the insert is safe.

Usage:
    python -m scheduler.jobs.live_poll --db data/prx.db [--idle 60 --poll 30 --once]
"""

import argparse
import asyncio
import sqlite3
from datetime import datetime, timezone

import structlog

from ingestion.vlr_client import VlrClient

logger = structlog.get_logger()

# Fields that constitute a "score change" worth logging / re-predicting on.
_CHANGE_FIELDS = ["team1_score", "team2_score", "team1_round_ct", "team1_round_t",
                  "team2_round_ct", "team2_round_t", "map_number", "current_map"]


def _to_int(value):
    """Parse a live_score numeric field; 'N/A'/blank/None -> None."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_live_segment(seg):
    """Map a /v2/match?q=live_score segment to a live_state row dict."""
    return {
        "match_id": _to_int(seg.get("match_id")),
        "team1_score": _to_int(seg.get("score1")),
        "team2_score": _to_int(seg.get("score2")),
        "team1_round_ct": _to_int(seg.get("team1_round_ct")),
        "team1_round_t": _to_int(seg.get("team1_round_t")),
        "team2_round_ct": _to_int(seg.get("team2_round_ct")),
        "team2_round_t": _to_int(seg.get("team2_round_t")),
        "map_number": _to_int(seg.get("map_number")),
        "current_map": seg.get("current_map"),
    }


def state_changed(old, new):
    """Tracked fields that differ between two states ([] if old is None / same match)."""
    if old is None or old.get("match_id") != new.get("match_id"):
        return []
    return [f for f in _CHANGE_FIELDS if old.get(f) != new.get(f)]


_TIER_RANK = {"Champions": 3, "Masters": 2, "Kickoff": 1, "RegionalLeague": 1}


def classify_tier(match_event):
    """Tier of a live match from its event name (live_score's `match_event`).

    Order matters: VCT names carry the "Champions Tour" circuit brand, so check the
    specific tiers first and only treat a name as the Champions *tournament* when it
    says "champion(s)" without the "champions tour" branding.
    """
    e = (match_event or "").lower()
    if "kickoff" in e:
        return "Kickoff"
    if "master" in e:
        return "Masters"
    if "champion" in e and "champions tour" not in e:
        return "Champions"
    return "RegionalLeague"   # catch-all: regional league stages, "Champions Tour: ... Stage N"


def _is_prx(seg):
    return "paper rex" in f"{seg.get('team1', '')} {seg.get('team2', '')}".lower()


def _priority_key(seg):
    """Sort key (higher = higher priority): PRX > tier > earliest start."""
    ts = _to_int(seg.get("unix_timestamp"))
    return (
        1 if _is_prx(seg) else 0,
        _TIER_RANK.get(classify_tier(seg.get("match_event")), 0),
        -(ts if ts is not None else float("inf")),   # earliest start wins ties
    )


def select_match(segments):
    """Pick the live match to track by SPEC-D3 priority: PRX > Champions > Masters >
    Regional League > earliest start. No hard tier-2 exclusion — live matches aren't
    in the curated tier-1 registry, so the key just deprioritizes non-tier-1 events
    (DEVIATIONS 2026-06-06)."""
    if not segments:
        return None
    return max(segments, key=_priority_key)


def write_live_state(conn, state):
    """Singleton write: keep only the tracked match's row, stamped now (UTC)."""
    conn.execute("DELETE FROM live_state")
    conn.execute(
        "INSERT INTO live_state (match_id, team1_score, team2_score, team1_round_ct, "
        "team1_round_t, team2_round_ct, team2_round_t, map_number, current_map, last_updated) "
        "VALUES (:match_id, :team1_score, :team2_score, :team1_round_ct, :team1_round_t, "
        ":team2_round_ct, :team2_round_t, :map_number, :current_map, :last_updated)",
        {**state, "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    )
    conn.commit()


def to_predict_live_state(state):
    """Map a poller live_state to models.predict's live_state shape.

    predict's score-state lookup wants **round counts on the current map** (not the
    map/series score) + team1's current side. Side is best-effort: live_score
    doesn't expose the current side, so infer the first-half side from team1's wins
    (default ct at 0-0) and flip in the second half (DEVIATIONS 2026-06-06).
    """
    t1 = (state.get("team1_round_ct") or 0) + (state.get("team1_round_t") or 0)
    t2 = (state.get("team2_round_ct") or 0) + (state.get("team2_round_t") or 0)
    total = t1 + t2
    half = "first" if total < 12 else ("second" if total < 24 else "ot")
    first_half_ct = (state.get("team1_round_ct") or 0) >= (state.get("team1_round_t") or 0)
    if half == "second":
        team1_side = "t" if first_half_ct else "ct"
    else:
        team1_side = "ct" if first_half_ct else "t"
    return {"half": half, "team1_score": t1, "team2_score": t2, "team1_side": team1_side}


def write_live_prediction(conn, match_id, map_index, prob):
    """Append a live win-prob to live_predictions (PK incl. microsecond timestamp)."""
    conn.execute(
        "INSERT INTO live_predictions (match_id, map_index, computed_at, team1_win_prob) "
        "VALUES (?, ?, ?, ?)",
        (match_id, map_index, datetime.now(timezone.utc).isoformat(), prob),
    )
    conn.commit()


def make_prediction_callback(db_path="data/prx.db"):
    """Build an on_change callback that re-predicts the map and stores it.

    NOTE: `predict_map_win_prob` needs the match's ingested map features, so live
    prediction works only for matches already in the warehouse; an un-ingested live
    match raises and is swallowed by poll_once's guard (upcoming-match prediction is
    a Phase-6 feature). See DEVIATIONS 2026-06-06.
    """
    from models.predict import predict_map_win_prob  # heavy (bambi/arviz) — import lazily

    def on_change(state, changed):
        map_index = (state.get("map_number") or 1) - 1
        live_state = to_predict_live_state(state)
        prob = predict_map_win_prob(state["match_id"], map_index,
                                    live_state=live_state, db_path=db_path)
        conn = sqlite3.connect(db_path)
        try:
            write_live_prediction(conn, state["match_id"], map_index, prob)
        finally:
            conn.close()
        logger.info("live_prediction", match_id=state["match_id"], map_index=map_index,
                    team1_win_prob=round(prob, 4))

    return on_change


async def poll_once(client, conn, last_state, on_change=None):
    """One poll: fetch live_score, select a match, log/persist, fire on_change.

    `on_change(state, changed)` is a synchronous callback invoked **once** per poll
    in which a same-match score change is detected (`changed` = the changed fields).
    It is not called on the baseline (first observation) or a match switch. A raising
    callback is caught and logged so the poll loop survives. Returns the new state
    (or None when nothing is live / the segment lacks a match_id).
    """
    segments = await client.get_segments("/v2/match", q="live_score")
    seg = select_match(segments)
    if seg is None:
        logger.info("no_live_match")
        return None
    state = parse_live_segment(seg)
    if state["match_id"] is None:
        logger.warning("live_segment_missing_match_id", segment=seg)
        return None

    if last_state is None or last_state.get("match_id") != state["match_id"]:
        logger.info("tracking_live_match", match_id=state["match_id"],
                    current_map=state["current_map"],
                    score=f"{state['team1_score']}-{state['team2_score']}")
    else:
        changed = state_changed(last_state, state)
        if changed:
            logger.info("score_change", match_id=state["match_id"], changed=changed,
                        **{f: state[f] for f in changed})
            if on_change is not None:
                try:
                    on_change(state, changed)
                except Exception as e:  # noqa: BLE001 - a callback failure must not kill the poller
                    logger.error("on_change_failed", match_id=state["match_id"], error=repr(e))
    write_live_state(conn, state)
    return state


async def run(db_path="data/prx.db", *, idle_interval=60, poll_interval=30, once=False,
              on_change=None):
    """IDLE/POLLING loop. `once=True` runs a single cycle (standalone smoke / tests)."""
    conn = sqlite3.connect(db_path)
    last = None
    try:
        async with VlrClient(cache=False) as client:
            while True:
                last = await poll_once(client, conn, last, on_change=on_change)
                if once:
                    break
                await asyncio.sleep(poll_interval if last is not None else idle_interval)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prx.db")
    ap.add_argument("--idle", type=float, default=60.0)
    ap.add_argument("--poll", type=float, default=30.0)
    ap.add_argument("--once", action="store_true", help="single poll then exit")
    args = ap.parse_args()
    asyncio.run(run(args.db, idle_interval=args.idle, poll_interval=args.poll, once=args.once,
                    on_change=make_prediction_callback(args.db)))


if __name__ == "__main__":
    main()
