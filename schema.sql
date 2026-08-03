PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  source_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  base_url TEXT,
  license_notes TEXT,
  access_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seasons (
  season_id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  start_date TEXT,
  end_date TEXT,
  complete INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competitions (
  competition_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT,
  level INTEGER,
  external_ids_json TEXT,
  UNIQUE(name, country)
);

CREATE TABLE IF NOT EXISTS clubs (
  club_id TEXT PRIMARY KEY,
  official_name TEXT NOT NULL,
  short_name TEXT,
  country TEXT,
  founded_year INTEGER,
  stadium_name TEXT,
  crest_url TEXT,
  external_ids_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS players (
  player_id TEXT PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  full_name TEXT NOT NULL,
  known_as TEXT,
  birth_date TEXT,
  nationality TEXT,
  second_nationality TEXT,
  height_cm INTEGER,
  weight_kg REAL,
  preferred_foot TEXT,
  weak_foot INTEGER CHECK(weak_foot BETWEEN 1 AND 5),
  primary_position TEXT,
  secondary_positions_json TEXT,
  photo_url TEXT,
  external_ids_json TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS player_seasons (
  player_season_id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  competition_id INTEGER NOT NULL,
  shirt_number INTEGER,
  contract_end_date TEXT,
  agent_name TEXT,
  market_value_eur REAL,
  estimated_salary_eur REAL,
  UNIQUE(player_id, season_id, club_id, competition_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
);

CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY,
  season_id INTEGER NOT NULL,
  competition_id INTEGER NOT NULL,
  match_date TEXT NOT NULL,
  stage TEXT,
  matchday INTEGER,
  home_club_id TEXT,
  away_club_id TEXT,
  home_score INTEGER,
  away_score INTEGER,
  status TEXT,
  external_ids_json TEXT,
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(competition_id) REFERENCES competitions(competition_id),
  FOREIGN KEY(home_club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(away_club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS player_match_stats (
  id INTEGER PRIMARY KEY,
  match_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  club_id TEXT NOT NULL,
  started INTEGER NOT NULL DEFAULT 0,
  minutes INTEGER NOT NULL DEFAULT 0,
  rating REAL,
  goals INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  xg REAL,
  xa REAL,
  shots INTEGER,
  shots_on_target INTEGER,
  passes_attempted INTEGER,
  passes_completed INTEGER,
  key_passes INTEGER,
  crosses_attempted INTEGER,
  crosses_completed INTEGER,
  dribbles_attempted INTEGER,
  dribbles_completed INTEGER,
  tackles INTEGER,
  interceptions INTEGER,
  clearances INTEGER,
  recoveries INTEGER,
  duels_won INTEGER,
  aerial_duels_won INTEGER,
  fouls_committed INTEGER,
  fouls_suffered INTEGER,
  yellow_cards INTEGER DEFAULT 0,
  red_cards INTEGER DEFAULT 0,
  saves INTEGER,
  penalties_saved INTEGER,
  goals_conceded INTEGER,
  clean_sheet INTEGER,
  UNIQUE(match_id, player_id),
  FOREIGN KEY(match_id) REFERENCES matches(match_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS player_season_stats (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  competition_id INTEGER NOT NULL,
  appearances INTEGER DEFAULT 0,
  starts INTEGER DEFAULT 0,
  minutes INTEGER DEFAULT 0,
  goals INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  penalty_goals INTEGER DEFAULT 0,
  penalties_missed INTEGER DEFAULT 0,
  own_goals INTEGER DEFAULT 0,
  xg REAL,
  xa REAL,
  shots INTEGER,
  shots_on_target INTEGER,
  pass_accuracy REAL,
  key_passes INTEGER,
  dribbles_completed INTEGER,
  tackles INTEGER,
  interceptions INTEGER,
  clearances INTEGER,
  recoveries INTEGER,
  duels_won INTEGER,
  aerial_duels_won INTEGER,
  fouls_committed INTEGER,
  fouls_suffered INTEGER,
  yellow_cards INTEGER,
  red_cards INTEGER,
  clean_sheets INTEGER,
  saves INTEGER,
  penalties_saved INTEGER,
  goals_conceded INTEGER,
  goals_per90 REAL,
  assists_per90 REAL,
  xg_per90 REAL,
  xa_per90 REAL,
  progressive_passes INTEGER,
  progressive_carries INTEGER,
  expected_threat REAL,
  UNIQUE(player_id, season_id, club_id, competition_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
);

CREATE TABLE IF NOT EXISTS injuries (
  injury_id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  injury_type TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  matches_missed INTEGER,
  recurrence INTEGER DEFAULT 0,
  risk_index INTEGER,
  FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS transfers (
  transfer_id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  transfer_date TEXT,
  from_club_id TEXT,
  to_club_id TEXT,
  fee_eur REAL,
  is_loan INTEGER DEFAULT 0,
  is_free INTEGER DEFAULT 0,
  FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS derived_ratings (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  overall INTEGER,
  potential INTEGER,
  pace INTEGER,
  shooting INTEGER,
  passing INTEGER,
  dribbling INTEGER,
  defending INTEGER,
  physical INTEGER,
  form_index INTEGER,
  reliability INTEGER,
  tactical_intelligence INTEGER,
  big_match INTEGER,
  creativity INTEGER,
  methodology_version TEXT NOT NULL,
  confidence REAL,
  UNIQUE(player_id, season_id, methodology_version),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS provenance (
  provenance_id INTEGER PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  field_name TEXT NOT NULL,
  source_id INTEGER NOT NULL,
  source_url TEXT,
  acquired_at TEXT NOT NULL,
  value_type TEXT NOT NULL CHECK(value_type IN ('observed','calculated','estimated','manual')),
  confidence REAL,
  transformation_rule TEXT,
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE TABLE IF NOT EXISTS quality_issues (
  issue_id INTEGER PRIMARY KEY,
  detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  severity TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_key TEXT,
  rule_code TEXT NOT NULL,
  description TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_player_name ON players(full_name);
CREATE INDEX IF NOT EXISTS idx_player_season_stats ON player_season_stats(player_id, season_id);
CREATE INDEX IF NOT EXISTS idx_match_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_provenance_entity ON provenance(entity_type, entity_key, field_name);
