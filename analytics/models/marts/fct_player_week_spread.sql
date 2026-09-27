-- The same player-week, scored by every league that rosters him.
-- This is the multi-tenant point in one table: one stat line, seven rule
-- sets, and the engine has to land on each league's number. 9/26: one
-- quarterback's week 2 ran from 29.78 to 81.55 across seven leagues,
-- all seven exact.
select
    season,
    week,
    player_id,
    any_value(position)                         as position,
    count(distinct league_id)                   as leagues,
    min(sleeper_points)                         as min_points,
    max(sleeper_points)                         as max_points,
    round(max(sleeper_points) - min(sleeper_points), 2) as points_spread,
    bool_and(is_match)                          as all_leagues_match,
    string_agg(league_name || '=' || cast(sleeper_points as varchar), '; '
               order by sleeper_points)         as by_league
from {{ ref('stg_truth__player_weeks') }}
group by season, week, player_id
