# HANDOFF.md — what's live, as of 2026-09-11

Read order: **CLAUDE.md** (rules) → this file (snapshot) → **DECISIONS.md**
(the log, append-only). Where this file and CLAUDE.md disagree, CLAUDE.md
wins on rules and this file wins on "what's true right now."

Nothing here is a substitute for running the tools.

---

## Start here

    python br.py                       # every command, grouped
    python br.py rhythm                # what to run today
    python br.py roster                # writes roster.md — READ IT FIRST

`br.py` is the only entry point you need to remember as of 9/2. The
toolkit moved into a `battle_rhythm/` package the same day; module
filenames did not change, so every name in DECISIONS.md still finds its
file. RESTRUCTURE.md carries the plan and what broke.

The gate, all offline:

    python br.py test                  # 61 passed, 0 failed
    python -m battle_rhythm.paths --selftest            # 18/18
    cd webhooks; npm ci; npm test; cd ..                # 38 (webhook receiver, Node 22)
    python -m battle_rhythm.lineup_value --selftest     # 93
    python -m battle_rhythm.dynasty_value --selftest    # 55
    python -m battle_rhythm.roster_snapshot --selftest  # 37
    python -m battle_rhythm.superflex_adp --selftest    # 10
    python -m battle_rhythm.draft_review --selftest     # 9
    python -m battle_rhythm.recap --selftest            # 28
    python -m battle_rhythm.rhythm --selftest           # 15
    python -m battle_rhythm.ext_tiers --selftest        # external tier join
    python -m battle_rhythm.ledger --selftest           # 18
    python -m battle_rhythm.truth --selftest            # 22
    python -m battle_rhythm.release --selftest          # 39

`recap` and `rhythm` also run inside `br.py test`. A count LOWER than
these means a check was deleted rather than fixed — find out which.

---

## ⚠ Restart discipline — a restart is OWED, and the VM is down

The MCP `sleeper` tools have served STALE code since the 9/7 position
fix: verified 9/7, the MCP board still returned the 11-deep DL list from
before it. `br.py live` and every CLI command start a fresh process and
always have current code; only the MCP server persists. Quit Claude
Desktop from the system tray and reopen.

The desktop's Linux VM (`device_bash` from a Cowork session) has failed
to start since 9/7. The bridge itself is fine — staging, committing and
the `sleeper` MCP server all work — so this is an app subsystem, and the
same full restart is the fix. Nothing in the Wednesday path needs it:
`out/fz/planner.py`, `bakeoff.py` and `slotplans.py` were repathed off
`~/mnt` on 9/8 and run in PowerShell. Only `fzboard.py` still needs the
cache mount, and its output is committed.

GIT FROM POWERSHELL: fixed 9/12. `.gitattributes` (`* text=auto eol=lf`)
is in, and commit `b86c56c` renormalised 249 files that had gone into the
index with CRLF (dossiers, roster.md, measured/). `checkout` and `reset`
are safe again; the 9/7 1,729-line revert cannot recur. Verified by
`git diff --cached -w --stat` printing nothing before the commit.

Still the standing rule: any change under `battle_rhythm/` reaches the
MCP tools only after a FULL Claude Desktop quit from the system tray.
The 9/4 turn-plan fix printed the old contradiction until that happened.

---

## What changed on 9/11 — the season starts, and the ledger with it

All seven drafts are done. The four-week ship window (9/4) is open, and
its rule — no new features, the eval is the deliverable — held by putting
the in-season tools INSIDE the eval. Full reasoning in DECISIONS 9/11.

**The weekly cadence now:**

    python br.py weekly                # every league; RECORDS every rec to the ledger
    python br.py waivers lg04       # claims only, one league
    python br.py ledger                # what has been recommended, what has been scored
    python br.py ledger score          # Tuesday, after the week has played (network)

MCP tools `waivers` and `ledger` are new (12 tools now). RESTART OWED:
they do not exist to Claude Desktop until the full quit-from-tray.

**What a waiver row carries now** — depth slot (RB3, LWR1), a ROLE? flag
when the chart puts him below the job his projection assumes, a named
handcuff when his RB1 is on your roster, `contested` for a top-3 free
agent at his position, a sized FAAB bid with the arithmetic printed once
per league, and a drop that is never a reserve or taxi player. Order
leagues (LG02) show your waiver position instead of a bid.

**What the ledger is.** `data/ledger/recs.jsonl`, tracked, one line per
lineup / waiver / trade recommendation with the projection it was priced
on. `ledger score` rescores the actual stats under each league and
writes `outcomes.jsonl`. The report is win rate by projected-edge bucket
next to the calibration prior — the same buckets backtest.py uses. That
comparison IS the eval: below the prior, the league rescoring is hurting;
above it, it is the edge. Nothing in it is a verdict on a single rec.

**Built in the cloud, not on the PC.** The device VM was still down on
9/11, so this was written against a staged copy of the repo and committed
back through the bridge. The offline suite ran green there (57), but
NOTHING here has touched the live API yet. First live run to do:

1. `python br.py test` on the PC — confirm 57.
2. `python br.py waivers lg04` — the first real waiver rows. Check
   that depth slots print (the field names `depth_chart_position` /
   `depth_chart_order` were read from the table schema, not exercised
   live) and that Conner is no longer the drop.
3. `python br.py weekly` — records the week's recs. Then `git status`
   shows `data/ledger/recs.jsonl`; commit it. The 9/4 baseline starts
   with that file.
4. Next Tuesday: `python br.py ledger score`, then `python br.py ledger`.

**Found on the first live run, 9/12.** (1) The API returns EIGHT
leagues: two "LG06", identical rosters and
scoring, one with the 🪓 prefix and FAAB 1000, one plain with FAAB 100.
RESOLVED same day: the plain one is real; the lg08 one is a commissioner
copy, registered as `lg08` with `ignore: true` and pruned
from the ledger. Third time an unregistered league has surfaced (Best
Ball, the IDP league before it). (2) The ROLE? flag fired on six of eight
receiver rows; receivers are no longer flagged (DECISIONS 9/12). (3) A
week-N waiver or trade is now scored from week N+1 — it cannot play for
you the week it was recommended. (4) The 41 week-1 recs included the
duplicate league's; pruned.

**Also 9/12, later.** `br.py lineup` (start/sit only) and a LINEUP
section at the top of every league in `weekly` — the CLI never showed
the actual-vs-optimal swaps before; only the dashboard did. The old
`br.py lineup` (lineup_value simulation) is now `br.py fit`. First live
run of it caught a display defect: swaps were paired by rank, so a
superflex league printed "start Reed (WR) over Daniels (QB) +-7.2 (75%)".
Pairs are by position now, odds print only on a positive gain, pinned
by `t_lineup_swaps_pair_by_position_not_rank`.

**Also 9/12, John's catch:** the brief told him to bench A.J. Brown,
who was hurt Thursday night and LOCKED. The optimiser had no idea a
game had started. `weekly.locked_teams()` reads the current week's stats
feed (a team with any stat line has kicked off; never written to the
hist_ cache) and locked players are on neither side of the diff, out of
the gap, and never recorded. `ledger list` and `ledger prune --rec <id>`
exist to remove advice that was not actionable when given.

**Not done, on purpose:** return-yardage / P(starts) (9/7 §3); trades
beyond 1-for-1; lineup bye/injury hardening. Trades and moves are the
next two builds, in that order of need, and both record to the same
ledger without further plumbing — recs_from_brief already reads them.

---

## League status

Seven leagues. `LG07` was found on 9/2 after running live and
unregistered — the second time that has happened.

| league | slug | status | next thing |
|---|---|---|---|
| **LG04** | `lg04` | **in season** | **DRAFTED 9/6** from slot 10. recap run 9/7; its grade is NOT trustworthy — see DECISIONS 9/7 |
| **LG06** | `lg06` | **in season** | **DRAFTED 9/9.** Grades and report in the Cowork project docs (2026-09-09-lg06-*) |
| **LG02** | `lg02` | **in season** | **DRAFTED 9/5.** Post-mortem drove the 9/6 tooling pass |
| **LG03** | `lg03` | in season | renamed from LG03-LG05; same id. Slug was `lg05` until 9/3 |
| **LG05** | `lg05` | in season | slug was `lg05-emoji` until 9/3 |
| **LG01** | `lg01` | in season | |
| **LG07** | `best-ball` | in season | **excluded from the weekly cadence** — no lineup, no waivers, no trades |

---

## The three draft cards

All in `leagues/<slug>/brief.md`. Each is priced against its own league's
scoring, and the three plans disagree with each other on purpose.

**LG04.** Running back is steep and receiver is flat, so buy backs
early and receivers out of the flat band. Two flex slots make that legal.
Quarterback is nearly free — replacement is Goff at ADP 94 — so take one
at 87. The 2027 round-cost keeper turns rounds 11–15 into a different
draft; Jadarian Price at ADP 131 is the pick not to skip.

**LG02.** The opposite call on quarterback: **thirteen QBs project
above replacement and fourteen teams need one.** Maye at pick 72 is the
last one worth having and there is nothing above replacement at 97. Slot
13 of 14 means picks come in pairs three apart, which changes what is
worth gambling on. Two of thirteen picks go to a kicker and a defense.

**LG06.** Volume scoring (0.5 per pass AND rush attempt, 10-point
touchdowns) makes **Josh Allen +111.7 over replacement — ninth overall,
ahead of every receiver** — against a generic ADP of 32. And **ten
defensive linemen sit above replacement for ten teams**, with Hutchinson
worth double the second one, while LB and DB run 79 and 69 deep. One
scarce defensive position, two free ones.

---

## What changed on 9/2

**The package move.** 24 modules into `battle_rhythm/`, 9 spent one-shot
scripts (2,683 lines) to `archive/spent`, one entry point. Three checks
would have gone VACUOUS rather than failed — `paths.REPO` pointing at the
package so `out()` would have created a second `out/` inside it, and two
lints globbing a root that now holds three files. All three now assert
what they see.

**League identity has one source.** `mcp_server` derives its ids and
aliases from `leagues/_index.json`. The old drift check compared two
hand-typed copies, which is how Best Ball hid; it is replaced by three
questions that can still fail.

**Two real defects, both of the "true number, false label" class:**

1. **The pre-draft turn plan named players who cannot be there.** LG04,
   slot 10, zero picks made, and the banner read "now: Jahmyr Gibbs" —
   ADP 1.0, nine picks ahead of the first. Live it self-corrected, so it
   only bit pre-draft, which is exactly when a card gets written. A
   candidate is presumed gone only if the market takes him in picks that
   have not happened yet; a still-available player priced above your pick
   has already fallen and IS the value. Both halves are pinned by a test.

2. **"Starters filled" printed with a required slot empty** (ROADMAP P1
   #5). `needs_open` excludes K and DEF from the need model, correctly,
   and also gated the banner. Two lists now. Matters in LG02, which
   rosters both.

**New: `recap` and `rhythm`.** `recap` grades your own picks the morning
after against two yardsticks that disagree on purpose — the board
(selection) and the market (price). `rhythm` is the cadence itself: what
to run today, every draft still coming, and the one-shot jobs that get
forgotten.

**Also caught:** LG04's return yardage is not a uniform scoring shift.
Parker Washington prices 12 points higher there than in LG02 because
he returns punts. A shared ADP does not imply shared value.

---

## What changed on 9/4 — the pre-draft pass

Four commits, all before the LG02 draft, gate green at 46.

**The draft path is in git at last.** `draft_live.py` (952 lines) was
untracked and `draft_helper.py` / `br.py` were modified. Going into a
live draft on uncommitted code means no fallback if it breaks at 4pm.
Committed as three separate ideas: draft_live wired into br.py, the IDP
ADP chain, and calibration widened from 2025 to 2018-2025 (141 weeks).

**A third true-number/false-label defect, caught the day before the
draft it would have bitten.** The LG02 turn plan read "now: Derrick
Henry" and "also priced to wait: Derrick Henry (ADP 23)" three lines
apart. The PICK was right — Henry at 13 into Barkley at 16 beats every
other pairing on need-vorp, and everyone above Henry is correctly
presumed gone. Only the page contradicted itself: `waiting` was built as
survivors minus `best_partner` and never minus `best`. One line. Pinned
by `t_turn_plan_never_names_one_man_in_both_lists`, which was checked
against the old code and fails there with the symptom as its message.

That is three shipments of this class now — the Gibbs banner, "starters
filled", and this. All three passed the arithmetic tests. Whatever the
eval layer becomes, agreement BETWEEN two lines of the same output is
the property none of the current tests check.

**Cleared, do not re-raise:**

- `reversal_round` is recorded 0 for LG04, LG02 and LG06
  in `leagues/_index.json`, confirmed by John 9/3. Read the index before
  worrying about snake shape.
- `roster_snapshot` has now run against a K + DL/LB/DB league. Both
  LG06 (K/DL/LB/DB) and LG02 (K/DEF) render every required
  slot. The ROADMAP P1 #5 fix works in the league it was written for.

**Found, not fixed, not urgent:**

- **`draft_helper` never reads `room_shave`.** Only `lineup_value` does.
  So the survival test behind the turn plan is raw `adp >= next_p + 3`
  and assumes every room drafts at market. Harmless in LG02, whose
  shave is 0. It is the LG01 room — the one measured shave of 10
  — where the board would say a player waits and that room takes him ten
  picks early. Two modules hold different models of one question.
- **LG03 reads 27 rostered against a capacity of 20**,
  open -7. [Likely] the two-stage draft: the commissioner's filler picks
  are counted from the picks feed without seeing the immediate drop.
  Five listed players project 0 and four show team FA. Five does not
  account for seven, so the mechanism is not proven. Only the two
  Hybrids can hit this.
- **`br.py` help says the suite is 33 checks.** It is 46.
- **`data/rosters_*.json` and `data/schedule_*.json` are untracked** —
  5.3MB, the backtest history behind calibration.json. Truth or Render
  is still John's call; by the one-command-under-a-minute test they are
  Truth, and the 9/2 commit message says only one machine can fetch
  them.

---

## What changed 9/7 and 9/8 — read this before touching the IDP draft

**503 defenders were invisible.** `SLOT_ALIAS` was applied to the
league's roster slots and never to the player, so `board_data` and
`player_hits` compared Sleeper's `position` (DE, DT, CB) against already
aliased slots and matched nothing. `find` answered "no player matching"
for Garrett, Bosa, Crosby, Hunter, Burns and Simmons two days before the
IDP draft. Fixed by `norm_pos()`, which prefers `fantasy_positions`
restricted to IDP_POS. LG06 pool: DL 61 -> 162, DB 131 -> 176,
LB unchanged. Pinned by a test that fails on the old code.

**Nine scoring rules were worth zero on every board.** This league pays
per-GAME thresholds the projection feed never projects, so they were
silently free. `out/fz/bonus_adjust.py` counts them off real 2025 game
logs and REBUILDS the replacement bars. Cook +95, JSN +90, Henry +85,
Campbell +45, Hutchinson +15. The measured file is
`data/measured/lg06_bonus_2025.json` (325 players) and `draft_live`
reads it, so the live board and the plan now agree.

**The tight-end opener at slots 8-10 was an artifact of that.** A
pre-bonus control run reproduced 9/3's own measurement; with the bonuses
in, a third running back beats it at every late seat. THE PLAN NOW:
slots 1-7 open RB RB WR WR, slots 9-10 open RB RB RB WR WR, slot 8 is a
coin flip — take the better player. IDP early loses 27/49/50 points on
three separate boards; do not take a defender before round 6.

**Wednesday runs on two things, and they now share numbers.**
`leagues/lg06/plan.html` is the frozen plan — all ten seats,
opens from disk, needs nothing running. `python br.py live --league
lg06` is the live board — it knows who is actually gone. If they
disagree, the live one is right about availability and the file is right
about value.

---

## What to distrust

- **Projections read 7–10% BELOW the Sleeper app on purpose.** The app
  assumes every player plays every game; we apply the availability
  discount. Measured 8/13 across nine QBs: -0.7% before, -9.4% after.
- **`room_shave` is 0 in every league except LG01 (10), and only
  that one is measured.** LG04 and LG02 have no entry and no
  prior at all. Run `br.py rooms <league>` after each draft.
- **ADP in the IDP league is not that league's market.** No defender
  carries one. Draft off VORP and the scarcity counts there.
- **`lineup_value` is a ONE-SEASON model** and assumes a static market —
  no other manager's roster is modelled anywhere in the toolkit.
- **`ages.json` curves are priors, not fitted.** The actuals-vs-
  projections backtest is still unbuilt and is still the only thing that
  would settle them.
- **The recap's replacement bar is computed pre-draft and held fixed** so
  the value column compares across picks. `draft_review` recomputes at
  every pick; they will not agree, and both are right about different
  questions.

---

## What changed on 9/6 — the draft-eve pass

Eight commits, all from replaying the completed LG02 draft against the
card that was actually frozen for it. Every finding came from real picks;
none of them failed a test first.

**survives() was reading the wrong input.** Measured on 101 players ranked
by both sources, this feed's ADP has residual sd 0.431 against actual pick
position; consensus rank has 0.284. `SIGMA_POS` assumes 0.18-0.27 — so
every survival number was computed with half the real spread, which is why
a back given 59% to last went 35 picks early. `mkt()` now prefers consensus
rank for skill positions. **DEF and K keep ADP**, from the same fit:
defenses are the tightest thing in the table against ADP (0.063) and get
worse under consensus.

**External tier boards.** `battle_rhythm/ext_tiers.py` joins any overall
board from `data/tiers/` onto the live board — ECR and sd columns. A file
must carry a `rank` column to load: overall boards (rank 1..200) and
per-position boards (RB tier 3) are different quantities, and the RotoWire
files in that directory are per-position. They were excluded only by
file extension until the guard went in.

**Read the sd column as a ratio, not a number.** Raw sd scales with rank —
median 6.3 at ranks 1-50, 29.3 at 151-200 — so a flat cutoff flags the tail
and nothing else. `bc_sd_rel` compares each player to the median sd of his
±25 rank neighbourhood. 1.8x flags four of 197 on LG04's board. And a
split panel says the situation is unresolved, NOT which way it resolves:
Josh Jacobs sat at rank 155 with a best rank of 37 a week after the
Commissioner's Exempt List. Check for a dated status event first.

**Frozen card carried 120 players into a 182-pick draft.** Every one was
gone by pick 128, so the fallback advised nothing, silently, in exactly the
scenario it exists for. `BOARD_ROWS = 400`.

**Display defects, all the same family** — a correct number under a false
label, or a working display over dead logic:

- `42%` in the plan reads as survival; it is how often that player was the
  pick at that turn across rollouts. Header added.
- the frozen card stubs `setSeat` while the note promised "change it any
  time". Note now tells the truth; the live picker was always fine.
- the roster panel drew one chip per required position — seven chips for
  fifteen seats, no bench. `lineup_slots()` returns every seat and its
  occupant, and a test asserts it agrees with `lineup_vorp`.
- the board cut at 60 with nothing saying whether the list was truncated or
  the position exhausted. 150 now, with a footer that says which.
- `.tw` named both the board wrapper and a tier-watch row; the row rule won
  and dropped the table into a 44px grid cell.
- page polled at 3s against a 5s fetch loop. One flag now, default 2s.

**Board sorting.** Any column, click to flip, third click resets. Sort runs
before the row cut; missing values sink in both directions.

---

## Two things that broke on draft morning, 9/6

Both found by running the pre-draft checklist for real. Neither had a test.

**`br.py board lg04` exited "league lg04 not found."** draft_helper's
entry point took a raw league id and nothing else, so it asked Sleeper for a
league literally named "lg04" — while `br.py live --league lg04`
resolved the same word fine. One identity, two resolvers, different answers.
`cli_league()` now resolves slugs and aliases there too, digits pass
through, and a test walks every slug and alias in the index. The path is
load-bearing exactly when nobody checks it: an id is what gets typed in
testing, a slug is what gets typed on the day.

**`br.py board` and `br.py live` disagreed about who survives.**
draft_helper priced survival off ADP while draft_live had moved to consensus
rank, so on draft morning `board lg04` printed "also priced to wait:
Saquon Barkley (ADP 36)" while the live card had him at 0% — consensus 13,
and he went 8th in the LG02 room. Both numbers were computed correctly;
only one was right. They now share `ext_tiers.market_pos()`, and the turn
plan prints the number the decision actually used, labelled ECR or ADP.

**`out/` held 3,200 lines of untracked source.** `.gitignore` excludes
`out/` as renders — "rebuildable in one command, under a minute" — but 31
`.py` files had accumulated there: `test_live.py` (the 51-check draft-day
suite), `calibrate_reach.py` and `runs_test.py` (the reach model this file
says to re-run after every draft), the `def_*` series behind the defense
null result, and the 9/6 replay scripts. None is a render; each costs a
research pass to rebuild, which is the Truth tier by CLAUDE.md's own test.
One `rm -rf out/` and they were gone. Force-added so git tracks them despite
the rule; ignore rules do not apply to already-tracked files. **Relocating
them into the package is the real fix and is still open** — that was not
worth doing with a draft twelve hours out and live commands pointing at
those paths.

**`python out/fz/test_live.py` could not import battle_rhythm.** Running a
script inside `out/fz/` puts that directory on sys.path, not the repo root,
so the 51-check suite died before its first check. It now anchors on its own
file location, so it runs from anywhere.

---

## Open items

- **Confirm the LG06 date.** This file and its brief say Wed 9/9;
  the 8/11 handoff said Thu 9/10. 9/9 is the Wednesday.
- **LG06 slot has still not published.** No pick numbers until it
  does.
- **Confirm every card's pick numbers on the day.** `reversal_round` is
  now recorded as 0 for all three (John, 9/3), so the arithmetic is
  sound — but the two Hybrids proved two rooms in one format need not
  share a shape, so still eyeball the real pick numbers in the room.
- **Restructure phases 6–8 are not done** — subpackages, and retiring the
  root entry points into docs. RESTRUCTURE.md has the sequence. Phases
  1–5 are a complete working state; nothing is half-moved.
- **`keeper.py` still prints swap advice against locked keepers.**
- **The actuals-vs-projections backtest** was invoked twice as "the real
  answer" and is still unbuilt.
- **WR cliff (0.78/yr past 30)** is still flagged as too steep in
  `ages.json`.
- **Source still lives in `out/`.** Tracked now, but in a directory whose
  whole contract is "disposable". `test_live.py` belongs beside
  `test_all.py`; the calibration and probe scripts belong in the package.
  Move them and drop the force-add.
- **No status join behind the sd flag.** A high `bc_sd_rel` means the panel
  is split, not which way. Separating a Jacobs from a Lloyd needs the
  dossier timeline, and that join is not built — the highlight is a prompt
  to look, not a verdict.
- **VORP has a single source.** Sleeper's projection feed, rescored under
  the league and availability-adjusted. Nothing external touches it, so a
  feed that is wrong about a player makes the tool confidently wrong with
  it. MarShawn Lloyd on 9/6: consensus rank 88, VORP rank 158, because the
  feed still models him as a backup with Jacobs on the exempt list since
  8/30. A second projection source is the only real fix.
- **No per-position shift term in `survives()`.** The LG02 fit has one
  (RB -0.204, WR +0.202) but that is one room, and unlike the input swap it
  corrects no demonstrated defect. Refit after LG04 and LG06.
- **`tier_up()` collapses the bottom of every position into one tier** — RB
  sizes came out [1,1,1,1,7,1,10,4] against RotoWire's [2,1,8,7,6,9,5,8,8].
  That blob is exactly where the LG02 draft happened. The floor
  (`max(6.0, 1.7 x median gap)`) is doing the damage, not the multiplier.
