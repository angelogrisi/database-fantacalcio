#!/usr/bin/env python3
"""Block 3: import Serie A player statistics from API-Football where available.

The importer never fabricates missing values. It stores provider observations and
calculates only transparent per-90 and percentage metrics.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
DB_PATH = Path(os.getenv("DATABASE_PATH", "data/database-fantacalcio.sqlite"))
API_KEY = os.getenv("API_FOOTBALL_API_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
SERIE_A_LEAGUE_ID = 135
SEASONS = {"2021-22": 2021, "2022-23": 2022, "2023-24": 2023, "2024-25": 2024, "2025-26": 2025}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, provider: str, external_id: Any) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, f'{provider}:{external_id}').hex[:20]}"


def request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_API_KEY non configurata")
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={"x-apisports-key": API_KEY},
        params=params,
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football error: {errors}")
    return payload


def ensure_schema(conn: sqlite3.Connection) -> None:
    schema = Path("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    migration = Path("migrations/003_block_3_player_statistics.sql").read_text(encoding="utf-8")
    conn.executescript(migration)


def find_season_id(conn: sqlite3.Connection, label: str) -> int:
    row = conn.execute("SELECT season_id FROM seasons WHERE label=?", (label,)).fetchone()
    if not row:
        raise RuntimeError(f"Stagione non inizializzata: {label}")
    return int(row[0])


def find_competition_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT competition_id FROM competitions WHERE name='Serie A' AND country='Italy'").fetchone()
    if not row:
        raise RuntimeError("Competizione Serie A non inizializzata")
    return int(row[0])


def upsert_club(conn: sqlite3.Connection, team: dict[str, Any]) -> str:
    ext = team.get("id")
    club_id = stable_id("CLB", "api-football", ext)
    current = conn.execute("SELECT external_ids_json FROM clubs WHERE club_id=?", (club_id,)).fetchone()
    ids = {"api_football": ext}
    if current and current[0]:
        try:
            ids.update(json.loads(current[0]))
        except json.JSONDecodeError:
            pass
    conn.execute(
        """INSERT INTO clubs(club_id, official_name, short_name, country, crest_url, external_ids_json)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(club_id) DO UPDATE SET official_name=excluded.official_name,
             short_name=excluded.short_name, crest_url=excluded.crest_url,
             external_ids_json=excluded.external_ids_json, updated_at=CURRENT_TIMESTAMP""",
        (club_id, team.get("name") or f"Team {ext}", team.get("code"), "Italy", team.get("logo"), json.dumps(ids)),
    )
    return club_id


def upsert_player(conn: sqlite3.Connection, player: dict[str, Any]) -> str:
    ext = player.get("id")
    player_id = stable_id("PLY", "api-football", ext)
    full_name = player.get("name") or "Unknown"
    conn.execute(
        """INSERT INTO players(player_id, first_name, last_name, full_name, birth_date, nationality,
              height_cm, weight_kg, primary_position, photo_url, external_ids_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(player_id) DO UPDATE SET first_name=COALESCE(excluded.first_name, players.first_name),
              last_name=COALESCE(excluded.last_name, players.last_name), full_name=excluded.full_name,
              birth_date=COALESCE(excluded.birth_date, players.birth_date),
              nationality=COALESCE(excluded.nationality, players.nationality),
              height_cm=COALESCE(excluded.height_cm, players.height_cm),
              weight_kg=COALESCE(excluded.weight_kg, players.weight_kg),
              primary_position=COALESCE(excluded.primary_position, players.primary_position),
              photo_url=COALESCE(excluded.photo_url, players.photo_url),
              external_ids_json=excluded.external_ids_json, updated_at=CURRENT_TIMESTAMP""",
        (
            player_id, player.get("firstname"), player.get("lastname"), full_name,
            (player.get("birth") or {}).get("date"), player.get("nationality"),
            parse_measure(player.get("height")), parse_measure(player.get("weight")),
            player.get("position"), player.get("photo"), json.dumps({"api_football": ext}),
        ),
    )
    return player_id


def parse_measure(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).split()[0].replace(",", "."))
    except (ValueError, TypeError):
        return None


def n(value: Any, default: int = 0) -> int:
    return default if value is None else int(value)


def f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_season(conn: sqlite3.Connection, season_id: int, competition_id: int) -> None:
    rows = conn.execute(
        """SELECT player_id, club_id, COUNT(*), SUM(started), SUM(CASE WHEN started=0 AND minutes>0 THEN 1 ELSE 0 END),
                  SUM(minutes), AVG(rating), SUM(goals), SUM(assists), SUM(COALESCE(goals_conceded,0)),
                  SUM(COALESCE(saves,0)), SUM(COALESCE(shots_total,0)), SUM(COALESCE(shots_on_target,0)),
                  SUM(COALESCE(passes_total,0)), SUM(COALESCE(passes_key,0)), AVG(pass_accuracy_pct),
                  SUM(COALESCE(tackles_total,0)), SUM(COALESCE(tackles_blocks,0)), SUM(COALESCE(tackles_interceptions,0)),
                  SUM(COALESCE(duels_total,0)), SUM(COALESCE(duels_won,0)), SUM(COALESCE(dribbles_attempts,0)),
                  SUM(COALESCE(dribbles_success,0)), SUM(COALESCE(fouls_drawn,0)), SUM(COALESCE(fouls_committed,0)),
                  SUM(yellow_cards), SUM(red_cards), SUM(penalty_won), SUM(penalty_committed), SUM(penalty_scored),
                  SUM(penalty_missed), SUM(penalty_saved)
           FROM player_match_statistics_extended pm
           JOIN matches m ON m.match_id=pm.match_id
           WHERE m.season_id=? AND m.competition_id=? AND pm.source_name='API-Football'
           GROUP BY player_id, club_id""",
        (season_id, competition_id),
    ).fetchall()
    for r in rows:
        minutes = r[5] or 0
        per90 = lambda value: round((value or 0) * 90 / minutes, 4) if minutes else None
        duels_pct = round((r[20] or 0) * 100 / r[19], 2) if r[19] else None
        dribble_pct = round((r[22] or 0) * 100 / r[21], 2) if r[21] else None
        conn.execute(
            """INSERT INTO player_season_statistics_extended(
              player_id,season_id,club_id,competition_id,appearances,starts,substitute_appearances,minutes,avg_rating,
              goals,assists,goals_conceded,saves,shots_total,shots_on_target,passes_total,passes_key,pass_accuracy_pct,
              tackles_total,blocks,interceptions,duels_total,duels_won,dribbles_attempts,dribbles_success,
              fouls_drawn,fouls_committed,yellow_cards,red_cards,penalties_won,penalties_committed,penalties_scored,
              penalties_missed,penalties_saved,goals_per90,assists_per90,shots_per90,key_passes_per90,tackles_per90,
              interceptions_per90,duels_won_pct,dribble_success_pct,source_name)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(player_id,season_id,club_id,competition_id,source_name) DO UPDATE SET
                appearances=excluded.appearances, starts=excluded.starts, substitute_appearances=excluded.substitute_appearances,
                minutes=excluded.minutes, avg_rating=excluded.avg_rating, goals=excluded.goals, assists=excluded.assists,
                goals_conceded=excluded.goals_conceded, saves=excluded.saves, shots_total=excluded.shots_total,
                shots_on_target=excluded.shots_on_target, passes_total=excluded.passes_total, passes_key=excluded.passes_key,
                pass_accuracy_pct=excluded.pass_accuracy_pct, tackles_total=excluded.tackles_total, blocks=excluded.blocks,
                interceptions=excluded.interceptions, duels_total=excluded.duels_total, duels_won=excluded.duels_won,
                dribbles_attempts=excluded.dribbles_attempts, dribbles_success=excluded.dribbles_success,
                fouls_drawn=excluded.fouls_drawn, fouls_committed=excluded.fouls_committed,
                yellow_cards=excluded.yellow_cards, red_cards=excluded.red_cards, penalties_won=excluded.penalties_won,
                penalties_committed=excluded.penalties_committed, penalties_scored=excluded.penalties_scored,
                penalties_missed=excluded.penalties_missed, penalties_saved=excluded.penalties_saved,
                goals_per90=excluded.goals_per90, assists_per90=excluded.assists_per90, shots_per90=excluded.shots_per90,
                key_passes_per90=excluded.key_passes_per90, tackles_per90=excluded.tackles_per90,
                interceptions_per90=excluded.interceptions_per90, duels_won_pct=excluded.duels_won_pct,
                dribble_success_pct=excluded.dribble_success_pct, updated_at=CURRENT_TIMESTAMP""",
            (*r[:32], per90(r[7]), per90(r[8]), per90(r[11]), per90(r[14]), per90(r[16]), per90(r[18]), duels_pct, dribble_pct, "API-Football"),
        )


def import_season(conn: sqlite3.Connection, label: str, provider_season: int) -> None:
    season_id = find_season_id(conn, label)
    competition_id = find_competition_id(conn)
    started = now()
    run_id = conn.execute(
        "INSERT INTO import_runs(block_name,source_name,season_label,started_at,status) VALUES(?,?,?,?,?)",
        ("block-3", "API-Football", label, started, "running"),
    ).lastrowid
    received = inserted = skipped = 0
    try:
        fixtures = request("fixtures", {"league": SERIE_A_LEAGUE_ID, "season": provider_season}).get("response", [])
        for index, item in enumerate(fixtures, 1):
            fixture_id = item.get("fixture", {}).get("id")
            if not fixture_id:
                skipped += 1
                continue
            match_id = stable_id("MAT", "api-football", fixture_id)
            match_exists = conn.execute("SELECT 1 FROM matches WHERE match_id=?", (match_id,)).fetchone()
            if not match_exists:
                skipped += 1
                continue
            payload = request("fixtures/players", {"fixture": fixture_id})
            teams = payload.get("response", [])
            for team_block in teams:
                team = team_block.get("team", {})
                club_id = upsert_club(conn, team)
                for entry in team_block.get("players", []):
                    received += 1
                    player = entry.get("player", {})
                    stats_list = entry.get("statistics") or []
                    if not stats_list:
                        skipped += 1
                        continue
                    s = stats_list[0]
                    games, goals, shots = s.get("games", {}), s.get("goals", {}), s.get("shots", {})
                    passes, tackles, duels = s.get("passes", {}), s.get("tackles", {}), s.get("duels", {})
                    dribbles, fouls, cards, penalty = s.get("dribbles", {}), s.get("fouls", {}), s.get("cards", {}), s.get("penalty", {})
                    player_id = upsert_player(conn, {**player, "position": games.get("position")})
                    conn.execute(
                        """INSERT INTO player_match_statistics_extended(
                          match_id,player_id,club_id,provider_fixture_id,provider_player_id,started,substitute,minutes,
                          position,rating,captain,goals,assists,goals_conceded,saves,shots_total,shots_on_target,
                          passes_total,passes_key,pass_accuracy_pct,tackles_total,tackles_blocks,tackles_interceptions,
                          duels_total,duels_won,dribbles_attempts,dribbles_success,dribbles_past,fouls_drawn,
                          fouls_committed,yellow_cards,red_cards,penalty_won,penalty_committed,penalty_scored,
                          penalty_missed,penalty_saved,source_name)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(match_id,player_id,source_name) DO UPDATE SET
                            club_id=excluded.club_id, started=excluded.started, substitute=excluded.substitute,
                            minutes=excluded.minutes, position=excluded.position, rating=excluded.rating,
                            captain=excluded.captain, goals=excluded.goals, assists=excluded.assists,
                            goals_conceded=excluded.goals_conceded, saves=excluded.saves, shots_total=excluded.shots_total,
                            shots_on_target=excluded.shots_on_target, passes_total=excluded.passes_total,
                            passes_key=excluded.passes_key, pass_accuracy_pct=excluded.pass_accuracy_pct,
                            tackles_total=excluded.tackles_total, tackles_blocks=excluded.tackles_blocks,
                            tackles_interceptions=excluded.tackles_interceptions, duels_total=excluded.duels_total,
                            duels_won=excluded.duels_won, dribbles_attempts=excluded.dribbles_attempts,
                            dribbles_success=excluded.dribbles_success, dribbles_past=excluded.dribbles_past,
                            fouls_drawn=excluded.fouls_drawn, fouls_committed=excluded.fouls_committed,
                            yellow_cards=excluded.yellow_cards, red_cards=excluded.red_cards,
                            penalty_won=excluded.penalty_won, penalty_committed=excluded.penalty_committed,
                            penalty_scored=excluded.penalty_scored, penalty_missed=excluded.penalty_missed,
                            penalty_saved=excluded.penalty_saved, acquired_at=CURRENT_TIMESTAMP""",
                        (
                            match_id, player_id, club_id, str(fixture_id), str(player.get("id")),
                            1 if games.get("substitute") is False else 0, 1 if games.get("substitute") else 0,
                            n(games.get("minutes")), games.get("position"), f(games.get("rating")),
                            1 if games.get("captain") else 0, n(goals.get("total")), n(goals.get("assists")),
                            goals.get("conceded"), goals.get("saves"), shots.get("total"), shots.get("on"),
                            passes.get("total"), passes.get("key"), f(passes.get("accuracy")), tackles.get("total"),
                            tackles.get("blocks"), tackles.get("interceptions"), duels.get("total"), duels.get("won"),
                            dribbles.get("attempts"), dribbles.get("success"), dribbles.get("past"), fouls.get("drawn"),
                            fouls.get("committed"), n(cards.get("yellow")), n(cards.get("red")), n(penalty.get("won")),
                            n(penalty.get("commited")), n(penalty.get("scored")), n(penalty.get("missed")),
                            n(penalty.get("saved")), "API-Football",
                        ),
                    )
                    inserted += 1
            conn.commit()
            if index % 10 == 0:
                print(f"{label}: {index}/{len(fixtures)} partite elaborate")
            time.sleep(0.2)
        aggregate_season(conn, season_id, competition_id)
        conn.execute(
            "UPDATE import_runs SET completed_at=?,status='completed',records_received=?,records_inserted=?,records_skipped=? WHERE import_run_id=?",
            (now(), received, inserted, skipped, run_id),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            "UPDATE import_runs SET completed_at=?,status='failed',records_received=?,records_inserted=?,records_skipped=?,error_message=? WHERE import_run_id=?",
            (now(), received, inserted, skipped, str(exc), run_id),
        )
        conn.commit()
        raise


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        for label, season in SEASONS.items():
            try:
                import_season(conn, label, season)
            except Exception as exc:
                print(f"[WARN] {label}: {exc}", file=sys.stderr)
        counts = {
            "match_rows": conn.execute("SELECT COUNT(*) FROM player_match_statistics_extended").fetchone()[0],
            "season_rows": conn.execute("SELECT COUNT(*) FROM player_season_statistics_extended").fetchone()[0],
            "players": conn.execute("SELECT COUNT(*) FROM players").fetchone()[0],
        }
        print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
