# RESTRUCTURE.md — the package move

Written 2026-09-02. Supersedes DEPENDENCIES.md's "Red — defer until
after the 8/18 draft." That date has passed; this is that phase.

DEPENDENCIES.md still answers *what is coupled to what* and is the file
to read before moving anything. This file answers *how the move is
sequenced and what must not break.*

---

## What the folder actually is, as of today

36 Python files, 16,076 lines, flat at the repo root. Six offline test
suites, all green: `test_all.py` 33, `dynasty_value` / `lineup_value` /
`roster_snapshot` / `superflex_adp` / `draft_review` `--selftest`, and
`paths --selftest` 14/14.

Phases 0-4 of DEPENDENCIES.md are done. `paths.py` owns `DATA`,
`MEASURED`, `LEAGUES`, `OUT`, `DOSSIERS`, `FIXTURES`, plus `index()`,
`slug_for()`, `id_for()` and two linters (`shadowed()`, `cwd_writes()`).
That is the reason this phase is now cheap enough to attempt.

### Three things the docs do not know

1. **There are seven leagues, not six.** `LG07` (12 teams,
   in-season, no FAAB) has never appeared in `leagues/_index.json`,
   `keepers.json`, or `mcp_server.LEAGUE_IDS`. This is the second time
   a league arrived unnoticed; `smoke.py` asks the API and is the only
   thing that would have caught it, and it needs network the sandbox
   does not have.

2. **`LG03-LG05` is now named `LG03`.** Same id,
   `9000000000000000013`. The slug rule held — every folder and file
   keyed on the id survived a rename that would have broken any
   name-keyed path. `_index.json`'s `name` field and every prose
   reference are wrong; the code is right.

3. **The season is live.** Week 1, regular. Four leagues in season,
   three pre-draft. HANDOFF.md describes a pre-draft world from 8/11.

---

## Dead code — 8 orphans, 2,683 lines

Nothing imports these and no document names them. Every one is a
spent one-shot that already did its job and got committed:

    add_drop_flag.py     291    added lineup_value --drop (commit f0d41a5)
    adp_probe.py         375    the adp_keys_for investigation
    dedupe_shape.py      288    roster geometry dedupe (commit 67e326f)
    fix_keeper_board.py  317    the three contradicting labels (0baca0e)
    fix_writers.py       226    re-anchored the cheatsheet write (595e11a)
    organize.py          214    placement-as-a-rule (4040655)
    wire_all.py          505    adp wiring, phase 1 (bfe9925)
    wire_rest.py         367    adp wiring, phase 2 (dfa477d)

They go to `archive/`, which CLAUDE.md defines as kept and never read.
`migrate.py` joins them — README calls it "kept for reference," which is
the same thing.

Kept live, though nothing imports them, because a document tells a future
session to run them: `idp_probe.py` (HANDOFF: run before the IDP draft),
`qb_supply.py` (the pick-8 count that settled the Hybrid card),
`smoke.py`, `backtest_probe.py`, `draft2_probe.py`, `proj_audit.py`,
`reconcile.py`.

---

## Layout

Module **filenames do not change.** 115 KB of `DECISIONS.md`, a
`CHANGELOG.md`, four other docs and every commit message refer to these
files by name. The written history is the most expensive thing in this
repo to rebuild — CLAUDE.md's own recoverability axis puts it in the
Truth tier — and renaming `draft_helper.py` to `board.py` orphans every
sentence written about it. Location changes; names do not.

    battle_rhythm/
      __init__.py
      paths.py              REPO must climb one MORE level — see below
      leagues.py            NEW. the one league-identity reader
      sleeper_client.py
      league_rules.py
      roster_shape.py
      model/
        draft_helper.py     the brain
        dynasty_value.py
        lineup_value.py
        superflex_adp.py
        keeper.py
        room_bias.py
      season/
        weekly.py
        recap.py            NEW. draft recap
        trades.py           NEW. trade flags
      report/
        dashboard.py
        roster_snapshot.py
        draft_review.py
        dossier.py
        research_queue.py
        roster_map.py
      tools/                the kept probes
      cli.py                one dispatcher

    br.py                   the single entry point
    mcp_server.py           STAYS AT ROOT. see G below
    test_all.py             stays at root
    roster.md               stays at root, tracked. CLAUDE.md rule

---

## The five things that break, and the fix for each

### 1 · `paths.REPO` — the one line that fails silently

    REPO = pathlib.Path(__file__).resolve().parent

Inside `battle_rhythm/` that resolves to the package directory, not the
repo. `DATA`, `LEAGUES`, `OUT`, `DOSSIERS` all move with it, and every
one of them then points at a directory that does not exist. Some readers
would raise; `paths.out()` would happily create a second `out/` inside
the package and write there.

Fix: `.parent.parent`, and a selftest assertion that `REPO / "data"` and
`REPO / "leagues/_index.json"` both exist. Assert the location, do not
trust the arithmetic.

### 2 · Bare-name imports, 22-way fan-in

`from sleeper_client import ...` in 23 modules, `draft_helper` in 22,
`paths` in 21. Every one becomes a package-relative import. Mechanical,
wide, and the kind of edit that is either completely right or fails
loudly at import time — which is the good failure mode.

### 3 · Class B leftovers — four sites still resolve data as a sibling

    sleeper_client.py:74    config.json via Path(__file__).parent
    lineup_value.py:66      HERE = Path(__file__).parent
    roster_snapshot.py:30   HERE = Path(__file__).parent
    dashboard.py:915        _load_json("keepers.json"), _load_json("fonts.json")

These survived phases 1-4. Each must route through `paths` before the
move, not after.

### 4 · Two selftests read their own source

`lineup_value.py:1749` and `roster_snapshot.py:690` call
`Path(__file__).read_text()` and assert against the text. They survive a
move but any assertion about file content needs re-reading after one.

### 5 · G · The external reference

`%APPDATA%\Claude\claude_desktop_config.json` holds the absolute path
`C:\Users\johnb\workspace\Sleeper\mcp_server.py`. Moving that file
breaks the MCP server — the tools used mid-draft — and fixing it means
editing a file outside this repo plus a full Claude Desktop quit from
the system tray.

Fix: **`mcp_server.py` does not move.** It stays at the root and becomes
a thin shim that imports from the package. The external config keeps
working, untouched, and no restart is needed to *keep* working. A
restart is still required to pick up the change itself.

The same shim logic covers the 27 documented `python <file>.py`
commands: the handful that CLAUDE.md and HANDOFF.md name as standing
rules — `roster_snapshot.py` above all — keep a root shim until the docs
are rewritten in the same commit that removes it.

---

## Sequence

Each phase ends with all six suites at or above their recorded counts.
A count that drops means a check was deleted rather than fixed; find out
which before continuing.

| phase | scope | risk |
|---|---|---|
| 0 | commit everything; tag `pre-restructure-2026-09-02` | none — **done** |
| 1 | 9 orphans to `archive/`; delete `__pycache__` | none |
| 2 | route the four Class B leftovers through `paths` | low |
| 3 | `battle_rhythm/` flat: every module moves, imports rewritten, `paths.REPO` climbs | medium |
| 4 | root shims: `mcp_server.py`, `roster_snapshot.py`, `test_all.py` | low |
| 5 | `br.py` + `cli.py` — one entry point, consistent flags | low |
| 6 | subpackages `model/ season/ report/ tools/` | medium |
| 7 | `leagues.py`: one league key; `keepers.json` and `LEAGUE_IDS` read it | medium |
| 8 | rewrite the 27 documented commands; retire the shims | low |

**Phase 3 is a strict prefix of phase 6.** A flat package is a real
package with one entry point and a clean root; the subpackage grouping
is presentation on top of it. If LG04 on 9/6 arrives with phases 1-5
done and 6-8 not, nothing is half-moved and nothing is broken. That is
the reason for the split, and it is the only concession this plan makes
to the draft calendar.

---

## What would flip this plan

- **If `test_all.py` cannot be made to pass from inside the package**,
  stop at phase 2. The suite is the only thing standing between a
  16,000-line move and a silent wrong number, and this repo's own
  history says the dangerous defect is a true computation under a false
  label — which no import error will catch.
- **If the MCP server cannot be restarted and verified before 9/6**,
  phases 3-4 do not ship. A draft-day tool that does not answer is worse
  than a cluttered root.
