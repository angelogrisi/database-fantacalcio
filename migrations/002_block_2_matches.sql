PRAGMA foreign_keys = ON;

ALTER TABLE matches ADD COLUMN utc_date TEXT;
ALTER TABLE matches ADD COLUMN venue TEXT;
ALTER TABLE matches ADD COLUMN referee_name TEXT;
ALTER TABLE matches ADD COLUMN winner TEXT;
ALTER TABLE matches ADD COLUMN duration TEXT;
ALTER TABLE matches ADD COLUMN last_updated TEXT;

CREATE TABLE IF NOT EXISTS match_scores (
  match_id TEXT PRIMARY KEY,
  halftime_home INTEGER,
  halftime_away INTEGER,
  fulltime_home INTEGER,
  fulltime_away INTEGER,
  extratime_home INTEGER,
  extratime_away INTEGER,
  penalties_home INTEGER,
  penalties_away INTEGER,
  FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS match_referees (
  id INTEGER PRIMARY KEY,
  match_id TEXT NOT NULL,
  referee_name TEXT NOT NULL,
  referee_type TEXT,
  nationality TEXT,
  external_id TEXT,
  UNIQUE(match_id, referee_name, referee_type),
  FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE TABLE IF NOT EXISTS match_lineups (
  id INTEGER PRIMARY KEY,
  match_id TEXT NOT NULL,
  club_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  position TEXT,
  shirt_number INTEGER,
  is_starter INTEGER NOT NULL DEFAULT 0,
  captain INTEGER NOT NULL DEFAULT 0,
  formation TEXT,
  UNIQUE(match_id, club_id, player_id),
  FOREIGN KEY(match_id) REFERENCES matches(match_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS match_events (
  event_id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  club_id TEXT,
  player_id TEXT,
  related_player_id TEXT,
  minute INTEGER,
  extra_minute INTEGER,
  event_type TEXT NOT NULL,
  detail TEXT,
  comments TEXT,
  is_penalty INTEGER DEFAULT 0,
  is_own_goal INTEGER DEFAULT 0,
  external_ids_json TEXT,
  FOREIGN KEY(match_id) REFERENCES matches(match_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(related_player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS substitutions (
  substitution_id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  club_id TEXT NOT NULL,
  player_out_id TEXT,
  player_in_id TEXT,
  minute INTEGER,
  extra_minute INTEGER,
  FOREIGN KEY(match_id) REFERENCES matches(match_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(player_out_id) REFERENCES players(player_id),
  FOREIGN KEY(player_in_id) REFERENCES players(player_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_season_day ON matches(season_id, matchday);
CREATE INDEX IF NOT EXISTS idx_match_events_match_minute ON match_events(match_id, minute, extra_minute);
CREATE INDEX IF NOT EXISTS idx_match_lineups_match ON match_lineups(match_id, club_id);
