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

**Phase:** 3 in progress (statistical modeling). Phase 2 (`v0.1.0-phase-2`) + deferred Phase 0 validation (`v0.1.0-phase-0`) complete. Rahat gave the go-ahead for Phase 3.
**Last completed task:** P3.T8 + deep investigation (Rahat-requested). **Conclusion: signal ceiling, not a bug** — Bayes-opt accuracy ~0.587; features beyond Elo have AUC≈0.50; in-sample also ~57%; no leakage/orientation/base-rate bug. SPEC §6.3's 65-75% map target is unachievable on this corpus (DEVIATIONS 2026-06-06).
**Phase:** Phase 6 + revision complete (tagged `v0.1.1`). Now starting the **Decision-grade analytics** program (Rahat-directed, before Phase 7/8): make the model betting-grade — calibration + track-record + edge/EV. Tier-1 data only (no rib.gg yet); an odds source will be wired in Wave B. Plan: `.claude/plans/…curried-pizza.md`.
**Last completed task:** P6 revision — insight-first PRX-centric dashboard, expected-vs-actual, live prediction wired to the upcoming-feature builder (un-ingested live matches now get a win-prob), subject-aware live hero, `.gitignore` fix (dashboard/src/lib was untracked). Re-tagged `v0.1.1`.
**Next task:** Decision-grade **Wave A** — `models/calibration.py` (recalibrate probabilities) + `models/backtest.py` (+`prediction_log`, walk-forward track record) + a "Model trust" dashboard page. No external data needed. Then Wave B (odds → EV/CLV).
**Open blockers:** Phase-6 container build (`docker compose up --build`) deferred to Phase 8. Live panel needs the P5 poller running (scheduler not registered). Wave B's odds source is a new ToS-gray scrape (gated by a spike). Pre-match model accuracy is intrinsically ~57% (calibration, not accuracy, is Wave A's lever).
**Open blockers:** repo is public by choice (secrets in gitignored `.env`). 29 player handles unresolved (1.2% of stat rows, by design). Phase 0 not a literal Peng replication (loadout unavailable per round).
**Workflow note:** working directly on `main` now (no per-phase branches) — Rahat's call after a stale branch caused a duplicate Phase 1.

---

## Phase summaries

### Phase 0 — Peng dataset validation (reframed; done after Phase 2)

**Built:** `notebooks/00_round_eda.py` (round/economy EDA) + `notebooks/01_round_baseline.py` (round-winner logistic) — marimo, run headless via `python notebooks/*.py`.

**What works / found (on the 67,799-round 2024–2026 warehouse):**
- Toolchain validated end-to-end: SQL → pandas feature build → time-aware split (by map date) → sklearn LogisticRegression → accuracy.
- **Loadout signal (descriptive):** eco rounds win ~42.7% vs ~54% for buys (~11pt) — matches Peng's thesis that loadout dominates, but only visible in aggregate (no per-round loadout from vlrggapi).
- **Side:** barely predictive (CT 50.3% / T 50.7% team1 win) — pro maps are balanced.
- **Fitted baseline:** side-only = 49.9% (chance); **side + score-state = 55.4%** test accuracy (lift from `score_diff` — leading teams win more), vs 50.1% majority baseline.

**What's pending or deferred:** Not a literal Peng replication (no per-round loadout / ultimate features). 55.4% < Peng's 60.6% — the gap is the loadout signal we can't see per round (DEVIATIONS 2026-06-06).

**Numbers:** 55.4% round accuracy (side+score-state), +5.3pt over majority baseline; `score_diff` is the dominant available feature.

**Surprises:** vlrggapi exposes no per-round loadout; `map_team_economy` stores win-% not counts (economy validated descriptively). Side alone is non-predictive at the (arbitrary) team1 level.

**Next phase prep:** `score_diff` carries into the Phase 3 score-state model; loadout won't be a round-level feature.

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

**Built:**
- SQLite schema (`ingestion/schema.py`, 16 tables/11 indexes) + the full ingestion package: `vlr_client` (async, retries, 429-aware, **disk cache**, request throttling), `teams`, `events` (+`tier1_events` registry), `matches`, `match_details`, `players` (handle→ID resolution), `roster_history` (from player profiles), `patches` (Riot scrape→`data/patches.json`).
- `scripts/`: `bulk_ingest.py` (year orchestrator, `--skip-events/--skip-matches/--min-interval`), `validate_ingestion.py`, `smoke_vlrggapi.py`.
- 45 tests (unit, no-network via fakes/MockTransport); CI green.

**What works — warehouse spans 2024–2026 tier-1 (FK clean):**
- 43 events, 1,258 matches, 3,203 maps, 67,799 rounds, 32,030 map_player_stats, 4,862 map_team_economy, 69 teams, 505 players, 864 roster_history, 142 patches.
- Rounds-completeness: 2024 100% / 2025 99.8% / 2026 100%. 0 NULL winners, 0 NULL patch_id.
- Verified done-whens: PRX team/match data; Masters Madrid→London events; per-match maps/rounds/stats/economy; PRX roster on 2025-06-22 = f0rsakeN/Jinggg/d4v41/something/PatMen; patch backfill matches the per-match label (312765→8.04).

**What's pending or deferred:** Phase 0 validation (T2–T6) still deferred (Peng paywalled). 391 stat rows (1.2%, 29 handles) unresolved player_id (subs/casing — by design). 2 showmatch/forfeit matches with 0 maps; 3 incomplete maps.

**Numbers:** see table above. HTTP cache ~tens of MB (gitignored, rebuildable).

**Surprises (all in DEVIATIONS):** vlrggapi exposes names not IDs for teams/players (resolved via match-detail IDs / search+team-context); `/v2/team?q=transactions` broken (roster from player profiles); `/v2/events` unusable for tier-1 (curated ID registry); match dates omit the year for the current year (use listing date); sustained load trips vlrggapi's vlr.gg circuit breaker (added throttling + per-event resilience). map_player_stats re-keyed to handle (schema change).

**Next phase prep:** Phase 3 (modeling) can build on a clean, patch-tagged, FK-consistent warehouse. Use `players_on_team_at()` for roster-aware features; exclude `series_name LIKE 'Showmatch%'` from competitive aggregates.

### Phase 3 — Statistical modeling

**Built:** `models/elo.py` (margin-of-victory Elo update), `models/elo_replay.py` + `scripts/build_elo.py` (→ `elo_ratings`), `models/elo_map_offsets.py` (→ `elo_map_offsets`), `models/training_data.py` (point-in-time per-map features incl. `skill_diff`), `models/bayes_logistic.py` (hierarchical Bambi logistic; numba backend — local g++ broken), `models/score_state.py` (→ `score_state_lookup`), `models/predict.py` (pre-match + live log-odds pooling). Notebooks `02_model_validation.py` (holdout) + `04_player_skill_lift.py` (the revisit).

**What works:** Elo replay ranks teams plausibly (PRX/NRG/EDG/T1/SEN top ~15); map offsets pass eye test (PRX Sunset +63); score-state lookup sane (up 9-3 at half on D → 0.92); Bambi converges (r̂ 1.0); `predict_map_win_prob` returns sensible pre-match + live probabilities.

**What's pending / deferred:** Map-level pre-match prediction has a **low intrinsic ceiling** — the broad holdout reaches **0.583 acc / Brier 0.240**, finally **above** the Elo-sign baseline (0.580) once `skill_diff` was added, but elite Masters maps stay ~coinflip (0.534). SPEC §6.3's 65-75% target is **not achievable** here (Bayes-optimal under Elo ~0.587; DEVIATIONS 2026-06-06).

**Numbers:** holdout acc 0.583 (Elo-sign 0.580), Brier 0.240; `skill_diff` coef 0.214 (HDI [0.093,0.333]); score_state 408 states / 135k obs; Phase-0 round baseline 55.4%.

**Surprises:** every team-level feature beyond Elo was dead weight (form/H2H/side/patch AUC ≈ 0.50); the **only** feature to add real signal was team-aggregated **player skill** (`skill_diff`, corr 0.49 w/ Elo). PyTensor's C backend can't link locally → numba backend. Match dates, economy %, etc. all surfaced earlier.

**Next phase prep:** Phase 5 (live) hooks `models.predict.predict_map_win_prob(..., live_state=...)`; the score-state table + log-odds pooling are ready.

### Phase 4 — Player skill layer

**Built:** `models/player_skill.py` (pure TrueSkill update wrapper), `scripts/build_player_skill.py` (chronological replay → `player_skill`, + `replay_skill_diffs` point-in-time team-skill feature), `models/expected_stats.py` (expected ACS/K/D/A). Notebooks `03_player_skill_validation.py` + `04_player_skill_lift.py`. `trueskill==0.4.5` added to the stack.

**What works:** 477 players rated (439 with ≥10 maps); top conservative ratings are recognizable stars (aspas, Derke, Alfajer, zekken, t3xture). Expected stats hit the ±30 done-when at match level (PRX 666493 MAE(ACS) 24.9; Toronto 2025 27.2). The team-skill feature **lifts map prediction above the Elo ceiling** (integrated into Phase 3's model).

**What's pending / deferred:** Per-(agent, map) skill cells (Layer 5 full granularity) and Layer-6 player-movement adjustment are deferred (post-v1 / when a consumer needs them). Expected stats are match-level only (per-map ACS is unpredictable, ~43 MAE).

**Numbers:** `player_skill` 477 rows; expected ACS MAE 24.9–27.2; `skill_diff` univariate AUC 0.61 (strongest single feature), model coef 0.214.

**Surprises:** per-map ACS is irreducibly noisy (~43 MAE) — only match-level averaging meets ±30. Player skill turned out to be the key feature that beat the Phase-3 Elo ceiling (firepower separates evenly-matched elite teams).

**Next phase prep:** ratings + `replay_skill_diffs` are reusable; the "expected vs actual" panel (Phase 6) consumes `expected_stats.predict_expected_stats`.

### Phase 5 — Live update logic

**Built:** `scheduler/jobs/live_poll.py` — the live-match poller: `parse_live_segment` (live_score → state, handles "N/A"/strings), `select_match` (SPEC-D3 priority PRX > Champions > Masters > Regional > earliest, via `classify_tier`), `state_changed` + `on_change` callback (fires once per same-map change), `write_live_state` (singleton), `to_predict_live_state` + `make_prediction_callback` (re-predict → `live_predictions`), and an async `poll_once`/`run` IDLE-POLLING loop with a `--once` CLI. Tests: `tests/test_live_poll.py` (17).

**What works:** polls `/v2/match?q=live_score` (`VlrClient(cache=False)`), tracks the highest-priority live match, writes the `live_state` singleton, logs + fires the callback exactly once per score change, and recomputes the map win-prob (`predict_map_win_prob` with a live_state) writing it to `live_predictions`. A callback failure is swallowed so the loop survives. Live `--once` smoke connected to the real endpoint (logged `no_live_match`); the prediction path is verified on a simulated ingested match.

**What's pending / deferred:**
- **Real (un-ingested) live-match prediction** needs the Phase-6 upcoming-match feature builder — `predict_map_win_prob` requires ingested map features, so an in-progress match's prediction no-ops (swallowed). Done-when met via an ingested-match simulation.
- **Current-side inference** is best-effort (live_score doesn't expose it); **no hard tier-1/tier-2 exclusion** (live matches aren't in the curated registry).
- **Scheduler registration** (APScheduler job, season cadence) is not wired yet — T1–T4 built the job logic; hooking it into the `prx-app` container is later scheduler/Phase-8 work. The poller runs standalone.

**Numbers:** 17 live-poll tests; full suite 123 passed.

**Surprises:** live_score `score1/score2` are *series* scores, not the round counts the score-state lookup needs (derived from `team{1,2}_round_{ct,t}`); VCT event names carry the "Champions Tour" brand (classification trap, handled); `match_event`/`match_series`/`unix_timestamp` are exposed in live_score (enabled tier ranking with no DB lookup).

**Next phase prep:** Phase 6 API/dashboard reads `live_state` + `live_predictions`; the pre-match panel for an *upcoming* (unplayed) match needs the as-of-now feature builder (the recurring Phase-6 gap noted since P3.T7).

### Phase 6 — FastAPI + React dashboard

**Built:** FastAPI backend (`api/`) — 10 endpoints: predict (pre-match ingested+upcoming / replay / live), teams (+active roster), players (+team-stint stats per D2), events (status-classified from the DB), matches/upcoming (vlrggapi, best-effort). New `models/upcoming.py` (as-of-now feature builder) closes the long-standing upcoming-match gap so **unplayed** matches can be predicted. `models/predict.py` gained `predict_map_win_prob_detailed`/`detailed_from_row`/`_top_factors` (mean + HDI + coef×feature attribution) without changing the float `predict_map_win_prob` the P5 poller uses. React+Vite+TS dashboard (`dashboard/`): dark-theme shell with a mode switcher, TanStack Query, and 4 panels — PreMatch (both modes, factors + HDI), Live (30s poll + Recharts sparkline), Player (per-stint table + ACS bars, D2), Replay (per-map round-prob line chart) — with D3 auto-detect. FastAPI serves the built bundle at `/`; multi-stage Dockerfile (node build → python app).

**What works / numbers:** Full suite **141 passed** (was 123; +18 API/upcoming, prediction-path guarded for CI). `npm run build` clean (tsc strict). Verified end-to-end via TestClient: pre-match ingested (Bo5 666493 → series 0.17/0.83, per-map probs+HDI, factors), pre-match upcoming (PRX-vs-SEN 0.72, HDI 0.62–0.82 — matches the model CLI), replay round trace, live `no_live` fallback, D2 stint partitioning, and `/` serving the SPA alongside `/api`+`/docs`. OpenAPI exposes all 10 paths.

**What's pending / deferred:**
- **Container build (`docker compose up --build`) → Phase 8.** App-level serving is verified locally with uvicorn/TestClient; the heavy bambi/pymc image + posterior/warehouse volume wiring + health checks are Phase-8 deployment (DEVIATIONS 2026-06-06).
- **LLM endpoints (`/api/llm/*`) → Phase 7** (explain + chat-on-data), marked in the contract.
- **Live panel needs the P5 poller running** to show live predictions (scheduler registration is later); and **D3's true next-opponent** falls back to a representative 624-vs-188 matchup because vlrggapi upcoming gives names, not IDs.
- Dashboard uses **state-driven view switching**, not §7.3 path routing (deep links a later nicety).

**Surprises:** the `matches` table is completed-only, so upcoming prediction needed a genuinely separate as-of-now builder; async route + sync sqlite dependency needs `check_same_thread=False`; the factor attribution faithfully reflects Phase-3's near-zero (noisy-signed) recent-form coefficient — kept honest rather than hacked.

**Next phase prep:** Phase 7 fills `api/routes/llm.py` (DeepSeek explain/chat) — the pre-match panel already has a slot for an LLM explanation; the chat endpoint reads the same warehouse.

### Phase 7 — LLM adapter
*Locked*

### Phase 7 — LLM adapter
*Locked*

### Phase 8 — Deployment
*Locked*

---

## Entries

*Newest at top. Don't edit old entries.*

### 2026-06-07 — Analyst scouting (Wave B, slice 1) — team scouting from existing data

**Done:** Rahat pivoted Wave B from betting/odds (edge is thin on efficient tier-1 markets) to **analyst scouting** — no external dependency. First slice uses *only data already in the warehouse* (no re-ingestion): `models/scouting.py` computes, over a team's recent 30 maps — **map pool + CT/T side win-rates**, **economy efficiency** (pistol/eco/semi/full-buy win%), **most-run agent comp per map** (+win%), **agent pools per player**, and **opening-duel win rate** (FK vs FD, team + per player). `GET /api/teams/{id}/scouting` + a `/team/:id` **TeamPage**; match team-names and expected-stats player-names are now clickable (match page = nav hub).

**Learned or surprised (face validity is strong):** PRX scout reads cleanly — strong on Split/Lotus (83%), weak Abyss/Corrode; Lotus T-side 70%; Split comp Jett/Omen/Raze/Skye/Viper 100% over 5; **`something` is the entry fragger (61% opening-duel win) and f0rsakeN is not (50%)**; d4v41 is the sentinel (Vyse/Killjoy), f0rsakeN the controller (Omen 17). All derived from `maps`/`map_player_stats`(agent, fk, fd)/`economy` we already had.

**Verification:** `python -m models.scouting --team 624` (face-valid report); `/api/teams/624/scouting` 200; **Playwright** TeamPage renders all sections, 0 console errors; full suite **157 passed** (+3: scouting model + endpoint).

**Pending (scouting tier 2 — needs re-ingestion from cached match details):** kill matrix → player duel matrix, clutches (1vX), multikills (2K–5K), plants/defuses, and the map-veto sequence (the `map_vetos` string is scraped but dropped). These are the richer scouting signals; a separate ingestion chunk.

**Files touched:**
- `models/scouting.py` (created); `api/routes/teams.py` (scouting endpoint)
- `dashboard/src/pages/TeamPage.tsx` (created); `App.tsx`, `lib/api.ts`, `pages/MatchPage.tsx`, `index.css` (modified — routes + clickable nav)
- `tests/test_scouting.py` (created), `tests/test_api.py` (+scouting); `docs/DEVIATIONS.md`, `docs/PROGRESS.md`

**Commit:** `<pending>` — `decision-grade.scouting: team scouting from existing data`

### 2026-06-07 — Decision-grade Wave A — calibration + track-record + confidence

**Done:** Started the decision-grade program. `models/calibration.py` (measure + recalibrate only if it helps), `models/backtest.py` + `prediction_log` (walk-forward out-of-sample track record + regime map), confidence tier wired into the prediction path (`predict.detailed_from_row`), `GET /api/model/track-record`, and a **"Model trust"** dashboard page (reliability curve + sharp/coinflip table + recent calls) with a confidence chip on match cards.

**Learned or surprised (the key results):**
- **The model is already well-calibrated** (overall ECE 0.013); isotonic recalibration makes OOS Brier slightly *worse* → `calibrate()` is the identity (honest: no forced recalibration).
- **It's a coinflip on most maps but sharp where it matters:** by confidence tier **sharp 73.7% / lean 62.1% / coinflip 55.5%**; the edge lives almost entirely in the ~5% of maps with `|elo_diff| ≥ 150` (74% acc, Brier 0.19). This is the regime Wave B will bet.

**Verification:** `python -m models.calibration` (ECE 0.013, identity, no map saved); `python -m models.backtest` (regime table, wrote prediction_log 1816 rows); `/api/model/track-record` returns the regimes + reliability; **Playwright** Model-trust page renders (reliability scatter on the diagonal), 0 console errors; full suite **154 passed** (+9: calibration/backtest/track-record).

**Files touched:**
- `models/calibration.py`, `models/backtest.py`, `api/routes/model.py` (created); `models/predict.py`, `api/routes/predict.py`, `api/main.py` (modified)
- `dashboard/src/pages/ModelTrustPage.tsx` (created); `App.tsx`, `lib/api.ts`, `pages/MatchPage.tsx`, `index.css` (modified)
- `ingestion/schema.py` + `docs/ARCHITECTURE.md` (`prediction_log`), `.gitignore` (calibration.json)
- `tests/test_calibration.py`, `tests/test_backtest.py` (created), `tests/test_api.py` (+track-record); `docs/DEVIATIONS.md`, `docs/PROGRESS.md`

**Commit:** `<pending>` — `decision-grade.wave-a: calibration + track-record + confidence tiers`

### 2026-06-07 — Live prediction gap closed (wire live path → upcoming builder)

**Done:** Rahat asked to "wire the live path to the upcoming-feature builder" so a real **un-ingested** live match gets a win-prob (not just a tracked score). Added `models.predict.predict_live_win_prob` (ingested path, else upcoming-prior + score-state pool, prior cached per match). The poller now resolves the live segment's team names → `team_id`s and stores them in `live_state` (new nullable `team1_id/team2_id` columns); `make_prediction_callback` uses the new function. The home `_live_hero` reads those ids so an un-ingested live match is PRX-framed correctly.

**Learned or surprised:** `predict_map_win_prob` is slightly non-deterministic for **holdout patches** (`sample_new_groups=True` samples a new patch random-effect each call) — ~±0.0002, harmless, but don't assert bit-identical. The live prior is constant per match, so caching it avoids re-running the posterior-predictive every score change.

**Verification:** simulated an un-ingested match (Cloud9 vs PRX, match 99999999) through the **full** poll→resolve-ids→predict→`live_predictions`→home chain → hero "PRX lead 8-3 on Ascent — 95% to win it" (PRX-framed, opponent resolved), Playwright **0 console errors**; sim data cleared after. Full suite **145 passed** (+1 un-ingested-fallback test). `data/prx.db` `live_state` migrated with `ALTER TABLE`.

**Files touched:**
- `models/predict.py` (`predict_live_win_prob` + prior cache), `scheduler/jobs/live_poll.py` (team names → ids, callback), `api/routes/home.py` (`_live_hero` uses live_state ids)
- `ingestion/schema.py` + `docs/ARCHITECTURE.md` §2.5 (`live_state.team1_id/team2_id`)
- `tests/test_predict.py` (+1), `docs/DEVIATIONS.md`, `docs/PROGRESS.md`

**Commit:** `<pending>` — `phase-6.revision: wire live prediction to the upcoming-feature builder`

### 2026-06-07 — P6 revision — insight-first, PRX-centric dashboard

**Done:** Rahat's feedback: the dashboard was "just charts, no insight … like vlr.gg … picking players/matches by id is wasteful." Rebuilt it to the SPEC's actual vision (§1/§7.2/Layer-5) — **PRX-centric, narrative-first, click-through**. Backend: `api/insight.py` (templated narrative — pre/post/live + biggest-swing, PRX-framed, LLM-ready), `api/compute.py` + 3 **view-shaped endpoints** (`/api/home`, `/api/matches/{id}`, `/api/players/{id}`) that surface the previously-unexposed **expected-vs-actual** layer, **model-was-right/wrong** on recent matches, PRX **Elo rank**, roster **skill**, and player **percentile**. Frontend: `react-router-dom` + `pages/{Home,Match,Player}` — **ID inputs removed**, navigation by clicking recent matches / roster; `<Insight>` leads every view, charts support. Match view fully **PRX-framed** (per-map, factors "favours Paper Rex", replay rises for PRX). FastAPI **SPA fallback** + vite `base '/'` so deep links work.

**Learned or surprised:**
- The whole insight layer was *latent* — `predict_expected_stats` already returned expected+actual; it just needed exposing + narrating ("f0rsakeN stepped up: 266 vs ~201 expected (+66)").
- `base: './'` breaks deep-link asset resolution with a router (browser fetches `/match/assets/…`) → must be `'/'` + an SPA fallback that serves `index.html` for non-`/api` paths.
- The model's recent calls read well: 5/6 recent PRX matches correct; the one MISS (a 1-2 loss it gave 65%) is exactly the kind of upset the post-match "✗" surfaces.

**Verification:** `npm run build` clean; full suite **144 passed** (+3 view-endpoint tests; home/match guarded for bambi, player view light). **Playwright** end-to-end: Home (PRX #2/55, last-match story, recent ✓/✗, roster) → click match (`/match/666493`: prematch+postmatch narrative, PRX-framed maps/factors/replay, expected-vs-actual ±delta) → click player (`/player/…`: 96th-pct skill, exp-vs-actual trend, stints) — **0 console errors**, deep links work.

**Files touched:**
- backend: `api/insight.py`, `api/compute.py`, `api/routes/home.py` (created); `api/routes/{predict,matches,players}.py`, `api/main.py` (modified); `tests/test_api.py` (+3)
- frontend: `dashboard/src/lib/api.ts`, `App.tsx`, `main.tsx`, `index.css`, `vite.config.ts` (rewritten/modified); `components/Insight.tsx`, `pages/{HomePage,MatchPage,PlayerPage}.tsx` (created); old `components/{PreMatchPanel,LivePanel,PlayerPanel,ReplayPanel}.tsx` (deleted); `react-router-dom` added
- `docs/DEVIATIONS.md`, `docs/PROGRESS.md`

**Commit:** `<pending>` — `phase-6.revision: insight-first PRX-centric dashboard`

### 2026-06-07 — P6 fixes — replay perf + chart sizing (Playwright review)

**Done:** Rahat ran the dashboard (`uvicorn api.main:app`) and reviewed it with Playwright; flagged issues. Drove the live app headlessly (chromium) + screenshotted every panel. Found and fixed two real issues:
1. **Replay was slow (9.3s for 68 rounds).** `/api/predict/replay` re-ran the Bambi posterior-predictive prior for *every* round, but the prior is identical across a map's rounds (only the score-state changes). Added `models.predict.score_state_prob` (cheap lookup) and rewrote the replay route to compute the prior **once per map**, then `combine_prior_and_state` per round. **9.3s → 0.30s (31×)**, numerically identical output.
2. **Recharts `width(-1)/height(-1)` console warnings.** Caused by a `.sub` heading sharing the fixed-height chart container in `PlayerPanel`/`LivePanel` (ResponsiveContainer measured a transiently-negative size). Gave each chart an explicit numeric `height` and moved headings out. Browser console is now clean (verified: 0 console/page errors).

Also corrected a stale comment (default opponent 188 = Cloud9, not Sentinels).

**Verification:** Playwright across all panels → no console/page errors; replay renders 3 per-map probability line charts; player (D2 stint table + ACS bars), pre-match (prob bar + factors + HDI), and live (`no_live`) all render correctly. TestClient replay **0.30s**; full suite **141 passed** (replay test's model calls dropped 68→3). **Note:** restart `uvicorn` to pick up the replay perf fix; refresh the browser for the rebuilt bundle.

**Files touched:**
- `models/predict.py` (added `score_state_prob`), `api/routes/predict.py` (replay route)
- `dashboard/src/components/{PlayerPanel,LivePanel,ReplayPanel}.tsx` (chart sizing), `dashboard/src/App.tsx` (comment)
- `docs/PROGRESS.md` (this entry)

**Commit:** `<pending>` — `fix(phase-6): replay perf (31x) + chart sizing warnings`

### 2026-06-06 — P6.T11 — Phase 6 summary + tag

**Done:** Wrote the Phase 6 summary (above) and updated Current state. Phase 6 (FastAPI prediction API + React dashboard) is complete: 10 endpoints, the upcoming-match feature builder, 4 dashboard panels with D3 auto-detect, and FastAPI static serving. Tagging `v0.1.0-phase-6`. Container build + LLM endpoints are explicitly deferred (Phase 8 / Phase 7).

**Verification:** full suite **141 passed**; `npm run build` clean; TestClient serves `/` + `/api` + `/docs`.

**Files touched:**
- `docs/PROGRESS.md` (Phase 6 summary + current state + this entry)

**Commit:** `<pending>` — `phase-6.task-11: phase 6 summary` (+ tag `v0.1.0-phase-6`)

### 2026-06-06 — P6.T10 — Build + serve dashboard from FastAPI

**Done:** `api/main.py` mounts the built `dashboard/dist` at `/` via `StaticFiles(html=True)` (guarded by dir existence; `DASHBOARD_DIST` override) — mounted **last** so `/api/*` and `/docs` win. Rewrote `docker/Dockerfile` as a multi-stage build (Node 24 builds the dashboard → Python 3.11 installs `requirements.txt` + app + `dist`, sets `DASHBOARD_DIST`). Updated `docker/docker-compose.yml`: `prx-app` runs the real app (`uvicorn api.main:app`), `DATA_DIR=/data`, with `../data:/data` + `../models/saved` volume mounts.

**Learned or surprised:** Mount order matters — registering routers (and FastAPI's `/docs`) before the `/` mount keeps the SPA from shadowing them. The full `docker compose up --build` (heavy bambi/pymc image + posterior/warehouse via volumes) overlaps Phase-8 deployment, so it's **deferred to Phase 8**; the app-level serving is verified locally (DEVIATIONS 2026-06-06).

**Verification:** TestClient against the built bundle — `GET /` → 200 `text/html` with the React root div; `/api/health` → ok; `/docs` → 200; `/assets/*.js` → 200 `application/javascript`. Full suite **141 passed** (static mount executes at import; no test regressions).

**Files touched:**
- `api/main.py` (modified — StaticFiles mount)
- `docker/Dockerfile` (rewritten — multi-stage), `docker/docker-compose.yml` (modified — real app + volumes)
- `docs/DEVIATIONS.md` (frontend choices entry), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-6.task-10: serve dashboard from fastapi + multi-stage docker`

### 2026-06-06 — P6.T4–T9 — Dashboard UI (shell + 4 panels + auto-detect)

**Done:** Built the dashboard UI. **T4 shell** (`App.tsx`, dark theme in `index.css`, TanStack Query in `main.tsx`): sticky top bar with a live/no-live mode pill + manual switcher (Live/Pre-match/Player/Replay) + a contextual ID input. Typed API client `src/lib/api.ts` (axios, mirrors the §3 contract). **T5 `PreMatchPanel`**: series win-prob bar (`WinProbBar`), per-map probs, top-factor breakdown with HDI; works in both ingested + upcoming modes. **T6 `LivePanel`**: `useQuery` with `refetchInterval: 30_000`, scoreline + current-map prob + a Recharts probability sparkline; handles `no_live`. **T7 `PlayerPanel`**: per-team-**stint** table (D2 — no cross-team pooling) + a per-stint ACS bar chart. **T8 `ReplayPanel`**: round-by-round probability line chart per map. **T9 auto-detect (D3)**: on mount queries `/api/predict/live` → Live panel if live, else Pre-match for PRX's next matchup (default 624-vs-188 until schedule/veto known); manual switcher always overrides.

**Learned or surprised:** Recharts' Tooltip `formatter` types its value as the wide `ValueType` (not `number`) → coerce with `Number(v)`. Bundle is 641 KB (Recharts-dominated); advisory `>500 kB` warning only — acceptable for a LAN dashboard (code-splitting is YAGNI for v1). D3's "PRX next match" can't be predicted without both team IDs (vlrggapi upcoming gives names, not IDs), so the no-live default uses a representative 624-vs-188 upcoming matchup that renders real model output; a match-ID input allows any ingested match.

**Verification:** `npm run build` (tsc strict typecheck + vite bundle) passes clean. Visual/data rendering is manual per ARCHITECTURE §9 (no dashboard e2e in v1) — exercised end-to-end against the served bundle in T10.

**Files touched:**
- `dashboard/src/lib/api.ts`, `dashboard/src/main.tsx`, `dashboard/src/App.tsx`, `dashboard/src/index.css` (created/rewritten)
- `dashboard/src/components/{WinProbBar,PreMatchPanel,LivePanel,PlayerPanel,ReplayPanel}.tsx` (created)
- removed dead scaffold `src/App.css`, `src/assets/react.svg`
- `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-6.task-4-9: dashboard ui (shell + panels + auto-detect)`

### 2026-06-06 — P6.T3 — React + Vite dashboard scaffold

**Done:** Rahat gave the frontend go-ahead. Scaffolded `dashboard/` via `create-vite` (react-ts), installed `recharts`, `axios`, `@tanstack/react-query` (ARCHITECTURE §7.2). Configured `vite.config.ts`: `base: './'` (so the built bundle works when FastAPI serves it from `/` in T10) + a dev proxy `/api → http://localhost:8000` (so `npm run dev` hits the real API; overridable via `VITE_API_URL`).

**Verification:** `npm install` clean (0 vulnerabilities); `npm run build` succeeds (tsc + vite bundle). Scaffold `.gitignore` covers `node_modules`/`dist`.

**Files touched:** `dashboard/**` (scaffold), `dashboard/vite.config.ts` (proxy + base), `docs/PROGRESS.md`.

**Commit:** `<pending>` — `phase-6.task-3: react+vite dashboard scaffold`

### 2026-06-06 — P6.T2 — FastAPI server + upcoming-match feature builder

**Done:** Built the Phase-6 backend. New `api/` package: `main.py` (FastAPI app, CORS, lazy/opt-in `PRX_WARM` resource warming via lifespan), `deps.py` (per-request sqlite conn, `check_same_thread=False` for async routes), and one router per resource — `predict.py` (pre-match ingested+upcoming / replay / live), `teams.py`, `players.py`, `events.py`, `matches.py`. New `models/upcoming.py` closes the long-standing **upcoming-match gap**: `build_upcoming_features` reads snapshot/history tables (latest `elo_ratings`, current-roster mean `player_skill.mu`, last-5-map form, EB-shrunk H2H) into the FORMULA's feature columns, and `predict_upcoming_win_prob` runs it through `models.predict`'s cached Bambi model. Added `predict_map_win_prob_detailed` + `detailed_from_row` + `_top_factors` to `models/predict.py` (mean + HDI + coef×feature attribution) — the float `predict_map_win_prob` is untouched (P5 poller safe). `fastapi`/`uvicorn` added to `requirements.txt` + CI. Tests: `tests/test_api.py` (TestClient shapes, D2 stint partitioning, graceful no-vlrggapi) + `tests/test_upcoming.py` (feature shape/sign/antisymmetry + guarded predict).

**Learned or surprised:**
- The `matches` table is **completed-only**, so upcoming prediction needed a genuinely separate builder reading *as-of-now* state (no point-in-time replay; "now" is after all data → no leakage).
- **Async route + sync generator dependency** creates the sqlite conn in a threadpool thread but runs the body in the event-loop thread → `check_same_thread=False` required.
- **Factor attribution is faithfully noisy:** PRX-vs-SEN upcoming shows Player skill (0.40) + Elo (0.39) dominating correctly, but the near-zero/dead recent-form coefficients (Phase-3 finding) produce a counterintuitive "team1's 5-0 form favors team2" at low weight. Kept faithful to the model (documented as approximate, not Shapley) rather than hacking signs.
- vlrggapi best-effort calls use `VlrClient(max_retries=0, timeout=5)` so live/upcoming fail fast (return `source: "unavailable"`) instead of stalling the request when the container is down.

**Verification:** `python -m models.upcoming --db data/prx.db --team1 624 --team2 188` → P(PRX)=0.720 HDI [0.62,0.82], 0 NaN. TestClient: pre-match ingested (match 666493 Bo5 → series 0.17/0.83, 3 map probs+HDI, 4 factors), pre-match upcoming (0.719, matches the CLI), replay (3 maps, round trace 0.29→0.06), live → `no_live`/next-PRX (graceful when vlrggapi down), D2 stint partitioning (5 distinct-team stints). OpenAPI lists all 10 paths. Full suite **141 passed** (was 123; +18 new, prediction-path guarded/skipped in CI).

**Files touched:**
- `models/upcoming.py` (created), `models/predict.py` (modified — detailed helpers)
- `api/main.py`, `api/deps.py`, `api/routes/__init__.py`, `api/routes/{predict,teams,players,events,matches}.py` (created)
- `tests/test_api.py`, `tests/test_upcoming.py` (created)
- `requirements.txt`, `.github/workflows/ci.yml` (modified — fastapi/uvicorn)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-6.task-2: fastapi server + upcoming-match feature builder`

### 2026-06-06 — P6.T1 — API contract reconciliation

**Done:** Started Phase 6 (Rahat go-ahead; backend-only scope T1–T2 this session). Reconciled `docs/ARCHITECTURE.md` §3/§5.3 with the built code rather than the aspirational original. Key changes: `predict_map_win_prob` documented as returning a bare `float` (the `Prediction(...)` object was never built; the P5 poller depends on the float), with two new Phase-6 composition helpers (`predict_map_win_prob_detailed`, `models.upcoming.predict_upcoming_win_prob`); `top_factors` = interpretable coef×feature attribution (not Shapley); `series_win_prob` = derived Bo-N binomial; `/api/predict/pre-match` gains an **upcoming mode** (`team1_id`+`team2_id`) for D3's next-PRX-match (not in the `matches` table); HDI surfaced per SPEC §6.1; `/api/predict/live` reads the poller's tables; `/api/llm/*` marked Phase 7. DEVIATIONS entry added.

**Learned or surprised:** The `matches` table holds **completed matches only** (P2.T5), so the D3 default view genuinely has no row — the upcoming-match feature builder (T2, `models/upcoming.py`) is required, not optional. FastAPI 0.115.6 + uvicorn 0.49.0 are installed but **missing from `requirements.txt`** (same gap as trueskill) — to be added in T2.

**Verification:** Docs-only task; read-through confirms every dashboard endpoint is documented and the contract now matches the real `predict` signature. No code changed → test suite unaffected (123 passing as of P5.T5).

**Files touched:**
- `docs/ARCHITECTURE.md` (modified — §3.1 pre-match/live, §3.3 LLM, §5.3 signatures)
- `docs/DEVIATIONS.md` (modified — P6.T1 reconciliation entry)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-6.task-1: api contract reconciliation`

### 2026-06-06 — P5.T5 — Phase 5 summary + tag

**Done:** Wrote the Phase 5 summary (above) and updated Current state. Phase 5 (live update logic) is complete: poller → priority match selection → live_state + score-change callback → re-prediction → live_predictions. Tagging `v0.1.0-phase-5`.

**Verification:** full suite **123 passed**; the live-poll job is exercised by 17 tests + a live `--once` smoke.

**Files touched:**
- `docs/PROGRESS.md` (Phase 5 summary + current state + this entry)

**Commit:** `<pending>` — `phase-5.task-5: phase 5 summary` (+ tag `v0.1.0-phase-5`)

### 2026-06-06 — P5.T4 — Priority logic for multiple live matches

**Done:** Refactored `select_match` in `scheduler/jobs/live_poll.py` into the SPEC-D3 priority (`_priority_key` = PRX > tier > earliest start), with `classify_tier(match_event)` + `_TIER_RANK`. Tier and start time come from the live_score segment's own `match_event`/`unix_timestamp` — no DB lookup. Extended `tests/test_live_poll.py` (+4). Tier-classification + soft-gap notes in DEVIATIONS 2026-06-06.

**Learned or surprised:** VCT event names carry the **"Champions Tour"** circuit brand, so a naive "champions" match would misclassify Kickoff/Stage events — fixed by checking Kickoff/Masters first and excluding "champions tour" from the Champions tournament test. No hard tier-2 exclusion (live matches aren't in the curated registry) — documented soft gap.

**Verification:** `pytest tests/test_live_poll.py -q` → 17 passed (classify Champions/Masters/Kickoff/Stage; PRX beats higher tier; Champions>Masters>Regional; earliest-start tiebreak). Full suite **123 passed**.

**Files touched:**
- `scheduler/jobs/live_poll.py` (modified — priority `select_match` + helpers)
- `tests/test_live_poll.py` (modified — priority tests)
- `docs/DEVIATIONS.md` (modified — tier classification + gap), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-5.task-4: multi-match priority`

### 2026-06-06 — P5.T3 — Hook score-change to re-prediction

**Done:** Added to `scheduler/jobs/live_poll.py`: `to_predict_live_state` (poller state → predict's `{half, team1_score, team2_score, team1_side}` from round counts; best-effort side), `write_live_prediction` (→ `live_predictions`, microsecond `computed_at`), and `make_prediction_callback(db_path)` — an `on_change` that calls `predict_map_win_prob` and stores the result. Wired into `main()`. Extended `tests/test_live_poll.py` (+4). Mapping + the un-ingested-match limitation in DEVIATIONS 2026-06-06.

**Learned or surprised:** the poller's `team1_score/team2_score` are *map/series* scores, not the round scores the score-state lookup needs — derived round scores from the per-side round fields. Real (un-ingested) live matches can't be predicted yet (predict needs ingested features) → error swallowed by the T2 guard; deferred to Phase 6. Simulated the done-when with an ingested match.

**Verification:** `pytest tests/test_live_poll.py -q` → 13 passed (mapping + half boundaries + write always; guarded integration: ingested match 666493 + 2 fake states → exactly one `live_predictions` row, 0<prob<1). Full suite **119 passed**.

**Files touched:**
- `scheduler/jobs/live_poll.py` (modified — mapping, prediction write, callback factory, main wiring)
- `tests/test_live_poll.py` (modified — T3 tests)
- `docs/DEVIATIONS.md` (modified — live_state mapping + gap), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-5.task-3: hook score-change to re-prediction`

### 2026-06-06 — P5.T2 — Score-change detection (callback)

**Done:** Threaded an optional `on_change(state, changed)` callback through `poll_once`/`run` in `scheduler/jobs/live_poll.py`, fired **exactly once per poll** in which a same-match change is detected (not on baseline or match switch). Wrapped in try/except → logs `on_change_failed` so a downstream (P5.T3 prediction) failure can't kill the poll loop. Extended `tests/test_live_poll.py` (+3 tests).

**Learned or surprised:** Nothing notable — built directly on the P5.T1 `state_changed` seam; sync callback (T3's `models.predict` is sync).

**Verification:** `pytest tests/test_live_poll.py -q` → 9 passed (incl. fires-once across `[a,a,b,b,c]` = 2 calls with correct changed-fields; no fire on baseline/match-switch; raising callback swallowed). Full suite **115 passed**.

**Files touched:**
- `scheduler/jobs/live_poll.py` (modified — `on_change` param + guarded invocation)
- `tests/test_live_poll.py` (modified — callback tests)
- `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-5.task-2: score-change callback`

### 2026-06-06 — P5.T1 — Live score poller

**Done:** Started Phase 5. Added `scheduler/jobs/live_poll.py` (+ `scheduler/jobs/__init__.py`) — pure seams (`parse_live_segment`, `state_changed`, `select_match`, `write_live_state`) + async `poll_once` / `run` IDLE-POLLING loop. Writes the tracked match to the singleton `live_state` table and logs every score change; `VlrClient(cache=False)`; `--once` CLI. Match-selection is minimal (PRX-preferred) — full tier-1/priority is T4. Added `tests/test_live_poll.py` (6 tests). Choices in DEVIATIONS 2026-06-06.

**Learned or surprised:** live_score round/score fields arrive as strings or `"N/A"` → parsed to int/NULL. Chose the `live_state` table over a bare in-memory cache (per SCHEDULER.md, for cross-process API reads). FK to `matches` is safe (enforcement off; a live match may be un-ingested).

**Verification:** `pytest tests/test_live_poll.py -q` → 6 passed (parse N/A, state_changed incl. different-match, PRX selection, singleton write, poll_once persists a score change, no-live-match). Full suite **112 passed**. Live smoke: started the vlrggapi container, `python -m scheduler.jobs.live_poll --once --db data/prx.db` → reached `/v2/match?q=live_score` (200) and logged `no_live_match` (none live now); container stopped.

**Files touched:**
- `scheduler/jobs/live_poll.py` (created), `scheduler/jobs/__init__.py` (created)
- `tests/test_live_poll.py` (created)
- `docs/DEVIATIONS.md` (modified — T1 choices), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-5.task-1: live score poller`

### 2026-06-06 — Integration + Phase 3 (T9) & Phase 4 (T5) summaries

**Done:** Integrated `skill_diff` into the pre-match model (commit `184455b`: `models/training_data.py` adds the column, `models/bayes_logistic.py` formula + refit), re-validated (`notebooks/02_model_validation.py`), and wrote the Phase 3 and Phase 4 summaries above. Tags `v0.1.0-phase-3` + `v0.1.0-phase-4`.

**Result:** refit converged (r̂ 1.0, 0 div); `scale(skill_diff)` coef **0.214** (HDI [0.093,0.333]). Broad post-cutoff holdout **0.583 acc / 0.240 Brier** — first time the model beats the Elo-sign baseline (0.580); RegionalLeague 0.602; elite Masters 0.534 (~coinflip, n=118). `skill_diff` is the strongest single feature (AUC 0.61).

**Verification:** `python -m models.bayes_logistic` (refit, PASS); `python notebooks/02_model_validation.py` (numbers above); `python -m models.predict` (sane); full suite **106 passed**.

**Files touched:**
- `models/training_data.py`, `models/bayes_logistic.py`, `notebooks/02_model_validation.py`, `tests/test_training_data.py`, `tests/test_bayes_logistic.py`, `docs/DEVIATIONS.md` (integration commit `184455b`)
- `docs/PROGRESS.md` (Phase 3 + Phase 4 summaries, current state, this entry)

**Commit:** `<pending>` — `docs: phase 3 + phase 4 summaries` (+ tags `v0.1.0-phase-3`, `v0.1.0-phase-4`)

### 2026-06-06 — Phase 3 revisit — does player skill lift map prediction?

**Done:** Planned-then-executed. Added `replay_skill_diffs(conn)` to `scripts/build_player_skill.py` (point-in-time per-map `mean μ(team1) − mean μ(team2)`, reusing a refactored `_iter_maps`/`_update_map_ratings` shared with `replay`). Added `notebooks/04_player_skill_lift.py` comparing elo / skill / elo+skill logistic models on the holdout. Added a `replay_skill_diffs` unit test. Conclusion in DEVIATIONS 2026-06-06.

**Numbers:** `corr(skill_diff, elo_diff)=0.49` (distinct info). Broad post-cutoff: **elo+skill acc 0.589 / AUC 0.622 / Brier 0.238** vs elo-only 0.580 / 0.609 / 0.241. Elite Masters: **skill-alone acc 0.585 / AUC 0.603** vs elo 0.542 / 0.546 (~+4pt). Player skill is the **first feature to add real signal beyond Elo** (every Layer-3 feature was dead).

**Learned or surprised:** The P3.T8 ceiling holds for *team-level* features but player-level skill lifts it — modestly broad, notably on elite events (firepower separates evenly-matched top teams). Lift is real but small in absolute terms; not a route to the original 65-75% target.

**Verification:** `python notebooks/04_player_skill_lift.py` headless prints the comparison; `pytest tests/test_build_player_skill.py` → 6 passed (incl. point-in-time skill-diff sign); full suite **106 passed**.

**Files touched:**
- `scripts/build_player_skill.py` (modified — `replay_skill_diffs` + `_iter_maps`/`_update_map_ratings` refactor)
- `notebooks/04_player_skill_lift.py` (created)
- `tests/test_build_player_skill.py` (modified — skill-diff test)
- `docs/DEVIATIONS.md` (modified — revises P3.T8 ceiling), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-3.revisit: player-skill lift on map prediction`

### 2026-06-06 — P4.T4 — Player-skill validation

**Done:** Added `notebooks/03_player_skill_validation.py` (marimo) — applies `predict_expected_stats` to every map-resolved player in Masters Toronto 2025 (event 2282, time-held-out), reports MAE + bias per stat and an expected-vs-actual ACS scatter. Runs headless.

**Numbers (Toronto 2025, 24 matches, 239 player rows, mean history 91 maps):** ACS MAE **27.2** (bias +6.0), kills 2.55, deaths 2.16, assists 1.78 (actual means 194/14.7/14.7/5.7). ACS within the ±30 done-when. Slight positive ACS bias — players underperformed recent form at this elite event (consistent with "elite events are harder").

**Verification:** `python notebooks/03_player_skill_validation.py` runs end-to-end headless and prints the metrics above; full suite **105 passed** (no model code changed).

**Files touched:**
- `notebooks/03_player_skill_validation.py` (created)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-4.task-4: player-skill validation`

### 2026-06-06 — P4.T3 — Expected player stats prediction

**Done:** Planned-then-executed (Rahat asked to plan first). Added `models/expected_stats.predict_expected_stats(match_id)` — match-level expected ACS/K/D/A from each player's recent-form mean (last 30 maps, point-in-time; fallbacks career→league) + a mild opponent-Elo ACS adjustment (from `elo_ratings`, `opponent_coef=0.06`). Map term dropped (empirically harmful). In-module `--db/--match-id` CLI. Added `tests/test_expected_stats.py` (6 tests). Granularity/decision rationale in DEVIATIONS 2026-06-06.

**Learned or surprised:** Per-map ACS is unpredictable (MAE ~43; map offset made it worse); match-level recent-form gets to the ±30 floor. MAE is ~30 on a broad recent sample (≈half of matches ≤30) but ~25 on stable lineups. Opponent-Elo term helps only ~0.2 MAE (kept, marginal). Predictions read sensibly (f0rsakeN expected 201 vs actual 266 → over-performer flagged — the panel's purpose).

**Verification:** `pytest tests/test_expected_stats.py -q` → 6 passed (recent-form windowing, point-in-time no-leak on a synthetic DB, unknown-match raises, real-match sane). Full suite **105 passed**. Live `python -m models.expected_stats --db data/prx.db` (PRX match 666493): **MAE(ACS)=24.9 across 10 players** (done-when met).

**Files touched:**
- `models/expected_stats.py` (created)
- `tests/test_expected_stats.py` (created)
- `docs/DEVIATIONS.md` (modified — match-level/recent-form rationale), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-4.task-3: expected player stats`

### 2026-06-06 — P4.T2 — Replay to compute current player skills

**Done:** Added `scripts/build_player_skill.py` — `replay(conn)` walks resolved `map_player_stats` in date order; each map is one TrueSkill round (performance = player ACS − opposing team avg ACS; opponent = mean(mu,sigma) of the 5 opposing players' current ratings; all 10 update from pre-map ratings). `build(conn)` writes the current **overall** rating per player (agent/map NULL, stamped with last-played date; idempotent rebuild). `--db/--min-maps` CLI prints the top players by conservative skill (mu−3σ). Added `tests/test_build_player_skill.py` (5 tests). Scope/definition choices in DEVIATIONS 2026-06-06.

**Learned or surprised:** Top conservative ratings are recognizable stars (aspas, Derke, Alfajer, zekken, t3xture, ZmjjKK, BuZz, marteen) — strong face validity for an ACS-driven rating. Per-(agent,map) cells deferred (would be sparse) — overall rating is what the ≥10-map done-when and the team-strength feature need.

**Verification:** `pytest tests/test_build_player_skill.py -q` → 5 passed (one row/player, consistent over/under-performer rises/falls, last-map as_of_date, showmatch exclusion, idempotent). Full suite **99 passed**. Live `python -m scripts.build_player_skill --db data/prx.db` → **477 rated, 439 with ≥10 maps** (done-when), face-valid top-15.

**Files touched:**
- `scripts/build_player_skill.py` (created)
- `tests/test_build_player_skill.py` (created)
- `docs/DEVIATIONS.md` (modified — T2 scope/definitions), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-4.task-2: player-skill replay -> player_skill`

### 2026-06-06 — P4.T1 — TrueSkill integration

**Done:** Started Phase 4 (Rahat: player-skill first, to test a map-prediction lift). Installed `trueskill==0.4.5` (missing from the P0.T1 bootstrap; added to `requirements.txt` + CI). Added `models/player_skill.py` — pure `update_skill(player_id, agent, map_name, performance_score, opponent_skill, *, current=None, baseline=0.0)`: a map is a 1v1 TrueSkill match vs `opponent_skill`, outcome from the sign of `performance_score` (win/loss/draw). `new_rating()` helper; library-default env. Binary-outcome choice in DEVIATIONS 2026-06-06. Added `tests/test_player_skill.py` (7 tests).

**Learned or surprised:** `env.rate_1vs1` is deprecated → use module-level `trueskill.rate_1vs1(..., env=_ENV)`. `draw_probability=0` makes a forced draw degenerate → use the library default (0.10). `player_id/agent/map_name` are identity keys, not math inputs (the T2 replay keys its store by them).

**Verification:** `pytest tests/test_player_skill.py -q` → 7 passed (defaults, win↑mu/↓sigma, loss↓mu, draw-vs-equal no mean shift, beating stronger gains more, unseen-player default, sigma monotone↓). Full suite **94 passed**.

**Files touched:**
- `models/player_skill.py` (created)
- `tests/test_player_skill.py` (created)
- `requirements.txt` (modified — trueskill), `.github/workflows/ci.yml` (modified — install trueskill)
- `docs/DEVIATIONS.md` (modified — binary-outcome + late install), `docs/PROGRESS.md` (modified)

**Commit:** `<pending>` — `phase-4.task-1: trueskill player-skill wrapper`

### 2026-06-06 — P3.T8 (cont.) — Deep investigation of the underperformance

**Done:** Per Rahat's "deep investigate" choice, added ablation cells to `notebooks/02_model_validation.py` (univariate AUC per feature, parameter-free Elo-probability baseline, Bayes-optimal ceiling) and ran sklearn ablations + base-rate/calibration checks.

**Conclusion — genuine signal ceiling, no bug:**
- **No leakage/orientation bug:** in-sample acc also ~57%; `corr(elo_diff,won)` positive throughout; Elo-sign > 50%.
- **No team1 artifact:** team1 win-rate ~0.50 across years/tiers; Masters 0.449 base is small-sample noise.
- **Features beyond Elo are dead:** univariate AUC ≈ 0.50 (side 0.47-0.49, form ~0.46-0.55, H2H 0.50-0.56). `map_elo_diff` is marginally best on elite (AUC 0.584) but swapping it for the collinear pair doesn't change accuracy.
- **Intrinsic ceiling:** parameter-free Elo-prob matches the fitted model; Bayes-opt accuracy ~0.587; elite Brier floor ~0.247 (vs 0.25 coin) → ~zero headroom. Elite teams are coinflips at map level; regional ~60%.

**Recommendation:** accept an Elo-centric v1 with revised expectations (SPEC §6.3's 65-75% map target is not achievable here — DEVIATIONS 2026-06-06). System value = team ranking + the in-match score-state layer. Optionally simplify the model (drop zero-signal terms) — no accuracy cost or gain. Phase 4 (player skill) + more 2026 data are the future levers.

**Verification:** `python notebooks/02_model_validation.py` runs end-to-end headless with all ablation/ceiling numbers; full suite still **87 passed**.

**Files touched:**
- `notebooks/02_model_validation.py` (modified — ablation cells + honest conclusion)
- `docs/DEVIATIONS.md` (modified — §6.3 target not achievable, evidence)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-8: deep investigation of holdout underperformance`

### 2026-06-06 — P3.T8 — Validation on holdout (result below target — flagged)

**Done:** Added `notebooks/02_model_validation.py` (marimo) — batch-predicts all post-cutoff maps from the saved posterior, reports accuracy/Brier + majority & Elo-sign baselines on the primary holdout (Masters Toronto 2025 + Santiago 2026), per-tier context across all post-cutoff maps, and a calibration plot. Runs headless.

**Numbers:**
- **Primary holdout (Masters Toronto+Santiago, n=118): acc 50.9%, Brier 0.257, ECE 0.15** — *below* majority 55.1% and Elo-sign 54.2%, and far short of SPEC §6.3 (65-75% / 0.20-0.23). (Brier 0.257 > 0.25, i.e. worse than a constant 0.5 here — miscalibrated on this slice.)
- All post-cutoff (n=1816): model 57.0% vs Elo-sign 58.0%, Brier 0.242. Per tier: RegionalLeague 59.5% (elo 59.8), Kickoff 52.8, Masters 50.9, Champions 44.3.
- In-sample (train) acc only ~56.6%.

**Learned / surprised (IMPORTANT):** The model **essentially reproduces the Elo-sign baseline** on every slice (and the extra features — map offsets, recent form, H2H, patch/tier pooling — add ~no marginal signal; matches the T5 posterior where `elo_diff` dominated, others ≈0). Elite events (Masters/Champions = top, evenly-matched teams) are near-coinflips at map level (corr(elo_diff, won) 0.04–0.12) — the T8-mandated holdout is the *hardest* possible slice; regional play is more predictable (~60%). Low **in-sample** accuracy confirms this is a **signal ceiling**, not overfitting or a bug (orientation verified: corr(elo,y) positive throughout, Elo-sign > 50%). Per CLAUDE.md ("two results not matching expectations → surface"), **stopped to ask Rahat** before the Phase 3 summary.

**Verification:** `python notebooks/02_model_validation.py` runs end-to-end headless and prints all metrics above; full test suite still **87 passed** (no model code changed this task).

**Files touched:**
- `notebooks/02_model_validation.py` (created)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-8: holdout validation (result below target)`

### 2026-06-06 — P3.T7 — Combined prediction function

**Done:** Added `models/predict.predict_map_win_prob(match_id, map_index, live_state=None)`. Pre-match: posterior-mean `p` from the Bambi model on the point-in-time feature row (`sample_new_groups=True` handles holdout patches). Live: **log-odds pooling** `logit(post)=logit(prior)+logit(p_state)` (`combine_prior_and_state`) — SPEC Layer 4's "posterior ∝ prior × likelihood" (score-state table's implicit prior ≈0.5, so its odds = the likelihood ratio). bambi/arviz imported lazily so the pure math is CI-testable. Resources cached per db path. Added `tests/test_predict.py` (7 tests). Rule + scope in DEVIATIONS 2026-06-06.

**Learned or surprised:** Bambi posterior-predictive mean lives in `pred.posterior["p"]`. Pre-match prediction reuses the `build_training_data` point-in-time row, so it covers maps already in the warehouse; predicting an *upcoming* (unplayed) map needs an as-of-now feature builder → deferred to Phase 6. `live_state` is from team1's perspective.

**Verification:** `pytest tests/test_predict.py -q` → 7 passed (5 pure: roundtrip, neutral-state/neutral-prior identities, direction/monotonic, symmetry; 2 guarded integration: real-map 0<p<1 with up>pre>down, unknown-map raises). Full suite **87 passed**. Live `python -m models.predict --db data/prx.db` (latest PRX map 666493 Fracture): pre-match **0.334**; up 9-3 def **0.852**; down 3-9 def **0.065**; 0-0 start 0.322 (≈ prior).

**Files touched:**
- `models/predict.py` (created)
- `tests/test_predict.py` (created)
- `docs/DEVIATIONS.md` (modified — log-odds pooling + scope)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-7: combined prediction function`

### 2026-06-06 — P3.T6 — Score-state empirical lookup

**Done:** Added `models/score_state.compute_score_state(conn)` — walks each non-showmatch map's rounds in order, and at every pre-round state records two observations (`(half, team_score, opp_score, side)` from each team's perspective) labelled by whether that team won the **map**. Aggregates into `score_state_lookup` with Laplace-smoothed `(wins+5)/(obs+10)`. Full rebuild (idempotent); in-module `--db` CLI with spot-checks. Added `tests/test_score_state.py` (6 tests).

**Learned or surprised:** Win counted is the **map** outcome (not next-round), confirmed by the done-when example. Each round → 2 observations (both perspectives), so 135,348 obs = 2 × (67,799 − 125 showmatch) rounds. Included **'ot'** states too (the schema comment lists only first/second, but OT states are real and the live predictor will hit them) — minor completeness choice, column is unconstrained TEXT.

**Verification:** `pytest tests/test_score_state.py -q` → 6 passed (counts+symmetry, smoothing formula, cross-map accumulation, big-lead high / mirror low, showmatch exclusion, idempotent). Full suite **80 passed**. Live `python -m models.score_state --db data/prx.db` → 408 states; done-when spot-check **(second, 9-3, ct) = 0.920**; (first,0-0) 0.514/0.486; (second,3-9,ct)=0.121; (second,1-11,t)=0.083.

**Files touched:**
- `models/score_state.py` (created)
- `tests/test_score_state.py` (created)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-6: score-state empirical lookup`

### 2026-06-06 — P3.T5 — Fit Bambi logistic regression

**Done:** Added `models/bayes_logistic.py` — hierarchical Bernoulli logistic via Bambi: `team1_won ~ scale(elo_diff) + scale(map_elo_diff) + team1_starts_atk_or_def + scale(recent_form_team1/2) + scale(h2h_team1_win_rate) + C(tier) + (1|patch_id)`. Trains on maps ≤ 2025-03-02 (Bangkok end), 1381 rows; saves posterior to `models/saved/bayes_logistic.nc` (gitignored, regenerable) + arviz summary to `logs/bayes_logistic_fit.txt`. `build_model(train_df)` is reusable by P3.T7. Added `tests/test_bayes_logistic.py` (2 tests, `importorskip` — skipped in CI). Model spec + toolchain workaround in DEVIATIONS 2026-06-06.

**Learned or surprised:** **PyTensor's C backend can't link on this box** (msys64 g++ → `ld returned 116`), blocking PyMC; pure-Python (`cxx=`) was far too slow. Fixed by compiling via the **numba/LLVM backend** (`PYTENSOR_FLAGS=mode=NUMBA,cxx=`, set in-module before importing bambi; numba already in env) → full 4-chain fit in ~1 min. `map_elo_diff` (r=0.89 with `elo_diff`) is absorbed → coef ≈ 0; `elo_diff` carries team strength (0.28). Slight defense-start edge (−0.16). Patch σ ≈ 0.10 (patches barely differ).

**Verification:** Live fit `python -m models.bayes_logistic --db data/prx.db` → **max r̂ = 1.0000, 0 divergences (PASS, threshold 1.05)**; `elo_diff` 0.28 (94% HDI [0.08, 0.48]). `pytest tests/test_bayes_logistic.py -q` → 2 passed (split cutoff, model constructs). Full suite **74 passed**.

**Files touched:**
- `models/bayes_logistic.py` (created)
- `tests/test_bayes_logistic.py` (created)
- `models/saved/.gitkeep` (created), `.gitignore` (modified — ignore `models/saved/*.nc`)
- `docs/DEVIATIONS.md` (modified — model spec + numba workaround)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-5: bambi logistic fit (numba backend)`

### 2026-06-06 — P3.T4 — Training data builder for Bayesian regression

**Done:** Added `models/training_data.build_training_data(conn)` — a single chronological pass that emits one point-in-time feature row per competitive map: `elo_diff`, `map_elo_diff`, `team1_starts_atk_or_def`, `recent_form_team1/2`, `h2h_team1_win_rate`, `patch_id`, `tier`; target `team1_won`. State (Elo via `update_elo`, per-(team,map) win counts for offsets, last-5 form, EB-shrunk H2H) is snapshotted pre-match and advanced only after each match — no holdout leakage. In-module `--db` CLI. Added `tests/test_training_data.py` (8 tests). CI now installs `pandas`. Design choices in DEVIATIONS 2026-06-06.

**Learned or surprised:** "Row count matches map count" = 3197, not 3203 — the 6 gap is maps on **showmatch** matches (some showmatches *do* have maps), excluded like in P3.T2/T3. Only 1 map lacks round-1 data → side falls back to 0 (tracked in `df.attrs['side_fallbacks']`). Recompute Elo inline rather than reading `elo_ratings` (those snapshots are post-match/full-history → would leak).

**Verification:** `pytest tests/test_training_data.py -q` → 8 passed (neutral first match, target+side encoding, Elo/offset/H2H/form evolve pre-match, showmatch exclusion, side fallback, no-NaN). Full suite **72 passed**. Live `python -m models.training_data --db data/prx.db` → shape (3197, 15), **0 NaN**, team1_won mean 0.505; elo_diff std 66 (±240), h2h shrunk around 0.5 (std 0.12).

**Files touched:**
- `models/training_data.py` (created)
- `tests/test_training_data.py` (created)
- `.github/workflows/ci.yml` (modified — install pandas)
- `docs/DEVIATIONS.md` (modified — point-in-time / row-count note)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-4: point-in-time training data builder`

### 2026-06-06 — P3.T3 — Map-specific Elo offsets

**Done:** Added `models/elo_map_offsets.py` — `compute_map_offsets(conn, *, prior_games=10, elo_per_winrate=400)`: per (team, map) `raw_dev = map_wr − overall_wr`, partial-pooled toward 0 by sample size (`× games/(games+prior)`), converted to Elo points (`× 400`), written to `elo_map_offsets` as a single latest-date snapshot (full rebuild = idempotent). Showmatches excluded. Small `--db/--prior/--scale` CLI in-module. Added `tests/test_elo_map_offsets.py` (5 tests). Units conversion + the two constants logged in DEVIATIONS 2026-06-06.

**Learned or surprised:** "Offsets sum to ~0 per team" is exact only in *win-rate-weighted* space; the unweighted, shrunk, ×400 Elo sums are small but visible (PRX −45.8 Elo = −0.114 win-rate over 12 maps ≈ 1pp/map; worst team −84 Elo ≈ 1.8pp/map). Chose not to force-center (TASKS asks for pooling toward 0, not zero-mean) and to report transparently. PRX's offsets pass the eye test: Sunset +63 / Split +39 (strong), Ascent −37 / Corrode −35 (weak).

**Verification:** `pytest tests/test_elo_map_offsets.py -q` → 5 passed (sign + zero-sum on symmetric data, small-sample shrinkage, latest as_of_date, showmatch exclusion, idempotent rebuild). Full suite **64 passed**. Live `python -m models.elo_map_offsets --db data/prx.db` → 625 (team,map) offsets; **PRX has 12 maps** (done-when ≥5); per-team sums ~0 in win-rate space.

**Files touched:**
- `models/elo_map_offsets.py` (created)
- `tests/test_elo_map_offsets.py` (created)
- `docs/DEVIATIONS.md` (modified — units/constants note)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-3: map-specific elo offsets`

### 2026-06-06 — P3.T2 — Replay all matches to compute current Elo

**Done:** Added `models/elo_replay.py` — `replay_elo(conn, *, k, initial_rating)` reads completed matches in `(date_utc, match_id)` order, applies `models.elo.update_elo` per match, and rebuilds the `elo_ratings` table (daily snapshot per team; full DELETE-then-insert = idempotent). Showmatches excluded (`series_name LIKE 'Showmatch%'`). Added `scripts/build_elo.py` CLI (`--db/--k/--initial/--top`) that replays and prints top-N. Added `tests/test_elo_replay.py` (5 tests). Flat 1500 prior — region priors deferred (`teams.region` NULL; DEVIATIONS 2026-06-06).

**Learned or surprised:** All 1258 matches have non-zero scores, consistent `winner_id`, 0 NULL winners — no `ValueError`/skip cases beyond the 8 showmatches. A team that plays on two dates gets two snapshot rows (initial idempotency-test count was wrong; fixed). 1250 matches replayed (1258 − 8 showmatches), 55 teams rated.

**Verification:** `pytest tests/test_elo_replay.py -q` → 5 passed (zero-sum, fresh-team-at-1500, showmatch exclusion, same-day snapshot collapse, idempotent rebuild). Full suite **59 passed**. Live `python -m scripts.build_elo --db data/prx.db` → done-when met: **PRX #2 (1657), NRG #3 (1608), EDG #7 (1583), T1 #9 (1579), Sentinels #15 (1541)** all in top 15; G2 #1 (1670) plausible (2025–26 form).

**Files touched:**
- `models/elo_replay.py` (created)
- `scripts/build_elo.py` (created)
- `tests/test_elo_replay.py` (created)
- `docs/DEVIATIONS.md` (modified — flat-prior note)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-2: elo replay -> elo_ratings`

### 2026-06-06 — P3.T1 — Team Elo update logic

**Done:** Started Phase 3 (Rahat go-ahead). Added `models/elo.py` — pure, no-DB-I/O Elo math: `expected_score(a, b)` (standard logistic, 400 divisor) and `update_elo(rating_a, rating_b, score_a, score_b, k=24)` returning `(new_a, new_b)`. Actual outcome is **margin-of-victory** (`score_a/(score_a+score_b)`) per Rahat's choice this session (DEVIATIONS 2026-06-06); update is zero-sum; 0-0 raises `ValueError`. Added `tests/test_elo.py` (9 tests).

**Learned or surprised:** Nothing unexpected — the only open design point was binary vs margin-of-victory outcome (SPEC §6.2 only says "standard Elo, K=24"); Rahat chose margin-of-victory.

**Verification:** `pytest tests/test_elo.py -q` → 9 passed (win 1512/1488, loss 1488/1512, draw no-change, 2-0 > 2-1, zero-sum invariant, K override, expected_score, 0-0 ValueError). Full suite **54 passed**. `update_elo(1500,1500,2,0)` → `(1512.0, 1488.0)`.

**Files touched:**
- `models/elo.py` (created)
- `tests/test_elo.py` (created)
- `docs/DEVIATIONS.md` (modified — margin-of-victory note)
- `docs/PROGRESS.md` (modified — current state + this entry)

**Commit:** `<pending>` — `phase-3.task-1: team elo update logic`

### 2026-06-06 12:25 UTC — P0.T3–T7 — Deferred Phase 0 validation (reframed) + tag

**Done:** Resumed the deferred Phase 0 validation against the warehouse (Rahat-approved reframe — no per-round loadout, DEVIATIONS 2026-06-06). Added two marimo notebooks: `00_round_eda.py` (round/economy EDA) and `01_round_baseline.py` (round-winner logistic). Wrote the Phase 0 summary; tagging `v0.1.0-phase-0`.

**Learned or surprised:** vlrggapi exposes no per-round loadout (Peng's exact model unbuildable). Loadout signal validated descriptively (eco 42.7% vs buys ~54%). Side non-predictive (~50.3/50.7%). Fitted side+score-state logistic = **55.4%** test accuracy (vs 50.1% majority; lift from `score_diff`), short of Peng's 60.6% — the gap is the unavailable loadout signal, confirming Peng's thesis.

**Verification:** `python notebooks/00_round_eda.py` and `…/01_round_baseline.py` both run end-to-end headless; full suite 45 passed.

**Files touched:**
- `notebooks/00_round_eda.py`, `notebooks/01_round_baseline.py` (created)
- `.gitignore` (modified — marimo artifacts), `docs/DEVIATIONS.md` (reframe entry)
- `docs/PROGRESS.md` (Phase 0 summary + this entry)

**Commit:** `913d3f0` — `phase-0.task-3-7: round-level validation (reframed) + tag`

### 2026-06-05 00:32 UTC — P2.T11 (2026) + P2.T14 — Phase 2 complete

**Done:** **T11 — 2026 bulk complete** after fixing the date bug: 13 events, 318 matches, 821 maps, 17,424 rounds, 8,210 player_stats, 276 players resolved, 864 roster rows, 0 failures. Re-ran the patch backfill over all matches (1,258 updated, **0 NULL**). **T14 — Phase 2 summary written + tagging `v0.1.0-phase-2`.**

**Root cause of the 2026 "0 matches":** not the circuit breaker — vlr omits the year in `/v2/match/details` dates for current-year matches (`'Thursday, January 15 … Patch 12.0'`), so `parse_match_date` skipped all 318. Fixed by using the `/v2/events/matches` listing date (carries the year). Commit `dcc76db`. The cached match data made the fixed re-run near-instant.

**Final warehouse (2024–2026, FK clean):** 43 events, 1,258 matches, 3,203 maps, 67,799 rounds, 32,030 map_player_stats, 4,862 economy, 69 teams, 505 players, 864 roster, 142 patches. Completeness 100/99.8/100% per year. 391 stat rows (1.2%) unresolved player_id; 2 showmatch matches w/0 maps; 3 incomplete maps.

**Verification:** `scripts/validate_ingestion.py` report (`logs/ingestion_validation.txt`): 0 NULL winner, 0 NULL patch, FK check empty. Full test suite 45 passed.

**Files touched:**
- `docs/PROGRESS.md` (Phase 2 summary + current state + this entry)

**Commit:** `e0cff4f` — `phase-2.task-14: phase 2 summary + tag`; tag `v0.1.0-phase-2`

### 2026-06-04 23:35 UTC — P2.T10 done (2025); T11 (2026) failed on upstream circuit breaker; bulk resilience fix

**Done:** **P2.T10 — 2025 bulk complete:** 15 events, 504 matches, 1,277 maps, 26,974 rounds, 12,770 player_stats, 331 players resolved (24 unresolved), 709 roster rows; 1 detail_failure. All 15 2025 events have matches. Warehouse now spans 2024+2025: 940 matches, 2,382 maps, 50,375 rounds, 23,820 player_stats, 421 players.

**P2.T11 — 2026 FAILED (0 ingested):** vlrggapi's **circuit breaker to vlr.gg tripped** after hours of sustained load — `/v2/events/matches` returns `503 "Circuit open for www.vlr.gg — request blocked"`. The 2026 run got 0 matches (first events returned empty listings as the breaker began tripping; event 2863 then raised and aborted the year).

**Bug fixed:** `scripts/bulk_ingest.py` did not guard the per-event `ingest_event_matches` call (only the details loop), so one event's transient failure aborted the whole year. Now wrapped in try/except → logs `event_failed`, increments `event_failures`, and continues. (compile + 43 tests green.)

**Next:** re-run 2026 after a vlr.gg cooldown (container stopped to let upstream recover). `python -m scripts.bulk_ingest --year 2026 --db data/prx.db --skip-events`. The cache + resilience fix make this safe/resumable.

**Files touched:**
- `scripts/bulk_ingest.py` (modified — per-event try/except, `event_failures`)

**Commit:** `3dd8e0a` — `fix(bulk): don't abort the year on one event's failure`

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
