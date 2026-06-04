# PRX Predictor — Project Spec v0.1

**Status:** Planning complete, ready for Claude Code implementation
**Owner:** Rahat
**Implementer:** Claude Code
**Spec author:** Claude (research & planning)
**Last updated:** June 4, 2026

---

## 0. Verified facts and corrections from earlier discussion

Per the working principle "verify and confirm even if it's a single thing," the following were checked against primary sources (Liquipedia, vlr.gg, Wikipedia, Riot Games announcements). Several earlier assumptions in chat were wrong and are corrected here.

**Masters Toronto was 2025, not 2026.** PRX won Masters Toronto on June 22, 2025, defeating Fnatic 3-1. Prize $350,000. First Southeast-Asian team to win an international VCT title. Earlier chat said "Masters Toronto 2026" — incorrect.

**2026 Masters events are Santiago and London, not Bangkok and Toronto.** Earlier turn referenced "Masters Bangkok 2026" and "Masters Toronto 2026" — both wrong. 2026 calendar is Kickoff → Masters Santiago (already concluded; PRX lost final 0-3 to Nongshim RedForce) → Stage 1 → Masters London (June 6–21, 2026, starts in 2 days) → Stage 2 → Champions Shanghai.

**Current PRX active roster (2026):** d4v41 (Khalish Rusyaidee, MY, joined 2021-02-08), f0rsakeN (Jason Susanto, ID, 2021-02-08), something (Ilia Petrov, RU, 2023-03-22), Jinggg (Wang Jing Jie, SG, returned to active 2024-03-29), invy (Adrian Reyes, PH, joined 2025-12-16). Head coach: alecks since 2021-02-08. Assistant coach: Wendler since 2025-11-13.

**Relevant player movements in the recent past, all verified from Liquipedia:**
- PatMen joined PRX 2025-03-04, won Masters Toronto with PRX, released 2025-12-15, now on Global Esports for 2026.
- mindfreak moved to reserve 2025-07-14, officially departed 2025-10-20.
- spicyuuu left 2025-11-05.
- invy is the only 2026 roster addition.

**PRX VLR team ID is 624** (confirmed from vlr.gg URL `https://www.vlr.gg/team/624/paper-rex`).

---

## 1. Project goal

Build a personal Valorant analytics system that produces probabilistic predictions for matches Rahat is watching — primarily PRX, secondarily any tier-1 VCT match. Predictions update from pre-match through during-match (coarse, score-triggered) and include a retrospective round-by-round replay after the match. Display is a web dashboard served from a Docker container running on Rahat's PC.

Rahat does no manual data work. Claude Code handles ingestion, cleaning, modeling, and deployment.

---

## 2. Hard constraints and scope decisions

1. **Tier 1 data only for v1** — vlrggapi (self-hosted) is the sole data source for v1. rib.gg via unofficial endpoints is a Phase 2 consideration after v1 is working.
2. **No code from Claude (researcher/planner role).** Claude Code does implementation against this spec.
3. **PRX-focused application, league-wide data layer.** The dashboard centers PRX but the ingestion pulls all tier-1 matches so the model has enough samples to be meaningful.
4. **No Riot official API.** Riot's published policy prohibits scouting tools and individual-player analytics without RSO opt-in — that excludes our use case from getting a production key.
5. **Player identity is independent of team.** Players carry historical stats from prior teams; a player's "current team" is determined by latest roster; their historical match data is attributed to whichever team they were on at the time.
6. **Self-host vlrggapi** because the public Vercel deployment is currently down (free-tier exhaustion, per the repo README).

---

## 3. Data sources — segmented by usability

### 3.1 Usable for v1 — vlrggapi (self-hosted)

vlrggapi is an unofficial REST scraper of vlr.gg, FastAPI + httpx + selectolax. MIT licensed. Rate limit 600 req/min. Built-in TTL caching. The relevant endpoints and what they give us:

| Endpoint | Use for v1 | Cache TTL |
|---|---|---|
| `GET /v2/team?id=624` | PRX profile, current roster, rating | 30 min |
| `GET /v2/team/matches?id={team_id}&page=N` | Match history per team (paginated) | 10 min |
| `GET /v2/team/transactions?id={team_id}` | Roster change history (player joined/left dates) | 1 hour |
| `GET /v2/player?id={id}&timespan=all` | Per-player career stats with agent breakdown | 30 min |
| `GET /v2/player/matches?id={id}&page=N` | Player match history | 10 min |
| `GET /v2/match/details?match_id={id}` | Per-map player stats, round-by-round outcomes with sides, economy summary per team per map, kill matrix, H2H, advanced stats (multi-kills, clutches) | 5 min normal, 30s live |
| `GET /v2/match?q=live_score` | Live match score with per-half side scores (`team1_round_ct`, `team1_round_t`, etc.), current map, map number | 30s |
| `GET /v2/match?q=upcoming` | Schedule | 5 min |
| `GET /v2/match?q=results` | Recent results | 1 hour |
| `GET /v2/events?q=upcoming\|completed` | Event list | 30 min |
| `GET /v2/events/matches?event_id={id}` | Match list within an event | 10 min |
| `GET /v2/rankings?region={code}` | Regional team rankings | 1 hour |
| `GET /v2/stats?region={code}&timespan={30\|60\|90\|all}` | Regional player stat leaderboards | 30 min |

**What this gives us:** match results, per-map results, per-round outcomes including which side won, per-map per-player stats (Rating, ACS, K/D/A, ADR, KAST, HS%, FK/FD, multi-kills, clutches), team-level economy splits (pistol/eco/semi-buy/full-buy win %), live score with side, agent picks per map, map veto (`picked_by`), event/series context, H2H history, roster transactions with dates.

**What this does NOT give us, in order of how much it would help:**
- Per-round economy (we get team aggregate per map, not round-by-round)
- Per-round utility usage
- Player positions or alive/dead state during a round
- First-blood timestamps within a round
- Spike plant/defuse outcomes per round
- Anything from Riot's observer feed

**Caveats and risks:**
- Some older matches on vlr.gg have parsing gaps in the rounds array. Plan for missing data per map.
- vlrggapi may break if vlr.gg's HTML changes. Mitigated by self-hosting a pinned version we control.
- 600 req/min ceiling is generous but back off appropriately during bulk ingestion.

### 3.2 External bootstrap — Peng IEEE DataPort dataset (2024 Pacific + EMEA)

Publicly available dataset of 1,301 rounds from 2024 VCT Pacific and EMEA. Fields: team loadout values, available ultimates, ultimate points, map, side, round outcome, plus historical map/atk-side/def-side win percentages per team. Use this BEFORE any of our own ingestion to validate the modeling pipeline. Free, clean, well-documented.

Reference: Peng's 2024 paper "A Predictive Analysis of Valorant Esports: Win Probability Through Economy and Ultimate Ability," TechRxiv, plus dataset on IEEE DataPort. Their logistic regression on three features (loadout difference, ultimate availability difference, ult points difference) hit 60.61% round-level accuracy — that's our published baseline to beat with vlrggapi data.

### 3.3 Phase 2 (NOT v1) — rib.gg unofficial endpoints

rib.gg has dramatically richer data: per-gunfight events with player positions (px, py), gun price and armor for both sides, agent, alive counts, round time, spike state. This is the dataset NRG Esports used for their published "Wins Above Expected" model. A community R package called `valorantr` (tonyelhabr/valorantr on GitHub) reverse-engineered the API. Status of the wrapper: "experimental," only 3 stars, possibly stale.

**Why not in v1:** unofficial endpoints (terms-of-service gray zone), wrapper may not work, much more complex schema. Re-evaluate after v1 ships and you've measured how accurate the tier-1 model is. If tier-1 accuracy ceilings out and you want better, this is the upgrade path.

### 3.4 Permanently out of scope — Riot official API

Per the 2020 Riot DevRel announcement, the VALORANT API requires a production key obtained by application pitch. Riot is "discerning" about approvals. Explicitly forbidden in policy: scouting tools, guides based on individual players, personalized data of any kind without per-player RSO opt-in. A PRX scouting/prediction tool is the textbook case Riot says no to. Document and forget.

---

## 4. Data scope and volume estimates

**Time range:** January 2024 through present (June 2026), continuing forward as new matches happen.

**Events included** (all tier-1, all four International Leagues, all Masters, all Champions):

*2024:*
- Kickoff (all 4 leagues, Feb 17 – March 8)
- Masters Madrid (March 14–24, Sentinels won)
- Stage 1 (all 4 leagues)
- Masters Shanghai (May 23 – June 9, Gen.G won)
- Stage 2 (all 4 leagues)
- Champions Seoul (Aug 1–25)

*2025:*
- Kickoff (all 4 leagues, Jan 11 – Feb 10)
- Masters Bangkok (Feb 20 – March 2, T1 won)
- Stage 1 (all 4 leagues)
- Masters Toronto (June 7–22, **PRX won**)
- Stage 2 (July 3 – Aug 31)
- Champions Paris (Sept 12 – Oct 5)

*2026 (in progress):*
- Kickoff (all 4 leagues, Jan 15 – Feb 15)
- Masters Santiago (PRX runner-up to Nongshim RedForce)
- Stage 1 (Pacific complete; others in progress per region)
- Masters London (starts June 6, 2026 — 2 days from this spec)
- Stage 2 + Champions Shanghai upcoming

**Excluded on purpose:**
- VCT Challengers / promotion leagues (tier 2) — different skill ceiling, would add noise
- Game Changers — separate circuit, treat as future expansion if interesting
- Showmatches, exhibitions, Red Bull Home Ground, off-season events — different incentive structure changes economy/play
- Pre-2024 data — patch and meta drift make older data weaker than its sample size suggests

**Volume estimate (back-of-envelope, not measured):**
- ~44 events across 2.5 years
- ~20–30 matches per event average
- → ~800–1,500 matches total
- Each match is 1–5 maps (Bo3/Bo5), average ~3
- → ~2,500–4,500 map records
- Each map has ~13–26 rounds
- → ~50,000–100,000 round records

Initial bulk ingestion is roughly 1,500 match-detail API calls. At 600 req/min that's ~3 minutes of API time plus the time to scrape/render each page on vlr.gg's end. Realistic wall-clock: 15–45 minutes for the full historical pull. SQLite storage: ~500MB–1GB. Trivially manageable.

---

## 5. Data warehouse schema (proposed)

SQLite, normalized. Tables and key fields:

**`teams`** — `team_id` (vlr.gg ID, PK), `name`, `tag`, `country`, `region`, `current_logo_url`. Updated periodically.

**`players`** — `player_id` (vlr.gg PK), `handle`, `real_name`, `country`, `current_team_id` (FK, nullable, latest known). The handle history is preserved via the matches table (since a player's stats are recorded under their handle as of that match).

**`roster_history`** — `player_id`, `team_id`, `role` (player/coach/assistant/manager/etc.), `joined_date`, `left_date` (nullable for active). Sourced from `/v2/team/transactions`. This is what lets us answer "who was on PRX in March 2025?" — essential for player-level historical analysis.

**`events`** — `event_id`, `name`, `tier` (Masters/Champions/RegionalLeague), `region` (NA/EMEA/PAC/CN/Global), `start_date`, `end_date`, `prize_usd`, `patch` (best-effort).

**`matches`** — `match_id` (vlr.gg PK), `event_id` (FK), `series_name`, `team1_id`, `team2_id`, `team1_score` (maps won), `team2_score`, `winner_id`, `date_utc`, `format` (Bo1/Bo3/Bo5), `match_url`.

**`maps`** — `map_id` (synthetic PK), `match_id` (FK), `map_index` (0–4), `map_name` (Bind/Ascent/etc.), `picked_by_team_id` (FK), `team1_score`, `team2_score`, `team1_ct_score`, `team1_t_score`, `team2_ct_score`, `team2_t_score`, `duration_seconds`, `winner_id`.

**`rounds`** — `round_id` (synthetic PK), `map_id` (FK), `round_number` (1–N), `half` ('first'|'second'|'OT'), `team1_side` ('CT'|'T'), `team2_side` ('CT'|'T'), `winner_id`. Sourced from match-detail `rounds` array. **Will have gaps for some older matches** — track `is_complete` boolean per map.

**`map_player_stats`** — composite key (`map_id`, `player_id`), plus `team_id_at_match` (important: their team at the time, not current), `agent`, `rating`, `acs`, `kills`, `deaths`, `assists`, `kast_pct`, `adr`, `hs_pct`, `fk`, `fd`. Sourced from match-detail.

**`map_team_economy`** — composite key (`map_id`, `team_id_at_match`), `pistol_win_pct`, `eco_win_pct`, `semi_buy_win_pct`, `full_buy_win_pct`. Team-level economy summary per map.

**`head_to_head`** — `match_id`, derived. Maybe pre-compute per (team_a, team_b) pair as a materialized view.

**`ratings_elo`** — `team_id`, `as_of_date`, `rating`, computed offline by Elo update logic.

**`ratings_elo_per_map`** — `team_id`, `map_name`, `as_of_date`, `rating_offset` (deviation from team's overall Elo on this map).

**`player_skill`** — `player_id`, `as_of_date`, `mu`, `sigma` (TrueSkill-style or Bayesian rating).

**Important schema rule:** `team_id_at_match` columns let us correctly attribute historical stats. Querying "PRX last 50 matches" pulls everything attributed to team_id=624 over time. Querying "PatMen's stats while on PRX" filters `map_player_stats` by `player_id` AND `team_id_at_match`=624.

---

## 6. Modeling approach

### 6.1 Why hierarchical Bayesian + Elo, and not a deep model

Small data forces this choice. The PRX-only corpus is in the low hundreds of matches; even league-wide we're talking thousands of maps, not millions. Hierarchical Bayesian methods with partial pooling are the textbook fit:

- **Complete pooling** ("every team is the same") loses too much information.
- **No pooling** ("PRX is unique, ignore everyone else") overfits and gives wide intervals on small per-team samples.
- **Partial pooling** shares strength across teams — PRX's parameters are pulled toward the league mean, more so when their sample is small and less so when it's large. This is the standard approach in academic and applied sports analytics (e.g., the PyMC rugby case study, baseball batting-average models).

XGBoost and neural nets are out of v1 scope: they need an order of magnitude more data than we have, and they don't quantify uncertainty natively — which matters when you're asserting "65% win prob" and the user wants to know how confident that is.

### 6.2 V1 model stack

**Layer 1 — Team strength via Elo:** Each team gets a rating. Update after each match. K-factor calibrated empirically (start at K=24, tune on 2024–2025 holdout). Initialize ratings using region-based priors so early-season is not arbitrary.

**Layer 2 — Map-specific Elo offsets:** Each (team, map) gets a deviation from the team's base Elo. PRX historically over-performs on certain maps; this captures that. Updated via partial pooling — if PRX has only 4 maps played on Sunset, the offset is pulled strongly toward zero.

**Layer 3 — Pre-match map win probability:** Bayesian logistic regression with features:
- Elo difference (team-level)
- Map-specific Elo difference
- Side first half (attack/defense) — encoded as which team is on each side
- Recent form (rolling 5-map W/L)
- H2H win rate (regularized — use empirical Bayes shrinkage toward league average when H2H samples are thin)
- Patch indicator (categorical, regularized) — see decision D1 in section 10 for the date→patch lookup requirement, since vlrggapi doesn't expose patch directly
- Tournament tier (regional vs Masters vs Champions)

Implemented in PyMC or in scikit-learn with sklearn-bayesian-models / Bambi for simplicity. PyMC is more flexible but slower; scikit-learn + a custom shrinkage step is faster to ship. **Recommendation: start with Bambi (Bayesian wrapper around statsmodels formulas) for v1 — fastest path to a working model with proper uncertainty estimates.**

**Layer 4 — Score-state lookup (the live-update mechanism):** Empirical table of `P(team wins map | current score, current half, current side, half score)`. Estimated from the full tier-1 corpus, not PRX-specific. Apply Laplace smoothing toward 50% for cells with sparse data (e.g., 8-4 to 9-4 specifically). Combined with the pre-match prior using Bayesian updating: posterior ∝ prior × likelihood-from-score.

**Layer 5 — Player skill model:** TrueSkill-style rating per (player_id, agent, map). Player skill is mostly about identifying over- and under-performers relative to expectation. Used for the "expected vs actual" panel during a match, not the win-prob computation directly. This is the layer that benefits most from going league-wide — gives every PRX player a credible baseline.

**Layer 6 (optional v1, definitely v2) — Player movement adjustment:** When PRX swaps a player (e.g., invy replacing PatMen for 2026), the team's effective rating should adjust. Naive Elo doesn't model this. Approach: decompose team rating as `base + Σ(player_skill_at_role)` so when invy joins, the team's expected performance shifts by `(invy's rating in initiator role) - (PatMen's rating in initiator role)`. Optional for v1 if it's complex; ship without it first and add it once PRX has more 2026 matches to calibrate against.

### 6.3 Realistic accuracy expectations

Calibrated against published precedent (Peng 60.61% round-level on the simple model with loadout, ult, ult points). Our model uses less granular round-level features (no live loadout) but more team-level signal (Elo, map-specific offsets, recent form). Likely outcomes:

- **Round-level accuracy:** 55–62% (we're worse than Peng on per-round inputs but pre-match prior helps before round 1)
- **Map-level accuracy:** 65–75% (errors average across rounds; Peng's loadout signal not needed because Elo carries the team-strength info)
- **Series/match-level accuracy:** 70–80% (further averaging)
- **Brier scores around 0.20–0.23** for map prediction (comparable to NRG's gunfight model at 0.228 — different task but similar order)

These are realistic targets, not aspirational. Don't lower the ceiling further but don't claim higher without measurement. Validate on a held-out time window (e.g., train on 2024+early 2025, test on Masters Toronto 2025 + 2026 events) before declaring success.

---

## 7. LLM integration — where it helps and where it doesn't

### 7.1 What LLMs are NOT for in this project

- Core probability estimation. Stats wins for structured prediction with limited data; using an LLM as the "predictor" would be slower, less calibrated, and untraceable.
- Round-level real-time prediction. Latency, cost, and unreliability all bad here.
- Filling in missing data. LLMs hallucinate; you'd be injecting noise into your training set.

### 7.2 What LLMs ARE for

1. **Natural-language explanation of predictions.** "PRX is 67% to win this map" → an LLM produces "Because they're 4-1 on Bind in their last 5, they're starting on defense which they prefer (61% def-side win rate), and Forsaken historically averages 1.23 rating vs DRX." This is where LLMs shine: turning structured data into readable text.

2. **Chat / question-answering interface on the data.** "How does Jinggg do on Lotus?" → LLM constructs a SQL query against your warehouse, runs it, summarizes. The "talk to your data" pattern. Works well when the schema is documented in the prompt.

3. **Scouting report generation.** Pre-match: "What should I watch for in PRX vs T1 today?" → LLM combines stats with historical context. Post-match: "Why did PRX lose round 14?" with structured round context.

4. **News and announcement parsing.** Roster changes are announced in tweets and press releases. An LLM can parse "Paper Rex is pleased to announce a new addition to our roster — please welcome invy" and emit a structured event `{team: PRX, player_handle: invy, action: joined, date: 2025-12-16}` for the roster_history table. Keeps the data fresh without manual entry.

5. **Anomaly explanation.** If the model says "PRX 92% win" but they lose, an LLM can synthesize "Forsaken had a 0.62 rating, well below his 1.15 average — that's the anomaly." Useful post-match analysis.

### 7.3 Recommended model and cost estimate

Verified pricing as of June 2026 (subject to change — verify before committing):

| Model | Input ($/1M) | Output ($/1M) | Notes |
|---|---|---|---|
| DeepSeek V4 Flash | ~$0.14 | ~$0.28 | Cheapest practical option. Strong general capability. Recommended default. |
| DeepSeek V4 Pro | ~$0.435 | ~$0.87 (promo through 2026-05-31; list $1.74/$3.48) | When V4 Flash isn't enough |
| Qwen 3 (varies by size) | from ~$0.01 input | varies | Wide range of model sizes; good for batch work |
| Kimi K2.6 | ~$0.74 | ~$4.66 | Premium pricing, no cheap tier; strong agentic capability |
| GLM-4.7 | similar to DeepSeek | similar | Reasoning-focused alternative |

**Recommendation: DeepSeek V4 Flash for everything in v1.** Per typical use:
- One explanation: ~2,000 input + 500 output tokens = ~$0.0004
- One chat query (with stats context): ~5,000 input + 1,000 output = ~$0.001
- 1,000 explanations/month = ~$0.40
- 10,000 chat queries/month = ~$10

LLM bill is rounding error vs. the value added. Use the OpenRouter or DeepSeek API directly. Keep model selection swappable via env var so you can A/B against Kimi or Qwen later without code changes.

### 7.4 Implementation note for Claude Code

The LLM layer should be a thin adapter, NOT coupled to the model layer. Architecture:
```
[stat model] → numerical prediction → [LLM adapter] → natural language
```
This way you can swap models, change prompts, or strip the LLM out entirely without touching the core math.

---

## 8. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ GitHub repo (prx-predictor)                                     │
│  ├── /ingestion (Python — pulls vlrggapi, writes SQLite)        │
│  ├── /models (Elo, Bayesian regression, score-state)            │
│  ├── /api (FastAPI — serves predictions)                        │
│  ├── /dashboard (HTML + JS — polls API)                         │
│  ├── /llm (DeepSeek adapter, prompts)                           │
│  ├── /docker (Dockerfile, docker-compose.yml)                   │
│  └── /.github/workflows (build + push to GHCR)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ GitHub Actions
                              ▼
                  ┌─────────────────────────┐
                  │ GHCR (container registry)│
                  └─────────────────────────┘
                              │
                              │ docker pull
                              ▼
                  ┌─────────────────────────┐
                  │ Rahat's PC (Docker)     │
                  │  ┌─────────────────┐    │
                  │  │ vlrggapi (3001) │    │
                  │  └─────────────────┘    │
                  │  ┌─────────────────┐    │
                  │  │ prx-app (8000)  │    │
                  │  │  + SQLite       │    │
                  │  │  + scheduler    │    │
                  │  └─────────────────┘    │
                  └─────────────────────────┘
                              │
                              │ http://desktop.local:8000
                              ▼
                  Web dashboard (any device on LAN)
```

**Container registry: GHCR over Docker Hub.** Native GitHub integration, no separate account, no relevant pull rate limits for personal use. Push from Actions, pull on PC. Simpler than the Docker Hub flow Rahat originally proposed.

**Two services via docker-compose:**
1. `vlrggapi` (upstream, pinned version — keep as-is, upgrade independently)
2. `prx-app` (your code: ingestion + models + API + dashboard + LLM adapter)

**Data refresh strategy:**
- Scheduled job inside `prx-app` container using APScheduler. Pulls new match data every 30 minutes during VCT season, hourly otherwise.
- Live-mode poll: when ANY tier-1 match is detected as "LIVE" via `/v2/match?q=live_score` (per decision D3, section 10), the scheduler temporarily polls every 30 seconds. Priority order if multiple live matches: PRX > Champions > Masters > Regional League > earliest start.
- Dashboard startup logic: front-end queries `live_score` on page load and immediately renders either live mode (if any tier-1 is live, picked by priority order) or pre-match mode for PRX's next scheduled match. Manual switcher is always visible.
- Model retraining: weekly, Sundays. Re-fits Elo from scratch + updates score-state lookup table + refreshes date→patch lookup from Riot patch notes.

**LAN access:** Expose `prx-app` port on the host's local IP (not just localhost) so phone/tablet/laptop on the same WiFi can hit it. Configure via `0.0.0.0:8000` binding in the FastAPI launch and explicit port-mapping in docker-compose.

**Power constraint to acknowledge:** PC must be on while the dashboard is in use. Live updates won't happen if the PC sleeps. Acceptable for "I'm watching the match on my desktop and want predictions" — not for "I want this while my PC is off."

---

## 9. Implementation phases for Claude Code

Numbered by dependency. Each phase produces an artifact that can be tested before moving on.

**Phase 0 — Pipeline validation with Peng dataset.** Download the IEEE DataPort 1,301-round dataset. Replicate Peng's logistic regression in a notebook. Confirm you can hit ~60% round accuracy. Goal: prove the modeling toolchain works on known-clean data before touching vlrggapi. Expected effort: 1 day.

**Phase 1 — Self-host vlrggapi.** Clone the repo, build the Docker image, run locally. Verify `/v2/health` and `/v2/team?id=624` both return PRX data. Set up a basic GHCR push from GitHub Actions for the combined image (vlrggapi + prx-app stub). Expected effort: 1 day.

**Phase 2 — Schema and ingestion.** Implement the SQLite schema from section 5. Write the ingestion script that walks `/v2/team/matches` for all tier-1 teams, then `/v2/match/details` for each match, then `/v2/team/transactions` for roster history. Handle the rounds-array gaps with `is_complete` flag. Bulk-load 2024 + 2025 + 2026-to-date. Expected output: a populated SQLite DB. Effort: 2–3 days.

**Phase 3 — Model layer.** Implement Elo (team + map-specific offsets), Bayesian logistic regression for pre-match win prob (Bambi recommended), and the score-state empirical lookup. Validate on a held-out time window: train on 2024+early 2025, test on Masters Toronto 2025 + Masters Santiago 2026. Report accuracy at round, map, and series level. Compare against Peng baseline. Effort: 3–5 days.

**Phase 4 — Player skill layer.** TrueSkill-style ratings per (player, agent, map). Hook into the existing pipeline. Effort: 2 days.

**Phase 5 — Live update logic.** Hook the `live_score` endpoint into the score-state model. When the score field changes, re-run prediction. Define the "live mode" polling cadence. Effort: 1–2 days.

**Phase 6 — FastAPI service + dashboard.** Build the prediction API endpoint, plus a single-page HTML dashboard that polls it every 30 seconds during live matches. Sections: pre-match panel, live win-prob panel, player expected-vs-actual panel, post-match retrospective. Use plain HTML + a charting library (Chart.js or similar — keep it light). Effort: 3 days.

**Phase 7 — LLM adapter.** Implement the DeepSeek V4 Flash adapter. Add explanation generation for predictions and a chat endpoint for QA on the warehouse. Prompt the LLM with schema info + the user's question and have it write SQL against SQLite. Effort: 2 days.

**Phase 8 — Deployment.** Finalize the docker-compose, GitHub Actions to build and push to GHCR, document `docker pull && docker compose up`. Test on Rahat's PC. Effort: 1 day.

**Phase 9 — Tier 2 evaluation.** Measure Phase 3's actual accuracy after 2–3 months of live use. Decide whether to add rib.gg data (gunfight-level features) for a v2 model. If accuracy is at the high end of expectations and you're satisfied, skip. If you want more, build the rib.gg ingestion using `valorantr` as reference. Note: this is a *post-v1* decision gate, not part of the v1 build.

Total v1 effort estimate: ~17 working days of Claude Code time (~3 calendar weeks at a moderate pace). Phase 9 is excluded from the v1 estimate since it's a post-launch decision gate.

**Roster updates note:** roster_history is maintained automatically via the `/v2/team/transactions` vlrggapi endpoint, polled during the weekly retrain job. No separate LLM-driven roster parsing layer (the originally-proposed Phase 9 was dropped during planning — the transactions endpoint covers the data need).

---

## 10. Decisions resolved during planning

The following three decisions were resolved by Rahat before implementation and are reflected in the relevant sections above.

**D1. Patch handling: rolling window with `patch_id` as a categorical feature.** Models do NOT reset at patch boundaries. The Bayesian logistic regression includes `patch_id` as a regularized categorical predictor (section 6.2, layer 3).

Implementation requirement Claude Code must address: **vlrggapi does not directly expose the patch version per match.** Claude Code needs to build and maintain a date-range → patch lookup, seeded from Riot's official patch notes (https://playvalorant.com/en-us/news/tags/patch-notes/). Mid-event patch changes do happen (Masters events often span 2+ weeks and can cross a patch), so patch must be attached at the *match* level, not the event level. Refresh the lookup as part of the weekly retrain job.

**D2. Player stats default scope: all career matches, with team-at-match shown alongside each stat.** The schema in section 5 already supports this via `team_id_at_match` in `map_player_stats`. Dashboard implementation requirement: every per-match row in player views must display the team context (logo + tag) for that match; aggregated views (career K/D, etc.) must show breakdowns by team stint rather than pooling across teams. Example: viewing PatMen shows his current Global Esports stats AND a separate panel for his 2025 PRX stint (where he won Masters Toronto).

**D3. Dashboard default view: auto-detect with priority order.** On dashboard open, the front-end queries `/v2/match?q=live_score`. Decision tree:
1. If a tier-1 match is currently live, show live mode for that match.
2. If multiple tier-1 matches are live, priority order: (a) PRX match if any, (b) higher tournament tier (Champions > Masters > Regional League), (c) earliest start time.
3. If no tier-1 match is live, show pre-match panel for PRX's next scheduled match.
A manual switcher must always be available to override the auto-detected view (e.g., to look at a non-PRX upcoming match the user is curious about).

## 11. Items for verification during implementation

These are observations Claude Code should handle while implementing — not blocking decisions:

1. **PRX VLR team ID continuity.** ID 624 is verified for current PRX. Confirm during Phase 2 that this ID has been stable since 2020 — if at any point the org changed its vlr.gg entity (rare but possible), older matches may be under a different ID and need to be merged.

2. **Game Changers separation.** Excluded for v1, but if we ever expand, make sure the corpus is clearly partitioned — don't pool GC and main tier-1 stats together.

3. **2026 Champions Shanghai recalibration.** Champions hasn't happened yet (scheduled October 2026). When it does, the model will absorb ~1 month of high-stakes data that may meaningfully shift ratings. Plan for a mid-October retrain that's slightly more aggressive (higher K-factor) so the new data weighs appropriately.

---

## 12. References (verified during planning)

**Data sources:**
- vlrggapi repo: https://github.com/axsddlr/vlrggapi
- Liquipedia PRX page: https://liquipedia.net/valorant/Paper_Rex
- vlr.gg PRX team: https://www.vlr.gg/team/624/paper-rex
- valorantr (rib.gg wrapper): https://github.com/tonyelhabr/valorantr
- IEEE DataPort Peng dataset: search "Valorant Champions Tour 2024 Pacific EMEA round data"
- Complete Valorant Champions Tour 2024 - All events: https://www.kaggle.com/datasets/piyush86kumar/valorant-champions-tour-2024-all-events
- Valorant 2025 -All Events International + Regional: https://www.kaggle.com/datasets/piyush86kumar/valorant-vct-2025-all-events

**Published prior art:**
- Peng, Y. (2024). "A Predictive Analysis of Valorant Esports: Win Probability Through Economy and Ultimate Ability." TechRxiv.
- NRG DeRover, D. et al. "Winning Fights in VALORANT: A Predictive Analytics Approach." MIT Sloan-style paper, NRG Esports.
- Multiple academic Bayesian sports modeling references (PyMC rugby example, Stan partial pooling case study).

**Reference policies:**
- Riot Games VALORANT API Launch and Policies (2020): https://www.riotgames.com/en/DevRel/valorant-api-launch

**Cheap LLM landscape (as of June 2026):**
- Multiple comparison articles confirming DeepSeek V4 Flash ($0.14/$0.28 per 1M tokens) as the practical cheap default, with Kimi K2.6, Qwen 3, GLM-4.7 as alternatives.

---

## Appendix A — PRX active roster verified (2026)

| Handle | Real name | Country | Joined active | Source |
|---|---|---|---|---|
| d4v41 | Ahmad Khalish Rusyaidee bin Nordin | Malaysia | 2021-02-08 | Liquipedia |
| f0rsakeN | Jason Susanto | Indonesia | 2021-02-08 | Liquipedia |
| something | Ilia Petrov | Russia | 2023-03-22 | Liquipedia |
| Jinggg | Wang Jing Jie | Singapore | 2024-03-29 (return to active) | Liquipedia |
| invy | Adrian Jiggs Aisa Reyes | Philippines | 2025-12-16 | Liquipedia |

Coaches: alecks (head, since 2021-02-08), Wendler (assistant, since 2025-11-13). Manager: Tommy.

## Appendix B — VCT calendar 2024–2026 (verified)

| Year | Events |
|---|---|
| 2024 | Kickoff → Masters Madrid (won by Sentinels) → Stage 1 → Masters Shanghai (won by Gen.G) → Stage 2 → Champions Seoul |
| 2025 | Kickoff → Masters Bangkok (won by T1) → Stage 1 → Masters Toronto (won by **PRX**) → Stage 2 → Champions Paris |
| 2026 | Kickoff → Masters Santiago (won by Nongshim RedForce; PRX runner-up) → Stage 1 → Masters London (June 6–21, ongoing as of spec date) → Stage 2 → Champions Shanghai (upcoming) |

End of spec.
