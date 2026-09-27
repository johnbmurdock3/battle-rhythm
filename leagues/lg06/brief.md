# LG06 — draft card

**League `9000000000000000021`** · **Wed Sep 9, 5:00 PM PT — one week out**
10 teams · 16 rounds · plain snake · redraft · FAAB 100 · playoffs week 15

Starters: QB1 RB2 WR2 TE1 FLEX1 **K1 DL1 LB1 DB1**, bench 5.
Eleven starting slots, five bench. Carries a kicker and individual
defenders; no team defense.

Rewritten 9/2, slot handling rebuilt 9/3. **Your draft position lands
about 30 minutes before the draft** — John's word, and it shapes this
whole card. Everything below works without a slot; the table in the next
section turns a slot into pick numbers in the time it takes to read one
row.

That is also the right shape for this league regardless, because there is
no usable market here to price survival against.

---

## You get your slot 30 minutes before the draft

That is the curveball here, per John 9/3, and it is why this card is built
the way it is: nothing below needs a slot until the last half hour, and the
half hour is already done for you.

**Plain snake, no reversal.** 10 teams, 16 rounds, 160 picks. When the slot
lands, read one row.

| slot | your 16 picks |
|---|---|
| 1 | 1, 20, 21, 40, 41, 60, 61, 80, 81, 100, 101, 120, 121, 140, 141, 160 |
| 2 | 2, 19, 22, 39, 42, 59, 62, 79, 82, 99, 102, 119, 122, 139, 142, 159 |
| 3 | 3, 18, 23, 38, 43, 58, 63, 78, 83, 98, 103, 118, 123, 138, 143, 158 |
| 4 | 4, 17, 24, 37, 44, 57, 64, 77, 84, 97, 104, 117, 124, 137, 144, 157 |
| 5 | 5, 16, 25, 36, 45, 56, 65, 76, 85, 96, 105, 116, 125, 136, 145, 156 |
| 6 | 6, 15, 26, 35, 46, 55, 66, 75, 86, 95, 106, 115, 126, 135, 146, 155 |
| 7 | 7, 14, 27, 34, 47, 54, 67, 74, 87, 94, 107, 114, 127, 134, 147, 154 |
| 8 | 8, 13, 28, 33, 48, 53, 68, 73, 88, 93, 108, 113, 128, 133, 148, 153 |
| 9 | 9, 12, 29, 32, 49, 52, 69, 72, 89, 92, 109, 112, 129, 132, 149, 152 |
| **10** | 10, 11, 30, 31, 50, 51, 70, 71, 90, 91, 110, 111, 130, 131, 150, 151 |

**Do not read a slot off Sleeper before it publishes.** The placeholder
`draft_order` produced a confident, fictional "slot 4 of 10" once already.
When it lands, confirm with the tool rather than the table:

    python br.py board lg06

### The 30 minutes, in order

1. `python br.py board lg06` — confirms the slot and the pick numbers.
2. Find your row above. The only thing it changes is **round 1**.
3. `python br.py roster` — first run ever against a K + DL/LB/DB roster.
   Do it now, not at pick 8.

### What your row actually changes

Almost nothing, and that is the point. Two of the three big calls below
are slot-independent.

**Slots 1–4.** You get one of the four backs above 140 — Gibbs (+223),
Bijan (+211), McCaffrey (+160), Taylor (+143). Take him. Josh Allen at
round 2.

**Slots 5–8.** Henry (+136), Cook (+131), Chase (+121) and Saquon (+120)
are the band. All four beat Allen's +112, so take the skill player and
Allen at round 2.

**Slots 9–10.** Your two picks are back to back (9 and 12, or 10 and 11),
and the board there is Allen (+112), Nacua (+111), Chase Brown (+105),
Achane (+101), Bowers (+99). Take two of them. This is the best draw on
the board, not the worst — the wheel hands you a quarterback worth a first
and a second asset one pick later.

## Why every instinct from your other leagues is wrong here

Touchdowns are 10 points, not 6. Passing yards 0.05. Full PPR. Turnovers
−5. Yardage bonuses at 100 and 200 rushing and receiving, 300 and 400
passing. And the one nothing else you play has: **0.5 per pass attempt and
0.5 per rush attempt.**

Volume pays before efficiency does. A 600-attempt quarterback banks 300
points before he throws for a yard. That is why the projections here look
absurd next to your other cards — Josh Allen at 702, Lamar at 644 — and
why the position order is different.

---

## The three things that decide this draft

### 1. Josh Allen is a first-round pick here

| | proj | over replacement |
|---|---|---|
| **Josh Allen** | 702.0 | **+111.7** |
| Lamar Jackson | 644.0 | +53.7 |
| Joe Burrow | 635.0 | +44.7 |
| Drake Maye | 620.9 | +30.6 |
| Jayden Daniels | 620.3 | +30.0 |
| Bo Nix | 590.3 | 0.0 |

That +111.7 is the ninth-best number on the entire board, ahead of Puka
Nacua and every receiver alive. His generic ADP is 32.

Ten quarterbacks sit above replacement and ten teams need one, so the
position is exactly exhausted — there is no free quarterback at the end of
this draft the way there is in LG04.

The gap between Allen and Lamar is 58 points. The gap between Lamar and
the tenth quarterback is 54. One player is worth more than the entire rest
of the position's spread.

**Round 2, from any slot.** Eight players beat his +111.7 — Gibbs,
Bijan, McCaffrey, Taylor, Henry, Cook, Chase and Saquon — and in a
10-team room all eight are gone inside round 1. So round 1 takes whoever
your slot hands you and round 2 takes Allen, unless you pick 9th or 10th,
where he may be the best player on the board at your first pick.

**Do not wait for round 3.** His generic ADP is 32, which is round 4 here,
and that price was set in rooms that pay 4 points for a passing touchdown
instead of 10 and nothing per attempt. If one manager in this league has
read the scoring settings, Allen does not reach round 3. Paying a round-2
pick for the ninth-best number on the board is not a reach.

### 2. Aidan Hutchinson, and nobody in the room has a price for him

| | over replacement |
|---|---|
| **Aidan Hutchinson** | **+70.4** |
| Tuli Tuipulotu | +34.1 |
| Jared Verse | +33.2 |
| Will Anderson | +27.2 |
| Austin Booker | +23.5 |
| Abdul Carter | +19.8 |
| Boye Mafe | +12.6 |
| Laiatu Latu | +7.8 |
| Yaya Diaby | +1.1 |
| Byron Murphy | 0.0 |

Ten defensive linemen above replacement. Ten teams. The position empties
exactly, and Hutchinson is worth double the second name.

**No defender in this league carries an ADP at all.** That cuts both ways:
you cannot price his survival, and neither can anyone else. In a room
drafting off a generic app board, defenders go late by habit. In a room
that has played IDP before, Hutchinson goes in round 3.

His +70.4 ranks twentieth overall. **Take him in round 3, from any slot.**

Here is why that is nearly free. The best offensive player left at your
round-3 pick is worth about +60 — Montgomery at +60.4, Loveland at +59.8,
Javonte at +67.8 if he lasts. Hutchinson is +70.4. So you are not paying
anything to take him; you are taking the best player on the board and
happening to fill a scarce slot with him.

Then compare the alternative. Wait, and your defensive lineman is
Tuipulotu at +34.1 or Verse at +33.2. That is a 36-point positional edge
nobody in the room can replicate, bought at no cost against the offensive
board.

**Do not be the person who waits until round 8 to find out which kind of
room this is.**

### 3. Linebacker and defensive back are free

Above 120 points: **DL 20, LB 79, DB 69.**

Seventy-nine linebackers for ten starting slots. The tenth-best is not
meaningfully worse than the twentieth. Take both in the last three rounds
and spend nothing earlier on either.

This is the whole IDP strategy in one line: **one position is scarce and
two are not.** Buy the scarce one early and let the other two come to you.

---

## Priority order

Positions in the order the board says they are worth taking. Slide the
whole thing to fit whatever slot publishes.

| round | take |
|---|---|
| 1 | the best skill player in your slot band above — only slots 9–10 should be taking **Josh Allen** here |
| 2 | **Josh Allen**, from every slot, if you do not already have him |
| 3 | **Aidan Hutchinson** |
| 4–5 | running backs — Henry (+135.9), Saquon (+120.2), Chase Brown (+104.8), Achane (+100.9) all price past round 3 on generic ADP |
| 6 | **Brock Bowers** (+99.3) or **Trey McBride** (+73.0) — the tight end cliff falls off hard after McBride |
| 7–9 | receivers. Chase (+121.1) and Nacua (+110.7) go early; after them the position is flat and deep at 66 above the line |
| 10–12 | flex, bench, second running back tier |
| 13 | **DL2** as insurance if Hutchinson is your only lineman |
| 14–15 | **linebacker and defensive back** |
| 16 | **kicker** — 29 above the line, it does not matter which |

**Do not take a defender before round 13 other than Hutchinson.** Verse
and Tuipulotu at +33 are worth less than a fourth running back, and the
tenth linebacker costs a sixteenth-round pick.

---

## What to distrust

- **ADP here is not this league's market.** The app shows Josh Allen at
  19.1 and the feed says 29; no defender carries one at all. Every ADP in
  this card is the generic redraft 1QB market, which describes a room that
  does not score touchdowns at 10 points or pay per attempt. **Draft off
  the VORP column and the scarcity counts, not off survival flags.**
- **IDP carries about 12% inflation against offence.** Mean availability
  ratio is 1.039 for DL/LB/DB against 0.926 for QB/RB/WR/TE. Defenders all
  move together, so the ranking within IDP holds; only IDP-versus-offence
  tilts, and it tilts toward defenders. Hutchinson's +70.4 is probably
  nearer +62 against offence. It does not change the call.
- **Projections read 7 to 10 percent below the Sleeper app on purpose.**
  Availability discount, measured 8/13 across nine quarterbacks.
- **Do not use `br.py lineup` here.** This is redraft with an empty roster,
  so marginal value against an empty lineup collapses to raw projection. It
  offered six quarterbacks for a one-quarterback league before the guard
  went in.
- **`roster_snapshot` has never been run against a K + DL/LB/DB league.**
  Run it once before draft day so the first time it sees this roster shape
  is not mid-draft.
- **No kicker strategy exists anywhere in the toolkit**, and at 29 above
  the line it does not need one.
- **The draft date needs confirming.** The prior handoff said Thursday
  9/10 and this file says Wednesday 9/9; 9/9 is the Wednesday. Check the
  app.

---

## Before draft day

    python br.py board lg06            # does a slot line appear yet?
    python br.py board lg06 --pos DL   # has anything moved at the top
    python br.py roster                 # first run against a K + IDP roster
    python br.py idp                    # the IDP sanity probe

The plan is a prior. Reread the board every pick.
