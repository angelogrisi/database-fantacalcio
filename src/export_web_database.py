#!/usr/bin/env python3
from __future__ import annotations
import json, os, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.getenv('DATABASE_PATH',ROOT/'data'/'database-fantacalcio.sqlite'))
OUT=Path(os.getenv('WEB_DATA_PATH',ROOT/'pages'/'data'/'database.json'))

def tables(con): return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def cols(con,t): return {r[1] for r in con.execute(f'PRAGMA table_info({t})')}
def expr(alias,column,default='NULL'):
    return f'{alias}.{column}' if column in COLUMN_MAP.get(alias,set()) else default

def main():
    if not DB.exists(): raise SystemExit(f'Database non trovato: {DB}')
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    ts=tables(con)
    global COLUMN_MAP
    COLUMN_MAP={}
    aliases={'p':'players','ps':'player_seasons','s':'seasons','c':'clubs','st':'player_season_stats','fm':'fantasy_season_metrics','am':'advanced_player_metrics','pi':'proprietary_player_indexes'}
    for a,t in aliases.items(): COLUMN_MAP[a]=cols(con,t) if t in ts else set()

    joins=[]
    base='players p'
    if 'player_seasons' in ts: joins.append('LEFT JOIN player_seasons ps ON ps.player_id=p.player_id')
    if 'seasons' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN seasons s ON s.season_id=ps.season_id')
    if 'clubs' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN clubs c ON c.club_id=ps.club_id')
    if 'player_season_stats' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN player_season_stats st ON st.player_id=p.player_id AND st.season_id=ps.season_id AND st.club_id=ps.club_id')
    if 'fantasy_season_metrics' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN fantasy_season_metrics fm ON fm.player_id=p.player_id AND fm.season_id=ps.season_id AND fm.club_id=ps.club_id')
    if 'advanced_player_metrics' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN advanced_player_metrics am ON am.player_id=p.player_id AND am.season_id=ps.season_id')
    if 'proprietary_player_indexes' in ts and 'player_seasons' in ts: joins.append('LEFT JOIN proprietary_player_indexes pi ON pi.player_id=p.player_id AND pi.season_id=ps.season_id')

    select=[
      f"{expr('p','player_id')} player_id",f"{expr('p','full_name',"''")} name",f"{expr('p','nationality')} nationality",f"{expr('p','primary_position',expr('p','position'))} position",
      f"{expr('s','label')} season",f"{expr('c','official_name')} club",f"{expr('fm','fantasy_role')} fantasy_role",
      f"{expr('st','appearances',expr('fm','appearances_with_rating','0'))} appearances",f"{expr('st','minutes','0')} minutes",f"{expr('st','goals','0')} goals",f"{expr('st','assists','0')} assists",
      f"{expr('fm','average_rating')} average_rating",f"{expr('fm','fantasy_average')} fantasy_average",f"{expr('fm','auction_value_index',expr('pi','auction_value'))} auction_value",
      f"{expr('st','xg',expr('am','xg'))} xg",f"{expr('st','xa',expr('am','xa'))} xa",f"{expr('pi','form_index')} form_index",f"{expr('pi','reliability_index')} reliability_index"
    ]
    sql='SELECT '+','.join(select)+' FROM '+base+' '+' '.join(joins)
    rows=[dict(r) for r in con.execute(sql)]
    # remove exact duplicate player-season-club rows
    unique={}
    for r in rows: unique[(r.get('player_id'),r.get('season'),r.get('club'))]=r
    rows=list(unique.values())
    summary={
      'players': con.execute('SELECT COUNT(*) FROM players').fetchone()[0],
      'clubs': con.execute('SELECT COUNT(*) FROM clubs').fetchone()[0] if 'clubs' in ts else 0,
      'matches': con.execute('SELECT COUNT(*) FROM matches').fetchone()[0] if 'matches' in ts else 0,
      'records': len(rows)
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'summary':summary,'players':rows},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Esportati {len(rows)} record in {OUT}')

if __name__=='__main__': main()
