# analytics/ — the engine check as a dbt model

`python br.py truth compare --recent` (or `--season 2025 --all`) rebuilds
`../out/truth/player_weeks.csv` from the tracked snapshots. This project
models it in DuckDB; no server, no credentials.

    pip install dbt-duckdb
    cd analytics
    dbt build --profiles-dir .

| Model | Grain | What it answers |
|---|---|---|
| `stg_truth__player_weeks` | league × season × week × player | typed rows, ids kept as text |
| `dim_league` | league × season | names and week range |
| `fct_engine_check_league_week` | league × week | match rate, misses, largest gap |
| `fct_engine_misses` | player-week | every disagreement, with the key that would explain it |
| `fct_player_week_spread` | season × week × player | one stat line scored by every league that rosters him |

Tests: grain uniqueness, accepted values, and `assert_engine_matches_sleeper`
(warn severity: a miss is a finding, not a build failure).

Output lands in `target/br.duckdb`, gitignored.
