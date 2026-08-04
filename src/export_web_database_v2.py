#!/usr/bin/env python3
import json, os, sqlite3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
db_path = Path(os.getenv('DATABASE_PATH', root / 'data' / 'database-fantacalcio.sqlite'))
out_path = Path(os.getenv('WEB_DATA_PATH', root / 'pages' / 'data' / 'database.json'))

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

def has_table(name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def cols(name):
    return {r[1] for r in con.execute(f'PRAGMA table_info({name})')} if has_table(name) else set()

def field(alias, table, name, fallback='NULL'):
    return f'{alias}.{name}' if name in cols(table) else fallback

joins = []
joins.append('LEFT JOIN player_seasons ps ON ps.player_id=p.player_id')
joins.append('LEFT JOIN seasons s ON s.season_id=ps.season_id')
joins.append('LEFT JOIN clubs c ON c.club_id=ps.club_id')

mapping = [
 ('player_season_statistics_extended','st','st.player_id=p.player_id AND st.season_id=ps.season_id AND st.club_id=ps.club_id'),
 ('fantasy_player_season','fm','fm.player_id=p.player_id AND fm.season_id=ps.season_id AND fm.club_id=ps.club_id'),
 ('player_advanced_season_metrics','am','am.player_id=p.player_id AND am.season_id=ps.season_id AND am.club_id=ps.club_id'),
 ('proprietary_player_indexes','pi','pi.player_id=p.player_id AND pi.season_id=ps.season_id AND pi.club_id=ps.club_id'),
 ('player_availability','av','av.player_id=p.player_id AND av.season_id=ps.season_id AND av.club_id=ps.club_id'),
 ('player_lineup_readiness','lr','lr.player_id=p.player_id AND lr.season_id=ps.season_id AND lr.club_id=ps.club_id'),
 ('fantasy_recommendations','fr','fr.player_id=p.player_id AND fr.season_id=ps.season_id AND fr.club_id=ps.club_id'),
 ('auction_values','au','au.player_id=p.player_id AND au.season_id=ps.season_id AND au.club_id=ps.club_id'),
 ('season_simulations','ss','ss.player_id=p.player_id AND ss.season_id=ps.season_id AND ss.club_id=ps.club_id'),
 ('ai_player_predictions','ai','ai.player_id=p.player_id AND ai.season_id=ps.season_id AND ai.club_id=ps.club_id')
]
for table, alias, on in mapping:
    if has_table(table): joins.append(f'LEFT JOIN {table} {alias} ON {on}')

fields = [
 field('p','players','player_id')+' player_id',
 field('p','players','full_name',"''")+' name',
 field('p','players','nationality')+' nationality',
 field('p','players','primary_position',field('p','players','position'))+' position',
 field('s','seasons','label')+' season',
 field('c','clubs','official_name')+' club',
 field('fm','fantasy_player_season','fantasy_role')+' fantasy_role',
 field('st','player_season_statistics_extended','appearances','0')+' appearances',
 field('st','player_season_statistics_extended','starts','0')+' starts',
 field('st','player_season_statistics_extended','minutes','0')+' minutes',
 field('st','player_season_statistics_extended','avg_rating')+' average_rating',
 field('st','player_season_statistics_extended','goals','0')+' goals',
 field('st','player_season_statistics_extended','assists','0')+' assists',
 field('st','player_season_statistics_extended','shots_total')+' shots',
 field('st','player_season_statistics_extended','shots_on_target')+' shots_on_target',
 field('st','player_season_statistics_extended','passes_total')+' passes',
 field('st','player_season_statistics_extended','passes_key')+' key_passes',
 field('st','player_season_statistics_extended','pass_accuracy_pct')+' pass_accuracy',
 field('st','player_season_statistics_extended','tackles_total')+' tackles',
 field('st','player_season_statistics_extended','interceptions')+' interceptions',
 field('st','player_season_statistics_extended','yellow_cards')+' yellow_cards',
 field('st','player_season_statistics_extended','red_cards')+' red_cards',
 field('fm','fantasy_player_season','fantasy_average')+' fantasy_average',
 field('fm','fantasy_player_season','total_fantasy_points')+' fantasy_points',
 field('am','player_advanced_season_metrics','xg')+' xg',
 field('am','player_advanced_season_metrics','xa')+' xa',
 field('am','player_advanced_season_metrics','xg_per90')+' xg_per90',
 field('am','player_advanced_season_metrics','xa_per90')+' xa_per90',
 field('am','player_advanced_season_metrics','progressive_passes')+' progressive_passes',
 field('am','player_advanced_season_metrics','progressive_carries')+' progressive_carries',
 field('pi','proprietary_player_indexes','form_index')+' form_index',
 field('pi','proprietary_player_indexes','reliability_index')+' reliability_index',
 field('pi','proprietary_player_indexes','continuity_index')+' continuity_index',
 field('pi','proprietary_player_indexes','auction_value_index')+' auction_value',
 field('pi','proprietary_player_indexes','bonus_index')+' bonus_index',
 field('pi','proprietary_player_indexes','malus_risk')+' malus_risk',
 field('av','player_availability','availability_pct')+' availability_pct',
 field('av','player_availability','injury_risk_index')+' injury_risk',
 field('lr','player_lineup_readiness','starter_probability')+' starter_probability',
 field('lr','player_lineup_readiness','appearance_probability')+' appearance_probability',
 field('lr','player_lineup_readiness','expected_minutes')+' expected_minutes',
 field('lr','player_lineup_readiness','lineup_status')+' lineup_status',
 field('fr','fantasy_recommendations','recommendation_score')+' recommendation_score',
 field('fr','fantasy_recommendations','predicted_rating')+' predicted_rating',
 field('fr','fantasy_recommendations','predicted_fantasy_score')+' predicted_fantasy_score',
 field('fr','fantasy_recommendations','recommendation')+' recommendation',
 field('fr','fantasy_recommendations','explanation')+' recommendation_explanation',
 field('au','auction_values','budget_500_value')+' budget_500_value',
 field('au','auction_values','budget_1000_value')+' budget_1000_value',
 field('au','auction_values','value_tier')+' value_tier',
 field('ss','season_simulations','expected_goals')+' expected_goals',
 field('ss','season_simulations','expected_assists')+' expected_assists',
 field('ss','season_simulations','expected_fantasy_points')+' expected_fantasy_points',
 field('ss','season_simulations','breakout_probability')+' breakout_probability',
 field('ss','season_simulations','flop_probability')+' flop_probability',
 field('ai','ai_player_predictions','predicted_rating')+' ai_predicted_rating',
 field('ai','ai_player_predictions','goal_probability')+' goal_probability',
 field('ai','ai_player_predictions','assist_probability')+' assist_probability',
 field('ai','ai_player_predictions','yellow_probability')+' yellow_probability',
 field('ai','ai_player_predictions','clean_sheet_probability')+' clean_sheet_probability',
 field('ai','ai_player_predictions','explosion_index')+' explosion_index',
 field('ai','ai_player_predictions','flop_index')+' ai_flop_index'
]

sql = 'SELECT '+','.join(fields)+' FROM players p '+' '.join(joins)
rows = [dict(r) for r in con.execute(sql)]
unique = {(r.get('player_id'),r.get('season'),r.get('club')):r for r in rows}
rows = list(unique.values())
summary = {
 'players': con.execute('SELECT COUNT(*) FROM players').fetchone()[0],
 'clubs': con.execute('SELECT COUNT(*) FROM clubs').fetchone()[0] if has_table('clubs') else 0,
 'matches': con.execute('SELECT COUNT(*) FROM matches').fetchone()[0] if has_table('matches') else 0,
 'records': len(rows),
 'stats_records': con.execute('SELECT COUNT(*) FROM player_season_statistics_extended').fetchone()[0] if has_table('player_season_statistics_extended') else 0,
 'fantasy_records': con.execute('SELECT COUNT(*) FROM fantasy_player_season').fetchone()[0] if has_table('fantasy_player_season') else 0,
 'prediction_records': con.execute('SELECT COUNT(*) FROM ai_player_predictions').fetchone()[0] if has_table('ai_player_predictions') else 0
}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({'summary':summary,'players':rows},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(json.dumps(summary,indent=2,ensure_ascii=False))
