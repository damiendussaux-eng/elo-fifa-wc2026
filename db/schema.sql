-- Schéma SQLite du bracket WC2026. Idempotent (CREATE TABLE IF NOT EXISTS).
-- Base reconstruite à chaque lancement à partir du dataset + ESPN.

CREATE TABLE IF NOT EXISTS teams (
    team_id    INTEGER PRIMARY KEY,           -- auto-incrément (rowid)
    name       TEXT NOT NULL UNIQUE,
    code_iso2  TEXT,
    flag_emoji TEXT,
    is_host    INTEGER NOT NULL DEFAULT 0     -- booléen (0/1)
);

-- Ratings Elo historisés : une ligne par (équipe, date, source).
CREATE TABLE IF NOT EXISTS elo_ratings (
    team_id  INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    rating   REAL NOT NULL,
    as_of    TEXT NOT NULL,                   -- date ISO 'YYYY-MM-DD'
    source   TEXT NOT NULL,
    PRIMARY KEY (team_id, as_of, source)
);
CREATE INDEX IF NOT EXISTS idx_elo_ratings_asof ON elo_ratings (as_of);

-- Grille du tableau : emplacements R32 (round 0) ; team_id NULL = à déterminer.
CREATE TABLE IF NOT EXISTS bracket_slots (
    slot_id   INTEGER PRIMARY KEY,
    round_idx INTEGER NOT NULL,
    match_idx INTEGER NOT NULL,
    position  INTEGER NOT NULL,
    team_id   INTEGER REFERENCES teams(team_id) ON DELETE SET NULL,
    label     TEXT,
    UNIQUE (round_idx, match_idx, position)
);

-- Métadonnées de chaque case-match de l'arbre (31 matchs).
CREATE TABLE IF NOT EXISTS matches (
    round_idx     INTEGER NOT NULL,
    match_idx     INTEGER NOT NULL,
    match_date    TEXT,                        -- date ISO
    venue         TEXT,
    fifa_match_no INTEGER,
    PRIMARY KEY (round_idx, match_idx)
);

-- Composition des poules (tirage officiel) : 12 groupes × 4 équipes.
CREATE TABLE IF NOT EXISTS group_teams (
    group_code TEXT NOT NULL,
    team_id    INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    draw_pos   INTEGER,
    PRIMARY KEY (group_code, team_id)
);

-- Matchs de poule (ingérés) + prédiction PRÉ-MATCH figée + Elo pré-match/delta.
CREATE TABLE IF NOT EXISTS group_matches (
    group_code      TEXT NOT NULL,
    home_team_id    INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    away_team_id    INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    home_score      INTEGER NOT NULL,
    away_score      INTEGER NOT NULL,
    played_at       TEXT,                       -- date ISO
    pred_home_goals INTEGER,
    pred_away_goals INTEGER,
    p_home          REAL,
    p_draw          REAL,
    p_away          REAL,
    elo_home_pre    REAL,
    elo_away_pre    REAL,
    elo_home_delta  REAL,
    elo_away_delta  REAL,
    PRIMARY KEY (group_code, home_team_id, away_team_id)
);

-- Résultats connus -> avancement dans l'arbre.
CREATE TABLE IF NOT EXISTS results (
    round_idx       INTEGER NOT NULL,
    match_idx       INTEGER NOT NULL,
    winner_team_id  INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    played_at       TEXT,
    PRIMARY KEY (round_idx, match_idx)
);
