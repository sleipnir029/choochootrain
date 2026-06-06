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
