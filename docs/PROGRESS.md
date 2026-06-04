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

**Phase:** 1 (pulled forward) — Phase 0 validation (T2–T6) deferred, see DEVIATIONS 2026-06-04
**Last completed task:** P1.T6 — CI workflow stub
**Next task:** P1.T7 — Combined docker-compose dry-run
**Open blockers:** Peng IEEE dataset is paywalled/unobtainable; Phase 0 validation will resume after Phase 1, loadout-only from vlr.gg

---

## Phase summaries

### Phase 0 — Peng dataset validation
*To be filled in after Phase 0 complete*

### Phase 1 — Self-host vlrggapi
*Locked until Phase 0 complete*

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
