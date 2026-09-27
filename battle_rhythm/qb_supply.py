"""
qb_supply.py — is "replacement quarterback" a real player or a fiction?

    python qb_supply.py 9000000000000000013 --slot 8
    python qb_supply.py lg05 --slot 3

THE QUESTION THIS SETTLES (8/13). `lineup_value` prices Dak Prescott at
+82.7 and Chase Brown at +167.2, so the turn plan takes no quarterback at
any pick. That number is measured against a REPLACEMENT superflex
quarterback — floored_roster puts one in the SUPER_FLEX seat for free.

The draft card argues the opposite: every elite quarterback in the room
is kept, so there IS no replacement, and pick 8 is the last access to a
real superflex starter.

Both are internally consistent. They disagree about one fact —
**whether a startable quarterback is still there when your turn comes
back around** — and `lineup_value` says so itself at the bottom of its
own output: "It still assumes a static market — no other manager's run
on a position moves these ADPs."

A static market is exactly the wrong assumption for the position every
team in a superflex league still needs. So count it.

WHAT IT COUNTS

    supply   quarterbacks still on the board past each of your picks,
             projecting at or above the model's own QB replacement level
    demand   starting quarterback seats league-wide that nobody holds yet:
             the dedicated QB slots, plus SUPER_FLEX seats weighted by
             FLEX_SHARE (0.85 QB), minus quarterbacks already rostered

If supply comfortably exceeds demand at your later picks, waiting is free
and the turn plan is right. If it does not, "replacement QB" is a phantom
the simulation invented and the draft card is right.

This does not decide it for you. It prints the count both arguments are
assuming without checking.
"""

import sys

from battle_rhythm import paths

DEFAULT_SLOT = None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slot = None
    if "--slot" in sys.argv:
        slot = int(sys.argv[sys.argv.index("--slot") + 1])
    if not args:
        sys.exit("usage: python qb_supply.py <league id or slug> [--slot N]\n"
                 "  known: " + ", ".join(paths.leagues()))

    lid = paths.id_for(args[0]) or args[0]

    from battle_rhythm.draft_helper import board_data
    from battle_rhythm.roster_shape import slot_plan, FLEX_SHARE
    from battle_rhythm.sleeper_client import get, slot_picks

    d = board_data(lid, depth=400)
    lg, tbl, season = d["lg"], d["tbl"], d["season"]
    rp = lg.get("roster_positions") or []
    teams = lg.get("total_rosters") or lg.get("total_teams") or 12
    ded, flex, _bn = slot_plan(rp)

    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    print(f"\n== {lg.get('name')} — quarterback supply against demand")
    if not sflex:
        print("   Not a superflex league. One QB seat per team; the "
              "replacement-QB question\n   this script exists for does not "
              "arise here.")
        return 0

    repl = (d.get("replacement") or {}).get("QB")
    if not repl:
        sys.exit("board_data returned no QB replacement level — cannot set a "
                 "startable line.")
    print(f"   startable line: {repl:.0f} projected season points "
          f"(the model's own QB replacement level)")

    # ---------------- demand: seats nobody holds yet
    rosters = get(f"league/{lid}/rosters") or []
    held_qb = 0
    for r in rosters:
        for pid in (r.get("players") or []):
            if (tbl.get(str(pid)) or {}).get("position") == "QB":
                held_qb += 1

    dedicated_seats = ded.get("QB", 0) * teams
    sflex_seats = sum(FLEX_SHARE.get(s, {}).get("QB", 0.0) for s, _f in flex)
    sflex_seats *= teams
    seats = dedicated_seats + sflex_seats
    demand = max(0.0, seats - held_qb)

    print(f"\n   demand")
    print(f"     {dedicated_seats:.0f} dedicated QB seats "
          f"({ded.get('QB', 0)} x {teams} teams)")
    print(f"     {sflex_seats:.0f} more implied by flex "
          f"(FLEX_SHARE weights SUPER_FLEX at 0.85 QB)")
    print(f"     {held_qb} quarterbacks already rostered league-wide")
    print(f"     -> {demand:.1f} starting QB seats still to fill")
    print(f"     NOTE this is NET of quarterbacks already rostered. The gross "
          f"figure\n     keeper.py --board prints ({seats:.0f}) is seats, not "
          f"unmet need.")

    # ---------------- supply: startable QBs still on the board
    qbs = []
    for row in d["rows"]:
        m = row.get("meta") or {}
        if m.get("position") != "QB":
            continue
        adp = row.get("adp")
        pts = row.get("pts")
        if pts is None or pts < repl:
            continue
        qbs.append((adp if adp else 9999, pts, row))
    qbs.sort()
    print(f"\n   supply")
    print(f"     {len(qbs)} quarterbacks on the board at or above the "
          f"startable line")
    if not qbs:
        print("     Nothing to count. Every startable QB is already gone.")
        return 0

    # ---------------- the curve, at your picks
    # slot_picks is the ONE implementation of pick geometry, and it honours
    # the round-3 reversal that LG03-LG05 uses and the emoji league does
    # not (lineup_value.snake_picks delegates here for the same reason:
    # "Three copies is how all three ended up wrong").
    draft = d.get("draft") or {}
    dset = draft.get("settings") or {}
    rounds = dset.get("rounds") or 10
    reversal = dset.get("reversal_round") or 0
    picks = []
    if slot:
        try:
            picks = slot_picks(slot, rounds, teams, reversal)
        except Exception:
            picks = []
    if not picks:
        sys.exit("no --slot given and none inferred. Pass --slot N "
                 "(lineup_value prints yours).")
    if reversal:
        print(f"\n   pick geometry: snake with a REVERSAL at round "
              f"{reversal} — round {reversal} repeats\n   round "
              f"{reversal - 1}'s order, so these are not plain-snake numbers.")

    print(f"\n   {'your pick':>10s} {'startable QBs left':>20s} "
          f"{'seats still to fill':>21s}  verdict")
    print("   " + "-" * 74)
    for n in picks[:8]:
        left = sum(1 for adp, _p, _r in qbs if adp > n)
        # every seat filled before your pick is one less competitor, but we
        # cannot know who the room takes; demand is reported flat and the
        # comparison is deliberately the pessimistic one.
        # Print and compare the SAME number. The first version showed
        # demand rounded to 2 and compared against 2.2, so a row reading
        # "2 left, 2 seats" was labelled SHORT. That is the exact defect
        # this whole session has been chasing, in the tool built to catch it.
        if left >= demand + 3:
            v = "deep — waiting is free"
        elif left >= demand:
            v = "tight — one run empties it"
        elif left >= 1:
            v = "THIN — fewer left than seats, but not zero"
        else:
            v = "GONE — no startable QB survives this pick"
        print(f"   {n:>10d} {left:>20d} {demand:>21.1f}  {v}")

    print(f"\n   YOUR need is not the league's. Subtract the quarterbacks "
          f"you already\n   hold and start from there — the seats column is "
          f"league-wide.")
    print(f"\n   Caveat this cannot fix: ADP is a distribution, not a "
          f"deadline, and this\n   counts the room's demand as if nobody has "
          f"drafted yet. It is the floor of\n   the argument, not the whole "
          f"of it.")

    n = 12
    print(f"\n   the {n} startable QBs closest to gone:")
    print(f"     {'adp':>6s}  {'proj':>6s}  player")
    for adp, pts, row in qbs[:n]:
        nm = row.get("name") or row.get("pid")
        a = "—" if adp == 9999 else f"{adp:.0f}"
        print(f"     {a:>6s}  {pts:>6.0f}  {nm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
