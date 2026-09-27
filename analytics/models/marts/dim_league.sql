-- One row per league-season. A league's id changes every season on
-- Sleeper (previous_league_id links them), so league-season IS the key.
select
    league_id,
    season,
    arg_max(league_name, fetched_at)   as league_name,
    min(week)                          as first_week,
    max(week)                          as last_week,
    count(distinct roster_id)          as rosters
from {{ ref('stg_truth__player_weeks') }}
group by league_id, season
