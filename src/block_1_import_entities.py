#!/usr/bin/env python3
"""Blocco 1: importa club, rose e identità giocatori della Serie A.

Fonti:
- seed verificato data/serie_a/block_1_club_seasons.csv
- football-data.org API v4 per rose disponibili

Le chiavi restano nel file locale .env. I PlayerID sono UUIDv5 permanenti.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "database-fantacalcio.sqlite"))
SEED_PATH = ROOT / "data" / "serie_a" / "block_1_club_seasons.csv"
API_BASE = "https://api.football-data.org/v4"
NAMESPACE = uuid.UUID("8f09a5a6-5e89-4c5f-b5d7-a17027a63ab9")
SEASON_START = {"2021-22": 2021, "2022-23": 2022, "2023-24": 2023, "2024-25": 2024, "2025-26": 2025}


def uid(kind: str, canonical: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{canonical.strip().casefold()}"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS competitions(
      competition_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, country TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS seasons(
      season_id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE, start_year INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS clubs(
      club_id TEXT PRIMARY KEY, official_name TEXT NOT NULL UNIQUE, short_name TEXT,
      country TEXT, crest_url TEXT, founded INTEGER, venue TEXT
    );
    CREATE TABLE IF NOT EXISTS club_seasons(
      club_id TEXT NOT NULL, season_id TEXT NOT NULL, competition_id TEXT NOT NULL,
      source TEXT NOT NULL, PRIMARY KEY(club_id,season_id,competition_id),
      FOREIGN KEY(club_id) REFERENCES clubs(club_id),
      FOREIGN KEY(season_id) REFERENCES seasons(season_id),
      FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
    );
    CREATE TABLE IF NOT EXISTS players(
      player_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, first_name TEXT, last_name TEXT,
      birth_date TEXT, nationality TEXT, position TEXT, shirt_number INTEGER,
      last_updated TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_external_ids(
      player_id TEXT NOT NULL, provider TEXT NOT NULL, external_id TEXT NOT NULL,
      PRIMARY KEY(provider,external_id), FOREIGN KEY(player_id) REFERENCES players(player_id)
    );
    CREATE TABLE IF NOT EXISTS player_club_seasons(
      player_id TEXT NOT NULL, club_id TEXT NOT NULL, season_id TEXT NOT NULL,
      competition_id TEXT NOT NULL, role TEXT, shirt_number INTEGER, source TEXT NOT NULL,
      PRIMARY KEY(player_id,club_id,season_id,competition_id),
      FOREIGN KEY(player_id) REFERENCES players(player_id),
      FOREIGN KEY(club_id) REFERENCES clubs(club_id)
    );
    CREATE TABLE IF NOT EXISTS provenance(
      entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, provider TEXT NOT NULL,
      acquired_at TEXT NOT NULL, payload_hash TEXT, PRIMARY KEY(entity_type,entity_id,provider)
    );
    """)
    return con


def import_seed(con: sqlite3.Connection) -> None:
    competition_id = uid("competition", "Serie A Italy")
    con.execute("INSERT OR IGNORE INTO competitions VALUES (?,?,?)", (competition_id, "Serie A", "Italy"))
    with SEED_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            season_id = uid("season", row["season"])
            club_id = uid("club", row["club_name"])
            con.execute("INSERT OR IGNORE INTO seasons VALUES (?,?,?)", (season_id, row["season"], SEASON_START[row["season"]]))
            con.execute("INSERT OR IGNORE INTO clubs(club_id,official_name,short_name,country) VALUES (?,?,?,?)",
                        (club_id,row["club_name"],row["short_name"],row["country"]))
            con.execute("INSERT OR IGNORE INTO club_seasons VALUES (?,?,?,?)",
                        (club_id,season_id,competition_id,"verified_public_seed"))
    con.commit()


def fetch_json(path: str, key: str) -> dict:
    r = requests.get(API_BASE + path, headers={"X-Auth-Token": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def import_squads(con: sqlite3.Connection, key: str) -> None:
    competition_id = uid("competition", "Serie A Italy")
    now = datetime.now(timezone.utc).isoformat()
    for label, start_year in SEASON_START.items():
        season_id = uid("season", label)
        try:
            payload = fetch_json(f"/competitions/SA/teams?season={start_year}", key)
        except requests.HTTPError as exc:
            print(f"{label}: non disponibile nel piano API ({exc})")
            continue
        for team in payload.get("teams", []):
            name = team.get("name") or team.get("shortName")
            club_id = uid("club", name)
            con.execute("""INSERT INTO clubs(club_id,official_name,short_name,country,crest_url,founded,venue)
                           VALUES(?,?,?,?,?,?,?) ON CONFLICT(club_id) DO UPDATE SET
                           short_name=excluded.short_name,crest_url=excluded.crest_url,
                           founded=excluded.founded,venue=excluded.venue""",
                        (club_id,name,team.get("shortName"),"Italy",team.get("crest"),team.get("founded"),team.get("venue")))
            con.execute("INSERT OR IGNORE INTO club_seasons VALUES (?,?,?,?)",
                        (club_id,season_id,competition_id,"football-data.org"))
            for person in team.get("squad") or []:
                ext = str(person["id"])
                canonical = f"football-data:{ext}"
                player_id = uid("player", canonical)
                full = person.get("name") or "Unknown"
                parts = full.split(maxsplit=1)
                con.execute("""INSERT INTO players(player_id,full_name,first_name,last_name,birth_date,nationality,position,shirt_number,last_updated)
                               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(player_id) DO UPDATE SET
                               full_name=excluded.full_name,birth_date=excluded.birth_date,
                               nationality=excluded.nationality,position=excluded.position,
                               shirt_number=excluded.shirt_number,last_updated=excluded.last_updated""",
                            (player_id,full,parts[0],parts[1] if len(parts)>1 else None,person.get("dateOfBirth"),
                             person.get("nationality"),person.get("position"),person.get("shirtNumber"),now))
                con.execute("INSERT OR IGNORE INTO player_external_ids VALUES (?,?,?)", (player_id,"football-data.org",ext))
                con.execute("INSERT OR REPLACE INTO player_club_seasons VALUES (?,?,?,?,?,?,?)",
                            (player_id,club_id,season_id,competition_id,person.get("position"),person.get("shirtNumber"),"football-data.org"))
                digest = hashlib.sha256(repr(sorted(person.items())).encode()).hexdigest()
                con.execute("INSERT OR REPLACE INTO provenance VALUES (?,?,?,?,?)",
                            ("player",player_id,"football-data.org",now,digest))
        con.commit()
        print(f"Completata importazione disponibile: {label}")
        time.sleep(6.2)


def report(con: sqlite3.Connection) -> None:
    for table in ("seasons","clubs","club_seasons","players","player_club_seasons"):
        print(f"{table}: {con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    con = connect()
    import_seed(con)
    key = os.getenv("FOOTBALL_DATA_API_KEY")
    if key and key != "insert_key_here":
        import_squads(con,key)
    else:
        print("FOOTBALL_DATA_API_KEY assente: importati solo club e stagioni verificati.")
    report(con)
    con.close()

if __name__ == "__main__":
    main()
