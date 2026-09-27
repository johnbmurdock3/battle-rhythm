-- One row per league x season x week x rostered player, typed.
-- Ids are TEXT on purpose: Sleeper ids are 19 digits, and anything that
-- reads them as a float silently rounds the last digits and breaks joins
-- (the Tableau connector did exactly this on 9/22).
with src as (
    select *
    from read_csv(
        '{{ var("truth_csv") }}',
        header = true,
        columns = {
            'season': 'INTEGER', 'week': 'INTEGER', 'league_id': 'VARCHAR',
            'league': 'VARCHAR', 'roster_id': 'INTEGER', 'player_id': 'VARCHAR',
            'position': 'VARCHAR', 'slot': 'VARCHAR', 'computed': 'DOUBLE',
            'sleeper': 'DOUBLE', 'diff': 'DOUBLE', 'status': 'VARCHAR',
            'cause_hint': 'VARCHAR', 'custom_points': 'VARCHAR', 'source': 'VARCHAR',
            'fetched_at': 'VARCHAR'
        }
    )
)
select
    season,
    week,
    league_id,
    trim(league)                                   as league_name,
    roster_id,
    player_id,
    nullif(position, '')                           as position,
    slot,
    slot = 'starter'                               as is_starter,
    computed                                       as engine_points,
    sleeper                                        as sleeper_points,
    diff                                           as points_diff,
    status                                         as match_status,
    status in ('exact', 'rounding')                as is_match,
    nullif(cause_hint, '')                         as cause_hint,
    nullif(nullif(custom_points, ''), 'None')      as custom_points,
    source,
    try_cast(fetched_at as timestamp)              as fetched_at
from src
