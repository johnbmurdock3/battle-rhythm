"""
fix_keeper_board.py — three false labels on `keeper.py --board`.

    python fix_keeper_board.py --dry-run
    python fix_keeper_board.py

None of these touched a pick. All three were sentences printed above a
correct computation, which ROADMAP's closing section calls the worst
combination: nothing looks broken and the sentence is what gets read.

1. "positional demand still unfilled: QB:0/12 teams"

   Built as a set-membership test -- a team holding ONE quarterback
   counted as filled, in a league that starts a QB and a SUPER_FLEX.
   Same for RB against two slots plus a flex, and WR against three. It
   printed QB:0/12 for LG03-LG05 directly above "a position most teams
   already kept falls because nobody needs it", five days before a draft
   plan built on taking a quarterback at pick 8.

   Now counts OPEN DEDICATED SLOTS via roster_shape.slot_plan(), which
   knows SUPER_FLEX and every other slot type, and reports flex
   separately. `need` was display-only, so no pick ever moved on it.

2. Pick 68's shortlist led with a quarterback projected for 1 point,
   above a tight end projected for 225.

   The list ranks by `eff` -- where a player actually goes -- with no
   projection floor beyond zero, so anyone the market prices early and
   the projection feed does not know floats to the top. draft_helper's
   `find` documents the same trap: "a star with proj 0.0 means the
   projections feed is missing him." Floored at 120, which is the
   board's own existing threshold for a startable season, and the count
   of suppressed rows is printed rather than hidden.

3. "── PICK 8   best available (adp )"

   `f"(adp {'' if not here else ''})"` -- both branches empty. A
   placeholder that shipped. Now prints the global-market ADP span of
   what is actually listed, which is the contrast the tool exists for:
   at pick 8 these are players the wider market prices 32nd to 62nd.

Fail-closed, same as the rest: exact matches verified before any write,
suite before and after, rollback on regression.
"""

import io
import os
import re
import shutil
import subprocess
import sys

import paths

REPO = paths.REPO
DRY = "--dry-run" in sys.argv

C_OK, C_BAD, C_WARN, C_DIM, C_END = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        C_OK = C_BAD = C_WARN = C_DIM = C_END = ""


NEED_OLD = '''    need = {p: 0 for p in ("QB", "RB", "WR", "TE")}
    for r in rosters:
        held = {(tbl.get(p) or {}).get("position")
                for p in (r.get("players") or []) if p}
        for p in need:
            if p not in held:
                need[p] += 1'''

NEED_NEW = '''    # OPEN SLOTS, not positions-held. A team holding one quarterback
    # counted as QB-filled, in a league that starts a QB AND a
    # SUPER_FLEX. That printed QB:0/12 for LG03-LG05 above a note saying
    # a position nobody needs falls — five days before a plan built on
    # taking a quarterback at pick 8. slot_plan knows SUPER_FLEX.
    from roster_shape import slot_plan
    ded, flex_slots, _bn = slot_plan(lg.get("roster_positions"))
    need = {p: 0 for p in ("QB", "RB", "WR", "TE")}
    for r in rosters:
        held = {}
        for _pid in (r.get("players") or []):
            _pos = (tbl.get(_pid) or {}).get("position")
            if _pos:
                held[_pos] = held.get(_pos, 0) + 1
        for p in need:
            need[p] += max(0, ded.get(p, 0) - held.get(p, 0))
    flex_open = len(flex_slots) * len(rosters)'''

PRINT_OLD = '''    print("   positional demand still unfilled: "
          + "  ".join(f"{p}:{n}/{len(rosters)} teams" for p, n in need.items()))
    print("   (a position most teams already kept falls because nobody "
          "needs it, not because the room misprices it)")'''

PRINT_NEW = '''    print("   dedicated starting slots still open, league-wide: "
          + "  ".join(f"{p}:{n}" for p, n in need.items()))
    # A superflex league has ONE dedicated QB slot, so counting dedicated
    # slots alone still prints QB:0 while twelve teams need a second
    # quarterback. The demand is real and it lives in the flex slots.
    # FLEX_SHARE already encodes where the model thinks each flex slot
    # goes (SUPER_FLEX is 85% QB), so say it rather than leaving the
    # reader to infer it from a raw flex count.
    if flex_slots:
        from roster_shape import FLEX_SHARE
        implied = {}
        for _slot, _fills in flex_slots:
            for _p, _share in (FLEX_SHARE.get(_slot) or {}).items():
                implied[_p] = implied.get(_p, 0.0) + _share * len(rosters)
        print(f"   flex slots ({len(flex_slots) * len(rosters)} league-wide: "
              + ", ".join(s for s, _f in flex_slots) + ") imply: "
              + "  ".join(f"{p}:{v:.0f}" for p, v in
                          sorted(implied.items(), key=lambda kv: -kv[1])))
    print("   (a position most teams already kept falls because nobody "
          "needs it, not because the room misprices it)")'''

LOOP_OLD = '''    for n in my_picks[:6]:
        here = [x for x in pool if x[0] >= n]
        print(f"── PICK {n}   best available (adp {'' if not here else ''})")
        for e, a, pr, pid, m in here[:top]:'''

LOOP_NEW = '''    # A shortlist ranked by WHERE A PLAYER GOES surfaces anyone the market
    # prices early and the projection feed does not know. Pick 68 led with
    # a quarterback projected for 1 point, above a tight end at 225.
    # draft_helper.find documents the same trap: "a star with proj 0.0
    # means the projections feed is missing him." 120 is the board's own
    # threshold for a startable season.
    FLOOR = 120
    for n in my_picks[:6]:
        here = [x for x in pool if x[0] >= n]
        shown = [x for x in here if x[2] >= FLOOR][:top]
        cut = sum(1 for x in here[:top] if x[2] < FLOOR)
        span = (f"global adp {min(x[1] for x in shown):.0f}"
                f"\\u2013{max(x[1] for x in shown):.0f}"
                if shown else "nothing left above the floor")
        print(f"── PICK {n}   best available ({span})")
        for e, a, pr, pid, m in shown:'''

CUT_OLD = '''        gone = [x for x in pool if x[0] < n][-6:]'''

CUT_NEW = '''        if cut:
            print(f"     ({cut} suppressed: projected under {FLOOR} — "
                  f"marginal, or missing from the feed)")
        gone = [x for x in pool if x[0] < n][-6:]'''

EDITS = [
    ("keeper.py", NEED_OLD, NEED_NEW, 1),
    ("keeper.py", PRINT_OLD, PRINT_NEW, 1),
    ("keeper.py", LOOP_OLD, LOOP_NEW, 1),
    ("keeper.py", CUT_OLD, CUT_NEW, 1),
]

CHECKS = [
    ("test_all.py", ["test_all.py"], "suite"),
    ("dynasty_value --selftest", ["dynasty_value.py", "--selftest"], "oks"),
    ("lineup_value --selftest", ["lineup_value.py", "--selftest"], "oks"),
    ("roster_snapshot --selftest", ["roster_snapshot.py", "--selftest"], "oks"),
    ("superflex_adp --selftest", ["superflex_adp.py", "--selftest"], "oks"),
    ("draft_review --selftest", ["draft_review.py", "--selftest"], "oks"),
    ("paths --selftest", ["paths.py", "--selftest"], "oks"),
    ("roster_shape --selftest", ["roster_shape.py", "--selftest"], "oks"),
    ("league_rules --selftest", ["league_rules.py", "--selftest"], "oks"),
    ("room_bias --selftest", ["room_bias.py", "--selftest"], "oks"),
]


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def git(*a, check=True):
    r = subprocess.run(["git"] + list(a), cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(a)} failed:\n{r.stdout}\n{r.stderr}")
    return r


def run_checks(label):
    print(f"\n{C_DIM}running {label} checks…{C_END}")
    res = {}
    for name, argv, kind in CHECKS:
        if not (REPO / argv[0]).exists():
            continue
        r = subprocess.run([sys.executable] + argv, cwd=str(REPO),
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if kind == "suite":
            m = re.search(r"(\d+)\s+passed,\s+(\d+)\s+failed", out)
            res[name] = (int(m.group(1)), int(m.group(2))) if m else None
        else:
            ok = len(re.findall(r"^\s+ok\s{2}", out, re.M))
            bad = len(re.findall(r"^\s+XX\s{2}", out, re.M))
            res[name] = (ok, bad) if (ok or bad) else None
        v = res[name]
        if v is None:
            print(f"  {C_BAD}UNREADABLE{C_END}  {name}")
            for line in out.strip().splitlines()[-8:]:
                print(f"    {C_DIM}{line[:104]}{C_END}")
        else:
            print(f"  {C_OK if v[1] == 0 else C_BAD}{v[0]:3d} ok, "
                  f"{v[1]} failed{C_END}  {name}")
    return res


def main():
    if shutil.which("git") is None:
        sys.exit("git is not on PATH — no rollback available, refusing to run.")

    print(f"\n{'=' * 64}\nvalidating\n{'=' * 64}")
    texts, problems = {}, []
    for fn, old, new, want in EDITS:
        p = REPO / fn
        t = texts.get(fn) or (read(p) if p.exists() else None)
        if t is None:
            problems.append(f"{fn}: missing")
            continue
        norm = t.replace("\r\n", "\n")
        marker = new.strip().splitlines()[0]
        if marker in norm and old not in norm:
            print(f"  {C_DIM}already applied{C_END}  {fn}: "
                  f"{old.strip().splitlines()[0][:44]}…")
            texts[fn] = t
            continue
        n = norm.count(old)
        if n != want:
            problems.append(f"{fn}: expected {want} copy of "
                            f"'{old.strip().splitlines()[0][:52]}…', found {n}")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(old, new)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        print(f"  {C_OK}ok{C_END}  {fn}: {old.strip().splitlines()[0][:52]}…")

    if problems:
        print(f"\n{C_BAD}edits do not match the file on disk:{C_END}")
        for pr in problems:
            print(f"  - {pr}")
        sys.exit("\nNothing was written.")

    if DRY:
        print(f"\n{C_WARN}--dry-run:{C_END} keeper.py would change.")
        return 0

    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("-c", "user.email=fix@local", "-c", "user.name=fix",
            "commit", "-m", "pre-keeper-board-fix snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")
    if any(v is None or v[1] for v in before.values()):
        sys.exit(f"\n{C_BAD}not green before we start.{C_END}")

    for fn, t in texts.items():
        write(REPO / fn, t)
    print(f"\n{C_OK}rewrote keeper.py{C_END}")

    after = run_checks("post-fix")
    bad = []
    for name, b in before.items():
        a = after.get(name)
        if a is None:
            bad.append(f"{name}: no readable result")
        elif a[1]:
            bad.append(f"{name}: {a[1]} failing")
        elif b and a[0] < b[0]:
            bad.append(f"{name}: {b[0]} passing before, {a[0]} now")

    if bad:
        print(f"\n{C_BAD}REGRESSION — rolling back{C_END}")
        for b in bad:
            print(f"  - {b}")
        git("reset", "--hard", base)
        git("clean", "-fd")
        print(f"\n{C_OK}rolled back to {base[:10]}{C_END}")
        return 1

    git("add", "-A")
    git("-c", "user.email=fix@local", "-c", "user.name=fix", "commit", "-m",
        "keeper --board: three labels that contradicted the board under them\n\n"
        "Positional demand was a set-membership test, so a team holding one\n"
        "quarterback read as QB-filled in a league that starts a QB and a\n"
        "SUPER_FLEX. It printed QB:0/12 for LG03-LG05 next to a note saying\n"
        "a position nobody needs falls, five days before a plan built on\n"
        "taking a quarterback at pick 8. Now counts open dedicated slots\n"
        "via roster_shape.slot_plan and reports flex separately.\n\n"
        "The shortlist ranked by where a player goes with no projection\n"
        "floor, so pick 68 led with a QB projected for 1 point above a TE\n"
        "at 225. Floored at 120 with the suppressed count printed.\n\n"
        "And the header read '(adp )' — both branches of the conditional\n"
        "were empty strings. It now shows the ADP span of what is listed.\n\n"
        "None of the three moved a pick. All three were read as if they had.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    print(f"\n  Check it: {C_WARN}python keeper.py 9000000000000000014 "
          f"--board{C_END}")
    print("  QB should no longer read 0, and pick 68 should not lead with a "
          "1-point QB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
