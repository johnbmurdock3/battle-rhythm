# LG02 — draft card

**League `9000000000000000011`** · date not set · **slot 13 of 14** · 13 rounds
Written 9/2 off a pre-draft board with zero picks made. First card this
league has ever had.

Starters: QB1 RB2 WR2 TE1 FLEX1 **K1 DEF1**, bench 4.
0.5 PPR, 4-point passing touchdowns, **waiver order rather than FAAB**.
No keeper rules; nothing on file in `keepers.json` and nothing needed.

Your picks, if this is a plain snake: **13, 16, 41, 44, 69, 72, 97, 100,
125, 128, 153, 156, 181.** **Plain snake, no reversal round** — John, 9/3, and recorded
in `leagues/_index.json`. Still run `python br.py board lg02` on the day:
a slot can change and a traded pick moves the list.

---

## This draft is not like your others

Three structural facts, and every recommendation below comes out of them.

**You pick in pairs.** Slot 13 of 14 puts your picks three apart: 13 and
16, then 41 and 44, then 69 and 72. Twenty-eight picks pass between pair
and pair, and only two inside one. That inverts the usual rule. Inside a
pair you can take the player who will not survive three picks and bank the
one who will; between pairs you cannot bank anything.

**Two of your thirteen picks are a kicker and a defense.** No other league
of yours makes you spend picks on both. Eleven picks for seven skill
starters and four bench spots.

**Thirteen quarterbacks project above replacement and fourteen teams need
one.** One team in this room starts a quarterback worth less than nothing.
Do not let it be you. This is the single biggest difference from LG04,
where quarterback is nearly free.

---

## What the board says

Best available at each pick, points over replacement, priced off ADP.

| pick | RB | WR | TE | QB |
|---|---|---|---|---|
| 13 | Henry 104.8 | Nico 65.8 | **Bowers 81.7** | Allen 72.1 |
| 16 | **Henry 104.8** | London 55.2 | Bowers 81.7 | Allen 72.1 |
| 41 | **Montgomery 57.3** | Evans 34.6 | T. Warren 44.4 | Lamar 46.0 |
| 44 | Swift 55.5 | **Evans 34.6** | T. Warren 44.4 | Lamar 46.0 |
| 69 | **Etienne 55.4** | Egbuka 21.6 | Kraft 25.4 | Maye 28.2 |
| 72 | Etienne 55.4 | Egbuka 21.6 | Pitts 19.0 | **Maye 28.2** |
| 97+ | Price 23.7 | out of data | Kittle 18.3 | **nothing above replacement** |

"Out of data" is my top thirty per position running out, not the position.
"Nothing above replacement" at quarterback is real.

---

## The plan

| pick | take | why |
|---|---|---|
| **13** | **Brock Bowers** (TE, 81.7) | ADP 17, so pick 16 is a coin flip on him and 13 is not |
| | fallback: Nico Collins (WR, 65.8) | ADP 15, same logic, lower number |
| **16** | **Derrick Henry** (RB, 104.8) | ADP 23. Seven picks of cushion — the safest big number on your board |
| | fallback: Kenneth Walker (85.2) or Hampton (81.0) | both priced past 16 as well |
| **41** | **David Montgomery** (RB, 57.3) | ADP 41, right at your pick |
| **44** | **Mike Evans** (WR, 34.6) | ADP 54. Your first receiver — see the receiver problem below |
| | alternative: D'Andre Swift (RB, 55.5) | 21 more points and it makes the receiver problem worse |
| **69** | **Travis Etienne** (RB, 55.4) | ADP 75. Best value at this pick at any position |
| **72** | **Drake Maye** (QB, 28.2) | ADP 73, one pick of cushion. **Do not push this later** |
| | fallback: Dak Prescott (14.4, ADP 72) | if Maye goes at 70 or 71 |
| **97, 100** | second receiver, fourth back | |
| **125, 128** | bench: handcuff your own backs | |
| **153, 156** | **kicker and defense** | |
| **181** | flier | |

That is Bowers, Henry, Montgomery, Evans, Etienne, Maye through six picks:
tight end, three backs, one receiver, one quarterback. It fills the flex
with a back and leaves receiver thin on purpose.

---

## The receiver problem, stated plainly

You will not have good receivers, and neither will anybody else.

Fourteen teams starting two receivers plus a flex drains the position
before your second pair. The best receiver available at 44 is Mike Evans
at 34.6 and he is 33 years old with a foot. At 69 the best is Egbuka at
21.6. There is no version of this draft where you leave with two receivers
you are happy about.

The choice at 44 is between Swift at 55.5 and Evans at 34.6 — 21 points to
take a fourth back instead of your first receiver. Take the receiver. The
21 points are real but they sit in a flex slot you can fill from the wire,
and this league has waiver order rather than FAAB, so you cannot buy your
way out of a hole in week 3.

What would flip this: if a run on backs empties the position by 41. Then
Swift at 44 is the last real back and you take him and live with receivers
off the wire.

---

## Quarterback: pick 72, and not later

| | ADP | over replacement |
|---|---|---|
| Josh Allen | 32 | +72.1 |
| Lamar Jackson | 49 | +46.0 |
| Drake Maye | 73 | +28.2 |
| Jayden Daniels | 64 | +27.3 |
| Jalen Hurts | 55 | +26.3 |
| Brock Purdy | 79 | +12.1 |
| Justin Herbert | 93 | +10.9 |
| Bo Nix | 81 | +3.1 |

The list ends at Nix. That is thirteen names for fourteen teams.

At pick 97 there is nothing above replacement left, so the honest read is
that quarterback here is a real cost, not the free slot it is in LG04.
Maye at 72 is the last one worth more than twenty points, and his ADP of
73 gives you exactly one pick of room.

Lamar at 44 is the aggressive version: +46.0 instead of +28.2, paid for
with Mike Evans. Eighteen points to make the receiver problem worse. I
would not, but it is close enough that if Evans is gone at 44 the answer
flips.

---

## Kicker and defense

Both are required starters and both are last-round picks. The turn plan
used to print "starters filled" while one of them sat empty; that was
fixed 9/2 and the banner now names the slot. If you see it claim you are
done before picks 153 and 156, something regressed.

Take them at 153 and 156. Neither is worth a pick before that, and neither
is worth thinking about on the day.

---

## The bench is four deep and there is no FAAB

Four bench spots across a 14-team room, and waivers run on order rather
than money. You cannot outbid anyone for a breakout, and you cannot stash.

That makes rounds 10 through 12 the opposite of LG04's. No lottery
tickets, no rookies you hope earn a role in November. Take the backup to
your own starting back and a receiver who is playing in week 1. The value
of a bench spot here is insurance, not upside.

---

## What to distrust

- **The projections read 7 to 10 percent below the Sleeper app on
  purpose.** Availability discount; measured 8/13 across nine
  quarterbacks.
- **ADP is the redraft 1QB market and it is a mean.** Bowers at 17 against
  your pick 13, Montgomery at 41 against your 41, and Maye at 73 against
  your 72 are all inside a pick or two. Treat them as likely, not certain.
- **`room_shave` is 0 here and it has never been measured.** Fourteen-team
  rooms tend to reach earlier than twelve-team rooms because the talent
  runs out sooner, and nothing in the data says whether this one does. Run
  `python br.py rooms lg02` after the draft.
- **The receiver numbers past pick 72 are missing, not zero.** I pulled the
  top thirty per position and the position has 53 players above 120 points.
- **No other roster is modelled.** In a 14-team room that matters more, not
  less.
- **The draft date is not set.** Whenever it lands, rerun the board — three
  weeks of injury news moves more than the plan does.

---

## On the day

    python br.py board lg02             # confirm slot and pick numbers FIRST
    python br.py roster                 # rewrite roster.md, then read it
    python br.py watch lg02             # live, bells on your turn

The plan is a prior. Reread the board every pick.
