-- The fact table's grain: a player appears once per league-week.
-- A duplicate means the same league was snapshotted twice into one week
-- (the lg08 LG08 did this to the ledger on 9/12).
select league_id, season, week, player_id, count(*) as n
from {{ ref('stg_truth__player_weeks') }}
group by all
having count(*) > 1
