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
