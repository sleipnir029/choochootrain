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

**Phase:** 0
**Last completed task:** P0.T1 — Bootstrap Python environment
**Next task:** P0.T2 — Download Peng IEEE DataPort dataset
**Open blockers:** none

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
