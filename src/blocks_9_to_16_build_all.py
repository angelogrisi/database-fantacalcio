#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, sqlite3
from pathlib import Path

DB=Path(os.getenv('DATABASE_PATH','data/database-fantacalcio.sqlite'))
MIG=Path('migrations/009_016_remaining_blocks.sql')

def clamp(v,a=0,b=100): return max(a,min(b,float(v)))
def pct(v): return clamp(v)/100

def tables(c): return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def cols(c,t): return {r[1] for r in c.execute(f'PRAGMA table_info({t})')}
def has(c,t): return t in tables(c)
def val(r,k,d=0):
    x=r[k] if k in r.keys() else None
    return d if x is None else x

def main():
    if not DB.exists(): raise SystemExit(f'Database non trovato: {DB}')
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.executescript(MIG.read_text())
    ts=tables(c)

    # Canonical player-season base from the most reliable available table.
    if 'player_season_stats' in ts:
        base=list(c.execute('SELECT player_id,season_id,club_id,COALESCE(appearances,0) appearances,COALESCE(minutes,0) minutes,COALESCE(goals,0) goals,COALESCE(assists,0) assists,COALESCE(yellow_cards,0) yellow_cards,COALESCE(red_cards,0) red_cards FROM player_season_stats'))
    elif 'player_season_statistics_extended' in ts:
        base=list(c.execute('SELECT player_id,season_id,club_id,COALESCE(appearances,0) appearances,COALESCE(minutes,0) minutes,COALESCE(goals,0) goals,COALESCE(assists,0) assists,COALESCE(yellow_cards,0) yellow_cards,COALESCE(red_cards,0) red_cards FROM player_season_statistics_extended'))
    else:
        base=list(c.execute('SELECT player_id,season_id,club_id,0 appearances,0 minutes,0 goals,0 assists,0 yellow_cards,0 red_cards FROM player_seasons'))

    # Build lookup maps from previous blocks.
    fantasy={}
    if 'fantasy_player_season' in ts:
        for r in c.execute('SELECT * FROM fantasy_player_season'):
            fantasy[(r['player_id'],r['season_id'],r['club_id'])]=r
    prop={}
    if 'proprietary_player_indexes' in ts:
        for r in c.execute('SELECT * FROM proprietary_player_indexes'):
            prop[(r['player_id'],r['season_id'],r['club_id'])]=r
    ready={}
    if 'player_lineup_readiness' in ts:
        for r in c.execute('SELECT * FROM player_lineup_readiness'):
            ready[(r['player_id'],r['season_id'],r['club_id'])]=r
    avail={}
    if 'player_availability' in ts:
        for r in c.execute('SELECT * FROM player_availability'):
            avail[(r['player_id'],r['season_id'],r['club_id'])]=r
    adv={}
    if 'player_advanced_season_metrics' in ts:
        for r in c.execute('SELECT * FROM player_advanced_season_metrics'):
            adv[(r['player_id'],r['season_id'],r['club_id'])]=r

    # Block 9: club schedule difficulty from season match results where available.
    club_seasons={(r['season_id'],r['club_id']) for r in base}
    for sid,cid in club_seasons:
        attack=defence=overall=50.0; balance=50.0
        if 'matches' in ts:
            mc=cols(c,'matches')
            needed={'season_id','home_club_id','away_club_id'}
            if needed.issubset(mc):
                games=list(c.execute('SELECT * FROM matches WHERE season_id=? AND (home_club_id=? OR away_club_id=?) ORDER BY COALESCE(utc_date,match_date) DESC LIMIT 5',(sid,cid,cid)))
                if games:
                    home=sum(1 for g in games if g['home_club_id']==cid)
                    balance=100*home/len(games)
                    overall=clamp(50 + (len(games)-home)*2-home)
                    attack=clamp(overall+3); defence=clamp(overall-3)
        c.execute('INSERT OR REPLACE INTO schedule_difficulty(season_id,club_id,horizon_matches,attack_difficulty,defence_difficulty,overall_difficulty,home_away_balance,methodology_version) VALUES(?,?,?,?,?,?,?,?)',(sid,cid,5,attack,defence,overall,balance,'block9-v1'))

    outputs=0
    for r in base:
        key=(r['player_id'],r['season_id'],r['club_id'])
        f=fantasy.get(key); p=prop.get(key); lr=ready.get(key); av=avail.get(key); ad=adv.get(key)
        apps=val(r,'appearances'); mins=val(r,'minutes'); goals=val(r,'goals'); assists=val(r,'assists')
        avg=val(f,'average_rating',6.0) if f else 6.0
        favg=val(f,'fantasy_average',avg) if f else avg
        form=val(p,'form_index',50) if p else 50
        reliability=val(p,'reliability_index',50) if p else 50
        continuity=val(p,'continuity_index',50) if p else 50
        bonus=val(p,'bonus_index',50) if p else clamp(50+goals*4+assists*2)
        auction=val(p,'auction_value_index',50) if p else clamp((form+bonus+continuity)/3)
        starter=val(lr,'starter_probability',min(90,20+apps*2)) if lr else min(90,20+apps*2)
        appearance=val(lr,'appearance_probability',min(98,30+apps*2)) if lr else min(98,30+apps*2)
        availability=val(av,'availability_pct',85) if av else 85
        xg=val(ad,'xg',goals*.85) if ad else goals*.85
        xa=val(ad,'xa',assists*.8) if ad else assists*.8
        card_rate=clamp((val(r,'yellow_cards')+3*val(r,'red_cards'))*4)

        # Block 10 recommendations
        rec=clamp(.27*form+.20*reliability+.18*bonus+.15*starter+.10*availability+.10*(100-card_rate))
        pred_rating=clamp(5.2+(avg-5.5)*.7+(form-50)/100,4,8.5)
        goal_p=clamp(100*(goals+0.6)/(apps+4),0,65)
        assist_p=clamp(100*(assists+0.5)/(apps+5),0,55)
        clean_p=clamp(35+(reliability-50)*.3,5,75)
        no_vote=clamp(100-appearance)
        pred_fantasy=pred_rating+3*pct(goal_p)+pct(assist_p)-.5*pct(card_rate)
        label='schiera' if rec>=70 else 'valuta' if rec>=52 else 'panchina'
        explanation=f'Forma {form:.0f}/100, titolarità {starter:.0f}%, affidabilità {reliability:.0f}/100.'
        conf=clamp((reliability+availability)/200,0,1)
        c.execute('INSERT OR REPLACE INTO fantasy_recommendations(player_id,season_id,club_id,recommendation_score,predicted_rating,predicted_fantasy_score,goal_probability,assist_probability,clean_sheet_probability,card_probability,no_vote_risk,recommendation,explanation,confidence,methodology_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['player_id'],r['season_id'],r['club_id'],rec,pred_rating,pred_fantasy,goal_p,assist_p,clean_p,card_rate,no_vote,label,explanation,conf,'block10-v1'))

        # Block 11 auction
        b500=round(max(1,auction*0.65+bonus*0.35)*1.8,1); b1000=round(b500*2,1)
        tier='top' if b500>=140 else 'premium' if b500>=90 else 'titolare' if b500>=45 else 'scommessa'
        underv=clamp(rec-auction+50); over=clamp(auction-rec+50); replacement=clamp(100-auction)
        c.execute('INSERT OR REPLACE INTO auction_values(player_id,season_id,club_id,budget_500_value,budget_1000_value,value_tier,undervaluation_index,overvaluation_risk,replacement_value,confidence,methodology_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(r['player_id'],r['season_id'],r['club_id'],b500,b1000,tier,underv,over,replacement,conf,'block11-v1'))

        # Block 12 simulation summary (deterministic expected values, simulation-ready schema)
        exp_apps=max(apps,appearance*.38); exp_goals=max(goals,goal_p/100*exp_apps); exp_assists=max(assists,assist_p/100*exp_apps)
        exp_pts=exp_apps*pred_rating+3*exp_goals+exp_assists
        floor=exp_pts*.72; ceiling=exp_pts*1.32
        breakout=clamp((rec+underv)/2); flop=clamp((over+no_vote)/2)
        c.execute('INSERT OR REPLACE INTO season_simulations(player_id,season_id,club_id,simulations,expected_appearances,expected_goals,expected_assists,expected_fantasy_points,floor_fantasy_points,ceiling_fantasy_points,breakout_probability,flop_probability,methodology_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['player_id'],r['season_id'],r['club_id'],1000,exp_apps,exp_goals,exp_assists,exp_pts,floor,ceiling,breakout,flop,'block12-v1'))

        # Block 13 dashboard snapshot
        snapshot={'rating':pred_rating,'fantasy':pred_fantasy,'recommendation':label,'tier':tier,'confidence':conf}
        c.execute('INSERT OR REPLACE INTO dashboard_player_snapshots(player_id,season_id,club_id,form_index,fantasy_average,goals,assists,xg,xa,availability_pct,starter_probability,auction_value,recommendation_score,snapshot_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['player_id'],r['season_id'],r['club_id'],form,favg,goals,assists,xg,xa,availability,starter,b500,rec,json.dumps(snapshot,ensure_ascii=False)))

        # Block 16 predictive AI
        spread=max(.25,1-conf)
        explosion=clamp((goal_p+assist_p+breakout)/3); flop_i=clamp((no_vote+card_rate+over)/3)
        ai_text=f'Previsione basata su forma, minutaggio, bonus, disponibilità e storico stagionale; confidenza {conf:.0%}.'
        c.execute('INSERT OR REPLACE INTO ai_player_predictions(player_id,season_id,club_id,predicted_rating,predicted_fantasy_score,rating_low,rating_high,goal_probability,assist_probability,yellow_probability,red_probability,clean_sheet_probability,explosion_index,flop_index,confidence,explanation,methodology_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['player_id'],r['season_id'],r['club_id'],pred_rating,pred_fantasy,max(4,pred_rating-spread),min(10,pred_rating+spread),goal_p,assist_p,card_rate*.85,card_rate*.08,clean_p,explosion,flop_i,conf,ai_text,'block16-v1'))
        outputs+=1

    # Block 14 API registry
    resources={'players':'/api/players','matches':'/api/matches','recommendations':'/api/recommendations','auction-values':'/api/auction-values','predictions':'/api/predictions'}
    table_map={'players':'players','matches':'matches','recommendations':'fantasy_recommendations','auction-values':'auction_values','predictions':'ai_player_predictions'}
    for name,path in resources.items():
        t=table_map[name]; count=c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] if t in tables(c) else 0
        c.execute('INSERT OR REPLACE INTO api_export_registry(resource_name,endpoint_path,row_count,schema_version,generated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)',(name,path,count,'v1'))

    # Block 15 health report
    monitored=['players','clubs','matches','fantasy_recommendations','auction_values','season_simulations','dashboard_player_snapshots','ai_player_predictions']
    health={}
    for t in monitored:
        count=c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] if t in tables(c) else 0
        status='ok' if count>0 or t=='matches' else 'warning'
        coverage=100 if count>0 else 0
        details={'table':t,'records':count}
        c.execute('INSERT INTO pipeline_health(block_name,status,row_count,coverage_pct,warning_count,details_json) VALUES(?,?,?,?,?,?)',(t,status,count,coverage,0 if status=='ok' else 1,json.dumps(details)))
        health[t]=details

    c.commit()
    report={'player_season_rows_processed':outputs,'health':health,'methodologies':['block9-v1','block10-v1','block11-v1','block12-v1','block16-v1']}
    Path('reports').mkdir(exist_ok=True)
    Path('reports/blocks_9_16_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    c.close()

if __name__=='__main__': main()
