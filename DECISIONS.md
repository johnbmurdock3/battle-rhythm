# DECISIONS.md — append-only decision log

One entry per decision: date, what won, why, and what would reopen it.
Never edit an old entry — add a new one that supersedes it and say so.
Entries before 2026-08-10 predate this file and are reconstructed from
HANDOFF.md and session notes; dates marked "pre-8/10" are approximate.

---

## Project

**pre-8/10 — Toolkit is read-only.** No writes to Sleeper, ever; action
buttons deep-link to sleeper.com. Reopens: never. This is a standing
constraint, not a preference.

**pre-8/10 — keepers.json holds a manual "keeper" flag.** Sleeper's
settings.type: 2 covers both full dynasty and the 3-keeper Hybrids, so
league type alone can't drive the keeper ADP caveat. Reopens: if
Sleeper's API ever distinguishes them.

**pre-8/10 — IDP support built ahead of need.** LB/DL/DB scoring and
slot aliases are tested and dormant. When an IDP league exists, delete
~/.sleeper_cache once so projections pick up the positions. Reopens:
n/a — it activates on its own.

## LG01 (slow draft, slot 9)

**pre-8/10 — No Green Bay pass catchers while Watson is rostered.**
Target collision; the user's rule and it has survived every challenge.
Reopens: Watson traded or cut.

**pre-8/10 — No K slot in this league; DEF at ~256.** DEF order
Texans > Seahawks > Eagles, re-checked against the board at pick time.
Reopens: DEF order re-sorts every session — the slot timing doesn't.

**pre-8/10 — Survival math shaves ~10 off dADP.** The room buys vets
about 10 picks early, consistently. Reopens: if the room's behavior
shifts in the later rounds; re-verify around pick 180.

**8/10 (pick 112) — Downs over Gainwell.** Long debate; WR value at
market beat handcuff appeal one round early. Consequence accepted:
Gainwell might not survive to 129. Reopens: closed — pick is made.

**8/10 — Queue for 129 (RB): Mason > Gainwell > Rodriguez.** Only 5
playable RBs left; Gainwell stays interesting as Irving's handcuff.
Re-verified live 8/11 at 118 picks: all three available; Gainwell is
the at-risk name (dADP 134.7, minus the room's 10). Reopens: any of
the three drafted before 129 — take the highest survivor, no re-debate.

**8/10 — Queue for 136 (QB): Dak > Stroud > Mayfield.** Dart needs
insurance; the shelf is deep and sliding (all three past their dADP and
still on the board as of 8/11). Mendoza and Nix went in the 113-118
window. Reopens: if Dak survives to 129 AND both queue RBs are gone,
flip the order of operations — Dak at 129, RB scramble at 136.

**8/10 — Taxi plan (3 seats, declare post-draft).** Chris Bell (ACL
redshirt — the lock costs nothing while he's out) plus two of
Boston / Stribling / Branch / Bernard / Stowers. Reopens: at
declaration time, against final roster.

**8/11 — Target-collision rule generalized; handcuff bump gated on
standalone value.** The GB/Watson rule was one instance of the real
rule: any WR/TE sharing a QB with a rostered pass catcher takes a
value haircut (collision_mult in ages.json), on every team. The RB
handcuff bump applies only when the handcuff beats replacement on his
own (Stevenson-style goal-line role) — pure insurance backs get
nothing. Encoded in dynasty_value.roster_adjust and the FIT engine.
Reopens: the multipliers (0.6 / 1.15) are priors — tune in ages.json.

**8/11 — The blanket GB ban is retired. SUPERSEDES the pre-8/10 "No
Green Bay pass catchers while Watson is rostered" entry above.** The
rule was never about Green Bay; it was about two receivers eating one
QB's throws. The generalized collision haircut replaces it, so a GB
pass catcher is now draftable at a discount rather than forbidden.
Practical effect: Jayden Reed re-enters consideration at roughly 0.6x
his raw value. Reopens: if a discounted same-QB pick actually burns
him in-season, the ban comes back as a hard rule and this entry gets
superseded in turn.

**8/11 — RESOLVED: Willis is the steal, not an artifact.** Miami
released Tua Tagovailoa in March 2026 and signed Willis the same day
to 3yr/$67.5M; he is the presumptive starter, healthy as of 8/4, and
leading a camp competition against a 7th-round rookie (Quinn Ewers).
Sources: ESPN, MiamiDolphins.com, Miami Herald, Heavy. The ~242
projection at a 334 dADP is a real starting QB going undrafted.
Action: take the planned QB at 136, then take Willis in round 15+
territory where the market still has him free. Reopens: he loses the
camp competition, or Miami adds a veteran.

## Research / dossiers

**8/11 — Scope is "everything draftable," depth is triaged.** User
overrode the recommendation to cap at ~40. Resolution: cover all 447,
vary depth by research_score (deep 40 / medium 110 / light 297) so
coverage is total without uniform cost. Reopens: if the light tier
returns nothing useful, stop running it.

**8/11 — research_score = stakes x uncertainty x proximity.** v1 was
divergence x proximity x volatility and ranked a buried, unpriced,
injured rookie TE #1 of 447: maximum uncertainty, zero stakes. Fixes:
stakes is value-based (share of best model value, or market rank
decay), unpriced scores ZERO market stakes rather than last-place
stakes, and unpriced/sub-replacement no longer count as uncertainty.
Pinned by t_research_queue_ranks_stars_first. Reopens: if the queue
starts surfacing players the user would never draft.

**8/11 — Dossiers enforce sourcing.** dossier.py rejects any record
claiming high/medium confidence with no sources. Given the WebFetch
summarizer's invention problem, an unsourced research assertion is
worse than a gap. Stable facts (team, contract, scheme, career
workload) and volatile ones (injury, camp quotes) are split so only
the volatile half needs re-running before a draft. Reopens: never —
this is the guard that makes agent research trustworthy.

**8/11 — Weekly refresh is append-only, and triaged.** Dossier
`volatile` became a dated `timeline`; each weekly run appends rather
than replaces, because slope is the only thing weekly cadence buys
(45 -> 58 -> 71 snap share is a signal the projection feed cannot
show). trend() refuses to report a direction from one observation.
Scope is 100-150/week (rostered + top-25-available-per-league + open
questions), not all 447. Scheduled task fires Tuesdays 8:00 AM PT,
checks the device bridge first and stops cleanly if the repo is
unreachable. Reopens: if the diff report stops surfacing anything
actionable for 3+ weeks, cut the cadence or the scope.

**8/11 — Research does NOT feed the FIT score.** Dossier facts display
beside the numbers, never inside them. board_data must stay one
auditable, tested computation; hand-researched multipliers would make
it unreproducible and let stale research corrupt the board silently
instead of loudly. Reopens: if a backtest shows dossier-flagged role
changes predict projection misses better than the projections do, a
gated availability adjustment becomes arguable — that test is now
possible since historical proj-vs-actual data is confirmed available.

## LG03-LG05 (drafts Tue 8/18, 9:00 AM PT, slot 8)

**8/11 — Pick 8 changed: Nabers OUT, Love downgraded, Warren in.**
SUPERSEDES the 8/10 "Love clean, Nabers if you'll wear the knee" call.
Nabers tore his ACL in Wk4 2025 with meniscus damage plus a spring
2026 cleanup, missed spring, ~70-80% through rehab in mid-July;
Harbaugh: "not a simple knee." Love is listed RB2 behind Tyler
Allgeier on Arizona's first preseason depth chart (8/2) despite a $53M
guaranteed rookie deal. New order: Warren (TE, target tree cleared by
the Pittman trade, and this room pays bonus_rec_te 0.5 + buckets) >
Pickens > London. Reopens: a full-clearance report on Nabers puts him
back in the conversation; a Love promotion on the next depth chart
restores him.

**8/11 (evening) — Brief rebuilt on observed keepers. SUPERSEDES the
8/11 morning rewrite entirely.** 73 players are kept league-wide (read
live from rosters, not estimated), so global ADP overstates
availability by roughly 40-50 picks in the middle rounds. Consequences:
Warren, Love, London, Pickens, Nabers and Cook are all gone before
pick 8, killing the morning version's pick-8 call; the QB fork moves
from 17-as-fallback to 17-as-the-pick, because 8 of 12 teams need a
startable QB2 and Lawrence/Herbert (both 358) beat the best skill
player there by ~60. New plan: RB at 8 (Chase Brown, else Saquon),
QB at 17 (Lawrence, else Herbert), Swift at 32, McLaurin at 41,
Geno Smith in the endgame. Reopens: re-run --board on draft morning;
the kept set is live and other managers may still move players.

**8/11 — Limited-keeper leagues price off REDRAFT ADP, not dynasty.**
Sleeper types the Hybrids as dynasty, but they keep 7 and churn the
rest, so dynasty ADP's age penalty describes a market this room isn't
in. It surfaced as fake availability — Dak, Kittle, Evans and Adams all
showing 40+ picks late. keepers.json's "keeper" flag now selects the
market. Reopens: if the 8/18 draft shows veterans going LATER than the
redraft-priced board predicts, flip back.

**8/11 — dynasty_value takes a holding horizon.** Full career for true
dynasty, 2 seasons for a 7-max keeper league, 1 for redraft (ages.json
"horizons"). Summing a player's whole remaining career priced seasons
the user will never own and talked the model out of elite older players
for younger lesser ones — the exact mistake he named ("I wouldn't pass
on Jefferson for a less than top tier talent because he's 4 years
younger"). Reopens: WR cliff [30, 0.78] is still too steep — it
overrode a 20-point projection edge in testing. Tune before it matters.

**8/11 — Mendoza does not count toward the two-QBs-by-65 rule.**
Kubiak named Kirk Cousins the starter 7/28. Mendoza stays a dynasty
asset and free drafted-rookie keeper, but not 2026 production.
Reopens: Cousins injury or benching.

**8/10 — Priced in the 2QB market, and the QB plan forked.** The
superflex repricing moved the plan from "wait til 41" to "fork at 17":
Love/Nabers at 8; Herbert-or-Lawrence at 17 if alive; two QBs by pick
65. lg05_brief.md is the working doc. Reopens: Nabers' knee — check
the morning of the draft.

## Model

**8/11 — Scarcity damping added, then corrected to one-sided.**
Pure positional VORP had a 22-year-old TE worth 3.7x Justin Jefferson:
a one-TE league puts TE replacement on a far worse player and the
multi-year sum multiplies the gap ~5x before you see it. Damping
(ages.json roster.scarcity_damp, 0.35) pulls each position's bar
toward a global average. The first version pulled in BOTH directions,
which was wrong. A scarce position has a low bar because replacement
there is a bad player; a deep position has a high bar because
replacement is a real starter. Lowering a high bar invents surplus.
In LG01 (1QB) it cut the QB bar ~43 points a season, the
20-season discounted sum turned that into ~285 points handed to every
quarterback, and draft_review answered with Dart, Purdy, Nix, Love and
Willis at nearly every mid-round pick in a league that starts one QB.
Damping now only RAISES bars below the global average
(`max(v, v + d * (bar - v))`). Reopens: if the board still reads
TE-heavy, raise scarcity_damp; if a QB still tops a mid-round pick
after this, the cause is curve length (QB end 42 against a 20-season
horizon), not the bar — that is a curves conversation, not a damping
one.

**8/11 — Disagreement is a ratio, and it is a signal to check, not a
score to override.** market_disagreement flags model-rank vs
market-rank as a multiple (Willis: model #3 vs market #250, 83x). The
QB sweep above was caught by these flags, not by the rankings. When a
flag fires, verify before trusting the number. Reopens: if flags fire
on more than ~10% of a board they have stopped being informative —
raise the ratio.

**8/11 — rise 0.96 across all four positions; scarcity_damp STAYS at
0.35.** Three single-variable runs of draft_review, logged here so the
next session doesn't re-run them. (1) rise 0.90->0.96 cut the top-of-
board-normalized gap 2.80 -> 2.40 and, more importantly, surfaced Ladd
McConkey over Harold Fannin and Trey McBride at all — the old curve
preferred younger-and-worse at the same market price. Adopted. (2)
scarcity_damp 0.35 -> 0.55 made things worse: normalized gap 2.40 ->
2.47, and it cut the user's own RB picks hard (Henderson 60->45, Irving
90->73, Rodriguez 17->6) while barely moving the TE gap. Rejected. (3)
The residual Loveland-over-Jefferson gap is neither the bar nor rise.
It is career length: discounted career multiplier x6.01 for a 22yo TE
vs x3.57 for a 27yo WR, a 1.68x ratio that matches the observed 1.65x
almost exactly. No single knob flips it — a discount rate of 0.65,
which would make year 10 worth 1% of year 1, still leaves 1.24x.
Conclusion: this is not a bug, it is what a 20-season horizon says
about 13 remaining seasons vs 7. Whether to take Jefferson anyway is a
football judgment, not a parameter. STOP TUNING — three rounds of
one-more-knob is the shape of fitting to a desired answer. Reopens:
only with out-of-sample evidence (actuals vs projections), not with
another board that reads wrong.

**8/11 — SLEEPER_RISE / SLEEPER_DAMP env overrides.** load_params()
accepts them so a knob can be A/B'd without editing ages.json and
risking leaving the experiment committed. draft_review prints the rise
values every run and stamps ** ENV OVERRIDE ACTIVE when one is set.
Reopens: n/a.

**8/11 — UTF-8 stdout forced in sleeper_client.** Windows consoles
report UTF-8 but `>` redirection falls back to cp1252, so every CLI
here crashed on its first box-drawing character when piped to a file.
Fixed at the shared base since all 13 CLIs import it. Reopens: n/a.

**8/11 — Positional saturation: the third and last instance of "you can
only start N."** Once you hold as many players at a position as the
league gives dedicated slots, the next one is not taking a slot at that
position — he is taking a flex, and his replacement is the flex bar,
not his own position's. roster_adjust now rescales him by
(proj - flex_bar) / (proj - own_bar), which is not a fudge factor: it is
the same VORP with the correct replacement substituted. A position with
no flex path (QB in 1QB, DEF, K) falls back to roster.bench_mult 0.25,
which IS a judgement call and is labelled as one. Why it matters: he
took Bowers at 9, so the review's Loveland-at-16 recommendation valued a
second elite TE against TE12 in a league with one TE slot. Priced against
the flex bar the same player drops ~57% (273 -> 119 on the selftest's
bars) and Jefferson wins without touching a single curve. The two prior
instances were the QB damping subsidy and the QB wall. Reopens:
bench_mult is unpriced — a backup QB has injury and trade value this
model cannot see.

**8/11 — The dashboard never applied scarcity damping.** draft_review
damped, the DYNASTY tab did not, so the same player carried two
different VALUEs under one name for the whole session — the exact bug
the market-blend fix was supposed to have ended. Now damped with
available-players-per-position weights, matching the review. Reopens:
n/a, but the lesson is that every consumer of dynasty_value must apply
the SAME pipeline; check this first when two views disagree.

**8/11 — roster.md reports PRODUCTION, not occupancy.** First real run of
roster_snapshot.py reported LG03-LG05 as QB 1/1 (Jalen Milroe) and RB 2/2
(Derrick Henry, Brashard Smith) — every slot green, "what must still be
filled" listing only WR and FLEX. Milroe projects 15.3 points and Smith
24.5 under that league's scoring. Two starting slots were held by players
who will not play, and the file whose entire job is naming the binding
constraint counted bodies instead of starters. It also sorted the QB slot
by roster order, putting a 15-point quarterback in front of a 382-point
one on the single row that mattered. Fixed: slots carry projections, a
filled slot whose occupant is below the position's teams-th best
projection is marked THIN with an explicit "treat as OPEN" callout, the
best player fills the dedicated slot, and flex rows name their occupant
instead of printing the eligibility string. Reopens: the bar is
teams x 1 starter; in a league with two dedicated slots at a position it
should arguably be teams x 2.

**8/11 — pre_draft leagues reported "picks remaining 0."** my_next_picks
walks draft_order, which Sleeper leaves unset until slots are assigned,
so two pre_draft leagues printed "picks remaining 0 ... you will finish
UNDER capacity" for drafts that had not started. Falls back to one pick
per round when no picks exist yet, labelled as an estimate. Reopens: n/a.

**8/11 — CORRECTION to the 8/10 LG03-LG05 QB plan.** I told him the plan
was dead because both superflex QB slots were filled. That read slot
occupancy off roster.md without checking whether the occupants produce.
Jayden Daniels (382) is a starter; Jalen Milroe (15.3) is not. The
SUPER_FLEX is effectively empty and QB is back on the board. Same error
class as lesson 8 in CLAUDE.md, made while criticizing the tool that
caused it. Reopens: n/a — the correction stands on projections.

**8/11 — Both Hybrids run a TWO-STAGE draft (user-supplied).** Managers
keep different numbers of players, so the commissioner runs a 10-round
draft and then a second draft to fill rosters out. This retires half of
the "picks remaining" finding above: finishing the first draft under
capacity is the design, not a shortfall, and roster.md flagging it as a
warning would argue for drafting depth over value in rounds 8-10.
keepers.json now carries "supplemental_draft": true for both Hybrids and
roster_snapshot reports "N slot(s) left for the SECOND draft (expected)".
The pre_draft "picks remaining 0" for the emoji Hybrid and LG02 was
still a real bug (unset draft_order) and is separately fixed. Reopens:
if the commissioner changes format, clear the flag.

**8/11 — Taxi players were filling starting slots (user-supplied
correction).** Milroe and Brashard Smith are on LG03-LG05's TAXI squad,
not the active roster. roster_snapshot merged taxi into `mine` and then
used them to fill the lineup, so the file reported QB 1/1 and RB 2/2
with both slots actually empty and both players ineligible to play.
keepers.json has said "taxi players do NOT consume an active roster
spot" since 8/10; the code never read it. Fixed: taxi is tracked
separately, never fills a slot, gets its own line with names and
projections, and capacity is reported as ACTIVE capacity. This
supersedes the THIN diagnosis for these two — THIN stays for genuinely
active players below the bar, which is a different failure. Note the
ordering of my own errors here: I read occupancy off the slot table and
called the QB plan dead; corrected that with projections and called
them thin starters; the real answer was that they were never starters
at all. Each correction came from HIM, not the tool. Reopens: n/a.

**8/11 — lineup_value.py: displacement replaces vacancy (user's frame).**
His words: "the kept players earned a spot last year... I need to build a
locker room with WR1/WR2/WR3/WR4 that I can best in slot. The rest of the
roster could have a player slide down the depth chart because the draft
will have talent. I will likely not start Jayden Higgins if I can get a
better WR in his place." Every other view asks "how much better is he
than replacement at his position," which is a startup-draft question. In
a keeper draft the question is what he ADDS to the lineup you already
own: a new WR is worth his projection minus Higgins (197.6), not his
surplus over WR36. Implemented as a season simulation -- each week every
player is available with his own probability, best legal lineup is
filled, average over a few hundred seasons. Empty slot, weak incumbent,
strong incumbent and bench-depth-as-injury-cover all fall out of one
definition instead of four rules. Availability comes from
availability_ratios(), Rotowire's own haircut already used by
season_projection_totals, so no new assumption enters -- it just stops
being collapsed into a single season number. He chose "full roster,
weighted by odds of starting" over starters-only after I warned the odds
were the hard part; the ratios turned out to already be there. Common
random numbers across candidates so a 0.5 ppg edge is not lost to noise.
Scope: ONE SEASON. It knows nothing about age or 2027 and does not
replace dynasty_value -- weight this in the 2-keeper Hybrids, weight
dynasty_value in LG01. Reopens: availability is modelled as
independent week to week, which understates multi-week injuries.

**8/11 — THIN bar recalibrated: teams x STARTERS, not teams x 1.** The
first version priced every position at the 12th-best player in a 12-team
league. That is a WR1 line in a league that starts two receivers plus two
flexes — about 35 of them. It flagged five of nine LG01 starters
(Etienne, Irving, Watson, Harrison, Downs), three of them ordinary
starters, and "treat as unfilled" on the majority of a lineup is noise,
not a warning. The bar now counts every slot a position actually starts
including flex share: 2 WR + 2 FLEX at 12 teams is WR35, RB34, TE16;
superflex puts QB at QB22. Milroe (15) and Brashard Smith (24) still
flag, which is the case the feature was built for. Reopens: FLEX_SHARE
is copied from draft_helper's priors and is not fitted.

**8/11 — lineup_value called resolve_league with two args.** It takes a
fragment and returns an ID, not a league dict. Shipped untested against
the live API because this session cannot reach Sleeper — the selftest is
offline and never exercised build(). Reopens: any function only reachable
with a network call is untested here by construction; read the signature,
do not assume it.

**8/11 — Taxi is an OPTION with a price, not a dead spot (user-supplied
rule).** His words: "I brought him over from last year for free, which is
why the taxi exists, I get to keep as long as I forgo their year while he
sits on the taxi position. If I had taken him out of taxi mid season I
would forgo a bench seat." Also: eligibility can EXPIRE while the player
stays parked — Gadsden is no longer taxi-eligible but is grandfathered,
so removing him is irreversible. Consequence for the model: excluding
taxi players from the lineup was right, excluding them from the candidate
pool as well was wrong — it priced an option he already owns at zero.
lineup_value now scores taxi players as candidates, marks them [TAXI],
and states the price: a bench seat now plus the free carry into next
season, versus points this year. Live case: 🦸💪 has an EMPTY TE slot and
Oronde Gadsden (182 proj, in a league with a 0.5 TE reception bonus)
sitting on the taxi. Reopens: the free-carry-forgone side is not
quantified anywhere — it is a keeper slot, and keeper.py prices those.

**8/11 — CORRECTED taxi cost: a forfeited taxi SEAT, not a keeper slot.**
I priced activation as "he stops carrying into next season free, weigh it
against a keeper slot." Wrong on both halves. His correction: Gadsden is
not a keeper this season, he is "just a player I don't have to draft."
The cost that matters is that a vacated taxi seat CANNOT be refilled
mid-season — activate one and he carries 6 rather than 7 for the year,
with 2 taxi spots becoming 1. Two consequences. (1) Taxi seats must be
filled DURING the draft; leaving one open is not deferring a decision,
it is losing it. (2) The decision number is not the taxi player's points,
it is his points MINUS the best player available at the same position —
because the empty TE slot gets filled either way. lineup_value now prints
that delta per taxi player, with the caveat that the alternative shown is
the best on the board and may not survive to his pick, which makes the
delta pessimistic for the taxi player. Reopens: one taxi seat's option
value is still unquantified; it is a free 2027 asset and nothing prices
it. That is the number that settles a close call, and I do not have it.

**8/11 — Taxi seats are options he EXERCISES, not storage (his record).**
He drafted Jayden Daniels as a rookie and stashed him, drafted Lamar
Jackson and Baker Mayfield, started Mayfield, then mid-season traded
Mayfield for a star RB and promoted Daniels off the taxi. Carried six
that year instead of seven and won the championship. Gadsden was the
same bet: park a TE he believed would earn a role while two TEs already
held active spots, keep him free, add to kept capital. That bet has now
come in — Gadsden projects 182 in a league with a 0.5 TE reception
bonus, and 🦸💪's TE slot is empty. Consequence for how to advise him:
the question is never "can I afford to lose the seat," it is "is the new
bet I would put in that seat worth more than cashing the one already in
it." Holding an in-the-money option forever is not patience, it is never
collecting. Written into CLAUDE.md so it survives this session.
Reopens: n/a — this is how he plays, not a tuning choice.

**8/11 — FINAL taxi correction: it is a one-year rookie redshirt that
EXPIRES.** Rookies only, one season, then the player joins the active
roster automatically. There was never an activate-or-hold decision on
Gadsden, and I priced that non-existent decision twice — first as a
forfeited keeper slot, then as a forfeited taxi seat — building a whole
"exercise the option" argument on top of a rule I had invented. Each
correction came from him. What the seat actually bought: a season of
free storage (no bench spot consumed) and a player who arrives still
eligible for a drafted-rookie keeper slot, plus one skill position he
does not have to reach for early in the draft. Keeper allowance is 5
from last year's active roster: 3 keepers + 2 drafted rookies.
Implemented as dynasty_value.taxi_split(), which classifies a taxi
player by years_exp: 0 = redshirting now (cannot start, holds the seat),
>=1 = expired (active roster, seat is open for this year's class),
missing = reported as unknown rather than guessed, since assuming either
way silently moves a player between "can start" and "cannot."
roster_snapshot reports the three groups separately and counts open
seats; lineup_value puts expired redshirts in the LINEUP and drops
current ones from both lists. Reopens: years_exp is Sleeper's field and
has been wrong before; if a returning player shows as still redshirting,
check it there first.

**8/11 — lineup_value was starting THREE quarterbacks in a superflex
league.** _order() pooled every flex slot into one eligibility list and
one count, so the union of FLEX (RB/WR/TE) and SUPER_FLEX (QB/RB/WR/TE)
let a quarterback start in the plain FLEX. Symptom in the 8/11 run: with
Lamar Jackson and Jayden Daniels already rostered, Josh Allen came back
at +426 "fills an empty slot" — a full starter's points for a third QB
who cannot legally play. Every quarterback on both boards was inflated
the same way, which is exactly the QB-wall failure from earlier today
arriving through a different door. Fixed: each flex slot is assigned
separately against its own eligibility, most-restrictive first. That is
optimal while eligibility sets are nested (FLEX subset of SUPER_FLEX),
true in all five leagues; crossing sets like WRRB_FLEX with REC_FLEX
would need a real assignment solver and none of his leagues has that
pair. Allen against that roster should now price as the delta over
Daniels, roughly +50, not +426. Reopens: if a league ever adds crossing
flex types, this needs rewriting, not tuning.

**8/11 — lineup_value gets ADP and a per-pick draft plan.** The value
numbers were unusable without a market column: knowing Baker Mayfield
adds 305 points tells you nothing until you know he goes ten rounds
after Josh Allen. Added superflex- and keeper-aware ADP (same key
selection as draft_review — adp_2qb prepended for superflex, redraft
market for keeper-flagged leagues) and a --slot mode that walks his
snake picks and shows who is reachable at each, shaving 10 off ADP for
this room's habit of buying ahead of market. The plan is a PATH — each
row assumes the row above it was taken — and it assumes a static market.
Reopens: it does not model other managers' rosters, so a run on
quarterbacks by the three teams above him is invisible to it.

**8/11 — the honest limit of lineup_value, stated in its own output.**
With empty starting slots every candidate "fills an empty slot" and the
number collapses to raw projection. In 🦸💪 (two holes) the top of the
board is just the projection ranking and the tool adds nothing. It bites
only where there is an incumbent to displace — LG03-LG05's SUPER_FLEX
(Milroe, 15) and WR3 (Higgins, 198). The real fix is simulating the
draft FORWARD so a candidate is measured against the final roster rather
than today's partial one. Not built. Reopens: build it if the 8/18 plan
needs picks 5-10 to be more than "best projection left."

**8/11 — room_shave is per-league data, not a global default.** I shipped
the draft plan with a hardcoded 10-pick ADP shave for every league,
generalising CLAUDE.md lesson 6 — a LG01 observation — onto rooms
it does not describe. His correction: the Hybrid rooms draft close to
market, "these guys know what they're doing, for the most part." Now
stored per league in keepers.json (LG01 10, both Hybrids 0,
LG04 0, unknown leagues 0) and read by lineup_value, with --shave as
an explicit override and the reason printed in the plan header. CLAUDE.md
lesson 6 rewritten to say room behaviour is per-league data. Reopens:
room_bias.py MEASURES this once a draft has picks; the stored numbers are
pre-draft priors and should be replaced by measurement mid-draft.

**8/11 — the draft plan recommended ten quarterbacks; it never grew the
roster.** Each pick was scored against the ORIGINAL roster, so every QB
in turn "displaced Jalen Milroe (15)" — the plan struck the chosen player
from the shortlist but never added him to the simulated team. The "each
row assumes you took the row above it" note I printed was simply false.
🦸💪 had the same bug in a quieter form: Bowers at 8 then McBride at 17,
two tight ends for one slot. Fixed: the plan now re-simulates after every
pick against the roster the earlier picks built, and flags "GONE by N,
take him now" when a suggestion will not survive to the next turn. The
invariant is tested — with a 1-point body on the SUPER_FLEX the first
upgrade QB is worth +408 and the second +34. My first version of that
test asserted the second should be small on a roster where it was
correctly large; the code was right and the assertion was wrong, which is
worth remembering before loosening an assertion to make a suite pass.
Reopens: still a static market — another manager's run on a position is
invisible.

**8/11 — QB ADPs look like 1QB numbers in a superflex league.** Josh
Allen at 29, Mahomes at 128, Willis at 140 while Gibbs is 1 and Bijan 2.
In a room that starts two quarterbacks the elite ones go far earlier than
that, so adp_2qb is probably missing for many of them and _adp is falling
back to the 1QB tier — silently, because only the value was read and the
`exact` half of its return was discarded. lineup_value now reads both and
prints a WARNING naming the quarterbacks that fell back, since every
"reachable at pick 104" call on those names is optimistic. NOT yet fixed,
only surfaced. Reopens: if the warning fires on the 8/18 board, the
survival math for QBs cannot be trusted and the fix is to source a real
superflex ADP.

**8/11 — the plan spent pick 8 on a player who lasts to 29.** Josh Allen
carries a superflex ADP of 29; the greedy plan took him at pick 8 and
then took Bowers at 17 — but Allen survives to 17, so the ordering threw
away everything between. Added a two-pick lookahead: taking the expiring
player yields value(G) + value(best survivor); taking the survivor yields
value(S) + value(2nd survivor); so reach for the expiring player exactly
when he beats the SECOND-best survivor. The plan now prints why it
reached. Values used are pre-pick estimates — after a quarterback lands
every other quarterback collapses to ~+25, so the lookahead understates
how much the ordering matters. Reopens: a real solution optimises the
whole ten-pick path, not two at a time; this is the cheap version.

**8/11 — the ADP fallback suspicion was WRONG.** I argued Josh Allen at
29 and Mahomes at 128 had to be 1QB numbers leaking through a silent
fallback. The header reads "ADP market: adp_2qb (SUPERFLEX)" and no
quarterback triggered the warning — the superflex market really does
price them there. The check earns its place anyway: it is what turned a
plausible theory into a settled question in one run instead of a
redesign. Reopens: n/a.

**8/11 — SUPERSEDES the "ADP fallback suspicion was wrong" entry above.**
He asked "Allen's superflex is 29?" and he was right to. My clearance was
worthless. _adp returns (value, exact) where exact is False ONLY when the
value came from the `fallback` tuple — but `keys` for a superflex league
is ("adp_2qb", "adp_dd_ppr", "adp_ppr", "adp_half_ppr", "adp_std"), and
_pick returns the FIRST key present. A missing adp_2qb therefore yields a
1QB PPR number reported as exact=True, and the warning I built could
never fire for the case it was built for. The pattern was visible without
any of this: Gibbs 1, Bijan 2, McCaffrey 3, Nacua 4 with Allen at 29 is a
1QB PPR board, not a room that starts two quarterbacks.
Consequences: every QB survival call in the plan is optimistic —
"Mahomes lasts to 128" would be badly wrong in superflex, and the
mid-round-QB strategy I recommended rests on it. Fixed detection: ask
weekly_projections week 1 whether the adp_2qb FIELD exists per player,
mark rows [1QB adp] / adp*, and warn. Also: ~/.sleeper_cache/
adp_<season>_adp_2qb.json has been storing 1QB values under the superflex
key, so it must be deleted before a rerun means anything. NOT fixed:
sourcing real superflex ADP where the field is absent. Reopens: that is
now the last thing worth building before 8/18.

**8/11 — lesson for the next session.** Twice today I treated "the check
did not fire" as evidence. The first time the check was vacuous (this
entry); earlier the THIN bar fired on five of nine starters and I read it
as signal. A check is only evidence once you have seen it fire on a case
you know is bad. Write the failing case first.

**8/11 — superflex_adp.py: Sleeper has no 2QB market, so build one.**
Confirmed on his machine: 33 of 33 quarterbacks carry no adp_2qb field.
Both Hybrids have been drafting off a single-quarterback board — one
where no QB goes in round 1 of a league that starts 24 of them, and
Mahomes "survives" to pick 128. New module, two tiers in preference
order. (1) probe() asks the per-player season endpoint, the same place
dynasty ADP comes from that the bulk feed omits; if a real 2QB field
exists there we cache it and this is just a fetcher. (2) If not, derive:
keep the skill players' 1QB ORDER (twelve managers ranking backs is real
signal and superflex does not change which back is better), re-price
quarterbacks off QB24 rather than QB12, insert each QB among the skill
players where his surplus matches theirs, and recompute every pick
number from the merged order — so inserting QBs pushes skill players
later exactly as a real superflex room does. Cached at
~/.sleeper_cache/sflex_adp_<season>.json, deliberately NOT the poisoned
adp_<season>_adp_2qb.json. lineup_value uses it automatically when every
QB lacks a real 2QB price, and labels the board DERIVED. 11 checks.
Reopens: the derivation is surplus-based, and real superflex markets
overweight positional panic beyond what surplus justifies — if the
derived board puts fewer QBs in round 1 than he has seen in these rooms,
the market is doing something the model is not, and room_bias.py should
measure it once picks exist.

**8/11 — Sleeper DOES have a 2QB market; it is on the per-player
endpoint.** The probe found adp_2qb (and adp_dynasty_2qb) where the bulk
weekly feed carries neither — the same asymmetry that already forced
dynasty ADP through per-player calls. So superflex_adp is a FETCHER
first and a model only for gaps. Real prices confirm the size of the
error: Josh Allen 29 -> 1, Mahomes 125 -> 29, Willis 140 -> 32, Purdy
102 -> 20. Every one of those is a quarterback the 1QB board said would
last sixty to a hundred picks longer than he will.

**8/11 — the first superflex board mixed two rulers.** Fetched players
kept their true ADP while everyone else got a 1,2,3 merged RANK, so Josh
Allen and Jahmyr Gibbs both read "pick 1" and Lamar Jackson collided with
De'Von Achane at 11. Pick numbers from different scales cannot be
compared, and every downstream "reachable at pick N" was that comparison.
Fixed twice over: fetch_all now pulls adp_2qb for the WHOLE pool (~0.09s
per player, cached permanently, saved every 25 so a Ctrl-C keeps the
work), and any player still missing a price is interpolated BETWEEN the
two real anchors his surplus falls between rather than numbered on a
separate scale. Ties are nudged apart so no two players claim one pick.
lineup_value now switches to this board when ANY quarterback lacks a real
price, not only when all of them do — a board half-priced by each market
is worse than either. Reopens: interpolation assumes surplus maps
monotonically onto draft position, which is roughly true within a
position and rougher across them.

**8/11 — the superflex ADP was computed and then thrown away.**
marginal_values returns {**c, ...} — a COPY of each candidate — so
rewriting cands[i]["adp"] AFTER the simulation changed nothing the plan
or the table ever read. The board announced "REPLACED with a DERIVED
superflex board" and then printed Josh Allen at adp 29 and planned all
ten picks off the 1QB numbers. A banner claiming a fix is not a fix.
Two changes: the whole ADP resolution now runs BEFORE marginal_values,
and the repricing mutates the same candidate objects the simulation will
copy (matched by pid) rather than a parallel list. Reopens: any future
value written onto a candidate after marginal_values has the same
problem — set it before, or set it on rows.

**8/11 — the Hybrid boards were recommending rivals' KEPT players.**
lineup_value excluded his own roster and anyone already drafted, but in
a pre-draft keeper league the rosters endpoint holds what every OTHER
manager kept — roughly five per team, ~55 players in a 12-team Hybrid —
and none of them reach the board. They were sitting in the candidate
pool being scored as picks. Two fixes, both required. (1) Rivals'
keepers are excluded from candidacy. (2) KEEPER DEPLETION: ADP is a
price from drafts where everyone was available, so every remaining
player's real pick number is his ADP minus the keepers ranked above
him. In a 12-team Hybrid that is dozens of picks, and it is the same
error keeper.py made on 8/11 when it called Derrick Henry reclaimable at
65 with ~30 kept players ahead of him. The display shows "56<61" so the
shift is visible rather than silent.
Ordering matters and cost a rewrite: keepers are priced on the SAME
board as everyone else (superflex market applied to the full pool)
before being split out, because computing depletion from 1QB numbers
while candidates carry superflex numbers compares two rulers — exactly
the bug fixed one entry earlier. Reopens: depletion assumes the keeper
set is final; a manager who drops a keeper before the draft makes it
slightly pessimistic.

**8/11 — THE LG03-LG05 QB SITUATION, and a reversal of my advice.** With
rivals' keepers finally excluded, the available quarterback pool is Dak
Prescott, Trevor Lawrence, Justin Herbert, Jared Goff, Malik Willis,
Kyler Murray, Baker Mayfield, Darnold, Stroud, Bryce Young, Geno Smith.
Every elite one is KEPT: Allen, Lamar, Maye, Burrow, Caleb Williams,
Mahomes, Dart, Nix, Purdy — plus Jayden Daniels on his own roster. 66
players kept in total.
This inverts what I told him twice. I first said skip QB early because
the position is deep in the middle rounds (read off a 1QB board), then
said take one early because superflex prices them in round 1. The real
reason to take one at pick 8 is neither: it is that the top ten
quarterbacks in this league are not draftable at all, so the drop from
Herbert/Lawrence/Dak to the next tier is a cliff, and after depletion
Herbert's real pick number is 7 — before his turn.
Both earlier claims were right about mechanics and wrong about this
league, because the tool was scoring 66 players who cannot be picked.
Reopens: if a rival drops a keeper before 8/18 the pool changes; rerun
roster_snapshot and lineup_value that morning.

**8/11 — two display bugs from that run.** The header announced "38 of 38
quarterbacks have NO adp_2qb field" and then, two lines later, that it
had replaced the board with 230 real adp_2qb prices — both true (the
weekly feed has none, the per-player cache has 230) and together
unreadable. Reworded. And interpolated players were tagged "[1QB adp]"
when they are interpolated onto the SUPERFLEX scale; a correct number
was wearing the label of a known bug. Now "[interp]".

**8/11 — Milroe confirmed QB3 in Seattle; he will be cut after the
draft (user).** RotoWire's depth chart has Darnold, then Lock, then
Milroe. The 15.3-point projection is accurate, not a modelling artifact,
so LG03-LG05's SUPER_FLEX is genuinely empty and filling it is the
largest single number on his board (~+348). He plans to release Milroe
once the draft is done. Consequences: (1) the pick-8 quarterback stands;
(2) his active roster is effectively 6, not 7, so one more of the 14
open active slots is real; (3) every QB row reading "displaces Jalen
Milroe" is displacing ~nothing, which is why they all price within a few
points of their full projection. He is NOT taxi-eligible — the redshirt
expired — so the spot he occupies is an active one until cut.
This is also the first research ever run on one of his own kept players.
The 447-dossier pass covered the draftable pool only, so all seven were
invisible; Milroe is exactly what that gap hides. Reopens: run the same
check on Brashard Smith and Jayden Higgins before 8/18.

**8/11 — depth-chart check on the last two unresearched kept players.**
Brashard Smith is RB4 in Kansas City behind Kenneth Walker, Emmett
Johnson and Emari Demercado — his 24-point projection is accurate and
the user's read that he will not stay is right. Jayden Higgins is WR2 in
Houston behind Nico Collins, which is a REAL role: his 198 projection is
a genuine starter's, not a placeholder, and the THIN flag on him (198 vs
a WR43 bar of 204) is marginal rather than damning. So do not plan to
replace Higgins — plan to add above him.
Net LG03-LG05 roster after cuts: Daniels (QB), Henry (RB1), St. Brown
(WR1), Higgins (WR2), Loveland (TE). Four real holes — SUPER_FLEX, RB2,
WR3, FLEX — against ten picks plus the second draft. That matches what
lineup_value has been saying, now confirmed against depth charts rather
than inferred from projections.
All seven kept players are now researched. The 447-dossier pass covered
draftable players only; this closes that gap for the leagues that matter
before 8/18. Reopens: depth charts move through preseason — recheck the
morning of the draft.

**8/11 — the draft has two jobs, and the plan now runs both.** His
correction: drafted-rookie eligibility attaches to players HE drafted in
their NFL rookie year, and DROPPING one destroys it permanently. He
believes Higgins and Loveland qualify. If so his 2027 core is already
locked — 3 keepers (Daniels, Henry, St. Brown) plus 2 DRs (Higgins,
Loveland) — and this draft's second job is stocking two taxi seats with
2026 rookies who carry over free WITHOUT consuming a keeper or DR slot,
exactly as Milroe and Smith did last year.
Built into lineup_value: the last N picks (N = open taxi seats) are
RESERVED and filled by taxi_pick(), which ranks 2026 rookies by DYNASTY
adp — the market's view of their future — and deliberately excludes any
rookie good enough to start in 2026, since he belongs on the active
roster where a seat is not the constraint. Ranking a stash by 2026
points is what put Geno Smith (+8) and Chig Okonkwo (+7) in picks 104
and 113. The report also names which rostered players are
drafted-rookie eligible, via keeper.py's dr_eligible() rather than
assumption, and states that a cut is permanent.
Reopens: dr_eligible walks previous_league_id chains and multiple drafts
per season; if it returns nothing for a league the chain is broken and
the DR list will be silently empty — check it names Higgins and Loveland
before trusting the rest.

**8/11 — the taxi picks came back empty because rookies were filtered
out by projection.** "TAXI: no reachable rookie left" at both 104 and
113 while the entire rookie class sat outside the candidate shortlist.
Cause: the pool drops anyone projecting <= 0 and is then truncated to
the top ~240 by 2026 points. A taxi-profile rookie projects almost
nothing — that is the whole reason to park him — so every one of them
was cut before taxi_pick ever ran. The feature was looking for players
the pipeline had already discarded. Fixed: rookies (years_exp 0) are
kept regardless of projection and are re-appended after truncation, so
they still receive the superflex market and keeper depletion but never
compete for a place on the 2026-points shortlist. The plan now reports
how many rookies are on the board and how many carry a dynasty price.
Reopens: a rookie with no dynasty ADP is still unrankable for a stash;
if the count of priced rookies is low, dynasty ADP coverage is the gap.

**8/11 — DR eligibility is BROADER than he assumed, and confirmed by
data.** dr_eligible names four: Brashard Smith, Colston Loveland, Jalen
Milroe, Jayden Higgins. He had guessed Higgins and Loveland. Jayden
Daniels is NOT on the list for this league — he is a regular keeper
here, which is consistent with the Daniels-as-drafted-rookie story
belonging to the emoji Hybrid. So: 3 keepers (Daniels, Henry, St.
Brown) + 2 DR from four eligible. Cutting Milroe and Smith is still
right, but it is not free — it permanently burns his only two spare DR
options, so if Higgins or Loveland busts there is no fallback. Reopens:
worth re-checking before he actually drops them, not after.

**8/11 — the taxi picks were still empty: a redshirt has no redraft ADP,
and I was requiring one.** After fixing the pool filter, 300 rookies were
on the board with 117 carrying a dynasty price, and taxi_pick still
returned nothing. Cause: the reachability test demanded
`adp is not None and adp - shave >= pick`, so every rookie the redraft
market does not rank at all — precisely the population a taxi seat
exists for — failed at the first clause. The absence of a redraft price
is the SIGNAL, not a missing value: if the market does not rank him,
nobody in this room is spending a pick on his 2026 production, so he
lasts. Only an explicit ADP earlier than the pick now means he is gone.
Third distinct bug in the same feature, all the same shape: the taxi
pipeline kept applying 2026-production logic to players whose defining
property is that they will not produce in 2026. Reopens: none of the
three would have been caught by a test that did not include a genuine
redshirt — the fixture now does.

**8/11 — the taxi picks were empty a fourth time, and it was the copy
bug I had already documented.** marginal_values returns {**c, ...} —
copies — so 'dadp' being set on candidates AFTER the call meant every
row reaching taxi_pick carried dadp=None and failed the last filter.
I wrote the warning for exactly this when the superflex ADP hit it
("any future value written onto a candidate after marginal_values has
the same problem — set it before, or set it on rows"), then did it
again one feature later and spent three rounds hunting the wrong
filters. Fixed: ALL candidate mutation now happens before the
simulation, the constraint is stated at the top of marginal_values, and
two selftests pin it — a field set after the call must NOT appear on the
row, a field set before must. Lesson worth more than the fix: a comment
warning about a trap does not prevent the trap. A test does.

**8/11 — LG03-LG05 draft card written; the 8/18 plan is closed.** Taxi
picks resolve (Chris Brazzell WR, dynasty ADP 128; Le'Veon Moss RB, 236),
and the top eight picks have been identical across four consecutive runs
through four separate bug fixes, which is the strongest evidence
available that they are not an artifact. lg05_brief.md rewritten as
a draft-day card: roster after cuts, pick-by-pick with alternates, the
rules that bind (two taxi seats fillable only during the draft, four DR-
eligible players for two slots with cuts permanent, two-stage draft,
non-PPR scoring), and an explicit list of what the plan does not know.
The two genuine judgment calls are flagged rather than hidden: picks 41
and 56 both take a player who will not survive over one who scores
higher and will, which is right only if the survival read holds.
Reopens: the emoji Hybrid has no plan and no research queue; LG04
drafts Sep 6; LG02 has nothing. LG01 is mid-draft with DEF
unfilled and 3 taxi seats open.

**8/11 — HANDOFF.md rewritten for a cold start.** Per CLAUDE.md the
handoff is a snapshot and gets rewritten at session end. It now carries:
per-league status with the one thing each needs next; the 8/18 plan in
two sentences with the real reason for QB at 8; the five model errors
found and fixed today, each with the symptom a future session would see;
the new files and what each is for; an explicit "what to distrust" list;
open items; and the process lessons that cost time. Selftest counts are
recorded (55/54/37/10/9/23) with a note that a LOWER count means a check
was deleted rather than fixed. Durable rules stayed in CLAUDE.md and the
reasoning stayed here — the handoff points at both rather than repeating
them. Reopens: rewrite again at the end of the next session; it goes
stale the moment a pick lands.


**8/12 — LG05 draft card written; the QB conclusion from the
other Hybrid does NOT transfer.** He is slot 8 of 12 in this league too,
same picks (8, 17, 32, 41, 56, 65, 80, 89, 104, 113), same 9:00 AM start
as the no-emoji Hybrid — he is on the clock in both rooms simultaneously,
ten times, which is now the binding practical constraint on how these
cards are written. Where the other league had every elite quarterback
kept and needed one at pick 8, this one has Lamar (404) and Daniels (382)
already holding QB and SUPER_FLEX and six draftable quarterbacks over 300
points. Spend nothing there. 98 players are kept by rivals, which halves
every real pick number: Henry costs market pick 46 and this draft's pick
11. Plan: Henry 8, McConkey 17, Parker Washington 32, Kelce 41, Reed 56,
Price 65, Geno Smith 80, Okonkwo 89, taxi at 104/113. Reopens: if a rival
drops a keeper before Tuesday every adjusted price below him moves.

**8/12 — I recommended a tight end strategy off dynasty ADP and it was
wrong.** The first version of the card said take no tight end at all and
upgrade Gadsden in the second draft, because the `board` tool priced
Andrews at 154 and Kelce at 170. That is DYNASTY ADP on a SUPERFLEX
board. Real keeper-adjusted superflex numbers: Hunter Henry 53, Andrews
56, Kelce 64, Likely 70 — every one inside round 6, none reaching the
second draft. There was no free tight end. What makes this worth logging
is that I had flagged the dynasty-ADP substitution as the shakiest thing
in the brief and shipped the recommendation anyway. Naming an assumption
is not the same as refusing to build on it. When the only available
number is known to be the wrong ruler, the honest output is "I cannot
price this yet," not a recommendation with a caveat attached.

**8/12 — Depth-chart check caught Gadsden, which the session premise had
assumed safe.** The starting prompt said "Gadsden is my only tight end,"
true but incomplete: David Njoku signed in Los Angeles and the Chargers'
first unofficial depth chart lists the starter as "Charlie Kolar OR
Oronde Gadsden OR David Njoku." Gadsden projects 182 against a 216
replacement bar. Kyle Williams checked out as WR7 in New England behind
A.J. Brown and Romeo Doubs, so his 35-point projection is the depth
chart rather than a model error — the Milroe case, caught by the same
rule. The rule earns its keep: check every rostered player, including
the ones the prompt tells you are fine.

**8/12 — lineup_value's roster header asserted the opposite of its own
code.** It printed "{len(roster)} active players simulated · {len(taxi)}
on taxi (cannot start, excluded)". Both numbers were computed correctly
and the sentence was still false, because build() keeps EXPIRED
redshirts in `roster` (correctly — the redshirt expires, they are active
this season) while Sleeper's taxi field still lists them. On his
seven-man roster it read "7 active · 2 on taxi (cannot start, excluded)"
— nine players, two counted twice and described as unable to start while
they were starting. This is HANDOFF bug #5 in a new place, and worse in
one specific way: the LINEUP was right, so nothing looked broken, and a
future session reading the header would have re-derived the wrong roster
from a correct simulation. Fixed by extracting `taxi_line()`, which
splits the taxi field through taxi_split and names the expired group as
active. Four selftests pin it, and per the 8/11 lesson they were run
against the OLD header first and confirmed to FAIL there — a check that
has not fired on a known-bad case is not evidence. lineup_value selftest
count 54 -> 58. Reopens: `roster_snapshot.py` and `dashboard.py` both
report taxi counts too; neither was audited for the same overlap.


**8/13 — a roster is not a keeper list until it has been purged, and the
whole 🦸💪 plan was priced as though it were.** His correction: "two
teams never dropped their non keepers so we couldn't know who was going
to be available." Sleeper's roster endpoint before the purge returns
whatever a manager has not bothered to clean up, and `build()` counted
every rostered rival player as kept. That broke the board in two
directions at once. Real draftable players were excluded from the
candidate pool outright, so they could never be recommended. And the
depletion count was inflated, so `deplete_adp` shifted every surviving
ADP too many picks forward and the plan reported players as "GONE by
your next turn" who were never going anywhere. The 98-kept figure that
turned Derrick Henry from market pick 46 into pick 11 was carrying
roughly 26 players who are going back in the pool.

Fixed with `legal_keeper_cap()`: in a league flagged `"keeper": true`,
each rival is capped at the allowance the rules actually grant — 5
active (3 keepers + 2 drafted rookies) with at most 2 QB, plus taxi
riders, which carry free. The retained five are his best by projection,
which is a guess, but a far smaller one than assuming he keeps eighteen.
The QB cap earns its place in superflex specifically: a rival sitting on
four quarterbacks can legally hold two, and the other two are draft
pool.

The design choice worth keeping: this needs no flag and is never
opt-in. A roster that HAS been purged already sits at or under the
allowance, so the cap is a no-op there. It bites only the stragglers and
stops biting on its own as they clean up. A correction that switches
itself off cannot be left on by accident.

Twelve selftests pin it; count 58 -> 70. Reopens: (1) `draft_helper.board_data` builds its own
kept/gone sets and was NOT audited — the `board` tool and the dashboard
may still be reading uncapped rosters; (2) best-5-by-projection is a
prior, not knowledge, so the numbers move again when those two teams
actually purge — rerun on draft morning; (3) the 8/18 pick table was
built on the uncapped board and every survival call in it is suspect
until it is regenerated.


**8/13 — the second-QB keeper is conditional, and a flat "max 2 QB" got
it wrong.** His correction, an hour after the keeper-cap fix shipped: "a
rival holding 4 QBs can hold 1 Drafted Rookie QB and one regular Keeper
QB but he had to draft the rookie QB." The two QB allowances are not
interchangeable. One QB may take a regular keeper slot. A second may
take a DRAFTED-ROOKIE slot, and only if that manager drafted him
himself in the player's rookie year — acquired by trade does not
qualify. So a rival sitting on four quarterbacks keeps TWO only when one
of them is his own drafted rookie, and otherwise keeps ONE.

The flat cap I shipped first let every hoarder keep two, which hid a
real quarterback per hoarding team from a SUPERFLEX board. That error
runs the wrong way twice: the room looks thinner at QB than it is, the
model pulls rivals' quarterback picks earlier than they will actually
come, and skill players then look like they last longer than they will.

Implemented as an actual slot assignment rather than a count: 3 keeper
slots (max 1 QB, anyone) + 2 DR slots (max 1 QB, DR-eligible only) +
free taxi. DR-eligible players are placed in DR slots FIRST, because a
keeper slot holds anybody and a DR slot does not — spending the
flexible resource first strands the rigid one. Eligibility comes from
`dr_eligible_by_owner()`, which applies keeper.py's rule to every
manager at once: keeper.dr_eligible() re-walks the whole
previous-league chain per uid, and doing that eleven times for
identical data would hammer the API. One walk, bucketed by picked_by,
enumerating /drafts rather than league.draft_id because a season can
hold multiple drafts.

A consequence I had backwards until a test failed: the DR slots are NOT
a second allowance, they are an allowance CONDITIONAL on having drafted
the man yourself. A rival with nobody DR-eligible keeps 3, not 5. I
wrote the test expecting 5 + taxi, it failed, and the code was right.
Worth recording because the same wrong intuition produced the flat QB
cap an hour earlier.

Count 65 -> 70. Reopens: everything the previous entry reopened, plus —
this makes the QB pool materially deeper than Tuesday's card assumes,
and the card's "spend nothing at quarterback" call now rests on an even
larger surplus than it was written against.


**8/13 — the cap is on CARRYOVER, not on roster size.** His
clarification: "they can have many QBs on the roster, they just can't
bring them to next year except for the explicit rule around keepers."
The logic was already right — `legal_keeper_cap` models what a manager
brings forward, and the surplus is released before the draft, which is
exactly why it belongs on the board. The PROSE was wrong. The header
line said a QB pile "is thinner than it looks," which reads as a claim
about how many a rival may hold, and the docstring used "keeps" where it
meant "carries." Nothing binds what a rival may ROSTER, all season,
without limit.

Logged because the failure mode is specific and repeatable: a comment
that describes a correct mechanism in the wrong vocabulary survives
every test, and a future session reads the comment, not the assignment
loop. This is the third report-versus-reality defect in two days
(taxi header, turn-plan banner, now this), and the first two were caught
only because he read the output. Wording that a test cannot fail is
exactly where they hide.


**8/13 — roster census, and the ceiling is 7, which I had not actually
enforced.** He asked for it directly: "there should be a max of 7
players per team, but some folks just dropped their full roster down to
7 or less and I want to make sure we're tracking it appropriately." Two
things came out of it.

First, a bug in the cap I shipped an hour earlier. `legal_keeper_cap`
ended `return set(keep) | taxi_ids` with taxi UNBOUNDED, so the ceiling
was 3 + 2 + infinity rather than 3 + 2 + taxi_slots. Sleeper does not
clear expired redshirts from the taxi field — John's own Gadsden and
Kyle Williams still show there — so a rival listing six taxi names would
have carried all six, and an expired redshirt is an ACTIVE player, not
free carryover. Taxi is now capped at the league's taxi_slots.

Second, `roster_census()`: per team, rostered / on taxi / legal carries
/ released / quarterbacks released, sorted worst first, printed above
the value board. The point he was making is that the raw count is not
the test. A team sitting AT 7 with an empty taxi carries 5 and releases
2. The census reports both numbers because neither alone settles it.

And the thing that keeps happening: a team with NO drafted-rookie
eligibility of its own tops out at 3 + taxi, not 7, because the DR slots
are conditional and unusable without them. I wrote the census test
expecting a 7-man roster to release 2 with an empty DR map; it failed at
4 and the code was right. That is the third time in one session that my
mental model of this rule was more generous than the rule, always in the
same direction — assuming allowances are additive when they are gated.
Both cases are now pinned as tests so the next session inherits the
distinction instead of the intuition.

Count 70 -> 77. Reopens: the census only runs where keepers.json says
"keeper": true, so LG01 and LG02 get nothing; and the
released-player estimate still assumes best-by-projection retention,
which is a prior, not knowledge.


**8/13 — the census printer crashed the draft plan, and the fix is a
test that catches the class.** `report()` unpacks eleven names from
`build()`, one of which is `rows`, the candidate board the draft plan
reads about two hundred lines later. The census block I added bound its
own list to `rows`. Everything above the plan printed perfectly and then
it died on `KeyError: 'pid'` — a display-only block silently redefining
its caller's data, which is the cheapest possible bug and still cost a
live run five days before the draft.

Renaming to `cen` fixes the instance. What fixes the class: a selftest
that parses this file with `ast`, reads the tuple `report()` unpacks
from `build()`, and asserts no name in it is ever reassigned inside
`report()`. Verified by mutating the source back to the broken form and
watching the check fail — per the 8/11 rule, a check that has not fired
on a known-bad case is not evidence. Count 77 -> 78.

**8/13 — the cap's live effect: rival keepers 98 -> 58.** Nine of twelve
teams still hold more than they can carry, releasing 15 players
including 4 quarterbacks. Note the shape, because it is not what I
predicted: I expected two badly unpurged rosters of ~18. The reality is
nine teams sitting at 6-7 with an EMPTY taxi, each 1-2 over, because
without taxi riders the ceiling is 5, not 7. The remaining gap from 98
to 73 rostered is the league purging over the last two days, not the
cap. Reopens: those nine will keep purging, so rerun on draft morning.


**8/13 — SUPERSEDES the keeper-cap entries above. The board does not cull
rosters.** His correction: "since teams have purged their rosters on July
1st or so, the roster max can be 7. The players in taxi can be moved. We
should look at the roster and assume a max of 7, we should look at the
pool of FA after. We will not be culling anyone's roster if they're over.
That's the commissioner's job."

Two errors in what I built, and the second is the serious one.

The mechanical error: I modelled the ceiling as 3 keepers + 2 drafted
rookies + 2 taxi with the split ENFORCED, which made a team holding
seven with an empty taxi look two over. Taxi players can be moved, so
the split is the manager's business and only the total binds. Seven is
seven.

The judgment error: having decided a roster was over, the board then
guessed which players would be dropped and handed them back as
draftable. That is a guess stacked on a guess, and worse, it is a tool
quietly overruling a human decision nobody has made yet. Enforcement is
the commissioner's job. A board that silently reassigns another
manager's keepers will be confidently wrong in a way no test catches,
because the code is doing exactly what it was written to do.

The rosters are post-purge. A rostered player is kept, the draftable
pool is everyone else, and an overage is a line of output. `roster_census`
now returns counts only — a test asserts no player is ever named for
release — and prints "OVER — commissioner's call" with an explicit note
that if cuts are forced, those names hit the pool late and the board will
not have seen them coming.

`legal_keeper_cap` and `dr_eligible_by_owner` are DELETED rather than left
uncalled, along with their twelve tests. Both were correct implementations
of a rule the league does have; the danger was never the code, it was that
a future session finds a tested, working culling function sitting unused
and wires it back in. The DR/QB slot logic is recorded in the entries above
if it is ever wanted for HIS OWN keeper decisions, which is keeper.py's job.

Count 78 -> 64. A lower count normally means a check was deleted rather
than fixed; here it means a rule was deleted because it was not real.


**8/13 — DRAFT PICKS ARE TRADEABLE AND THE TOOLKIT DOES NOT KNOW.** His
question: "draft picks can be traded, take a look at both hybrid
leagues." Both have trades, and he is on the receiving end of one in
each.

  LG03-LG05 (9000000000000000014), draft 9000000000000000015
    round 8, roster 1 (slot 11) -> HIM (roster 6)   = pick 86
    round 9, roster 1 -> roster 2                   = pick 107, rival
    round 9, roster 3 -> roster 1                   = pick 98, rival
  LG03-LG05 emoji (9000000000000000020), draft 9000000000000000021
    round 8, roster 1 (slot 7) -> HIM (roster 11)   = pick 90

He has ELEVEN picks in each league, not ten, and loses none. In the
emoji league the extra pick is 90, immediately before his own 91 —
consecutive picks, which is a real tactical asset because it lets him
gamble on survival at 90 with a free recovery at 91.

`grep -rn traded` across the toolkit returns one unrelated comment.
Nothing reads `/draft/{id}/traded_picks`. `snake_picks()` is pure
arithmetic and three files depend on it — draft_helper, keeper,
lineup_value — so every pick list, every turn plan, and every
"reachable / GONE by your next turn" survival call in this repo has been
computed against a pick set that may not be the user's. Silent, and
wrong in the direction that matters: a missing pick makes the plan
under-count its own turns.

Also resolved as a side effect: `/draft/{id}` carries `draft_order` and
`slot_to_roster_id`, both now published. His slots are VERIFIED at 6
(emoji) and 8 (no-emoji) rather than assumed. That is the third slot
correction in two days and the first one grounded in the API instead of
inference — the endpoint was available the whole time.

Fix, not yet written: fetch traded_picks in board_data/build, map
roster_id -> slot via slot_to_roster_id, convert (round, slot) to an
overall pick, then add gained and subtract lost before any turn plan
runs. Until then every card carries its pick list by hand.

Reopens: LG01 and LG04 were not checked for traded picks;
LG01 is mid-draft, so a traded pick there would corrupt the live
turn plan the same way.


**8/13 — the two Hybrids do not share a draft format, and snake_picks()
could not express one of them.** He handed me his real card as
`1.8 2.5 3.5 4.8 5.5 6.8 7.5 8.8 8.11 9.5 10.8` and said it should be
telling me something. It was: a plain snake from slot 8 gives 3.8 and
4.5, his league gives 3.5 and 4.8. `settings.reversal_round` is **3** in
LG03-LG05 and **0** in the emoji league.

A reversal at round R makes round R repeat R-1's order instead of
flipping, then alternates from there. It compensates late-slot pickers,
and from round R down it inverts every number a plain snake predicts. At
slot 8 he picks 5th in BOTH rounds 2 and 3 rather than waiting 15 picks
for 3.8.

Consequences: his real picks are 8, 17, 29, 44, 53, 68, 77, 92, 95, 101,
116 — the card had 8, 17, 32, 41, 56, 65, 80, 86, 89, 104, 113, correct
for the first two rounds and wrong for the remaining nine. Every
"reachable / GONE by your next turn" call in that league was computed
against picks he does not own. The traded round-8 pick also moves: roster
1 sits at slot 11, round 8 runs FORWARD under the reversal, so it is
8.11 = overall 95, not the 86 I derived assuming a reverse round.

`snake_picks` now takes `reversal_round`, read from the draft settings
in `build()` and threaded to the turn plan, which prints the format and
warns when a reversal is active. Six selftests, including his verbatim
card as the fixture and a pair asserting that a reversal helps a late
slot and costs an early one. The plain-snake path is unchanged and
pinned.

The lesson is narrower than "check the settings." I had already fetched
`/draft/{id}` twice today for `slot_to_roster_id` and `traded_picks` and
read straight past `reversal_round` sitting in the same object, because
I was not looking for a format I did not know existed. Two of the last
three corrections came from him reading output I generated. The
arithmetic was never the weak point; assuming I knew the shape of the
problem was.

Reopens: `draft_helper.my_next_picks` and `keeper.upcoming_picks` have
the same defect and are NOT fixed — the board tool and keeper.py still
print plain-snake numbers for LG03-LG05. LG04, LG02 and LG01 have not been checked for a reversal.


**8/13 — pick geometry consolidated into sleeper_client; all three
consumers fixed.** He confirmed LG04, LG02 and LG01 are
2026 startups with no traded picks, and LG01 reads
reversal_round=0 from the API, so only the two Hybrids carry any of this
complexity. Verified rather than assumed — LG01 is mid-draft and
a reversal there would have been corrupting a live turn plan.

The root cause was three copies of the same arithmetic. draft_helper's
my_next_pick, keeper's upcoming_picks and lineup_value's snake_picks each
implemented a plain snake independently, so a format the toolkit did not
know about broke all three at once and no single fix could reach them.
sleeper_client now owns it: round_is_forward, slot_picks, overall_of,
traded_deltas, my_draft_picks. lineup_value.snake_picks delegates rather
than duplicating; draft_helper and keeper read reversal_round from the
draft settings; keeper additionally applies traded picks when given a
roster_id.

my_next_pick keeps its own forward walk on purpose — it answers "when
does my SEAT come up next" from an arbitrary point in a live draft,
which is a different question from "which picks do I hold." A test now
walks it round by round and asserts the result equals the closed form
from slot_picks under both formats, so the two implementations are
pinned to each other instead of drifting.

End-to-end against the real API payloads: no-emoji resolves to 8, 17,
29, 44, 53, 68, 77, 92, 95, 101, 116 and emoji to 6, 19, 30, 43, 54, 67,
78, 90, 91, 102, 115. Both match the cards, and the no-emoji list matches
the card he read off Sleeper himself.

test_all 23 -> 25. Reopens: dashboard.py and draft_review.py were not
audited for their own pick arithmetic; roster_snapshot's "picks
remaining" count still assumes one pick per round.


**8/13 — P0 of ROADMAP.md done: owned picks, taxi filter, bye pressure.**

**P0-1, the turn plan now uses OWNED picks.** `build()` captures the
user's roster_id off the roster walk, calls `my_draft_picks()`, and
stores the result. `report()` uses that list instead of
`snake_picks(--slot)`, prints traded-in and traded-away picks
explicitly, and flags consecutive picks — he holds 90 and 91 in the
emoji Hybrid, which is worth saying because back-to-back turns let you
gamble on survival for free.

It also derives the slot from the PUBLISHED draft order rather than the
`--slot` the user typed, and prints a SLOT MISMATCH warning when the two
disagree. That check would have caught the 8-versus-6 error I made: I
handed `--slot 8` to a tool that had the real answer in an object it had
already fetched.

**P0-2, the taxi filter no longer requires a dynasty price.** Of 300
rookies only 117 carry one, and the other 183 ARE the redshirt
population — a player nobody drafts is a player no market ranks. Both
Hybrids reported "no rookie qualifies" at all four taxi seats. Priced
rookies still win when they exist, because a price is real information;
only when none is priced do the unpriced compete, youngest first with a
name tiebreak so the answer is stable across runs.

This is the third time the same shape of bug has been fixed in this
function: rank by 2026 points (wrong, a redshirt scores nothing), then
require a redraft ADP (wrong, he has none), now require a dynasty ADP
(wrong for the same reason). The lesson that keeps not sticking: every
filter that demands a market signal excludes exactly the population a
taxi seat exists for.

**P0-3, bye pressure.** New `byes.json` — season data, no Sleeper
endpoint exists for it, the player table does not carry the field, and
`load_byes()` refuses to answer rather than lying when the season key
does not match. Every candidate now carries `bye`, the plan tracks the
bye shape of the roster it is building, and the report prints
availability per week with a SHORT flag when a week cannot field a
lineup. Its own 8/13 emoji plan would have tripped it: six of fourteen
out in week 13.

A real latent bug surfaced while testing it. `bye_pressure` filtered
into a list and then called `len(list(roster_byes))` on the original,
which returns 0 for any generator — every week would have reported
negative slack. Caught only because a test expectation of mine was wrong
first and I went looking at the helper. Now materialised once and pinned
by a generator test.

lineup_value 70 -> 85, test_all 25 -> 26. Reopens: the bye check reports
but does not re-rank; `draft_helper`/`dashboard` do not read byes at all;
byes.json must be replaced for 2027 and nothing enforces that beyond the
season-key guard.


**8/13 — the bye work crashed on his first real run, and the reason is a
coverage hole worth naming.** I loaded byes near the top of `build()` and
stashed the note on `market` in the same breath, 84 lines before the
dict is created. `UnboundLocalError` on the first live invocation.

All 85 selftests passed. All 26 in test_all passed. Neither suite
touches `build()` at all, because it needs the live API — it is the
single largest function in the file and the only one with no coverage.
Everything downstream of it is well pinned, which is exactly why this
felt safe and wasn't.

Fixed by moving the assignment to where `market` exists, and guarded by
a static AST walk that asserts no `market[...]` subscript in `build()`
appears before the line that creates it. Same trick as the report()
rebinding check: it catches the class, needs no network, and was
verified by re-introducing the bad line and watching it fail. 85 -> 86.

The durable lesson: an offline suite cannot cover a function whose first
statement is a network call, so ordering bugs inside `build()` reach the
user by definition. Static walks over the AST are the only cheap defence
available there, and there are now two of them. A third belongs on any
future edit that touches build()'s locals.


**8/13 — bye block was never in the file, and the taxi fix did not take.**
His live run landed three of four: eleven picks with the traded 90, the
TRADED IN line, and the back-to-back note. Missing: the BYE SHAPE block,
and taxi still printed "no rookie qualifies".

The bye block was a bad `str.replace` anchor — the target line wraps
differently than I typed it, so the replacement silently matched nothing
and I shipped a file that did not contain the feature. `grep -c` said 0.
Lesson already known and violated anyway: a replace that matches nothing
is not an error, so ASSERT the anchor exists before writing. The insert
now uses a variable checked with `assert anchor in s`.

Taxi is not diagnosed. `taxi_pick` is demonstrably correct in isolation
(five selftests including the unpriced case), `marginal_values` returns
one row per candidate with no filtering, the dadp fill runs before it,
and `market["rookies"]` reports 300 with 117 priced. Every hypothesis I
formed was wrong and I could not run the live path to test another one.

So rather than guess a fourth time, `taxi_funnel()` now reports the
count surviving each stage — rows, rookies, not_taken, reachable,
under_bar, priced — and prints it in place of the old message. One live
run answers it. Two selftests pin the counts and assert the funnel and
the picker agree on whether anybody survives, so the diagnostic cannot
drift from the thing it diagnoses.

Also fixed: `t['dadp']:.0f` would crash on the unpriced rookie the new
picker can now return. Prints "UNPRICED — no dynasty market, which is
the redshirt signal" instead.

88 selftests. Reopens: the taxi cause itself, pending his next run.


**8/13 — the taxi bug was never in the taxi code. `startable_bar`
returned 0.** The funnel found it in one live run:
`rookies=300 not_taken=300 reachable=289 under_bar(=0)=0`.

`startable_bar` clamped with `min(n, len(r))`, so a position with fewer
candidates than its demand count returned the WORST player at that
position. In a superflex league where most quarterbacks are kept, only
about twenty remained against a demand of twenty-four — the twentieth
being a zero-projection rookie. `min()` then spread that 0.0 across every
position, and `taxi_pick` excludes anyone with `proj >= bar`, which every
player satisfies at zero. The pool emptied silently.

A position thinner than its demand means supply has run out and true
replacement sits BELOW the worst man available; it has no player with
which to define a bar, so it must not lower one. Skipped now, and zero is
treated as the absence of a bar rather than a bar of zero. `taxi_pick`
and `taxi_funnel` also guard independently, because that filter fails
CLOSED — a degenerate bar empties the pool instead of raising.

Worth recording plainly: I "fixed" this twice in the wrong place first,
once by removing the dynasty-price requirement and once by removing the
redraft-ADP requirement. Both were real improvements and neither was the
cause. Three theories, all wrong, all confidently argued. The funnel —
six integers, one run — beat all of them, and it exists only because I
ran out of hypotheses and admitted it rather than guessing a fourth
time. When a fix does not take, instrument; do not re-reason.

93 selftests. Reopens: `startable_bar` is used by `draft_helper` too and
the same degenerate bar may have been distorting anything downstream of
it there; nothing has audited that.


**8/13 — the sixth league landed: "LG06",
`9000000000000000022`.** Found by listing his 2026 leagues off the user
id already in hand from the draft order, rather than asking.

Shape: 10 teams, REDRAFT (settings.type 0), no keepers, no taxi, no
previous_league_id. 16 rounds, plain snake, FAAB 100, playoffs start
week 15. Draft **Wed Sep 9 2026, 5:00 PM PT**; draft_order is still
NULL, so the slot is unknown and must not be guessed. Starters are QB RB
RB WR WR TE FLEX K DL LB DB — eleven — plus five bench, which is sixteen
against sixteen rounds. Every pick is a roster spot; there is nowhere to
stash and nothing to cut into.

THE SCORING IS THE STORY, and it is extreme in both directions.

Defence: `idp_sack` 10.0 and `idp_int` 10.0, `idp_def_td` 10, `idp_ff`
and `idp_fum_rec` 5, `idp_pass_def` 2. Critically `idp_tkl` is 1.0 and
`idp_tkl_ast` is ALSO 1.0 while `idp_tkl_solo` is 0.0 — assists count
full, so combined-tackle volume is the currency and inside linebackers
on bad defences pile it up. A fifteen-sack edge rusher earns 150 points
from sacks alone, more than an elite tight end earns from every
reception he catches.

Offence: every touchdown is 10 points — pass, rush and receiving alike —
with full PPR, pass_yd 0.05, rush/rec_yd 0.1, no first-down or TE
bonuses. Turnovers are punitive: pass_int -5, pass_int_td -5, fum_lost
-5, so a fifteen-interception quarterback donates 75 points back.

Rough season archetypes under it: elite QB ~580, mid QB ~405, elite RB
~370, elite WR ~340, elite TE ~270, fifteen-sack DL ~229, volume LB
~202, coverage DB ~164, eight-sack DL ~144. One quarterback starts in a
ten-team league, so only ten are needed, but the top one is the single
largest scorer on the board by a wide margin and touchdown dependence
matters more than yardage everywhere.

Registered in keepers.json with all of the above as rules text. NOTHING
ELSE NEEDED ON THE DASHBOARD: `load_leagues(refresh=True)` discovers it
unprompted, `POS_COLORS` and `DEPTH_POS` already carry DL/LB/DB, the
position chips follow each league's own slots, and `score()` is a dot
product with no whitelist, so idp_tkl and idp_sack price themselves the
moment they appear in a stat line. The IDP work done in August against
no league is doing its job.

Which leaves exactly one open question, and it is upstream of all of it:
does Sleeper's projections feed carry idp_* stats at all? If it does
not, every defender scores zero and eleven of sixteen rounds are drafted
blind — and no downstream correctness survives an empty numerator.
`idp_probe.py` answers it in one run and prints a VERDICT line. I could
not run it myself: WebFetch needs permission for api.sleeper.com, and
this container has no route to the API.

Reopens: the slot, once the draft order publishes; whether replacement
level and the saturation logic behave sanely when DL/LB/DB each have
exactly one slot in a ten-team league; and LG04 and LG02 still
have no cards.


**8/13 — IDP projections are real, and my read on WHICH defenders matter
was wrong.** `idp_probe` verdict: 293 of 2111 rostered DL/LB/DB carry
projections, thirteen distinct idp_* keys appear in the feed, nine of
them scored by this league, and the engine prices them with no new code.
The August IDP groundwork earned its keep — nothing downstream needed
changing.

The correction is the useful part. I predicted from the scoring table
that `idp_sack` at 10 would make pass rushers the premium position.
The feed says otherwise: **eight of the top ten projected defenders in
week 1 are linebackers**, one DL, one DB. The best paces about 279
points, ahead of an elite tight end.

The arithmetic I skipped: a fifteen-sack season is 0.88 sacks a week,
roughly 8.8 points. A volume linebacker banks about nine combined
tackles every week — before a single sack, pass defensed or takeaway —
because assists count full at 1.0. Steady beats spiky when the spike is
one event a week. I read the bounty on the rare event and never divided
it by seventeen.

Same failure shape as the Kyle Pitts call: a standalone number that
looked decisive, asserted before checking it against the thing that
actually generates points. Both times the fix came from running the
tool rather than reasoning harder about the inputs.

keepers.json rules rewritten to lead with the measurement rather than
the inference, and to say plainly that a high-sack DL is the second tier
here, not the first. Reopens: the slot once draft_order publishes; and
with exactly one DL, one LB and one DB slot in a ten-team league, the
replacement bars are LB10/DL10/DB10 — worth checking that saturation and
the `startable_bar` fix behave when a position has exactly ten starters
league-wide.


**8/13 — the IDP league's first real run exposed two bugs that made the
plan worse than useless, and both had been latent since before the
league existed.**

**One: `live` was hardcoded to {"QB","RB","WR","TE"}.** That set filters
both the roster and the candidate pool, so every kicker and every
defender was deleted from the board before anything was ranked. The
consequence in a league that starts K, DL, LB and DB: a board with no
defender anywhere on it, and a sixteen-round plan that took SIX
quarterbacks for a one-QB league while leaving three starting slots
empty. Following it would have forfeited K, DL, LB and DB outright.

`live` now comes from `lineup_shape(rp)` — the league's own
roster_positions, dedicated slots plus flex eligibility. Verified the
Hybrids are unchanged at {QB,RB,WR,TE}, so this is additive rather than
a behaviour change for the leagues that already worked.

The filter was not wrong when it was written; it was written for
four-position leagues and never revisited when IDP support was added
everywhere else. The August IDP work covered vocabulary, colours, slot
aliases and the scoring engine — and then the board dropped the players
one layer above all of it.

**Two: an unpublished draft order was read as if it were real.** Sleeper
ships `slot_to_roster_id` as an IDENTITY map (slot 1 -> roster 1, slot 2
-> roster 2, ...) with `draft_order` null until the commissioner
randomises. `my_draft_picks` read a slot off that placeholder and
returned "slot 4 of 10" with a complete sixteen-pick list for a draft
whose order does not exist. Confident, precise, fiction.

`draft_order` is the field that says the order is real, so it is now
required; without it the function returns no slot and no picks, and
`report()` prints that pick numbers are a guess from `--slot`. Note the
irony: this is the same class as the slot-8-versus-6 error, one layer
deeper — I fixed "trust the published order over the user's guess" and
then trusted a placeholder that only looked published.

Both pinned: `t_league_shape_drives_positions` asserts the IDP league
yields all eight positions while the Hybrids yield four, and
`t_unpublished_draft_order_yields_no_slot` asserts an identity map with
a null order produces nothing. Fixing the second exposed that my own two
earlier fixtures had omitted `draft_order` entirely — they modelled a
published draft without saying so, and only passed because nothing
checked. test_all 26 -> 28.

Reopens: IDP players carry no ADP in any Sleeper market, so every
survival call on the DL/LB/DB board will be blind — the "GONE by your
next turn" flags cannot work for the three positions that most need
them. That is the next real problem for this league, and it is not
solved by any fix above.


**8/13 — projections disagree with the app; built proj_audit.py rather
than theorise about which is right.** He reported the league showing
different numbers than the board. `reconcile.py` was no help — despite
the name it reconciles dossier competition entries against the player
table, not projections against the app.

The pipeline, stated so the disagreement has somewhere to land:

    weekly_sum = sum(score(week_stats, league_scoring) for weeks 1..18)
    board      = weekly_sum * availability_ratio

`availability_ratios` divides the season aggregate's generic points by
the summed weekly generic points, clamps to [0.5, 1.05], and — this is
the part that matters — DEFAULTS TO 1.0 for anyone the aggregate does
not cover, which its own docstring puts at roughly the top 100 per
position.

The specific worry for the IDP league: if the aggregate does not reach
defenders, every DL, LB and DB is priced with no injury haircut at all
while every offensive player around them carries a real one. That is not
a rounding difference, it is a systematic flattering of three of eleven
starting slots, and it would be invisible in any single-player
comparison.

`proj_audit.py` prints haircut COVERAGE per position — how many
projected players the aggregate reaches, and the mean ratio actually
applied — then a per-player table of weekly sum, ratio, board value and
whether that ratio was real or defaulted. The closing note tells him
which column his screen matching implies: weekly sum means the app is
unadjusted and our haircut is the entire gap; board means we agree and
the difference is elsewhere.

Deliberately no fix yet. Which number is CORRECT is a judgement about
what the app displays, and I have neither his screen nor a route to the
API. Measuring first is cheaper than being wrong twice, which is the
lesson the taxi funnel taught two hours ago.

Reopens: the answer, once he runs it; and if defenders are indeed
unhaircut, whether the right fix is to extend the aggregate, drop the
haircut for uncovered positions, or apply a position-level mean instead
of 1.0 — the third is probably least wrong but all three are guesses
until the coverage numbers exist.


**8/13 — `lineup_value` is the wrong tool for a league with an empty
roster, and it said so far too quietly.** The IDP board came back with
twenty-five quarterbacks on top of a league that starts one.

That is not the `live` bug returning; `live` is fixed and defenders are
on the board now, just ranked below forty offensive players. It is
arithmetic. Marginal value is measured against the lineup you already
have, and with nothing to displace every candidate "fills an empty slot"
and scores his full projection. The board therefore degenerates to a raw
points ranking, and in a scoring system where every touchdown is 10 the
raw ranking is quarterbacks all the way down.

It has always carried a footnote — "with empty starting slots, most
candidates fill an empty slot and this collapses toward raw projection."
That footnote is at the bottom, hedged with "most" and "toward", and
describes a partial effect. With a COMPLETELY empty roster it is not a
tendency, it is the whole output. The Hybrids hid this because seven
keepers gave the model something to displace.

Now prints a blocking warning at the top when the roster is empty, and
names the right tool: `draft_helper.py board`, which prices against
replacement rather than against nothing. Redraft leagues are empty by
definition before the draft, so this is the default state for three of
his six leagues, not an edge case.

Also fixed the byes message. It said "missing or unreadable" and told me
nothing — it fired on the IDP league while the emoji league printed a
correct bye table from the same file in the same session, and I had no
way to tell which of the two failure modes it was. It now carries the
exception type, the message and the path it actually looked in. Verified
the local file reads 32 teams with an empty note, a bad path reports
FileNotFoundError with the path, and a wrong season reports the season
mismatch. Whatever his run hits will now say what it hit.

Reopens: why byes.json failed to load for HIM specifically, which the
new message will answer on the next run; and IDP players carry no ADP in
any market, so `board`'s survival column will be blank for DL/LB/DB even
though its VORP column is exactly what this league needs.


**8/13 — the VORP board settles the IDP question, and I had it wrong
twice.** Third answer, and this one comes with numbers from the tool
rather than from reasoning about the scoring table.

  attempt 1: "sacks are 10, so DL is premium"    -- wrong on raw points
  attempt 2: "LB dominates, DL is second tier"   -- wrong on value
  the board:  LB scores more, DL is worth more

Both earlier claims were about POINTS. Value is points over replacement,
and the two positions have completely different depth. LB is 80 deep
against 10 starting slots, a ratio of 8.0x, so replacement is LB10 = 220
and even a 270-point linebacker is only +50. DL is 20 deep against the
same 10 slots, 2.0x, replacement DL10 = 161, so a 230-point lineman is
+69. The best DL outscores nobody and is worth twenty more than the best
LB anyway.

DL is the scarcest position in the league by depth ratio — ahead of RB
at 2.5x. Draft DL early, LB and DB late.

The same lens corrects the quarterback read. Josh Allen projects 785,
the largest number on the board by two hundred and fifty points, and is
worth +106 because 32 quarterbacks remain for 10 slots and replacement
sits at 679. The biggest number is not the biggest edge. Value
concentrates at RB — Gibbs +219, Bijan +208 — and at the very top of TE,
Bowers +99.

Confirmed as predicted: every IDP player shows "-" in the ADP column.
No Sleeper market prices defenders, so survival flags cannot work for
three of eleven starting slots. That is now the known-and-stated limit
for this league rather than a surprise on draft day.

keepers.json rewritten to lead with the depth ratios and to say plainly
which tool to use. Reopens: a survival substitute for IDP — with no ADP,
the only signals available are positional scarcity and how many of the
top N at a position have already gone, which is a live-draft
calculation rather than a pre-draft one.


**8/13 — projection audit: my hypothesis was wrong, and it found
something else.** I predicted the season aggregate would not reach
defenders, leaving DL/LB/DB with a defaulted 1.0 ratio while offensive
players took a real injury haircut. Coverage is **100% for every
position** — 7652 of 9411 projected players are aggregated, and every
DL, LB and DB with a projection is among them. The default-to-1.0 path
never fires for anyone who matters.

What the coverage table shows instead:

    offence  QB .959  RB .920  WR .917  TE .907   mean 0.926  -> haircut
    IDP      DB 1.039 LB 1.041 DL 1.038            mean 1.039  -> BOOST
    K .808   DEF .777

Defenders are not merely unhaircut, they are marked UP about 4%, while
offensive players are marked DOWN about 8%. Relative inflation of IDP
against offence is roughly 12%. The ratio is season-aggregate generic
points over summed weekly generic points, clamped [0.5, 1.05], and 1.04
is inside the clamp so nothing complains. Whether that boost is real
Rotowire signal or an artefact of computing a GENERIC point total for
players whose production is entirely idp_* is not something the audit
can answer.

Impact, stated honestly: every defender moves together, so DL-versus-LB
and the whole within-IDP ranking is untouched. What shifts is IDP as a
class against RB/WR/TE. Hutchinson's +69 VORP would be roughly +61 on an
even footing. Directional, not decisive, and not worth redrafting the
strategy over — DL is still the scarcest position by depth ratio.

The ORIGINAL question is still open, because it needs one number I do
not have: Josh Allen is weekly-sum 838.3 and board 785.0. Which one his
screen shows decides whether the app is unadjusted (haircut is the
entire gap) or whether we agree and the difference lives somewhere else.
Asked for it rather than assuming.

Reopens: whether to normalise the IDP boost, and if so how — forcing
IDP to the offensive mean is one option, clamping the ratio at 1.0 is
another, and doing nothing is defensible if Rotowire's aggregate is
genuinely saying defenders outperform their weekly lines. All three are
guesses until somebody checks what the generic point formula does with
an idp_-only stat line.


**8/13 — ANSWERED: Sleeper displays the unadjusted projection; our
haircut is the entire systematic gap.** Nine quarterbacks off his
screen, compared against both stages of our pipeline:

    mean error to the app     weekly sum  -0.7%     board  -9.4%
    mean ABSOLUTE error       weekly sum   3.2%     board   9.4%

Before the availability haircut we track the app to under a percent on
average. After it we sit consistently 6-11% below. The app projects
every player as if he plays all seventeen games; ours applies the feed's
own injury discount. Neither is wrong — they answer different questions,
and the discount is real information rather than a defect.

So: NOT changing the number. Changed the LABEL. Both boards now state
the offset and its size up front, so the difference reads as a known
convention instead of a discrepancy. That is the whole fix.

Residual scatter is about 3.2% mean absolute, with Drake Maye -7.7% and
Jayden Daniels +8.0% the outliers in opposite directions. That is
consistent with cache drift — projections refetch every six hours and
the app updates continuously — and not with a systematic error, which
would not change sign.

**byes.json independently validated, 9/9.** The screenshot carries a BYE
column and every team matched: BUF 7, BAL 13, NE 11, PHI 10, WAS 7, CIN
6, DAL 14, JAX 7, SF 8. That file was hand-entered from NFL.com this
morning with no second source, so this is the first outside confirmation
it is right.

**Open, and flagged rather than fixed: ADP disagrees.** The app shows
Josh Allen at 19.1; our board says 29. `REDRAFT_ADP_KEYS` leads with
`adp_dd_ppr`, which is a generic PPR redraft market. This league is
10-team IDP, where eleven starting slots include DL, LB and DB — real
drafts there spend picks on defenders and shift every offensive player,
so neither our key nor any generic market describes this room. Combined
with defenders carrying no ADP at all, the honest instruction for this
league is to treat ADP as decoration and draft off VORP and positional
scarcity. Not guessing at a better key without knowing what the app's
number represents.


**8/13 — correction to an earlier Reopens: `startable_bar` is NOT used
by draft_helper.** When the degenerate-zero bug was fixed I logged
"startable_bar is used by draft_helper too and the same bar may have
been distorting anything downstream of it there." `grep` says otherwise:
the function is defined and used only in lineup_value. draft_helper and
dashboard never call it. That reopen is void, and a future session
should not go hunting for a bug that cannot exist.

Logged because an append-only file is trusted, and a wrong Reopens costs
somebody an hour looking for nothing. I asserted a call graph instead of
grepping one.

**The real gap in draft_helper is different and does matter:** its turn
plan calls `my_next_picks`, which I fixed for the round reversal but
which still does not read traded picks. Its own docstring says so. He
holds ELEVEN picks in each Hybrid and the live board will tell him ten,
including on 8/18 while two drafts run at once — and CLAUDE.md's own
rule is to reread the live board every pick rather than trust the card.

**Draft calendar, pulled rather than assumed:** Hybrids 8/18 9:00 AM,
**LG02 Sat 9/5 4:00 PM**, LG04 9/6, IDP Wed 9/9 5:00 PM. LG02 drafts BEFORE LG04, which reverses the order I suggested an hour
ago off memory.

**8/13 — Every pick count in the toolkit reads real ownership.** Four
places counted picks by walking a seat, which is one pick per round by
construction. He owns eleven in each Hybrid against ten seats, so all
four were wrong in the same direction: `draft_helper.board`'s turn plan,
`roster_snapshot`'s "picks remaining", the live `watch` alarm, and
`lineup_value` (already fixed). All now route through
`sleeper_client.my_draft_picks`, which reads `/draft/<id>/traded_picks`.
`draft_helper.my_roster_id(league_id)` was added because ownership is
recorded against a roster, not a user, and nothing else resolved it.
Each falls back to the seat walk when the draft order is unpublished —
a seat beats nothing — but now SAYS which one it used. Reopens: never;
this is arithmetic against a documented endpoint.

**8/13 — Provenance is part of the output, not a debug aid.** The
picks-remaining line now prints where its number came from: real
ownership, a seat walk, or a 1/round estimate. The number alone was
right in the estimate case and wrong in the seat case and looked
identical either way. This follows the pattern named in ROADMAP.md —
six of the last eight defects were true numbers under false labels, and
every one was caught by him rather than by a test. Reopens: if the line
gets noisy enough that he stops reading it.

**8/13 — String-anchor patching of rendered output is banned.** The
1/round note was bolted onto `roster_snapshot`'s block afterwards with
`blk.replace("- picks remaining", ...)`. When an anchor like that moves,
the text vanishes and nothing fails — which is exactly how the bye block
disappeared earlier the same day. It is a `picks_note` parameter now,
and a selftest greps the source to keep it that way. The first version
of that guard failed against its own source line, so the needle is
assembled at runtime. Reopens: never.

**8/13 — An open taxi seat is a committed pick, not a spare one.** The
picks-remaining line compared the raw pick count against open ACTIVE
slots. A taxi seat cannot be filled mid-season, so those picks are spoken
for before the draft opens — both Hybrid cards already earmark two. The
emoji Hybrid therefore read "11 picks for 11 open ACTIVE slots — exactly
filling out" when nine picks were actually available and he finishes two
bodies short; LG01 read "more picks than slots; some will be
cuts" when the whole surplus was its three open taxi seats. The line is
now scored on picks-minus-open-taxi and says so on its own row. Reopens:
if he decides to leave taxi seats empty, which the rules make costly.

**8/13 — The all-clear answers to gaps AND thin starters.** "All starting
slots covered" hung off `thin_seen` alone, so a roster with real gaps and
no thin starters printed every unfilled slot and then the all-clear
directly beneath them. Three leagues did it in one run. Reopens: never;
a dangling else.

**8/13 — Room-by-position reads the league's slots, not a literal.** The
list was hardcoded through DEF, so the IDP league's DL, LB and DB — three
of its eleven starting slots — never appeared in the section that reports
what you hold. Same defect as `lineup_value`'s hardcoded `live` set,
which recommended six quarterbacks for a one-QB league. Second occurrence
in two days; the rule is that no position list is ever written as a
literal. Reopens: never.

**8/13 — All three above were found by reading live output, not by a
test.** The suite was 30/30 green across the two fixes it was written
for, and the run against real leagues surfaced three more — one of which
(taxi) changes a Tuesday number. This is the seventh, eighth and ninth
instance of the pattern ROADMAP.md names: true arithmetic under a false
sentence. Ship-and-read beats ship-and-trust.

**8/13 — SUPERSEDES the taxi entry from earlier today. An open taxi seat
is an option, not a committed pick.** I had just made `roster_snapshot`
subtract open seats from the pick count, on the belief that a seat left
empty could not be filled later. Wrong on three counts, corrected by the
user within the hour: seats must be filled by the start of the season or
they simply stay empty, an empty seat costs nothing, and a seat can be
filled from EITHER draft. The subtraction understated available picks by
exactly the number of open seats. Reverted to the raw count; the seats
now get a line saying they compete for the same picks without claiming
them. Reopens: if the commissioner ever makes seats mandatory.

**8/13 — Taxi eligibility is narrower than anything on file said.** Only
a rookie YOU DRAFTED THIS YEAR may occupy a seat. Not a free agent, not a
trade, not last year's rookie. So a seat can only ever be bought with one
of your own picks. Nothing in `keepers.json` or either card said this.
Reopens: never; it is a league rule.

**8/13 — The taxi advice was backwards, and it was mine.** Both cards and
`roster_snapshot` said to spend the last picks of draft 1 on redshirts
and called that "the correct use of those picks." A rookie still on the
board in round 9 of a 10-round draft is by definition one the room does
not rate — precisely the player not worth a free keeper next year. The
user's own precedent is the counterexample: he stashed Jayden Daniels,
a rookie good enough to start, paid one season of production, and now
owns him outside the 3+2 keeper budget. The real rule is a sequencing
one: a rookie who will last until draft 2 should be taken there, since
those picks are near-free; a first-draft pick is justified only for one
who will not last. Reopens: never.

**8/13 — Draft 2 makes draft 1 a pure value auction.** Its length is set
by the team with the greatest need; every team drafts that many rounds,
and teams needing fewer bodies get commissioner-inserted retired or
zero-value players which they immediately drop, so all rosters end level.
Practical effect: draft 1 carries NO obligation to fill roster slots.
Positional need should carry very little weight in it, which puts
`lineup_value`'s marginal-value model — scored against holes in your
lineup — at odds with what draft 1 actually rewards. `draft_helper.board`
VORP is the closer model. NOT yet acted on: both need to be run against
the same eleven picks and compared before any card changes. Reopens: on
that comparison.

**8/13 — data/ shadows the repo root, and the root copy is a decoy.**
`paths.data()` prefers `data/<name>` and falls back to the repo root. Both
copies of `keepers.json` existed. Every edit I made today went to the root
copy, which nothing reads: the corrected taxi rule, and — going back
further — the registration of the ENTIRE IDP league. That is why the IDP
league has never printed a keeper-rules line in `roster.md`, a silence I
read as "no rules configured" rather than "wrong file." Two full runs
showed the superseded 8/11 taxi text with no sign anything was wrong.
`paths.data()` now prints a WARNING naming the dead file whenever both
exist. Reopens: never — the fix is to delete the shadow, and the warning
says which one.

**8/13 — The IDP league's rules were never actually registered.** Carried
across into `data/keepers.json` with the rest. Anything earlier in this
project that claims the IDP league is registered in `keepers.json` was
true of the wrong file.

**8/13 — LG01 does NOT inherit the Hybrid taxi corrections.** Its
rules text carried a copy of the 8/11 Hybrid paragraph. Rather than apply
the 8/13 corrections there, its block now says explicitly that they were
confirmed for the Hybrids only, names two reasons they are unlikely to
carry (full dynasty means no keeper budget for a taxi seat to dodge, and
there is no second draft to defer a rookie into), and says to confirm
with the commissioner. Reopens: on that confirmation.

**8/13 — Deleting the dead keepers.json broke `lineup_value`, and I told
him to delete it.** The migration to `data/` was partial. `dashboard`,
`keeper`, `draft_review` and `dynasty_value` had been converted to
`paths.data()`; `lineup_value` had not, and read `HERE / "keepers.json"`
in three places. All three sit inside bare excepts, so removing the root
copy produced no error — it produced defaults. The worst was
`board()`'s `keeper` flag going False for both Hybrids, which selects the
DYNASTY ADP market instead of REDRAFT and moves every survival flag on
Tuesday's card. `room_shave` and `keeper_rules` were returning 0 and {}.
All three now go through `paths.data()`, and the `keeper` read prints a
WARNING naming the consequence instead of failing quietly. Reopens: never.

**8/13 — `byes.json` was never being read at all.** `sleeper_client.
load_byes` built its path from the module directory. Only `data/byes.json`
exists, so every bye lookup fell into the empty dict. The bye work done
earlier the same day — the file, the 32-team validation, `bye_pressure` —
has never once run against real data on his machine. Repointed at
`paths.data()`.

**8/13 — Authored JSON is read as UTF-8, explicitly, everywhere.** A bare
`read_text()` uses the locale codepage; on his Windows box that is cp1252,
so the moment `keepers.json` was written as UTF-8 every em dash came back
as mojibake in `roster.md`. 22 reads across 12 files fixed. Writes were
already safe — `json.dumps` defaults to `ensure_ascii=True`, so the bytes
are pure ASCII whatever the codec.

**8/13 — One AST guard now covers both.** `t_authored_data_is_read_from_
data_dir_as_utf8` walks every module for a read with no encoding and for
any path built as `<dir> / "keepers.json"` (or ages/byes/fonts). It found
the `byes.json` bug on its first run, which is the only defect all week a
test caught before a human did. Written with AST rather than grep because
the grep version matched its own docstring — the second time today a
source-scanning guard failed against itself.

**8/13 — The two value models disagreed at pick 8, and both were wrong in
different ways.** `lineup_value` said Dak Prescott (+361); the VORP board
ranked him eleventh (+42). Diagnosed, and both fixed rather than picking
a winner.

**8/13 — `draft_helper.board` was pricing both Hybrids off the DYNASTY
market.** It derived `keeper` from `settings.type == 1`. Sleeper types
both Hybrids as 2 (dynasty), and the thing that makes them redraft-priced
— they churn everyone but seven — lives only in `keepers.json`'s manual
`keeper` flag, which `lineup_value` has always read and the board never
did. Derrick Henry priced at dADP 83 in a market that actually drafts him
at 46. The board now reads the same flag and prints which market it used.
Reopens: never.

**8/13 — The board never applied keeper depletion either.** ~65-73 players
per Hybrid are rostered and never reach the draft, so every market ADP is
dozens of picks late. The board told him Drake London "waits past pick 17"
when London's depleted price is 5, and said the same of Pickens (12, shown
as 32) and A.J. Brown (8, shown as 60). Every survival flag in both rooms
was wrong. Now runs `lineup_value.deplete_adp` over the same kept set and
says so in the header. Reopens: never.

**8/13 — `lineup_value` now measures against a REPLACEMENT FLOOR, not
against the roster as it stands.** This is the deeper of the two. Marginal
value answers "what does he add to my lineup?" correctly, but that is the
wrong question in a draft: declining a player does not leave the slot as
it is, you fill it with a later pick — and in these leagues with an entire
second draft. So a corpse in a starting slot made any real player look
like a franchise pick. `floored_roster()` upgrades every below-replacement
starter and fills every empty slot at replacement before measuring. Value
now converges on VORP where a slot is empty or dead, and keeps genuine
displacement value where the incumbent is actually good. Reopens: if the
second draft turns out too thin to backfill a startable body, in which
case the floor is too high — that is the one number worth measuring after
Tuesday.

**8/13 — A selftest was wrong, not the code.** The first floor test
asserted "value against the floor is less than half value against the
corpse" and failed at 212 vs 408 with replacement 196 — arithmetically
perfect. Replaced with the actual claim: the floor removes one
replacement player's worth of credit, +/- 15%. Assert the quantity you
mean, not a vague inequality near it.

**8/13 — The replacement floor shipped broken and the run proved it.**
`lineup_value.replacement_level` reimplemented the formula instead of
calling the board's, and got remaining demand wrong: it scored TOTAL
league demand against the ALREADY-DEPLETED candidate pool, counting the
kept players twice. On a shallow position the index walks off the end and
lands on the worst player in the league, so QB replacement in the
no-emoji Hybrid came out near one point. Jalen Milroe, the corpse the
whole fix existed to neutralise, was therefore NOT below replacement, was
not floored, and Dak Prescott came back at +359 — identical to before the
fix, under a header announcing that 3 slots had been floored.

It survived its own selftest because that test used a deep synthetic
pool. It was caught only because the EMOJI Hybrid — same code, same run —
has two real quarterbacks and behaved correctly, so the twins disagreed.

`draft_helper.replacement_levels()` is now the one implementation and
`lineup_value` delegates. Two tests: one reproduces the shallow-pool
shape with kept demand subtracted, one walks the AST to assert
`lineup_value` still delegates rather than growing a third copy. This is
the same lesson as the pick geometry in August — three copies is how all
three ended up wrong — and I repeated it inside a fix for a different
instance of it. Reopens: never.

**8/13 — A header that announces a fix is not evidence the fix ran.**
"3 starting slot(s) were floored" printed truthfully while the slot that
mattered was untouched, because the count included empty-slot fills that
did nothing for the QB problem. The number was true and the impression it
gave was false — the defect class ROADMAP.md names, now committed by the
message I wrote to guard against it. Any future banner of this kind should
report the SPECIFIC thing changed, not a count.

**8/13 — MEASURED: draft 2 cannot fill a starting slot. My own assumption,
refuted by my own probe.** `draft2_probe.py` strips the keepers, strips
the top 120 by depleted ADP, and reports what is left. Both Hybrids come
back SHORT at every offensive position, by margins far beyond method
error:

    no-emoji   QB 320/262 (-58)  RB 266/90 (-176)  WR 228/126 (-103)  TE 225/113 (-112)
    emoji      QB 322/189 (-133) RB 253/90 (-163)  WR 230/115 (-115)  TE 219/113 (-106)

Only 28 running backs in the no-emoji pool project 120+, and all 28 go
inside draft 1's 120 picks. Draft 2 is waiver quality.

Both cards had been rebuilt hours earlier around the opposite claim —
"draft 1 carries no obligation to fill roster slots" — which I had flagged
twice as unverified and shipped anyway. Removed from both. The replacement
floor in `lineup_value` is therefore too HIGH: a hole-filler is worth more
than it says. Reopens: rerun the probe with `room_bias.py`'s measured
shave after Tuesday, since the ordering assumes the room drafts to market.

**8/13 — DECIDED: the VORP board is the draft ranking, `lineup_value` is
not.** After two failed attempts to make the marginal model rank a draft
correctly, the honest read is that it is the wrong tool for the job.
With most slots floored it measures every candidate against the single
weakest body in the lineup rather than against his own position, so it
ranks by raw projection: Chase Brown (RB 316) over George Pickens (WR
302), while the board has Pickens ahead — correctly, since replacement RB
is 266 and replacement WR 228. `lineup_value` keeps two jobs it is
genuinely good at: depleted ADP for survival and sequencing, and
in-season lineup calls where the roster is full. Both cards now say this
in a section of their own. Reopens: if someone rewrites the marginal
model to price each candidate against his OWN position's replacement,
which is a real fix and not one to attempt five days out.

**8/13 — Late-round tight-end stacking is a floor artifact.** The
no-emoji plan takes three tight ends behind a 294-point starter, because
a second TE reads "fills an empty slot" at a 36% start share. Cards now
say picks 53-95 are for running backs and receivers. Same root cause as
above; same reason it is documented rather than coded around today.

**9/7 — FOUND, NOT FIXED: LG04's recap is graded on the wrong horizon,
and one boolean is standing in for three regimes.** `keepers.json` carries
`keeper: true` for LG04, so `recap` runs `horizon_for(keeper=True)` and
prices all 15 picks as a discounted 2-season surplus with age curves. That
horizon was fitted to the Hybrids — `horizon_for`'s own docstring says "a
3-keeper league carries 7 players; the rest churns." LG04 carries ONE,
at the cost of the round he was drafted, and not until 2027. Full dynasty,
a 3+2+taxi Hybrid, and a one-round-cost keeper are three different
regimes; `keeper` is a boolean and can only name two.

Same shape as the 8/11 `room_shave` error — a parameter measured on one
room generalised onto rooms it does not describe.

[Likely] this is why Derrick Henry prices 0.0 at LG04 pick 15 while the
same player is 97.9 in LG02: age 32 on a 2-year curve falls under the
RB bar in both seasons, so both contribute zero. Rerunning LG04 with
`keeper` false would settle it; not run, the shell reaching this folder
has no route to the Sleeper API.

It contradicts a standing instruction. John's rule for LG04 is draft to
win 2026, keeper value as a TIEBREAKER not a driver. The recap made it the
driver.

**9/7 — Second LG04 defect: six phantom keepers in a startup.**
`keepers.json` says in plain English that LG04 is a 2026 startup and
nobody keeps anyone. There is no `previous_league_id`, so `recap` falls to
`kept = undrafted` and counted a day of waiver adds as keepers — six of
them, which then deplete the board and shift every ADP earlier. The
correct kept set is empty and the file already knows it. The fallback
should read the startup fact rather than infer from roster minus draft.

Small in magnitude — at most six picks of ADP shift — but it moves the
market column, which is the column that otherwise survives defect one.

**9/7 — WHAT SURVIVES, so the LG04 recap is not discarded whole.** The
value and board columns are unusable and so is "took the best player on
the board: 2 of 15" and "worst selection: Derrick Henry." The MARKET
column does not depend on the horizon at all and is distorted only by the
six-keeper shift, so "biggest reach: Alec Pierce, 55 picks early" and
"best price: Harold Fannin, 28 picks of value" both stand.

The finding that survives both defects: LG04 ran -72 against the market
across 8 priced picks where LG02 ran -8, one day apart. That gap is
real and is not explained by either defect.

Reopens: what is a single round-cost keeper worth in seasons? That is a
modelling decision for John, not a patch. Until it is answered, `keeper`
should be a horizon per league rather than a flag. Both defects are for
after the 9/9 IDP draft; LG06 is redraft-IDP with no keepers.json
entry, grades on this season only, and is unaffected.

**9/7 — FIXED: the IDP pool was missing 503 defenders, and SLOT_ALIAS had
been applied to one side of the comparison since it was written.** Sleeper
carries `position` (the real NFL position -- Myles Garrett is DE) and
`fantasy_positions` (what he is eligible for -- ['DL']). `board_data` and
`player_hits` filtered on `position` against roster slots already aliased,
so DE, DT, CB, SS, NT, ILB, FS, S and OLB matched nothing.

Measured on the live table before touching anything: CB 178, DT 164, DE
147 and 14 others dropped -- 503 of 1,281 defenders, and 314 of 458
linemen. `find` said 'no player matching' for six household-name pass
rushers. The LG06 card was built on "ten linemen above replacement
for ten teams," computed on 61 of 162 available linemen.

Found two days before that draft, by chasing a disagreement between the
board's DL list and an external consensus board. The disagreement was the
signal; neither list was wrong about the players it held.

WHAT THE FIX IS. `norm_pos(meta, rostered)` -- match on `position` first
(so nothing that worked moves), then `fantasy_positions` restricted to
IDP_POS, then SLOT_ALIAS. One player, one bucket. The pool carries a COPY
with the corrected position so the shared player table is never mutated.

WHAT THE MEASUREMENT CHANGED. The first version left `fantasy_positions`
unrestricted, which also admitted fullbacks (position FB, eligible ['RB'])
and moved a settled league's RB pool from 125 to 129. The docstring at the
time claimed the five non-IDP leagues "cannot change at all". It was
wrong, and only the probe caught it. Restricting the branch to IDP_POS
makes the containment claim true instead of asserted.

DUAL ELIGIBILITY, asked by John before this shipped. Thirteen of the 101
new linemen are ['DL','LB'] edge rushers -- Hunter 202.8, Burns 200.9,
Hines-Allen, Greenard. All thirteen land in DL, none in LB or DB, and zero
players reach two buckets. Sleeper's own ordering decides the bucket, not
ours.

TWO SAME-NAME PAIRS, both genuinely two different men, neither a
double-count: Justin Jefferson (WR MIN 259.0 / LB CLE 63.6) and Byron
Murphy (DL SEA 150.9 / CB MIN 133.0, the latter newly visible because of
this fix). ext_tiers keys on (name, position) and strips suffixes, so
"Byron Murphy II" on the DL consensus board joins the Seattle lineman and
not the Minnesota corner. Checked, not assumed.

OPEN, deliberately: (1) should a fullback eligible at RB be in the RB
pool? Probably yes; not decided on the eve of a draft. (2) is DL the right
home for a dual-eligible edge rusher in a league that starts DL1/LB1/DB1,
or should the bucket follow scarcity? DL is convention and is where the
edge is; revisit with the eval.


**9/8 — MEASURED: nine scoring rules this league pays were worth ZERO on every
board, and fixing that reversed the draft plan.** LG06 scores nine
per-GAME thresholds -- 100/200 receiving and rushing yards, 300/400 passing, a
10-tackle game, a 2-sack game, 3 passes defensed. Sleeper's projection feed
never projects them, because a season total cannot say how often a player
crossed a per-game line. So `score()` was right, the feed was incomplete, and
every downstream number was computed as though the rules did not exist.

Found by decomposing Jack Campbell: 209 projected tackles at 11.6 a game, in a
league that pays 5 for a ten-tackle game, with no bonus line anywhere in the
output. A rule the league SCORES and the feed does NOT project appears in
neither `explain`'s scored list nor its unscored list. It is invisible by
construction.

HOW THEY WERE PRICED. Not modelled -- counted. `out/fz/bonus_adjust.py` pulls
each player's real 2025 week-by-week lines and counts how many games cleared
each threshold, at this league's own rates. Cook +95, JSN +90, Henry +85,
Campbell +45, Hutchinson +15.

REPLACEMENT IS RECOMPUTED, and that is the half that matters. Adding an
absolute bonus onto a relative VORP overstates everyone, because the
replacement-level man earns bonuses too. The bonus goes onto `proj` and the
bars are rebuilt: RB +11.0, WR +12.2, QB +26.4, LB +28.3, DB +8.8, TE +1.9,
DL and K +0.0. DL not moving is not a bug -- two-sack games are rare and the
tenth-best lineman had none in 2025, which is why the whole bonus flows to
VORP at the top of DL while LB's gains are eaten by its own bar.

THIS REVERSED A CALL I MADE THE SAME DAY. Before recomputing the bars I told
John that Campbell (+45) clearly beat Hutchinson (+15) and that the R6/R7
order should flip. With the bars rebuilt they land ~67 and ~65 -- inside
noise, and the flip was withdrawn. Absolute-onto-relative is the error; it is
worth a couple of hundred points spread across a board.

**9/8 — THE TIGHT-END FLIP AT SLOTS 8-10 WAS AN ARTIFACT, and a control run
proves it was the bonuses.** The 9/3 plan opened RB RB TE WR WR from a late
seat, recorded as worth 8/25/35 points at slots 8/9/10. `bakeoff.py` never
contained a TE strategy, so every run had compared the front-of-room plan
against itself and left the late-seat plan untested; the TE openers were added
9/8 and all ten slots reported.

Three boards, same rooms, same code:

    pre-bonus     TE beats three backs by  +5 / +17 / +22  at slots 8/9/10
    bonus count   three backs beat TE by  +22 / +22 / +14
    bonus rate    three backs beat TE by  +10 /  +8 /  +8

The pre-bonus run reproduces 9/3's own measurement (+4/+21/+33 against
RB RB WR WR, recorded then as 8/25/35), so the old plan was right about its
own board. The only thing that changed is nine rules. Backs stack 100-yard
games; the marginal RB3 gains far more from them than the first TE does.

SETTLED, on all three boards: slots 1-7 open RB RB WR WR. Slots 9-10 open
RB RB RB WR WR. IDP early loses 27, 49 and 50 points -- three boards, one
answer, do not take a defender before round 6. zero-RB loses 73 to 117.

NOT SETTLED: slot 8. RB2 wins it by +3 on the rate board and loses it by 14 on
the count board -- a 17-point swing that depends only on how the durability
bias is treated. Take the better player there; the model has no opinion worth
overriding the board with.

THE DURABILITY BIAS, tested both ways. Counting games under-credits anyone who
missed time (Drake London cleared five thresholds in TWELVE games). `--rate`
divides by games played and rescales by the board's own availability ratio.
London +12, Lamb +6.5, and correctly NEGATIVE for a 17-game player whose ratio
is below 1. It swapped the error rather than removing it -- rating assumes the
games come back -- but the top six are the same six backs in the same order
under both, so the openers do not depend on the choice. Plans were built on
`--rate` as the more conservative of the two.

**9/8 — the live server and the pre-draft plan no longer disagree.**
`br.py live` runs `draft_helper` VORP, which has none of this. On 9/8 it
recommended Colston Loveland at TE in round 3 from seat 9 at 68%, while the
card said take a third back -- two tools, one question, opposite answers, on a
60-second clock. The class this repo has now shipped four times.

`draft_live._bonus_overlay()` adds `bonus_2025` to `proj` when
`out/fz/board_adj_rate.json` exists. Onto proj, not vorp, so `reprice()`
rebuilds the bars on every poll exactly as the offline board does. Verified
live: 325 of 948 players carried a bonus, Cook moved 6th to 3rd, McCaffrey 3rd
to 6th, JSN 18th to 11th, and R3 at seat 9 went from Loveland 68% to Breece
Hall 32% with Loveland second. Guarded by the file's existence, so the six
drafted leagues are untouched. Delete the file to revert.

**9/8 — OPEN: three replacement-level formulas.** `draft_helper` and
`draft_live` share one and a test enforces it. `out/fz/fzboard.py` has a third,
rank-based with a FLEX share. They agree on RB (284.6 v 296.5), WR (243.8 v
250.4) and DL (169.6 v 169.0) and diverge at QB (585.8 v 691.8), TE (173.3 v
191.4) and K (209.7 v 223.2). No ordering changes and no decision turns on it,
so it is logged rather than fixed four days out. It belongs in the eval.

**9/8 — also confirmed:** the external tier board is out of `data/tiers/`, so
survival prices off `adp_idp_1qb` -- this room's own market -- and the ECR
column reads empty by design. Measured 9/7 against that market, the half-PPR
consensus ran +6.7 picks late on backs and -5.9 early on receivers, and priced
Josh Allen at 28 where this room says 16.

**9/11 — DECIDED: the in-season tools are built INSIDE the 9/4 eval, not
instead of it.** All seven drafts are done and John asked for the trade,
lineup and waiver tools. The 9/4 rule says no new features for four weeks.
The reconciliation, agreed: every recommendation the toolkit makes is
written to a ledger with the projection it was priced on, and scored the
following Tuesday against what actually happened under that league's own
scoring. The tools get built; recommend-record-score is the contract from
the first run. First target is waivers (the cadence that repeats first;
both Hybrids carry 1,000 FAAB unspent). Output lands in the MCP tools and
the dashboard tabs; the Tuesday scheduled brief is unchanged for now.

WHAT SHIPPED. `battle_rhythm/ledger.py` (new): recs.jsonl is append-only
and keyed on sha1(kind, league, season, week, subject pids, over pids), so
a brief run three times on a Tuesday records each rec once, as of its
first run. `ledger score` pulls actual stats through backtest_probe's
cached fetch, rescores under the league, and rewrites outcomes.jsonl
whole. The report buckets win rate by projected edge beside the
calibration prior from backtest.py — same buckets, so the two tables read
side by side. Below the prior means the rescoring is worse than the raw
feed; above it means the league-specific engine is doing work.
`data/ledger/` is Truth tier and tracked (paths.ledger()).

Waivers v2 in weekly.py, each item a defect John caught by hand first:

- RESERVE IS NOT BENCH. `reserve` and `taxi` off my roster row are
  excluded from starters, from the tier-2 bar and from every drop. Conner
  was the named drop in every LG04 claim (9/7) because bench was
  `mine - starters`.
- DEPTH CHART READ, no new data source. The player table already carries
  depth_chart_position/order. Every waiver row prints the slot (RB3, LWR1)
  and a ROLE? flag when order is at or past QB2 / TE2 / RB3 / any-WR-slot-2.
  Tracy (+78.9 over Saylors) and MarShawn Lloyd (ECR 88, VORP 158) are both
  this flag. Handcuffs are named: an RB2 whose RB1 is on MY roster.
- FAAB BIDS ARE SIZED by a stated formula (spendable slice x this add's
  share of this week's tier-1 value, hold-back decaying to zero by week
  17). It is a prior, not a measurement; the ledger records the bid and
  the transactions feed records what won, which is how it gets corrected.
  Winning bids so far in the league are printed as comps when history
  exists (it does not, yet, in the four 2026 startups).
- ORDER LEAGUES show waiver_position off the roster row. WAIVER_MODE
  labels for type 0 and 1 are NOT verified against a league page; the
  position is real, the label may not be.

NOT DONE, deliberately: the return-yardage / P(starts) rule from 9/7 §3
(a value source that pays only from the starting lineup) — needs a
projection component the feed does not carry; trades stay 1-for-1 against
a static market; lineup moves get bye/injury handling in the next pass.
Three tests pinned against the old code (reserve drop, depth flag +
handcuff, FAAB bid), plus a weekly→ledger→outcome join test and the
ledger selftest inside test_all. Suite: 57. `t_weekly_trades_both_sides`
changed on purpose — trade pids are no longer popped, the ledger keys on
them.

Reopens: the bid formula's 0.5 hold-back and 17-week horizon are guesses
until the ledger has a season of claims; the DEPTH_STALE thresholds are
one-room observations (two backs) generalised, which is exactly the
lesson-6 error if they turn out wrong — measure the flag's hit rate in the
ledger before trusting it.

**9/12 — CORRECTED after the first live run: the ROLE? flag no longer
fires on receivers.** `br.py waivers lg04` flagged six of eight rows,
including Keenan Allen (RWR3) and Rashod Bateman (LWR2). Sleeper's
receiver chart stacks several players under each of LWR/RWR/SWR, so slot
order 2 is not WR4. The 9/11 entry's own "reopens" line named this risk
(thresholds generalised from two backs); it was real within one run.
DEPTH_STALE is QB/RB/TE only; the receiver slot still prints. Also seen
live: the entire LG04 tier-2 list is "+27 to +46 over Dike", every
one understated by ~90 points of return yardage the feed does not carry
(9/7 §3) — those rows are probably all negative. That gap is now the
next in-season fix, ahead of trades.

**9/12 — FIXED before the first `ledger score`: waivers and trades count
from the week after the recommendation.** A week-1 claim processes
Tuesday night and plays in week 2; scoring it on week 1 credits a game
the manager could not have used. `score` now starts non-lineup recs at
rec.week + 1 and skips any whose N+1 has not played. Lineup calls still
score on their own week. `ledger prune --league <id>` added for the
duplicate-LG06 records (see HANDOFF 9/12) — the API returned
eight leagues, two of them the same room. Selftest 16 -> 18.

**9/12 — the 🪓 LG06 is a commissioner copy, registered as
`lg08` with `ignore: true`.** John confirmed the plain-named
league (9000000000000000022) is the real room; the lg08 one
(9000000000000000025) has an id newer than the real room's draft, FAAB
1000 against the real 100, and an identical roster. He has asked the
commissioner whether it stays. `paths.ignored_ids()` is new; weekly and
the dashboard skip ignored leagues, smoke still counts them as known.
Its week-1 recs were pruned from the ledger. If it becomes a real second
room, flip the flag and give it its own folder.

**9/12 — FIXED the same hour it shipped: lineup swaps paired by rank.**
`print_lineup` is new (the terminal brief never showed the
actual-vs-optimal swaps; only the dashboard did). Its first live run
printed, for LG03, "start Jayden Reed (WR) over Jayden
Daniels (QB) +-7.2 (75% an edge this size wins)". The optimiser
wanted Reed in for a ruled-out A.J. Brown (0.0) and Geno at SUPER_FLEX
over Daniels; zip() paired the sit and
start lists by rank across positions. The 15.3 total was right and every
line under it was wrong -- the true-number/false-label class, fourth
shipment. Pairs are same-position first now, odds only where the printed
gain is positive, sign printed honestly. Suite 58.

**9/12 — FIXED, John's catch: a player whose game has started is locked,
and the model did not know games start.** The lineup brief said bench
A.J. Brown for Jayden Reed. Brown had been hurt on Thursday night; Sleeper
had locked him the moment the game kicked off. The advice was impossible
and the ledger had recorded it, which would have booked a loss against a
move nobody could make. `locked_teams()` now reads the CURRENT week's
stats feed -- Sleeper writes a line only once a game is under way, so any
team with a line has started -- fetched fresh, never cached as history.
Locked players are excluded from both sides of the diff, the gap counts
only movable swaps, and no rec is written for them. `ledger list` prints
ids; `ledger prune --rec <id>` removes the Brown rec. Pinned by
`t_locked_players_are_not_lineup_advice`. Suite 59.

The general form: every in-season recommendation needs an "is this move
still possible" gate before it is printed or recorded. Lineup has one now.
Waivers have a version of it (claims process on a schedule); trades do
not (a player in a game cannot be traded either). Add the gate to trades
when they are built, not after the first impossible proposal.

**9/26 — MEASURED: the engine scores what Sleeper scored, 3,103 of 3,103.**
The question was whether the ledger's "actual" was real. It was not
Sleeper's number: `ledger score` rescores the stats feed with our own dot
product, so a wrong rule would have been wrong on both sides of every
outcome and invisible. `verify_scoring()` did check against Sleeper's
`players_points`, but one roster, one week. New `br.py truth`: `fetch`
(the PC only -- VM and cloud are still denied CONNECT) writes stats plus
every league's settings, matchups and positions under ONE timestamp to
data/truth/ (tracked: a stat correction rewrites the as-of state);
`compare` runs offline and writes one row per league x week x rostered
player to out/truth/player_weeks.csv. Weeks 1-2, all seven leagues:
3,103 rows, 2,579 non-zero, every one exact to the cent, zero rounding
gaps, zero custom_points. It covers what was most likely to break:
LG04 return yards (30 player-weeks with kr/pr points) and distance
kicking, LG06 attempt scoring and IDP, team DEF, K, and the
Hybrid reception buckets and first downs. One QB-week scored 29.78 to
81.55 across the seven leagues, all seven exact. So the ledger's
rescoring stands, and it is now evidence rather than assumption --
including for free agents, who are not in matchups and still rest on the
engine alone. Keys a league pays that NO line carried in both weeks
(def_st_td, st_td, fum_rec_td, fgm_0_19; LG06 idp_safe and the
200-yard bonuses) are rare events or feed gaps; the weekly run will tell
which. Named `truth`, not `diff`: `scoring_diff` compares league RULES
and that name clash cost the 9/26 conversation its first ten minutes.
Pinned by `t_truth_selftest_clean` (the two hand-scored LG03-LG05 wk2
lines, 36.8 and 16.8). Suite 60.

**9/26 — WIRED: the truth check runs every Tuesday.** Split by the same
network line as everything else. Windows Task Scheduler on the PC runs
`br.py truth fetch --last` at 6:30 AM local (DST-proof, unlike the UTC
cron): the latest week Sleeper has scored, read off the leagues'
`settings.last_scored_leg` rather than /state/nfl, plus the week before
it again. The 7:00 research refresh runs `truth compare --recent` offline
in the VM (new Step 5B), leads its report with the TRUTH headline, and
pushes on any miss or a missing morning snapshot. A week with two
snapshots now lists every player whose Sleeper points moved between them
-- the stat-correction log the re-fetch exists for. Every fetch appends
to out/truth/fetch.log, so an unattended run leaves a trace. The refresh
never edits the engine: a miss is a diagnosis for John.

**9/26 — BUILT REMOTELY, installed later: history backfill, release gate, CI, dbt.**
Built while John was away from the workstation and installed in one push.
`truth fetch --history` snapshots every scored week of each league's
previous season (both Hybrids have a 2025 on Sleeper; their 2025 scoring
settings match 2026 key for key, checked 9/26), and every compare now
prints RULE COVERAGE: which paid rules have been proven on an exact row and
which have never come up. `player_weeks.csv` became the whole fact table
across seasons. `br.py release` is the public-repo gate the 9/4 plan
required: `scan-key` searches all history for the push key (read with
getpass, never stored or printed). John, 9/26: his private leagues must not
be published, his friends' names must be safeguarded, and he wants a
surrogate key to cite in public. So every league becomes LGnn (numbered by
id, past seasons share it, keys never renumber) and every manager MGRnn,
pulled from Sleeper's own users lists rather than typed from memory; names,
slugs, aliases, filenames and folder names are all rewritten, generic
format words (dynasty, hybrid, idp) are left alone, and the mapping in
data/release/ is never exported. `export` writes LEAGUES.md (key and
format only); `verify` proves nothing private survived. The public repo is a fresh history from `export`, never
this one made public. `.github/workflows/tests.yml` runs the offline suite
and selftests on Ubuntu 3.10 and Windows 3.12 plus a gitleaks scan of the
full history. `analytics/` is the dbt-duckdb model of the fact table (built
and tested on sample data; first real build at install). docs/ENGINE_CHECK.md
is the write-up.

**9/26 — CORRECTION to the 3,103-of-3,103 entry above.** It says the check
covered LG04's "distance kicking". It did not: LG04 has no K slot, so
no LG04 row ever carried fgm_yds, and the first rule coverage table
(same evening) lists it as never exercised. What the entry got right is
return yards (30 player-weeks). The coverage table also shows the Hybrids
and Best Ball paying DEF and K rules with no DEF or K slot -- rules that can
never fire, as distinct from rare ones. Coverage should eventually leave out
rules for positions a league cannot start; until then read "never
exercised" with the roster slots in mind.

**9/26 -- WEBHOOK RECEIVER (webhooks/).** Sleeper has no webhooks, so the
push side of the build comes from GitHub. John, 9/26: nothing at VSP or
Booz involved webhooks, and he wants the experience to be real before he
claims it. br-hooks is a Cloudflare Worker with D1 in two separate
environments: sandbox (a throwaway repo, stores raw bodies for fixtures)
and production (battle-rhythm). It verifies X-Hub-Signature-256 on the raw
bytes with a constant-time compare, logs bad signatures without storing
them (so unsigned requests can't burn a delivery id), claims each
X-GitHub-Delivery once in a single upsert (failed or stuck deliveries can
be claimed again, so Redeliver is a retry), alerts Discord on CI state
changes and force-pushes, ignores out-of-order older runs, and only
advances state once Discord accepts the alert. Workers over Render because
a free-tier cold start can exceed GitHub's 10-second timeout. 38 offline
tests; ten planted bugs, two survived the first suite and got tests;
12/12 probe checks against the real Workers runtime with local D1. Not yet
deployed: needs John's Cloudflare account, a sandbox repo and two Discord
webhooks (webhooks/README.md, Setup).

