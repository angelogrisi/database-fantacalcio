#!/usr/bin/env python3
"""Block 5: build advanced Serie A metrics from available match statistics.

The script never invents provider-owned metrics. Native xG/xA/xT fields are imported
only when present. Other indexes are calculated from observed fields and explicitly
marked as calculated with a methodology version.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

METHODOLOGY = "block5-v1"


def safe_div(value: float | None, denominator: float | None) -> float | None:
    if value is None or denominator in (None, 0):
        return None
    return value / denominator


def per90(value: float | None, minutes: int | None) -> float | None:
    ratio = safe_div(value, minutes)
    return None if ratio is None else ratio * 90.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def initialise(conn: sqlite3.Connection) -> None:
    migration = Path("migrations/005_block_5_advanced_metrics.sql").read_text(encoding="utf-8")
    conn.executescript(migration)


def build_season_metrics(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT
          pss.player_id, pss.season_id, pss.club_id, pss.competition_id,
          COALESCE(pss.minutes, 0), pss.xg, pss.xa,
          COALESCE(pss.shots, 0), COALESCE(pss.key_passes, 0),
          COALESCE(pss.progressive_passes, 0), COALESCE(pss.progressive_carries, 0),
          COALESCE(pss.tackles, 0), COALESCE(pss.interceptions, 0),
          COALESCE(pss.expected_threat, 0), COALESCE(pss.appearances, 0)
        FROM player_season_stats pss
        """
    ).fetchall()

    written = 0
    for row in rows:
        (
            player_id, season_id, club_id, competition_id, minutes, xg, xa,
            shots, key_passes, progressive_passes, progressive_carries,
            tackles, interceptions, expected_threat, appearances,
        ) = row

        xg90 = per90(xg, minutes)
        xa90 = per90(xa, minutes)
        xgxa90 = None if xg90 is None and xa90 is None else (xg90 or 0) + (xa90 or 0)
        xt90 = per90(expected_threat, minutes)

        attacking = clamp((per90(shots, minutes) or 0) * 14 + (xgxa90 or 0) * 35)
        creation = clamp((per90(key_passes, minutes) or 0) * 18 + (xa90 or 0) * 40)
        progression = clamp(
            (per90(progressive_passes, minutes) or 0) * 4
            + (per90(progressive_carries, minutes) or 0) * 5
        )
        pressing = clamp(
            (per90(tackles, minutes) or 0) * 10
            + (per90(interceptions, minutes) or 0) * 12
        )

        populated = sum(v not in (None, 0) for v in (xg, xa, shots, key_passes, progressive_passes,
                                                       progressive_carries, expected_threat))
        coverage = round(populated / 7 * 100, 2)
        quality = round(min(100.0, coverage * (1.0 if appearances >= 5 else 0.8)), 2)

        conn.execute(
            """
            INSERT INTO player_advanced_season_metrics (
              player_id, season_id, club_id, competition_id, minutes,
              xg, xa, xg_per90, xa_per90, xg_plus_xa_per90,
              progressive_passes, progressive_carries, expected_threat,
              expected_threat_per90, attacking_involvement_index,
              chance_creation_index, progression_index, pressing_index,
              data_coverage_pct, source_quality, methodology_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(player_id, season_id, club_id, competition_id, methodology_version)
            DO UPDATE SET
              minutes=excluded.minutes, xg=excluded.xg, xa=excluded.xa,
              xg_per90=excluded.xg_per90, xa_per90=excluded.xa_per90,
              xg_plus_xa_per90=excluded.xg_plus_xa_per90,
              progressive_passes=excluded.progressive_passes,
              progressive_carries=excluded.progressive_carries,
              expected_threat=excluded.expected_threat,
              expected_threat_per90=excluded.expected_threat_per90,
              attacking_involvement_index=excluded.attacking_involvement_index,
              chance_creation_index=excluded.chance_creation_index,
              progression_index=excluded.progression_index,
              pressing_index=excluded.pressing_index,
              data_coverage_pct=excluded.data_coverage_pct,
              source_quality=excluded.source_quality
            """,
            (player_id, season_id, club_id, competition_id, minutes,
             xg, xa, xg90, xa90, xgxa90,
             progressive_passes, progressive_carries, expected_threat,
             xt90, attacking, creation, progression, pressing,
             coverage, quality, METHODOLOGY),
        )
        written += 1

    conn.commit()
    return written


def write_report(conn: sqlite3.Connection, output: Path) -> None:
    report = {
        "methodology": METHODOLOGY,
        "advanced_season_rows": conn.execute(
            "SELECT COUNT(*) FROM player_advanced_season_metrics"
        ).fetchone()[0],
        "players_with_xg": conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM player_advanced_season_metrics WHERE xg IS NOT NULL"
        ).fetchone()[0],
        "players_with_xa": conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM player_advanced_season_metrics WHERE xa IS NOT NULL"
        ).fetchone()[0],
        "average_coverage_pct": conn.execute(
            "SELECT ROUND(AVG(data_coverage_pct),2) FROM player_advanced_season_metrics"
        ).fetchone()[0],
        "note": "Unavailable provider metrics remain NULL; calculated indexes use only observed database fields.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("DATABASE_PATH", "data/database-fantacalcio.sqlite"))
    parser.add_argument("--report", default="reports/block_5_coverage_report.json")
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    initialise(conn)
    count = build_season_metrics(conn)
    write_report(conn, Path(args.report))
    conn.close()
    print(f"Block 5 completed: {count} advanced player-season rows generated")


if __name__ == "__main__":
    main()
