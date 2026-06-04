# DEVIATIONS.md

Tracks places where implementation deviates from `PRX_PREDICTOR_SPEC.md` or `docs/ARCHITECTURE.md`. Every deviation needs an entry with reasoning, so we can trace back why a choice was made.

---

## When to add a deviation entry

Add an entry HERE before making the change, when implementation:
- Contradicts something stated in the SPEC
- Requires a schema change (any DDL not in ARCHITECTURE.md)
- Requires a different library than the one in CLAUDE.md's tech stack
- Changes user-visible UX in a non-trivial way
- Discovers that vlrggapi or another upstream behaves differently than expected
- Punts a feature documented in the SPEC to a later phase

For trivial fixes (typos in comments, version bumps to patch releases, file renames within a module), don't bother — keep this file signal, not noise.

---

## Approval gates

- **Minor deviation** (single function, no schema change, no user-visible effect): log entry, proceed
- **Material deviation** (schema, library, UX, significant scope change): log entry, **stop and ask Rahat** before proceeding

If unsure which category applies, treat it as material and ask.

---

## Entry format

```
### YYYY-MM-DD — <short title>

**Phase / Task:** P{X}.T{Y}

**Spec said:**
<quote or paraphrase the relevant SPEC or ARCHITECTURE section>

**What was actually done:**
<what the implementation does instead>

**Why:**
<the discovery that forced the change — be specific>

**Impact:**
<does this affect other phases? schema? UI? performance?>

**Rahat approval:** yes / no / N/A (N/A only for minor deviations)

**Related commit:** `<short SHA>`
```

---

## Entries

*Newest at top. Don't edit old entries.*

### 2026-06-04 — Ingestion validation anomalies (P2.T12): showmatch + unresolved handles

**Phase / Task:** P2.T12

**Spec said:**
P2.T12: validation checks every match has >=1 map, every map has player_stats, rounds-completeness per year; note anomalies here.

**What was actually done / found (2024 data):**
`scripts/validate_ingestion.py` reports: 436 matches, 1,105 maps, 23,401 rounds, **100% rounds-complete maps**, 0 maps missing stats, 0 NULL winners, FK clean. Two benign anomalies:
- **1 match with 0 maps — `match_id=321373`**, a "Showmatch: Showmatch" at Masters Madrid 2024 (ad-hoc all-star teams 15315/15316). Showmatches come through `/v2/events/matches` but have no competitive map data. Harmless for map-level modelling; flagged in case showmatches should be filtered from `matches` later.
- **4 of 11,050 map_player_stats rows have NULL player_id** (handles `EQ118`, `dank1ng`, `spicyuuu`, `zhang yanqi` — no exact `/v2/search` match; likely CN subs/stand-ins). Left NULL by design (P2.T7 policy).

`matches.patch_id` is NULL for all 436 (expected; populated by P2.T13).

**Impact:** none requiring action now. Consider excluding `series_name LIKE 'Showmatch%'` from competitive aggregates in Phase 3.

**Rahat approval:** N/A (informational data-quality findings).

**Related commit:** `<this commit>`

### 2026-06-04 — Universal on-disk response cache in VlrClient

**Phase / Task:** P2.T9 (infrastructure; affects all ingestion)

**Spec said:**
ARCHITECTURE.md §4.2 lists env config but specifies no HTTP caching layer.

**What was actually done (Rahat-requested):**
Added a disk cache to `VlrClient.get_json` — the single chokepoint every download goes through. Each **successful** GET is written to `VLR_CACHE_DIR` (default `data/http_cache`, gitignored) keyed by `sha256(path?sorted(params))`; subsequent identical requests are served from disk with no network call. Enabled by default; `VlrClient(cache=False)` bypasses it (for volatile endpoints like the Phase-5 live poller). Cache writes are atomic (temp + rename), best-effort (never fatal), and only success envelopes are cached (errors/empties are not). Added `VLR_CACHE_DIR` to ARCHITECTURE §4.2. Also added `bulk_ingest --skip-matches` so a resumed run skips the already-ingested match phases and runs only players + roster.

**Why:**
The bulk pulls make thousands of heavily rate-limited (`429`) calls; without caching, every pause/resume or re-run re-fetches the same static historical data, wasting hours and keeping the container resident. Caching makes the downloading system fetch any endpoint at most once.

**Impact:**
Pause/resume is now cheap and safe; re-runs are near-instant for already-fetched endpoints. Cache is a rebuildable artifact (delete `data/http_cache/` to force refresh). Volatile/live endpoints must opt out with `cache=False` when those features are built.

**Rahat approval:** yes (requested: "introduce caching … universal rule for all of the downloading system").

**Related commit:** `<this commit>`

### 2026-06-04 — roster_history built from player profiles (transactions endpoint broken)

**Phase / Task:** P2.T8

**Spec said:**
TASKS.md P2.T8: "for each tier-1 team, fetches `/v2/team/transactions`, parses into `roster_history` rows. Handles open-ended (left_date=NULL)."

**What was actually done (Rahat-approved):**
`/v2/team?id=...&q=transactions` is **broken** in the pinned upstream — its `date` field contains the player's *real name* and `role` contains a *tweet URL*; there is no transaction date and no role (only `player{name,id,country}` + `action`). So `ingestion/roster_history.py` reconstructs rosters from **player profiles** instead: it iterates players in the DB, parses each `/v2/player` `current_team` (active, `left_date=NULL`) + `past_teams[].dates` into `roster_history` rows.

**Decisions baked in:**
- Dates are **month-granularity** → `joined_date` = first of month, `left_date` = last of month.
- `role` defaults to **'player'** (profiles give no per-tenure role) → coaches/staff are not captured.
- Team resolved by **substring match** against tracked teams (vlrggapi glues date ranges onto team names, e.g. 'Karmine CorpDecember 2023…'); month regexes are anchored on real month names so the glued boundary parses.
- Only tenures on a **tracked (tier-1) team** are kept; undated tenures skipped (`joined_date` NOT NULL).
- Idempotent via per-player delete+rebuild (`roster_history` has no natural unique key).
- A player can yield duplicate overlapping PRX rows (profile lists a team in both current + past); `players_on_team_at()` uses `SELECT DISTINCT`.

**Impact:**
Done-when met: PRX roster on 2025-06-22 = f0rsakeN, Jinggg, d4v41, something, PatMen. Non-player staff rosters are out of scope until a dated source exists. Helper `players_on_team_at(conn, team_id, date)` is reusable by later phases (team_id_at_match sanity, features).

**Rahat approval:** yes (build from player-profile tenures).

**Related commit:** `<this commit>`

### 2026-06-04 — Player handle→ID resolution heuristics (P2.T7)

**Phase / Task:** P2.T7

**Spec said:**
TASKS.md P2.T7: "extracts player_ids from `map_player_stats`, fetches `/v2/player?id={id}` for each." (Assumed IDs already present.)

**What was actually done:**
Since `map_player_stats` holds handles, not IDs (P2.T6 schema change), `ingestion/players.py` resolves each distinct unresolved handle via `/v2/search`:
- exactly one exact (case-insensitive) name match → use it;
- several (alt/fan/dup accounts are common) → fetch each candidate's `/v2/player` and pick the one whose **team history matches a team the handle actually played for** (from `map_player_stats.team_id_at_match`); 0 or >1 matches → leave `player_id` NULL and **log** (correctness over recall).

Two wrinkles found and handled:
- vlrggapi **glues the date range onto past-team names** (e.g. `'Karmine CorpDecember 2023 – November 2024'`), so team matching is by **substring**, not equality (this initially left 2/10 handles unresolved on the test match).
- `/v2/player`'s `current_team` has **no ID** → `players.current_team_id` is matched by team **name** against the `teams` table (NULL if absent/ambiguous; so it's NULL for players whose current team isn't a tier-1 team we've ingested).
Also observed: `/v2/player`/`/v2/search` are **rate-limited** (HTTP 429); the VlrClient backoff handles it (waited ~55s once) — relevant for the bulk runs.

**Impact:**
On the verification match (312765) all 10 handles resolved (after the substring fix) with real names + countries. Unresolved handles in the full bulk will be logged and remain `player_id=NULL` until handled.

**Rahat approval:** N/A (implementation detail within the approved T6/T7 approach).

**Related commit:** `<this commit>`

### 2026-06-04 — map_player_stats keyed by handle; economy buckets mapped; schema change

**Phase / Task:** P2.T6 (schema change — affects P2.T7, Phase 4)

**Spec said:**
ARCHITECTURE.md §2.3 `map_player_stats` PK `(map_id, player_id)`, `player_id` NOT NULL FK. P2.T6 populates maps/rounds/map_player_stats/map_team_economy from `/v2/match/details`.

**What was actually done (Rahat-approved schema change):**
`/v2/match/details` exposes player **handles**, not numeric IDs (no ID in `players`, `performance.kill_matrix`, or `advanced_stats`). So `map_player_stats` is re-keyed: **PK `(map_id, player_handle)`, new `player_handle` column, `player_id` now nullable** (backfilled in P2.T7 by resolving handles → vlr IDs). Updated both `docs/ARCHITECTURE.md` §2.3 and `ingestion/schema.py`; added `idx_mps_handle`.

Other P2.T6 parsing decisions (informational):
- `maps.picked_by_team_id` left **NULL** — the detail's `picked_by` is the literal string `"PICK"`, not a team.
- `is_rounds_complete = 1` iff count of valid rounds (winner∈team1/team2, side∈ct/t) equals `team1_score+team2_score`; the rounds array contains empty placeholders that are filtered.
- `rounds.half` derived from round number (1–12 first, 13–24 second, 25+ ot); `team1_side` = detail's per-round `side`, `team2_side` = its opposite.
- **OT** per-side scores are dropped (schema has only ct/t columns; `score_ot` ignored).
- **Economy**: vlr exposes 5 buckets (pistol, eco, $, $$, $$$) as `"total (won)"`; the schema has 4 pct columns, so `pistol_win_pct`=won/2, `eco_win_pct`←eco, `semi_buy_win_pct`←`$$`, `full_buy_win_pct`←`$$$`; the `$` (semi-eco) bucket is **dropped**.

**Why:**
Player numeric IDs are simply absent from the match detail; resolving every stat row via fuzzy `/v2/search` during the bulk would be slow and error-prone. Capturing by handle now and resolving unique handles once in T7 is more robust.

**Impact:**
- P2.T7 changes from "extract player_ids from map_player_stats" to "resolve distinct handles → player_id, upsert players, backfill `map_player_stats.player_id`".
- Phase 4 (player skill) should join on `player_id` once backfilled (or handle pre-backfill).
- `init_db` on an existing pre-change DB won't migrate (IF NOT EXISTS) — drop/recreate `data/prx.db` (done; it's a rebuildable artifact).

**Rahat approval:** yes (capture by handle, resolve IDs in T7).

**Related commit:** `<this commit>`

### 2026-06-04 — Matches require /v2/match/details (team IDs + format not in /v2/events/matches)

**Phase / Task:** P2.T5

**Spec said:**
TASKS.md P2.T5: "for each event in events table, fetches `/v2/events/matches?event_id={id}`, upserts into matches table. Handles missing optional fields gracefully."

**What was actually done:**
`/v2/events/matches` only returns team **names** + scores + `is_winner` + `event_series` + url — **no numeric team IDs** and **no format**, but `matches` needs numeric `team1_id/team2_id` (FK) and `format` NOT NULL. So `ingestion/matches.py` uses `/v2/events/matches` to enumerate match_ids per event, then fetches `/v2/match/details` per *completed* match (its `teams[].id` are numeric), and:
- infers `format` from the winning score (2→Bo3, 3→Bo5, 1→Bo1);
- **auto-upserts the two teams** referenced by each match (id/name/tag/logo), with an upsert that **preserves** any existing `country`/`region` (so ingestion.teams' richer data isn't clobbered);
- parses `date_utc` to an ISO **date** (time/timezone dropped);
- leaves `patch_id` NULL (P2.T13 backfills from date);
- ingests **completed matches only** (unplayed matches have no scores; `team*_score` is NOT NULL).

**Why:**
Confirmed by probing both endpoints: numeric team IDs exist only in `/v2/match/details`; no endpoint returns Bo-format directly. Rahat approved fetching match/details per match and re-fetching it again in P2.T6 (no shared cache for now).

**Impact:**
- T5 and T6 both call `/v2/match/details` (~2× detail requests across the bulk runs); acceptable for the one-time T9–T11 pulls.
- The `teams` table is populated as a side effect of match ingestion (region/country stay NULL for teams only seen here).
- **Full 800–1,500 row population happens in the bulk runs (T9–T11)**; T5 itself was verified on one event (Masters Madrid 2024 → 17 matches, teams 2→10, FK clean, idempotent).

**Rahat approval:** yes (fetch match/details per match; re-fetch in T6).

**Related commit:** `<this commit>`

### 2026-06-04 — Events sourced from a curated ID registry, not by filtering /v2/events

**Phase / Task:** P2.T4

**Spec said:**
TASKS.md P2.T4: "fetches `/v2/events` (both `q=upcoming` and `q=completed`), filters to tier-1 (Masters, Champions, Regional League Kickoff/Stage 1/Stage 2 from 2024–present), upserts." Implies the list endpoint is filterable by tier.

**What was actually done:**
Pinned a curated registry of the exact tier-1 vlr event IDs in `ingestion/tier1_events.py` (45 events, verified against SPEC §4 dates) and fetch each via `/v2/event/{id}`. `ingestion/events.py` combines the registry's tier/region with the API's name/dates/prize and upserts.

**Why (what the API actually does):**
- `/v2/events?q=completed` is **paginated, recent-first** (~51/page; VCT events are 30–50 pages back), its `region` is a *country* code (de/br/us), `dates` has **no year**, and there is **no tier field** — so the list can't classify the tier-1 set.
- `/v2/search` is **fuzzy** (searching "Champions Seoul" returned a Game Changers event) and naming is **inconsistent across years** ("Champions Tour 2024: …" vs "VCT 2025: …" vs "Valorant Masters London 2026").
- `/v2/event/{id}` is clean: `data.segments` is a **dict** (keys `event/prizes/teams/standings`); `event` has `name, series, dates ("Mar 14 - 24, 2024"), prize ("$500,000 USD"), location`.
Rahat chose the curated-registry approach (over automated pagination or search) and "all tier-1 per SPEC §4" scope.

**Decisions baked in:**
- tier ∈ {Masters, Champions, Kickoff, RegionalLeague}; Stage 1/Stage 2 → RegionalLeague.
- region: international → `global`; **Americas league → `na`** (per SPEC §4's NA/EMEA/PAC/CN wording), EMEA→`emea`, Pacific→`pac`, China→`cn`.
- **Ascension** (promotion) events are excluded — not tier-1 per §4.
- Two 2026 Stage-2 events (2977 Americas, 2978 China) are **unscheduled** (`dates = "Jun 30 – TBD"`) and skipped; they'll be picked up on a later re-ingest. Result: 43/45 ingested now.

**Impact:**
P2.T5 (matches) iterates the `events` table → only these tier-1 events' matches are pulled. Adding/refreshing events = edit the registry + re-run. No schema change.

**Rahat approval:** yes (curated registry; all tier-1 per SPEC §4).

**Related commit:** `<this commit>`

### 2026-06-04 — /v2/team does not expose team region; `teams.region` left NULL

**Phase / Task:** P2.T3

**Spec said:**
ARCHITECTURE.md §2.1 `teams.region` ('na', 'emea', 'pac', 'cn'); P2.T3 fetches `/v2/team` and upserts team rows.

**What was actually done:**
The `/v2/team` profile segment (pinned upstream `a6075fe`) exposes `id, name, tag, logo, country, country_name, rating, roster, event_placements, total_winnings` — but **no region**. `ingestion/teams.py` maps the available fields and sets `region = NULL` (the column is nullable).

**Why:**
Region simply isn't in the team profile payload (confirmed by probing the live endpoint). Country (e.g. `sg`) is present but isn't the league region.

**Impact:**
`teams.region` is NULL after P2.T3. Backfill later from a region-scoped endpoint — `/v2/rankings?region=...` (P2 follow-up) or infer from each team's `events`. No schema change; downstream Elo/region logic must not assume region is populated yet.

**Rahat approval:** N/A (minor; nullable column, no behaviour change).

**Related commit:** `<this commit>`

### 2026-06-04 — Resolution: repo stays PUBLIC; secrets via gitignored .env

**Phase / Task:** P1.T5/T6 follow-up (resolves the "repo is PUBLIC" entry below)

**Spec said:**
P1.T5 expected a private repo.

**What was actually done:**
Rahat decided to **keep the repo public**. To make that safe, hardened secret handling: `.gitignore` now ignores `.env` and all `.env.*` variants while allowing the committed template `.env.example` (`!.env.example`). Added `.env.example` (placeholders only — `VLRGGAPI_URL` default + empty `DEEPSEEK_API_KEY`). Verified `git check-ignore` ignores `.env`/`.env.local`/`.env.production` and that a real `.env` is invisible to git.

**Why:**
Rahat's explicit choice (public is fine), with the constraint that keys/secrets must live in `.env` and never be committed.

**Impact:**
Supersedes the "private" requirement in P1.T5/P8 — these docs' "private" wording is now intentionally not followed. All future secret-bearing work (DeepSeek key in Phase 7, any tokens) must go in `.env` only. No secrets committed to date.

**Rahat approval:** yes (keep public; secrets in gitignored .env)

**Related commit:** `<this commit>`

### 2026-06-04 — GitHub repo is PUBLIC, SPEC expected private

**Phase / Task:** P1.T5 / P1.T6 (discovered)

**Spec said:**
TASKS.md P1.T5: "Create remote `prx-predictor` repo on GitHub (private)." P8 deployment assumes a private repo.

**What was actually done:**
The pre-existing repo `https://github.com/sleipnir029/choochootrain` is **public** (`private: false`, `visibility: public`) — confirmed because the unauthenticated GitHub Actions/repo API returned data during P1.T6 verification. Nothing was changed; flagging the mismatch. Branches `phase-0-*` and `phase-1-*` (pushed in P1.T5) are therefore publicly visible.

**Why:**
The repo predates this work (created outside the task flow) and was set public. Not noticed in P1.T5 because `gh` is unavailable to query visibility; surfaced in P1.T6 when the public API responded.

**Impact:**
All committed code/history is public. No secrets are committed yet (`.env`/keys are gitignored; DeepSeek key arrives in Phase 7) — so no leak so far, but this must be resolved before any secret-bearing work. Decision needed from Rahat: make the repo private (GitHub → Settings → Danger Zone → Change visibility, or `gh repo edit --visibility private`) or consciously keep it public. I cannot change visibility (no `gh`/auth).

**Rahat approval:** pending (decision required)

**Related commit:** `2ebe2de` (P1.T6, where it was discovered)

### 2026-06-04 — vlrggapi team sub-resources are q-variants, not separate paths (affects Phase 2)

**Phase / Task:** P1.T3 (impacts P2.T3, P2.T8, and `scheduler` roster sync)

**Spec said:**
TASKS.md P1.T3 and P2.x, plus SCHEDULER.md, assume these vlrggapi paths:
`/v2/team/matches?id=624&page=1` and `/v2/team/transactions?id={id}`.

**What was actually done:**
Smoke test (P1.T3) hit the **actual** routes the pinned upstream (`a6075fec`) exposes. There is **no** `/v2/team/matches` or `/v2/team/transactions` path. Team match history and roster transactions are `q` variants on `/v2/team`:
- team profile:      `GET /v2/team?id=624`            (q defaults to `profile`)
- team matches:      `GET /v2/team?id=624&q=matches&page=1`
- team transactions: `GET /v2/team?id=624&q=transactions`
- team map stats:    `GET /v2/team?id=624&q=stats`
Confirmed-correct as-documented: `/v2/events/matches?event_id=`, `/v2/match/details?match_id=`, `/v2/match?q=live_score`, `/v2/player?id=` (with `q=profile|matches`).

**Why:**
Discovered by reading `vendor/vlrggapi/routers/v2_router.py` and probing the live container before writing `scripts/smoke_vlrggapi.py`.

**Impact:**
No code yet (Phase 2 not started). Phase 2 ingestion (`ingestion/teams.py` P2.T3, `ingestion/roster_history.py` P2.T8) and the `roster_history_sync` scheduler job must use the `q=`-variant URLs above, not the separate paths the docs assume. ARCHITECTURE.md / SCHEDULER.md / TASKS.md wording can be reconciled when those tasks are built (not edited now — they're not the active task). `scripts/smoke_vlrggapi.py` already uses the correct routes.

**Rahat approval:** N/A (minor; informational, no behavior change yet)

**Related commit:** `<this commit>`

### 2026-06-04 — vlrggapi upstream is on Python 3.14, not 3.11 (minor)

**Phase / Task:** P1.T2

**Spec said:**
CLAUDE.md tech stack: "Python 3.11 (matches vlrggapi pinned version)."

**What was actually done:**
Nothing changed in our code. Noting that the vendored vlrggapi (pinned `a6075fec`) builds on `python:3.14.5-alpine` in its Dockerfile — upstream has moved well past 3.11.

**Why:**
Discovered while reading the vendored Dockerfile before building (P1.T2). Upstream upgraded since the SPEC was written.

**Impact:**
None on our app. The vlrggapi service runs in its own container with its own Python; our prediction app/ingestion still targets Python 3.11 (env `choochoo`) and talks to vlrggapi only over HTTP. The CLAUDE.md parenthetical "(matches vlrggapi pinned version)" is simply outdated — our 3.11 choice stands on its own. Flagging so the rationale isn't trusted as still-true.

**Rahat approval:** N/A (minor)

**Related commit:** `db09a6b` (P1.T1 vendoring, where the pin was set)

### 2026-06-04 — Phase 0 validation deferred; Phase 1 pulled forward (Peng dataset unobtainable)

**Phase / Task:** P0.T2 (and downstream P0.T3–T6)

**Spec said:**
SPEC §3.2 and TASKS.md P0.T2 call for bootstrapping the modeling pipeline on the Peng IEEE DataPort dataset — "Valorant Champions Tour 2024: Pacific and EMEA Round Data" (DOI 10.21227/v3bk-2n86, `VCT DATA.xlsx`, ~1,301 rounds) — using three features (loadout diff, ultimate-availability diff, ult-points diff) to replicate Peng's 60.61% round-level logistic. Phase ordering: validate on this known-clean dataset BEFORE self-hosting vlrggapi (Phase 1).

**What was actually done:**
Phase 0 validation (T2–T6) is **deferred**. We will do **Phase 1 (self-host vlrggapi) first**, then return to Phase 0 validation sourced from our own pipeline. P0.T1 (environment bootstrap) is already complete and stands.

**Why:**
The Peng dataset is paywalled behind a **paid IEEE DataPort subscription** — no open-access download (confirmed on the dataset page; only `VCT DATA.xlsx`, "LOGIN TO ACCESS DATASET FILES"). Rahat cannot obtain it (costs money). Investigation of free alternatives established:
- No free dataset contains Peng's **ultimate features** (available-ultimates / ult-points per round). vlr.gg has never exposed ultimate economy; the Peng author hand-charted it.
- A reference parser, `Data.java` (the author's), was found and placed in the repo root. It only documents the schema + feature math; its raw input `VCT Data.csv` (with the hand-charted ult data) is not present and is not on public GitHub. The parser alone yields no data.
- vlr.gg's economy tab **does** expose numeric per-round loadout values + buy categories; round winners come from the round-result strip / match details. So a **loadout-only** (1-feature) replication is feasible from vlr.gg — but only by writing a scraper, which overlaps Phase 1/2 work the SPEC sequences later.
Faced with "build a Phase-0 scraper now (early vlr.gg use)" vs "reorder," Rahat chose to **reorder**: stand up the Phase 1 vlrggapi pipeline first, then run Phase 0 validation through it (loadout-only, since ult data is permanently unavailable for free).

**Impact:**
- **Sequencing:** Phase 1 runs before Phase 0 validation completes. Phase 0 T2–T6 reopen after Phase 1, sourced from vlrggapi/vlr.gg, **loadout-only** (drops the 2 ultimate features → not a literal Peng replication; accuracy target stays ~55–62% round-level, loadout being Peng's dominant signal).
- **Schema/UI:** none.
- **Artifacts:** `data/external/` created (gitignored except `.gitkeep`); `.gitignore` gained a `data/external/*` rule. `Data.java` retained at repo root as a reference for the eventual loadout/feature parsing (left untracked for now).

**Rahat approval:** yes (chose "free alternative," then "only vlr.gg," then "defer T2, do Phase 1 first").

**Related commit:** `552a7b2`
