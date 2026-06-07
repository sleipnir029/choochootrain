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

### 2026-06-07 — Phase A (surface existing data): two data realities reshape the approach

**Phase / Task:** Decision-grade analytics, Phase A (Rahat-directed: surface agent-comp / patch-meta / duel insights from data already ingested)

**Plan said:** The approved plan (`.claude/plans/okay-a-few-things-abstract-creek.md`) assumed flex-vs-specialist detection could draw on `player_skill` **agent-granular** rows, and that patch-windowed map/comp win-rates could be split **per patch**.

**What was actually done:** Both assumptions were checked against the warehouse and corrected:
- **`player_skill` has zero agent- or map-granular rows** (all 477 are overall: `agent IS NULL AND map_name IS NULL`). So flex/specialist is derived purely from the `map_player_stats.agent` **pool composition** (distinct-agent count, top-agent concentration) + a **static agent→role map** (29 agents in the data, incl. two non-canonical labels `Miks`/`Veto` mapped to "Unknown"). No agent-specific TrueSkill is used because it does not exist.
- **Per-patch samples are too thin** (a team sees 2–18 maps per patch; 40 distinct patches league-wide). Single-patch win-rates would be noise, so the "meta shift" view uses a **recent-vs-prior date/era split** (anchored to the boundary patch label for context), combined with shrinkage — not per-patch breakdowns.

**Why:** Direct DB probe (2026-06-07) of `player_skill` granularity and the patch×maps distribution for team 624.

**Impact:** No schema change. Adds a static `AGENT_ROLES` map + shrinkage/role helpers in `models/scouting.py`; new scouting fields (role profiles, meta-shift, shrunk win-rates) surfaced on Team/Matchup pages and woven into the matchup narrative. Phase B (visuals) will fetch canonical roles from valorant-api and can supersede the static map.

**Rahat approval:** yes (approved Phase A, then Phase B).

**Related commit:** `<pending>`

### 2026-06-07 — Scouting tier-2: re-ingest the dropped match-details data (duels, clutches, veto)

**Phase / Task:** Decision-grade analytics, Wave B (scouting tier-2)

**What was done:** Extended `ingestion/match_details.py` to capture data the original P2 ingestion dropped (DEVIATIONS 2026-06-04 P2.T6): the **kill matrix** (`match_player_duels`), **advanced stats** — multikills + clutches (`match_player_advanced`), and the **map-veto sequence** (`match_veto`). `scripts/reingest_details.py` re-runs match-details ingestion from the disk cache (no new network) into these new tables; idempotent, per-match savepoint so a bad match skips. Surfaced via the team scouting page (veto tendencies, round impact) + the player page (head-to-head **duel matrix** — "Jinggg dominates xavi8k 65-26, struggles vs skuba 24-68").

**Key discoveries / decisions:**
- **vlr's performance tab is MATCH-level**, not per-map — the identical kill matrix + advanced stats repeat on every map. Storing per-map and summing inflated everything ~N×, so the tables are keyed by `match_id` and the data is parsed **once per match** (from the first map carrying it). Caught via Playwright sanity (f0rsakeN "8 2Ks per map" was impossible vs his ~19 kills).
- **Veto uses team tags**, but `teams.tag` is NULL and the detail's tag is empty — so a backfill derives each team's tag as the **modal veto tag across its matches**, then resolves `match_veto.team_id` per match (in `reingest_details`).
- **Plants/defuses captured but NOT surfaced** — the advanced table has a variable leading column making the plant/defuse index unreliable (one player showed 239 plants). Multikills (keys 2-5) + clutches (6-10) are reliable and shown; plants/defuses stay in the schema, unused.
- **Coverage ~1098/1258 matches** — the rest are rate-limited cache misses (not in cache; the live container throttled them). Spread, not systematic.

**Impact:** New scouting surfaces (duel matrix, veto tendencies, clutch/multikill impact), all tier-1, no external dependency. Schema adds 3 tables (regenerable from cache via `scripts/reingest_details`).

**Rahat approval:** yes (continue into tier-2 re-ingestion).

**Related commit:** `<this commit>`

### 2026-06-07 — Wave B pivot: analyst scouting instead of betting/odds

**Phase / Task:** Decision-grade analytics, Wave B

**Context / decision:** Wave A showed the model's edge is thin and concentrated (sharp only on ~5% of maps), and tier-1 match-winner markets are efficient — so wiring an odds source for EV/CLV has limited payoff and adds a ToS-gray external dependency. Rahat pivoted Wave B to **analyst scouting** (tier-1, no external data).

**What was done (slice 1, no re-ingestion):** `models/scouting.py` + `GET /api/teams/{id}/scouting` + a `/team/:id` page deliver an opponent scouting report from data **already in the warehouse**: map pool + CT/T side win-rates, economy-by-buy-type, most-run agent comp per map, player agent pools, and opening-duel (FK/FD) win rates — over a recent-N-maps window. This is the SPEC's *fan-grade* warehouse repurposed for *analyst-grade* scouting (new surface, not a spec contradiction).

**Deferred (scouting tier 2):** the richer signals — **kill matrix (duel matrix), clutches, multikills, plants/defuses, and the map-veto sequence** — are scraped by vlrggapi but dropped at ingestion (DEVIATIONS 2026-06-04 P2.T6). Surfacing them needs a re-ingestion chunk (re-parse cached `/v2/match/details` into new tables). Odds/EV/CLV betting is deferred (revisit if a source is provided).

**Rahat approval:** yes (chose "skip odds — do scouting").

**Related commit:** `<this commit>`

### 2026-06-07 — Decision-grade Wave A: calibration is already good; value is the regime map; `prediction_log` added

**Phase / Task:** Decision-grade analytics, Wave A

**What was found / done:**
Building the betting-grade core, the honest result on the recalibration step: **the model is already well-calibrated** (overall holdout ECE **0.013**; reliability bins predicted≈actual). An isotonic recalibration **does not improve** out-of-sample Brier (0.2388 → 0.2407, slightly worse — it overfits), so `models.calibration` only persists a map if it *demonstrably* helps; here it saves nothing and `calibrate()` stays the **identity**. (Don't manufacture confidence.)

The real deliverable is the **regime map** from `models.backtest` (`prediction_log`): the model is a coinflip on most maps but **genuinely sharp where there's a big Elo gap** — by confidence tier, **sharp 73.7% (n=99, Brier 0.191) / lean 62.1% / coinflip 55.5%**; by |elo_diff|, 0–50→53%, 100–150→66%, 150–250→**74%**. So a `confidence_tier(elo_diff, tier)` (sharp ≥150 Elo, lean ≥75, elite events downgraded) now rides on every prediction, and `GET /api/model/track-record` + a "Model trust" dashboard page surface calibration + the sharp-vs-coinflip map honestly.

**Schema add (minor):** `prediction_log` (out-of-sample track record; built by `python -m models.backtest`, regenerable) — `ingestion/schema.py` + ARCHITECTURE §2.4. `models/saved/calibration.json` is gitignored (regenerable, and usually absent since calibration is identity).

**Impact:** No accuracy change (calibration was the lever, and it's already good). Predictions now carry a `confidence` tier; the dashboard tells the user where to trust the model. Sets up Wave B (edge/EV only on the *sharp* regime).

**Rahat approval:** yes (chose decision-grade focus).

**Related commit:** `<this commit>`

### 2026-06-07 — Live prediction wired to the upcoming-feature builder; live_state gains team ids

**Phase / Task:** P6 revision (closes the live-prediction gap flagged since P3.T7 / P5.T3)

**Spec said:**
`models.predict.predict_map_win_prob` needs a match's **ingested** map features, so the P5 poller could only track a live match's **score** — a real (un-ingested) live match's win-prob no-op'd (DEVIATIONS 2026-06-06). ARCHITECTURE §2.5 `live_state` had no team columns.

**What was actually done:**
- **`models.predict.predict_live_win_prob(match_id, map_index, live_state, *, team_ids, db_path)`** — tries the ingested path; on `ValueError` (un-ingested) it builds the pre-match prior from the **as-of-now upcoming features** (`models.upcoming.predict_upcoming_win_prob`) for `team_ids=(team1_id, team2_id)` and log-odds-pools it with the score-state likelihood. The prior is constant per match, so it's cached per `(db, t1, t2)` — the Bambi posterior-predictive runs once, not per score change.
- **Poller** (`scheduler/jobs/live_poll.py`): `parse_live_segment` now carries the team **names**; `poll_once` resolves them to `team_id`s (`teams.name COLLATE NOCASE`) and stores them; `make_prediction_callback` uses `predict_live_win_prob` with those ids. A genuinely live match now produces a win-prob instead of a no-op (still best-effort: needs both team names to resolve + the trained posterior).
- **Schema add (material):** `live_state.team1_id`, `live_state.team2_id` (nullable, resolved from the live segment) — needed so both the prediction and the home **live hero** (`api/routes/home.py:_live_hero`) can identify/PRX-frame an un-ingested live match (whose `match_id` isn't in `matches`). Updated `ingestion/schema.py` + ARCHITECTURE §2.5; existing `data/prx.db` migrated via `ALTER TABLE ADD COLUMN` (the table is ephemeral/singleton).

**Impact:** Closes the long-standing gap — the live panel/hero now shows a real win-prob for an un-ingested live match. Verified by simulating an un-ingested match (Cloud9 vs PRX) through the full poll→predict→home chain: "PRX lead 8-3 on Ascent — 95% to win it." Caveats unchanged: `team1_side` is best-effort (live_score has no side); team-name→id resolution is best-effort. Scheduler registration (running the poller in-process) is still later work.

**Rahat approval:** yes (asked to "wire the live path to the upcoming-feature builder").

**Related commit:** `<this commit>`

### 2026-06-07 — Dashboard redesign: insight-first, PRX-centric, view-shaped API (P6 revision)

**Phase / Task:** P6 revision (post-tag, Rahat-directed)

**Spec said:**
SPEC §1 / §7.2 / §6.2-Layer-5 frame the product as a PRX-centric tool with **narrative** explanations ("PRX 67% because…") and an **expected-vs-actual** panel — not a raw stat browser. The first Phase-6 dashboard (T3–T10) shipped raw charts + manual match/player **ID inputs**, which Rahat flagged as "just charts, no insight … like vlr.gg … picking up by id is wasteful."

**What was actually done (approved redesign):**
- **Templated narrative composer** `api/insight.py` (pure, no LLM): `prematch_insight` / `postmatch_insight` / `live_insight` + `biggest_swing`. Returns `{headline, points, tone}`, PRX-framed. The SPEC's §7.2 LLM stays Phase 7 — it will rephrase the *same* structured inputs. (Decision: templated now, LLM-ready.)
- **Surfaced the built-but-unexposed expected-vs-actual layer** (`models/expected_stats.predict_expected_stats`) — over/under-performance vs each player's baseline.
- **View-shaped endpoints** (one call per screen, vs many REST calls): `GET /api/home` (PRX rank + roster skill + live/next/last-match hero + recent results with **model-was-right/wrong**), `GET /api/matches/{id}` (prediction + insight + replay + expected-vs-actual + outcome), `GET /api/players/{id}` (skill **percentile** + stints + expected-vs-actual trend). New `api/compute.py` composes these; `build_replay` extracted from the replay route for reuse. `recent_prx_results` is process-cached (static data, avoids re-predicting on every home load).
- **Frontend rebuilt** as `pages/{HomePage,MatchPage,PlayerPage}` with **`react-router-dom`** (real `/`, `/match/:id`, `/player/:id` URLs per ARCHITECTURE §7.3) — the mode-switcher + numeric **ID inputs are gone**; navigation is by clicking recent matches / roster cards. Narrative (`<Insight>`) leads every view; charts are support. Old panels deleted.
- **vite `base` changed `'./'` → `'/'`** (absolute asset URLs) so client routes resolve `/assets/*` under the new FastAPI **SPA fallback** (`api/main.py` serves `index.html` for non-`/api`, non-asset paths so deep links/refresh work).

**Impact:** No schema or model-internals change; reuses `predict`/`upcoming`/`expected_stats`/`elo_ratings`/`player_skill`. The first-cut panels (`PreMatchPanel` etc.) are removed. Live hero still needs the P5 poller; next-match hero still needs vlrggapi (degrades to the last-match story offline). Verified end-to-end with Playwright (Home → click match → click player; 0 console errors).

**Rahat approval:** yes (chose templated-insight-now + full PRX-centric redesign).

**Related commit:** `<this commit>`

### 2026-06-06 — Dashboard: state-driven views (not path routing); D3 opponent; Docker deferred (P6.T4–T10)

**Phase / Task:** P6.T4–T10

**Spec said:**
ARCHITECTURE §7.3 lists client routes `/`, `/match/:id`, `/team/:id`, `/player/:id`. TASKS P6.T3 lists deps Recharts + axios. P6.T10 done-when: `docker compose up` serves the dashboard at `http://localhost:8000/`.

**What was actually done:**
- **State-driven view switching, no react-router.** The top-bar mode switcher (Live/Pre-match/Player/Replay) + a contextual ID input drive a single-page view via component state — matching the T4/T9 task wording ("switcher toggles state", "auto-detect shows the right panel") without adding `react-router-dom`. Manual entry of a match/player ID replaces path params. Minor UX deviation from §7.3's path routes; deep-linkable URLs are a later nicety (YAGNI for v1).
- **Added `@tanstack/react-query`** beyond the T3 dep list (Recharts + axios) — it's the state manager ARCHITECTURE §7.2 already prescribes; used for caching/polling. Not a new stack decision.
- **D3 default (no live match) uses a representative PRX matchup (624 vs 188).** D3 says "pre-match panel for PRX's next scheduled match", but vlrggapi's upcoming feed exposes team **names, not IDs** (P2.T5 deviation), and the prediction needs both team IDs — so the opponent can't be reliably resolved to an ID. The no-live default renders a real upcoming prediction for PRX vs Sentinels; a match-ID input switches to any ingested match. Resolving the true next opponent's ID is a later enhancement (needs a name→ID lookup).
- **Docker image validation deferred to Phase 8.** P6.T10's app-level behavior — FastAPI serving the built `dashboard/dist` at `/` alongside `/api` and `/docs` — is implemented and **verified locally with uvicorn/TestClient**. The full `docker compose up --build` (heavy bambi/pymc image, posterior + warehouse via volume mounts) is deployment work that overlaps Phase 8 (GHCR, health checks, volumes); the Dockerfile (Node build stage + Python app) and compose (data + `models/saved` volumes) are written but the container build is validated in Phase 8.

**Impact:** No schema change, no API change. The dashboard is fully functional served locally. Phase 8 builds/validates the container and finalizes deployment.

**Rahat approval:** yes (frontend go-ahead). Routing/opponent/Docker scoping are implementation calls within that.

**Related commit:** `<this commit>`

### 2026-06-06 — API contract reconciled to reality (P6.T1)

**Phase / Task:** P6.T1

**Spec said:**
ARCHITECTURE.md §5.3 declared `predict_map_win_prob(...) -> Prediction(team1_win_prob, top_factors, confidence)`; §3.1 declared `/api/predict/pre-match?match_id=` returning `series_win_prob` + `map_predictions` + `top_factors`.

**What was actually done:**
Reconciled the documented contract with the built code (P6.T1 is "write *or confirm* the contract"):
- **`predict_map_win_prob` returns a bare `float`** — the `Prediction(...)` object was never built and the P5 live poller depends on the float. §5.3 now documents the float plus two thin Phase-6 composition helpers, `models.predict.predict_map_win_prob_detailed` (mean + HDI + factor attribution) and `models.upcoming.predict_upcoming_win_prob`, used only by the API.
- **`top_factors`** is documented as an *interpretable attribution* (posterior-mean coef × standardized feature value per term, ranked; `favors` = sign vs team1) — explicitly not exact Shapley. The natural-language explanation stays a Phase-7 LLM call.
- **`series_win_prob`** is *derived, not modeled* — maps as independent Bernoulli(p), Bo-N series prob in closed form; upcoming mode uses one team-strength `p` for all maps.
- **`/api/predict/pre-match` gains an upcoming mode** (`team1_id`+`team2_id` instead of `match_id`) so D3's "PRX's next scheduled match" — which is **not** in the `matches` table (completed matches only, P2.T5) — can be predicted via the new as-of-now feature builder.
- Pre-match/live responses surface an **HDI** (SPEC §6.1 uncertainty), and `/api/predict/live` is documented as **reading** the poller's `live_state`/`live_predictions` tables (not polling vlrggapi itself).
- `/api/llm/*` marked Phase 7 (not built in the Phase 6 backend).

**Impact:** No schema change. P6.T2 implements exactly this. The `predict_map_win_prob` float signature is preserved (no break to P5). `models/upcoming.py` is a new additive module.

**Rahat approval:** yes (chose "build the as-of-now feature builder" + backend-only scope for this session).

**Related commit:** `<this commit>`

### 2026-06-06 — Live priority (P5.T4): tier from match_event string; no hard tier-2 exclusion

**Phase / Task:** P5.T4

**What was done:**
`select_match` now picks by SPEC-D3 priority — **PRX > Champions > Masters > Regional League > earliest start** — using the live_score segment's own `match_event` (tournament name) and `unix_timestamp` (no DB lookup). `classify_tier` checks Kickoff/Masters first and treats a name as the Champions *tournament* only when it lacks the **"Champions Tour"** circuit branding (VCT names like "Champions Tour 2024: Pacific Kickoff" would otherwise misclassify as Champions). Kickoff and league stages rank as Regional-League level.

**Soft gap:** no hard tier-1/tier-2 *exclusion* — live matches aren't in the curated tier-1 ID registry, and event-name classification can't reliably separate tier-2 (Challengers/Game Changers). The key correctly prioritizes tier-1 when present; a lone non-tier-1 live match would still be tracked (its prediction no-ops via the un-ingested guard). Acceptable for v1; the done-when (priority ordering) is met.

**Rahat approval:** N/A (implements SPEC-D3 priority; gap documented).

**Related commit:** `<this commit>`

### 2026-06-06 — Live re-prediction (P5.T3): round-count live_state mapping; real-live-match gap

**Phase / Task:** P5.T3

**Spec said:**
TASKS P5.T3: on a detected change, call `models.predict.predict_map_win_prob` with live_state; store to `live_predictions`. Done-when: for a simulated live match, predictions recomputed + stored on each score change.

**What was actually done:**
`scheduler/jobs/live_poll.py` adds `to_predict_live_state` + `write_live_prediction` + `make_prediction_callback(db_path)`, wired into `main()` as the `on_change` callback. Two notes:
- **live_state mapping:** predict's score-state lookup wants **round counts on the current map** + team1's current side; the poller's `team1_score/team2_score` are *map/series* scores, so the mapping derives round scores from `team{1,2}_round_{ct,t}`, `half` from total rounds (<12 first / <24 second / else ot), and `map_index = map_number-1`. **`team1_side` is best-effort** — live_score doesn't expose the current side, so it's inferred from team1's per-side wins and flipped at half (can be wrong mid-map; the score-state side term is small).
- **Real-live-match gap (key):** `predict_map_win_prob` needs the match's **ingested** map features (`build_training_data`), so live prediction works only for matches already in the warehouse. A real, in-progress (un-ingested) match raises `ValueError`, swallowed by poll_once's guard (logged) — the poller survives but stores no prediction. Upcoming/live-match feature construction is a Phase-6 item (same gap as P3.T7). The done-when was met by simulating with an ingested match (666493 + fake live states → a `live_predictions` row per change, 0<prob<1).

**Impact:** `live_predictions` populated for ingested matches; `computed_at` uses microsecond ISO to avoid PK collisions on rapid changes. No schema change. Phase 6 must add upcoming-match features for true live use.

**Rahat approval:** N/A (implements P5.T3; gap is informational, deferred to Phase 6).

**Related commit:** `<this commit>`

### 2026-06-06 — Live poller (P5.T1): writes live_state table; minimal match-selection; FK note

**Phase / Task:** P5.T1

**Spec said:**
TASKS P5.T1: poll `/v2/match?q=live_score` every 30s when a tier-1 match is live; write state to in-memory cache **or** `live_state` table (choose one). SCHEDULER.md: IDLE 60s / POLLING 30s state machine; PRX > Champions > Masters > Regional > earliest priority.

**What was actually done:**
`scheduler/jobs/live_poll.py` writes to the **`live_state` SQLite table** (singleton — `DELETE` + insert the tracked match), per SCHEDULER.md, so the Phase-6 API can read it cross-process; an in-memory `last_state` drives change detection. `VlrClient(cache=False)`; async IDLE/POLLING loop; `--once` for a single cycle.

Two intentional T1 simplifications:
- **Match selection is minimal** — prefer a "Paper Rex" segment, else the first live one. Full tier-1 detection + the SPEC-D3 priority order is **P5.T4** (the `live_score` segment carries no event/tier, so tier-1 filtering needs more than the poll response).
- **FK:** `live_state.match_id → matches(match_id)`, but a live match may not be ingested yet; SQLite FK enforcement is off (never enabled), so the insert is safe. Round/score fields arrive as strings/`"N/A"` → parsed to int or NULL (columns nullable).

**Impact:** done-when (logs every score change) verified by unit tests (`poll_once` across a score change) + a live `--once` smoke against the container (logged `no_live_match`; real score-change logging needs an actual live match). P5.T2 formalizes change→callback on `state_changed`; T3 adds `live_predictions`; T4 adds priority.

**Rahat approval:** N/A (follows SCHEDULER.md; documented deferrals to T2–T4).

**Related commit:** `<this commit>`

### 2026-06-06 — Player-skill feature integrated into the pre-match model

**Phase / Task:** Phase 3 revisit → integration (Rahat-approved)

**What was done:**
Added `skill_diff` (point-in-time team TrueSkill diff) to the production model:
- `models/training_data.py` imports `scripts.build_player_skill.replay_skill_diffs` and adds a `skill_diff` column (per `map_id`, `fillna(0.0)` for the ~3 maps without two identifiable lineups; no-NaN invariant preserved). One extra `map_player_stats` pass per `build_training_data` call (cached in `predict._resources`). Intentional `models`→`scripts` import (no cycle).
- `models/bayes_logistic.py` `FORMULA` gains `+ scale(skill_diff)`; posterior refit.

**Result:** refit converged (max r̂ 1.0000, 0 div); **`scale(skill_diff)` = 0.214, 94% HDI [0.093, 0.333]** — credibly non-zero, co-dominant with `elo_diff` (0.201). On the broad post-cutoff holdout the Bambi model now **beats the Elo-sign baseline for the first time: 0.583 acc vs 0.580** (was 0.571), Brier 0.240 (was 0.242), RegionalLeague 0.602. Elite Masters stays ~coinflip (0.534, n=118). `skill_diff` univariate AUC 0.614 broad / 0.603 Masters — the strongest single feature. The formula was **not** simplified (the lift held without dropping the dead terms).

**Impact:** `models/saved/bayes_logistic.nc` regenerated (gitignored — rebuild via `python -m models.bayes_logistic`). `predict.py`/`expected_stats.py` unchanged (they pick up the new feature/formula automatically). Honest bounds unchanged: map-level prediction remains hard; no claim near SPEC §6.3's 65-75%.

**Rahat approval:** yes (integrate, planned).

**Related commit:** `<this commit>`

### 2026-06-06 — Player skill DOES lift map prediction beyond the Elo ceiling (revises P3.T8)

**Phase / Task:** Phase 3 revisit (Rahat-directed: Phase 4 before finalizing Phase 3)

**Context:**
P3.T8 (DEVIATIONS 2026-06-06) concluded map prediction was stuck at a ~57% Elo ceiling because features beyond team Elo added no signal. Rahat deferred the Phase 3 summary to build Phase 4 (player skill) and test whether a team-aggregated player-skill feature beats that ceiling.

**What was found (`notebooks/04_player_skill_lift.py` + `replay_skill_diffs`):**
A point-in-time team-skill feature (`skill_diff` = mean TrueSkill μ of team1's lineup − team2's, pre-map) **does** add signal — unlike every Layer-3 feature:
- `corr(skill_diff, elo_diff) = 0.49` (distinct info, not redundant), `corr(skill_diff, won) = 0.17 ≈ elo`.
- **elo+skill** beats elo-only on the broad post-cutoff holdout: acc 0.580 → **0.589**, AUC 0.609 → **0.622**, Brier 0.241 → **0.238**.
- **Elite Masters holdout:** skill *alone* = acc **0.585** / AUC **0.603** vs Elo 0.542 / 0.546 (~+4pt) — individual firepower separates top, evenly-matched teams where team Elo is weakest.

**Impact:** Partially revises the P3.T8 "hard ceiling" finding — the ceiling holds for *team-level* features, but *player-level* skill lifts it modestly (broad) / notably (elite). Recommendation: integrate `skill_diff` into the pre-match model (add to `models/training_data.py` + refit `models/bayes_logistic.py`, re-run P3.T8 validation) — pending Rahat's go-ahead, as it modifies committed Phase 3 artifacts. The lift is modest in absolute terms (map-level prediction remains hard), not a path to the original 65-75% target.

**Rahat approval:** experiment approved (plan); model-integration decision pending.

**Related commit:** `<this commit>`

### 2026-06-06 — Expected stats: match-level recent-form baseline; map term dropped; ±30 is the floor

**Phase / Task:** P4.T3

**Spec said:**
TASKS P4.T3: `expected_stats.py` predicts each player's expected ACS/K/D/A from "skill + opponent + map"; done when predicted ACS within ±30 of actual on average across 10 players.

**What was actually done (evidence-driven):**
A read-only feasibility check showed **per-map ACS is unpredictable** (career-mean MAE ~43; a per-map map offset made it *worse*). At **match level** (a player's mean ACS over the match's maps) a **recent-form** baseline hits the target. So `models/expected_stats.predict_expected_stats(match_id)` predicts match-level expected stats:
- **skill** = recent-form mean of each stat over the last `FORM_MAPS=30` maps before the match (fallback: career mean → league per-stat mean);
- **opponent** = a mild ACS multiplier from the opposing team's pre-match Elo (`elo_ratings`, as-of before the match; `DEFAULT_OPP_COEF=0.06`). It only improves sample MAE by ~0.2 (monotonic, theoretically sound) — kept but marginal; `opponent_coef=0` disables it;
- **map term dropped** — it measurably increased error.

**On the ±30 done-when:** match-level ACS MAE is **~30 on a broad recent sample** (right at the noise floor; ~half of matches ≤30) and **~25 on stable, established lineups** (e.g. PRX match 666493 = **MAE 24.9** across 10 players). Per-map prediction (~43) cannot meet ±30 — match-level is required. This mirrors the Phase 3 finding: player ACS is high-variance; ±30 is essentially the achievable floor.

**Impact:** `predict_expected_stats` depends on `elo_ratings` being built (P3.T2) for the opponent term (degrades to 1500/no-op if absent). Upcoming-match prediction (no maps yet → roster-based participants) is deferred to Phase 6. Per-(agent,map) expected stats not needed (match-level meets the goal).

**Rahat approval:** approach chosen from the analysis at Rahat's direction ("choose based on the analysis"); plan approved.

**Related commit:** `<this commit>`

### 2026-06-06 — Player-skill replay: overall rating only; ACS-vs-opponent performance, mean-of-5 opponent

**Phase / Task:** P4.T2

**Spec said:**
SPEC §6.2 Layer 5: TrueSkill rating per (player, agent, map). TASKS P4.T2: replay `map_player_stats` chronologically; performance score "e.g. normalized ACS vs opponent average"; populate `player_skill` for all players with ≥10 maps.

**What was actually done:**
`scripts/build_player_skill.py` computes the **overall** rating per player (`agent=NULL, map_name=NULL`) — what the ≥10-map done-when and the planned team-strength feature need. Per-(agent, map) cells (Layer 5's full granularity) are **deferred** until a consumer needs them (P4.T3 expected-stats / dashboard) — populating them now would be thousands of sparse, low-sample cells (YAGNI). Definitions: a player's **performance** = their ACS − the opposing team's average ACS (sign → win/loss/draw); the **opponent** for the 1v1 update is the aggregate (mean mu, mean sigma) of the five opposing players' current ratings. All ten players update from pre-map ratings (no within-map leakage); each player's row is stamped with their last-played date. Showmatches and rows lacking a resolved `player_id` or `acs` are excluded.

**Impact:** `player_skill` holds one overall row per player (477 rated; 439 with ≥10 maps). Top conservative ratings (mu−3σ) are recognizable stars (aspas, Derke, Alfajer, zekken, t3xture…), a good face-validity check. Adding per-(agent, map) ratings later is additive (same schema). The mean-of-5 opponent is a simplification of full team-vs-team TrueSkill (`trueskill.rate`) — adequate for a v1 over/under-performance signal.

**Rahat approval:** N/A (implementation choices within the approved Layer-5 approach; the per-(agent,map) deferral is a scope/YAGNI call, additive later).

**Related commit:** `<this commit>`

### 2026-06-06 — Player skill: binary win/loss/draw from performance sign; trueskill installed late

**Phase / Task:** P4.T1

**Spec said:**
SPEC §6.2 Layer 5 / TASKS P4.T1: TrueSkill rating per (player, agent, map); `update_skill(player_id, agent, map_name, performance_score, opponent_skill)`. CLAUDE.md stack lists the `trueskill` library.

**What was actually done:**
`models/player_skill.py` wraps `trueskill` (0.4.5). A map is a 1v1 TrueSkill match between the player and `opponent_skill`; the outcome is the **sign of `performance_score` vs `baseline`** (>baseline win, <baseline loss, ==baseline draw). Binary win/loss/draw is the library's native, minimal usage; margin-aware TrueSkill (how *much* a player over-performed) is a deferred refinement (cf. the Elo MOV choice, 2026-06-06). The prescribed signature is followed; `player_id/agent/map_name` are identity keys (the P4.T2 replay keys its store by them) and don't enter the math, and a keyword-only `current=` (defaulting to a fresh rating) supplies the player's prior rating. Uses the library-default env (mu=25, sigma=25/3, draw_probability=0.10) via the non-deprecated module-level `trueskill.rate_1vs1(..., env=_ENV)`.

Also: `trueskill` was **not** installed in P0.T1 (that bootstrap installed only the 9 Phase-0 packages); added now — `requirements.txt` (`trueskill==0.4.5`) + CI install. It's a fixed-stack item, so no new-dependency approval needed.

**Impact:** P4.T2 (replay) decides how `performance_score` is computed (e.g. normalized ACS vs opponent average) and owns the per-(player,agent,map) rating store. No schema change. `requirements.lock.txt` not regenerated (Windows freeze; trueskill is pure-Python, no transitive deps).

**Rahat approval:** N/A (minimal/standard TrueSkill usage; trueskill is a pre-approved stack item).

**Related commit:** `<this commit>`

### 2026-06-06 — SPEC §6.3 map-level accuracy target (65-75%) not achievable — evidence-based ceiling ~57-60%

**Phase / Task:** P3.T8 (validation + deep investigation, Rahat-requested)

**Spec said:**
SPEC §6.3: map-level accuracy 65-75%, Brier 0.20-0.23 (round 55-62%, series 70-80%).

**What was found (deep investigation, `notebooks/02_model_validation.py`):**
The pre-match map model reaches **51% on the mandated holdout** (Masters Toronto 2025 + Santiago 2026) and **57% across all post-cutoff maps** — at/just-below the Elo-sign baseline (54% / 58%), not 65-75%. This is a **genuine signal ceiling, not a bug**:
- **No leakage / orientation bug:** in-sample (train) accuracy is also only ~57%; `corr(elo_diff, won)` is positive throughout; Elo-sign > 50%.
- **No team1 assignment artifact:** team1 win-rate is ~0.50 across years and tiers (2024 0.519 / 2025 0.511 / 2026 0.475; tiers 0.47-0.53), so team1/team2 is effectively random w.r.t. outcome; the 0.449 Masters base rate is small-sample noise (n=118).
- **Features beyond team Elo add ~nothing:** univariate AUC ≈ 0.50 for side/form/H2H (and the T5 posterior + sklearn ablations give them coefs ≈ 0). `map_elo_diff` is marginally the best single feature on elite events (AUC 0.584) but swapping it in for the collinear pair doesn't move accuracy.
- **The ceiling is intrinsic:** a parameter-free Elo-probability matches the fitted model; the Bayes-optimal accuracy implied by Elo is only **~0.587**; on elite events the Brier *floor* is ~0.247 vs 0.250 for a coin (≈zero headroom). Top, evenly-matched teams are coinflips at map level; regional play (more lopsided) tops out ~60%.

**Impact:**
The 65-75% map target is revised down to a realistic **~57-60% (regional) / ~50-55% (elite)** for pre-match team features on this corpus. The system's value is **team-strength ranking + the in-match score-state layer (Layer 4)**, not pre-match map calls. No code bug to fix. Optional (no accuracy gain): simplify the model to drop the zero-signal terms — deferred to Rahat. Phase 4 (player skill) and more 2026 data are the realistic levers for any future lift.

**Rahat approval:** pending — surfaced before the Phase 3 summary (T9). Decision: accept Elo-centric v1 with revised expectations vs further work.

**Related commit:** `<this commit>`

### 2026-06-06 — Prediction: log-odds pooling for the live update; feature row from the warehouse

**Phase / Task:** P3.T7

**Spec said:**
TASKS P3.T7: `predict_map_win_prob(match_id, map_index, live_state=None)` — pre-match = Bayes logistic; live = "Bayesian update combining pre-match prior + score_state lookup". SPEC §6.2 Layer 4: "posterior ∝ prior × likelihood-from-score."

**What was actually done:**
`models/predict.py` implements the live update as **log-odds pooling**: `logit(post) = logit(prior) + logit(p_state)` (`combine_prior_and_state`). Justification: the score-state table is built over all teams from both perspectives, so its implicit prior at a state is the league-average matchup (~0.5); thus `odds(p_state)` is the score evidence's likelihood ratio, and prior_odds × LR = posterior_odds — exactly "posterior ∝ prior × likelihood." At the 0-0 start `p_state ≈ 0.5` so the posterior equals the prior. `live_state` is a dict from **team1's** perspective `{half, team1_score, team2_score, team1_side}`; an unseen state falls back to 0.5 (neutral).

The **pre-match prior** is the Bambi posterior-mean `p` (`model.predict(idata, data=row, sample_new_groups=True)` — the latter handles holdout patches unseen in train). The feature row is the **point-in-time row from `build_training_data`** for that `(match_id, map_index)` — so prediction currently works for maps that exist in the warehouse (the P3.T8 holdout, the demo). Predicting a *future/unplayed* map (no row yet) needs an as-of-now feature builder — deferred to Phase 6 (the API/dashboard), out of scope for T7's done-when ("sample call for a known match").

**Impact:**
P5 (live poller) supplies `live_state`; P6 will add upcoming-match feature construction. The `(match_id, map_index)→map_id` and score-state tables are cached per db path on first call. Requires the saved posterior (`models/saved/bayes_logistic.nc`).

**Rahat approval:** N/A (faithful implementation of SPEC Layer 4; pre-match scope matches the T7 done-when).

**Related commit:** `<this commit>`

### 2026-06-06 — Bayesian logistic: model spec, numba backend workaround, .nc not committed

**Phase / Task:** P3.T5

**Spec said:**
TASKS P3.T5: fit a Bambi formula model with the P3.T4 features; train through end of Masters Bangkok 2025, hold out the rest; save posterior to `models/saved/bayes_logistic.nc`. Done when converges (r_hat < 1.05 all params), summary logged. CLAUDE.md tech stack: Bambi (raw PyMC only if needed).

**What was actually done:**
`models/bayes_logistic.py` fits `team1_won ~ scale(elo_diff) + scale(map_elo_diff) + team1_starts_atk_or_def + scale(recent_form_team1) + scale(recent_form_team2) + scale(h2h_team1_win_rate) + C(tier) + (1|patch_id)`, Bernoulli/logit, train cutoff `2025-03-02` (Bangkok end). Choices:
- continuous predictors standardized with the **stateful `scale()`** transform (prediction reapplies the train mean/sd automatically);
- **`tier` as a fixed categorical** (only 4 levels — too few to estimate a random-effect variance);
- **`(1|patch_id)` random intercept** for partial pooling across patches (SPEC §6.1 hierarchical intent);
- both `elo_diff` and `map_elo_diff` kept despite r=0.89 collinearity — converged cleanly (NUTS handles it; `map_elo_diff`'s signal is absorbed by `elo_diff`, coef ≈ 0).

**Toolchain workaround (material to running the fit):**
This machine's PyTensor **C backend cannot link** (`C:\msys64\ucrt64\bin\g++.EXE` → `collect2: ld returned 116`), which blocks PyMC sampling. The pure-Python backend (`cxx=`) works but is far too slow (a tiny 1-chain fit didn't finish in minutes). Fix: compile via the **numba/LLVM backend** — `models/bayes_logistic.py` sets `os.environ.setdefault("PYTENSOR_FLAGS", "mode=NUMBA,cxx=")` before importing bambi. Full 4-chain × (1000+1000) fit then runs in ~1 min. numba 0.65.1 is already in the env (no new dependency installed). Overridable via `PYTENSOR_FLAGS` (e.g. a working C toolchain in the Phase 8 Linux image).

**`.nc` not committed:** the posterior trace is a regenerable artifact (re-trained weekly per ARCHITECTURE §5.2), so `models/saved/*.nc` is gitignored (dir kept via `.gitkeep`); rebuild with `python -m models.bayes_logistic`. ARCHITECTURE §5.1 says the API loads it at startup — Phase 6/8 must ensure it's generated into the image/volume, not pulled from git.

**Result:** max r_hat = 1.0000, 0 divergences (PASS). `elo_diff` coef 0.28 (94% HDI [0.08, 0.48], dominant); patch σ ≈ 0.10.

**Impact:** P3.T7 reconstructs the model via `build_model(train_df)` + the saved trace; it inherits the numba flag by importing this module first. bambi/pymc deliberately **not** added to CI (heavy; no test samples — `test_bayes_logistic.py` uses `importorskip`).

**Rahat approval:** N/A (model-spec + local-toolchain workaround within the approved Bambi approach; no stack/dep change).

**Related commit:** `<this commit>`

### 2026-06-06 — Training data: point-in-time replay; row count = competitive maps (3197)

**Phase / Task:** P3.T4

**Spec said:**
TASKS P3.T4: build a per-map feature row (elo_diff, map_elo_diff, team1_starts_atk_or_def, recent_form_team1/2, h2h_team1_win_rate, patch_id, tier; target team1_won). Done when: DataFrame produced; no NaN; **row count matches map count in DB**.

**What was actually done:**
`models/training_data.build_training_data(conn)` makes a **single chronological pass** over matches and computes every feature point-in-time (from state strictly before the match), advancing Elo / map-win counts / form / H2H only after emitting a match's rows. This recomputes Elo inline via `models.elo.update_elo` (and the P3.T3 offset formula) rather than reading the `elo_ratings`/`elo_map_offsets` snapshot tables — those are full-history snapshots and would leak future info into the P3.T8 holdout.

Decisions baked in:
- **Row count = 3197**, not the 3203 in `maps`. The 6 difference are maps on **showmatch** matches (some showmatches do have maps), excluded for consistency with P3.T2/T3. So "row count matches map count" holds for the *competitive* map set.
- **recent_form** = win fraction over the last `FORM_WINDOW = 5` maps; **0.5** when a team has no prior maps (avoids NaN, neutral prior). Form/Elo/H2H are snapshotted **pre-match** (same for all maps in a match), so map 3 doesn't peek at maps 1–2 of its own series.
- **h2h_team1_win_rate** = map-level, empirical-Bayes shrunk toward 0.5 with `H2H_PRIOR = 4` (`(t1_wins + 2) / (total + 4)`); 0.5 when no prior meetings.
- **team1_starts_atk_or_def** = 1 if team1's round-1 side is T (attack), else 0. **1 map** has no round-1 row → falls back to 0 (logged via `df.attrs['side_fallbacks']`).
- `patch_id` (TEXT) and `tier` kept as categoricals for Bambi (P3.T5).

**Impact:**
Clean, leak-free features for P3.T5/T8. `FORM_WINDOW` and `H2H_PRIOR` are tunable knobs (K-factor precedent). No schema change.

**Rahat approval:** N/A (minor; implements the approved P3.T4 with documented neutral-prior / shrinkage choices).

**Related commit:** `<this commit>`

### 2026-06-06 — Map offsets: win-rate deviation converted to Elo points via a tunable scale

**Phase / Task:** P3.T3

**Spec said:**
SPEC §6.2 Layer 2: map offset is "a deviation from the team's base Elo" (Elo points; Layer 3 uses "map-specific Elo difference"). TASKS P3.T3: "compute deviation between team's win rate on that map vs overall win rate; smooth using partial pooling toward 0." `elo_map_offsets.rating_offset` is the stored column.

**What was actually done:**
`models/elo_map_offsets.py` computes `raw_dev = map_win_rate - overall_win_rate`, shrinks it by sample size (`shrunk = raw_dev * games / (games + PRIOR_GAMES)`, `PRIOR_GAMES = 10`), then converts to Elo points (`offset = ELO_PER_WINRATE * shrunk`, `ELO_PER_WINRATE = 400`). Both constants are function args / CLI flags. TASKS specifies the computation (win-rate deviation + pooling) but not the win-rate→Elo conversion; that scale is a tuning knob, defaulted conservatively — the same "default now, tune on holdout" pattern SPEC §6.2 sets for the K-factor.

**On "offsets sum to roughly 0 per team":**
Deviations are defined in win-rate space, where the games-weighted sum is exactly 0; the unweighted, shrunk sum is small but nonzero. Per-team sums are ~0 in win-rate space (PRX = −0.114 across 12 maps, ~1pp/map; worst team −0.21, ~1.8pp/map). The ×400 Elo scaling inflates this to PRX −45.8 Elo / worst −84 Elo. No centering is applied (TASKS asks for pooling toward 0, not zero-mean centering) — values are reported transparently.

**Impact:**
P3.T4 adds `rating_offset` to base Elo to form the map-adjusted Elo / `map_elo_diff` feature, so the units match (Elo points). If the scale proves too strong/weak on the holdout, tune `ELO_PER_WINRATE` (and `PRIOR_GAMES`) — no schema change.

**Rahat approval:** N/A (minor; follows the SPEC's Elo-point intent + K-factor "default + tune" precedent).

**Related commit:** `<this commit>`

### 2026-06-06 — Elo replay uses a flat 1500 prior (region-based priors deferred)

**Phase / Task:** P3.T2

**Spec said:**
SPEC §6.2 Layer 1: "Initialize ratings using region-based priors so early-season is not arbitrary." TASKS P3.T2: "Initial rating per region: 1500 (configurable)."

**What was actually done:**
`models/elo_replay.py` starts every team at a flat `INITIAL_RATING = 1500.0` (configurable via `--initial`). Region-based priors are **not** applied because `teams.region` is NULL for all 69 teams (the `/v2/team` profile doesn't expose region — see DEVIATIONS 2026-06-04, P2.T3). This satisfies the literal TASKS P3.T2 wording (flat 1500) but not SPEC §6.2's region-prior intent.

**Why:**
Region is simply unavailable in the warehouse, so a region-keyed prior can't be computed yet. A flat prior is the correct minimal choice until region is backfilled (e.g. from `/v2/rankings?region=...` or each team's event set).

**Impact:**
Early-season ratings are arbitrary (all start equal), as SPEC §6.2 warned. Mitigated in practice because the replay spans 2024–2026, so ratings converge well before the holdout window (Masters Toronto 2025 / Santiago 2026). If region priors are wanted later: backfill `teams.region`, then pass a per-team initial map into `replay_elo` (the signature already takes `initial_rating`; would generalize to a dict). No schema change now.

**Rahat approval:** N/A (minor; follows TASKS P3.T2 literally, region genuinely unavailable).

**Related commit:** `<this commit>`

### 2026-06-06 — Elo actual-outcome term is margin-of-victory, not binary

**Phase / Task:** P3.T1

**Spec said:**
SPEC §6.2 Layer 1: "Each team gets a rating. Update after each match. K-factor calibrated empirically (start at K=24)." Says "standard Elo" without pinning how the actual-outcome term is derived from a series score.

**What was actually done (Rahat-approved):**
`models/elo.update_elo(rating_a, rating_b, score_a, score_b, k=24)` computes the actual outcome as **margin-of-victory** — `actual_a = score_a / (score_a + score_b)` — so a 2-0 sweep moves Elo more than a 2-1 win (vs a binary 1/0/0.5 outcome where 2-0 and 2-1 move identically). Expected score is standard logistic (400 divisor); update is zero-sum (`delta_b = -delta_a`). Raises `ValueError` on a 0-0 score (no valid completed match).

**Why:**
The function signature passes both series scores, and Rahat chose to use that margin signal rather than discard it. A clean win carries more information about relative strength than a deciding-map win.

**Impact:**
Affects every downstream Elo value (P3.T2 replay, P3.T3 map offsets) and any feature built on Elo diffs. No schema or UX impact. K and the outcome formula are the obvious tuning knobs for the 2024–2025 holdout calibration.

**Rahat approval:** yes (chose margin-of-victory over binary this session).

**Related commit:** `<this commit>`

### 2026-06-06 — Phase 0 validation reframed: no per-round loadout; economy descriptive + score-state baseline

**Phase / Task:** P0.T3–T6 (deferred validation, resumed after Phase 2)

**Spec said:**
SPEC §3.2 / TASKS P0.T2–T6: replicate Peng's round-level logistic on 3 features (team loadout diff, ult-availability diff, ult-points diff) → ~60.6% round accuracy. The 2026-06-04 deferral assumed a "loadout-only" replication was possible from vlr.gg per-round loadout values.

**What was actually done (Rahat-approved):**
Confirmed the pinned vlrggapi (`a6075fe`) exposes **no per-round loadout** — only map-level buy-category aggregates (`/v2/match/details` economy = pistol/eco/$/$$/$$$ counts+wins per team per map), and `rounds` has only `{winner, side, half}`. So Peng's round-level loadout-diff model is **not reproducible**. Reframed to two validations on our warehouse:
1. **Economy/loadout signal — descriptive** (`notebooks/00_round_eda.py`): win% by buy category from `map_team_economy`, showing the monotonic loadout effect (eco < semi < full). Note `map_team_economy` stores win **%** (not round counts; counts were lossy at ingest), so this is descriptive, not a fitted per-round logistic.
2. **Score-state round-level logistic — fitted** (`notebooks/01_round_baseline.py`): predict round winner from `team1_side` + pre-round score diff (+ half), reconstructed from `rounds`. Proves the sklearn toolchain end-to-end and directly seeds the Phase 3 score-state model.

Notebooks renamed from `00_peng_eda`/`01_peng_baseline` to `00_round_eda`/`01_round_baseline` (not Peng data).

**Impact:**
Not a literal Peng replication. Expected accuracy ~52–56% (side+score-state); loadout — Peng's dominant signal — is unavailable at round level, so we won't hit ~60%. Toolchain validated regardless. If a fitted economy model is later wanted, `map_team_economy` would need round-count columns (schema change + cheap re-parse from cached details).

**Rahat approval:** yes (both: economy-signal descriptive + score-state baseline).

**Related commit:** `<this commit>`

### 2026-06-04 — Patches sourced by scraping Riot once into a committed data/patches.json

**Phase / Task:** P2.T13

**Spec said:**
P2.T13: "scrapes Riot's patch notes index … builds `data/patches.json` … Populate `patches` table. Backfill `matches.patch_id` based on date." (New external source — confirmed with Rahat.)

**What was actually done (Rahat-approved):**
`ingestion/patches.py` fetches `https://playvalorant.com/en-us/news/tags/patch-notes/` **once**, parses the embedded `__NEXT_DATA__` JSON (patch titles + release dates, `notes_url` from `action.payload.url`), and writes a **committed** `data/patches.json` (the reproducible source of truth — `--refresh` to re-scrape; default uses the JSON, no network). One page covers the full history (142 patches, `0.47`→`12.10`, all 57 from 2024 onward). `matches.patch_id` is backfilled to the latest patch with `release_date <= date_utc`.

**Notes:**
- The article date is under `publishedAt`/`publishDate`, **not** `date` (an initial wrong key gave 0 patches).
- Backfill validated against the authoritative per-match patch label: match 312765 (2024-03-14) → `8.04`, exactly what `/v2/match/details` reported. All 436 matches resolved (0 NULL).

**Impact:** `patches` table (142 rows) + every match has a patch. `data/patches.json` is committed and used offline; re-scrape only when new patches ship.

**Rahat approval:** yes (scrape once, commit patches.json).

**Related commit:** `<this commit>`

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
