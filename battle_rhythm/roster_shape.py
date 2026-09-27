"""
roster_shape.py — what a league's roster IS, defined once.

Before 8/13 this lived in five places. FLEX_SHARE was byte-identical in
draft_review, roster_snapshot and weekly. FLEX_FILL was byte-identical in
dynasty_value and roster_snapshot. The same nine-position tuple went by
two names, DEDICATED_SLOTS and DEDICATED. slot_plan() was written twice
with the same logic and a cosmetic difference (defaultdict vs dict).

None of those copies had drifted yet, which is the only reason this was
housekeeping rather than a bug hunt. The ADP-key branch next door had
seven copies and two of them HAD drifted, inside one file.

Stdlib only — no project imports at all, so anything can import this
without a cycle.

    python roster_shape.py --selftest
"""

# Which real positions can fill each flex-ish slot.
FLEX_FILL = {
    "FLEX": ("RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
    "REC_FLEX": ("WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    "IDP_FLEX": ("DL", "LB", "DB"),
}

# How a flex slot's demand is expected to split across positions. Used to
# spread replacement-level demand, not to decide eligibility — FLEX_FILL
# does that.
FLEX_SHARE = {
    "FLEX": {"RB": .40, "WR": .45, "TE": .15},
    "WRRB_FLEX": {"RB": .5, "WR": .5},
    "REC_FLEX": {"WR": .8, "TE": .2},
    "SUPER_FLEX": {"QB": .85, "RB": .05, "WR": .10},
}

# Slots that name exactly one position.
DEDICATED = ("QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB")

# dynasty_value used this name. Kept so nothing has to change twice.
DEDICATED_SLOTS = DEDICATED




def slot_plan(roster_positions):
    """(dedicated {pos: n}, flex [(slot, fills)], bench_n) from the league.

    TAXI and IR are neither starting slots nor bench: a taxi player does
    not consume an active roster spot, and counting them as bench
    overstates capacity. See CLAUDE.md on the one-year rookie redshirt.
    """
    ded, flex, bench = {}, [], 0
    for s in roster_positions or []:
        if s == "BN":
            bench += 1
        elif s in ("TAXI", "IR"):
            continue
        elif s in DEDICATED:
            ded[s] = ded.get(s, 0) + 1
        elif s in FLEX_FILL:
            flex.append((s, FLEX_FILL[s]))
    return ded, flex, bench


def selftest():
    checks = []

    def ck(n, c):
        checks.append((n, bool(c)))

    ck("FLEX_SHARE and FLEX_FILL name the same slots",
       set(FLEX_SHARE) <= set(FLEX_FILL))
    for slot, share in FLEX_SHARE.items():
        ck(f"{slot} shares sum to 1.0", abs(sum(share.values()) - 1.0) < 1e-9)
        ck(f"{slot} shares only name positions it can actually fill",
           set(share) <= set(FLEX_FILL[slot]))
    ck("DEDICATED_SLOTS is DEDICATED, not a second copy",
       DEDICATED_SLOTS is DEDICATED)
    ck("no slot is both dedicated and flex",
       not (set(DEDICATED) & set(FLEX_FILL)))

    # a real league: LG03-LG05 — superflex, 11 starters, deep bench
    hy = (["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
          + ["BN"] * 11 + ["TAXI"] * 3)
    ded, flex, bench = slot_plan(hy)
    ck("LG03-LG05 dedicated counts", ded == {"QB": 1, "RB": 2, "WR": 3,
                                             "TE": 1})
    ck("LG03-LG05 flex slots", [s for s, _ in flex] == ["FLEX", "SUPER_FLEX"])
    ck("LG03-LG05 bench is 11", bench == 11)
    ck("taxi seats are not bench", bench == 11)

    # LG02 — the only league carrying both K and DEF
    bb = (["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
          + ["BN"] * 4)
    ded, flex, bench = slot_plan(bb)
    ck("K and DEF are dedicated slots, not ignored",
       ded.get("K") == 1 and ded.get("DEF") == 1)
    ck("LG02 bench is 4", bench == 4)

    # IDP, built and tested but with no league yet
    idp = ["QB", "RB", "WR", "TE", "DL", "LB", "DB", "IDP_FLEX", "BN", "IR"]
    ded, flex, bench = slot_plan(idp)
    ck("IDP positions are dedicated",
       all(ded.get(p) == 1 for p in ("DL", "LB", "DB")))
    ck("IDP_FLEX is a flex slot", [s for s, _ in flex] == ["IDP_FLEX"])
    ck("IR is neither a slot nor bench", bench == 1)

    ck("an empty roster is empty, not an error", slot_plan([]) == ({}, [], 0))
    ck("None is empty too", slot_plan(None) == ({}, [], 0))
    ck("an unknown slot name is dropped, not counted",
       slot_plan(["QB", "WHATEVER"])[0] == {"QB": 1})

    for n, c in checks:
        print(f"  {'ok' if c else 'XX'}  {n}")
    ok = all(c for _, c in checks)
    print(f"\nselftest {'PASSED' if ok else 'FAILED'}  "
          f"({sum(1 for _, c in checks if c)}/{len(checks)})")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
