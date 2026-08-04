#!/usr/bin/env python3
from __future__ import annotations
import base64,csv,hashlib,io,json,lzma,math,os,re,sqlite3,unicodedata
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.getenv('DATABASE_PATH',ROOT/'data/database-fantacalcio.sqlite'))
REPORT=Path(os.getenv('KAGGLE_IMPORT_REPORT_PATH',ROOT/'reports/kaggle_serie_a_import_report.json'))
DATA=Path(os.getenv('KAGGLE_SERIE_A_PATH',ROOT/'data/sources/kaggle/serie_a_league'))
EMBED=ROOT/'data/sources/kaggle/embedded'
TRANS=str.maketrans({'ł':'l','Ł':'L','đ':'d','Đ':'D','ø':'o','Ø':'O','æ':'ae','Æ':'AE','œ':'oe','Œ':'OE','ß':'ss'})
DROP={'fc','ac','ssc','ss','us','bc','calcio','1907','1909','1913','1919'}

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '').translate(TRANS))
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',''.join(c for c in s if not unicodedata.combining(c)).lower()).split())
def cnorm(v):
    s=' '.join(x for x in norm(v).split() if x not in DROP)
    return {'internazionale milano':'inter','internazionale':'inter','hellas verona':'verona'}.get(s,s)
def num(v,integer=False):
    try:
        if v is None or str(v).strip().lower() in {'','nan','none','null','-'}: return None
        x=float(str(v).replace(',','.'))
        if math.isnan(x): return None
        return int(round(x)) if integer else x
    except ValueError:return None
def sid(prefix,*parts):return f"{prefix}_{hashlib.sha1('|'.join(norm(x) for x in parts).encode()).hexdigest()[:20]}"
def per90(v,m):return round(float(v)*90/m,4) if v is not None and m else None
def role(p):
    p=(p or '').upper()
    return 'P' if 'GK' in p else 'D' if 'DF' in p else 'C' if 'MF' in p else 'A' if 'FW' in p else None

def rows_from_source():
    files=sorted(DATA.glob('*.csv')) if DATA.exists() and DATA.is_dir() else ([DATA] if DATA.exists() else [])
    rows=[]
    if files:
        for f in files:
            with f.open(encoding='utf-8-sig',newline='') as h: rows.extend(csv.DictReader(h))
        return rows,[str(x) for x in files]
    parts=sorted(EMBED.glob('serie_a_stats.xz.b64.*'))
    if not parts: raise SystemExit('Dataset Kaggle non trovato')
    text=lzma.decompress(base64.b64decode(''.join(p.read_text().strip() for p in parts))).decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(text))),[str(x) for x in parts]

def ensure(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS player_source_matches(id INTEGER PRIMARY KEY,source_dataset TEXT,season_label TEXT,source_player_name TEXT,source_squad TEXT,player_id TEXT,club_id TEXT,match_method TEXT,match_confidence REAL,imported_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(source_dataset,season_label,source_player_name,source_squad));
    CREATE TABLE IF NOT EXISTS dataset_import_runs(id INTEGER PRIMARY KEY,source_name TEXT,dataset_path TEXT,started_at TEXT DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,input_rows INTEGER,imported_rows INTEGER,exact_player_matches INTEGER,fuzzy_player_matches INTEGER,created_players INTEGER,unmatched_clubs INTEGER,skipped_rows INTEGER,coverage_pct REAL,details_json TEXT);
    ''')
    con.execute("INSERT OR IGNORE INTO sources(name,base_url,license_notes,access_type) VALUES(?,?,?,?)",('Kaggle community datasets (FBref-derived)','https://www.kaggle.com/','User-provided archives; verify original and upstream licenses before commercial redistribution.','download'))

def resolve_club(con,season_id,squad):
    target=cnorm(squad); best=(None,0,'unmatched')
    for r in con.execute('''SELECT c.*,(SELECT COUNT(*) FROM player_seasons ps WHERE ps.club_id=c.club_id AND ps.season_id=?) n FROM clubs c''',(season_id,)):
        names={cnorm(r['official_name']),cnorm(r['short_name'])}
        score=1 if target in names else max([SequenceMatcher(None,target,x).ratio() for x in names if x] or [0])
        score+=.08 if r['n'] else 0; score+=.02 if 'football_data' in (r['external_ids_json'] or '') else 0
        if score>best[1]:best=(r['club_id'],score,'exact' if target in names else 'fuzzy')
    return best if best[1]>=.72 else (None,best[1],'unmatched')

def pscore(name,born,p):
    a,b=norm(name),norm(p['full_name']); seq=SequenceMatcher(None,a,b).ratio(); ta,tb=set(a.split()),set(b.split())
    score=max(seq,.7*seq+.3*len(ta&tb)/max(1,len(ta|tb)))
    if a==b:score=1
    py=int(str(p['birth_date'])[:4]) if p['birth_date'] and str(p['birth_date'])[:4].isdigit() else None
    if born and py:score+=.07 if born==py else -.18
    if a.split()[-1:]==b.split()[-1:]:score+=.03
    return max(0,min(1,score))

def resolve_player(con,season_id,club_id,r):
    name=r['player_name'].strip(); born=num(r.get('born'),True)
    local=con.execute('''SELECT DISTINCT p.* FROM players p JOIN player_seasons ps ON ps.player_id=p.player_id WHERE ps.season_id=? AND ps.club_id=?''',(season_id,club_id)).fetchall()
    exact=[p for p in local if norm(p['full_name'])==norm(name)]
    if exact:return exact[0]['player_id'],'exact_club',1,False
    ranked=sorted(((pscore(name,born,p),p) for p in local),reverse=True,key=lambda x:x[0])
    if ranked and ranked[0][0]>=.86:return ranked[0][1]['player_id'],'fuzzy_club',ranked[0][0],False
    glob=[p for p in con.execute('SELECT * FROM players') if norm(p['full_name'])==norm(name)]
    if glob:return glob[0]['player_id'],'exact_global',.96,False
    pid=sid('PLY','kaggle',name,born or ''); parts=name.split(maxsplit=1); nat=(r.get('nationality') or '').split()
    con.execute('''INSERT OR IGNORE INTO players(player_id,first_name,last_name,full_name,nationality,primary_position,external_ids_json) VALUES(?,?,?,?,?,?,?)''',(pid,parts[0],parts[1] if len(parts)>1 else None,name,nat[-1] if nat else None,r.get('position') or None,json.dumps({'kaggle_key':f"{r.get('season')}|{r.get('squad')}|{name}"},ensure_ascii=False)))
    return pid,'created',.70,True

def iv(r,k):return num(r.get(k),True)
def fv(r,k):return num(r.get(k))
def completeness(r):
    keys='appearances starts minutes goals assists yellow_cards red_cards xg xag shots shots_on_target progressive_passes progressive_carries'.split()
    return round(100*sum(num(r.get(k)) is not None for k in keys)/len(keys),2)

def write_stats(con,r,pid,season_id,club_id,competition_id):
    apps=iv(r,'appearances') or 0; starts=iv(r,'starts') or 0; mins=iv(r,'minutes') or 0; goals=iv(r,'goals') or 0; assists=iv(r,'assists') or 0
    pk=iv(r,'penalty_goals') or 0; pka=iv(r,'penalty_attempts') or 0; missed=max(0,pka-pk); own=iv(r,'own_goals') or 0
    yc=iv(r,'yellow_cards') or 0; rc=iv(r,'red_cards') or 0; xg=fv(r,'xg'); xa=fv(r,'xag'); shots=iv(r,'shots'); sot=iv(r,'shots_on_target')
    kp=iv(r,'key_passes'); tkl=iv(r,'tackles'); inte=iv(r,'interceptions'); clr=iv(r,'clearances'); rec=iv(r,'recoveries'); drib=iv(r,'dribbles_completed')
    fls=iv(r,'fouls_committed'); fld=iv(r,'fouls_drawn'); aerial=iv(r,'aerial_duels_won'); cs=iv(r,'clean_sheets'); saves=iv(r,'saves'); pks=iv(r,'penalties_saved'); ga=iv(r,'goals_conceded'); prgp=iv(r,'progressive_passes'); prgc=iv(r,'progressive_carries')
    con.execute('''INSERT INTO player_season_stats(player_id,season_id,club_id,competition_id,appearances,starts,minutes,goals,assists,penalty_goals,penalties_missed,own_goals,xg,xa,shots,shots_on_target,pass_accuracy,key_passes,dribbles_completed,tackles,interceptions,clearances,recoveries,duels_won,fouls_committed,fouls_suffered,yellow_cards,red_cards,clean_sheets,saves,penalties_saved,goals_conceded,goals_per90,assists_per90,xg_per90,xa_per90,progressive_passes,progressive_carries) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(player_id,season_id,club_id,competition_id) DO UPDATE SET appearances=excluded.appearances,starts=excluded.starts,minutes=excluded.minutes,goals=excluded.goals,assists=excluded.assists,penalty_goals=excluded.penalty_goals,penalties_missed=excluded.penalties_missed,own_goals=excluded.own_goals,xg=COALESCE(excluded.xg,player_season_stats.xg),xa=COALESCE(excluded.xa,player_season_stats.xa),shots=COALESCE(excluded.shots,player_season_stats.shots),shots_on_target=COALESCE(excluded.shots_on_target,player_season_stats.shots_on_target),pass_accuracy=COALESCE(excluded.pass_accuracy,player_season_stats.pass_accuracy),key_passes=COALESCE(excluded.key_passes,player_season_stats.key_passes),dribbles_completed=COALESCE(excluded.dribbles_completed,player_season_stats.dribbles_completed),tackles=COALESCE(excluded.tackles,player_season_stats.tackles),interceptions=COALESCE(excluded.interceptions,player_season_stats.interceptions),clearances=COALESCE(excluded.clearances,player_season_stats.clearances),recoveries=COALESCE(excluded.recoveries,player_season_stats.recoveries),duels_won=COALESCE(excluded.duels_won,player_season_stats.duels_won),fouls_committed=COALESCE(excluded.fouls_committed,player_season_stats.fouls_committed),fouls_suffered=COALESCE(excluded.fouls_suffered,player_season_stats.fouls_suffered),yellow_cards=excluded.yellow_cards,red_cards=excluded.red_cards,clean_sheets=COALESCE(excluded.clean_sheets,player_season_stats.clean_sheets),saves=COALESCE(excluded.saves,player_season_stats.saves),penalties_saved=COALESCE(excluded.penalties_saved,player_season_stats.penalties_saved),goals_conceded=COALESCE(excluded.goals_conceded,player_season_stats.goals_conceded),goals_per90=excluded.goals_per90,assists_per90=excluded.assists_per90,xg_per90=COALESCE(excluded.xg_per90,player_season_stats.xg_per90),xa_per90=COALESCE(excluded.xa_per90,player_season_stats.xa_per90),progressive_passes=COALESCE(excluded.progressive_passes,player_season_stats.progressive_passes),progressive_carries=COALESCE(excluded.progressive_carries,player_season_stats.progressive_carries)''',(pid,season_id,club_id,competition_id,apps,starts,mins,goals,assists,pk,missed,own,xg,xa,shots,sot,fv(r,'pass_accuracy'),kp,drib,tkl,inte,clr,rec,aerial,fls,fld,yc,rc,cs,saves,pks,ga,per90(goals,mins),per90(assists,mins),per90(xg,mins),per90(xa,mins),prgp,prgc))
    con.execute('''INSERT INTO player_season_statistics_extended(player_id,season_id,club_id,competition_id,appearances,starts,substitute_appearances,minutes,goals,assists,goals_conceded,saves,shots_total,shots_on_target,passes_total,passes_key,pass_accuracy_pct,tackles_total,interceptions,duels_won,dribbles_attempts,dribbles_success,fouls_drawn,fouls_committed,yellow_cards,red_cards,penalties_scored,penalties_missed,penalties_saved,goals_per90,assists_per90,shots_per90,key_passes_per90,tackles_per90,interceptions_per90,dribble_success_pct,source_name,methodology_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(player_id,season_id,club_id,competition_id,source_name) DO UPDATE SET appearances=excluded.appearances,starts=excluded.starts,substitute_appearances=excluded.substitute_appearances,minutes=excluded.minutes,goals=excluded.goals,assists=excluded.assists,goals_conceded=excluded.goals_conceded,saves=excluded.saves,shots_total=excluded.shots_total,shots_on_target=excluded.shots_on_target,passes_total=excluded.passes_total,passes_key=excluded.passes_key,pass_accuracy_pct=excluded.pass_accuracy_pct,tackles_total=excluded.tackles_total,interceptions=excluded.interceptions,duels_won=excluded.duels_won,dribbles_attempts=excluded.dribbles_attempts,dribbles_success=excluded.dribbles_success,fouls_drawn=excluded.fouls_drawn,fouls_committed=excluded.fouls_committed,yellow_cards=excluded.yellow_cards,red_cards=excluded.red_cards,penalties_scored=excluded.penalties_scored,penalties_missed=excluded.penalties_missed,penalties_saved=excluded.penalties_saved,goals_per90=excluded.goals_per90,assists_per90=excluded.assists_per90,shots_per90=excluded.shots_per90,key_passes_per90=excluded.key_passes_per90,tackles_per90=excluded.tackles_per90,interceptions_per90=excluded.interceptions_per90,dribble_success_pct=excluded.dribble_success_pct,updated_at=CURRENT_TIMESTAMP''',(pid,season_id,club_id,competition_id,apps,starts,max(0,apps-starts),mins,goals,assists,ga,saves,shots,sot,iv(r,'passes_attempted'),kp,fv(r,'pass_accuracy'),tkl,inte,aerial,iv(r,'dribbles_attempted'),drib,fld,fls,yc,rc,pk,missed,pks,per90(goals,mins),per90(assists,mins),per90(shots,mins),per90(kp,mins),per90(tkl,mins),per90(inte,mins),round(100*drib/iv(r,'dribbles_attempted'),2) if drib is not None and iv(r,'dribbles_attempted') else None,'Kaggle-FBref','kaggle-import-v1'))
    isgk=(r.get('position') or '').upper().startswith('GK'); bonus=goals*3+assists+(pks or 0)*3; malus=-3*missed-2*own-.5*yc-rc+(-1*(ga or 0) if isgk else 0); rel=min(100,apps*100/38) if apps else 0; bidx=min(100,max(0,bonus*4)); mrisk=min(100,abs(malus)*8); auction=min(100,max(0,.4*(goals*3+assists*1.5+(xg or 0)+(xa or 0))*3+.3*rel+.3*min(100,mins/30)))
    con.execute('''INSERT INTO fantasy_player_season(ruleset_id,player_id,season_id,club_id,competition_id,fantasy_role,appearances_with_rating,average_rating,fantasy_average,total_bonus,total_malus,total_fantasy_points,goals,assists,penalty_goals,penalties_missed,own_goals,yellow_cards,red_cards,penalties_saved,goals_conceded,clean_sheets,reliability_index,availability_index,bonus_index,malus_risk_index,auction_value_index,data_quality) VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ruleset_id,player_id,season_id,club_id,competition_id) DO UPDATE SET fantasy_role=excluded.fantasy_role,total_bonus=excluded.total_bonus,total_malus=excluded.total_malus,goals=excluded.goals,assists=excluded.assists,penalty_goals=excluded.penalty_goals,penalties_missed=excluded.penalties_missed,own_goals=excluded.own_goals,yellow_cards=excluded.yellow_cards,red_cards=excluded.red_cards,penalties_saved=excluded.penalties_saved,goals_conceded=excluded.goals_conceded,clean_sheets=excluded.clean_sheets,reliability_index=excluded.reliability_index,availability_index=excluded.availability_index,bonus_index=excluded.bonus_index,malus_risk_index=excluded.malus_risk_index,auction_value_index=excluded.auction_value_index,data_quality=excluded.data_quality''',(pid,season_id,club_id,competition_id,role(r.get('position')),0,None,None,bonus,malus,0,goals,assists,pk,missed,own,yc,rc,pks or 0,ga or 0,cs or 0,rel,rel,bidx,mrisk,auction,completeness(r)))

def main():
    rows,files=rows_from_source(); DB.parent.mkdir(parents=True,exist_ok=True); REPORT.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); ensure(con)
    comp=con.execute("SELECT competition_id FROM competitions WHERE name='Serie A' AND country='Italy'").fetchone()[0]
    run=con.execute('INSERT INTO dataset_import_runs(source_name,dataset_path) VALUES(?,?)',('Kaggle community datasets (FBref-derived)',','.join(files))).lastrowid
    c=Counter(input_rows=len(rows)); by=defaultdict(Counter); unmatched=[]
    for r in rows:
        if r.get('competition_scope')!='serie_a_league':c['skipped_rows']+=1;continue
        s=con.execute('SELECT season_id FROM seasons WHERE label=?',(r.get('season'),)).fetchone()
        if not s:c['skipped_rows']+=1;continue
        club,cc,cm=resolve_club(con,s[0],r.get('squad'))
        if not club:c['unmatched_clubs']+=1;c['skipped_rows']+=1;unmatched.append({'season':r.get('season'),'club':r.get('squad')});continue
        pid,pm,pc,created=resolve_player(con,s[0],club,r); c['created_players']+=created; c['exact_player_matches']+=pm.startswith('exact'); c['fuzzy_player_matches']+=pm.startswith('fuzzy')
        con.execute('INSERT OR IGNORE INTO player_seasons(player_id,season_id,club_id,competition_id) VALUES(?,?,?,?)',(pid,s[0],club,comp)); write_stats(con,r,pid,s[0],club,comp)
        con.execute('''INSERT INTO player_source_matches(source_dataset,season_label,source_player_name,source_squad,player_id,club_id,match_method,match_confidence) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_dataset,season_label,source_player_name,source_squad) DO UPDATE SET player_id=excluded.player_id,club_id=excluded.club_id,match_method=excluded.match_method,match_confidence=excluded.match_confidence,imported_at=CURRENT_TIMESTAMP''',(r.get('source_dataset'),r.get('season'),r.get('player_name'),r.get('squad'),pid,club,f'{cm}+{pm}',round(min(cc,pc),3)))
        c['imported_rows']+=1;by[r.get('season')]['imported']+=1;by[r.get('season')]['created_players']+=created
    con.commit(); coverage=round(100*c['imported_rows']/max(1,c['input_rows']),2)
    report={'source':'Kaggle community datasets (FBref-derived)','dataset_files':files,**dict(c),'coverage_pct':coverage,'by_season':{k:dict(v) for k,v in sorted(by.items())},'database_counts':{'player_season_stats':con.execute('SELECT COUNT(*) FROM player_season_stats').fetchone()[0],'extended_stats':con.execute('SELECT COUNT(*) FROM player_season_statistics_extended').fetchone()[0],'fantasy_season':con.execute('SELECT COUNT(*) FROM fantasy_player_season').fetchone()[0]},'unmatched_sample':unmatched[:30],'note':'The uploaded 2021-22 and 2022-23 club files contain all-competition totals, so they are not inserted as Serie A-only statistics.'}
    con.execute('''UPDATE dataset_import_runs SET completed_at=CURRENT_TIMESTAMP,input_rows=?,imported_rows=?,exact_player_matches=?,fuzzy_player_matches=?,created_players=?,unmatched_clubs=?,skipped_rows=?,coverage_pct=?,details_json=? WHERE id=?''',(c['input_rows'],c['imported_rows'],c['exact_player_matches'],c['fuzzy_player_matches'],c['created_players'],c['unmatched_clubs'],c['skipped_rows'],coverage,json.dumps(report,ensure_ascii=False),run));con.commit();con.close()
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
