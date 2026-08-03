PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fantasy_rulesets (
  ruleset_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  goal_bonus REAL NOT NULL DEFAULT 3,
  assist_bonus REAL NOT NULL DEFAULT 1,
  penalty_scored_bonus REAL NOT NULL DEFAULT 3,
  penalty_missed_malus REAL NOT NULL DEFAULT -3,
  own_goal_malus REAL NOT NULL DEFAULT -2,
  yellow_card_malus REAL NOT NULL DEFAULT -0.5,
  red_card_malus REAL NOT NULL DEFAULT -1,
  penalty_saved_bonus REAL NOT NULL DEFAULT 3,
  goal_conceded_gk_malus REAL NOT NULL DEFAULT -1,
  clean_sheet_gk_bonus REAL NOT NULL DEFAULT 0,
  methodology_version TEXT NOT NULL DEFAULT 'v1'
);

CREATE TABLE IF NOT EXISTS fantasy_player_match (
  id INTEGER PRIMARY KEY,
  ruleset_id INTEGER NOT NULL,
  match_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  club_id TEXT NOT NULL,
  fantasy_role TEXT,
  official_rating REAL,
  calculated_rating REAL,
  rating_source TEXT,
  goals INTEGER NOT NULL DEFAULT 0,
  assists INTEGER NOT NULL DEFAULT 0,
  penalty_goals INTEGER NOT NULL DEFAULT 0,
  penalties_missed INTEGER NOT NULL DEFAULT 0,
  own_goals INTEGER NOT NULL DEFAULT 0,
  yellow_cards INTEGER NOT NULL DEFAULT 0,
  red_cards INTEGER NOT NULL DEFAULT 0,
  penalties_saved INTEGER NOT NULL DEFAULT 0,
  goals_conceded INTEGER NOT NULL DEFAULT 0,
  clean_sheet INTEGER NOT NULL DEFAULT 0,
  bonus_total REAL NOT NULL DEFAULT 0,
  malus_total REAL NOT NULL DEFAULT 0,
  fantasy_score REAL,
  is_estimated INTEGER NOT NULL DEFAULT 1,
  confidence REAL,
  UNIQUE(ruleset_id, match_id, player_id),
  FOREIGN KEY(ruleset_id) REFERENCES fantasy_rulesets(ruleset_id),
  FOREIGN KEY(match_id) REFERENCES matches(match_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id)
);

CREATE TABLE IF NOT EXISTS fantasy_player_season (
  id INTEGER PRIMARY KEY,
  ruleset_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  season_id INTEGER NOT NULL,
  club_id TEXT NOT NULL,
  competition_id INTEGER NOT NULL,
  fantasy_role TEXT,
  appearances_with_rating INTEGER NOT NULL DEFAULT 0,
  average_rating REAL,
  fantasy_average REAL,
  total_bonus REAL NOT NULL DEFAULT 0,
  total_malus REAL NOT NULL DEFAULT 0,
  total_fantasy_points REAL NOT NULL DEFAULT 0,
  goals INTEGER NOT NULL DEFAULT 0,
  assists INTEGER NOT NULL DEFAULT 0,
  penalty_goals INTEGER NOT NULL DEFAULT 0,
  penalties_missed INTEGER NOT NULL DEFAULT 0,
  own_goals INTEGER NOT NULL DEFAULT 0,
  yellow_cards INTEGER NOT NULL DEFAULT 0,
  red_cards INTEGER NOT NULL DEFAULT 0,
  penalties_saved INTEGER NOT NULL DEFAULT 0,
  goals_conceded INTEGER NOT NULL DEFAULT 0,
  clean_sheets INTEGER NOT NULL DEFAULT 0,
  reliability_index REAL,
  availability_index REAL,
  bonus_index REAL,
  malus_risk_index REAL,
  auction_value_index REAL,
  data_quality REAL,
  UNIQUE(ruleset_id, player_id, season_id, club_id, competition_id),
  FOREIGN KEY(ruleset_id) REFERENCES fantasy_rulesets(ruleset_id),
  FOREIGN KEY(player_id) REFERENCES players(player_id),
  FOREIGN KEY(season_id) REFERENCES seasons(season_id),
  FOREIGN KEY(club_id) REFERENCES clubs(club_id),
  FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
);

CREATE INDEX IF NOT EXISTS idx_fantasy_match_player ON fantasy_player_match(player_id, match_id);
CREATE INDEX IF NOT EXISTS idx_fantasy_season_player ON fantasy_player_season(player_id, season_id);

INSERT OR IGNORE INTO fantasy_rulesets(
  ruleset_id,name,description,goal_bonus,assist_bonus,penalty_scored_bonus,
  penalty_missed_malus,own_goal_malus,yellow_card_malus,red_card_malus,
  penalty_saved_bonus,goal_conceded_gk_malus,clean_sheet_gk_bonus,methodology_version
) VALUES (
  1,'Standard Italia','Regolamento generico e modificabile; i voti ufficiali non vengono inventati.',
  3,1,3,-3,-2,-0.5,-1,3,-1,0,'v1'
);
