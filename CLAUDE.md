# CLAUDE.md

**Project:** PRX Predictor — Valorant match prediction system focused on Paper Rex, league-wide data layer.

**Source of truth:** `PRX_PREDICTOR_SPEC.md` (in repo root). Architecture decisions live there. Don't re-derive what's already decided.

---

## Working principles

Apply by default. These are inspired by Karpathy's practice and standard software engineering. Re-read this before each session.

### 1. Read before writing

Always `view` a file before editing it. If you've already edited the file this session, view it again — your earlier view is stale after any `str_replace`.

### 2. Surgical changes

One file, one purpose per edit. If you notice an unrelated bug or inconsistency, write it down in `docs/DEVIATIONS.md` and keep moving. Don't refactor on the way through.

### 3. Minimal code

The best code is no code. The next best is the smallest code that solves the task. Don't add abstractions until you have a second concrete use case. Don't write classes when functions suffice. Don't add config knobs until something needs them.

### 4. Verify each step

Build → run → observe → next. Don't write 200 lines and pray. After every edit, run something to confirm the behavior is what you expected. Print intermediate state. If you're guessing, you're wrong.

### 5. Don't refactor without reason

If existing code works, leave it. "Cleaning up" introduces bugs and consumes tokens. Only refactor when the existing structure actively blocks the current task.

### 6. YAGNI

You aren't gonna need it. No "we might want this later" — only what's in the current task. Future requirements are future work.

### 7. Explicit > implicit

No magic. No global state. No clever metaclasses. Boring code is good code. If you have to think hard to explain it, simplify it.

### 8. Decompose before coding

If a task feels big, write the decomposition into `docs/PROGRESS.md` first. List the sub-steps. Then code one at a time. Big edits without a plan produce bugs.

### 9. Read the SPEC for design decisions

`PRX_PREDICTOR_SPEC.md` already resolved patch handling (D1), player stat scope (D2), and dashboard default view (D3). Don't reopen those. If a decision isn't in the SPEC and isn't obvious, stop and ask.

### 10. Print/log to inspect

When something doesn't work, the first move is a print statement or log line. Don't guess. Observe state. Reproduce the bug deterministically before fixing it.

---

## Session protocol

### Start of session
1. Read `CLAUDE.md` (this file)
2. Read `docs/PROGRESS.md` — find the last 3 entries to see where you left off
3. Read `docs/DEVIATIONS.md` — see what's been adjusted from spec
4. Read the current phase section of `docs/TASKS.md`
5. State which task you're starting before any code: "Starting P{X}.T{Y}: <description>"

### During a task
- View files before editing them
- Make the smallest change that completes the task
- Run / test after each edit
- If you discover something that contradicts the SPEC, STOP and add an entry to `docs/DEVIATIONS.md` before continuing
- If you're blocked or the SPEC is ambiguous, ask Rahat. Don't guess.

### End of a task
1. Append an entry to `docs/PROGRESS.md` (newest at top under "Entries"): what was done, what was learned, files touched, commit SHA
2. Git commit with format: `phase-{X}.task-{Y}: <short description>`
3. State the next task

### End of a phase
1. Write a phase summary at the top of that phase's section in `docs/PROGRESS.md` (3–5 bullets: what was built, what's working, what's pending, accuracy/numbers if applicable)
2. Update the "Current state" block at the top of PROGRESS.md
3. Don't auto-start the next phase — wait for Rahat's go-ahead

---

## Repo layout

```
/
├── CLAUDE.md                          ← this file
├── PRX_PREDICTOR_SPEC.md              ← source of truth for design decisions
├── docs/
│   ├── TASKS.md                       ← phased task list, follow in order
│   ├── ARCHITECTURE.md                ← DB schema, API contract, service wiring
│   ├── SCHEDULER.md                   ← scheduled jobs configuration
│   ├── PROGRESS.md                    ← running log; update after every task
│   ├── DEVIATIONS.md                  ← deviations from spec, with reasoning
│   └── MARIMO_CONVENTIONS.md          ← how to write marimo notebooks (read before touching any .py in notebooks/)
├── notebooks/                         ← marimo notebooks (.py files; NOT .ipynb)
├── ingestion/                         ← vlrggapi → SQLite pipeline (Phase 2)
├── models/                            ← Elo, Bayesian regression, score-state (Phase 3-4)
├── api/                               ← FastAPI prediction service (Phase 6)
├── dashboard/                         ← React + Vite frontend (Phase 6)
├── llm/                               ← DeepSeek adapter (Phase 7)
├── scheduler/                         ← APScheduler jobs (Phase 5)
├── data/
│   ├── prx.db                         ← SQLite warehouse
│   └── patches.json                   ← date→patch lookup
├── tests/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── .github/workflows/                 ← CI: build + push to GHCR
```

---

## Tech stack (fixed — do not change without explicit ask)

- **Python 3.11** (matches vlrggapi pinned version)
- **SQLite** for the warehouse
- **FastAPI** for the prediction API
- **React 18 + Vite + Recharts** for the dashboard
- **APScheduler** for scheduled jobs
- **Bambi** for Bayesian regression (escalate to raw PyMC only if Bambi can't express the model)
- **trueskill** library for player ratings
- **DeepSeek V4 Flash** via API for LLM features
- **Docker + docker-compose**, image pushed to **GHCR** via GitHub Actions
- **structlog** for logging
- **pytest** for tests
- **marimo** for all notebooks (NOT Jupyter; see `docs/MARIMO_CONVENTIONS.md`)

---

## Off-limits without explicit ask

- Switching any item in the tech stack above
- Adding a new external dependency (always propose first)
- Schema changes not already in `docs/ARCHITECTURE.md`
- Building tier-2 (rib.gg) features — that's a post-v1 decision gate (Phase 9)
- Refactoring existing working modules from earlier phases
- Changing user-facing dashboard UX in a non-trivial way without a deviation entry

---

## When to stop and ask Rahat

- Schema changes beyond what's in ARCHITECTURE.md
- Any new external API integration
- Choices that materially affect $ cost (LLM token budget, hosting)
- Anything affecting dashboard UX beyond minor styling
- Two tasks in a row produce results that don't match expectations — something's off, surface it

---

## Git hygiene

- Branch per phase: `phase-0-peng-bootstrap`, `phase-1-vlrggapi-setup`, etc.
- Commit per task: `phase-{X}.task-{Y}: <description>`
- Merge to main only after the phase is complete and PROGRESS.md has the phase summary
- Tag at end of each phase: `v0.1.0-phase-{X}`

---

## Failure modes to watch for

- Writing code before reading existing files → bugs from stale assumptions
- Skipping verification because "it should work" → wasted next-task time
- Over-engineering a v1 component → schedule slips
- Silently fixing unrelated issues → losing trace of what changed
- Pre-creating files for future phases → dead code accumulates

If you catch yourself doing any of these, stop and restart the task from the protocol.
