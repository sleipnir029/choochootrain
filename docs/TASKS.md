# TASKS.md

Granular task list for Claude Code, organized by phase. Follow in order. Don't skip ahead.

**Format for each task:**
- **ID:** P{phase}.T{task}
- **What:** clear action
- **Touch:** files Claude Code is expected to create or edit
- **Don't touch:** files outside this task's scope
- **Done when:** verifiable definition of completion

**Global "don't touch" rule:** never edit files belonging to a later phase, never modify `PRX_PREDICTOR_SPEC.md` or `CLAUDE.md`, never edit anything in `docs/` except via the documented update protocol.

---

## Phase 0 — Peng dataset validation

**Goal:** prove the modeling toolchain on a known-clean public dataset before touching vlrggapi.
**Estimated effort:** 1 day.

### P0.T1 — Bootstrap Python environment
- **What:** Create Python 3.11 venv. Install pinned versions of: pandas, numpy, scikit-learn, statsmodels, bambi, jupyterlab, pytest, structlog, httpx.
- **Touch:** `.python-version`, `pyproject.toml` or `requirements.txt`, `README.md` (one-line setup instructions)
- **Don't touch:** any source file
- **Done when:** `pip install` completes in a fresh venv with no resolver conflicts; `python -c "import bambi"` succeeds.

### P0.T2 — Download Peng IEEE DataPort dataset
- **What:** Download the "Valorant Champions Tour 2024: Pacific and EMEA Round Data" dataset from IEEE DataPort. Save raw file to `data/external/peng_2024.csv` (or `.xlsx`, whichever the source provides).
- **Touch:** `data/external/peng_2024.{csv,xlsx}`, `.gitignore` (add `data/external/` if files are large)
- **Don't touch:** anything in `/data/prx.db`
- **Done when:** file exists, expected row count ~1,301.

### P0.T3 — EDA notebook with data inspection
- **What:** Create `notebooks/00_peng_eda.ipynb`. Load dataset, show column dtypes, missing values, basic descriptives, target balance.
- **Touch:** `notebooks/00_peng_eda.ipynb`
- **Don't touch:** main source code
- **Done when:** notebook runs end-to-end; markdown cells document each finding in one line.

### P0.T4 — Clean and reshape into features + target
- **What:** Build a clean DataFrame with three features (team loadout diff, ult availability diff, ult points diff) + target (round_won). Handle NaN rows per the dataset notes.
- **Touch:** `notebooks/01_peng_baseline.ipynb`
- **Done when:** DataFrame shape printed; no NaN in the kept rows; target balance shown.

### P0.T5 — Fit baseline logistic regression
- **What:** Train sklearn `LogisticRegression` on the three features. 70/30 time-aware split if dataset includes dates; otherwise random with seed=42.
- **Touch:** same notebook as T4
- **Done when:** model fit; coefficients printed; sign and magnitude of teamLO coef checked against Peng (should dominate).

### P0.T6 — Compute test accuracy on holdout
- **What:** Report accuracy on holdout. Target: ~60% (Peng reported 60.61%).
- **Touch:** same notebook
- **Done when:** accuracy printed; if below 55% or above 65%, investigate before claiming pass.

### P0.T7 — Phase summary
- **What:** Update `docs/PROGRESS.md` with phase summary; commit notebooks; tag `v0.1.0-phase-0`.
- **Touch:** `docs/PROGRESS.md`
- **Done when:** PROGRESS.md updated; git tag exists.

---

## Phase 1 — Self-host vlrggapi

**Goal:** vlrggapi runs locally in Docker, repo skeleton exists, CI builds clean.
**Estimated effort:** 1 day.

### P1.T1 — Vendor vlrggapi
- **What:** Add vlrggapi as a git submodule pinned to a specific commit, OR copy its source into `vendor/vlrggapi/` with a `VERSION.txt` recording the source commit. Submodule preferred — easier to update.
- **Touch:** `.gitmodules` (if submodule) or `vendor/vlrggapi/`, `vendor/vlrggapi/VERSION.txt`
- **Done when:** can build vlrggapi locally from the vendored source.

### P1.T2 — Build vlrggapi Docker image locally
- **What:** `docker build` the vlrggapi image. Use upstream's Dockerfile. Run with `docker run -p 3001:3001`.
- **Touch:** nothing new (upstream provides Dockerfile)
- **Done when:** `curl http://localhost:3001/v2/health` returns healthy status for both vlrggapi and vlr.gg upstream.

### P1.T3 — Smoke-test the endpoints we'll rely on
- **What:** Hit `/v2/team?id=624` (PRX), `/v2/team/matches?id=624&page=1`, `/v2/match/details?match_id={any-recent-id}`, `/v2/match?q=live_score`. Verify expected fields are present in each response.
- **Touch:** create `scripts/smoke_vlrggapi.sh` or `scripts/smoke_vlrggapi.py` — a small ad-hoc tester
- **Done when:** all four endpoints return data with the fields documented in ARCHITECTURE.md.

### P1.T4 — Initialize project repo skeleton
- **What:** Create empty folder structure per CLAUDE.md "Repo layout". Add `.gitignore`, `LICENSE` (MIT), `README.md`.
- **Touch:** all top-level folders (empty `__init__.py` placeholders), `.gitignore`, `LICENSE`, `README.md`
- **Don't touch:** source files in the folders (those come in Phase 2+)
- **Done when:** `tree` shows the layout from CLAUDE.md; repo is clean for git.

### P1.T5 — GitHub repo + initial push
- **What:** Create remote `prx-predictor` repo on GitHub (private). Push main branch.
- **Touch:** `.git/` (via git operations)
- **Done when:** repo visible on GitHub with initial structure.

### P1.T6 — CI workflow stub
- **What:** `.github/workflows/ci.yml` — runs pytest (no tests yet, just placeholder), checks Python syntax, builds the prx-app Docker image (doesn't push yet). Triggered on push to main.
- **Touch:** `.github/workflows/ci.yml`, `docker/Dockerfile` (minimal stub: FROM python:3.11-slim, COPY requirements, that's it)
- **Don't touch:** GHCR push workflow (Phase 8)
- **Done when:** CI passes on a no-op push.

### P1.T7 — Combined docker-compose dry-run
- **What:** `docker/docker-compose.yml` with two services: `vlrggapi` and `prx-app` (stub). Network them together. Start both, verify they can talk.
- **Touch:** `docker/docker-compose.yml`, `docker/Dockerfile` (prx-app stub: just a FastAPI hello-world)
- **Done when:** `docker compose up` runs both; from inside prx-app container, `curl http://vlrggapi:3001/v2/health` works.

### P1.T8 — Phase summary
- **What:** Update PROGRESS.md, git tag.
- **Touch:** `docs/PROGRESS.md`
- **Done when:** PROGRESS.md updated; tag `v0.1.0-phase-1`.

---

## Phase 2 — Schema + bulk ingestion

**Goal:** SQLite warehouse populated with all tier-1 matches 2024 → present.
**Estimated effort:** 2–3 days.

### P2.T1 — Implement SQLite schema
- **What:** Create `ingestion/schema.py` that defines the DDL from `docs/ARCHITECTURE.md`. Function `init_db(path)` creates the file and runs all CREATE TABLE statements.
- **Touch:** `ingestion/schema.py`
- **Done when:** running `python -m ingestion.schema init data/prx.db` creates a SQLite file with all tables from ARCHITECTURE.md, no errors.

### P2.T2 — Base HTTP client for vlrggapi
- **What:** `ingestion/vlr_client.py` — thin async httpx wrapper. Reads base URL from env (`VLRGGAPI_URL`, default `http://localhost:3001`). Handles retries (3x with backoff), rate limit awareness (sleep on 429), structured logging.
- **Touch:** `ingestion/vlr_client.py`
- **Done when:** smoke test in P1.T3 can be rewritten using this client; passes.

### P2.T3 — Teams ingestion (idempotent)
- **What:** `ingestion/teams.py` — given a list of vlr team IDs, fetches `/v2/team` for each, upserts into `teams` table.
- **Touch:** `ingestion/teams.py`, `tests/test_teams_ingestion.py`
- **Done when:** running twice produces the same row counts (upsert works); PRX (id=624) exists with correct fields.

### P2.T4 — Events ingestion
- **What:** `ingestion/events.py` — fetches `/v2/events` (both `q=upcoming` and `q=completed`), filters to tier-1 (Masters, Champions, Regional League Kickoff/Stage 1/Stage 2 from 2024–present), upserts.
- **Touch:** `ingestion/events.py`, `tests/test_events_ingestion.py`
- **Done when:** events table contains the events listed in SPEC section 4 (verify Masters Madrid 2024 through Masters London 2026 are all present).

### P2.T5 — Matches ingestion (per event)
- **What:** `ingestion/matches.py` — for each event in events table, fetches `/v2/events/matches?event_id={id}`, upserts into matches table. Handles missing optional fields gracefully.
- **Touch:** `ingestion/matches.py`, `tests/test_matches_ingestion.py`
- **Done when:** matches table populated; row count is in the expected 800–1,500 range.

### P2.T6 — Match details ingestion
- **What:** `ingestion/match_details.py` — for each match_id, fetches `/v2/match/details`, populates `maps`, `rounds`, `map_player_stats`, `map_team_economy` tables. Sets `is_rounds_complete=1` only if the rounds array length equals expected.
- **Touch:** `ingestion/match_details.py`, `tests/test_match_details.py`
- **Done when:** for a known recent PRX match, all four downstream tables have the right rows; `is_rounds_complete` is true for most maps.

### P2.T7 — Player profile ingestion
- **What:** `ingestion/players.py` — extracts player_ids from `map_player_stats`, fetches `/v2/player?id={id}` for each, upserts into players table.
- **Touch:** `ingestion/players.py`, `tests/test_players_ingestion.py`
- **Done when:** all players appearing in any match are in the players table with handle + real_name.

### P2.T8 — Roster history ingestion
- **What:** `ingestion/roster_history.py` — for each tier-1 team, fetches `/v2/team/transactions`, parses into `roster_history` rows. Handles open-ended (left_date=NULL) for active roster members.
- **Touch:** `ingestion/roster_history.py`, `tests/test_roster_history.py`
- **Done when:** querying "who was on PRX on 2025-06-22" (Masters Toronto final) returns: f0rsakeN, Jinggg, d4v41, something, PatMen.

### P2.T9 — Bulk pull: 2024
- **What:** Run the full ingestion pipeline for all 2024 events. Log progress, errors, skipped matches with reasons. Save the log.
- **Touch:** `scripts/bulk_ingest.py`, `logs/bulk_ingest_2024.log`
- **Done when:** all 2024 tier-1 events processed; row counts logged; no fatal errors.

### P2.T10 — Bulk pull: 2025
- **What:** Same as T9 but for 2025.
- **Touch:** `scripts/bulk_ingest.py` (already exists), `logs/bulk_ingest_2025.log`
- **Done when:** 2025 done; Masters Toronto 2025 is in the DB with PRX as winner.

### P2.T11 — Bulk pull: 2026 to date
- **What:** Same as T9 but for 2026.
- **Touch:** `logs/bulk_ingest_2026.log`
- **Done when:** 2026 events through Masters Santiago + Pacific Stage 1 are ingested.

### P2.T12 — Ingestion validation
- **What:** Write a validation script that checks: every match has at least one map, every map has player_stats rows, rounds completeness rate per year. Print summary.
- **Touch:** `scripts/validate_ingestion.py`
- **Done when:** summary report saved to `logs/ingestion_validation.txt`; any anomalies noted in DEVIATIONS.md.

### P2.T13 — Date→patch lookup
- **What:** `ingestion/patches.py` — scrapes Riot's patch notes index (https://playvalorant.com/en-us/news/tags/patch-notes/), builds a `data/patches.json` with patch_id, release_date. Populate `patches` table. Backfill `matches.patch_id` based on date.
- **Touch:** `ingestion/patches.py`, `data/patches.json`
- **Done when:** patches table contains all patches from 2024 onward; every match has a non-NULL patch_id.

### P2.T14 — Phase summary
- **What:** Update PROGRESS.md with: total matches ingested, total maps, total rounds, rounds-completeness rate per year, any data quality issues.
- **Touch:** `docs/PROGRESS.md`
- **Done when:** summary written; git tag `v0.1.0-phase-2`.

---

## Phase 3 — Statistical modeling

**Goal:** team Elo + map-specific offsets + Bayesian pre-match logistic + score-state empirical lookup, validated on holdout.
**Estimated effort:** 3–5 days.

### P3.T1 — Team Elo update logic
- **What:** `models/elo.py` — pure functions: `update_elo(rating_a, rating_b, score_a, score_b, k)`. K-factor configurable. No DB I/O in this file.
- **Touch:** `models/elo.py`, `tests/test_elo.py`
- **Done when:** unit tests pass (3 manual cases: win, loss, draw if applicable).

### P3.T2 — Replay all matches to compute current Elo
- **What:** `models/elo_replay.py` — iterates matches chronologically, calls update_elo, writes `elo_ratings` table at each step. Initial rating per region: 1500 (configurable).
- **Touch:** `models/elo_replay.py`, `scripts/build_elo.py`
- **Done when:** running script populates elo_ratings; final rating of top 5 teams looks plausible (PRX, NRG, Sentinels, T1, EDG all in top ~15).

### P3.T3 — Map-specific Elo offsets
- **What:** `models/elo_map_offsets.py` — for each (team, map), compute deviation between team's win rate on that map vs overall win rate; smooth using partial pooling toward 0. Write to `elo_map_offsets` table.
- **Touch:** `models/elo_map_offsets.py`
- **Done when:** PRX has offsets for at least 5 maps; offsets sum to roughly 0 per team.

### P3.T4 — Training data builder for Bayesian regression
- **What:** `models/training_data.py` — for each historical map, build a feature row: elo_diff, map_elo_diff, team1_starts_atk_or_def, recent_form_team1, recent_form_team2, h2h_team1_win_rate, patch_id, tier. Target: did team1 win this map.
- **Touch:** `models/training_data.py`
- **Done when:** DataFrame produced; no NaN; row count matches map count in DB.

### P3.T5 — Fit Bambi logistic regression
- **What:** `models/bayes_logistic.py` — fits a Bambi formula model with the features above. Train on data through end of Masters Bangkok 2025; hold out everything after.
- **Touch:** `models/bayes_logistic.py`, `models/saved/bayes_logistic.nc` (saved posterior trace)
- **Done when:** model converges (r_hat < 1.05 for all params); summary written to log.

### P3.T6 — Score-state empirical lookup
- **What:** `models/score_state.py` — for each unique (half, team_score, opp_score, side), count wins and observations from historical rounds data. Apply Laplace smoothing (add 5 to numerator and 10 to denominator). Write to `score_state_lookup` table.
- **Touch:** `models/score_state.py`
- **Done when:** table populated; spot-check a few cells (e.g., team up 9-3 at half on defense should have a high smoothed_win_pct).

### P3.T7 — Combined prediction function
- **What:** `models/predict.py` — `predict_map_win_prob(match_id, map_index, live_state=None)`. If live_state is None: pre-match prediction only (Bayes logistic). If live_state provided: Bayesian update combining pre-match prior + score_state lookup.
- **Touch:** `models/predict.py`, `tests/test_predict.py`
- **Done when:** unit tests pass; sample call for a known match returns a sensible prediction.

### P3.T8 — Validation on holdout
- **What:** Run predictions on all maps from Masters Toronto 2025 + Masters Santiago 2026. Report: accuracy, Brier score, calibration plot. Compare against Peng baseline.
- **Touch:** `notebooks/02_model_validation.ipynb`
- **Done when:** notebook produces accuracy/Brier numbers; results recorded in PROGRESS.md.

### P3.T9 — Phase summary
- **What:** Phase summary in PROGRESS.md with the accuracy numbers, what surprised, any deviations.
- **Touch:** `docs/PROGRESS.md`
- **Done when:** summary written; git tag `v0.1.0-phase-3`.

---

## Phase 4 — Player skill layer

**Goal:** TrueSkill-style ratings per (player, agent, map); expected-vs-actual stat tracking.
**Estimated effort:** 2 days.

### P4.T1 — TrueSkill integration
- **What:** Use the `trueskill` PyPI library. Wrapper in `models/player_skill.py`. Function: `update_skill(player_id, agent, map_name, performance_score, opponent_skill)`.
- **Touch:** `models/player_skill.py`, `tests/test_player_skill.py`
- **Done when:** unit tests for update logic pass.

### P4.T2 — Replay to compute current skills
- **What:** `scripts/build_player_skill.py` — iterate all map_player_stats chronologically, compute performance score (e.g., normalized ACS vs opponent average), update skills.
- **Touch:** `scripts/build_player_skill.py`
- **Done when:** player_skill table populated for all players with ≥10 maps.

### P4.T3 — Expected stats prediction
- **What:** `models/expected_stats.py` — given an upcoming match, predicts each player's expected ACS/K/D/A based on their skill + opponent + map.
- **Touch:** `models/expected_stats.py`
- **Done when:** for a known match, predicted ACS is within ±30 of actual on average across 10 players.

### P4.T4 — Validation
- **What:** Compare predicted vs actual on the Masters Toronto 2025 holdout. Report mean error per stat.
- **Touch:** `notebooks/03_player_skill_validation.ipynb`
- **Done when:** notebook produces error metrics; results in PROGRESS.md.

### P4.T5 — Phase summary
- **Touch:** `docs/PROGRESS.md`
- **Done when:** summary written; git tag `v0.1.0-phase-4`.

---

## Phase 5 — Live update logic

**Goal:** detect any live tier-1 match, poll its state, trigger re-prediction on score change.
**Estimated effort:** 1–2 days.

### P5.T1 — Live score poller
- **What:** `scheduler/jobs/live_poll.py` — polls `/v2/match?q=live_score` every 30s when any tier-1 match is live, else idles. Writes current state to an in-memory cache (or `live_state` SQLite table — choose one and document).
- **Touch:** `scheduler/jobs/live_poll.py`
- **Done when:** running standalone, the poller logs every score change for a live match.

### P5.T2 — Score-change detection
- **What:** Compare current state to last cached state. Trigger callback on any change to (team1_score, team2_score, team1_round_ct/t, team2_round_ct/t, current_map).
- **Touch:** same file
- **Done when:** simulated test with two fake states fires callback exactly once per change.

### P5.T3 — Hook score-change to re-prediction
- **What:** On detected change, call `models.predict.predict_map_win_prob` with live_state. Write result to a `live_predictions` table (or in-memory cache, again — pick one and document).
- **Touch:** `scheduler/jobs/live_poll.py`, possibly schema add for `live_predictions`
- **Done when:** for a simulated live match, predictions are recomputed and stored on each score change.

### P5.T4 — Priority logic for multiple live matches
- **What:** If multiple tier-1 matches are live, pick one to track first: PRX > Champions > Masters > Regional League > earliest start time.
- **Touch:** `scheduler/jobs/live_poll.py`
- **Done when:** unit test with synthetic live-match list returns the expected winner.

### P5.T5 — Phase summary
- **Touch:** `docs/PROGRESS.md`
- **Done when:** git tag `v0.1.0-phase-5`.

---

## Phase 6 — FastAPI + React dashboard

**Goal:** prediction API + working dashboard on second monitor.
**Estimated effort:** 3 days.

### P6.T1 — API contract draft
- **What:** Write the endpoint contracts to `docs/ARCHITECTURE.md` (or confirm what's there is accurate). Each endpoint: path, params, response shape.
- **Touch:** `docs/ARCHITECTURE.md`
- **Done when:** all endpoints needed for the dashboard are documented.

### P6.T2 — FastAPI server
- **What:** `api/main.py` — implements all endpoints from T1. Reads from SQLite, calls models. CORS enabled for localhost frontend.
- **Touch:** `api/main.py`, `api/routes/*.py` (one file per resource: matches, teams, players, predict, llm)
- **Done when:** all endpoints return data; OpenAPI docs at `/docs` look right.

### P6.T3 — React + Vite project setup
- **What:** In `dashboard/`, run `npm create vite@latest . -- --template react-ts`. Add Recharts, axios.
- **Touch:** `dashboard/package.json`, `dashboard/vite.config.ts`, all generated files
- **Done when:** `npm run dev` serves a hello-world page.

### P6.T4 — App shell
- **What:** Top bar (mode indicator + manual switcher), main panel container, dark mode default.
- **Touch:** `dashboard/src/App.tsx`, `dashboard/src/components/Layout.tsx`
- **Done when:** shell renders; mode switcher toggles state but doesn't yet route to panels.

### P6.T5 — Pre-match panel
- **What:** Component that calls `/api/predict/pre-match`, displays team logos, win prob bar, per-map win probs, top factor breakdown.
- **Touch:** `dashboard/src/components/PreMatchPanel.tsx`
- **Done when:** given a known match_id, renders correctly with real data.

### P6.T6 — Live panel
- **What:** Component that polls `/api/predict/live` every 30s, displays current score, side, live win prob with a sparkline of probability over rounds.
- **Touch:** `dashboard/src/components/LivePanel.tsx`
- **Done when:** polls every 30s; sparkline updates on score change.

### P6.T7 — Player stats panel
- **What:** Per-player view: current team, career K/D/A, breakdown by team stint (per D2 in SPEC). Recharts bar chart for per-map performance.
- **Touch:** `dashboard/src/components/PlayerPanel.tsx`
- **Done when:** loading PatMen's profile shows both his current GE stats and his prior PRX stint.

### P6.T8 — Post-match replay panel
- **What:** Round-by-round prediction trace using `/api/predict/replay`. Line chart of probability across rounds.
- **Touch:** `dashboard/src/components/ReplayPanel.tsx`
- **Done when:** for a completed match, the chart shows probability evolution and lines up with actual outcomes.

### P6.T9 — Default view auto-detect logic
- **What:** Implements D3 from SPEC. On mount, hits `/api/predict/live`; if a tier-1 match is live, shows LivePanel; else shows PreMatchPanel for PRX's next match.
- **Touch:** `dashboard/src/App.tsx`
- **Done when:** simulating both states (live present / absent) shows the right panel.

### P6.T10 — Build + serve from FastAPI
- **What:** `npm run build` produces static files. FastAPI mounts `dashboard/dist` as static. Accessing `/` serves the React app.
- **Touch:** `api/main.py` (add StaticFiles), `docker/Dockerfile` (add Node build stage)
- **Done when:** `docker compose up` serves the dashboard at `http://localhost:8000/`.

### P6.T11 — Phase summary
- **Touch:** `docs/PROGRESS.md`
- **Done when:** git tag `v0.1.0-phase-6`.

---

## Phase 7 — LLM adapter

**Goal:** prediction explanations + chat-on-data interface using DeepSeek V4 Flash.
**Estimated effort:** 2 days.

### P7.T1 — DeepSeek client
- **What:** `llm/deepseek_client.py` — async httpx wrapper around DeepSeek's OpenAI-compatible endpoint. Reads `DEEPSEEK_API_KEY` from env. Handles errors, retries.
- **Touch:** `llm/deepseek_client.py`, `.env.example`
- **Done when:** smoke test with "say hello" returns text response.

### P7.T2 — Cost guardrails
- **What:** Token counter (tiktoken), per-request input/output limits (5000/1500), daily budget cap ($1) checked from a `data/llm_usage.json` file.
- **Touch:** `llm/budget.py`
- **Done when:** crossing the cap raises an exception with a clear message.

### P7.T3 — Prediction explanation endpoint
- **What:** `POST /api/llm/explain` — takes prediction context (match info, prediction, top factors), prompts LLM to generate ~3-sentence natural language explanation.
- **Touch:** `api/routes/llm.py`, `llm/prompts/explain.py`
- **Done when:** for a pre-match prediction, the LLM returns a sentence referencing the actual factors (not hallucinated).

### P7.T4 — Chat-on-data endpoint
- **What:** `POST /api/llm/chat` — takes a natural language question, LLM writes SQL against documented schema, SQL runs, LLM summarizes result. Document the schema in the prompt template.
- **Touch:** `api/routes/llm.py`, `llm/prompts/chat.py`, `llm/sql_executor.py` (safe SQL: SELECT only, no DDL/DML)
- **Done when:** "How does Jinggg perform on Bind?" returns a sensible answer with real numbers.

### P7.T5 — Phase summary
- **Touch:** `docs/PROGRESS.md`
- **Done when:** git tag `v0.1.0-phase-7`.

---

## Phase 8 — Deployment

**Goal:** image builds in CI, pushes to GHCR, pulls cleanly on Rahat's PC, runs end-to-end.
**Estimated effort:** 1 day.

### P8.T1 — Finalize docker-compose
- **What:** Two services with health checks, restart policies, volume mounts for `data/`, `.env` env file.
- **Touch:** `docker/docker-compose.yml`, `.env.example`
- **Done when:** `docker compose up -d` runs cleanly; `docker compose logs` shows both services healthy.

### P8.T2 — GHCR push workflow
- **What:** `.github/workflows/release.yml` — on tag push (`v*`), builds prx-app image, pushes to `ghcr.io/<user>/prx-predictor:<tag>` and `:latest`.
- **Touch:** `.github/workflows/release.yml`
- **Done when:** pushing a test tag triggers build and successful push to GHCR.

### P8.T3 — Deployment runbook
- **What:** `README.md` section: prerequisites, how to pull, how to set env vars, how to start, how to stop, how to update.
- **Touch:** `README.md`
- **Done when:** Rahat can follow the README without asking questions.

### P8.T4 — End-to-end test on Rahat's PC
- **What:** Pull image from GHCR. Run. Open dashboard from phone on the same LAN. Verify all panels.
- **Touch:** none in repo; manual test
- **Done when:** Rahat confirms it works from his phone browser.

### P8.T5 — Phase summary + v1 release tag
- **Touch:** `docs/PROGRESS.md`
- **Done when:** PROGRESS.md updated; git tag `v1.0.0`.

---

## Phase 9 — Tier-2 evaluation (POST-V1, not part of v1 build)

**Goal:** decide if rib.gg integration is worth pursuing for a v2.
**Estimated effort:** 0 days during v1. Revisit after 2–3 months of v1 use.

Do not start this phase as part of the v1 build. After v1 has been in use for 2–3 months and you have measured accuracy on at least 30+ live matches, open a planning session with Rahat to decide whether to proceed.
