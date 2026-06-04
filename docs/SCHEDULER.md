# SCHEDULER.md

APScheduler configuration for the prx-app container. All scheduled jobs run inside the FastAPI process via `BackgroundScheduler` started in the FastAPI lifespan handler.

---

## Jobs

| Job ID | Schedule | Purpose | Cost |
|---|---|---|---|
| `ingest_new_matches` | every 30 min during VCT season; every 4 hours off-season | pull new completed matches and update DB | ~50 vlrggapi requests per run |
| `live_match_poll` | every 30s when any tier-1 match is LIVE; else idle | track current live state for predictions | ~120 vlrggapi requests per live match-hour |
| `weekly_retrain` | Sundays 03:00 UTC | re-fit Bambi model, recompute Elo from scratch, rebuild score-state lookup | local CPU only |
| `patch_lookup_refresh` | Sundays 02:00 UTC | scrape Riot patch notes, update `patches` table | ~5 HTTP requests |
| `roster_history_sync` | daily 04:00 UTC | pull `/v2/team/transactions` for tier-1 teams | ~50 vlrggapi requests |

---

## Implementation

### Code structure
```
scheduler/
├── __init__.py            # setup_scheduler() function
├── config.py              # job schedule definitions (cron strings, intervals)
├── locks.py               # SQLite-based advisory locks to prevent overlap
└── jobs/
    ├── __init__.py
    ├── ingest.py          # ingest_new_matches job
    ├── live_poll.py       # live_match_poll job (state machine: IDLE → POLLING → IDLE)
    ├── retrain.py         # weekly_retrain job
    ├── patch.py           # patch_lookup_refresh job
    └── roster.py          # roster_history_sync job
```

### Startup wiring (in `api/main.py`)
```python
from contextlib import asynccontextmanager
from scheduler import setup_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

---

## Per-job specifications

### `ingest_new_matches`

**Logic:**
1. Read latest `date_utc` from `matches` table.
2. Hit `/v2/match?q=results` paginated until results predate that cutoff.
3. For each new match: ingest match details, populate maps, rounds, player_stats, economy.
4. Update Elo ratings incrementally (no full replay).
5. Update player_skill incrementally.
6. Log row deltas.

**Trigger:**
- VCT season (= today is within any active event's date range): `IntervalTrigger(minutes=30)`
- Off-season: `IntervalTrigger(hours=4)`
- Determined dynamically by `is_vct_active()` helper that checks events table

**Lock:** acquire `ingest_lock` before running. Skip if locked (another instance running).

**Failure mode:** if vlrggapi returns 5xx, log + retry on next schedule. Don't crash the scheduler.

---

### `live_match_poll`

**State machine:**
- IDLE: every 60s, check `/v2/match?q=live_score` for any tier-1 match
- POLLING (when match detected): every 30s, fetch live state for the tracked match, run prediction, write to `live_state` + `live_predictions`
- Transition POLLING → IDLE when tracked match status is no longer LIVE

**Priority logic when multiple tier-1 matches are live (per SPEC D3):**
1. PRX match (team_id 624)
2. Higher tournament tier (Champions > Masters > Regional League)
3. Earliest start time

**Implementation:**
- Single in-memory state variable for the currently-tracked match_id
- Reset to None on shutdown; rehydrate on startup if any match is live

**Lock:** none needed (single in-memory state)

---

### `weekly_retrain`

**Logic:**
1. Acquire `retrain_lock`
2. Backup current `data/prx.db` to `data/prx.db.backup-{date}`
3. Truncate `elo_ratings`, `elo_map_offsets`, `score_state_lookup`, `player_skill`
4. Replay all matches chronologically to rebuild Elo + map offsets + player skills
5. Rebuild score_state_lookup from all rounds
6. Re-fit Bambi model on all training data, save posterior trace to `models/saved/bayes_logistic.nc`
7. Release lock
8. Log timing and any anomalies

**Trigger:** `CronTrigger(day_of_week='sun', hour=3, minute=0, timezone='UTC')`

**Expected duration:** 5–20 minutes (Bambi fit dominates)

**Failure mode:** if anything fails, restore from backup. Log + alert via warning log line. Next attempt next Sunday.

---

### `patch_lookup_refresh`

**Logic:**
1. Scrape https://playvalorant.com/en-us/news/tags/patch-notes/ — look for entries with title pattern `VALORANT Patch Notes X.YY`
2. For each patch, parse the release date from the article metadata
3. Upsert into `patches` table
4. Backfill `matches.patch_id` for any matches missing one, based on their `date_utc` and the patches release dates
5. Save current state to `data/patches.json` for traceability

**Trigger:** `CronTrigger(day_of_week='sun', hour=2, minute=0, timezone='UTC')`

**Failure mode:** if scrape fails (Riot site change), log warning + retry next week. Patches don't change often; one missed refresh is fine.

---

### `roster_history_sync`

**Logic:**
1. List all tier-1 team IDs (from `teams` table where region is one of the regional codes)
2. For each: fetch `/v2/team/transactions?id={id}`
3. Diff against current `roster_history` rows for that team
4. Insert new rows for new transactions
5. Update `left_date` on existing rows if a player has moved
6. Update `players.current_team_id` based on the latest active row per player

**Trigger:** `CronTrigger(hour=4, minute=0, timezone='UTC')` — daily

**Lock:** `roster_lock` to avoid concurrent updates

**Failure mode:** if vlrggapi fails, retry next day. Roster changes are typically slow (~50 events/year tier-1-wide), so a day's delay is acceptable.

---

## Locking

SQLite-based advisory locks to prevent job overlaps. Lock table:

```sql
CREATE TABLE job_locks (
    lock_name TEXT PRIMARY KEY,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
```

Helper functions in `scheduler/locks.py`:
- `acquire_lock(name, ttl_seconds)` — returns True if acquired, False if held
- `release_lock(name)`
- `with_lock(name, ttl_seconds)` — context manager

Locks have a TTL so a crashed job doesn't permanently block the next run.

---

## Time zones

- All schedules expressed in UTC
- All timestamps stored in UTC (ISO 8601)
- Frontend converts to user's browser-local time for display

---

## Observability

Each job logs structured events:
- `job_start` — job_id, scheduled_at, actual_start_at
- `job_end` — job_id, duration_seconds, rows_affected (where applicable)
- `job_error` — job_id, exception_type, exception_message, stack

Aggregate metrics not in scope for v1. If we need dashboards later, add Prometheus exporters.

---

## Manual triggers

For one-off runs (e.g., after a code change), expose admin endpoints:
- `POST /api/admin/jobs/{job_id}/run` — requires `X-Admin-Token` header matching env var
- Returns 200 + job-run-id, runs in background

Don't auto-document these in `/docs`; they're for Rahat's manual use.
