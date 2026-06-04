# PROGRESS.md

Running log of work done on PRX Predictor. Updated by Claude Code after every task. This file is how the next session knows where to pick up.

---

## How to use this file

### Before starting any task
1. Read the "Current state" block below
2. Read the latest 3 entries under "Entries" (most recent first)
3. Read the current phase's summary (if it exists)
4. Read any unresolved blockers

### After completing a task
1. Add an entry at the top of "Entries" using the template
2. Update "Current state" if the next task changes
3. Don't delete or edit old entries (immutable history)

### After completing a phase
1. Write a phase summary in that phase's section (template at the bottom of this file)
2. Update "Current state" with the new phase
3. Tag the git commit (e.g., `v0.1.0-phase-2`)
4. **Stop and wait for Rahat** — do not auto-start the next phase

---

## Current state

**Phase:** 2 IN PROGRESS — schema + bulk ingestion. (Phase 0 validation T2–T6 still deferred.)
**Last completed task:** P2.T13 — Date→patch lookup + backfill (also did T12 validation). 2024 data fully ingested, validated, and patch-tagged.
**Next task:** P2.T10 — Bulk pull 2025, then T11 (2026 to date). [T12 ✓, T13 ✓ done out of order per Rahat.] Then T14 phase summary + tag.
**Open blockers:** none. Rate-limiting (429) makes the bulk player/roster stages slow; caching mitigates re-runs. 4 one-off 2024 handles unresolved (by design).
**Open blockers:** Peng IEEE dataset paywalled (Phase 0 loadout-only when resumed); repo is public by choice (secrets in gitignored `.env`).
**Workflow note:** working directly on `main` now (no per-phase branches) — Rahat's call after a stale branch caused a duplicate Phase 1.

---

## Phase summaries

### Phase 0 — Peng dataset validation
*To be filled in after Phase 0 complete*

### Phase 1 — Self-host vlrggapi

**Built:**
- vlrggapi vendored as a git submodule at `vendor/vlrggapi`, pinned to `a6075fec` (+ `vendor/VERSION.txt` provenance).
- Local Docker image `vlrggapi:a6075fe` (186MB) built from the vendored source.
- `scripts/smoke_vlrggapi.py` — stdlib smoke tester for the 4 endpoints ingestion will use.
- Project skeleton (`ingestion/ models/ api/ scheduler/ llm/ tests/` packages + `notebooks/ dashboard/ docker/ .github/workflows/`).
- CI: `.github/workflows/ci.yml` (syntax check + pytest placeholder + prx-app image build), `docker/Dockerfile` (FastAPI hello-world stub), `pytest.ini`.
- `docker/docker-compose.yml` — `vlrggapi` + `prx-app` two-service dry-run; `docker/app_stub.py`; `.dockerignore`.
- Secret hygiene: `.gitignore` covers `.env*` (keeps `!.env.example`); `.env.example` template.

**What works:** vlrggapi container health `success` (service + vlr.gg upstream Healthy); all 4 smoke endpoints pass (PRX profile, team matches, match details w/ maps+economy, live_score); GitHub Actions CI green; compose stack verified — `prx-app` reaches `http://vlrggapi:3001/v2/health` over the network.

**What's pending or deferred:** **Phase 0 validation (T2–T6) remains deferred** — Peng IEEE dataset is paywalled; will resume loadout-only from vlr.gg via the Phase 2 pipeline (see DEVIATIONS 2026-06-04). The prx-app is only a hello-world stub (real app = Phase 6).

**Numbers:** vlrggapi image 186MB; prx-app stub image small; smoke 4/4; CI ~1 min.

**Surprises:** upstream vlrggapi is on Python 3.14 (not the SPEC's 3.11); team match/transactions are `q=` variants on `/v2/team`, not separate paths; repo is public (kept, with secrets gitignored). All logged in DEVIATIONS.

**Next phase prep:** Phase 2 (schema + ingestion) can build directly on the vendored vlrggapi and the verified endpoints/field shapes. Use the `q=`-variant team URLs.

### Phase 2 — Schema + bulk ingestion
*Locked until Phase 1 complete*

### Phase 3 — Statistical modeling
*Locked until Phase 2 complete*

### Phase 4 — Player skill layer
*Locked*

### Phase 5 — Live update logic
*Locked*

### Phase 6 — FastAPI + React dashboard
*Locked*

### Phase 7 — LLM adapter
*Locked*

### Phase 8 — Deployment
*Locked*

---

## Entries

*Newest at top. Don't edit old entries.*

### 2026-06-04 23:35 UTC — P2.T10 done (2025); T11 (2026) failed on upstream circuit breaker; bulk resilience fix

**Done:** **P2.T10 — 2025 bulk complete:** 15 events, 504 matches, 1,277 maps, 26,974 rounds, 12,770 player_stats, 331 players resolved (24 unresolved), 709 roster rows; 1 detail_failure. All 15 2025 events have matches. Warehouse now spans 2024+2025: 940 matches, 2,382 maps, 50,375 rounds, 23,820 player_stats, 421 players.

**P2.T11 — 2026 FAILED (0 ingested):** vlrggapi's **circuit breaker to vlr.gg tripped** after hours of sustained load — `/v2/events/matches` returns `503 "Circuit open for www.vlr.gg — request blocked"`. The 2026 run got 0 matches (first events returned empty listings as the breaker began tripping; event 2863 then raised and aborted the year).

**Bug fixed:** `scripts/bulk_ingest.py` did not guard the per-event `ingest_event_matches` call (only the details loop), so one event's transient failure aborted the whole year. Now wrapped in try/except → logs `event_failed`, increments `event_failures`, and continues. (compile + 43 tests green.)

**Next:** re-run 2026 after a vlr.gg cooldown (container stopped to let upstream recover). `python -m scripts.bulk_ingest --year 2026 --db data/prx.db --skip-events`. The cache + resilience fix make this safe/resumable.

**Files touched:**
- `scripts/bulk_ingest.py` (modified — per-event try/except, `event_failures`)

**Commit:** `<pending>` — `fix(bulk): don't abort the year on one event's failure`

### 2026-06-04 22:02 UTC — P2.T13 — Date→patch lookup + backfill

**Done:** Added `ingestion/patches.py` — scrapes Riot's patch-notes index once (parses `__NEXT_DATA__`), writes committed `data/patches.json` (142 patches, 0.47→12.10), populates the `patches` table, and backfills `matches.patch_id` to the latest patch released on/before each match date. CLI `python -m ingestion.patches --db data/prx.db [--refresh]`. Added `tests/test_patches.py` (3 tests). Rahat-approved external source (DEVIATIONS 2026-06-04).

**Learned or surprised:** article date is under `publishedAt`/`publishDate` (not `date`) — wrong key initially yielded 0. One page covers the full patch history (no pagination needed). Backfill matches the authoritative per-match label (312765 → 8.04, as the match detail said).

**Verification:** `pytest tests/test_patches.py` → 3 passed (parse fixture, date-range backfill incl. before-first-patch NULL, idempotent populate); full suite **43 passed**. Live: 142 patches, **all 436 matches backfilled, 0 NULL patch_id**, FK clean; re-run from committed JSON (no network) reproduces it.

**Files touched:**
- `ingestion/patches.py` (created)
- `data/patches.json` (created — committed source of truth)
- `tests/test_patches.py` (created)
- `docs/DEVIATIONS.md` (modified — patches source)

**Commit:** `952b4d4` — `phase-2.task-13: date→patch lookup + backfill`

### 2026-06-04 21:53 UTC — P2.T12 — Ingestion validation

**Done:** Added `scripts/validate_ingestion.py` (read-only) — row counts, per-year matches/maps/rounds + rounds-completeness, and anomaly checks (matches w/o maps, maps w/o stats, incomplete maps, NULL player_id/winner/patch, FK check). Prints + saves to `logs/ingestion_validation.txt`. Gitignored generated logs/reports (`logs/*` except `.gitkeep`).

**Verification (2024):** 436 matches / 1,105 maps / 23,401 rounds, **100% rounds-complete maps**, 0 maps missing stats, 0 NULL winners, FK clean. Anomalies (benign, in DEVIATIONS): 1 match with 0 maps = showmatch 321373; 4/11,050 stat rows NULL player_id. patch_id NULL for all (→ T13).

**Files touched:**
- `scripts/validate_ingestion.py` (created)
- `.gitignore` (modified — ignore generated logs/reports)
- `docs/DEVIATIONS.md` (modified — validation anomalies)

**Commit:** `ee4f6fc` — `phase-2.task-12: ingestion validation script`

### 2026-06-04 21:46 UTC — P2.T9 — Bulk pull 2024 (complete)

**Done:** Completed the full 2024 bulk via `scripts/bulk_ingest.py` (run in two halves around a pause: match phases, then a cached `--skip-matches` resume for players+roster). All 15 2024 tier-1 events ingested end-to-end. Log saved to `logs/bulk_ingest_2024.log`.

**Warehouse state (data/prx.db, FK check clean):** events 43, matches 436 (435 with full map detail; 1 detail_failure — a match with no maps, non-fatal), maps 1,105, rounds 23,401, map_player_stats 11,050, map_team_economy 1,630, teams 47, players 267, roster_history 515.

**Player resolution:** 11,046/11,050 stat rows resolved (**99.96%**). 4 unresolved one-off handles (`EQ118`, `dank1ng`, `spicyuuu`, `zhang yanqi` — likely CN subs/stand-ins; no exact search match), left `player_id` NULL by design.

**Learned or surprised:** rate-limiting (429) dominated wall-clock; the player-resolution stage is by far the slowest. The cache (added mid-task) makes future re-runs cheap. `economy=0` on some matches (empty economy block upstream).

**Verification:** counts above queried post-run; `PRAGMA foreign_key_check` empty. `bulk_done` logged (resume: players_resolved=251, unresolved=4, roster_rows=515; match-phase counts from the earlier half in the same log).

**Files touched:** none new (orchestrator `scripts/bulk_ingest.py` committed earlier at `4b45ccb`; cache at `c7b6dcf`). `logs/bulk_ingest_2024.log` (gitignored).

**Commit:** docs-only (this entry).

### 2026-06-04 17:20 UTC — Caching + resume; 2024 bulk paused mid-run

**Done:** Added a universal on-disk response cache to `VlrClient` (caches every successful GET under `VLR_CACHE_DIR`=`data/http_cache`, keyed by path+params; `cache=False` to bypass; atomic best-effort writes) so the downloading system fetches each endpoint at most once across stages/runs. Added `bulk_ingest --skip-matches` to resume straight into players+roster. `tests/test_vlr_client.py` (4 tests) covers hit/miss/disabled/non-success. Rahat-requested (DEVIATIONS 2026-06-04).

**2024 bulk status (PAUSED, resumable):** ran all **15/15 2024 events** through matches+details, then was paused early in player resolution. Persisted in `data/prx.db`: 436 matches, 1,105 maps, 23,401 rounds, 11,050 map_player_stats, 1,630 map_team_economy, 47 teams, 43 events. **Pending:** ~255 distinct handles still to resolve (10,230 stat rows `player_id` NULL) + roster_history. NOTE: this match data was ingested *before* the cache existed, so it's not in the cache — a resumed `--skip-matches` run will fetch the player/roster profiles fresh (and cache them).

**Resume command:** start the vlrggapi container, then
`python -m scripts.bulk_ingest --year 2024 --db data/prx.db --skip-events --skip-matches > logs/bulk_ingest_2024.log 2>&1`

**Verification:** `pytest` → **40 passed** (incl. 4 new cache tests); `compileall` clean. Cache logic proven via httpx.MockTransport (2nd identical request served from disk, no network).

**Files touched:**
- `ingestion/vlr_client.py` (modified — disk cache)
- `scripts/bulk_ingest.py` (modified — `--skip-matches`)
- `tests/test_vlr_client.py` (created)
- `.gitignore` (modified — ignore `data/http_cache/`)
- `docs/ARCHITECTURE.md` (modified — `VLR_CACHE_DIR` env), `docs/DEVIATIONS.md` (modified)

**Commit:** `c7b6dcf` — `feat(ingest): universal VlrClient response cache + bulk --skip-matches`

### 2026-06-04 16:08 UTC — P2.T8 — Roster history ingestion (from player profiles)

**Done:** Added `ingestion/roster_history.py`. The `q=transactions` endpoint is broken (no dates/roles), so rosters are built from `/v2/player` profiles: `current_team` (active, left NULL) + `past_teams[].dates` → `roster_history` rows (team by substring match, month-granularity joined/left, role='player'). Idempotent per-player rebuild. Exposes `players_on_team_at(conn, team_id, date)`. CLI: `python -m ingestion.roster_history --db data/prx.db [--player-id N]`. Added `tests/test_roster_history.py` (5 tests). All per DEVIATIONS 2026-06-04, Rahat-approved.

**Learned or surprised:** transactions `date`=real_name, `role`=tweet URL (unusable). Month regexes must anchor on real month names (not `[A-Za-z]+`) so glued 'Karmine CorpDecember 2023' splits; also hit a regex-precedence bug (alternation needs `(?:…)` wrapping). Profiles can list a team in both current + past → query uses `SELECT DISTINCT`.

**Verification:** `pytest tests/test_roster_history.py` → 5 passed (month helpers incl. leap year + year-only fallback, current/past/glued tenure extraction, idempotent rebuild, the roster-on-date query). Full suite **36 passed**. Live (seeded the 5 PRX players via real resolution, ran T8 against real profiles): **PRX roster on 2025-06-22 = [f0rsakeN, Jinggg, d4v41, something, PatMen]** — exactly the done-when; FK clean.

**Files touched:**
- `ingestion/roster_history.py` (created)
- `tests/test_roster_history.py` (created)
- `docs/DEVIATIONS.md` (modified — transactions-broken rationale)

**Commit:** `23f020d` — `phase-2.task-8: roster history from player profiles`

### 2026-06-04 15:52 UTC — P2.T7 — Player profile ingestion (resolve handles → player_id)

**Done:** Added `ingestion/players.py` — for each distinct unresolved handle in `map_player_stats`, resolves a vlr `player_id` via `/v2/search` (exact name match; ambiguous → disambiguate by team history), upserts the `/v2/player` profile into `players` (handle, real_name, country, best-effort `current_team_id` by team-name match), and backfills `map_player_stats.player_id`. CLI: `python -m ingestion.players --db data/prx.db`. Added `tests/test_players_ingestion.py` (4 tests).

**Learned or surprised:** `/v2/search` returns multiple exact-name hits (alt/fan accounts) — resolved via team-context. vlrggapi **glues date ranges onto past-team names** (`'Karmine CorpDecember 2023 – …'`), so team matching had to be substring-based (this fix turned 2 unresolved → 0). `/v2/player` `current_team` has no ID (matched by name). `/v2/player` is rate-limited (429) — the client backoff handled it (~55s wait once). All per DEVIATIONS 2026-06-04.

**Verification:** `pytest tests/test_players_ingestion.py` → 4 passed (parse, unique + team-context disambiguation, glued-name substring, unresolved, idempotency, backfill). Full suite **31 passed**. Live on match 312765's stats: **10/10 handles resolved**, 20/20 stat rows backfilled (0 NULL), all 10 players have real_name; `current_team_id` set where the team is in our DB; `foreign_key_check` clean.

**Files touched:**
- `ingestion/players.py` (created)
- `tests/test_players_ingestion.py` (created)
- `docs/DEVIATIONS.md` (modified — resolution heuristics)

**Commit:** `fc6903c` — `phase-2.task-7: player profile ingestion (resolve handles + backfill)`

### 2026-06-04 15:43 UTC — P2.T6 — Match details ingestion (maps/rounds/stats/economy)

**Done:** Added `ingestion/match_details.py` — parses `/v2/match/details` into `maps`, `rounds`, `map_player_stats`, `map_team_economy` (all idempotent upserts). Player stats are keyed by **handle** (`player_id` NULL until T7) — required a schema change to `map_player_stats` (PK `(map_id, player_handle)`, add `player_handle`, `player_id` nullable, `idx_mps_handle`), applied to both `docs/ARCHITECTURE.md` §2.3 and `ingestion/schema.py`. `is_rounds_complete=1` iff valid-round count == map score. CLI: `python -m ingestion.match_details --db data/prx.db --match-id N`. Added `tests/test_match_details.py` (9 tests).

**Learned or surprised:** No player IDs anywhere in the detail → handle-keyed capture (DEVIATIONS 2026-06-04, Rahat-approved schema change). `picked_by` is the literal `"PICK"` → `picked_by_team_id` NULL. Economy is 5 buckets as `"total (won)"`; mapped to the 4 schema pct columns (the `$` semi-eco bucket dropped). OT per-side scores dropped (no schema column).

**Verification:** `pytest tests/test_match_details.py` → 9 passed; full suite **27 passed**. Live end-to-end (re-inited DB → events → matches[1921] → details[312765]): match 312765 → 2 maps, 44 rounds, 20 player_stats, 4 economy, both maps complete; `foreign_key_check` clean; map Icebox 13-8 (ct 7/t 6, 3591s, winner 8877); stat N4RRATE/Gekko acs 281/kast 67/hs 32/rating 1.47 with `player_id` NULL; economy 50/33/40/77; idempotent on rerun.

**Files touched:**
- `ingestion/match_details.py` (created)
- `ingestion/schema.py` (modified — map_player_stats re-keyed)
- `docs/ARCHITECTURE.md` (modified — §2.3 schema change)
- `tests/test_match_details.py` (created)
- `docs/DEVIATIONS.md` (modified — schema change + parsing decisions)

**Commit:** `1a5fa01` — `phase-2.task-6: match details ingestion (maps/rounds/stats/economy)`

### 2026-06-04 15:31 UTC — P2.T5 — Matches ingestion (per event)

**Done:** Added `ingestion/matches.py`. Since `/v2/events/matches` lacks numeric team IDs and format, it enumerates a match list per event then fetches `/v2/match/details` per *completed* match for `teams[].id`, scores, winner; infers `format` from the winning score; auto-upserts the two referenced teams (preserving any existing country/region); parses `date_utc` to ISO date; leaves `patch_id` NULL (T13). CLI: `python -m ingestion.matches --db data/prx.db [--event-id N]`. Added `tests/test_matches_ingestion.py` (5 tests, no network).

**Learned or surprised:** numeric team IDs live only in match/details; no endpoint gives Bo-format → inferred from score (DEVIATIONS 2026-06-04, Rahat-approved). match/details `data.segments` is a **list** (vs the event-detail dict). Match upsert had to preserve country/region or it would NULL out PRX's `sg`.

**Verification:** `pytest tests/test_matches_ingestion.py` → 5 passed (format infer, date parse, row build, idempotency + completed-only skip, country preserved). Full suite 18 passed. Live on Masters Madrid (1921): **17 matches** upserted, teams auto-grew 2→10, formats Bo3×14/Bo5×2/Bo1×1, PRX `country` still `sg`, `PRAGMA foreign_key_check` clean, idempotent on rerun. **Full 800–1,500 population is deferred to the bulk runs (T9–T11).**

**Files touched:**
- `ingestion/matches.py` (created)
- `tests/test_matches_ingestion.py` (created)
- `docs/DEVIATIONS.md` (modified — match/details rationale)

**Commit:** `cabcce3` — `phase-2.task-5: matches ingestion (per event via match/details)`

### 2026-06-04 15:18 UTC — P2.T4 — Events ingestion (curated tier-1 registry)

**Done:** Added `ingestion/tier1_events.py` — a curated registry of 45 tier-1 vlr event IDs (all Masters/Champions + all four leagues' Kickoff/Stage 1/Stage 2, 2024–2026), each tagged with our tier/region classification (verified against SPEC §4). Added `ingestion/events.py` — fetches `/v2/event/{id}`, parses `dates`→(start,end ISO) and `prize`→int, combines with the registry, and upserts into `events` (idempotent). CLI `python -m ingestion.events --db data/prx.db`. Added `tests/test_events_ingestion.py` (10 tests, no network).

**Learned or surprised:** `/v2/events` list can't classify tier-1 (paginated/recent-first, country-code region, year-less dates, no tier) and `/v2/search` is fuzzy → curated registry instead (DEVIATIONS 2026-06-04, Rahat-approved). `/v2/event/{id}`'s `data.segments` is a **dict** (not a list). `dates` has two formats — compact `"Mar 14 - 24, 2024"` and full `"Feb 16, 2024 - Apr 6, 2024"` (+ en-dash/cross-year variants); the parser handles both and cleanly skips unscheduled `"… – TBD"` events.

**Verification:** `pytest tests/test_events_ingestion.py` → 10 passed (prize/date parsing incl. full/cross-year/TBD, classification, idempotency, skip). Full suite 13 passed. Live: `python -m ingestion.events` → **43/45 upserted** (2 skipped = 2026 Americas/China Stage 2, dates still TBD). All 9 Masters/Champions present with SPEC-correct dates (Madrid 2024 $500k → London 2026); Masters Toronto 2025 (2282) present. Distribution: Masters 6, Champions 3, Kickoff 12, RegionalLeague 22; regions global 9, na 8, emea 9, pac 9, cn 8.

**Files touched:**
- `ingestion/tier1_events.py` (created — the registry)
- `ingestion/events.py` (created)
- `tests/test_events_ingestion.py` (created)
- `docs/DEVIATIONS.md` (modified — curated-registry rationale)

**Commit:** `6450143` — `phase-2.task-4: events ingestion (curated tier-1 registry)`

### 2026-06-04 14:59 UTC — CI fix — install runtime deps for ingestion tests

**Done:** The Phase-1 CI job only installed `pytest`, so P2.T3's `tests/test_teams_ingestion.py` (which imports `ingestion.teams` → `httpx`/`structlog`) failed collection on GitHub Actions with `ModuleNotFoundError: structlog`. Changed `.github/workflows/ci.yml`'s install step to `pytest httpx structlog`. To expand when modeling tests land (Phase 3 needs pandas/bambi/etc.).

**Verification:** Ran the exact CI commands locally — `compileall -q . -x 'vendor/.*'` clean; `pytest -q` → 3 passed.

**Files touched:**
- `.github/workflows/ci.yml` (modified — install test deps)

**Commit:** `e5cd953` — `ci: install httpx+structlog so ingestion tests import`

### 2026-06-04 14:55 UTC — P2.T3 — Teams ingestion (idempotent)

**Done:** Added `ingestion/teams.py` — `parse_team(segment)` (maps a `/v2/team` profile to a `teams` row), `upsert_team(conn, row)` (SQLite `ON CONFLICT(team_id) DO UPDATE`), and `ingest_teams(team_ids, db_path, *, client=None)` (async; opens a `VlrClient` if none given). CLI: `python -m ingestion.teams 624 2 --db data/prx.db`. Added `tests/test_teams_ingestion.py` (3 tests, no network — a FakeClient feeds canned segments).

**Learned or surprised:** `/v2/team` exposes no `region` → `teams.region` left NULL, backfill later (DEVIATIONS 2026-06-04). Tests use `asyncio.run` inside sync test fns, so no `pytest-asyncio` dependency needed.

**Verification:** `pytest tests/test_teams_ingestion.py` → 3 passed (parse mapping; idempotency — ingest twice, count stays 2; missing team skipped). Live against a real container: `python -m ingestion.teams 624 2 --db data/prx.db` → PRX (624, Paper Rex, PRX, sg) and Sentinels (2) upserted; rerun keeps count at 2.

**Files touched:**
- `ingestion/teams.py` (created)
- `tests/test_teams_ingestion.py` (created)
- `docs/DEVIATIONS.md` (modified — region-not-in-profile entry)

**Commit:** `9f8136f` — `phase-2.task-3: teams ingestion (idempotent upsert)`

### 2026-06-04 14:49 UTC — P2.T2 — Base HTTP client for vlrggapi

**Done:** Added `ingestion/vlr_client.py` — an async `VlrClient` (async context manager over `httpx.AsyncClient`). Reads base URL from `VLRGGAPI_URL` (default `http://localhost:3001`); `get_json(path, **params)` returns the full v2 envelope, `get_segments(...)` unwraps `data.segments` after asserting `status == "success"`. Retries transport errors and HTTP 5xx with exponential backoff (0.5s×2ⁿ, 3 attempts), sleeps on 429 honouring `Retry-After`, raises `VlrApiError` on non-retryable 4xx or exhaustion. structlog logging throughout.

**Learned or surprised:** FastAPI returns a real 404 for unknown routes (not a success envelope), so 4xx correctly raises immediately. httpx `RequestError` is the right catch-all for transport+timeout retries.

**Verification:** Re-expressed the P1.T3 smoke checks through the client against a live `vlrggapi:vendored` container → **5/5 pass** (health, PRX profile, `q=matches`, results→match/details with maps, live_score). Error paths confirmed: 404 → immediate `VlrApiError`; unreachable host → 2 retries (backoff 0.5s, 1.0s) then `VlrApiError`. `compileall ingestion` clean.

**Files touched:**
- `ingestion/vlr_client.py` (created)

**Commit:** `4578220` — `phase-2.task-2: base async HTTP client for vlrggapi`

### 2026-06-04 14:44 UTC — P2.T1 — Implement SQLite schema

**Done:** Added `ingestion/schema.py` — the full warehouse DDL from ARCHITECTURE.md §2 (16 tables + 11 indexes), with `init_db(path)` (idempotent via `IF NOT EXISTS`), `list_tables(path)`, and an `init <db_path>` CLI. Added a `.gitignore` rule so the generated `data/*.db` warehouse (+ journal/wal/shm) is never committed.

**Learned or surprised:** `data/prx.db` was not previously gitignored — added a rule before creating it. Used `IF NOT EXISTS` so re-running init is a safe no-op (ARCHITECTURE's DDL has no such clause; this is an additive safety, not a schema change). Started directly on `main` per the new no-branches workflow.

**Verification:** `python -m ingestion.schema init data/prx.db` → "Initialized … with 16 tables" (all expected: teams, players, roster_history, events, patches, matches, maps, rounds, map_player_stats, map_team_economy, elo_ratings, elo_map_offsets, player_skill, score_state_lookup, live_state, live_predictions). Re-run idempotent. `PRAGMA foreign_key_check` empty (OK); 11 `idx_*` indexes present. `git check-ignore data/prx.db` confirms the DB is ignored.

**Files touched:**
- `ingestion/schema.py` (created)
- `.gitignore` (modified — ignore `data/*.db*`)

**Commit:** `a2ff555` — `phase-2.task-1: implement SQLite schema`

### 2026-06-04 13:05 UTC — P1.T8 — Phase 1 summary + merge to main + tag

**Done:** Wrote the Phase 1 summary (see "Phase summaries" above), updated Current state. Merged `phase-1-vlrggapi-setup` → `main` and tagged `v0.1.0-phase-1`; pushed main + tag to origin. Phase 1 is complete; Phase 0 validation stays deferred.

**Verification:** CI green through `372734b`. Summary commit `6f1a0f9` on `phase-1-vlrggapi-setup`; merged to `main` via `4cc900a` (`--no-ff`); tagged `v0.1.0-phase-1` on main.

**Files touched:**
- `docs/PROGRESS.md` (summary + current state + this entry)

**Commit:** `6f1a0f9` — `phase-1.task-8: phase 1 summary + tag v0.1.0-phase-1` (merge `4cc900a`)

### 2026-06-04 12:55 UTC — P1.T7 — Combined docker-compose dry-run

**Done:** Wrote `docker/docker-compose.yml` with two services — `vlrggapi` (built from the vendored submodule, internal-only `expose: 3001`) and `prx-app` (FastAPI hello-world stub, host `:8000`) — networked via compose's default network with `VLRGGAPI_URL=http://vlrggapi:3001`. Turned the `docker/Dockerfile` into the hello-world (installs fastapi+uvicorn, runs `app_stub:app`); the stub app lives in `docker/app_stub.py` (kept out of `api/` so Phase 6 stays clean). Added a repo-root `.dockerignore` so the prx-app build context (= repo root) excludes `.git`, `vendor`, `data`, etc.

**Learned or surprised:** `python:3.11-slim` has no `curl`, so the inter-container check uses `python -c urllib` instead. Compose auto-names containers (`docker-vlrggapi-1`/`docker-prx-app-1`) — fine since the service name `vlrggapi` is what DNS resolves for `http://vlrggapi:3001`. Stopped the standalone P1.T2 `vlrggapi` container first to avoid confusion.

**Verification:** `docker compose -f docker/docker-compose.yml up -d --build` → both Up (vlrggapi healthy). **From inside prx-app: `http://vlrggapi:3001/v2/health` → `status=success`** (done-when met). Host `:8000/` → hello; `:8000/vlrggapi-health` → `reached:true`, upstream Healthy. Stack torn down (`compose down`) to leave a clean state.

**Files touched:**
- `docker/docker-compose.yml` (created)
- `docker/Dockerfile` (modified — minimal stub → FastAPI hello-world)
- `docker/app_stub.py` (created)
- `.dockerignore` (created)

**Commit:** `<pending>` — `phase-1.task-7: docker-compose dry-run (prx-app <-> vlrggapi)`

### 2026-06-04 12:40 UTC — Secret hygiene (Rahat request; repo stays public)

**Done:** Rahat chose to keep the repo public. Hardened `.gitignore` to ignore `.env` + all `.env.*` (keeping `!.env.example`), and added `.env.example` with placeholders only (`VLRGGAPI_URL`, empty `DEEPSEEK_API_KEY`). Resolves the public-vs-private flag from P1.T6.

**Verification:** `git check-ignore` → `.env`, `.env.local`, `.env.production` all ignored; `.env.example` tracked. A test `.env` containing a fake key was invisible to `git status`.

**Files touched:**
- `.gitignore` (modified — `.env.*` + `!.env.example`)
- `.env.example` (created)
- `docs/DEVIATIONS.md` (modified — resolution entry)

**Commit:** `<pending>` — `chore: secret hygiene — gitignore .env*, add .env.example`

### 2026-06-04 12:30 UTC — P1.T6 — CI workflow stub

**Done:** Added `.github/workflows/ci.yml` (Python 3.11 syntax check via `compileall`, pytest placeholder, build `docker/Dockerfile` with no push) on `main` + `phase-*` + PRs + manual dispatch. Added minimal `docker/Dockerfile` stub (`FROM python:3.11-slim`, `COPY requirements.txt`). Pre-validated all three steps locally before pushing.

**Learned or surprised:** Two gotchas caught locally: (1) bare `pytest` at repo root collects the **vendored vlrggapi submodule's tests** (import-fail, no fastapi in our env) — fixed with a 3-line `pytest.ini` (`testpaths = tests`, `--ignore=vendor`); a small addition beyond T6's literal touch list but needed for correctness. (2) pytest exits **5** ("no tests collected") which fails CI, so the workflow treats exit 5 as pass (`pytest -q || [ $? -eq 5 ]`).

**Verification:** Local — `compileall` exit 0; `pytest` exit 5 → guard PASS; `docker build` success. **GitHub Actions CI run for `2ebe2de` → completed, conclusion `success`** (confirmed via Actions API). Done-when met.

**FLAG (not part of T6):** Actions API was readable unauthenticated → repo `sleipnir029/choochootrain` is **public** (`private: false`), but SPEC expected **private**. See DEVIATIONS 2026-06-04. Rahat to decide whether to flip visibility.

**Files touched:**
- `.github/workflows/ci.yml` (created)
- `docker/Dockerfile` (created — replaces the `.gitkeep`)
- `pytest.ini` (created — scope pytest to our tests/)

**Commit:** `2ebe2de` — `phase-1.task-6: CI workflow stub`

### 2026-06-04 12:18 UTC — P1.T5 — GitHub repo + initial push

**Done:** The GitHub remote already existed (`origin` → `https://github.com/sleipnir029/choochootrain.git`) with `main` pushed (initial commit), so no repo creation was needed. Per Rahat, pushed both feature branches so the work is backed up: `phase-0-peng-bootstrap` and `phase-1-vlrggapi-setup` are now on origin and tracking. `main` left untouched (merge happens at phase-end per git hygiene).

**Learned or surprised:** Repo is named **choochootrain**, not the SPEC/TASKS placeholder "prx-predictor" — keeping the existing name (matches the working dir). `gh` CLI is not installed, so repo **visibility (private?) could not be verified programmatically** — Rahat to confirm the repo is private if that matters (SPEC §P1.T5 expected private).

**Verification:** `git push -u origin <branch>` succeeded for both branches (`* [new branch]` + tracking set). `git branch -a` shows both `remotes/origin/phase-0-...` and `remotes/origin/phase-1-...`.

**Files touched:**
- none (git remote operations only)

**Commit:** `<pending>` — docs only

### 2026-06-04 12:12 UTC — P1.T4 — Initialize project repo skeleton

**Done:** Created the folder structure from CLAUDE.md's repo layout. Python-package dirs (`ingestion/ models/ api/ scheduler/ llm/ tests/`) got empty `__init__.py`; non-Python dirs (`notebooks/ dashboard/ docker/ .github/workflows/`) got `.gitkeep`. `LICENSE` (MIT), `README.md`, `.gitignore`, `data/` already existed from earlier tasks — left as-is. No source files created (those belong to Phase 2+).

**Learned or surprised:** Nothing notable. Kept placeholders truly empty to respect the "don't pre-create files for future phases" failure mode while still satisfying the skeleton task.

**Verification:** All 10 target dirs present; `git status` clean except the 10 staged placeholders and the intentionally-untracked `Data.java` reference.

**Files touched:**
- `ingestion/__init__.py`, `models/__init__.py`, `api/__init__.py`, `scheduler/__init__.py`, `llm/__init__.py`, `tests/__init__.py` (created, empty)
- `notebooks/.gitkeep`, `dashboard/.gitkeep`, `docker/.gitkeep`, `.github/workflows/.gitkeep` (created)

**Commit:** `<pending>` — `phase-1.task-4: initialize project repo skeleton`

### 2026-06-04 12:05 UTC — P1.T3 — Smoke-test the endpoints we'll rely on

**Done:** Wrote `scripts/smoke_vlrggapi.py` (stdlib-only ad-hoc tester, base URL from `VLRGGAPI_URL`) hitting the four endpoints ingestion will use and asserting the fields we depend on. All 4 pass against the running container: PRX profile (id 624 → "Paper Rex"), team match history (50 rows, latest 666493), match details for 666493 (3 maps + economy + head_to_head), and live_score (4 matches live, full round-state fields).

**Learned or surprised:** The pinned upstream has **no** `/v2/team/matches` or `/v2/team/transactions` paths — they're `q=matches` / `q=transactions` variants on `/v2/team` (the docs assume separate paths). Logged in DEVIATIONS for Phase 2. Cosmetic only: non-ASCII live team names mojibake in the Windows console on `print` (data itself is fine UTF-8).

**Verification:** `python scripts/smoke_vlrggapi.py` → "4/4 checks passed.", exit 0.

**Files touched:**
- `scripts/smoke_vlrggapi.py` (created)
- `docs/DEVIATIONS.md` (modified — route-shape entry)

**Commit:** `<pending>` — `phase-1.task-3: smoke-test vlrggapi endpoints`

### 2026-06-04 11:52 UTC — P1.T2 — Build vlrggapi Docker image locally

**Done:** Built the vlrggapi image from the vendored source (`docker build -t vlrggapi:a6075fe vendor/vlrggapi`, 186MB) and ran it (`docker run -d --name vlrggapi -p 3001:3001`). `/v2/health` returns `{"status":"success", service: Healthy, http_client: Healthy}` — both vlrggapi and its vlr.gg upstream reachability are healthy. Container shows `Up (healthy)` via Docker's own healthcheck. No repo files changed (upstream provides the Dockerfile).

**Learned or surprised:** Upstream's Dockerfile is on `python:3.14.5-alpine` (multi-stage, uv-based), not the 3.11 the SPEC assumed — logged as a minor deviation (no impact on our app; vlrggapi is HTTP-isolated). Build was fast (~Alpine + uv).

**Verification:** `docker ps` → `vlrggapi Up (healthy) 0.0.0.0:3001->3001`. `curl http://localhost:3001/v2/health` → `status: success`, service + http_client both Healthy. **NOTE: the container is left running** for P1.T3 (endpoint smoke tests); stop with `docker rm -f vlrggapi` if needed.

**Files touched:**
- none (image/container are runtime artifacts, not committed)
- `docs/DEVIATIONS.md` (modified — Python 3.14 note)

**Commit:** `<pending>` — docs only (P1.T2 builds no repo files)

### 2026-06-04 11:45 UTC — P1.T1 — Vendor vlrggapi

**Done:** Added upstream vlrggapi (axsddlr/vlrggapi, Python, branch `master`) as a git submodule at `vendor/vlrggapi`, pinned to commit `a6075fec` (master tip, pushed 2026-06-04). Recorded provenance + update instructions in `vendor/VERSION.txt`. Verified the vendored source is complete and buildable: it contains `Dockerfile`, `docker-compose.yml`, `main.py`, `requirements.txt`, and `api/ routers/ models/ utils/ tests/` — everything P1.T2 needs.

**Learned or surprised:** Submodule describes as `1.0.5-366-ga6075fe` (366 commits past the 1.0.5 tag), so upstream is well ahead of its last release tag — pinning to a SHA (not the tag) is the right call.

**Verification:** `git submodule status` → ` a6075fec... vendor/vlrggapi (1.0.5-366-ga6075fe)`. `git -C vendor/vlrggapi rev-parse HEAD` matches the pinned SHA. `ls vendor/vlrggapi/Dockerfile` exists.

**Files touched:**
- `.gitmodules` (created)
- `vendor/vlrggapi` (submodule gitlink, pinned `a6075fec`)
- `vendor/VERSION.txt` (created)

**Commit:** `db09a6b` — `phase-1.task-1: vendor vlrggapi as submodule pinned to a6075fe`

### 2026-06-04 11:38 UTC — P0.T2 — Deferred (Peng dataset unobtainable); reordering to Phase 1

**Done:** Did not download the Peng dataset — it's behind a paid IEEE DataPort subscription with no free download. Investigated alternatives with Rahat: no free source has Peng's ultimate features (vlr.gg never exposed them; the author hand-charted them). A reference parser `Data.java` was added to the repo root but its raw input `VCT Data.csv` isn't available. vlr.gg does expose per-round loadout values (a loadout-only model is feasible later). Per Rahat's decision, **deferred Phase 0 validation (T2–T6) and pulled Phase 1 forward**. Created `data/external/` (gitignored) as the eventual drop-in. Full reasoning in DEVIATIONS.md.

**Learned or surprised:** The Peng dataset's value is precisely the hand-charted per-round ultimate economy — unrecoverable from any free/automated source. Our eventual Phase 0 validation will be loadout-only (1-feature), not Peng's 3-feature model.

**Verification:** Confirmed IEEE paywall (dataset page: "LOGIN TO ACCESS DATASET FILES", paid subscription). Confirmed via vlr.gg economy tab that per-round numeric loadout values exist (e.g. "5.5k", "13.3k") and round winners are recoverable from the round-result strip. Public vlrggapi healthy (`/health` → Healthy).

**Files touched:**
- `data/external/.gitkeep` (created)
- `.gitignore` (modified — ignore `data/external/*` except `.gitkeep`)
- `docs/DEVIATIONS.md` (modified — reorder entry)
- `Data.java` (added at repo root by Rahat as reference; left untracked)

**Commit:** `552a7b2` — `phase-0.task-2: defer (peng dataset unobtainable), reorder to phase 1`

### 2026-06-04 10:54 UTC — P0.T1 — Bootstrap Python environment

**Done:** Declared the 9 Phase-0 packages (pandas, numpy, scikit-learn, statsmodels, bambi, marimo, pytest, structlog, httpx) in `requirements.txt` with exact top-level pins, and committed a full `pip freeze` (`requirements.lock.txt`, 80 deps) for reproducible installs. Installed into the existing conda env `choochoo` (Python 3.11.15) via pip — per Rahat, we reuse `choochoo` rather than a fresh `python -m venv`. Added `.python-version` (`3.11`) and a setup blurb to `README.md`.

**Learned or surprised:** Resolver pulled a very recent stack — numpy 2.4.6, pandas 3.0.3, bambi 0.17.2 (→ pymc 5.28.5, pytensor 2.38.3), marimo 0.23.8 — with no conflicts. matplotlib (3.10.9) came in transitively via arviz, so no need to name it explicitly. Caveat for later: the lock is a Windows freeze; the Phase 1 `python:3.11-slim` (Linux) Docker build may resolve some wheels (esp. pytensor) differently — revisit lock strategy at the Docker step, don't assume verbatim reinstall.

**Verification:** `pip install -r requirements.txt` completed with no resolver conflicts. `python -c "import bambi, marimo, pandas, numpy, sklearn, statsmodels, pytest, structlog, httpx, matplotlib"` → `imports ok`. `pip check` → `No broken requirements found.`

**Files touched:**
- `requirements.txt` (created)
- `requirements.lock.txt` (created)
- `.python-version` (created)
- `README.md` (modified)

**Commit:** `bdd8d4c` — `phase-0.task-1: bootstrap python environment`

---

## Entry template (copy this for new entries)

```
### YYYY-MM-DD HH:MM UTC — P{phase}.T{task} — <short title>

**Done:** <2-3 sentences on what was implemented>

**Learned or surprised:** <anything non-obvious; leave blank if nothing>

**Verification:** <what you ran to confirm the task is done; output snippets if useful>

**Files touched:**
- `path/to/file1.py` (created)
- `path/to/file2.py` (modified)

**Commit:** `<short SHA>` — `phase-X.task-Y: <message>`
```

---

## Phase summary template (copy this for each phase summary)

```
### Phase {X} — <name>

**Built:** <bulleted list of artifacts produced>

**What works:** <verified behaviors>

**What's pending or deferred:** <anything punted to later phases; reference DEVIATIONS.md if relevant>

**Numbers** (if applicable): <accuracy, row counts, latency, etc.>

**Surprises:** <anything that didn't go as the SPEC predicted>

**Next phase prep:** <if anything needs to be ready before the next phase starts>
```
