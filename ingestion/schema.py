"""SQLite warehouse schema for PRX Predictor.

The DDL below is the schema defined in docs/ARCHITECTURE.md §2 (the source of
truth). `init_db(path)` creates the SQLite file and runs every CREATE statement;
it is idempotent (IF NOT EXISTS) so re-running it on an existing DB is a no-op.

CLI:
    python -m ingestion.schema init data/prx.db
"""

import sqlite3
import sys
from pathlib import Path

# Transcribed from docs/ARCHITECTURE.md §2. Keep in sync with that document; any
# change here needs a docs/DEVIATIONS.md entry per the repo protocol.
SCHEMA_SQL = """
-- 2.1 Reference tables ------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY,                  -- vlr.gg team ID
    name TEXT NOT NULL,
    tag TEXT,
    country TEXT,
    region TEXT,                                  -- 'na', 'emea', 'pac', 'cn'
    logo_url TEXT,
    last_updated TEXT NOT NULL                    -- ISO 8601
);

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,                -- vlr.gg player ID
    handle TEXT NOT NULL,
    real_name TEXT,
    country TEXT,
    current_team_id INTEGER,                      -- latest known active team
    last_updated TEXT NOT NULL,
    FOREIGN KEY (current_team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS roster_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    role TEXT NOT NULL,                           -- 'player', 'coach', 'assistant_coach', 'manager', 'analyst'
    joined_date TEXT NOT NULL,                    -- ISO 8601 date
    left_date TEXT,                               -- NULL if still active
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
CREATE INDEX IF NOT EXISTS idx_roster_player ON roster_history(player_id);
CREATE INDEX IF NOT EXISTS idx_roster_team_active ON roster_history(team_id, left_date);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY,                 -- vlr.gg event ID
    name TEXT NOT NULL,
    tier TEXT NOT NULL,                           -- 'Champions', 'Masters', 'RegionalLeague', 'Kickoff'
    region TEXT NOT NULL,                         -- 'global' for Masters/Champions, else regional code
    start_date TEXT NOT NULL,                     -- ISO 8601 date
    end_date TEXT NOT NULL,
    prize_usd INTEGER
);

CREATE TABLE IF NOT EXISTS patches (
    patch_id TEXT PRIMARY KEY,                    -- e.g., '8.05', '9.01'
    release_date TEXT NOT NULL,                   -- ISO 8601 date
    notes_url TEXT
);

-- 2.2 Match data ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
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
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date_utc);
CREATE INDEX IF NOT EXISTS idx_matches_team1 ON matches(team1_id);
CREATE INDEX IF NOT EXISTS idx_matches_team2 ON matches(team2_id);
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);

CREATE TABLE IF NOT EXISTS maps (
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
CREATE INDEX IF NOT EXISTS idx_maps_match ON maps(match_id);

CREATE TABLE IF NOT EXISTS rounds (
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
CREATE INDEX IF NOT EXISTS idx_rounds_map ON rounds(map_id);

-- 2.3 Per-map per-player stats ---------------------------------------------
-- Keyed on (map_id, player_handle): /v2/match/details exposes handles, not
-- numeric IDs. player_id is NULL until P2.T7 resolves it. See DEVIATIONS.
CREATE TABLE IF NOT EXISTS map_player_stats (
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
CREATE INDEX IF NOT EXISTS idx_mps_player ON map_player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_mps_handle ON map_player_stats(player_handle);
CREATE INDEX IF NOT EXISTS idx_mps_team ON map_player_stats(team_id_at_match);

CREATE TABLE IF NOT EXISTS map_team_economy (
    map_id INTEGER NOT NULL,
    team_id_at_match INTEGER NOT NULL,
    pistol_win_pct INTEGER,                       -- 0..100
    eco_win_pct INTEGER,
    semi_buy_win_pct INTEGER,
    full_buy_win_pct INTEGER,
    PRIMARY KEY (map_id, team_id_at_match),
    FOREIGN KEY (map_id) REFERENCES maps(map_id)
);

-- 2.4 Model state tables ----------------------------------------------------
CREATE TABLE IF NOT EXISTS elo_ratings (
    team_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,                     -- ISO 8601 date
    rating REAL NOT NULL,
    PRIMARY KEY (team_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_elo_team_date ON elo_ratings(team_id, as_of_date DESC);

CREATE TABLE IF NOT EXISTS elo_map_offsets (
    team_id INTEGER NOT NULL,
    map_name TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    rating_offset REAL NOT NULL,                  -- deviation from team's overall Elo on this map
    PRIMARY KEY (team_id, map_name, as_of_date)
);

CREATE TABLE IF NOT EXISTS player_skill (
    player_id INTEGER NOT NULL,
    agent TEXT,                                   -- NULL for overall, or specific agent
    map_name TEXT,                                -- NULL for overall, or specific map
    as_of_date TEXT NOT NULL,
    mu REAL NOT NULL,                             -- TrueSkill mean
    sigma REAL NOT NULL,                          -- TrueSkill std deviation
    PRIMARY KEY (player_id, agent, map_name, as_of_date)
);

CREATE TABLE IF NOT EXISTS score_state_lookup (
    half TEXT NOT NULL,                           -- 'first', 'second'
    team_score INTEGER NOT NULL,
    opp_score INTEGER NOT NULL,
    side TEXT NOT NULL,                           -- side the team is on for the upcoming round
    n_observations INTEGER NOT NULL,
    n_wins INTEGER NOT NULL,
    smoothed_win_pct REAL NOT NULL,               -- with Laplace smoothing
    PRIMARY KEY (half, team_score, opp_score, side)
);

-- 2.5 Live state tables -----------------------------------------------------
CREATE TABLE IF NOT EXISTS live_state (
    -- Singleton table; max 1 row per currently-tracked live match
    match_id INTEGER PRIMARY KEY,
    team1_id INTEGER,                             -- resolved from the live segment name (nullable);
    team2_id INTEGER,                             -- lets us predict + PRX-frame an un-ingested live match
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

CREATE TABLE IF NOT EXISTS live_predictions (
    match_id INTEGER NOT NULL,
    map_index INTEGER NOT NULL,
    computed_at TEXT NOT NULL,                    -- ISO 8601 datetime
    team1_win_prob REAL NOT NULL,
    explanation TEXT,                             -- LLM-generated (lazy, computed on demand)
    PRIMARY KEY (match_id, map_index, computed_at)
);
"""


def init_db(path: str) -> None:
    """Create the SQLite file at `path` and run all CREATE statements.

    Idempotent: safe to run against an existing database.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def list_tables(path: str) -> list[str]:
    """Return the user table names present in the database at `path`."""
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "init":
        print("usage: python -m ingestion.schema init <db_path>", file=sys.stderr)
        return 2
    path = argv[1]
    init_db(path)
    tables = list_tables(path)
    print(f"Initialized {path} with {len(tables)} tables:")
    for t in tables:
        print(f"  - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
