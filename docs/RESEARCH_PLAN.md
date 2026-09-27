# Player dossiers — plan

Goal: a searchable per-player record of the things that move a draft
decision but never appear in a projection — team change, role change,
who is ahead of them and whether he is declining, scheme change,
injury history, contract signals, camp reports.

Written 8/11 after the Mason/Gainwell research proved the value and
exposed the cost.

## What we learned from the pilot

Two players took ~8 web fetches and produced one reversed
recommendation. The facts that actually moved the decision:

1. Team change (Gainwell: PHI -> PIT -> TB). Biggest single factor.
   His 2025 projection-beating was a Pittsburgh workload that does
   not transfer to Tampa.
2. Prior-year workload IN CONTEXT of which team it happened on.
3. Who is ahead of him: name, age, contract, health, decline
   (Aaron Jones, 31, pay cut $9M -> $5.5M, 2nd-worst YAC of 48).
4. Scheme / coordinator change (Zac Robinson; Vikings wide zone).
5. Injury history with dates and body part, plus current status.
6. Contract signals — a pay cut is the team telling you something.
7. Camp reports and beat-writer quotes.

Every one of those is invisible to Sleeper's projection feed. That is
the whole case for doing this.

## The scope problem, and the fix

"Every player" is the wrong target. ~419 players carry a real weekly
projection; the draftable universe across four leagues is 300-500.
At 6-8 fetches each that is thousands of calls, days of wall time,
and most of it changes no pick.

Triage instead. Research earns its cost only where:

- the model and the market disagree sharply (|model rank - dADP rank|
  is large — someone is wrong and it is worth knowing who),
- the player sits inside a pick window we actually own,
- something changed (new team, new coordinator, starter ahead of him
  hurt or aging, rookie with no track record).

That third bucket is the important one. The Gainwell finding
generalizes: projection systems lag role changes. So the players
worth researching are precisely the ones whose situation moved.

## Phase 1 — make the tool say who to research

New module, no network, reads board_data. Ranks every available
player by expected value of information:

    research_score = divergence x proximity x volatility

- divergence: |model value rank - dADP rank|, normalized
- proximity: how close he is to one of my actual next picks
- volatility: flags computable from data we already hold —
  team differs from last season, rookie (years_exp 0), injury tag
  present, depth_chart_order changed, age past the positional cliff

Output: a ranked research queue, top ~40. This turns an unbounded
job into a bounded one and stays useful for every future draft.

Cost: one session, offline, no restart risk beyond a serve reload.

## Phase 2 — schema and storage

One JSON file per player, keyed by Sleeper player_id (names collide;
one file per player means parallel writers never conflict).

    dossiers/<player_id>.json
    {
      "player_id": "...", "name": "...", "as_of": "2026-08-11",
      "stable": {                      # recompile rarely
        "team_history": [{"season": 2025, "team": "PIT"}, ...],
        "workload": [{"season": 2025, "team": "PIT",
                      "carries": 114, "rec": 73, "td": 8}],
        "contract": {"years": 2, "signed": "2026", "note": "..."},
        "scheme": {"oc": "Zac Robinson", "note": "..."},
        "competition": [{"name": "Bucky Irving", "age": 23,
                         "status": "full-go 7/29", "note": "..."}]
      },
      "volatile": {                    # refresh near draft day
        "injury": {"status": "...", "as_of": "..."},
        "camp": [{"quote": "...", "who": "...", "date": "..."}],
        "projected_share": 0.39
      },
      "sources": [{"url": "...", "fetched": "2026-08-11"}],
      "confidence": "high|medium|low"
    }

The stable/volatile split is what keeps this affordable. Team,
contract, scheme, and career workload hold for a season. Injury and
camp buzz decay in days. Compile stable once; refresh volatile the
morning of each draft.

Staleness is displayed, never hidden: anything past its freshness
window renders greyed with its as_of date. A three-week-old camp
report presented as current is worse than no dossier.

## Phase 3 — the research pass

Parallel subagents, 4-5 players each, each returning the schema above
as structured output. Batched by research-queue rank, so we stop when
the value runs out rather than when the list ends.

Rules for researchers, learned the hard way:
- mechanical facts with sources, never aggregate summaries
  (the WebFetch summarizer invents things — see CLAUDE.md lesson 4)
- date every volatile fact; conflicting reports keep the later date
  and record both
- never assert a team or depth chart from model memory (lesson 2)

## Phase 4 — surface it

- `python br.py dossier <name>` — the record, plain text
- dashboard: a NOTE column on the Board and Dynasty tabs showing the
  one-line "what changed" summary, full record on hover/expand
- a search box over dossiers + player names. Search was already a
  parked design leftover (design_brief.md), so this pays two debts.

## Weekly refresh (live as of 8/11)

Scheduled task "Sleeper weekly research refresh (Tue)", Tuesdays 8:00 AM
PT. Fires a FRESH session with no memory — the whole procedure lives in
the task prompt itself, not here. This section is for humans.

What it does: checks the device bridge first and stops cleanly if it
cannot reach the repo (stale player facts are worse than none), builds a
100-150 player refresh list from rostered + top-25-available-per-league +
open questions, fans out subagents at 1-3 searches per player, appends a
dated observation to each timeline, and delivers the rebuilt bundle plus
a one-page diff.

Why append and not overwrite: slope. A player at 71% snaps is a fact; a
player who went 45 -> 58 -> 71 across three weeks is a signal, and the
projection feed shows neither. Overwriting `volatile` each week throws
away the only thing weekly cadence buys you. dossier.py enforces this —
append_observation() never replaces a different date, and trend() will
not call a direction from a single observation.

Why not all 447 weekly: cost, and it would be mostly waste. A deep-bench
back's situation does not move, and when it does you hear about it. The
refresh list is the triage; everything else keeps its stable facts and
ages out of the volatile half honestly.

Known limitation: the task can only write to his disk when the Claude
desktop app is running. It always delivers the file, so nothing is lost
either way — he runs `python br.py dossier import <bundle>` when he next
sits down.

## Sequencing

Phase 1 is worth building regardless — it is offline, permanent, and
tells us how big Phase 3 actually needs to be. Phases 2-4 follow the
answer to one question: which draft does this serve first?

Dynasty is live now (picks 129/136). LG03-LG05 is Aug 18, superflex,
a different player universe and different ADP market. LG02 and
LG04 are Sep 5-6, both redraft-flavored.

Open decisions for the user:
- research depth (top 40 vs top 150 vs everything)
- whether to spend the tokens on parallel agent fan-out
- which league's universe gets researched first
