-- The engine check as a data test. WARN, not error: a miss is a finding
-- to diagnose (the 9/4 rule), and fct_engine_misses should still build
-- so there is something to look at. The Tuesday refresh reads the same
-- signal from `truth compare`.
{{ config(severity = 'warn') }}
select * from {{ ref('fct_engine_misses') }}
