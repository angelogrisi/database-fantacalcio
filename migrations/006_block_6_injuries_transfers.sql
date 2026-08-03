PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS player_injuries (
  injury_id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER,
  club_id TEXT,
  injury_type TEXT NOT NULL,
  injury_detail TEXT,
  start_date TEXT,
  end_date TEXT,
  days_absent INTEGER,
  matches_missed INTEGER,
  recurrence INTEGER NOT NULL DEFAULT 0,
  status TEXT,
  source_name TEXT,
  source_url TEXT,
  confidence REAL,
  observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id, injury_type, start_date, club_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS player_transfers (
  transfer_id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  transfer_date TEXT,
  season_id INTEGER,
  from_club_id TEXT,
  to_club_id TEXT,
  from_club_name TEXT,
  to_club_name TEXT,
  transfer_type TEXT,
  fee_eur REAL,
  currency TEXT DEFAULT 'EUR',
  is_loan INTEGER NOT NULL DEFAULT 0,
  is_free INTEGER NOT NULL DEFAULT 0,
  loan_end_date TEXT,
  source_name TEXT,
  source_url TEXT,
  confidence REAL,
  observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_id, transfer_date, from_club_name, to_club_name, transfer_type),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(from_club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(to_club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS player_availability (
  id INTEGER PRIMARY KEY,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  days_injured INTEGER DEFAULT 0,
  matches_missed_injury INTEGER DEFAULT 0,
  injury_count INTEGER DEFAULT 0,
  recurrence_count INTEGER DEFAULT 0,
  availability_pct REAL,
  injury_risk_index INTEGER,
  transfer_count INTEGER DEFAULT 0,
  methodology_version TEXT NOT NULL DEFAULT 'block6-v1',
  data_coverage_pct REAL,
  UNIQUE(player_id, season_id, club_id, methodology_version),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id)
);

CREATE INDEX IF NOT EXISTS idx_injuries_player_date ON player_injuries(player_id, start_date);
CREATE INDEX IF NOT EXISTS idx_transfers_player_date ON player_transfers(player_id, transfer_date);
CREATE INDEX IF NOT EXISTS idx_availability_player_season ON player_availability(player_id, season_id);
