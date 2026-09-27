# The engine check

Battle Rhythm computes fantasy points itself. It takes a player's raw stat line and multiplies it by each league's own scoring settings. I play in seven Sleeper leagues and no two score the same way. The two Hybrids pay receptions by yardage bucket and give nothing for a catch on its own. LG04 pays return yards and six-point passing touchdowns. LG06 pays half a point per pass and rush attempt and scores individual defenders. If the engine is wrong for one of them, every lineup call, waiver bid and trade grade in that league is wrong too.

For the first two weeks of the season I couldn't prove it wasn't. The recommendation ledger scored each piece of advice against "actual" points, but those actuals came from the same engine. A bad rule would have been wrong on both sides of every comparison and never shown up.

## What the check does

Sleeper publishes the points it awarded every rostered player, starters and bench, in each league's weekly matchups. That is ground truth I didn't have to label by hand. `br.py truth` compares the two:

1. `truth fetch` runs on my PC, the only machine that can reach Sleeper from a shell. It saves the week's stats, every league's settings, the matchups and player positions together under one timestamp. Pulling stats and matchups at different times would turn a Tuesday stat correction into a fake miss.
2. `truth compare` runs anywhere, offline, from those snapshots. It writes one row per league, week and rostered player, with the engine's number, Sleeper's number and the difference. When a row misses, it names the scoring rule that would explain the gap on its own.

## Result, weeks 1 and 2 of 2026

All seven leagues: 3,103 player-weeks, and every one matched Sleeper to the cent. That's 2,579 rows with non-zero points, no one-cent rounding differences, and no commissioner overrides. It covers the rules I expected to break: LG04's return yards (30 player-weeks where they counted), LG06' attempt scoring and individual defenders, team defenses, kickers, and the Hybrid reception buckets and first-down scoring.

One quarterback's week 2 came out anywhere from 29.78 to 81.55 points depending on the league. Same stat line, seven rule sets, seven exact matches. That's the whole design problem in one row.

So the ledger's rescoring holds up, and it holds up for free agents too. They never appear in matchups, so Sleeper never publishes a number for them, and for those rows the engine's score is the only one there is.

## What it doesn't prove yet

It only proves the rules that actually came up. Some rules can't come up at all: LG04 pays kickers by distance but has no kicker slot, and the Hybrids and Best Ball carry defense and kicker scoring with no slot for either. Those rules are dead weight in the settings, not gaps in the engine. Special-teams touchdowns, fumble-return touchdowns, field goals under 20 yards, and LG06' defensive safeties and 200-yard bonuses never happened in either week. `truth compare` now prints a rule coverage table showing which paid rules have been confirmed and which haven't been exercised. Backfilling the two Hybrids' 2025 seasons (17 weeks each, under their own 2025 settings) should close most of that gap for their rule set. LG04, LG02 and LG06 started on Sleeper this year, so their rare rules wait for real games.

## How it runs every week

Windows Task Scheduler runs `truth fetch --last` at 6:30 AM Pacific on Tuesdays. It pulls the week that just finished and pulls the week before it again, because Sleeper posts stat corrections after the first scoring pass. At 7:00 the scheduled research refresh runs `truth compare --recent` and puts the result at the top of its report. I get a notification if anything misses or the morning fetch didn't run. Nothing fixes the engine automatically. A miss is something to diagnose, and I approve fixes one cause at a time.

The rows land in `out/truth/player_weeks.csv`. Tableau reads that file directly, and `analytics/` models it with dbt.
