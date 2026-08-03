#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DB_PATH = Path(os.getenv('DATABASE_PATH', ROOT / 'data/database-fantacalcio.sqlite'))
TIMEOUT = int(os.getenv('REQUEST_TIMEOUT_SECONDS', '30'))

SEASONS = [
    ('2021-22', '2021-07-01', '2022-06-30', 1),
    ('2022-23', '2022-07-01', '2023-06-30', 1),
    ('2023-24', '2023-07-01', '2024-06-30', 1),
    ('2024-25', '2024-07-01', '2025-06-30', 1),
    ('2025-26', '2025-07-01', '2026-06-30', 1),
]

SOURCES = [
    ('football-data.org', 'https://api.football-data.org/v4', 'Provider terms apply', 'api_key'),
    ('API-Football', 'https://v3.football.api-sports.io', 'Provider terms apply', 'api_key'),
    ('StatsBomb Open Data', 'https://raw.githubusercontent.com/statsbomb/open-data/master/data', 'Open-data licence and attribution apply', 'open'),
    ('TheSportsDB', 'https://www.thesportsdb.com/api/v1/json/123', 'Free v1 API', 'public_key'),
]

COMPETITIONS = [
    ('Serie A', 'Italy', 1), ('Premier League', 'England', 1),
    ('La Liga', 'Spain', 1), ('Bundesliga', 'Germany', 1),
    ('Ligue 1', 'France', 1), ('Eredivisie', 'Netherlands', 1),
    ('Primeira Liga', 'Portugal', 1), ('Championship', 'England', 2),
    ('MLS', 'United States', 1), ('Saudi Pro League', 'Saudi Arabia', 1),
    ('Brasileirao', 'Brazil', 1), ('Liga Profesional Argentina', 'Argentina', 1),
    ('J League', 'Japan', 1), ('K League', 'South Korea', 1),
]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def stable_id(prefix: str, *parts: Any) -> str:
    raw = '|'.join('' if p is None else str(p).strip().lower() for p in parts)
    return f'{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}'


def init_db() -> None:
    schema = (ROOT / 'schema.sql').read_text(encoding='utf-8')
    with connect() as conn:
        conn.executescript(schema)
        conn.executemany('INSERT OR IGNORE INTO seasons(label,start_date,end_date,complete) VALUES (?,?,?,?)', SEASONS)
        conn.executemany('INSERT OR IGNORE INTO sources(name,base_url,license_notes,access_type) VALUES (?,?,?,?)', SOURCES)
        conn.executemany('INSERT OR IGNORE INTO competitions(name,country,level) VALUES (?,?,?)', COMPETITIONS)
    print(f'Database initialized: {DB_PATH}')


def request_json(url: str, *, headers: dict[str, str] | None = None) -> Any:
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def sync_football_data() -> None:
    key = os.getenv('FOOTBALL_DATA_API_KEY')
    if not key or key == 'insert_key_here':
        raise RuntimeError('FOOTBALL_DATA_API_KEY missing from .env')
    payload = request_json('https://api.football-data.org/v4/competitions/', headers={'X-Auth-Token': key})
    with connect() as conn:
        for item in payload.get('competitions', []):
            name = item.get('name')
            country = (item.get('area') or {}).get('name')
            if not name:
                continue
            ext = json.dumps({'football_data': item.get('id'), 'code': item.get('code')}, ensure_ascii=False)
            conn.execute('''INSERT INTO competitions(name,country,external_ids_json)
                            VALUES (?,?,?)
                            ON CONFLICT(name,country) DO UPDATE SET external_ids_json=excluded.external_ids_json''',
                         (name, country, ext))
    print('football-data.org competitions synchronized')


def sync_thesportsdb_leagues() -> None:
    payload = request_json('https://www.thesportsdb.com/api/v1/json/123/all_leagues.php')
    with connect() as conn:
        for item in payload.get('leagues') or []:
            if item.get('strSport') != 'Soccer':
                continue
            name = item.get('strLeague')
            if not name:
                continue
            ext = json.dumps({'thesportsdb': item.get('idLeague')}, ensure_ascii=False)
            conn.execute('''INSERT INTO competitions(name,external_ids_json)
                            VALUES (?,?) ON CONFLICT(name,country) DO NOTHING''', (name, ext))
    print('TheSportsDB soccer leagues synchronized')


def validate() -> int:
    rules = {
        'duplicate player identities': '''SELECT full_name,birth_date,COUNT(*) c FROM players
            GROUP BY full_name,birth_date HAVING c>1''',
        'starts exceed appearances': 'SELECT id FROM player_season_stats WHERE starts>appearances',
        'negative minutes': 'SELECT id FROM player_match_stats WHERE minutes<0 UNION ALL SELECT id FROM player_season_stats WHERE minutes<0',
        'invalid ratings': 'SELECT id FROM derived_ratings WHERE overall NOT BETWEEN 0 AND 100 OR potential NOT BETWEEN 0 AND 100',
        'orphan provenance': 'SELECT provenance_id FROM provenance WHERE source_id IS NULL',
    }
    failures = 0
    with connect() as conn:
        for name, sql in rules.items():
            rows = conn.execute(sql).fetchall()
            print(f'{name}: {len(rows)} issue(s)')
            failures += len(rows)
    return 1 if failures else 0


def status() -> None:
    tables = ['sources','seasons','competitions','clubs','players','matches','player_match_stats','player_season_stats','injuries','transfers','derived_ratings','provenance','quality_issues']
    with connect() as conn:
        for table in tables:
            count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f'{table}: {count:,}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Database Fantacalcio pipeline')
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--sync-football-data', action='store_true')
    parser.add_argument('--sync-thesportsdb', action='store_true')
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()

    if args.init: init_db()
    if args.sync_football_data: sync_football_data()
    if args.sync_thesportsdb: sync_thesportsdb_leagues()
    if args.status: status()
    if args.validate: raise SystemExit(validate())
    if not any(vars(args).values()): parser.print_help()


if __name__ == '__main__':
    main()
