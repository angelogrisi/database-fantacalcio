#!/usr/bin/env python3
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB=Path(os.getenv('DATABASE_PATH','data/database-fantacalcio.sqlite'))
OUT=Path(os.getenv('COVERAGE_REPORT_PATH','reports/pipeline_coverage_report.json'))
ESSENTIAL=['appearances','minutes','goals','assists']

con=sqlite3.connect(DB)
con.row_factory=sqlite3.Row

def table(name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def cols(name):
    return {r[1] for r in con.execute(f'PRAGMA table_info({name})')} if table(name) else set()

def count(name):
    return con.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] if table(name) else 0

def ensure_player_seasons():
    if not all(table(x) for x in ('players','seasons','clubs','player_seasons')): return 0
    source=None
    for candidate in ('player_season_statistics_extended','player_season_stats'):
        if table(candidate) and {'player_id','season_id','club_id'} <= cols(candidate): source=candidate; break
    if not source: return 0
    before=count('player_seasons')
    c=cols('player_seasons')
    fields=['player_id','season_id','club_id']
    if 'competition_id' in c and 'competition_id' in cols(source): fields.append('competition_id')
    sql=f"INSERT OR IGNORE INTO player_seasons({','.join(fields)}) SELECT DISTINCT {','.join(fields)} FROM {source} WHERE player_id IS NOT NULL AND season_id IS NOT NULL AND club_id IS NOT NULL"
    con.execute(sql)
    return count('player_seasons')-before

def fallback_stats():
    target='player_season_statistics_extended'
    source='player_season_stats'
    if not (table(target) and table(source)): return 0
    tc,sc=cols(target),cols(source)
    keys=['player_id','season_id','club_id','competition_id']
    if not set(keys)<=tc or not set(keys)<=sc: return 0
    before=count(target)
    common=[x for x in ['appearances','starts','minutes','goals','assists','yellow_cards','red_cards','goals_per90','assists_per90'] if x in tc and x in sc]
    fields=keys+common+(['source_name'] if 'source_name' in tc else [])
    select=keys+common+(["'secondary-database-fallback' AS source_name"] if 'source_name' in tc else [])
    con.execute(f"INSERT OR IGNORE INTO {target}({','.join(fields)}) SELECT {','.join(select)} FROM {source} WHERE player_id IS NOT NULL")
    return count(target)-before

def api_status():
    if not table('import_runs'): return {'available':False,'message':'import_runs table absent'}
    rows=[dict(r) for r in con.execute("SELECT block_name,source_name,season_label,status,records_received,records_inserted,records_updated,records_skipped,error_message FROM import_runs ORDER BY import_run_id")]
    successful=sum(1 for r in rows if r.get('status') in ('completed','success') and (r.get('records_received') or 0)>0)
    return {'available':bool(rows),'runs':rows,'successful_runs_with_data':successful,'api_returned_data':successful>0}

def coverage():
    source='player_season_statistics_extended' if table('player_season_statistics_extended') else ('player_season_stats' if table('player_season_stats') else None)
    if not source: return {'table':None,'rows':0,'coverage_pct':0,'fields':{}}
    c=cols(source); total=count(source); result={}
    for f in ESSENTIAL:
        if f not in c: result[f]={'available':False,'completed':0,'coverage_pct':0}; continue
        completed=con.execute(f'SELECT COUNT(*) FROM {source} WHERE {f} IS NOT NULL').fetchone()[0]
        result[f]={'available':True,'completed':completed,'coverage_pct':round(100*completed/total,2) if total else 0}
    available=[v['coverage_pct'] for v in result.values() if v['available']]
    overall=round(sum(available)/len(available),2) if available else 0
    return {'table':source,'rows':total,'coverage_pct':overall,'fields':result}

added_links=ensure_player_seasons()
fallback_rows=fallback_stats()
con.commit()
report={
 'generated_at':datetime.now(timezone.utc).isoformat(),
 'database':str(DB),
 'api':api_status(),
 'repairs':{'player_season_links_added':added_links,'secondary_source_rows_added':fallback_rows},
 'coverage':coverage(),
 'table_counts':{t:count(t) for t in ['players','clubs','seasons','matches','player_seasons','player_season_statistics_extended','player_season_stats','fantasy_player_season','player_advanced_season_metrics','player_availability','player_lineup_readiness'] if table(t)}
}
report['status']='complete' if report['coverage']['coverage_pct']>=98 else ('partial' if report['coverage']['rows'] else 'empty')
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
con.close()
