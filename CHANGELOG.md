# Changelog — 8/10 evening through 8/11

One session. Test suite went 14 → 23; two new modules carry their own
selftests (dynasty_value 30+ checks, dossier 30+, research_queue 9,
roster_map 8, reconcile 8, room_bias 12).

## New files

    CLAUDE.md              project memory: lessons, security, architecture,
                           style contract, where-truth-lives
    DECISIONS.md           append-only log; supersede, never edit
    CHANGELOG.md           this file
    RESEARCH_PLAN.md       dossier program: scope, schema, weekly refresh
    MISPRICING.md          11 categories of premium/discount the API
                           cannot price, with the attribution trap
    ages.json              aging curves, holding horizons, roster
                           multipliers — all tunable, none fitted
    dynasty_value.py       multi-year value model + CLI board
    dossier.py             research store: schema, timeline, flags,
                           preflight, refresh triage
    research_queue.py      who is worth researching and how deeply
    roster_map.py          league-wide ownership + roster links
    reconcile.py           cross-check dossiers vs the player table
    room_bias.py           measure a room's positional draft bias
    backtest_probe.py      does Sleeper serve historical projections
    dossiers/              447 player records
    dossiers_lg05_all.json, research_queue_lg05.json,
    room_bias.json

## The value model

Built from nothing to a working multi-year model:

- Positional aging curves (peak plateau, rise, decline, cliff, end)
- **Surplus over positional replacement**, not raw points. The first
  version compounded raw projections and returned a board where 13 of
  the top 14 were quarterbacks in a 1QB league.
- Market blending (35%) so role changes the model cannot see still land
- Tier breaks on value cliffs rather than fixed counts
- **Roster context**: same-QB target collision, and an RB handcuff bump
  gated on standalone value
- **Holding horizon** — full career for dynasty, 2 seasons for a 7-max
  keeper league, 1 for redraft. Pricing a veteran's age-33 season in a
  league that churns everyone is how a model talks you out of elite
  older players.
- Cross-position collisions (TE vs WR) softened to 0.8× vs 0.6×
- Collision and handcuff notes name the specific player

## Research system

- **447 dossiers, 1,217 sources, zero schema failures.** Deep tier 40,
  medium 110, light 297, all via parallel subagents.
- **108 verified 2025→2026 team changes** — the highest-yield output,
  since projections lag role changes badly.
- Sourcing is enforced: a record claiming high/medium confidence with
  no sources is rejected.
- **Append-only timeline** so weekly refreshes produce slope, not just
  state. All 447 backfilled with an 8/11 baseline.
- **Attributed opportunity flags** — BLOCKED (his own injury),
  INHERITING (someone ahead of him hurt or gone), WATCH (thin
  reporting). 98 of 447 flagged.
- `reconcile.py` resolved 935 competition entries against the player
  table: **zero unresolvable names**, 35 no-longer-teammates corrected.
- Weekly refresh scheduled Tuesdays 8:00 AM PT, triaged to ~100-150
  players, delivers a bundle plus a one-page diff.

## Draft tooling

- `research_queue` — stakes × uncertainty × proximity triage
- `roster_map --links` — who owns your handcuffs and target competitors
- `keeper --board` — availability adjusted for keeper depletion
- `keeper --kept` — every team's locked keepers, by position
- `room_bias` — positional draft bias measured from the room's own
  prior draft, relative to its own baseline
- `dossier preflight` — the morning-of check, made concrete
- `dossier refresh-list` — this week's research work list

## Dashboard

- New **DYNASTY tab** (dynasty-typed leagues): value, model, tiers,
  years left, research
- **RESEARCH column** plus research leading the WHY on the Board tab
- Horizon-aware pricing, displayed in the header
- Collision/handcuff shown as a single hoverable flag
- Table widened 860 → 1560px; research cell went ~246 → ~816px
- Injury chips clip at 10 chars with full text on hover

## Documentation

- `lg05_brief.md` rewritten twice — once on research, then again on
  observed keepers when the first rewrite proved unexecutable
- `HANDOFF.md` standing rules rewritten (GB ban retired)
- CLAUDE.md lesson 8 added: use the context you already have
- DECISIONS.md carries every reversal as a superseding entry

## Bugs found and fixed

Worth keeping because most were found by running against real data, not
by testing:

1. QB wall — compounding raw points instead of surplus
2. Market-blend ladder truncated on a half-drafted board
3. research_score ranked a buried injured rookie #1 of 447
4. Unpriced players credited last-place stakes instead of zero
5. League resolver could not distinguish "LG03-LG05" from "LG03-LG05 🦸"
6. `nfi` matched inside **con-fi-rmed**; `ir` inside **the-ir**
7. "signed with" read as departure when it means arrival
8. Past-season clauses in competitor bios read as current injuries
9. …and the fix for #8 silently dropped Nabers, the most important flag
10. keeper.py ignored keeper depletion entirely
11. room_bias priced QBs off the 1QB market in a superflex league
12. room_bias reported absolute reach, double-counting depletion
13. BASELINE row crashed the summary line
14. Keepers estimated when the API already showed them
15. roster_map invented relationships across team changes
16. roster_map missed "Kenneth" vs "Kenny" Gainwell
17. roster_map flagged self-owned handcuffs as rival-owned
18. Dynasty table capped at 860px with ten columns

## Draft decisions changed

- **Nabers off pick 8** — torn ACL plus a spring cleanup, not a
  Questionable tag
- **Willis resolved** — Miami's starter at a 334 dADP, an open question
  in the handoff since 8/10
- **Geno Smith surfaced** — Jets' Week 1 starter at ADP 186
- **Dynasty 129** — queue collapsed as Mason and Dak went; Rodriguez
- **LG03-LG05 restructured** — RB at 8, quarterback at 17

## My own errors, recorded

- Reversed the Mason/Gainwell call on beat-rate data, then reversed
  back when research showed the beat rate was measuring role change
- Called a fact unknowable that HANDOFF.md already answered
- Called a one-hour-old dossier stale when it had honestly flagged its
  own uncertainty
- Shipped the same substring-matching bug class three times

## Known-open

- `ages.json` curves are priors; the WR cliff (0.78/yr past 30) is
  steep enough to override a 20-point projection edge
- `--board` need counter asks who has zero at a position; wrong in
  superflex where you start two
- keeper.py still prints swap advice against locked keepers
- Weekly task fired 8/11 morning, unverified
- No research queue yet for Hybrid 🦸, LG02, LG04
- `endgame_plan.md` predates everything in this session
- Backtest of whether flagged role changes predict projection misses:
  data confirmed available, never built
