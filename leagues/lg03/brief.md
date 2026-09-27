# LG03 — draft card

> Named "LG03-LG05" when this card was written (8/13). Renamed in the app
> between 8/18 and 9/2; same league, same id. The league now named
> "LG05" is a DIFFERENT room — see leagues/lg05/.

**League `9000000000000000013`** · Tue Aug 18, 9:00 AM PT · slot 8 of 12
Rewritten 8/13 evening. Supersedes both earlier versions — see the bottom
for what changed and why every number under the old plan moved.

Your 11 picks (snake, **reversal at round 3** — these are not plain-snake
numbers): **8, 17, 29, 44, 53, 68, 77, 92, 95, 101, 116**
Pick 95 is traded in. 101 and 116 are taxi seats.

---

## Read this first

Everything below was rebuilt after the toolkit was pricing this league
off the wrong market. Until 8/13 the board read Justin Herbert at ADP
**90**. His real superflex price is **24.9**, and after keeper depletion
he goes around **7**. Every survival call on the old card was made
against 1QB prices in a room that starts two quarterbacks.

If a number here disagrees with something you remember, this is why.

---

## Pick 8 — settled: take the skill player

Counted 8/13 with `qb_supply.py`. **Do not take a quarterback at 8.**

The old card's premise was that the room would run on quarterbacks. It
will not. Twenty quarterbacks are already rostered across twelve teams in
a league with about twenty-two starting QB seats, so **roughly two seats
remain league-wide** and only one of them is yours — Jayden Daniels is
already your QB1.

Six quarterbacks project at or above this league's QB replacement level
of 320:

| | adp | proj | |
|---|---|---|---|
| Justin Herbert | 5 | 358 | gone before your first pick |
| Trevor Lawrence | 8 | 358 | your pick-8 option |
| Dak Prescott | 14 | 363 | gone by 17 |
| Jared Goff | 26 | 340 | **available at 17** |
| Kyler Murray | 40 | 320 | **available at 29** |
| Malik Willis | 48 | 328 | **available at 44 — the last one** |

Startable quarterbacks surviving each of your picks: **8 → 4, 17 → 3,
29 → 2, 44 → 1, 53 → 0.**

Spending pick 8 on Lawrence buys the same startable quarterback you can
have at 29 for nothing, and costs you Chase Brown at +165.

**Take Chase Brown (RB) at 8.** Pickens (+144) or Jeremiyah Love (+143)
if Brown is gone.

**Take your quarterback at 29 — Kyler Murray.** Waiting to 44 leaves one
candidate (Willis) against two league-wide seats. That is a coin flip you
do not need. If you would rather have Tyler Warren at 29, understand you
are betting pick 44 on Willis surviving.

**Do not take Daniel Jones at 44** even though `lineup_value` offers him
at +34. He projects 268, below the 320 line — not a startable superflex
quarterback here, and taking him leaves the seat effectively empty.

---

## The rest of the plan

From `lineup_value`, after whatever you take at 8:

| pick | take | note |
|---|---|---|
| 17 | Tee Higgins (+89) or Zay Flowers (+85) | both gone by 29 |
| 29 | **Kyler Murray (QB)** — see above | Tyler Warren (TE, +86) only if you take the pick-44 gamble |
| 44 | Jayden Reed (+53) | NOT Daniel Jones — 268 proj is below the 320 startable line |
| 53 | Alec Pierce (+14) | thin from here; everything is single digits |
| 68 | Mark Andrews or Kittle (+5) | **see the tight-end warning below** |
| 77 | Travis Kelce (+6) | |
| 92 | Jordan Mason (+2) | |
| 95 | Xavier Worthy (+0) | |
| 101 | **TAXI** Jonah Coleman (RB rookie) | will not play 2026 |
| 116 | **TAXI** Nicholas Singleton (RB rookie) | will not play 2026 |

### The tight-end warning

That plan drafts **three tight ends for one TE slot** — Warren at 29,
Kittle at 68, Kelce at 77. The second and third are worth five and eleven
points. Take Warren and then stop; spend 68 and 77 on a position you
actually start.

---

## Standing facts

- **Six of your nine starting slots are empty or below replacement.**
  That is why almost every candidate "displaces replacement WR" and why
  the board favours volume over upgrades. You are filling holes, not
  improving a lineup.
- **Two taxi seats.** Picks 101 and 116 are reserved for 2026 rookies who
  will not play this year. They cost no active spot, carry into next
  season free, and stay drafted-rookie eligible.
- **Cuts after the draft: Jalen Milroe, Brashard Smith.** Both are on the
  drafted-rookie eligible list with Colston Loveland and Jayden Higgins.
  **Dropping any of those four destroys that eligibility permanently** —
  it is not re-earnable, so a cut is a keeper decision.
  To see the board as if they were already gone:

      python br.py lineup 9000000000000000013 --slot 8 --drop "milroe,brashard smith"

- **Jayden Higgins is WR2 in Houston.** A real role. Do not plan to
  replace him.
- **Bye weeks are clean.** No week leaves you short of nine startable
  bodies. Nothing to design around.
- **`room_shave` is 0 here** — this room drafts close to market, on your
  word rather than measurement. Run `room_bias.py` after the draft to
  replace the prior with a number.

---

## What to distrust

- **`lineup_value` assumes a static market.** `qb_supply` tested that for
  quarterback and it holds — the room is nearly stocked, so no run is
  coming. It has NOT been tested for any other position.
- **The seat count assumes nobody has drafted yet.** It is the floor of
  the argument, not the whole of it, and ADP is odds, not a deadline.
- **One season only.** It knows nothing about age or 2027. Read it beside
  `dynasty_value.py`, never instead of it.
- **ADP is a distribution, not a deadline.** "Gone by 17" is odds.
- **Projections are availability-adjusted**, about 7–10% below what the
  Sleeper app shows. Neither is wrong; they answer different questions.

---

## What changed from the 8/11 card

1. **The market.** `adp_2qb` was silently resolving to 1QB prices because
   `_adp` only asked the per-player endpoint when nothing in the key
   chain matched the bulk feed — and `adp_dd_ppr` sits two keys later and
   always matches. Josh Allen read 29.0 against a real 1.2. Fixed 8/13.
2. **The keeper flag.** `board_data` priced this league as dynasty; it
   drafts as redraft, because everyone but the kept few churns. That
   alone was a 71-pick error on Derrick Henry.
3. **`keeper.py --board` said `QB:0/12 teams`** — a set-membership test
   that counted one quarterback as filling a superflex room. It now
   reports open slots and what the flex implies.
4. **The pick-8 recommendation reversed.** The old card said take a
   quarterback because the room would run on them. Counted: twenty are
   already rostered against about twenty-two seats, so two remain and no
   run is coming. Skill player at 8, quarterback at 29.
