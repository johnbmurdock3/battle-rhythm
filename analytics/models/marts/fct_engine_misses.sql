-- Every player-week where the engine disagreed with Sleeper, with the
-- hint truth.py attached (the scoring key that would explain it alone).
-- Empty is the goal. A row here is a diagnosis to approve, never an
-- automatic fix.
select
    season, week, league_id, league_name, roster_id, player_id, position, slot,
    engine_points, sleeper_points, points_diff, cause_hint, fetched_at
from {{ ref('stg_truth__player_weeks') }}
where match_status = 'miss'
