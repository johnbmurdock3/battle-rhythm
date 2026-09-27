# Weekly research refresh — 2026-09-15

Full hybrid run. The repo folder was **not** mounted at Step 0 and the run
started cloud-only; the folder-access prompt was approved on `zbookmurdock`
partway through, so the dossier half completed normally. Store 494 → 509.

NFL state: Week 1 is played (games Sept 13–14). Week 2 is upcoming.

Leagues are named, not slugged. The API now returns **eight** leagues, all
`in_season` — one more than the seven on record.

---

## 1. NEW OR WORSENED INJURIES — rostered players

Ranked by what it costs you.

| Player | Team | Status | Where you roster him |
|---|---|---|---|
| **James Conner** | ARI | IR, right foot, surgery. No return date. Trey Benson also on IR. | LG05 |
| **Jayden Higgins** | HOU | Torn ACL (Aug 18). Out for the season. | LG03 |
| **A.J. Brown** | NE | High-ankle sprain, IR ~9/11. Min 4 games, back ~Week 6. | LG03 |
| **Dylan Sampson** | CLE | Knee, Week 1. Left after 2 snaps, out significant time. | LG01 |
| **Devin Neal** | — | Waived by NO 9/3, season-ending hamstring. **No NFL team.** | LG05 |
| **Brock Bowers** | LV | Knee meniscus trim 9/9, out 1–2 games. Schefter 9/14: realistic chance to play Week 2. | LG07, LG02, LG01 |
| **Alvin Kamara** | NO | MCL sprain. Practiced fully, still held out Week 1. | LG05 |
| **Sean Tucker** | TB | Hamstring, inactive Week 1. Targeting Week 2. | LG03 |
| **Jalen McMillan** | TB | Lower-body since early Aug, inactive Week 1. Sources split calf vs knee. | LG07 |
| **Jalen Coker** | CAR | Ankle, walking boot postgame, expects to play. | LG01 |
| **Jordan Mason** | MIN | Sore thumb, under evaluation (9/14). | 🪓 LG06, LG07, LG03 |
| **Josh Downs** | IND | Sleeper says Questionable; he played Week 1. Tag unexplained. | LG01 |
| **TreVeyon Henderson** | NE | Ankle — **improving.** Practiced 9/14, first time since 8/24. | LG01 |

**Two corrections against last week.** Jalen Coker was filed 9/3 as *quad, IR,
out through Week 4*. He is not on IR — he played Week 1 and picked up a minor
ankle tweak. And Chuba Hubbard's hamstring, flagged then as likely to linger,
did not: he took 13 touches and scored twice.

**Four stale Sleeper flags. Do not act on any of them** — each is contradicted
by a dated source:

- **Jayden Daniels (WAS)** — Sleeper says `Out`. Carryover from a Dec 2025 elbow
  injury. He started Week 1 and threw 2 TDs. [Certain]
- **Khalil Shakir (BUF)** — `Questionable` from 8/20; not on the Week 1 injury report.
- **Wan'Dale Robinson (TEN)** — `Questionable/Head` from early Aug; cleared 9/9,
  played 82% of snaps.
- **Alec Pierce (IND)** — `Questionable/hand` and the store still carries `PUP`;
  he played a full workload and led the Colts in receiving yards.

---

## 2. TRENDS

**Nothing reportable.** `D.trend()` found only two rostered series with two or
more numeric points, and both compare an offseason datapoint to a Week 1 game:
Ray Davis `touches 58 → 1` (the 58 is dated 2026-05-03) and Derrick Henry
`touches 0 → 24` (the 0 is dated 2026-08-29, preseason). Neither is slope.

This run is the first to write in-season numeric fields. **Next week is the
first honest trend read** — two game weeks, same units.

One mechanical fix made this possible and is worth knowing about. See RUN NOTES,
"the date fix."

---

## 3. ROLE CHANGES

**Against you:**

- **Tyrone Tracy (NYG)** — demoted to RB3. Fumbled on his second carry, benched
  the rest of Week 1. Skattebo is healthy and scoring; Singletary is ahead of
  Tracy too. *LG02.* Clearest drop candidate on the sheet.
- **Khalil Shakir (BUF)** — Buffalo traded for DJ Moore, who played 75% of snaps
  to Shakir's 54%. Target ceiling capped. *LG03, LG01, LG04.*
- **Rhamondre Stevenson (NE)** — 85% of snaps with Henderson hurt. Henderson
  practiced 9/14. The lead role is on loan. *LG01.*
- **Brashard Smith (KC)** — KC signed Kenneth Walker; Smith is RB3. *LG05.*

**For you:**

- **Travis Etienne (NO)** — led passing-game work at 53% of snaps with Kamara out.
  Share should rise. *LG05, LG01.* Last week's call held.
- **Kenneth Walker (KC)** — 26 touches, 173 yards, 2 TD at 69% snaps. *LG05.*
- **Colston Loveland (CHI)** — Bears TE1 over Kmet, 100% of third-down snaps,
  65 snaps and 35 routes. The 0-catch line is noise; the usage is real.
  *🪓 LG06, LG03.*
- **Harold Fannin (CLE)** — now CLE's TE1 on the depth chart. David Njoku is
  absent from the chart entirely, reason unconfirmed. *LG04.* [Likely]
- **Pat Bryant (DEN)** — team-high 6 targets. *LG01.*

---

## 4. NEWLY FLAGGED — available, and worth a claim

Pool source: **Sleeper trending adds (168h)**, not board rank. Board tooling
needs projections and network and does not run here.

**Two claims are straight replacements for players you roster who are out.**

1. **Tyler Allgeier (ARI, RB)** — 17 carries Week 1. Arizona has *both* Conner
   (foot, IR) and Benson (knee, IR) out. Workhorse by default, and you hold
   Conner in LG05. **This was also the top call on 9/3 and he is still
   unrostered** — two weeks running, so either the league is not reading or
   someone is about to. [Certain on usage; Likely on duration]
2. **Raheim Sanders (CLE, RB)** — took over for Dylan Sampson, who you hold in
   LG01. 4 touches plus a 74-yard kick return, and Cleveland expects
   to give him more.

**Next tier:**

- **Devaughn Vele (NO, WR)** — 7 of 9 targets, 69 yards, TD. WR2 behind Olave
  with Jordyn Tyson on IR ~2 months. Most-cited Week 2 add.
- **Kaelon Black (SF, RB)** — 43.8% of snaps, 14 of 24 backfield carries on debut.
- **Caleb Douglas (MIA, WR)** — 86.5% route participation, 7 targets, as a rookie.
- **Carson Wentz (MIN, QB)** — Kyler Murray in concussion protocol, called less
  than 50/50. Wentz threw 3 TDs in relief.
- **Drew Lock (SEA, QB)** — Darnold's hip ended his day on the first drive; Lock
  won the game and Darnold is doubtful.
- **Michael Mayer (LV, TE)** — only if Bowers' return slips past Week 2.

**Off every board:** **Josh Jacobs (GB)** is on the Reserve/Commissioner's
Exempt list amid an NFL investigation, off the depth chart entirely — new since
9/3 and a real problem for anyone holding him. **Tyreek Hill** is still an
unsigned free agent who said in late July he has no power in his left leg.

---

## 5. STILL OPEN — carried from prior weeks

**163 dossiers carry an unresolved question, 37 of them rostered**
(9/3: 77 open, 5 rostered). By flag: 123 WATCH, 25 INHERITING, 24 BLOCKED.

**Read that jump carefully — most of it is an artifact, not news.** 113 of the
163 are open *only* on `thin reporting`, including Justin Jefferson, Derrick
Henry and Lamar Jackson, who are plainly healthy starters with full Week 1 lines.
The count rose because this run wrote text into 166 dossiers that previously had
little, and the WATCH heuristic reads sparse fields as thin coverage.

**Strip that and the real number is 50 open, 11 rostered** — up from 5, which is
the honest week-over-week move.

The 11 substantive rostered: **A.J. Brown** (IR), **Jayden Higgins** (ACL),
**Devin Neal** (season-ending, no team), **Alec Pierce** (store still says PUP —
stale, see §1), **James Conner** (Benson also out), **Josh Downs** (inheriting,
Pierce), **Khalil Shakir** (DJ Moore arrived), **Rhamondre Stevenson** (Gibson
released, Henderson returning), **Christian Watson** (Doubs departed), **Chuba
Hubbard** (Brooks out), **Eli Raridon** (Julian Hill out).

Carried from 9/3 and still unresolved: **Sean Tucker**, **Josh Downs**,
**Khalil Shakir**, **Rhamondre Stevenson**, **Eli Raridon** — all five, now
**two weeks open**. The three past-26-week dossiers the 9/3 report recommended
retiring (DeMario Douglas, Chris Manhertz, Theo Wease) were not retired and are
still open.

---

## 6. DRAFT WATCH

All eight leagues report `in_season`, so there is no pre-draft board to keep.
Two league-state problems instead, both worth a minute of your time:

- **LG04 (9000000000000000017)** — league says `in_season`,
  roster endpoint returns `players: null`, and the draft object reports
  `pre_draft` on one endpoint and `drafting` on another. All **180 of 180 picks
  are in** (15 rounds x 12 teams) and your 15 are recorded, so the draft
  finished but never finalized into rosters. **If closing it out needs a
  commissioner action, nobody has taken it.** I read your roster from the picks
  endpoint: Cook, Henry, Barkley, Montgomery, Watson, P. Washington, Pierce,
  Fannin, Diggs, Gainwell, Shakir, Dike, R. Davis, LAC, Stroud.
- **Two leagues named "LG06."** The old one
  (9000000000000000021) returns an empty roster. A new one
  (**9000000000000000024**, "LG08", 10 teams) holds
  your 16-player roster. The old ID looks abandoned, and `leagues/` still points
  at it. Worth a slug update before next Tuesday.

---

## RUN NOTES

- **Mode: hybrid, recovered.** Step 0 failed — no folders connected despite the
  task being configured with the Sleeper folder. Ran cloud-only through research,
  then the access prompt was approved on `zbookmurdock` and the dossier half ran
  normally. The bridge also dropped and reconnected once mid-run.
- **Leagues covered: 8.** `9000000000000000024` is new since 9/3.
- **Leagues with no roster via the API: 2.** LG04 LG04 (recovered from
  draft picks) and the old LG06 league (genuinely empty).
- **Candidates: 166. Researched: 166. Unresearched: 0.** 85 unique rostered
  across 6 readable leagues + 75 trending adds not already rostered + 6 recovered
  from LG04's picks. `refresh_list` was not used for triage — the run was
  cloud-only when triage had to happen, so the candidate set was built from
  rosters + trending directly.
- **Observation gate: 166 of 166 carry a today-dated observation.** 0 validation
  errors across all 166 documents.
- **The date fix.** The first bundle build failed the gate 29/166, and the cause
  is the 9/3 bug's actual mechanism. `append_observation` sets `volatile.as_of`
  from the newest timeline date, so filing an observation under the *news* date
  (9/13, or 2026-01-05 for a stale player) leaves `as_of` behind, re-flags the
  player every week, and lets two runs collapse onto one game date — which is
  what starves `D.trend()`. Observations are now dated the **run** date, with
  the news date preserved in the note as `[news YYYY-MM-DD]`. Gate went to 166/166
  and every doc's `as_of` is 2026-09-15. **Next week's run should keep doing
  this**, and the prompt's Step 4 wording ("use today's real date") should be
  made explicit about run-date-not-news-date.
- **One identity error caught and corrected.** A research agent swapped
  **4866** and **4881**, filing Lamar Jackson's Week 1 line into Saquon Barkley's
  dossier and Barkley's note into Jackson's. Verified against the API
  (4881 = Lamar Jackson BAL QB, 4866 = Saquon Barkley PHI RB), swapped back, and
  re-imported. A name-vs-store check across all 166 found no other mismatch.
  This is the same class of error as the 9/3 Aaron Jones retraction.
- **Pool source: Sleeper trending adds** (168h lookback, top 100). Not board rank.
- **Import:** `imported 15 new, 151 updated, 0 older-skipped, 0 rejected`, then
  `0 new, 166 updated` on the post-correction re-import. Store 494 → 509.
- **Not committed to git.** Constraint J (the `index.lock` problem) makes git
  writes on this mount a one-way door, and nothing here needed it. `dossiers/`
  and `reports/` are dirty and ready if you want the commit.

### Two data-quality notes

- Several subagents exhausted their WebSearch budgets and fell back to WebFetch
  against PFR, Ourlads, FantasyPros and RotoWire. Those entries carry fewer
  snap/route percentages. Empty fields are empty, not guessed.
- Agents repeatedly caught WebFetch summarizers inventing facts — Najee Harris
  as a Steeler, Kenneth Walker starting ahead of Emmett Johnson in Seattle,
  "117 receptions" after one game. Discarded at the source. The one-line-per-fact
  extraction rule is doing real work; keep it.
