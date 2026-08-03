#!/usr/bin/env python3
"""Importa partite e risultati della Serie A per le stagioni configurate.

Fonti:
- football-data.org: calendario, risultati, giornata, arbitri e punteggi.
- API-Football: eventi, formazioni e sostituzioni quando disponibili.

Le chiavi devono essere lette da .env e non salvate nel repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SEASONS = {
    "2021-22": 2021,
    "2022-23": 2022,
    "2023-24": 2023,
    "2024-25": 2024,
    "2025-26": 2025,
}
FD_BASE = "https://api.football-data.org/v4"
AF_BASE = "https://v3.football.api-sports.io"


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_migration(conn: sqlite3.Connection) -> None:
    migration = (ROOT / "migrations" / "002_block_2_matches.sql").read_text(encoding="utf-8")
    for statement in migration.split(";"):
        sql = statement.strip()
        if not sql:
            continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    conn.commit()


def ensure_reference_data(conn: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    conn.execute(
        "INSERT OR IGNORE INTO competitions(name,country,level,external_ids_json) VALUES (?,?,?,?)",
        ("Serie A", "Italy", 1, json.dumps({"football_data":"SA","api_football":135})),
    )
    competition_id = conn.execute(
        "SELECT competition_id FROM competitions WHERE name='Serie A' AND country='Italy'"
    ).fetchone()[0]
    season_ids: dict[str, int] = {}
    for label, year in SEASONS.items():
        conn.execute(
            "INSERT OR IGNORE INTO seasons(label,start_date,end_date,complete) VALUES (?,?,?,?)",
            (label, f"{year}-07-01", f"{year+1}-06-30", 1 if label != "2025-26" else 0),
        )
        season_ids[label] = conn.execute("SELECT season_id FROM seasons WHERE label=?", (label,)).fetchone()[0]
    conn.commit()
    return competition_id, season_ids


def source_id(conn: sqlite3.Connection, name: str, base_url: str, access_type: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO sources(name,base_url,license_notes,access_type) VALUES (?,?,?,?)",
        (name, base_url, "Use subject to provider terms", access_type),
    )
    conn.commit()
    return conn.execute("SELECT source_id FROM sources WHERE name=?", (name,)).fetchone()[0]


def upsert_club(conn: sqlite3.Connection, provider: str, data: dict[str, Any]) -> str:
    external = str(data.get("id"))
    existing = conn.execute(
        "SELECT club_id FROM clubs WHERE json_extract(external_ids_json, ?) = ?",
        (f"$.{provider}", external),
    ).fetchone()
    if existing:
        return existing[0]
    club_id = stable_id("CLB", provider, external, data.get("name"))
    conn.execute(
        """INSERT OR IGNORE INTO clubs
        (club_id,official_name,short_name,country,crest_url,external_ids_json)
        VALUES (?,?,?,?,?,?)""",
        (
            club_id,
            data.get("name") or data.get("shortName") or "Unknown",
            data.get("shortName") or data.get("tla"),
            "Italy",
            data.get("crest") or data.get("logo"),
            json.dumps({provider: external}),
        ),
    )
    conn.commit()
    return club_id


def fd_get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = requests.get(
        f"{FD_BASE}{path}", headers={"X-Auth-Token": token}, params=params, timeout=45
    )
    if r.status_code == 429:
        time.sleep(65)
        return fd_get(path, token, params)
    r.raise_for_status()
    return r.json()


def import_football_data(conn: sqlite3.Connection, token: str, competition_id: int, season_ids: dict[str,int]) -> dict[str,int]:
    src = source_id(conn, "football-data.org", FD_BASE, "api")
    counts = {"matches":0,"referees":0}
    for label, year in SEASONS.items():
        try:
            payload = fd_get("/competitions/SA/matches", token, {"season": year})
        except requests.HTTPError as exc:
            print(f"[football-data] {label}: non disponibile ({exc})")
            continue
        for m in payload.get("matches", []):
            home_id = upsert_club(conn, "football_data", m.get("homeTeam", {}))
            away_id = upsert_club(conn, "football_data", m.get("awayTeam", {}))
            ext_id = str(m.get("id"))
            match_id = stable_id("MAT", "football_data", ext_id)
            score = m.get("score") or {}
            full = score.get("fullTime") or {}
            conn.execute(
                """INSERT INTO matches
                (match_id,season_id,competition_id,match_date,utc_date,stage,matchday,
                 home_club_id,away_club_id,home_score,away_score,status,external_ids_json,
                 winner,duration,last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                 match_date=excluded.match_date, utc_date=excluded.utc_date,
                 matchday=excluded.matchday, home_score=excluded.home_score,
                 away_score=excluded.away_score, status=excluded.status,
                 winner=excluded.winner, duration=excluded.duration,
                 last_updated=excluded.last_updated""",
                (
                    match_id, season_ids[label], competition_id,
                    (m.get("utcDate") or "")[:10], m.get("utcDate"), m.get("stage"),
                    m.get("matchday"), home_id, away_id, full.get("home"), full.get("away"),
                    m.get("status"), json.dumps({"football_data":ext_id}),
                    score.get("winner"), score.get("duration"), m.get("lastUpdated"),
                ),
            )
            half = score.get("halfTime") or {}; extra = score.get("extraTime") or {}; pens = score.get("penalties") or {}
            conn.execute(
                """INSERT INTO match_scores(match_id,halftime_home,halftime_away,fulltime_home,fulltime_away,
                extratime_home,extratime_away,penalties_home,penalties_away)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET
                halftime_home=excluded.halftime_home,halftime_away=excluded.halftime_away,
                fulltime_home=excluded.fulltime_home,fulltime_away=excluded.fulltime_away,
                extratime_home=excluded.extratime_home,extratime_away=excluded.extratime_away,
                penalties_home=excluded.penalties_home,penalties_away=excluded.penalties_away""",
                (match_id,half.get("home"),half.get("away"),full.get("home"),full.get("away"),
                 extra.get("home"),extra.get("away"),pens.get("home"),pens.get("away")),
            )
            for ref in m.get("referees") or []:
                conn.execute(
                    """INSERT OR IGNORE INTO match_referees
                    (match_id,referee_name,referee_type,nationality,external_id) VALUES (?,?,?,?,?)""",
                    (match_id,ref.get("name"),ref.get("type"),ref.get("nationality"),str(ref.get("id") or "")),
                )
                counts["referees"] += 1
            conn.execute(
                """INSERT INTO provenance(entity_type,entity_key,field_name,source_id,source_url,
                acquired_at,value_type,confidence,transformation_rule) VALUES (?,?,?,?,?,?,?,?,?)""",
                ("match",match_id,"match_record",src,f"{FD_BASE}/matches/{ext_id}",now_iso(),"observed",95,None),
            )
            counts["matches"] += 1
        conn.commit()
        print(f"[football-data] {label}: {len(payload.get('matches', []))} partite")
    return counts


def api_get(path: str, token: str, params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(f"{AF_BASE}{path}", headers={"x-apisports-key":token}, params=params, timeout=45)
    if r.status_code == 429:
        time.sleep(65)
        return api_get(path, token, params)
    r.raise_for_status()
    return r.json()


def import_api_football_events(conn: sqlite3.Connection, token: str) -> dict[str,int]:
    """Arricchisce solo le partite già presenti. Rispetta i limiti del piano gratuito."""
    counts = {"events":0,"lineups":0}
    src = source_id(conn, "API-Football", AF_BASE, "api")
    rows = conn.execute("SELECT match_id, external_ids_json FROM matches ORDER BY match_date DESC").fetchall()
    for row in rows:
        ext = json.loads(row["external_ids_json"] or "{}")
        fixture_id = ext.get("api_football")
        if not fixture_id:
            continue
        for path, kind in (("/fixtures/events","events"),("/fixtures/lineups","lineups")):
            try:
                data = api_get(path, token, {"fixture":fixture_id}).get("response") or []
            except requests.HTTPError as exc:
                print(f"[api-football] fixture {fixture_id}: {exc}")
                break
            # L'adattatore conserva il payload grezzo nella provenienza finché i PlayerID non sono mappati.
            conn.execute(
                """INSERT INTO provenance(entity_type,entity_key,field_name,source_id,source_url,
                acquired_at,value_type,confidence,transformation_rule) VALUES (?,?,?,?,?,?,?,?,?)""",
                ("match",row["match_id"],f"api_football_{kind}",src,
                 f"{AF_BASE}{path}?fixture={fixture_id}",now_iso(),"observed",90,
                 json.dumps(data, ensure_ascii=False)),
            )
            counts[kind] += len(data)
        conn.commit()
    return counts


def validate(conn: sqlite3.Connection) -> None:
    checks = {
        "match senza squadre": "SELECT match_id FROM matches WHERE home_club_id IS NULL OR away_club_id IS NULL",
        "stessa squadra casa/trasferta": "SELECT match_id FROM matches WHERE home_club_id=away_club_id",
        "punteggi negativi": "SELECT match_id FROM matches WHERE home_score<0 OR away_score<0",
        "duplicati provider": "SELECT json_extract(external_ids_json,'$.football_data'),COUNT(*) FROM matches WHERE json_extract(external_ids_json,'$.football_data') IS NOT NULL GROUP BY 1 HAVING COUNT(*)>1",
    }
    for code, sql in checks.items():
        rows = conn.execute(sql).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO quality_issues(severity,entity_type,entity_key,rule_code,description) VALUES (?,?,?,?,?)",
                ("error","match",str(row[0]),code,code),
            )
        print(f"[validate] {code}: {len(rows)}")
    conn.commit()


def main() -> None:
    load_dotenv(ROOT / ".env")
    db_path = os.getenv("DATABASE_PATH", str(ROOT / "data" / "database-fantacalcio.sqlite"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    apply_migration(conn)
    competition_id, season_ids = ensure_reference_data(conn)
    result: dict[str,Any] = {}
    fd_token = os.getenv("FOOTBALL_DATA_API_KEY")
    if fd_token:
        result["football_data"] = import_football_data(conn, fd_token, competition_id, season_ids)
    else:
        print("FOOTBALL_DATA_API_KEY assente: calendario non importato")
    af_token = os.getenv("API_FOOTBALL_API_KEY")
    if af_token:
        result["api_football"] = import_api_football_events(conn, af_token)
    validate(conn)
    totals = {
        "matches": conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
        "scores": conn.execute("SELECT COUNT(*) FROM match_scores").fetchone()[0],
        "referees": conn.execute("SELECT COUNT(*) FROM match_referees").fetchone()[0],
        "quality_issues": conn.execute("SELECT COUNT(*) FROM quality_issues WHERE resolved=0").fetchone()[0],
    }
    conn.close()
    print(json.dumps({"imported":result,"database_totals":totals}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
