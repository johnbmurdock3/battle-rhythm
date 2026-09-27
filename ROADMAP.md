# ROADMAP.md — what to build, in what order

> **Updated 2026-09-02.** Shipped since 8/13: **P1 #5** (the turn-plan
> banner that printed "starters filled" with a required slot empty),
> **P2 #8** (draft review as the morning-after summary — `br.py recap`),
> and **P2 #11** (trade flags: surplus/deficit, bye pileup, playoff
> leverage and value gap were all already implemented in `weekly.py`
> when checked, so this entry was stale rather than open). **P1 #4** —
> the LG02 and LG04 cards — is done, and LG06 has one
> too. Still open: **P2 #12** (the backtest), **P2 #13** (`room_shave`
> measured), **P1 #7** (`keeper.py` reasons from last year's roster),
> and **A** (per-position baselines in `lineup_value`).
>
> A new defect of the same class as P1 #5 was found and fixed on 9/2:
> pre-draft, the turn plan's "now" line named players the market takes
> before your pick. See HANDOFF.md.

Written 8/13. Every P0 and P1 item below is grounded in something that
actually went wrong in a session, not in a guess about what might be
useful. The DECISIONS entry is cited so a future session can read the
failure before writing the fix.

Six leagues, all of them real as of 8/13: two Hybrids (8/18), LG01 (live), LG04 (9/6), LG02 (undated), and LG06 — the IDP league, `9000000000000000022`, pre-draft with no
date. All six are in `leagues/_index.json`.

---

## P0 — before Tuesday 8/18

These change which player gets taken. Everything else can wait.

### 1. Read traded picks into the turn plan · M — **DONE 8/13**

`sleeper_client.my_draft_picks()` exists and is tested. Nothing calls
it. `lineup_value` still builds its pick list from `slot_picks()` alone
and prints a warning telling you to check the endpoint by hand.

He owns **eleven** picks in each Hybrid and every tool says ten. The
turn plan therefore prices survival against a turn sequence that isn't
his, and in the emoji league it misses that picks 90 and 91 are
consecutive — which changes what's worth gambling on at 90.

Wire `my_draft_picks()` into `build()`, thread the result to the turn
plan, and print gained and lost picks explicitly. `keeper.upcoming_picks`
already accepts a `roster_id` and applies them; nothing passes one.

### 2. Fix the taxi filter · S

Both Hybrids currently report *"no rookie qualifies"* at both taxi
picks. Four picks across two drafts with no recommendation.

The cause is a filter that ranks taxi candidates by dynasty ADP and
discards the 183 rookies who don't have one. Those 183 **are** the taxi
population — a redshirt nobody drafts is exactly the player no market
prices. This is the same failure the projection filter had in August,
which is already logged, fixed once, and has now reappeared wearing
different clothes.

Fall back to rookie status plus age when no dynasty price exists, rather
than dropping the player.

### 3. Bye-week awareness · M

I have hand-computed byes four times this week and it changed the plan
every time. In the emoji league the model's own line put **six players
out in week 13** — four of them Baltimore — leaving eight bodies for
nine slots. That is a forfeited week the tool cannot see.

`lineup_value` is a season-total model by design and shouldn't become a
weekly simulator. The cheap version is enough: carry each candidate's
bye, count how many rostered players share it, and flag a pick that
would leave you short of nine startable bodies in any week. A warning,
not a re-ranking.

---

## P1 — before LG04 on 9/6

### 4. LG02 and LG04 cards · M

Nothing exists for either. LG02 is the harder one: 14 teams, and it
carries **K and DEF**, which no card has ever had to plan around. LG04
has two flex slots and a round-cost keeper rule that first bites in 2027,
so late-round value there is worth more than the board says.

### 5. The turn-plan banner lies when K or DEF is unfilled · S

`draft_helper.py:422` excludes K and DEF from `needs_open`, which is
correct for the need model — you don't want the board chasing a defense
in round 4. But `needs_open` also gates the depth-phase branch, so the
banner prints *"starters filled"* while a required slot sits empty. It
did exactly that through two live LG01 picks.

Harmless in the Hybrids, which have no DEF slot. Actively misleading in
LG02, which has both.

### 6. Audit dashboard.py and draft_review.py for pick arithmetic · S — **DONE 8/13**

Audited. `dashboard.py`, `draft_review.py` and `dossier.py` do no pick
arithmetic at all — nothing to fix. `roster_snapshot`'s "picks remaining"
did assume one pick per round and is now real ownership. The one site the
audit turned up that was NOT on this list: the live `watch` alarm, which
would not have rung for pick 95.

### 7. keeper.py reasons from last year's roster · S

It recommends Mike Evans, who wasn't kept, and prints swap advice against
keepers that locked on July 1. The eligibility list is correct; the
recommendations are retrospective. Either gate it on the lock date or
label the output as historical.

---

## P2 — post-draft, the season tools

The draft is one day. The season is eighteen weeks across six leagues,
and this is where the toolkit currently thins out. `weekly.py` covers
lineup, waivers and trades; the rest is unbuilt.

### 8. Draft review, run once per league · M

`draft_review.py` rebuilds the board at each past pick and already
works. What's missing is the summary a manager actually wants the next
morning: where you beat the board, where you reached, which of your
picks the room disagreed with, and what your roster now looks like
against the league.

### 9. Weekly lineup, run every Thursday · M

The one job that repeats sixty-odd times a season. `weekly.py` has the
bones. It needs to be trustworthy without supervision, which means
handling byes and injury designations properly rather than optimising a
lineup that includes a player on a bye.

### 10. Waiver targets with the two-tier rule · M

His rule, already stated: tier 1 is a free agent who beats a projected
starter, and that one gets FAAB. Tier 2 beats your worst bench player,
and that's churn. Both Hybrids carry **1,000 FAAB entirely unspent**,
which is a large asset doing nothing.

### 11. Trade flags · L

Also already specified: positional surplus and deficit, bye pileups,
playoff-week leverage in weeks 15 through 17, and gaps between league
scoring and market ADP. The last one is the interesting one, because
tiered-reception Hybrid scoring diverges from PPR ADP in a way most of
the room isn't pricing.

### 12. The actuals-versus-projections backtest · L

Invoked twice as "the real answer" and never built. It's the only thing
that settles whether `ages.json` is right, including the WR cliff at
0.78 a year past 30 that's been flagged as too steep since August. Until
it exists, every dynasty-value gap the tool reports is conditional on
curves nobody has tested.

### 13. `room_shave` measured instead of assumed · S

Zero in both Hybrids on his word, ten in LG01 from observation.
`room_bias.py` measures it once picks land. Run it after 8/18 and
replace the priors with numbers.

---

## Not on the list, deliberately

**Superseded 8/13: the sixth league exists.** This entry said IDP
support was built and waiting on a league id. There is an id --
`9000000000000000022`, 10 teams, pre-draft. It went unnoticed because
`paths.py --selftest` compared `leagues/_index.json` against
`mcp_server.LEAGUE_IDS`, two files maintained by hand; neither is the
API. `smoke.py` now asks the API.

Its scoring is not a normal league with defenders bolted on. Touchdowns
are 10 points, passing yards 0.05, full PPR, turnovers -5, yardage
bonuses at 100/200/300/400 -- and **0.5 per pass attempt and per rush
attempt**, which nothing else in the portfolio has. A 600-attempt
quarterback banks 300 points before a yard, so volume beats efficiency
in a way no existing card reasons about. It carries K but no team DEF,
a third roster shape after LG02 (both) and the Hybrids (neither).
The full note is in `leagues/_index.json`.

**No new data sources.** Every fix above uses endpoints already in use.
The failures this week came from not reading fields that were sitting in
responses already fetched — `reversal_round` was in an object I pulled
twice for other reasons.

---

## The pattern worth naming

Six of the last eight defects were **reports that contradicted the code
beneath them**. The taxi header claiming players were excluded while they
started. The turn banner claiming starters were filled with a slot empty.
The census printing "over the limit" for rosters that were legal. Pick
numbers that were arithmetically perfect for a format the league doesn't
use.

In every case the underlying computation was fine and the sentence on top
was wrong, which is the worst combination: nothing looks broken, and the
sentence is what the next session reads.

Tests catch bad math. They do not catch a true number with a false label.
The only thing that has caught those is a human reading the output — and
every single one this week was caught by him, not by me.

Where a fix below prints something, the message deserves as much scrutiny
as the arithmetic.

---

## Added 8/13 — after the draft-2 measurement

### A. Price each candidate against his OWN position's replacement · M

`lineup_value`'s marginal model measures every candidate against the
weakest body in the lineup, so with most slots floored it collapses to
raw projection and disagrees with the VORP board. Documented around for
Tuesday (the board is the ranking); the real fix is per-position
baselines. Do NOT attempt before 8/18.

### B. Rerun draft2_probe with a measured room_shave · S

The measurement assumes the room drafts to depleted ADP. `room_bias.py`
gives the real shave once Tuesday's picks land. If the room reaches, the
draft-2 tail is thinner still and holes cost even more.
