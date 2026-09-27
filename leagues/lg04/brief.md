# LG04 — draft card

**League `9000000000000000017`** · Sunday 9/6 · **slot 10 of 12** · 15 rounds
Written 9/2 off a pre-draft board with zero picks made.

Starters: QB1 RB2 WR2 TE1 **FLEX2** DEF1, bench 6. No kicker slot.
0.5 PPR, **6-point passing touchdowns**, kick and punt return yardage at
0.04, 100 FAAB. 2026 startup, nothing kept.

Your picks, if this is a plain snake: **10, 15, 34, 39, 58, 63, 82, 87,
106, 111, 130, 135, 154, 159, 178.**

---

## The pick numbers are confirmed

**Plain snake, no reversal round** — John, 9/3. So the list above is your
actual sequence, not an assumption, and it is recorded in
`leagues/_index.json` so nobody has to ask again.

Still worth one command on Sunday morning, because a slot can change and a
trade can move a pick:

    python br.py board lg04

---

## What the board actually says

Best player available at each of your picks, by points over replacement.
Computed from ADP, so read every cell as "the market says he is still
here," not as a promise.

| pick | RB | WR | TE | QB |
|---|---|---|---|---|
| 10 | **Cook 108.7** | Lamb 74.5 | Bowers 81.7 | Allen 69.6 |
| 15 | **Henry 104.8** | Nico Collins 70.6 | Bowers 81.7 | Allen 69.6 |
| 34 | **Saquon 92.7** | McConkey 41.0 | T. Warren 44.4 | Lamar 42.3 |
| 39 | Montgomery 57.3 | McConkey 41.0 | **T. Warren 44.4** | Lamar 42.3 |
| 58 | **Etienne 55.4** | P. Washington 34.7 | **LaPorta 39.3** | Maye 25.5 |
| 63 | **Etienne 55.4** | P. Washington 34.7 | Kraft 25.4 | Maye 25.5 |
| 82 | Tuten 27.2 | **P. Washington 34.7** | Pitts 19.0 | Herbert 5.0 |
| 87 | Tuten 27.2 | — | Kittle 18.3 | Herbert 5.0 |
| 106+ | Price 23.7 | — | Kincaid 12.4 | — |

The dashes are my data running out at the top thirty per position, not the
position running out.

Three things fall out of that grid.

**Running back is steep and receiver is flat.** Through pick 58 the back
column pays 20 to 50 more than the receiver column at the same pick. After
that they cross. Steep means waiting costs you; flat means waiting is
free. So buy backs early and receivers late, which is backwards from how a
half-PPR room usually drafts. Two flex slots are what let you get away
with it — you can start four backs.

**Tight end has one cliff and it sits between 58 and 63.** LaPorta at
ADP 61 is the last real one. At 63 the best left is Kraft, coming off an
ACL, fourteen points lower.

**Quarterback is nearly free.** Replacement is Jared Goff at ADP 94.

---

## The plan

| pick | take | why |
|---|---|---|
| **10** | **James Cook** (RB) | ADP 10.0, a coin flip on your own pick |
| | fallback: Chase Brown (RB, 90.1) | ADP 12, likelier to be there than Cook |
| | fallback: CeeDee Lamb (WR, 74.5) | if both backs are gone |
| **15** | **Derrick Henry** (RB, 104.8) | ADP 23. The second-best back on the board, priced eight picks after your turn |
| **34** | **Saquon Barkley** (RB, 92.7) | ADP 36. Same trick |
| **39** | **Ladd McConkey** (WR, 41.0) | ADP 50. Your first receiver |
| **58** | **Sam LaPorta** (TE, 39.3) | ADP 61, three picks of cushion. Do not leave here without a tight end |
| **63** | **Travis Etienne** (RB, 55.4) | ADP 75. The highest value at this pick at any position |
| **82** | **Parker Washington** (WR, 34.7) | ADP 83, one pick of cushion |
| **87** | **quarterback** | see below |
| **106, 111** | second receiver, backup QB | |
| **130, 135** | **Jadarian Price** (RB, 23.7) and one more young back | |
| **154, 159** | defense, bench flier | |
| **178** | rookie or handcuff | |

Cook, Henry, Saquon, Etienne is four backs for two dedicated slots and two
flexes, and Price makes five. That is on purpose. The fifth is trade
capital in a room that will be short at the position by week 4.

**The swap worth knowing:** Tyler Warren at 39 instead of McConkey, then a
receiver at 58. That is 44.4 + 34.7 against McConkey and LaPorta's
41.0 + 39.3. A point and a half apart. Take whichever is on the board and
do not spend clock on it.

---

## Quarterback: wait, and it is not close

| | ADP | over replacement |
|---|---|---|
| Josh Allen | 32 | +69.6 |
| Lamar Jackson | 49 | +42.3 |
| Drake Maye | 73 | +25.5 |
| Brock Purdy | 79 | +9.7 |
| Justin Herbert | 93 | +5.0 |
| Jared Goff | 94 | 0.0 |

Six-point passing touchdowns raise every quarterback's raw score, and the
projections already carry that. What six points does not do is widen the
gap between them, and the gap is the only thing you are buying.

Josh Allen at ADP 32 costs your pick 34, where Saquon is worth +92.7.
Paying 92.7 to get 69.6 is a 23-point loss, and it is the most expensive
mistake available to you on Sunday. Maye at 63 costs Etienne: 25.5 against
55.4, a 30-point loss. The same arithmetic holds at every pick until the
board runs out of anything better, which happens around 87.

Thirty-one quarterbacks project above 120 points here and twelve teams
need one. **Take yours at 87.**

What would flip this: quarterbacks going in a cluster. If four are gone
inside the first thirty picks, the tail thins faster than ADP says and
Maye at 63 becomes right. Count them; do not watch the clock.

---

## The 2027 keeper rule changes the last five rounds

Round-cost keepers start next year, and this is a startup, so nobody in
the room has one yet. A player you take in round 11 who turns into a
starter is a round 11 price in 2027.

That makes rounds 11 through 15 a different draft from rounds 1 through
10. Stop buying the veteran with the safer 2026 floor:

| | pos | age | ADP | over replacement |
|---|---|---|---|---|
| **Jadarian Price** | RB | 22 | 131 | +23.7 |
| Bhayshul Tuten | RB | 23 | 88 | +27.2 |
| Emeka Egbuka | WR | 23 | 77 | +26.4 |
| Luther Burden | WR | 22 | 57 | +24.4 |
| Rome Odunze | WR | 24 | 80 | +22.7 |

Price at 130 is the one I would not skip. Twenty-three points over
replacement in round 11 is startable production, and if it holds he is a
round 11 keeper next season.

---

## Defense

No kicker slot, so your last two picks are a defense and one flier rather
than both. LG04 pays 2 points for a fourth down stop, which none of
your other leagues do; the effect is too small to move a pick.

Stream it. Take whatever is left at 154 and check the week 1 matchup
Sunday morning. You have 100 FAAB and nothing to spend it on in week 1.

---

## What to distrust

- **The projections read 7 to 10 percent below the Sleeper app on
  purpose.** The app assumes every player plays every game; this applies
  the feed's availability discount. Measured 8/13 across nine
  quarterbacks: -0.7% before the haircut, -9.4% after.
- **Every ADP here is the redraft 1QB market**, which is the right one for
  this league, and it is a mean. A player at ADP 46 goes in a window, not
  on a pick. Cook at 10, Nico at 15 and Parker Washington at 82 are all
  inside one pick of your turn and are closer to coin flips than the table
  makes them look.
- **`room_shave` for LG04 is 0 and nobody has measured it.** There is no
  entry for this league in `keepers.json` and no prior at all. If the room
  reaches, every survival call above is optimistic. Run
  `python br.py rooms lg04` after Sunday and it stops being a guess.
- **Startup, so no keeper depletion.** Prices are the honest market here,
  unlike both Hybrids.
- **I did not price defenses.** The board has them; I did not pull them.
- **No other manager's roster is modelled.** A run on backs in rounds 3
  and 4 is invisible to all of the above, and two flex slots make a run
  likelier here than in a one-flex room.

---

## On the day

    python br.py board lg04          # confirm slot and pick numbers FIRST
    python br.py roster                 # rewrite roster.md, then read it
    python br.py watch lg04          # live, bells on your turn

The plan is a prior. Reread the board every pick.
