#!/usr/bin/env python3
import argparse, json, os, sqlite3
from pathlib import Path


def apply_migration(conn: sqlite3.Connection) -> None:
    sql = Path('migrations/004_block_4_fantasy.sql').read_text(encoding='utf-8')
    conn.executescript(sql)


def fantasy_role(position: str | None) -> str | None:
    if not position:
        return None
    p = position.lower()
    if 'goal' in p or p in {'gk','portiere'}: return 'P'
    if 'def' in p or p in {'cb','lb','rb','wb'}: return 'D'
    if 'mid' in p or p in {'cm','dm','am','lm','rm','centrocampista'}: return 'C'
    if 'att' in p or 'forward' in p or p in {'st','cf','lw','rw'}: return 'A'
    return None


def build(conn: sqlite3.Connection, ruleset_id: int = 1) -> dict:
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT * FROM fantasy_rulesets WHERE ruleset_id=?', (ruleset_id,)).fetchone()
    if not r:
        raise RuntimeError('Ruleset non trovato')

    rows = conn.execute('''
      SELECT pms.*, p.primary_position, m.season_id, m.competition_id
      FROM player_match_stats pms
      JOIN players p ON p.player_id=pms.player_id
      JOIN matches m ON m.match_id=pms.match_id
    ''').fetchall()

    inserted = 0
    for x in rows:
        goals = x['goals'] or 0
        assists = x['assists'] or 0
        yellow = x['yellow_cards'] or 0
        red = x['red_cards'] or 0
        saved = x['penalties_saved'] or 0
        conceded = x['goals_conceded'] or 0
        clean = x['clean_sheet'] or 0
        penalty_goals = 0
        missed = 0
        own_goals = 0
        bonus = goals*r['goal_bonus'] + assists*r['assist_bonus'] + saved*r['penalty_saved_bonus']
        malus = yellow*r['yellow_card_malus'] + red*r['red_card_malus'] + conceded*r['goal_conceded_gk_malus']
        rating = x['rating']
        score = (rating + bonus + malus) if rating is not None else None
        confidence = 90 if rating is not None else 55
        conn.execute('''
          INSERT INTO fantasy_player_match(
            ruleset_id,match_id,player_id,club_id,fantasy_role,official_rating,calculated_rating,
            rating_source,goals,assists,penalty_goals,penalties_missed,own_goals,yellow_cards,
            red_cards,penalties_saved,goals_conceded,clean_sheet,bonus_total,malus_total,
            fantasy_score,is_estimated,confidence
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(ruleset_id,match_id,player_id) DO UPDATE SET
            fantasy_role=excluded.fantasy_role, official_rating=excluded.official_rating,
            calculated_rating=excluded.calculated_rating, rating_source=excluded.rating_source,
            goals=excluded.goals, assists=excluded.assists, yellow_cards=excluded.yellow_cards,
            red_cards=excluded.red_cards, penalties_saved=excluded.penalties_saved,
            goals_conceded=excluded.goals_conceded, clean_sheet=excluded.clean_sheet,
            bonus_total=excluded.bonus_total, malus_total=excluded.malus_total,
            fantasy_score=excluded.fantasy_score, is_estimated=excluded.is_estimated,
            confidence=excluded.confidence
        ''', (ruleset_id,x['match_id'],x['player_id'],x['club_id'],fantasy_role(x['primary_position']),
              rating,None,'provider_rating' if rating is not None else 'missing',goals,assists,
              penalty_goals,missed,own_goals,yellow,red,saved,conceded,clean,bonus,malus,
              score,0 if rating is not None else 1,confidence))
        inserted += 1

    conn.execute('DELETE FROM fantasy_player_season WHERE ruleset_id=?', (ruleset_id,))
    conn.execute('''
      INSERT INTO fantasy_player_season(
        ruleset_id,player_id,season_id,club_id,competition_id,fantasy_role,
        appearances_with_rating,average_rating,fantasy_average,total_bonus,total_malus,
        total_fantasy_points,goals,assists,penalty_goals,penalties_missed,own_goals,
        yellow_cards,red_cards,penalties_saved,goals_conceded,clean_sheets,
        reliability_index,availability_index,bonus_index,malus_risk_index,
        auction_value_index,data_quality
      )
      SELECT f.ruleset_id,f.player_id,m.season_id,f.club_id,m.competition_id,
        MAX(f.fantasy_role),COUNT(f.official_rating),AVG(f.official_rating),AVG(f.fantasy_score),
        SUM(f.bonus_total),SUM(f.malus_total),SUM(COALESCE(f.fantasy_score,0)),
        SUM(f.goals),SUM(f.assists),SUM(f.penalty_goals),SUM(f.penalties_missed),SUM(f.own_goals),
        SUM(f.yellow_cards),SUM(f.red_cards),SUM(f.penalties_saved),SUM(f.goals_conceded),SUM(f.clean_sheet),
        MIN(100,COUNT(*)*100.0/38.0),MIN(100,COUNT(*)*100.0/38.0),
        MIN(100,SUM(f.bonus_total)*4),MIN(100,ABS(SUM(f.malus_total))*8),
        MIN(100,MAX(0,COALESCE(AVG(f.fantasy_score),0)*10 + COUNT(*)*0.6)),AVG(f.confidence)
      FROM fantasy_player_match f
      JOIN matches m ON m.match_id=f.match_id
      WHERE f.ruleset_id=?
      GROUP BY f.ruleset_id,f.player_id,m.season_id,f.club_id,m.competition_id
    ''', (ruleset_id,))
    conn.commit()
    return {
      'match_rows_processed': inserted,
      'fantasy_match_rows': conn.execute('SELECT COUNT(*) FROM fantasy_player_match').fetchone()[0],
      'fantasy_season_rows': conn.execute('SELECT COUNT(*) FROM fantasy_player_season').fetchone()[0],
      'note': 'I voti mancanti restano NULL; non vengono inventati.'
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db', default=os.getenv('DATABASE_PATH','data/database-fantacalcio.sqlite'))
    ap.add_argument('--report', default='reports/block_4_coverage_report.json')
    args=ap.parse_args()
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    Path(args.report).parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(args.db)
    conn.execute('PRAGMA foreign_keys=ON')
    apply_migration(conn)
    report=build(conn)
    conn.close()
    Path(args.report).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
