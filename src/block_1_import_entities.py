#!/usr/bin/env python3
"""Blocco 1: importa club, rose e identità giocatori della Serie A.
Compatibile con schema.sql inizializzato da pipeline.py.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "database-fantacalcio.sqlite"))
SEED_PATH = ROOT / "data" / "serie_a" / "block_1_club_seasons.csv"
API_BASE = "https://api.football-data.org/v4"
SEASONS = {"2021-22": 2021, "2022-23": 2022, "2023-24": 2023, "2024-25": 2024, "2025-26": 2025}


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS club_seasons(
      club_id TEXT NOT NULL,
      season_id INTEGER NOT NULL,
      competition_id INTEGER NOT NULL,
      source TEXT NOT NULL,
      PRIMARY KEY(club_id,season_id,competition_id),
      FOREIGN KEY(club_id) REFERENCES clubs(club_id),
      FOREIGN KEY(season_id) REFERENCES seasons(season_id),
      FOREIGN KEY(competition_id) REFERENCES competitions(competition_id)
    );
    CREATE TABLE IF NOT EXISTS player_external_ids(
      player_id TEXT NOT NULL,
      provider TEXT NOT NULL,
      external_id TEXT NOT NULL,
      PRIMARY KEY(provider,external_id),
      FOREIGN KEY(player_id) REFERENCES players(player_id)
    );
    """)
    return con


def ensure_reference_data(con: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    con.execute(
        "INSERT OR IGNORE INTO competitions(name,country,level,external_ids_json) VALUES (?,?,?,?)",
        ("Serie A", "Italy", 1, json.dumps({"football_data":"SA","api_football":135})),
    )
    competition_id = con.execute(
        "SELECT competition_id FROM competitions WHERE name='Serie A' AND country='Italy'"
    ).fetchone()[0]
    season_ids: dict[str, int] = {}
    for label, year in SEASONS.items():
        con.execute(
            "INSERT OR IGNORE INTO seasons(label,start_date,end_date,complete) VALUES (?,?,?,?)",
            (label, f"{year}-07-01", f"{year+1}-06-30", 1 if label != "2025-26" else 0),
        )
        season_ids[label] = con.execute("SELECT season_id FROM seasons WHERE label=?", (label,)).fetchone()[0]
    con.commit()
    return competition_id, season_ids


def import_seed(con: sqlite3.Connection, competition_id: int, season_ids: dict[str, int]) -> None:
    with SEED_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            club_id = stable_id("CLB", "seed", row["club_name"])
            con.execute(
                """INSERT OR IGNORE INTO clubs
                (club_id,official_name,short_name,country,external_ids_json)
                VALUES (?,?,?,?,?)""",
                (club_id,row["club_name"],row["short_name"],row["country"],json.dumps({"seed": row["club_name"]})),
            )
            con.execute(
                "INSERT OR IGNORE INTO club_seasons(club_id,season_id,competition_id,source) VALUES (?,?,?,?)",
                (club_id,season_ids[row["season"]],competition_id,"verified_public_seed"),
            )
    con.commit()


def fetch_json(path: str, key: str) -> dict:
    response = requests.get(API_BASE + path, headers={"X-Auth-Token": key}, timeout=30)
    response.raise_for_status()
    return response.json()


def import_squads(con: sqlite3.Connection, key: str, competition_id: int, season_ids: dict[str, int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for label, start_year in SEASONS.items():
        try:
            payload = fetch_json(f"/competitions/SA/teams?season={start_year}", key)
        except requests.HTTPError as exc:
            print(f"{label}: non disponibile nel piano API ({exc})")
            continue
        for team in payload.get("teams", []):
            ext_team = str(team.get("id"))
            name = team.get("name") or team.get("shortName") or "Unknown"
            club_id = stable_id("CLB", "football-data", ext_team)
            con.execute(
                """INSERT INTO clubs
                (club_id,official_name,short_name,country,founded_year,stadium_name,crest_url,external_ids_json,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(club_id) DO UPDATE SET
                  official_name=excluded.official_name,
                  short_name=excluded.short_name,
                  founded_year=excluded.founded_year,
                  stadium_name=excluded.stadium_name,
                  crest_url=excluded.crest_url,
                  external_ids_json=excluded.external_ids_json,
                  updated_at=excluded.updated_at""",
                (club_id,name,team.get("shortName"),"Italy",team.get("founded"),team.get("venue"),team.get("crest"),json.dumps({"football_data": ext_team}),now),
            )
            con.execute(
                "INSERT OR IGNORE INTO club_seasons(club_id,season_id,competition_id,source) VALUES (?,?,?,?)",
                (club_id,season_ids[label],competition_id,"football-data.org"),
            )
            for person in team.get("squad") or []:
                ext_player = str(person["id"])
                player_id = stable_id("PLY", "football-data", ext_player)
                full_name = person.get("name") or "Unknown"
                parts = full_name.split(maxsplit=1)
                con.execute(
                    """INSERT INTO players
                    (player_id,first_name,last_name,full_name,birth_date,nationality,primary_position,external_ids_json,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(player_id) DO UPDATE SET
                      first_name=excluded.first_name,
                      last_name=excluded.last_name,
                      full_name=excluded.full_name,
                      birth_date=excluded.birth_date,
                      nationality=excluded.nationality,
                      primary_position=excluded.primary_position,
                      external_ids_json=excluded.external_ids_json,
                      updated_at=excluded.updated_at""",
                    (player_id,parts[0],parts[1] if len(parts)>1 else None,full_name,person.get("dateOfBirth"),person.get("nationality"),person.get("position"),json.dumps({"football_data": ext_player}),now),
                )
                con.execute("INSERT OR IGNORE INTO player_external_ids VALUES (?,?,?)", (player_id,"football-data.org",ext_player))
                con.execute(
                    """INSERT OR IGNORE INTO player_seasons
                    (player_id,season_id,club_id,competition_id,shirt_number)
                    VALUES (?,?,?,?,?)""",
                    (player_id,season_ids[label],club_id,competition_id,person.get("shirtNumber")),
                )
        con.commit()
        print(f"Completata importazione disponibile: {label}")
        time.sleep(6.2)


def report(con: sqlite3.Connection) -> None:
    for table in ("seasons","clubs","club_seasons","players","player_seasons"):
        print(f"{table}: {con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    con = connect()
    competition_id, season_ids = ensure_reference_data(con)
    import_seed(con, competition_id, season_ids)
    key = os.getenv("FOOTBALL_DATA_API_KEY")
    if key and key != "insert_key_here":
        import_squads(con, key, competition_id, season_ids)
    else:
        print("FOOTBALL_DATA_API_KEY assente: importati solo club e stagioni verificati.")
    report(con)
    con.close()


if __name__ == "__main__":
    main()
