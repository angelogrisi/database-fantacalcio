#!/usr/bin/env python3
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.getenv('DATABASE_PATH',ROOT/'data/database-fantacalcio.sqlite'))
OUT=Path(os.getenv('WEB_DATA_PATH',ROOT/'pages/data/database.json'))
con=sqlite3.connect(DB); con.row_factory=sqlite3.Row

def has(t):return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None
def cols(t):return {r[1] for r in con.execute(f'PRAGMA table_info({t})')} if has(t) else set()
def c(a,t,n,default='NULL'):return f'{a}.{n}' if n in cols(t) else default
def co(*values):return 'COALESCE('+','.join(values)+')'

joins=[
 'LEFT JOIN player_seasons ps ON ps.player_id=p.player_id',
 'LEFT JOIN seasons s ON s.season_id=ps.season_id',
 'LEFT JOIN clubs club ON club.club_id=ps.club_id',
 'LEFT JOIN player_season_stats core ON core.player_id=p.player_id AND core.season_id=ps.season_id AND core.club_id=ps.club_id AND core.competition_id=ps.competition_id'
]

if has('player_season_statistics_extended'):
    joins.append('''LEFT JOIN (
      SELECT * FROM (
        SELECT x.*,ROW_NUMBER() OVER(
          PARTITION BY player_id,season_id,club_id,competition_id
          ORDER BY CASE source_name WHEN 'API-Football' THEN 1 WHEN 'Kaggle-FBref' THEN 2 ELSE 9 END
        ) AS provider_rank
        FROM player_season_statistics_extended x
      ) WHERE provider_rank=1
    ) ext ON ext.player_id=p.player_id AND ext.season_id=ps.season_id AND ext.club_id=ps.club_id AND ext.competition_id=ps.competition_id''')

optional=[
 ('fantasy_player_season','fm','fm.player_id=p.player_id AND fm.season_id=ps.season_id AND fm.club_id=ps.club_id AND fm.competition_id=ps.competition_id AND fm.ruleset_id=1'),
 ('player_advanced_season_metrics','adv','adv.player_id=p.player_id AND adv.season_id=ps.season_id AND adv.club_id=ps.club_id AND adv.competition_id=ps.competition_id'),
 ('proprietary_player_indexes','idx','idx.player_id=p.player_id AND idx.season_id=ps.season_id AND idx.club_id=ps.club_id'),
 ('player_availability','avail','avail.player_id=p.player_id AND avail.season_id=ps.season_id AND avail.club_id=ps.club_id'),
 ('player_lineup_readiness','lineup','lineup.player_id=p.player_id AND lineup.season_id=ps.season_id AND lineup.club_id=ps.club_id'),
 ('fantasy_recommendations','rec','rec.player_id=p.player_id AND rec.season_id=ps.season_id AND rec.club_id=ps.club_id'),
 ('auction_values','auction','auction.player_id=p.player_id AND auction.season_id=ps.season_id AND auction.club_id=ps.club_id'),
 ('season_simulations','sim','sim.player_id=p.player_id AND sim.season_id=ps.season_id AND sim.club_id=ps.club_id'),
 ('ai_player_predictions','ai','ai.player_id=p.player_id AND ai.season_id=ps.season_id AND ai.club_id=ps.club_id')
]
for t,a,on in optional:
    if has(t):joins.append(f'LEFT JOIN {t} {a} ON {on}')

fields=[
 c('p','players','player_id')+' AS player_id',
 c('p','players','full_name',"''")+' AS name',
 c('p','players','nationality')+' AS nationality',
 c('p','players','primary_position')+' AS position',
 c('p','players','photo_url')+' AS photo_url',
 c('s','seasons','label')+' AS season',
 c('club','clubs','official_name')+' AS club',
 c('club','clubs','crest_url')+' AS club_crest',
 c('fm','fantasy_player_season','fantasy_role')+' AS fantasy_role',
 co(c('ext','player_season_statistics_extended','appearances'),c('core','player_season_stats','appearances','0'))+' AS appearances',
 co(c('ext','player_season_statistics_extended','starts'),c('core','player_season_stats','starts','0'))+' AS starts',
 co(c('ext','player_season_statistics_extended','minutes'),c('core','player_season_stats','minutes','0'))+' AS minutes',
 c('ext','player_season_statistics_extended','avg_rating')+' AS average_rating',
 co(c('ext','player_season_statistics_extended','goals'),c('core','player_season_stats','goals','0'))+' AS goals',
 co(c('ext','player_season_statistics_extended','assists'),c('core','player_season_stats','assists','0'))+' AS assists',
 co(c('ext','player_season_statistics_extended','shots_total'),c('core','player_season_stats','shots'))+' AS shots',
 co(c('ext','player_season_statistics_extended','shots_on_target'),c('core','player_season_stats','shots_on_target'))+' AS shots_on_target',
 c('ext','player_season_statistics_extended','passes_total')+' AS passes',
 co(c('ext','player_season_statistics_extended','passes_key'),c('core','player_season_stats','key_passes'))+' AS key_passes',
 co(c('ext','player_season_statistics_extended','pass_accuracy_pct'),c('core','player_season_stats','pass_accuracy'))+' AS pass_accuracy',
 co(c('ext','player_season_statistics_extended','tackles_total'),c('core','player_season_stats','tackles'))+' AS tackles',
 co(c('ext','player_season_statistics_extended','interceptions'),c('core','player_season_stats','interceptions'))+' AS interceptions',
 co(c('ext','player_season_statistics_extended','yellow_cards'),c('core','player_season_stats','yellow_cards','0'))+' AS yellow_cards',
 co(c('ext','player_season_statistics_extended','red_cards'),c('core','player_season_stats','red_cards','0'))+' AS red_cards',
 c('fm','fantasy_player_season','fantasy_average')+' AS fantasy_average',
 c('fm','fantasy_player_season','total_fantasy_points')+' AS fantasy_points',
 co(c('adv','player_advanced_season_metrics','xg'),c('core','player_season_stats','xg'))+' AS xg',
 co(c('adv','player_advanced_season_metrics','xa'),c('core','player_season_stats','xa'))+' AS xa',
 co(c('adv','player_advanced_season_metrics','xg_per90'),c('core','player_season_stats','xg_per90'))+' AS xg_per90',
 co(c('adv','player_advanced_season_metrics','xa_per90'),c('core','player_season_stats','xa_per90'))+' AS xa_per90',
 co(c('adv','player_advanced_season_metrics','progressive_passes'),c('core','player_season_stats','progressive_passes'))+' AS progressive_passes',
 co(c('adv','player_advanced_season_metrics','progressive_carries'),c('core','player_season_stats','progressive_carries'))+' AS progressive_carries',
 c('idx','proprietary_player_indexes','form_index')+' AS form_index',
 c('idx','proprietary_player_indexes','reliability_index')+' AS reliability_index',
 c('idx','proprietary_player_indexes','continuity_index')+' AS continuity_index',
 co(c('idx','proprietary_player_indexes','auction_value_index'),c('fm','fantasy_player_season','auction_value_index'))+' AS auction_value',
 c('idx','proprietary_player_indexes','bonus_index')+' AS bonus_index',
 c('idx','proprietary_player_indexes','malus_risk')+' AS malus_risk',
 c('avail','player_availability','availability_pct')+' AS availability_pct',
 c('avail','player_availability','injury_risk_index')+' AS injury_risk',
 c('lineup','player_lineup_readiness','starter_probability')+' AS starter_probability',
 c('lineup','player_lineup_readiness','appearance_probability')+' AS appearance_probability',
 c('lineup','player_lineup_readiness','expected_minutes')+' AS expected_minutes',
 c('lineup','player_lineup_readiness','lineup_status')+' AS lineup_status',
 c('rec','fantasy_recommendations','recommendation_score')+' AS recommendation_score',
 c('rec','fantasy_recommendations','predicted_rating')+' AS predicted_rating',
 c('rec','fantasy_recommendations','predicted_fantasy_score')+' AS predicted_fantasy_score',
 c('rec','fantasy_recommendations','recommendation')+' AS recommendation',
 c('rec','fantasy_recommendations','explanation')+' AS recommendation_explanation',
 c('auction','auction_values','budget_500_value')+' AS budget_500_value',
 c('auction','auction_values','budget_1000_value')+' AS budget_1000_value',
 c('auction','auction_values','value_tier')+' AS value_tier',
 c('sim','season_simulations','expected_goals')+' AS expected_goals',
 c('sim','season_simulations','expected_assists')+' AS expected_assists',
 c('sim','season_simulations','expected_fantasy_points')+' AS expected_fantasy_points',
 c('sim','season_simulations','breakout_probability')+' AS breakout_probability',
 c('sim','season_simulations','flop_probability')+' AS flop_probability',
 c('ai','ai_player_predictions','predicted_rating')+' AS ai_predicted_rating',
 c('ai','ai_player_predictions','goal_probability')+' AS goal_probability',
 c('ai','ai_player_predictions','assist_probability')+' AS assist_probability',
 c('ai','ai_player_predictions','yellow_probability')+' AS yellow_probability',
 c('ai','ai_player_predictions','clean_sheet_probability')+' AS clean_sheet_probability',
 c('ai','ai_player_predictions','explosion_index')+' AS explosion_index',
 c('ai','ai_player_predictions','flop_index')+' AS ai_flop_index',
 c('ext','player_season_statistics_extended','source_name',"CASE WHEN core.id IS NOT NULL THEN 'season-dataset' END")+' AS data_source',
 c('fm','fantasy_player_season','data_quality')+' AS data_quality'
]

rows=[dict(r) for r in con.execute('SELECT '+','.join(fields)+' FROM players p '+' '.join(joins))]
# Keep one row for each real player-season-club and prefer populated statistics.
def score(r):return sum(r.get(k) not in (None,'') for k in ('appearances','minutes','goals','assists','xg','xa','data_source'))
unique={}
for r in rows:
    key=(r.get('player_id'),r.get('season'),r.get('club'))
    if key not in unique or score(r)>score(unique[key]):unique[key]=r
rows=list(unique.values())
summary={
 'players':con.execute('SELECT COUNT(*) FROM players').fetchone()[0],
 'clubs':con.execute('SELECT COUNT(*) FROM clubs').fetchone()[0] if has('clubs') else 0,
 'matches':con.execute('SELECT COUNT(*) FROM matches').fetchone()[0] if has('matches') else 0,
 'records':len(rows),
 'stats_records':con.execute('SELECT COUNT(*) FROM player_season_stats WHERE appearances IS NOT NULL').fetchone()[0],
 'fantasy_records':con.execute('SELECT COUNT(*) FROM fantasy_player_season').fetchone()[0] if has('fantasy_player_season') else 0,
 'prediction_records':con.execute('SELECT COUNT(*) FROM ai_player_predictions').fetchone()[0] if has('ai_player_predictions') else 0,
 'kaggle_records':con.execute("SELECT COUNT(*) FROM player_season_statistics_extended WHERE source_name='Kaggle-FBref'").fetchone()[0] if has('player_season_statistics_extended') else 0
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'summary':summary,'players':rows},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
con.close();print(json.dumps(summary,indent=2,ensure_ascii=False))
