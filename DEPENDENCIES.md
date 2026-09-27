# DEPENDENCIES.md — what breaks if a file moves

> **Superseded in part, 2026-09-02.** The package move this file calls
> "Red -- defer until after the 8/18 draft" has happened. RESTRUCTURE.md
> carries what actually moved and what broke. The coupling analysis
> below is still the right map; the line numbers and the "suggested
> order" table are history. Class G (Claude Desktop's absolute path to
> mcp_server.py) was resolved by not moving that file.

Written 2026-08-13, before any reorganization. Built by static analysis of
all 19 `.py` files plus every `.md` in the repo root. Line numbers are from
that date; re-verify before acting if code has changed since.

Read this before moving anything. The scaffold proposal lives separately;
this file only answers one question: **what is coupled to what.**

---

## The nine dependency classes

Every coupling in this repo falls into one of these. The move plan at the
bottom is ordered by which classes a move touches.

### A · Python import resolution — flat namespace

All 19 modules sit in one directory and import each other by bare name
(`from sleeper_client import ...`). There is no package, no `__init__.py`,
no relative imports.

Fan-in, highest first:

| module | imported by | count |
|---|---|---|
| `sleeper_client` | backtest_probe, dashboard, dossier, draft_helper, draft_review, dynasty_value, keeper, lineup_value, mcp_server, reconcile, room_bias, roster_map, roster_snapshot, superflex_adp, test_all, test_scoring, weekly | **17** |
| `draft_helper` | backtest_probe, dashboard, dossier, draft_review, dynasty_value, keeper, lineup_value, mcp_server, research_queue, room_bias, roster_map, roster_snapshot, superflex_adp, test_all, weekly | **15** |
| `dynasty_value` | dashboard, dossier, draft_review, lineup_value, research_queue, room_bias, roster_map, roster_snapshot, superflex_adp, test_all | **10** |
| `dossier` | dashboard, reconcile, roster_map, test_all | 4 |
| `weekly` | dashboard, mcp_server, test_all | 3 |
| `keeper` | lineup_value, mcp_server, test_all | 3 |
| `superflex_adp` | lineup_value | 1 |
| `room_bias` | keeper | 1 |
| `roster_map` | reconcile | 1 |
| `research_queue` | test_all | 1 |
| `dashboard` | test_all | 1 |

Leaf entry points, imported by nobody: `backtest_probe`, `draft_review`,
`lineup_value`, `mcp_server`, `reconcile`, `roster_snapshot`, `test_all`,
`test_scoring`.

Surface area actually crossing module lines: `sleeper_client` exports 22
symbols, `draft_helper` 22, `dynasty_value` 14. That is a wide contract —
splitting either of the top two across folders means auditing ~22 call
sites each, not one import line.

Existing `sys.path` bootstraps that assume the flat layout:

- `test_all.py:19` — `sys.path.insert(0, str(HERE))`
- `test_scoring.py:9` — `sys.path.insert(0, str(Path(__file__).parent))`
- `mcp_server.py:34-35` — inserts its own directory, using a Windows-first
  `__file__.rsplit("\\", 1)` with a POSIX fallback

All three break the moment the file doing the insert stops being a sibling
of the modules it imports.

### B · Data files resolved as siblings of code

Every data read is `Path(__file__).parent / "<name>.json"`. Code and data
are the same directory by assumption, at these sites:

| file read | read by | line |
|---|---|---|
| `keepers.json` | `keeper.py` | 266 |
| | `lineup_value.py` | 249, 684, 721 |
| | `roster_snapshot.py` | 371 |
| | `draft_review.py` | 146 |
| | `dashboard.py` | 96 (via `_load_json`), 905 |
| `fonts.json` | `dashboard.py` | 96, 906 |
| `ages.json` | `dynasty_value.py` | 58 |
| `byes.json` | `sleeper_client.py` | 463 |
| `config.json` | `sleeper_client.py` | 74 |
| `fixtures/*.json` | `test_all.py` | 39, 47 |
| | `test_scoring.py` | 12 |

**`keepers.json` has no shared loader.** Five modules open, parse, and
interpret it independently across seven sites. `lineup_value.py:684` and
`:721` each take an optional `path` override; the other five do not. Any
change to its shape or location is a five-module edit.

This is also where league rules that are not in the Sleeper API live, which
CLAUDE.md names as a repeat failure source. It deserves one reader.

### C · Outputs written next to the code

| output | writer | constant |
|---|---|---|
| `dashboard.html` | `dashboard.py` | `OUT` (:32), also served at :1376 |
| `roster.md` | `roster_snapshot.py` | `OUT` (:30), written :444 |
| `room_bias.json` | `room_bias.py` | `OUT` (:35), re-read :162, :205, :221 |
| `dossiers/` | `dossier.py` | `STORE` (:30), used :136, :150 |

Each is one constant. These are the cheapest moves in the repo.

### D · Outputs written to the current working directory

These have no `HERE` and no `OUT`. They land wherever the shell happens to
be when you launch:

| output | writer | line |
|---|---|---|
| `research_queue_<league>.json` | `research_queue.py` | 198 |
| `cheatsheet_<league>.txt` | `draft_helper.py` | 565 |
| `refresh_list.json` | `dossier.py` | 535 |

`research_queue_lg05.json` is in the repo root only because that is
where you were standing. This is a latent dependency on launch directory
that no folder structure fixes on its own — it needs three one-line edits.

### E · Cache — already outside the repo, unaffected

`sleeper_client.py:90` sets `CACHE = Path.home() / ".sleeper_cache"`.
Everything under it (`leagues.json`, `players_nfl.json`, `proj_*.json`,
`season_agg_*.json`, `adp_*.json`, `sflex_adp_*.json`) is untouched by any
reorganization. `test_all.py:59` redirects `dh.CACHE` to a temp dir, so
tests do not depend on it either.

### F · League identity is duplicated in three places

| source | contents | leagues |
|---|---|---|
| `keepers.json` | rules text, `keeper`, `taxi_slots`, `room_shave`, keyed by 19-digit ID | 4 |
| `mcp_server.py:37-43` `LEAGUE_IDS` | slug → ID map | **5** |
| Sleeper API discovery | `~/.sleeper_cache/leagues.json` | all |

`mcp_server.py` carries `"lg02": "9000000000000000010"`, which
`keepers.json` does not have at all. The two files disagree today.

Slugs also disagree with prose. `mcp_server` calls `9000000000000000019`
`hybrid_hero`; HANDOFF calls it "LG05"; `lg05_emoji_brief.md`
uses a third convention. `mcp_server`'s `lg05` is
`9000000000000000013`, the 8/18 draft, whose plan is `lg05_brief.md`.

Add `room_bias.json` (measured, keyed by ID), the HANDOFF status table, and
the `lg05_*` filename convention, and league identity is spread across
six places with no single index.

### G · References from outside the repo

- **Claude Desktop MCP config.** `%APPDATA%\Claude\claude_desktop_config.json`
  holds the absolute path `C:\Users\johnb\workspace\Sleeper\mcp_server.py`
  (documented in `mcp_server.py:16`). Moving that file breaks the MCP server
  and requires editing an external file plus a full Claude Desktop quit —
  CLAUDE.md lesson 1.
- **`mcp_server.py:162`** fakes `sys.argv = ["weekly.py", ...]` around a call
  into `weekly`. It depends on `weekly`'s argument parsing, not just its
  import.

### H · Documented commands

27 distinct `python <file>.py ...` invocations across README, HANDOFF,
CLAUDE.md and ROADMAP, all assuming repo root as the working directory.

The one that matters most: CLAUDE.md's standing rule — *"Before recommending
any pick, read roster.md. Regenerate it first: `python roster_snapshot.py`."*
If that command breaks after a move, the failure is silent. A future session
reads a stale `roster.md` and recommends picks against a roster that has
moved on. That is exactly the 8/11 failure the rule was written to prevent.

### I · Self-referential

`lineup_value.py:1488` reads its own source with
`Path(__file__).read_text()` inside a selftest. It survives a move, but any
assertion it makes about file content is worth checking after one.

---

## Move-safety verdict, per file

### Green — move today, nothing in code reads them

`MISPRICING.md`, `RESEARCH_PLAN.md`, `design_brief.md`, `COLUMNS.md`,
`CHANGELOG.md`, `endgame_plan.md`, `cowork-handoff-prompt.md`,
`next_session_prompt.md`, `before.txt`, `after.txt`, `lg05_brief.md`,
`lg05_emoji_brief.md`, `keepers.template.json`,
`dossiers_lg05_all.json`, `dossiers_lg05_deep.json`,
`research_queue_lg05.json`, `__pycache__/` (delete).

Caveat: `lg05_brief.md` is named in HANDOFF and ROADMAP five times.
Text-only, but those references are what a future session follows.

### Yellow — one constant each

| file | edit |
|---|---|
| `dashboard.html` | `dashboard.py:32` |
| `roster.md` | `roster_snapshot.py:30` + the CLAUDE.md rule text |
| `room_bias.json` | `room_bias.py:35` |
| `dossiers/` | `dossier.py:30` |
| `ages.json` | `dynasty_value.py:58` |
| `byes.json` | `sleeper_client.py:463` |
| `config.json` | `sleeper_client.py:74` |
| `fonts.json` | `dashboard.py:906` |
| `fixtures/` | `test_all.py:39,47` + `test_scoring.py:12` |

### Orange — multi-module, needs a shared loader first

`keepers.json` — 5 modules, 7 sites. Write `load_league_rules()` once,
returning today's exact dict shape, repoint all seven, confirm
`test_all.py` still passes, and only then move the file.

### Red — defer until after the 8/18 draft

- **Any `.py` file.** 17-way fan-in on `sleeper_client`, 15 on
  `draft_helper`. Requires a package with `__init__.py` and either relative
  imports run via `python -m`, or a path shim — plus rewriting all 27
  documented commands.
- **`mcp_server.py`.** External absolute path in Claude Desktop config, its
  own `sys.path` bootstrap, and a full app restart to test.

---

## Two blockers, before any move

**1 · There is no `.git` in this folder.** Verified 8/13. Fifty-one files,
a 79 KB append-only `DECISIONS.md`, no version control and no rollback. If a
move breaks something at 11pm on Monday there is nothing to reset to.
`git init` and one commit costs about a minute.

**2 · Five days to the 8/18 draft.** The Red items above have no upside
before Tuesday and a real downside. The Green and Yellow items carry the
organizational benefit and touch nine one-line constants between them.

---

## Suggested order

| phase | scope | risk | when |
|---|---|---|---|
| 0 | `git init`, commit everything as-is | none | now |
| 1 | Green moves: docs, briefs, dead artifacts, delete `__pycache__` | none | now |
| 2 | Yellow moves: nine constants, one file at a time, `test_all.py` green after each | low | now |
| 3 | Fix Class D — give the three cwd writers an explicit output root | low | now |
| 4 | `load_league_rules()` + one league index reconciling `keepers.json` with `mcp_server.LEAGUE_IDS` | medium | now or after 8/18 |
| 5 | Red: package the `.py` files, move `mcp_server.py`, rewrite documented commands | high | **after 8/18** |

Phase 4's league index is the one that pays twice: it closes the
`lg02`-missing-from-`keepers.json` gap and gives the per-league grouping
something to key on that is not a 19-digit number.

---

## Verification after every phase

    python test_all.py                     # 26 passed, 0 failed
    python dynasty_value.py --selftest     # 55
    python lineup_value.py --selftest      # 65
    python roster_snapshot.py --selftest   # 37
    python superflex_adp.py --selftest     # 10
    python draft_review.py --selftest      # 9

A count lower than these means a check was deleted, not fixed. Per HANDOFF,
find out which.

Selftests do not cover Class G. After any phase touching `mcp_server.py`,
quit Claude Desktop from the system tray, reopen, and call one tool.
