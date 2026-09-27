select league_id, season, count(*) as n
from {{ ref('dim_league') }}
group by all
having count(*) > 1
