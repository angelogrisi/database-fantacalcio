#!/usr/bin/env python3
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path

DB=Path(os.getenv('DATABASE_PATH','data/database-fantacalcio.sqlite'))
METHOD='block8-v1'

def clamp(v): return max(0.0,min(100.0,float(v)))
def table_exists(c,n): return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone() is not None

def main():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    con.executescript(Path('migrations/008_block_8_lineup_readiness.sql').read_text())
    has_av=table_exists(con,'player_availability')
    has_idx=table_exists(con,'proprietary_player_indexes')
    q='''SELECT ps.player_id,ps.season_id,ps.club_id,ps.competition_id,
                COALESCE(st.appearances,0) appearances,COALESCE(st.starts,0) starts,
                COALESCE(st.minutes,0) minutes,COALESCE(st.yellow_cards,0) yellow_cards,
                COALESCE(st.red_cards,0) red_cards'''
    q += ', av.availability_pct, av.injury_risk_index' if has_av else ', NULL availability_pct, NULL injury_risk_index'
    q += ', pi.continuity_index, pi.rotation_risk, pi.reliability_index' if has_idx else ', NULL continuity_index, NULL rotation_risk, NULL reliability_index'
    q += ''' FROM player_seasons ps
             LEFT JOIN player_season_statistics_extended st
             ON st.player_id=ps.player_id AND st.season_id=ps.season_id AND st.club_id=ps.club_id'''
    if has_av: q += ' LEFT JOIN player_availability av ON av.player_id=ps.player_id AND av.season_id=ps.season_id AND av.club_id=ps.club_id'
    if has_idx: q += " LEFT JOIN proprietary_player_indexes pi ON pi.player_id=ps.player_id AND pi.season_id=ps.season_id AND pi.club_id=ps.club_id AND pi.methodology_version='block7-v1'"
    rows=[dict(r) for r in con.execute(q)]
    total=0
    for r in rows:
        apps=r['appearances'] or 0; starts=r['starts'] or 0; mins=r['minutes'] or 0
        start_rate=starts/apps if apps else 0
        min_rate=min(1,mins/(apps*90)) if apps else 0
        availability=r['availability_pct'] if r['availability_pct'] is not None else 100-clamp(r['injury_risk_index'] or 15)
        continuity=r['continuity_index'] if r['continuity_index'] is not None else clamp(55*start_rate+45*min_rate)
        reliability=r['reliability_index'] if r['reliability_index'] is not None else clamp(45*min_rate+35*start_rate+min(20,apps))
        starter=clamp(.45*(start_rate*100)+.25*continuity+.20*reliability+.10*availability)
        appearance=clamp(.50*availability+.30*reliability+.20*min(100,apps*4))
        rotation=r['rotation_risk'] if r['rotation_risk'] is not None else clamp(100-continuity)
        bench=clamp(max(0,appearance-starter)*.85)
        expected=round(90*(starter/100)+28*(bench/100),1)
        suspension=clamp((r['yellow_cards'] or 0)*3+(r['red_cards'] or 0)*18)
        if appearance<35: status='unlikely'
        elif starter>=72: status='probable_starter'
        elif starter>=48: status='in_contention'
        else: status='probable_bench'
        coverage_fields=[apps>0,r['availability_pct'] is not None,r['continuity_index'] is not None,r['reliability_index'] is not None]
        coverage=round(100*sum(coverage_fields)/len(coverage_fields),1)
        confidence=round(coverage/100,3)
        con.execute('''INSERT INTO player_lineup_readiness(
          player_id,season_id,club_id,competition_id,starter_probability,appearance_probability,
          expected_minutes,bench_entry_probability,rotation_risk,availability_probability,
          suspension_risk,lineup_status,confidence,data_coverage_pct,value_type,methodology_version)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(player_id,season_id,club_id,competition_id,methodology_version) DO UPDATE SET
          starter_probability=excluded.starter_probability,appearance_probability=excluded.appearance_probability,
          expected_minutes=excluded.expected_minutes,bench_entry_probability=excluded.bench_entry_probability,
          rotation_risk=excluded.rotation_risk,availability_probability=excluded.availability_probability,
          suspension_risk=excluded.suspension_risk,lineup_status=excluded.lineup_status,
          confidence=excluded.confidence,data_coverage_pct=excluded.data_coverage_pct,
          generated_at=CURRENT_TIMESTAMP''',
          (r['player_id'],r['season_id'],r['club_id'],r['competition_id'],round(starter,1),round(appearance,1),expected,
           round(bench,1),round(rotation,1),round(availability,1),round(suspension,1),status,confidence,coverage,'estimated',METHOD))
        total+=1
    con.commit()
    report={'methodology_version':METHOD,'rows':total,'average_confidence':con.execute("SELECT ROUND(AVG(confidence),3) FROM player_lineup_readiness WHERE methodology_version=?",(METHOD,)).fetchone()[0]}
    Path('reports').mkdir(exist_ok=True); Path('reports/block_8_coverage_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    con.close(); print(json.dumps(report,indent=2))
if __name__=='__main__': main()
