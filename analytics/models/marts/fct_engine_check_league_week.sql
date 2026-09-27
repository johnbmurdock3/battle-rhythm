-- Match rate per league-week: the number the ledger's credibility rests on.
select
    p.league_id,
    p.season,
    p.week,
    l.league_name,
    count(*)                                          as player_rows,
    count(*) filter (where p.sleeper_points <> 0)     as scoring_rows,
    count(*) filter (where p.match_status = 'exact')  as exact_rows,
    count(*) filter (where p.match_status = 'rounding') as rounding_rows,
    count(*) filter (where p.match_status = 'miss')   as miss_rows,
    round(avg(case when p.is_match then 1.0 else 0.0 end), 4) as match_rate,
    max(abs(p.points_diff))                           as max_abs_diff,
    sum(p.sleeper_points) filter (where p.is_starter) as starter_points_sleeper,
    max(p.fetched_at)                                 as fetched_at
from {{ ref('stg_truth__player_weeks') }} p
join {{ ref('dim_league') }} l using (league_id, season)
group by p.league_id, p.season, p.week, l.league_name
