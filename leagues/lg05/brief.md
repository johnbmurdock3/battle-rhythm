# LG05 — draft card

**League `9000000000000000020`** · Tue Aug 18, 9:00 AM PT
**Slot 6 of 12** · 10 rounds · superflex · **plain snake, no reversal**

Your picks: **6 · 19 · 30 · 43 · 54 · 67 · 78 · 90 · 91 · 102 · 115**

    1.6   2.7   3.6   4.7   5.6   6.7   7.6   8.6   8.7   9.6   10.7

> This card covers **one league only**. Nothing in it refers to any other
> roster of yours. If a name here doesn't match the room on your screen,
> you're reading the wrong card.

> **Plain snake.** `settings.reversal_round = 0`. Straight snake
> arithmetic holds all the way down — unlike your other Hybrid, which
> does reverse. Do not carry a pick list between the two.
>
> **ELEVEN picks, not ten.** You own a traded-in round-8 pick at
> **overall 90**, and your own seat pick is **91**. Confirmed live
> against `/draft/9000000000000000021/traded_picks`.
>
> **90 and 91 are back to back.** You can gamble on survival at 90
> because 91 catches you if you're wrong. That is the only place in
> either of your drafts where a gamble is nearly free.

---

## Fresh-chat opener

    I'm dirtymurdock, working in C:\Users\johnb\workspace\Sleeper.
    Read CLAUDE.md, then HANDOFF.md, then leagues/lg05/brief.md.

    Today is the LG05 draft — league 9000000000000000020,
    the EMOJI one. Slot 6. This session covers that league and
    nothing else; I have a separate chat for my other Hybrid, so
    do not reference it or pull players from it.

    Start by running these and reading the output:
        python br.py roster
        python br.py board 9000000000000000020
        python br.py lineup 9000000000000000020 --slot 6

---

## Read the board first, the plan second

`draft_helper.py board` is the ranking. `lineup_value.py` is the
sequencing — who survives to your next turn. That split is new as of
8/13 and it exists because the two disagreed sharply and both were wrong.

Use the league **id**, never the name.

---

## Your roster

| slot | player | proj | bye |
|---|---|---|---|
| QB | Lamar Jackson | 404 | 7 |
| RB1 | Kenneth Walker | 308 | 10 |
| RB2 | **empty** | — | |
| WR1 | Brian Thomas | 236 | 8 |
| WR2 | DJ Moore | 215 | 7 |
| WR3 | Kyle Williams | 35 | 14 |
| TE | Oronde Gadsden | 182 | 12 |
| FLEX | **empty** | — | |
| SUPER_FLEX | Jayden Daniels | 382 | 7 |

**Two quarterbacks already, both real.** Lamar Jackson at 404 and Jayden
Daniels at 382 fill QB and SUPER_FLEX with the two best numbers on your
roster. **You do not need a quarterback in this draft.** That is the
single biggest difference between this room and your other one, where the
superflex slot is held by a player projecting one point.

**Two slots are filled in name only.** Kyle Williams (35 vs a WR43 bar of
204) and Oronde Gadsden (182 vs a TE14 bar of 216). Both came off expired
redshirts and are on your active roster now.

**RB is your worst hole** — one body for two slots, and the board agrees:
every one of the top four VORP names is a running back.

---

## Draft 2 will NOT bail you out — measured 8/13

The previous version of this card said draft 1 carried no obligation to
fill roster slots, because a second draft backfills anything you skip.
**That was wrong, and `draft2_probe.py` refuted it by a margin too large
to be method error.**

| pos | replacement | draft 2's BEST available | gap |
|---|---|---|---|
| QB | 322 | 189 | **-133** |
| RB | 253 | 90 | **-163** |
| WR | 230 | 115 | **-115** |
| TE | 219 | 113 | **-106** |

Every running back in this pool projecting 120 or better goes inside the
120 picks of draft 1. What reaches draft 2 is waiver quality.

**So a starting slot you leave open at the end of draft 1 is a real hole,
not a deferred errand.** Your open ones are RB2, FLEX, and upgrades over
Kyle Williams at WR3 and Oronde Gadsden at TE. That is four of your nine
non-taxi picks spoken for.

That does not mean reaching. It means when two players are close, take
the one who fills a slot — and do not finish this draft with an empty
one.

---

## The board is the ranking. `lineup_value` is not.

`draft_helper.py board` ranks by value over each position's own
replacement level. That is the number to draft from.

`lineup_value.py`'s value column **collapses toward raw projection when
most of your slots are floored**, because every candidate is measured
against the single weakest body in the lineup rather than against his own
position. Use it for **survival and sequencing** — its depleted ADP is
the best market read you have — and for in-season lineup calls, where the
roster is full and the marginal model is the right one.

Here the two agree at pick 6 anyway, which is part of why Henry is the
confident call.

---

## The plan

Board VORP for the ranking, `lineup_value`'s depleted ADP for survival.
ADP below is **keeper-depleted** — 80 players never reach this draft.

| pick | rd | take | ADP | why |
|---|---|---|---|---|
| **6** | 1.6 | **Derrick Henry** (RB, +67.6) | 5 | top VORP; both models agree |
| **19** | 2.7 | **Zay Flowers** (WR, +47.4) | 3→gone? | if gone: Ladd McConkey (44.1, ADP 17) |
| **30** | 3.6 | **David Montgomery** (RB) | 40 | second RB body |
| **43** | 4.7 | **Travis Kelce** (TE) | 23 | displaces Gadsden outright |
| **54** | 5.6 | **Jayden Reed** (WR) | 43 | |
| **67** | 6.7 | **Alec Pierce** (WR) | 67 | |
| **78** | 7.6 | **Josh Downs** (WR) | 47 | |
| **90** | 8.6 | gamble — 91 catches you | — | traded-in pick |
| **91** | 8.7 | best available | — | |
| **102** | 9.6 | see taxi note | — | |
| **115** | 10.7 | see taxi note | — | |

### Henry at 6 is the one call both models make

VORP 67.6, top of the board. `lineup_value` independently ranks him
first among reachable players at +150. Depleted ADP 5 means he does not
reach 19. De'Von Achane grades higher on raw VORP in one view but prices
at ADP 1 — he will not be there at 6.

**He is 32.** This card prices 2026 only. Read `dynasty_value.py` before
you commit if you intend to keep him.

### Do not take a quarterback here

Different reason from your other league: you already have two good ones.
Dak Prescott shows up at VORP 40.4 on this board and is worth nothing to
you. Any QB the model surfaces late is bench insurance, and bench
insurance is what draft 2 is for.

### Pick 43 — Kelce is a real upgrade here

Kelce displaces Oronde Gadsden outright (70% of his starts) rather than
filling air, so his value in this room is genuine and not a floor
artifact. Depleted ADP 23 says he may not last to 43. If he's gone, Kyle
Pitts and Tucker Kraft are the same idea.

---

## Taxi: this is not a leftover pick

**Corrected 8/13, and the previous card had it backwards.**

Only a rookie **you draft this year** may occupy a seat. Seats are
**optional** — fill them by the start of the season or they stay empty at
no cost — and can be filled from **either draft**.

The prize is that a taxi rookie carries over consuming **neither a keeper
nor a drafted-rookie slot** — a free keeper outside your 3+2 budget. That
is what you did with Jayden Daniels, who now starts at SUPER_FLEX here.

Sequencing, not timing:

- A rookie who **will last to draft 2** should be taken there.
- A rookie who **will not last** is the only reason to spend a
  first-draft pick on a seat.

The tool offers Jonah Coleman and Chris Brazzell at 102 and 115. Both are
draft-2 profiles. **Take them there and use 102 and 115 on active
value** — unless a rookie you believe in is sliding, in which case take
him earlier than this card says.

---

## Rules that bind

**Two-stage draft.** Ten rounds now, a second draft sized to the team
with the greatest need, padded with retired players that everyone drops.

**It fills roster spots. It does not fill starting slots** — see the
measured table above. Your empty RB2 has to come out of this draft.

**Four of your players are drafted-rookie eligible**: Brian Thomas,
Jayden Daniels, Kyle Williams, Oronde Gadsden. Two DR slots. Dropping any
destroys that eligibility permanently.

**Scoring is not PPR.** Tiered reception distance, first downs, half a
point per tight-end catch.

---

## Byes — the one thing to design around

Unlike your other league, this roster has a real cluster.

| week | out | available |
|---|---|---|
| 5 | 3 | 13 |
| **7** | **5** | **11** |
| 8 | 1 | 15 |
| 11 | 2 | 14 |
| **13** | **5** | **11** |

**Week 7 is the problem.** Lamar Jackson, Jayden Daniels and DJ Moore all
sit — that's both your quarterbacks in a superflex league in the same
week. Eleven bodies for nine slots is survivable, but you will start a
skill player at SUPER_FLEX.

No week forces a forfeit. But given two candidates of equal value, take
the one who isn't on bye in week 7 or 13.

---

## What this plan does not know

- **The other eleven rosters.** Static market.
- **`room_shave` is 0 by your word, not by measurement.** Run
  `room_bias.py` after Tuesday.
- **Whether the room drafts to market.** The draft-2 measurement above
  assumes the top 120 by depleted ADP come off the board. A room that
  reaches, or runs hard on one position, empties the tail differently.
  Rerun `draft2_probe.py` with a measured shave after Tuesday.
- **One season only.** Henry at 32 and Kelce at 36 look different in
  `dynasty_value.py`.
- **Depth charts move through preseason.**

---

## Morning-of checklist

1. `python br.py test` — 33 tests, all green
2. `python br.py roster` — confirm nobody dropped a keeper
3. `python br.py board 9000000000000000020` — the ranking
4. `python br.py lineup 9000000000000000020 --slot 6` — the sequencing
5. Confirm the board header says **REDRAFT 2QB/superflex** and reports
   ~80 players depleted. If it says DYNASTY, stop
6. Recheck Kyle Williams and Oronde Gadsden on depth charts
7. Re-check `/draft/9000000000000000021/traded_picks` — pick 90 is yours
   only as long as that trade stands
8. Confirm you're in league `9000000000000000020` before your first pick
