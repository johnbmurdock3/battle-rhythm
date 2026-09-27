# Weekly research refresh — 2026-09-22

Full hybrid run, clean. Week 2 is played (Sept 20–21); Week 3 is upcoming.
All eight leagues report `in_season`, so there is no draft board to keep —
§6 is retired for the season unless a league reopens.

**Two league-state problems from 9/15 are both gone.** LG04
now returns a real roster from the API instead of `players: null`, and the old
LG06 league (9000000000000000022) returns a populated roster too, not
an empty one. `leagues/_index.json` is already correct on both — `lg06`
points at the old id, the 🪓 copy carries `ignore: true`. Nothing to fix.

One thing to eyeball: LG04's API roster is **not** the same 15 I
reconstructed from the picks feed last week. Lamar Jackson is on it; C.J.
Stroud and Saquon Barkley are not. Either moves happened, or last week's
picks-based reconstruction was wrong. The API roster is the one I researched.

---

## 1. NEW OR WORSENED INJURIES — rostered players

Ranked by what it costs you.

| Player | Team | Status | Where you roster him |
|---|---|---|---|
| **Jayden Daniels** | WAS | **Dislocated left elbow**, stepped on by a teammate vs DAL. No timetable. Marcus Mariota starts Week 3. [news 9/21] | LG05, LG03 |
| **Jayden Reed** | GB | **Out — back.** Ruled out, unlikely to play Thursday vs ATL. Christian Watson and Matthew Golden take his starting snaps. [news 9/21] | LG06, LG05, LG03 |
| **Jaxson Dart** | NYG | **Sprained MCL** in Week 2 vs LAR. X-rays negative, expected to miss a few weeks. Jameis Winston starts. | LG01 |
| **Jordan Mason** | MIN | **IR — thumb**, expected back Week 7. Did not appear in the Week 2 box score. | LG06, LG07, LG03 |
| **Eli Raridon** | NE | Left Week 2 vs PIT with a **thigh** injury and did not return, right after a 30-yard catch. No timetable. [news 9/21] | LG03 |
| **DJ Moore** | BUF | **Questionable Week 3** — shoulder, AC joint. [news 9/21] | LG05 |
| **James Conner** | ARI | Still **IR, foot**. Trey Benson also on IR (knee). One source has Conner back ~Week 5; unconfirmed. | LG05, LG04 |
| **A.J. Brown** | **NE** | Still IR, high-ankle. One source has him back ~Week 8. **And he is a Patriot now** — traded from PHI [news 8/30]. | LG03 |
| **Dylan Sampson** | CLE | IR since 9/15, knee, minimum four weeks. Raheim Sanders has his third-down work. | LG01 |
| **Mike Evans** | **SF** | Sleeper says Questionable; **no body part found anywhere.** Also a team change — he is a 49er, WR1 in a thin room (Pearsall out for the year). | LG06, LG07, LG05, LG02 |
| **Brian Thomas Jr.** | JAX | Playing through a wrist injury; also a shoulder issue in the Week 2 practice week. Cleared, played. | LG05 |
| **Saquon Barkley** | PHI | Stinger scare in Week 2, left briefly, returned. No injury tag as of today. | LG06 |
| **Jalen Coker** | CAR | Rolled ankle, boot was precautionary, expects no missed time. [news 9/16] | LG01 |
| **Brock Bowers** | LV | **Improving.** Practicing in Week 3, targeting a return Sunday vs NO. | LG07, LG02, LG01 |

**One flag I cannot resolve, and it touches a starting lineup.** **Alvin Kamara**
(NO, LG03-LG05): Sleeper's API says `Out` today, but he played Week 2 and led
Saints backs with 14 touches. Either it is a fresh Week 3 designation or it is
stale. **Check Sleeper directly before you set LG03-LG05.** [Guessing] on which.

**Corrections against last week.** Alec Pierce is **not** PUP and not out for
weeks — he is heel/Questionable for Week 3 and played Week 2. The report that
Indianapolis signed Darius Slayton does not hold up; he is not on their roster
or injury report. Two lesser conflicts: Sleeper tags **Wan'Dale Robinson**,
**Josh Downs**, **Sean Tucker**, **J.K. Dobbins** and **Tyler Bass**
Questionable, and none of them appear on their team's own Week 3 injury report.
Do not act on those tags.

**Team changes on your own rosters that the store did not have.** Beyond Brown
and Evans: **Kenny Gainwell → TB** (RB2 behind Bucky Irving, whom you also
roster), **Kenneth Walker III → KC**, **Adonai Mitchell → NYJ**,
**Rico Dowdle → PIT**, **Jalen Nailor → LV**, **Geno Smith → NYJ**,
**Devaughn Vele → NO**, **Jacoby Brissett → ARI QB1**, **Germie Bernard → PIT**.
Every one of these is now filed.

---

## 2. TRENDS

First honest trend read of the season — two game weeks in the same units, which
is what the 9/15 date fix was for. `D.trend()` over the last three observations,
direction reported only on 2+ points.

**Down, and it matters:**

- **Rhamondre Stevenson** touches **23 → 7**. TreVeyon Henderson out-touched him
  16–6 in Week 2. Sleeper still lists Stevenson RB1; the field does not agree.
  *LG01.*
- **Kenneth Walker III** touches **26 → 17** in his first two Kansas City games.
  Still the lead back, smaller week. *LG05.*
- **James Cook** touches **16 → 8**. *LG04.*
- **Travis Etienne** touches **16 → 10**, and see §3 — the cause is Kamara.
  *LG05, LG01.*

**Up:**

- **Bucky Irving** snaps **62% → 68.9%**, touches **15 → 21**. Bell-cow, 51
  snaps to the backup's 23. *LG03, LG01.*
- **Alvin Kamara** touches **0 → 14**, returning from the Week 1 absence.
  *LG05.*

**Two readings to throw out.** **Derrick Henry** prints "up" only because the
series starts at a preseason 0; Week 1 → Week 2 is **24 → 16**, which is down.
**Ray Davis** prints "down 58" against a May datapoint. Both are the same
artifact and both wash out next week.

---

## 3. ROLE CHANGES

**Against you:**

- **Travis Etienne (NO)** — last week's call reverses. Kamara played Week 2 and
  out-targeted him 6–2 (Kamara 14 touches, Etienne 10). Etienne no longer leads
  the passing-down work. *LG05, LG01.*
- **Rhamondre Stevenson (NE)** — the loaned lead role did not come back.
  Henderson is the back. *LG01.* See §2.
- **Sean Tucker (TB)** — not hurt; a healthy scratch, buried behind Irving and
  **Kenny Gainwell**, whom you also roster in LG04. Your own two players are
  what blocked him. *LG03.* Clean drop.
- **Kendre Miller (NO)** — tied for the team carry lead in Week 1, zero recorded
  stats in Week 2. *LG05, LG01.*
- **Nicholas Singleton (TEN)** — RB4 behind Pollard, Spears and Chestnut. Healthy
  scratch Week 1; four carries for ten yards in his Week 2 debut. *LG05.*
- **Tyrone Tracy (NYG)** — still the clearest drop on the sheet. Najee Harris is
  healthy and taking carries. *LG02.*

**For you:**

- **Aaron Jones (MIN)** — Jordan Mason to IR through ~Week 7 makes Jones an
  outright bell-cow: 23 carries, 105 yards, 82% of team carries in Week 2.
  *LG05.* Note you hold Mason in three other leagues; this is one
  player cutting both ways.
- **Khalil Shakir (BUF)** — last week's worry may invert. DJ Moore caught 0 of 1
  target in Week 2 and is Questionable with a shoulder. Shakir's own Week 2 was
  quiet (2/3/22), but the ceiling cap is loosening, not tightening.
  *LG04, LG03, LG01.*
- **Christian Watson (GB)** — 6 catches, 147 yards, 2 TD, and he moves into the
  starting lineup with Jayden Reed out. *LG04, LG02, LG01.*
- **Josh Downs (IND)** — 7 of 9 targets for 72 yards. Healthy, resolved.
  *LG01.*
- **Harold Fannin (CLE)** — confirmed TE1 on the depth chart. *LG04.*

---

## 4. NEWLY FLAGGED — available, and worth a claim

Pool source: **Sleeper trending adds (168h, top 100)**, not board rank. Board
tooling needs projections and network and does not run in this environment.

**Three are straight replacements for a player of yours who is out.**

1. **Matthew Golden (GB, WR)** — leads Green Bay in targets and yards through
   two weeks (6 tgt, 4 rec, 58 yds Week 2) and steps into Jayden Reed's starting
   spot. You hold Reed in three leagues and he is out Thursday. Best single claim
   on the board. [Certain on the role; Likely on Reed's absence lasting]
2. **Romeo Doubs (NE, WR)** — now a Patriot and their top perimeter receiver:
   3 rec on 4 targets for 96 yards in Week 2, with A.J. Brown on IR. You hold
   Brown in LG03. **Mack Hollins (NE)** is the cheaper version of the
   same bet.
3. **Tyler Allgeier (ARI, RB)** — **third week running as the top call and still
   unrostered.** Both backs ahead of him, Conner and Benson, are now on IR.
   Presumptive Week 3 lead back. His Week 2 line (5 car, 10 yds) predates the
   IR news and undersells him. You hold Conner in two leagues.

**Quarterback streams, forced by §1:**

- **Marcus Mariota (WAS)** — named the Week 3 starter with Daniels' elbow
  dislocated. Direct swap in LG03-LG05 and LG03. [Likely — sourced to
  a 9/21 report, not verified against a second source]
- **Jameis Winston (NYG)** — starts with Dart's MCL. *LG01.*
- **Tyler Shough (NO)** — 27/34 for 252 and 2 total TD in Week 2; 662 passing
  yards through two games. Not a stopgap, a starter.
- **Bryce Young (CAR)** — 23/36, 287, 3 TD, 0 INT in a 34–3 win.
- **Kirk Cousins (LV)** — 3 TD in Week 2, Raiders 2–0.
- **Drew Lock (SEA)** — Sam Darnold is listed **Out (glute)**, but nobody has
  explicitly named Lock the starter. Contingent.

**Next tier:**

- **Raheim Sanders (CLE, RB)** — second week running. RB2 behind Judkins with
  Sampson on IR; you hold Sampson.
- **Darren Waller (CAR, TE)** — Panthers TE1, two touchdowns in Week 2.
- **Rashod Bateman (BAL, WR)** — 9 targets, 7 catches, 88 yards, TD.
- **Tre Tucker (LV, WR)** — 5 of 7 for 119 and a score.
- **Xavier Hutchinson (HOU, WR)** — 9 targets, most among Houston receivers,
  65 snaps, with Nico Collins questionable (hamstring) for Week 3.
- **Roman Wilson (PIT, WR)** — moved to the X role, led Steelers WRs in targets.
- **Jacory Croskey-Merritt (WAS, RB)** — early-down work, 12 carries Week 2, but
  Rachaad White owns the receiving back role 6 targets to 1.
- **Michael Mayer (LV, TE)** — case is **weakening**, not strengthening. Bowers
  is practicing and targeting Sunday.

**Off every board:** **Josh Jacobs (GB)** is unchanged — still Reserve/
Commissioner's Exempt, no investigation update, GM "hopeful" with no timeline.
**Tyreek Hill** is still unsigned and may not be cleared to play at all in 2026.
**Demarcus Robinson (SF)** is headed for IR with a high ankle sprain.
**Caleb Douglas (MIA)**, last week's rookie riser, hurt his ankle in Week 2 and
wore a boot postgame — do not chase him.

---

## 5. STILL OPEN — carried from prior weeks

**172 dossiers carry an unresolved question, 39 of them rostered**
(9/15: 163 / 37. 9/3: 77 / 5). By flag: 133 WATCH, 33 BLOCKED, 31 INHERITING.

**115 of the 172 are open only on `thin reporting`** — the same heuristic
artifact as last week, now slightly smaller. **Strip it and the real number is
57 open, 13 rostered**, against 50 / 11 last week. That is the honest move: up
two.

The 13 substantive rostered, with weeks open:

| Player | Why | Weeks open |
|---|---|---|
| A.J. Brown | IR | 3 |
| James Conner | IR; Benson also out | 3 |
| Jayden Higgins | ACL, season | 3 |
| Khalil Shakir | target competition | 3 |
| Rhamondre Stevenson | sources conflict | 3 |
| Eli Raridon | new thigh injury, no timetable | 3 |
| Chuba Hubbard | Brooks out | 3 |
| Christian Watson | Doubs departed | 3 |
| Alec Pierce | **flag is stale** | 3 |
| Josh Downs | **flag is stale** | 3 |
| Dylan Sampson | IR | 2 |
| Jayden Daniels | elbow, no timetable | **new** |
| Kansas City DEF | Norman-Lott ACL/PUP | **new** |

**Two of these should be closed by hand.** The `opportunity_flags` reasons for
**Alec Pierce** and **Josh Downs** are "the other one is on PUP" — pointing at
each other, both derived from `stable.notes` that predate the season. Both
played Week 2; Downs drew 7 of 9 targets. The research resolved them; the flag
reads stale notes, so `refresh_list` will keep re-flagging them every week until
someone edits those notes. Same shape for **Khalil Shakir**, whose flag says
"DJ Moore gone (traded to)" — Moore is now his teammate, not his departure.

**This is a mechanism worth fixing, not a per-player chore.** `opportunity_flags`
reads `stable.notes`, which a weekly observation never updates. Anything filed
there in August is permanent until hand-edited.

The three past-26-week dossiers (**DeMario Douglas**, **Chris Manhertz**,
**Theo Wease**) were flagged for retirement on 9/3 and again on 9/15. Still
there, still open, third ask.

---

## 6. DRAFT WATCH

Retired for the season. All eight leagues are `in_season` and both league-state
defects from 9/15 have cleared — see the header.

---

## RUN NOTES

- **Mode: hybrid, clean.** Device mounted at Step 0, Python 3.10.12, snapshot
  staged in one call. No bridge drops.
- **Leagues covered: 8.** Seven registered plus `lg08`
  (`ignore: true`), which returns the same 16 players as the real league.
- **Leagues with no roster: 0.** First week with all eight readable.
- **Candidates: 291. Researched: 291. Unresearched: 0.** 97 unique rostered
  across 8 leagues + 100 trending adds + 197 dossiers carrying an open question,
  deduped by `D.refresh_list(rostered, trending, days=7)`. No cap, no trimming.
- **Observation gate: 291 of 291 carry a today-dated observation.** 0 validation
  errors across all 291 documents. Observations dated the **run** date with news
  dates preserved in-note as `[news YYYY-MM-DD]`, per the 9/15 fix — that is
  what made §2 possible and it should keep being done this way.
- **Identity check: 0 name mismatches** between the research output and the
  store across all 291, and 4866/4881 were re-verified explicitly after the 9/15
  Barkley/Jackson swap. Two unnamed store entries resolved: 12556 = Donovan
  Ezeiruaku (DAL DL), 5189 = Eddy Pineiro (SF K), 7042 = Tyler Bass (BUF K),
  13379 = Josiah Trotter (TB LB).
- **Pool source: Sleeper trending adds** (168h lookback, top 100). Not board rank.
- **WebSearch was exhausted session-wide** partway through wave 2 of 21 research
  agents. Waves 2 and 3 ran on WebFetch only, against the Sleeper players API,
  ESPN's `site.api.espn.com` JSON endpoints, CBS Sports team injury pages (all
  dated 9/21) and FantasyPros. Google, Bing, DuckDuckGo and pro-football-
  reference are all blocked to WebFetch. **Cost: snap share and route
  participation are null almost everywhere this week** — §2 runs on touches,
  which is the one field box scores reliably gave up. Worth budgeting searches
  across the run next time rather than letting the first eight agents spend them.
- **Invented facts caught and discarded at the source, again:** a CBS page
  serving Derrick Henry's December 2025 line (36/216/4) as Week 2; an ESPN
  boxscore feed reporting Jared Goff 1-for-1; an Atlanta injury report containing
  Miami and Washington players; a KC game stuck "in progress 27–27" after it was
  final. The one-line-per-fact extraction rule is still earning its keep.
- **Team defenses are the weak spot.** The ESPN scoreboard endpoint truncated its
  events array on repeated fetches, so Week 2 points-allowed is unresolved for
  DAL, GB, JAX, LAC, LV, SF and TB, and SF's Week 3 opponent could not be
  resolved at all. Your three rostered defenses (DAL, KC, LAC) have injury data
  but incomplete scoring data.
- **Not committed to git.** Constraint J (the `index.lock` problem) makes git
  writes on this mount a one-way door and nothing here needed it. `dossiers/`
  and `reports/` are dirty and ready if you want the commit.
