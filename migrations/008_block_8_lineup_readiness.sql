PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS player_lineup_readiness (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  competition_id INTEGER NOT NULL,
  starter_probability REAL,
  appearance_probability REAL,
  expected_minutes REAL,
  bench_entry_probability REAL,
  rotation_risk REAL,
  availability_probability REAL,
  suspension_risk REAL,
  lineup_status TEXT,
  confidence REAL,
  data_coverage_pct REAL,
  value_type TEXT NOT NULL DEFAULT 'estimated' CHECK(value_type IN ('observed','calculated','estimated','manual')),
  methodology_version TEXT NOT NULL DEFAULT 'block8-v1',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id,season_id,club_id,competition_id,methodology_version),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
);

CREATE INDEX IF NOT EXISTS idx_lineup_readiness_season ON player_lineup_readiness(season_id,club_id);
CREATE INDEX IF NOT EXISTS idx_lineup_readiness_player ON player_lineup_readiness(player_id,season_id);
