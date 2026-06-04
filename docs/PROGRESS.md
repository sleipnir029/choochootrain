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
**Last completed task:** none (project not started)
**Next task:** P0.T1 — Bootstrap Python environment
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
