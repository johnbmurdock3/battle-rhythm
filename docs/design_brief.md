# Battle Rhythm — design brief

You are restyling an existing, working dashboard. Attached is `dashboard.html` —
the current generated page with stub data. **Restyle it; do not reinvent its
structure.** The page is produced by a Python script from live fantasy-football
data, and its class names and IDs are load-bearing (JavaScript wiring, listed at
the bottom). Deliver back one self-contained HTML file with your design applied
to the same structure; a developer will port your CSS/layout decisions into the
generator.

## What this app is

**Battle Rhythm** is a personal fantasy-football command center for one
manager's Sleeper leagues (five, in my case). It regenerates as a single local
HTML file. The page title is dynamic — `{Username}'s {Phase} Battle Rhythm`
(e.g. "Dirtymurdock's In-Flight Battle Rhythm") — where Phase is In-Flight if
any league is drafting, else Pre-Draft, else In-Season. The phase word in the
title is a living element; treat it as part of the identity, not just a string.
It will be shipped to friends, so nothing may be hardcoded to my name or teams
visually — the design must work for any username and 2–8 leagues.

## Page anatomy (all present in the attachment)

**Hero band** — app title, subtitle (league count, season/week, generated
timestamp), and a Refresh button that live-reloads data when served locally.
Current aesthetic: a football-field motif (green mowing stripes + yard lines)
confined to this band. Keep, evolve, or replace it — but the field must never
sit behind data tables.

**League tiles** — one card per league: name, a phase-colored dot, team count,
FAAB budget, next event (draft date or waiver cadence). Tiles are also the
page's filter: clicking one shows only that league's section; an "all leagues"
tile resets. Phase colors are semantic and repeat elsewhere: amber = pre-draft,
green (pulsing) = actively drafting, blue = in-season.

**One section per league**, whose contents depend on that league's phase:

- *Pre-draft*: a draft-countdown meta line; "first-3-pick scenarios" — for each
  of my first three picks, a table of candidates in three labeled bands (STEAL /
  FALL WATCH / EXPECTED); a filterable **depth board** (below); an optional
  keeper-rules block.
- *In-flight draft*: the **turn plan** — a callout recommending exactly who to
  take now and who waits until my next pick. This is the single most important
  element in the entire app; when a draft is live, a user glances at this and
  nothing else. It can alternatively show a "depth phase" banner when starters
  are filled. Below it: a 6-row alternates table and the depth board.
- *In-season*: my roster ranked by rest-of-season value (with starter/bench
  role); trade candidates (give/get with age + market-price annotations,
  partner name, gain for each side); waiver claims in two tiers (each row:
  add + injury badge + points gap, and the drop to make); situation flags
  (bye-week pileups, playoff weaknesses) as alert-style rows.

**Depth board** (pre-draft and in-flight) — a 40-row scrolling table with
sticky headers and a row of position filter chips: All / QB / RB / WR / TE /
Flex. Columns: player (+ injury badge), need, vorp, proj, market price (dADP),
age.

## Data realities the design must survive

- Tables are dense: 5–6 numeric columns, up to 40 rows, tabular numerals.
- Player names run long ("Jaxon Smith-Njigba (WR, SEA)"); league names contain
  emoji ("LG05").
- Injury badges appear inline anywhere a player renders: short codes like
  `Q-groin`, `OUT-hamstring`, `PUP-achilles`.
- Numbers can be negative (VORP) — must stay readable.
- A league section can also render a one-line failure note if its data fetch
  breaks; style that state too.

## Hard technical constraints (non-negotiable)

- ONE self-contained HTML file: inline CSS, inline JS, no frameworks (no
  React/Tailwind/build step), no external fonts, scripts, or images — system
  font stack only. It's emitted by a Python script with no bundler.
- No localStorage/sessionStorage anywhere.
- Light AND dark mode via `prefers-color-scheme`, both fully designed.
- Readability of dense numbers beats theme everywhere they conflict — this is
  the project's standing rule.
- Keep these hooks intact (JS depends on them):
  - `#refresh` button; it POSTs `/refresh` and shows busy/error states
  - `.tile[data-sec="secN"]` buttons + `section#secN` + `.tile.all` (filtering)
  - `.poschip[data-pos]` chips + `tr[data-pos]` rows (position filtering,
    `.hidden` class toggles rows/sections)
  - class names used for state: `.active`, `.hidden`

## What to deliver

The attached `dashboard.html` restyled — same elements, same hooks, your
visual system. If you restructure layout (columns, tabs, collapsing sections),
keep every element present and reachable and say what you changed so the
generator can follow. Bold ideas welcome on: hierarchy per phase, the tile
row, making the turn plan unmistakable, taming 40-row tables, and what
"battle rhythm" looks like as a visual identity.
