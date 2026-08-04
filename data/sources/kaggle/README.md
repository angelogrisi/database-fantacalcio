# Serie A Kaggle data source

This directory contains a normalized, compressed copy of the user-provided Kaggle datasets used to enrich the Serie A player database.

## Imported coverage

- 2023-24: 616 player-season rows
- 2024-25: 634 player-season rows
- 2025-26: 609 player-season rows
- Total: 1,859 player-season rows

The normalized dataset is stored as LZMA-compressed Base64 chunks under `embedded/serie_a_stats.xz.b64.*`. The importer concatenates the chunks in filename order, decodes them and loads the rows into SQLite.

## Importer

Run:

```bash
python src/import_kaggle_serie_a_stats.py
```

It writes or updates:

- `player_season_stats`
- `player_season_statistics_extended`
- `fantasy_player_season`
- `player_seasons`
- `player_source_matches`
- `dataset_import_runs`

The generated coverage report is:

```text
reports/kaggle_serie_a_import_report.json
```

## Older archive limitation

The uploaded archive covering 2021-22 and 2022-23 contains club totals across all competitions rather than Serie A-only league totals. Those rows are intentionally not imported as Serie A statistics to avoid mixing league, cup and European competition data.

## Licensing and provenance

These are user-provided Kaggle community datasets with FBref-derived fields. Before commercial redistribution, verify both the license shown on each Kaggle dataset page and the rights or terms of the original upstream source. The database records this source as `Kaggle community datasets (FBref-derived)` and keeps matching/audit metadata.