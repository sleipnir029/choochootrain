# ARCHITECTURE.md

System architecture for PRX Predictor v1: data warehouse schema, API contract, service wiring, model integration points, LLM integration.

This document is referenced by `CLAUDE.md` and `docs/TASKS.md`. Don't change anything here without an entry in `docs/DEVIATIONS.md`.

---

## 1. System overview

```
┌───────────────────────────────────────────────────────────────────┐
│ GitHub repo (prx-predictor)                                       │
│  source → tagged release                                          │
└──────────────────────────────┬────────────────────────────────────┘
                               │ GitHub Actions
                               ▼
                  ┌────────────────────────┐
                  │ GHCR container registry│
                  └────────────┬───────────┘
                               │ docker pull
                               ▼
            ┌──────────────────────────────────────┐
            │ Rahat's PC (Docker)                  │
            │  ┌─────────────────┐                 │
            │  │ vlrggapi:3001   │  internal only  │
            │  └────────┬────────┘                 │
            │           │ HTTP                     │
            │           ▼                          │
            │  ┌────────────────────────────────┐  │
            │  │ prx-app:8000                   │  │
            │  │  ├── api/    (FastAPI)         │  │
            │  │  ├── ingestion/                │  │
            │  │  ├── models/                   │  │
            │  │  ├── scheduler/ (APScheduler)  │  │
            │  │  ├── llm/    (DeepSeek)        │  │
            │  │  └── dashboard/ (React build)  │  │
            │  └────────┬───────────────────────┘  │
            │           │ reads/writes             │
            │           ▼                          │
            │  ┌────────────────────────────────┐  │
            │  │ SQLite: data/prx.db            │  │
            │  └────────────────────────────────┘  │
            └──────────────────┬───────────────────┘
                               │ HTTP (LAN)
                               ▼
              ┌──────────────────────────────┐
              │ Web dashboard (any LAN device)│
              └──────────────────────────────┘
```

---

## 2. Database schema (SQLite)

All tables in one SQLite file at `data/prx.db`. Foreign keys enforced (`PRAGMA foreign_keys = ON`).

### 2.1 Reference tables

```sql
CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY,                  -- vlr.gg team ID
    name TEXT NOT NULL,
    tag TEXT,
    country TEXT,
    region TEXT,                                  -- 'na', 'emea', 'pac', 'cn'
    logo_url TEXT,
    last_updated TEXT NOT NULL                    -- ISO 8601
);

CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,                -- vlr.gg player ID
    handle TEXT NOT NULL,
    real_name TEXT,
    country TEXT,
    current_team_id INTEGER,                      -- latest known active team
    last_updated TEXT NOT NULL,
    FOREIGN KEY (current_team_id) REFERENCES teams(team_id)
);

CREATE TABLE roster_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    role TEXT NOT NULL,                           -- 'player', 'coach', 'assistant_coach', 'manager', 'analyst'
    joined_date TEXT NOT NULL,                    -- ISO 8601 date
    left_date TEXT,                               -- NULL if still active
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE INDEX idx_roster_player ON roster_history(player_id);
CREATE INDEX idx_roster_team_active ON roster_history(team_id, left_date);

CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,                 -- vlr.gg event ID
    name TEXT NOT NULL,
    tier TEXT NOT NULL,                           -- 'Champions', 'Masters', 'RegionalLeague', 'Kickoff'
    region TEXT NOT NULL,                         -- 'global' for Masters/Champions, else regional code
    start_date TEXT NOT NULL,                     -- ISO 8601 date
    end_date TEXT NOT NULL,
    prize_usd INTEGER
);

CREATE TABLE patches (
    patch_id TEXT PRIMARY KEY,                    -- e.g., '8.05', '9.01'
    release_date TEXT NOT NULL,                   -- ISO 8601 date
    notes_url TEXT
);
```

### 2.2 Match data

```sql
CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY,                 -- vlr.gg match ID
    event_id INTEGER NOT NULL,
    series_name TEXT,                             -- 'Quarterfinal', 'Grand Final', 'Regular Season Week 3'
    team1_id INTEGER NOT NULL,
    team2_id INTEGER NOT NULL,
    team1_score INTEGER NOT NULL,                 -- maps won by team1
    team2_score INTEGER NOT NULL,
    winner_id INTEGER,                            -- NULL if draw / not yet decided
    date_utc TEXT NOT NULL,                       -- ISO 8601 datetime
    format TEXT NOT NULL,                         -- 'Bo1', 'Bo3', 'Bo5'
    patch_id TEXT,                                -- determined from date_utc + patches table
    match_url TEXT,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (team1_id) REFERENCES teams(team_id),
    FOREIGN KEY (team2_id) REFERENCES teams(team_id),
    FOREIGN KEY (winner_id) REFERENCES teams(team_id),
    FOREIGN KEY (patch_id) REFERENCES patches(patch_id)
);
CREATE INDEX idx_matches_date ON matches(date_utc);
CREATE INDEX idx_matches_team1 ON matches(team1_id);
CREATE INDEX idx_matches_team2 ON matches(team2_id);
CREATE INDEX idx_matches_event ON matches(event_id);

CREATE TABLE maps (
    map_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    map_index INTEGER NOT NULL,                   -- 0..4 for Bo5
    map_name TEXT NOT NULL,                       -- 'Bind', 'Ascent', 'Sunset', etc.
    picked_by_team_id INTEGER,                    -- which team selected this map in veto
    team1_score INTEGER NOT NULL,
    team2_score INTEGER NOT NULL,
    team1_ct_score INTEGER,                       -- rounds won on CT side
    team1_t_score INTEGER,                        -- rounds won on T side
    team2_ct_score INTEGER,
    team2_t_score INTEGER,
    duration_seconds INTEGER,
    winner_id INTEGER,
    is_rounds_complete INTEGER NOT NULL DEFAULT 0, -- 1 if rounds[] array fully present
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (picked_by_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (winner_id) REFERENCES teams(team_id),
    UNIQUE(match_id, map_index)
);
CREATE INDEX idx_maps_match ON maps(match_id);

CREATE TABLE rounds (
    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,                -- 1..N
    half TEXT NOT NULL,                           -- 'first', 'second', 'ot'
    team1_side TEXT NOT NULL,                     -- 'ct' or 't'
    team2_side TEXT NOT NULL,                     -- 'ct' or 't'
    winner_id INTEGER NOT NULL,
    FOREIGN KEY (map_id) REFERENCES maps(map_id),
    FOREIGN KEY (winner_id) REFERENCES teams(team_id),
    UNIQUE(map_id, round_number)
);
CREATE INDEX idx_rounds_map ON rounds(map_id);
```

### 2.3 Per-map per-player stats

```sql
-- NOTE: keyed on (map_id, player_handle) because /v2/match/details exposes
-- player handles, not numeric IDs. player_id is nullable and backfilled in
-- P2.T7 by resolving handles -> vlr.gg player IDs. See docs/DEVIATIONS.md
-- (2026-06-04, P2.T6).
CREATE TABLE map_player_stats (
    map_id INTEGER NOT NULL,
    player_handle TEXT NOT NULL,                  -- handle as it appears in the match
    player_id INTEGER,                            -- resolved from handle in P2.T7 (NULL until then)
    team_id_at_match INTEGER NOT NULL,            -- CRITICAL: team at the time, not current
    agent TEXT NOT NULL,
    rating REAL,
    acs INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    kast_pct INTEGER,                             -- 0..100
    adr REAL,
    hs_pct INTEGER,
    fk INTEGER,                                   -- first kills
    fd INTEGER,                                   -- first deaths
    PRIMARY KEY (map_id, player_handle),
    FOREIGN KEY (map_id) REFERENCES maps(map_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id_at_match) REFERENCES teams(team_id)
);
CREATE INDEX idx_mps_player ON map_player_stats(player_id);
CREATE INDEX idx_mps_handle ON map_player_stats(player_handle);
CREATE INDEX idx_mps_team ON map_player_stats(team_id_at_match);

CREATE TABLE map_team_economy (
    map_id INTEGER NOT NULL,
    team_id_at_match INTEGER NOT NULL,
    pistol_win_pct INTEGER,                       -- 0..100
    eco_win_pct INTEGER,
    semi_buy_win_pct INTEGER,
    full_buy_win_pct INTEGER,
    PRIMARY KEY (map_id, team_id_at_match),
    FOREIGN KEY (map_id) REFERENCES maps(map_id)
);
```

### 2.4 Model state tables

```sql
CREATE TABLE elo_ratings (
    team_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,                     -- ISO 8601 date
    rating REAL NOT NULL,
    PRIMARY KEY (team_id, as_of_date)
);
CREATE INDEX idx_elo_team_date ON elo_ratings(team_id, as_of_date DESC);

CREATE TABLE elo_map_offsets (
    team_id INTEGER NOT NULL,
    map_name TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    rating_offset REAL NOT NULL,                  -- deviation from team's overall Elo on this map
    PRIMARY KEY (team_id, map_name, as_of_date)
);

CREATE TABLE player_skill (
    player_id INTEGER NOT NULL,
    agent TEXT,                                   -- NULL for overall, or specific agent
    map_name TEXT,                                -- NULL for overall, or specific map
    as_of_date TEXT NOT NULL,
    mu REAL NOT NULL,                             -- TrueSkill mean
    sigma REAL NOT NULL,                          -- TrueSkill std deviation
    PRIMARY KEY (player_id, agent, map_name, as_of_date)
);

CREATE TABLE score_state_lookup (
    half TEXT NOT NULL,                           -- 'first', 'second'
    team_score INTEGER NOT NULL,
    opp_score INTEGER NOT NULL,
    side TEXT NOT NULL,                           -- side the team is on for the upcoming round
    n_observations INTEGER NOT NULL,
    n_wins INTEGER NOT NULL,
    smoothed_win_pct REAL NOT NULL,               -- with Laplace smoothing
    PRIMARY KEY (half, team_score, opp_score, side)
);
```

### 2.5 Live state tables

```sql
CREATE TABLE live_state (
    -- Singleton table; max 1 row per currently-tracked live match
    match_id INTEGER PRIMARY KEY,
    team1_id INTEGER,                             -- resolved from the live segment name (nullable)
    team2_id INTEGER,                             -- enables live prediction + PRX-framing of an un-ingested match
    team1_score INTEGER,
    team2_score INTEGER,
    team1_round_ct INTEGER,
    team1_round_t INTEGER,
    team2_round_ct INTEGER,
    team2_round_t INTEGER,
    map_number INTEGER,
    current_map TEXT,
    last_updated TEXT NOT NULL,                   -- ISO 8601 datetime
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

CREATE TABLE live_predictions (
    match_id INTEGER NOT NULL,
    map_index INTEGER NOT NULL,
    computed_at TEXT NOT NULL,                    -- ISO 8601 datetime
    team1_win_prob REAL NOT NULL,
    explanation TEXT,                             -- LLM-generated (lazy, computed on demand)
    PRIMARY KEY (match_id, map_index, computed_at)
);
```

---

## 3. API contract (FastAPI)

Base URL: `http://localhost:8000/api/`. All responses JSON.

### 3.1 Predictions

#### `GET /api/predict/pre-match?match_id={id}` — *ingested mode*
#### `GET /api/predict/pre-match?team1_id={a}&team2_id={b}[&event_id={e}]` — *upcoming mode*
Returns the pre-match prediction. **Two modes** (one of `match_id` *or* the `team1_id`+`team2_id` pair is required):
- **ingested** (`match_id`): the match already exists in the warehouse (completed/demo). Per-map probabilities come from `models.predict.predict_map_win_prob` on each ingested map.
- **upcoming** (`team1_id`+`team2_id`): a match **not** in the warehouse (e.g. PRX's next scheduled match per D3). Maps aren't known until veto, so a single team-strength prob is used and `map_predictions` is empty. Backed by `models.upcoming.predict_upcoming_win_prob` (the as-of-now feature builder).

```json
{
  "mode": "ingested",
  "match_id": 595657,
  "team1": {"id": 624, "name": "Paper Rex", "logo": "..."},
  "team2": {"id": 188, "name": "Sentinels", "logo": "..."},
  "series_win_prob": {"team1": 0.62, "team2": 0.38},
  "series_format": "Bo3",
  "map_predictions": [
    {"map_name": "Bind", "team1_win_prob": 0.71, "team1_win_prob_hdi": [0.64, 0.78], "picked_by": "team1"},
    {"map_name": "Ascent", "team1_win_prob": 0.55, "team1_win_prob_hdi": [0.47, 0.63], "picked_by": "team2"}
  ],
  "team1_win_prob": 0.62,
  "team1_win_prob_hdi": [0.54, 0.69],
  "top_factors": [
    {"factor": "Elo difference", "weight": 0.45, "favors": "team1"},
    {"factor": "Player skill", "weight": 0.22, "favors": "team1"},
    {"factor": "Recent form", "weight": 0.15, "favors": "team1"}
  ]
}
```

Notes:
- **`series_win_prob`** is *derived, not modeled*: each map is treated as an independent Bernoulli(p) and the Bo-N series win prob is computed in closed form. Upcoming mode (no veto) uses one team-strength `p` for every map.
- **`top_factors`** is an *interpretable attribution* (posterior-mean coefficient × standardized feature value per feature, ranked by magnitude; `favors` = sign relative to team1) — not exact Shapley. The natural-language explanation is a separate Phase-7 LLM call (`POST /api/llm/explain`).
- **`*_hdi`** is the highest-density credible interval of the posterior probability (SPEC §6.1 — surface uncertainty, not just a point estimate).
- Upcoming mode returns `"mode": "upcoming"`, `"map_predictions": []`, and no `match_id`.

#### `GET /api/predict/live`
Returns the current live prediction. **Reads the `live_state` + `live_predictions` tables** written by the P5 live poller (`scheduler/jobs/live_poll.py`); the API does not poll vlrggapi itself for this. The poller must be running for live data to appear (full scheduler wiring is Phase 8). `current_map_index` selects the tracked map's latest `live_predictions` row.
```json
{
  "mode": "live",
  "match_id": 595657,
  "current_map_index": 1,
  "current_map": "Ascent",
  "team1_score": 9,
  "team2_score": 4,
  "team1_round_ct": 5,
  "team1_round_t": 4,
  "team2_round_ct": 2,
  "team2_round_t": 2,
  "team1_win_prob_current_map": 0.78,
  "team1_win_prob_series": 0.85,
  "probability_history": [{"round": 1, "prob": 0.55}, ...]
}
```
If `live_state` is empty (no tier-1 match live): `{"mode": "no_live", "next_prx_match": {...}}`, where `next_prx_match` is sourced from vlrggapi upcoming (same source as `/api/matches/upcoming`).

#### `GET /api/predict/replay?match_id={id}`
Returns the round-by-round retrospective trace for a completed match.
```json
{
  "match_id": 595657,
  "maps": [
    {
      "map_index": 0,
      "map_name": "Bind",
      "rounds": [
        {"round": 1, "team1_side": "ct", "pre_round_prob_team1": 0.55, "winner": "team1"},
        {"round": 2, "team1_side": "ct", "pre_round_prob_team1": 0.61, "winner": "team2"}
      ]
    }
  ]
}
```

### 3.2 Reference data

#### `GET /api/teams/{id}`
Team profile + current active roster (filtered from roster_history where left_date IS NULL).

#### `GET /api/teams/{id}/matches?limit=20`
Recent matches for a team.

#### `GET /api/players/{id}`
Player profile.

#### `GET /api/players/{id}/stats?group_by=team_stint`
Player stats broken down by team stint (per D2). Each stint shows date range, aggregate K/D/A, top maps, top agents.

#### `GET /api/events?status={upcoming|completed|live}`
Tier-1 events.

#### `GET /api/matches/upcoming?team_id={id}`
Next scheduled match(es) for a team.

### 3.3 LLM endpoints *(Phase 7 — not implemented in the Phase 6 backend)*

#### `POST /api/llm/explain`
```json
// Request
{"type": "pre-match", "match_id": 595657}

// Response
{"explanation": "Paper Rex enters this match with a notable Elo edge..."}
```

#### `POST /api/llm/chat`
```json
// Request
{"question": "How does Jinggg perform on Bind?"}

// Response
{
  "answer": "Jinggg has played 12 maps on Bind in 2024-2026 with a 1.21 average rating...",
  "sql_executed": "SELECT ... FROM map_player_stats WHERE player_id = ..."
}
```

---

## 4. Service wiring

### 4.1 Containers
- `vlrggapi`: vendored upstream, port 3001 internal-only, talks only to vlr.gg upstream
- `prx-app`: our code, port 8000 exposed to host LAN

### 4.2 Internal communication
- `prx-app` → `vlrggapi`: `http://vlrggapi:3001/v2/...` (via docker-compose default network)
- All env config in `.env`: `VLRGGAPI_URL`, `DEEPSEEK_API_KEY`, `DATA_DIR`, `LOG_LEVEL`, `VLR_CACHE_DIR` (vlrggapi response cache dir; default `data/http_cache`)

### 4.3 Module boundaries (importable, no circular deps)
- `ingestion/` imports from `models/.schema` only
- `models/` is pure compute; no I/O except via passed-in DB connections
- `api/` imports from `models/`, `ingestion/`, `llm/` — never the other way
- `llm/` is independent; doesn't know about `models/` or `api/`
- `scheduler/` orchestrates `ingestion/` and `models/`; doesn't depend on `api/`

### 4.4 Data flow

**Ingestion path:**
```
scheduler → ingestion.vlr_client → vlrggapi (HTTP) → ingestion.{teams,events,matches,...} → SQLite
```

**Prediction path (pre-match):**
```
api → models.predict → SQLite (read elo_ratings, elo_map_offsets, training data lookups)
                    → Bambi posterior trace (loaded from disk) → response
```

**Prediction path (live):**
```
scheduler.live_poll → vlrggapi → score change detected → models.predict (with live_state)
                                                       → score_state_lookup (Bayesian update)
                                                       → SQLite (write live_predictions)
api → reads live_predictions → response
```

**LLM path (explain):**
```
api → llm.deepseek_client → DeepSeek API
                          → response → api → frontend
```

**LLM path (chat):**
```
api → llm.deepseek_client (with schema context) → SQL string
    → llm.sql_executor (SELECT-only validator) → SQLite → result
    → llm.deepseek_client (summarize) → answer → frontend
```

---

## 5. Model integration points

### 5.1 Where the model is loaded
- Bambi posterior trace: `models/saved/bayes_logistic.nc` (loaded once at API startup, kept in memory)
- Elo ratings: queried from `elo_ratings` table on each prediction (latest row per team_id)
- Score-state lookup: full table loaded into a dict at API startup (small, ~few KB)
- Player skills: queried from `player_skill` table per request

### 5.2 Update cadence
- Bambi model: re-trained weekly (Sunday 03:00 UTC); new posterior saved, API picks it up on next restart
- Elo ratings: appended after every new match ingestion (incremental)
- Score-state lookup: re-computed weekly along with model retrain
- Player skills: appended after every new match ingestion

### 5.3 Prediction call signatures

The core predictor returns a bare **`float`** (P(team1 wins the map)); the live poller (Phase 5) depends on this. The API layer composes `top_factors` + a credible interval separately (the earlier `Prediction(...)` object was never built).

```python
def predict_map_win_prob(
    match_id: int,
    map_index: int,
    live_state: dict | None = None,
    *, db_path: str = "data/prx.db",
) -> float:
    """
    P(team1 wins the map), in [0, 1].
    live_state is None  -> pre-match prediction (Bambi prior only).
    live_state provided -> log-odds pool of the prior with the score_state likelihood.
    live_state shape (team1's perspective):
        {"half": "second", "team1_score": 9, "team2_score": 3, "team1_side": "ct"}
    """
```

The API uses two thin composition helpers (Phase 6) over the same cached resources:

```python
# models/predict.py — for the pre-match / replay panels
def predict_map_win_prob_detailed(match_id, map_index, *, db_path=...) -> dict:
    """{'team1_win_prob': float, 'hdi': [lo, hi], 'top_factors': [{factor, weight, favors}, ...]}.
    hdi = highest-density interval of the posterior p; top_factors = coef × standardized
    feature value per term (interpretable attribution, not exact Shapley)."""

# models/upcoming.py — for the pre-match panel on an UNPLAYED match (D3 default view)
def predict_upcoming_win_prob(team1_id, team2_id, *, as_of_date=None, db_path=...) -> dict:
    """As-of-now team-strength prediction from snapshot tables (latest elo_ratings,
    current-roster player_skill, recent form, H2H). Returns the same dict shape as
    predict_map_win_prob_detailed (map_elo/side neutral until veto)."""
```

---

## 6. LLM integration

### 6.1 Model
DeepSeek V4 Flash (`deepseek-chat`). Input ~$0.14/1M, output ~$0.28/1M as of June 2026. Verify pricing at runtime by reading `.env`.

### 6.2 Prompt templates (`llm/prompts/`)
- `explain.py`: takes a prediction context dict, produces a 2-3 sentence explanation in plain English
- `chat.py`: takes a user question + schema description, produces a SQL string

### 6.3 Schema documentation in the chat prompt
The schema description sent to the LLM for chat-on-data is a curated subset (not the full DDL) — just the tables and columns relevant to common questions. Lives in `llm/prompts/schema_context.py`. Update when schema changes.

### 6.4 SQL safety
- `llm/sql_executor.py` runs SQL only after verifying:
  - Starts with `SELECT`
  - No `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `PRAGMA`
  - No semicolons (single statement only)
- Errors are caught and returned to the LLM for one retry; second failure returns an error to the user

### 6.5 Cost guardrails (`llm/budget.py`)
- Per-request token caps: 5000 input / 1500 output
- Daily budget cap: $1 USD (configurable via env)
- Tracked in `data/llm_usage.json`, reset daily
- Crossing the cap raises `LLMBudgetExceeded` exception; API returns 429 with `Retry-After`

---

## 7. Frontend ↔ API contract

Frontend is a React SPA served from FastAPI at `/`. It calls `/api/...` for data.

### 7.1 Polling cadence
- Live mode: poll `/api/predict/live` every 30 seconds
- Pre-match mode: load once on mount; no polling
- Manual refresh button always available

### 7.2 State management
- React Query (TanStack Query) for server state — caches, dedupes, retries
- No global state library needed; component state + URL params is enough

### 7.3 Routing
- `/` — auto-detect mode (live if available, else next-PRX-match)
- `/match/:id` — manual match view
- `/team/:id` — team profile
- `/player/:id` — player profile

---

## 8. Logging

- structlog throughout
- INFO by default; DEBUG via env (`LOG_LEVEL=DEBUG`)
- Two sinks: stdout (Docker captures) and `logs/app.log` (rotating)
- Format: JSON in production, key=value in dev
- Always log: request_id, user-facing errors, scheduler job start/end, LLM token usage

---

## 9. Tests

- pytest, lives in `tests/`
- Unit tests for: Elo math, score-state lookup logic, SQL safety validator, prediction combiner, LLM prompt formatters
- Integration tests for: ingestion idempotency (run twice, same result), API endpoint shapes
- No e2e tests for the dashboard in v1 (manual verification)
- Coverage target: not a hard number, but every model function should have at least one test
