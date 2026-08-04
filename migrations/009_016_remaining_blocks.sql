PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schedule_difficulty (
  id INTEGER PRIMARY KEY, season_id INTEGER NOT NULL, club_id TEXT NOT NULL,
  horizon_matches INTEGER NOT NULL DEFAULT 5, attack_difficulty REAL,
  defence_difficulty REAL, overall_difficulty REAL, home_away_balance REAL,
  methodology_version TEXT NOT NULL DEFAULT 'block9-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(season_id,club_id,horizon_matches,methodology_version)
);
CREATE TABLE IF NOT EXISTS fantasy_recommendations (
  id INTEGER PRIMARY KEY, player_id TEXT NOT NULL, season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL, recommendation_score REAL, predicted_rating REAL,
  predicted_fantasy_score REAL, goal_probability REAL, assist_probability REAL,
  clean_sheet_probability REAL, card_probability REAL, no_vote_risk REAL,
  recommendation TEXT, explanation TEXT, confidence REAL,
  methodology_version TEXT NOT NULL DEFAULT 'block10-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id,methodology_version)
);
CREATE TABLE IF NOT EXISTS auction_values (
  id INTEGER PRIMARY KEY, player_id TEXT NOT NULL, season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL, budget_500_value REAL, budget_1000_value REAL,
  value_tier TEXT, undervaluation_index REAL, overvaluation_risk REAL,
  replacement_value REAL, confidence REAL,
  methodology_version TEXT NOT NULL DEFAULT 'block11-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id,methodology_version)
);
CREATE TABLE IF NOT EXISTS season_simulations (
  id INTEGER PRIMARY KEY, player_id TEXT NOT NULL, season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL, simulations INTEGER NOT NULL DEFAULT 1000,
  expected_appearances REAL, expected_goals REAL, expected_assists REAL,
  expected_fantasy_points REAL, floor_fantasy_points REAL,
  ceiling_fantasy_points REAL, breakout_probability REAL, flop_probability REAL,
  methodology_version TEXT NOT NULL DEFAULT 'block12-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id,methodology_version)
);
CREATE TABLE IF NOT EXISTS dashboard_player_snapshots (
  id INTEGER PRIMARY KEY, player_id TEXT NOT NULL, season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL, form_index REAL, fantasy_average REAL, goals REAL,
  assists REAL, xg REAL, xa REAL, availability_pct REAL,
  starter_probability REAL, auction_value REAL, recommendation_score REAL,
  snapshot_json TEXT, generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id)
);
CREATE TABLE IF NOT EXISTS api_export_registry (
  resource_name TEXT PRIMARY KEY, endpoint_path TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0, schema_version TEXT NOT NULL,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pipeline_health (
  id INTEGER PRIMARY KEY, block_name TEXT NOT NULL, status TEXT NOT NULL,
  row_count INTEGER DEFAULT 0, coverage_pct REAL, warning_count INTEGER DEFAULT 0,
  details_json TEXT, checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(block_name,checked_at)
);
CREATE TABLE IF NOT EXISTS ai_player_predictions (
  id INTEGER PRIMARY KEY, player_id TEXT NOT NULL, season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL, predicted_rating REAL, predicted_fantasy_score REAL,
  rating_low REAL, rating_high REAL, goal_probability REAL,
  assist_probability REAL, yellow_probability REAL, red_probability REAL,
  clean_sheet_probability REAL, explosion_index REAL, flop_index REAL,
  confidence REAL, explanation TEXT,
  methodology_version TEXT NOT NULL DEFAULT 'block16-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id,methodology_version)
);
CREATE INDEX IF NOT EXISTS idx_recommendations_score ON fantasy_recommendations(season_id,recommendation_score DESC);
CREATE INDEX IF NOT EXISTS idx_auction_value ON auction_values(season_id,budget_500_value DESC);
CREATE INDEX IF NOT EXISTS idx_ai_predictions ON ai_player_predictions(season_id,predicted_fantasy_score DESC);
