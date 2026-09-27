# CLAUDE.md — Battle Rhythm project memory

Durable rules and context for any Claude session working in this repo.
Read order: this file, then HANDOFF.md (the current snapshot), then
DECISIONS.md (the log). README.md is the human-facing manual and
DEPENDENCIES.md is the coupling map — read that one before moving any
file. If this file and HANDOFF.md conflict, HANDOFF.md wins on "what's
live right now" and this file wins on rules.

## The user

dirtymurdock on Sleeper (config.json). He runs five leagues, watches
draft rooms live, and has been right every time his read conflicted with
a tool's first answer (Moore keeper bet, GB collision, snake QB
geometry, Gainwell = Bucky's backup, MGR30's RB count). When his read
and the tool disagree, check the tool before arguing.

## Security — non-negotiable

The toolkit is read-only by design. Never touch lineups, waivers, or
claims; deep-link to sleeper.com for actions. His Sleeper "push key" is
a secret: never ask for it, never store it, never put it in code,
config, or chat.

## Architecture

Everything below lives in `battle_rhythm/` as of 9/2 and is reached
through `br.py`; the module names are unchanged.
sleeper_client.py holds the verified scoring engine (dot product vs
league scoring_settings, 22/22 exact vs the app) and league discovery.
draft_helper.py is the brain: board_data() computes everything once
(VORP with remaining-demand replacement + keeper demand floor,
availability-adjusted projections, dynasty/redraft/2QB ADP selection by
league type and roster, turn plan, depth-phase detection);
board/watch/find/explain/rookies/sheet are views on it. weekly.py does
in-season work (lineup, waivers with named drops, both-gain trades)
and RECORDS every recommendation to ledger.py (data/ledger/, Truth
tier); `ledger score` grades them against actual stats the next week.
That ledger is the 9/4 eval — do not add an in-season recommendation
path that bypasses it.
keeper.py knows each league's keeper rules and chain-walks all drafts
per league season for drafted-rookie eligibility. dashboard.py renders
one self-contained HTML file (--serve adds refresh + live draft
polling). mcp_server.py exposes 12 tools to Claude Desktop. paths.py owns
every location on disk and is the only module that knows where anything
lives; nothing else builds a path. data/keepers.json is league rules as
data ("keeper": true drives the ADP caveat). IDP support (LB/DL/DB plus
slot aliases like CB→DB) is baked in and tested, waiting on a future IDP
league. test_all.py is the offline suite — 26/26 before any handoff.

## Where files go — sorted by how hard they are to get back

Set up 8/13. The axis is NOT topic (model / dashboard / league). It is
recoverability, because that is the line that has actually hurt us.

- **Source** — `battle_rhythm/`, plus `br.py`, `mcp_server.py` and
  `test_all.py` at the root. They are the program. (Moved into a
  package 9/2; filenames did not change, so every name in DECISIONS.md
  still finds its file. See RESTRUCTURE.md.)
- **Truth** — `data/` (authored: keepers, ages, byes, fonts),
  `data/measured/` (measured off real drafts: room_bias.json),
  `dossiers/` (447 accumulated research records), `fixtures/`,
  `reports/` (dated weekly research diffs). Rebuilding any of these costs
  a research pass, a season, or is impossible. All tracked in git.
- **Render** — `out/`. One command, under a minute, deterministic.
  Gitignored. Nothing here is ever an input to a decision.
- **Per-league authored material** — `leagues/<slug>/`. Draft briefs,
  notes. `leagues/_index.json` is THE league key: slug → id → folder.
- **`archive/`** — spent scratch. Kept, never read.

The test for the Truth/Render line: can you rebuild it with one command
in under a minute? `dashboard.html` can. `dossiers/` cannot.

Two rules that make the folders worth anything:

1. **Never build a path by hand.** `paths.py` has `data()`, `measured()`,
   `out()`, `league_out()`, `report()`. Before 8/13 three writers emitted to the
   current working directory, so output landed wherever the shell
   happened to be standing.
2. **Never key a folder or filename on a league NAME.** Both Hybrids
   normalize to the same string. Key on the id, resolve through
   `paths.slug_for()`.

`roster.md` is a render that deliberately stays at the repo root and
stays tracked — see "Before recommending any pick" below. Moving it is
the one change here that could fail silently.

`python br.py paths --selftest` fails if `leagues/_index.json` and
`mcp_server.LEAGUE_IDS` drift apart. They already had, once.

## Hard-won lessons — do not relearn these

1. RESTART DISCIPLINE. Code changes require restarting: the --serve
   process, the watch terminal, and for MCP changes a FULL Claude
   Desktop quit (system tray / Task Manager). The refresh button
   reloads data, never code. This bit us three times.
2. STALE PRIORS. Model memory about players (teams, depth charts,
   roles) can be a year wrong — Rachaad White is WAS, not TB. Trust
   live tool output over remembered facts; verify with tools before
   asserting who's on a roster or gone.
3. DISPLAY-ARTIFACT TRAP. Absence from a top-30 board or a market-list
   cutoff does NOT mean drafted. Jayden Higgins "wasn't gone" until
   pick 108 actually took him. Check via rookies/market lists or the
   picks feed.
4. WEBFETCH EXTRACTION. The summarizer garbles aggregation over big
   JSON (it invented MGR30 having 0 RBs when he had 3). Ask for
   mechanical line-per-record output, never aggregates, and cross-check
   surprises.
5. Sleeper settings.type: 2 means dynasty-TYPED, which includes both
   Hybrids (3-keeper leagues, not full dynasty). data/keepers.json's
   "keeper" flag exists because the type field can't tell them apart.
6. ROOM BEHAVIOUR IS PER-LEAGUE DATA, never a default. The LG01 room buys vets ~10 picks before market price, so shave ~10 off
   dADP when estimating survival THERE. Both Hybrid rooms draft close
   to market and get no shave — "these guys know what they're doing,
   for the most part" (8/11). The numbers live in data/keepers.json as
   room_shave; room_bias.py measures them once a draft has picks on the
   board, and the stored value is only the pre-draft prior. I shipped a
   global shave of 10 by generalising the LG01 habit onto rooms
   it does not describe — an observation about one room is not a rule.
7. Advisor discipline: when the user's live read conflicts with tool
   output, re-run the tool first (see The user, above).
8. USE THE CONTEXT YOU ALREADY HAVE. Before calling anything unknowable,
   check what this file, HANDOFF.md, and the session already established.
   Real failure (8/11): asked whether a rival rostered Bucky Irving as
   "the fact I can't see," while the user's own roster in HANDOFF lists
   Irving — which settled it. The error was not a missing tool; it was
   not consulting known context, and it produced a confident conclusion
   that reversed once corrected. roster_map.py now makes league-wide
   ownership a lookup, but the discipline is the lesson.
9. GIT THROUGH THE DEVICE BRIDGE LEAVES A LOCK. A Cowork session
   reaching this folder from the cloud cannot delete files by default,
   so every git write succeeds and then fails to unlink
   `.git/index.lock` — which blocks the NEXT git command. Ask for
   delete permission on the repo root once per session
   (`device_request_delete_permission`) before touching git. Without it
   git is effectively read-only and the only workaround is `mv`-ing the
   lock aside after each write. Found 9/3 mid-rename.
10. THAT SAME SHELL HAS NO GIT IDENTITY. `git commit` fails with
   "Author identity unknown". This repo's history is authored
   `John Murdock <author@example.com>` and that is now set
   `--local`, so it should persist — but if a fresh clone or a new
   machine hits this, read the identity off `git log` rather than
   inventing one, and set it `--local` so the machine's global config
   is left alone.

## Taxi seats — a one-year rookie redshirt, and how he uses them

Told 8/11 after I got the rule wrong three times in a row. Read this
before any taxi advice.

THE RULE. Taxi is rookies only, for one season, and it expires. A player
parked last year is on the ACTIVE roster this year automatically. There
is no activate-or-hold decision. What the seat bought is a season of
free storage — no bench spot consumed — and a player who arrives still
eligible for a drafted-rookie keeper slot. Keeper allowance is 5 off
last year's active roster: 3 keepers plus 2 drafted rookies. A vacated
seat cannot be refilled mid-season, so taxi seats are a DRAFT-DAY
allocation: spend late picks on this year's rookie class.

HOW HE USES IT. Not storage — a call option he intends to cash. He
drafted Jayden Daniels as a rookie and stashed him, drafted Lamar
Jackson and Baker Mayfield, started Mayfield, then mid-season traded
Mayfield for a star running back and promoted Daniels. Carried six that
year instead of seven and won the championship. Gadsden was the same
bet: park a tight end he expected to earn a role while two tight ends
already held active spots. It came in — Gadsden returns as a startable
TE he did not have to draft, in a league that pays a bonus per TE
reception.

THE PLANNING CONSEQUENCE, which is what he actually cares about: a
returning redshirt is one thin skill position he does NOT have to reach
for early. Count returning redshirts as roster BEFORE deciding what the
draft must cover.

MY FAILURE MODE HERE, for the next session: I invented a decision that
did not exist and priced it twice — as a forfeited keeper slot, then as
a forfeited taxi seat — and built an argument on top of both. League
rules that are not in the API live in data/keepers.json. Read them before
reasoning about roster mechanics, and ask him rather than infer.

## Style contract

Advisor, not assistant. Lead with the useful thing. Disagree with
structure: reason, then alternative, then the specific risk. Name what
would flip a recommendation. Mark [Certain]/[Likely]/[Guessing] where a
decision rests on it. Run humanizer on user-facing prose; skip code and
tables. His formatting complaints are precise — "columnar" means a
shared fixed grid across tables, not aligned per table.

## Before recommending any pick

Read **roster.md**. Regenerate it first if a draft has moved:

    python br.py roster

It stays at the repo ROOT, not in `out/`, and it stays tracked in git.
That is deliberate: it is the one render whose staleness fails quietly
instead of loudly, so `git status` showing it modified is how you see
when it was last rebuilt. Do not "tidy" it into `out/` without moving
this rule with it in the same commit.

It lists, per league, every slot and whether it is filled, capacity
against picks remaining, position counts with saturation and
no-insurance flags, and what must still be filled. Sleeper's roster
endpoint is EMPTY during a slow draft — the picks feed holds the truth —
so nothing else in the toolkit shows a live roster.

Late in a draft the binding constraint is roster shape, not talent.
On 8/11 three consecutive pick recommendations were made from a
hand-typed roster 18 picks stale; the real situation (five running
backs, no defense, one quarterback) was in the picks feed the whole
time. Do not reason about a roster from HANDOFF.md or memory.

## Where truth lives

- CLAUDE.md — rules, lessons, architecture. Update when a lesson is
  learned, not per pick.
- HANDOFF.md — snapshot of what's live. Rewrite it at session end;
  anything durable it contains should move here or to DECISIONS.md.
- DECISIONS.md — append-only log: what was decided, why, and what
  would reopen it. Never edit old entries; supersede with a new one.
- README.md — human-facing setup and usage. Don't duplicate its
  content here.
- DEPENDENCIES.md — what is coupled to what: the import graph, every
  filesystem path reference, the external Claude Desktop reference, and
  a move-safety verdict per file. Read it before relocating anything.
- leagues/_index.json — the league key. Slug, id, and folder in one
  place. data/keepers.json and mcp_server.py still carry their own copies;
  reconciling them is the next refactor.
- Plan files like archive/endgame_plan.md go stale the moment picks
  land. Reread the live board every pick; the plan is a prior, not an
  answer. Anything under archive/ is kept, not read.
