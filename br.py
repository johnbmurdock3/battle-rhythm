#!/usr/bin/env python3
"""br — one door into Battle Rhythm.

    python br.py                     what you can run
    python br.py board lg04       any command, any league fragment
    python br.py --help board        that command's own usage

Before 9/2 the toolkit was 27 scripts flat at the repo root, each with
its own hand-rolled argv parsing and no index. Knowing that the draft
board is `draft_helper.py board` and the roster census is
`roster_snapshot.py` was knowledge you carried in your head, and the
README listed 27 invocations you had to read to find the one you wanted.

This dispatches to the same modules with the same arguments. It does not
reimplement their parsing -- runpy runs each one as __main__ with argv
rewritten, so a command here behaves exactly as it always did and there
is no second copy of anything to drift.

LEAGUES take a name fragment, an alias, or the 19-digit id: `board
lg04`, `board lg06`, `board 9000000000000000017`. Never a bare
league NAME -- both Hybrids normalise to the same string, which is why
leagues/_index.json is keyed on the id.
"""

import runpy
import sys

# command -> (module, passthrough argv prefix, one-line what-it-does)
# The prefix is what the module's own __main__ expects to see first.
COMMANDS = {
    # ---- draft -----------------------------------------------------
    "board":    ("draft_helper",    ["board"],   "every available player, ranked by VORP against this league's scoring"),
    "watch":    ("draft_helper",    ["watch"],   "poll a live draft, bell on your turn"),
    "live":     ("draft_live",      [],          "live draft board that re-plans on every pick (localhost:8788)"),
    "find":     ("draft_helper",    ["find"],    "is he available, what is he worth"),
    "explain":  ("draft_helper",    ["explain"], "stat-by-stat breakdown of one player's score"),
    "rookies":  ("draft_helper",    ["rookies"], "rookie class and taxi lottery tickets"),
    "sheet":    ("draft_helper",    ["sheet"],   "printable cheat sheet"),
    "fit":      ("lineup_value",    [],          "what a player adds to YOUR starting lineup, by simulation (was `lineup`)"),
    "keeper":   ("keeper",          [],          "keeper math, per league's own rules"),
    "dynasty":  ("dynasty_value",   [],          "age-curve value, multi-season"),
    "qbsupply": ("qb_supply",       [],          "how many startable quarterbacks the room has left"),

    # ---- roster ----------------------------------------------------
    "roster":   ("roster_snapshot", [],          "rewrite roster.md — READ IT BEFORE RECOMMENDING ANY PICK"),
    "owners":   ("roster_map",      [],          "who in the league owns whom"),

    # ---- season ----------------------------------------------------
    "weekly":   ("weekly",          [],          "lineup / waiver / trade brief, all leagues (records to the ledger)"),
    "lineup":   ("weekly",          ["--lineup"],  "start/sit only: what you started vs what this week says, with odds"),
    "waivers":  ("weekly",          ["--waivers"], "claims only: sized FAAB bids, depth chart, handcuffs, named drops"),
    "ledger":   ("ledger",          [],          "every recommendation made, scored against what happened (`ledger score`)"),
    "truth":    ("truth",           [],          "engine vs Sleeper's own scored points, every league (`truth fetch` on the PC, then `truth compare`)"),
    "review":   ("draft_review",    [],          "rebuild the board at each past pick"),
    "rhythm":   ("rhythm",          [],          "what to run today, and every draft still coming"),
    "recap":    ("recap",           [],          "the morning after a draft: where you beat the board, where you reached"),
    "managers": ("draft_helper",    ["recap"],   "per-manager behaviour: who reaches for vets, who hoards youth (the trade map)"),

    # ---- research --------------------------------------------------
    "dossier":  ("dossier",         [],          "accumulated per-player research"),
    "research": ("research_queue",  [],          "what to look into next, ranked"),
    "rooms":    ("room_bias",       [],          "measure how early this room buys, once picks have landed"),
    "adp":      ("superflex_adp",   [],          "the 2QB market, fetched and interpolated"),

    # ---- output ----------------------------------------------------
    "dash":     ("dashboard",       [],          "build out/dashboard.html   (--serve for refresh + live polling)"),

    # ---- dev -------------------------------------------------------
    "test":     ("__test_all__",    [],          "the offline suite, no network (HANDOFF.md carries the current count)"),
    "smoke":    ("smoke",           [],          "ask the live API what leagues actually exist"),
    "discover": ("sleeper_client", ["discover"], "ask Sleeper which leagues you are in, and cache them"),
    "paths":    ("paths",           [],          "where everything lives (--selftest to check it)"),
    "idp":      ("idp_probe",       [],          "IDP league sanity probe"),
    "backtest": ("backtest_probe",  [],          "does Sleeper serve honest history? run this BEFORE trusting any beat rate"),
    "calibrate":("backtest",        [],          "what a projection edge is actually worth, measured on last season"),
    "release":  ("release",         [],          "the public-repo gate: scan history for the push key, export a scrubbed copy"),
}

GROUPS = [
    ("draft",    ["board", "watch", "live", "find", "explain", "rookies", "sheet",
                  "fit", "keeper", "dynasty", "qbsupply"]),
    ("roster",   ["roster", "owners"]),
    ("season",   ["rhythm", "weekly", "lineup", "waivers", "ledger", "truth", "recap", "review", "managers"]),
    ("research", ["dossier", "research", "rooms", "adp"]),
    ("output",   ["dash"]),
    ("dev",      ["test", "smoke", "discover", "paths", "idp", "backtest",
                  "calibrate", "release"]),
]


def usage():
    print(__doc__.split("\n\n")[0])
    print()
    for title, names in GROUPS:
        print(f"  {title}")
        for n in names:
            print(f"    {n:<10} {COMMANDS[n][2]}")
        print()
    print("  a league is a fragment, an alias or an id — 'board lg06' works")
    print("  every command also takes its own flags; `br.py --help <cmd>`")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        if len(argv) > 1 and argv[1] in COMMANDS:
            mod = COMMANDS[argv[1]][0]
            import importlib
            m = importlib.import_module(f"battle_rhythm.{mod}")
            print(m.__doc__ or f"{mod} has no docstring")
            return 0
        return usage()

    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        near = [c for c in COMMANDS if c.startswith(cmd)]
        print(f"br: no command {cmd!r}"
              + (f" — did you mean {' or '.join(near)}?" if near else ""),
              file=sys.stderr)
        print("run `python br.py` for the list", file=sys.stderr)
        return 2

    mod, prefix, _ = COMMANDS[cmd]
    if mod == "__test_all__":          # lives at the root, not in the package
        sys.argv = ["test_all.py", *rest]
        return runpy.run_path("test_all.py", run_name="__main__") and 0

    sys.argv = [f"{mod}.py", *prefix, *rest]
    runpy.run_module(f"battle_rhythm.{mod}", run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
