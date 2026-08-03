PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS proprietary_player_indexes (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  form_index INTEGER,
  reliability_index INTEGER,
  continuity_index INTEGER,
  rotation_risk INTEGER,
  injury_risk INTEGER,
  home_performance_index INTEGER,
  away_performance_index INTEGER,
  big_match_index INTEGER,
  bonus_index INTEGER,
  malus_risk INTEGER,
  auction_value_index INTEGER,
  potential_performance_index INTEGER,
  tactical_intelligence INTEGER,
  adaptability INTEGER,
  creativity INTEGER,
  intensity INTEGER,
  completeness INTEGER,
  confidence REAL,
  coverage_pct REAL,
  methodology_version TEXT NOT NULL,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id, season_id, club_id, methodology_version),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS player_similarity (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  similar_player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  rank INTEGER NOT NULL CHECK(rank BETWEEN 1 AND 20),
  similarity_score REAL NOT NULL,
  feature_coverage_pct REAL,
  methodology_version TEXT NOT NULL,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id, similar_player_id, season_id, methodology_version),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(similar_player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id)
);

CREATE INDEX IF NOT EXISTS idx_prop_indexes_player_season
ON proprietary_player_indexes(player_id, season_id);

CREATE INDEX IF NOT EXISTS idx_similarity_player_season
ON player_similarity(player_id, season_id, rank);
