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

def columns(name):
    return {row[1] for row in con.execute(f'PRAGMA table_info({name})')} if has_table(name) else set()

col = {name: columns(name) for name in ['players','player_seasons','seasons','clubs','player_season_stats','fantasy_season_metrics','advanced_player_metrics','proprietary_player_indexes']}

def pick(table_alias, table_name, field, fallback='NULL'):
    return f'{table_alias}.{field}' if field in col[table_name] else fallback

joins = []
if has_table('player_seasons'):
    joins.append('LEFT JOIN player_seasons ps ON ps.player_id=p.player_id')
if has_table('seasons') and has_table('player_seasons'):
    joins.append('LEFT JOIN seasons s ON s.season_id=ps.season_id')
if has_table('clubs') and has_table('player_seasons'):
    joins.append('LEFT JOIN clubs c ON c.club_id=ps.club_id')
if has_table('player_season_stats') and has_table('player_seasons'):
    joins.append('LEFT JOIN player_season_stats st ON st.player_id=p.player_id AND st.season_id=ps.season_id AND st.club_id=ps.club_id')
if has_table('fantasy_season_metrics') and has_table('player_seasons'):
    joins.append('LEFT JOIN fantasy_season_metrics fm ON fm.player_id=p.player_id AND fm.season_id=ps.season_id AND fm.club_id=ps.club_id')
if has_table('advanced_player_metrics') and has_table('player_seasons'):
    joins.append('LEFT JOIN advanced_player_metrics am ON am.player_id=p.player_id AND am.season_id=ps.season_id')
if has_table('proprietary_player_indexes') and has_table('player_seasons'):
    joins.append('LEFT JOIN proprietary_player_indexes pi ON pi.player_id=p.player_id AND pi.season_id=ps.season_id')

position = pick('p','players','primary_position',pick('p','players','position'))
appearances = pick('st','player_season_stats','appearances',pick('fm','fantasy_season_metrics','appearances_with_rating','0'))
auction = pick('fm','fantasy_season_metrics','auction_value_index',pick('pi','proprietary_player_indexes','auction_value'))
xg = pick('st','player_season_stats','xg',pick('am','advanced_player_metrics','xg'))
xa = pick('st','player_season_stats','xa',pick('am','advanced_player_metrics','xa'))

fields = [
    pick('p','players','player_id') + ' AS player_id',
    pick('p','players','full_name',"''") + ' AS name',
    pick('p','players','nationality') + ' AS nationality',
    position + ' AS position',
    pick('s','seasons','label') + ' AS season',
    pick('c','clubs','official_name') + ' AS club',
    pick('fm','fantasy_season_metrics','fantasy_role') + ' AS fantasy_role',
    appearances + ' AS appearances',
    pick('st','player_season_stats','minutes','0') + ' AS minutes',
    pick('st','player_season_stats','goals','0') + ' AS goals',
    pick('st','player_season_stats','assists','0') + ' AS assists',
    pick('fm','fantasy_season_metrics','average_rating') + ' AS average_rating',
    pick('fm','fantasy_season_metrics','fantasy_average') + ' AS fantasy_average',
    auction + ' AS auction_value',
    xg + ' AS xg',
    xa + ' AS xa',
    pick('pi','proprietary_player_indexes','form_index') + ' AS form_index',
    pick('pi','proprietary_player_indexes','reliability_index') + ' AS reliability_index'
]

rows = [dict(row) for row in con.execute('SELECT ' + ','.join(fields) + ' FROM players p ' + ' '.join(joins))]
unique = {(row.get('player_id'), row.get('season'), row.get('club')): row for row in rows}
rows = list(unique.values())
summary = {
    'players': con.execute('SELECT COUNT(*) FROM players').fetchone()[0],
    'clubs': con.execute('SELECT COUNT(*) FROM clubs').fetchone()[0] if has_table('clubs') else 0,
    'matches': con.execute('SELECT COUNT(*) FROM matches').fetchone()[0] if has_table('matches') else 0,
    'records': len(rows)
}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({'summary': summary, 'players': rows}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'Esportati {len(rows)} record in {out_path}')
