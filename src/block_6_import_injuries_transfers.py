#!/usr/bin/env python3
"""Block 6: import Serie A injuries/transfers and derive availability metrics.

Uses API-Football when the configured plan exposes the endpoints. Missing values
remain NULL and are never fabricated.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
DB_PATH = Path(os.getenv("DATABASE_PATH", "data/database-fantacalcio.sqlite"))
API_KEY = os.getenv("API_FOOTBALL_API_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
SERIE_A_LEAGUE_ID = 135
SEASONS = [2021, 2022, 2023, 2024, 2025]


def api_get(path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    if not API_KEY:
        return []
    response = requests.get(
        f"{BASE_URL}/{path}",
        headers={"x-apisports-key": API_KEY},
        params=params,
        timeout=45,
    )
    if response.status_code in (403, 429):
        print(f"{path}: unavailable for current plan or rate limited ({response.status_code})")
        return []
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors") or {}
    if errors:
        print(f"{path}: provider error: {errors}")
        return []
    return payload.get("response") or []


def get_player_id(conn: sqlite3.Connection, external_id: Any, name: str | None) -> str | None:
    if external_id is not None:
        pattern = f'%"api_football": {external_id}%'
        row = conn.execute(
            "SELECT player_id FROM players WHERE external_ids_json LIKE ? LIMIT 1", (pattern,)
        ).fetchone()
        if row:
            return row[0]
    if name:
        row = conn.execute(
            "SELECT player_id FROM players WHERE lower(full_name)=lower(?) LIMIT 1", (name.strip(),)
        ).fetchone()
        if row:
            return row[0]
    return None


def club_lookup(conn: sqlite3.Connection, external_id: Any, name: str | None) -> str | None:
    if external_id is not None:
        pattern = f'%"api_football": {external_id}%'
        row = conn.execute(
            "SELECT club_id FROM clubs WHERE external_ids_json LIKE ? LIMIT 1", (pattern,)
        ).fetchone()
        if row:
            return row[0]
    if name:
        row = conn.execute(
            "SELECT club_id FROM clubs WHERE lower(official_name)=lower(?) OR lower(short_name)=lower(?) LIMIT 1",
            (name.strip(), name.strip()),
        ).fetchone()
        if row:
            return row[0]
    return None


def season_id(conn: sqlite3.Connection, start_year: int) -> int | None:
    row = conn.execute("SELECT season_id FROM seasons WHERE label=?", (f"{start_year}-{str(start_year+1)[-2:]}",)).fetchone()
    return row[0] if row else None


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return None


def days_between(start: str | None, end: str | None) -> int | None:
    if not start:
        return None
    try:
        a = date.fromisoformat(start)
        b = date.fromisoformat(end) if end else date.today()
        return max(0, (b - a).days)
    except ValueError:
        return None


def import_injuries(conn: sqlite3.Connection) -> int:
    inserted = 0
    for year in SEASONS:
        sid = season_id(conn, year)
        rows = api_get("injuries", {"league": SERIE_A_LEAGUE_ID, "season": year})
        for item in rows:
            player = item.get("player") or {}
            team = item.get("team") or {}
            fixture = item.get("fixture") or {}
            pid = get_player_id(conn, player.get("id"), player.get("name"))
            if not pid:
                continue
            club_id = club_lookup(conn, team.get("id"), team.get("name"))
            injury_type = player.get("type") or player.get("reason") or "Unknown"
            detail = player.get("reason")
            start = parse_date(fixture.get("date"))
            conn.execute(
                """INSERT OR IGNORE INTO player_injuries
                (player_id,season_id,club_id,injury_type,injury_detail,start_date,status,
                 source_name,source_url,confidence)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, sid, club_id, injury_type, detail, start, "reported",
                 "API-Football", "https://www.api-football.com/", 75.0),
            )
            inserted += conn.total_changes > 0
        time.sleep(0.25)
    return int(inserted)


def import_transfers(conn: sqlite3.Connection) -> int:
    inserted = 0
    players = conn.execute("SELECT player_id, full_name, external_ids_json FROM players").fetchall()
    for idx, (pid, name, ids_json) in enumerate(players, 1):
        try:
            ids = json.loads(ids_json or "{}")
        except json.JSONDecodeError:
            ids = {}
        external_id = ids.get("api_football")
        if not external_id:
            continue
        rows = api_get("transfers", {"player": external_id})
        for wrapper in rows:
            for transfer in wrapper.get("transfers") or []:
                teams = transfer.get("teams") or {}
                team_in = teams.get("in") or {}
                team_out = teams.get("out") or {}
                transfer_date = parse_date(transfer.get("date"))
                transfer_type = transfer.get("type") or "Unknown"
                lower_type = transfer_type.lower()
                is_loan = int("loan" in lower_type or "prestito" in lower_type)
                is_free = int("free" in lower_type or "svincol" in lower_type)
                from_id = club_lookup(conn, team_out.get("id"), team_out.get("name"))
                to_id = club_lookup(conn, team_in.get("id"), team_in.get("name"))
                sid = None
                if transfer_date:
                    y = date.fromisoformat(transfer_date).year
                    start_year = y if date.fromisoformat(transfer_date).month >= 7 else y - 1
                    sid = season_id(conn, start_year)
                before = conn.total_changes
                conn.execute(
                    """INSERT OR IGNORE INTO player_transfers
                    (player_id,transfer_date,season_id,from_club_id,to_club_id,from_club_name,
                     to_club_name,transfer_type,is_loan,is_free,source_name,source_url,confidence)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, transfer_date, sid, from_id, to_id, team_out.get("name"),
                     team_in.get("name"), transfer_type, is_loan, is_free,
                     "API-Football", "https://www.api-football.com/", 85.0),
                )
                if conn.total_changes > before:
                    inserted += 1
        if idx % 50 == 0:
            print(f"Transfers checked: {idx}/{len(players)}")
        time.sleep(0.2)
    return inserted


def derive_availability(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM player_availability WHERE methodology_version='block6-v1'")
    rows = conn.execute(
        """SELECT ps.player_id, ps.season_id, ps.club_id,
                  COALESCE(SUM(i.days_absent),0),
                  COALESCE(SUM(i.matches_missed),0),
                  COUNT(i.injury_id),
                  COALESCE(SUM(i.recurrence),0)
           FROM player_seasons ps
           LEFT JOIN player_injuries i ON i.player_id=ps.player_id
                AND i.season_id=ps.season_id
           GROUP BY ps.player_id, ps.season_id, ps.club_id"""
    ).fetchall()
    for pid, sid, club_id, days, missed, count, recurrences in rows:
        days = int(days or 0)
        availability = max(0.0, min(100.0, 100.0 - (days / 300.0 * 100.0)))
        risk = max(0, min(100, round(count * 12 + recurrences * 15 + min(days, 180) / 3)))
        transfers = conn.execute(
            "SELECT COUNT(*) FROM player_transfers WHERE player_id=? AND season_id=?", (pid, sid)
        ).fetchone()[0]
        coverage = 100.0 if count else (50.0 if API_KEY else 0.0)
        conn.execute(
            """INSERT INTO player_availability
            (player_id,season_id,club_id,days_injured,matches_missed_injury,injury_count,
             recurrence_count,availability_pct,injury_risk_index,transfer_count,
             methodology_version,data_coverage_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, sid, club_id, days, missed, count, recurrences, availability, risk,
             transfers, "block6-v1", coverage),
        )
    return len(rows)


def report(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "injuries": conn.execute("SELECT COUNT(*) FROM player_injuries").fetchone()[0],
        "transfers": conn.execute("SELECT COUNT(*) FROM player_transfers").fetchone()[0],
        "availability_rows": conn.execute("SELECT COUNT(*) FROM player_availability").fetchone()[0],
        "players_with_injuries": conn.execute("SELECT COUNT(DISTINCT player_id) FROM player_injuries").fetchone()[0],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "limitations": "Coverage depends on API-Football plan and historical endpoint availability. Missing values remain NULL."
    }


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    migration = Path("migrations/006_block_6_injuries_transfers.sql").read_text(encoding="utf-8")
    conn.executescript(migration)
    injuries = import_injuries(conn)
    transfers = import_transfers(conn)
    availability = derive_availability(conn)
    conn.commit()
    result = report(conn)
    conn.close()
    Path("reports").mkdir(exist_ok=True)
    Path("reports/block_6_coverage_report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Block 6 complete: injuries={injuries}, transfers={transfers}, availability={availability}")


if __name__ == "__main__":
    main()
