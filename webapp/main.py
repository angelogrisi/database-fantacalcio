from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", "data/database-fantacalcio.sqlite"))

app = FastAPI(title="Database Fantacalcio", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Database non trovato: {DB_PATH}")
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "database": str(DB_PATH), "database_exists": DB_PATH.exists()}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    with connect() as connection:
        counts: dict[str, int] = {}
        for table in ("players", "clubs", "matches", "player_season_stats"):
            counts[table] = (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if table_exists(connection, table)
                else 0
            )
        seasons = []
        if table_exists(connection, "seasons"):
            seasons = [dict(row) for row in connection.execute(
                "SELECT season_id, label FROM seasons ORDER BY label DESC"
            ).fetchall()]
        clubs = []
        if table_exists(connection, "clubs"):
            clubs = [dict(row) for row in connection.execute(
                "SELECT club_id, official_name, short_name FROM clubs ORDER BY official_name"
            ).fetchall()]
        return {"counts": counts, "seasons": seasons, "clubs": clubs}


@app.get("/api/players")
def list_players(
    q: str = Query("", max_length=80),
    season_id: int | None = None,
    club_id: str | None = None,
    role: str | None = None,
    sort: str = Query("name", pattern="^(name|fantamedia|goals|assists|value)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    with connect() as connection:
        has_fantasy = table_exists(connection, "fantasy_player_season")
        has_indexes = table_exists(connection, "player_proprietary_indexes")

        fantasy_join = ""
        fantasy_fields = "NULL AS fantamedia, NULL AS media_voto, NULL AS auction_value_index"
        if has_fantasy:
            fantasy_join = """
                LEFT JOIN fantasy_player_season fps
                  ON fps.player_id = p.player_id
                 AND fps.season_id = ps.season_id
                 AND fps.club_id = ps.club_id
            """
            fantasy_fields = "fps.fantamedia, fps.media_voto, fps.auction_value_index"

        index_join = ""
        index_fields = "NULL AS form_index, NULL AS reliability_index"
        if has_indexes:
            index_join = """
                LEFT JOIN player_proprietary_indexes ppi
                  ON ppi.player_id = p.player_id
                 AND ppi.season_id = ps.season_id
            """
            index_fields = "ppi.form_index, ppi.reliability_index"

        where = ["1=1"]
        params: list[Any] = []
        if q.strip():
            where.append("(LOWER(p.full_name) LIKE LOWER(?) OR LOWER(COALESCE(p.known_as,'')) LIKE LOWER(?))")
            term = f"%{q.strip()}%"
            params.extend([term, term])
        if season_id is not None:
            where.append("ps.season_id = ?")
            params.append(season_id)
        if club_id:
            where.append("ps.club_id = ?")
            params.append(club_id)
        if role:
            where.append("UPPER(COALESCE(p.primary_position,'')) LIKE ?")
            params.append(f"%{role.upper()}%")

        order_map = {
            "name": "p.full_name COLLATE NOCASE ASC",
            "fantamedia": "fantamedia DESC NULLS LAST",
            "goals": "COALESCE(stats.goals,0) DESC",
            "assists": "COALESCE(stats.assists,0) DESC",
            "value": "auction_value_index DESC NULLS LAST",
        }

        sql = f"""
            SELECT
                p.player_id,
                p.full_name,
                p.known_as,
                p.photo_url,
                p.birth_date,
                p.nationality,
                p.primary_position,
                ps.season_id,
                s.label AS season,
                ps.club_id,
                c.official_name AS club,
                c.crest_url,
                COALESCE(stats.appearances, 0) AS appearances,
                COALESCE(stats.minutes, 0) AS minutes,
                COALESCE(stats.goals, 0) AS goals,
                COALESCE(stats.assists, 0) AS assists,
                {fantasy_fields},
                {index_fields}
            FROM players p
            JOIN player_seasons ps ON ps.player_id = p.player_id
            JOIN seasons s ON s.season_id = ps.season_id
            JOIN clubs c ON c.club_id = ps.club_id
            LEFT JOIN player_season_stats stats
              ON stats.player_id = p.player_id
             AND stats.season_id = ps.season_id
             AND stats.club_id = ps.club_id
            {fantasy_join}
            {index_join}
            WHERE {' AND '.join(where)}
            ORDER BY {order_map[sort]}
            LIMIT ? OFFSET ?
        """
        rows = connection.execute(sql, [*params, limit, offset]).fetchall()

        count_sql = f"""
            SELECT COUNT(*)
            FROM players p
            JOIN player_seasons ps ON ps.player_id = p.player_id
            WHERE {' AND '.join(where)}
        """
        total = connection.execute(count_sql, params).fetchone()[0]
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/players/{player_id}")
def player_detail(player_id: str) -> dict[str, Any]:
    with connect() as connection:
        player = connection.execute(
            "SELECT * FROM players WHERE player_id = ?", (player_id,)
        ).fetchone()
        if player is None:
            raise HTTPException(status_code=404, detail="Giocatore non trovato")

        seasons = [dict(row) for row in connection.execute(
            """
            SELECT ps.*, s.label AS season, c.official_name AS club,
                   stats.appearances, stats.starts, stats.minutes, stats.goals,
                   stats.assists, stats.goals_per90, stats.assists_per90,
                   stats.xg, stats.xa, stats.xg_per90, stats.xa_per90
            FROM player_seasons ps
            JOIN seasons s ON s.season_id = ps.season_id
            JOIN clubs c ON c.club_id = ps.club_id
            LEFT JOIN player_season_stats stats
              ON stats.player_id = ps.player_id
             AND stats.season_id = ps.season_id
             AND stats.club_id = ps.club_id
            WHERE ps.player_id = ?
            ORDER BY s.label DESC
            """, (player_id,)
        ).fetchall()]

        similar = []
        if table_exists(connection, "similar_players"):
            similar = [dict(row) for row in connection.execute(
                """
                SELECT sp.season_id, sp.rank, sp.similarity_score,
                       p.player_id, p.full_name, p.photo_url
                FROM similar_players sp
                JOIN players p ON p.player_id = sp.similar_player_id
                WHERE sp.player_id = ?
                ORDER BY sp.season_id DESC, sp.rank ASC
                LIMIT 20
                """, (player_id,)
            ).fetchall()]

        return {"player": dict(player), "seasons": seasons, "similar": similar}
