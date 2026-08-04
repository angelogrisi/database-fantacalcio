#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "database-fantacalcio.sqlite"))
OUT_PATH = Path(os.getenv("WEB_DATA_PATH", ROOT / "pages" / "data" / "database.json"))


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def col(alias: str, name: str, available: dict[str, set[str]], fallback: str = "NULL") -> str:
    return f"{alias}.{name}" if name in available.get(alias, set()) else fallback


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database non trovato: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tables = {
        "p": "players",
        "ps": "player_seasons",
        "s": "seasons",
        "c": "clubs",
        "st": "player_season_stats",
        "fp": "fantasy_player_season",
        "am": "player_advanced_season_metrics",
        "pi": "proprietary_player_indexes",
    }
    available = {alias: columns(conn, table) for alias, table in tables.items()}

    if not available["p"]:
        raise SystemExit("Tabella players non trovata")

    joins: list[str] = []
    if available["ps"]:
        joins.append("LEFT JOIN player_seasons ps ON ps.player_id = p.player_id")
    if available["s"] and available["ps"]:
        joins.append("LEFT JOIN seasons s ON s.season_id = ps.season_id")
    if available["c"] and available["ps"]:
        joins.append("LEFT JOIN clubs c ON c.club_id = ps.club_id")
    if available["st"] and available["ps"]:
        joins.append("LEFT JOIN player_season_stats st ON st.player_id = ps.player_id AND st.season_id = ps.season_id AND st.club_id = ps.club_id")
    if available["fp"] and available["ps"]:
        joins.append("LEFT JOIN fantasy_player_season fp ON fp.player_id = ps.player_id AND fp.season_id = ps.season_id AND fp.club_id = ps.club_id")
    if available["am"] and available["ps"]:
        joins.append("LEFT JOIN player_advanced_season_metrics am ON am.player_id = ps.player_id AND am.season_id = ps.season_id AND am.club_id = ps.club_id")
    if available["pi"] and available["ps"]:
        joins.append("LEFT JOIN proprietary_player_indexes pi ON pi.player_id = ps.player_id AND pi.season_id = ps.season_id AND pi.club_id = ps.club_id")

    full_name = col("p", "full_name", available, "''")
    position = col("p", "primary_position", available, col("p", "position", available))
    appearances = col("st", "appearances", available, col("fp", "appearances_with_rating", available, "0"))

    select = [
        f"{col('p', 'player_id', available)} AS player_id",
        f"{full_name} AS name",
        f"{col('p', 'nationality', available)} AS nationality",
        f"{position} AS position",
        f"{col('s', 'label', available)} AS season",
        f"{col('c', 'official_name', available)} AS club",
        f"{col('fp', 'fantasy_role', available)} AS fantasy_role",
        f"{appearances} AS appearances",
        f"{col('st', 'minutes', available, '0')} AS minutes",
        f"{col('st', 'goals', available, col('fp', 'goals', available, '0'))} AS goals",
        f"{col('st', 'assists', available, col('fp', 'assists', available, '0'))} AS assists",
        f"{col('fp', 'average_rating', available)} AS average_rating",
        f"{col('fp', 'fantasy_average', available)} AS fantasy_average",
        f"{col('fp', 'auction_value_index', available, col('pi', 'auction_value_index', available))} AS auction_value",
        f"{col('am', 'xg', available)} AS xg",
        f"{col('am', 'xa', available)} AS xa",
        f"{col('pi', 'form_index', available)} AS form_index",
        f"{col('pi', 'reliability_index', available)} AS reliability_index",
        f"{col('pi', 'continuity_index', available)} AS continuity_index",
        f"{col('pi', 'bonus_index', available)} AS bonus_index",
        f"{col('pi', 'injury_risk', available)} AS injury_risk",
    ]

    sql = "SELECT " + ", ".join(select) + " FROM players p " + " ".join(joins)
    rows = [dict(row) for row in conn.execute(sql)]

    unique: dict[tuple[object, object, object], dict] = {}
    for row in rows:
        unique[(row.get("player_id"), row.get("season"), row.get("club"))] = row
    players = list(unique.values())

    summary = {
        "players": conn.execute("SELECT COUNT(*) FROM players").fetchone()[0],
        "clubs": conn.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] if table_exists(conn, "clubs") else 0,
        "matches": conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] if table_exists(conn, "matches") else 0,
        "records": len(players),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"summary": summary, "players": players}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Esportati {len(players)} record in {OUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
