"""
dedupe_shape.py — point the five copies of the roster geometry at one file.

    python dedupe_shape.py --dry-run
    python dedupe_shape.py

roster_shape.py was written on 8/13 and then imported by nothing, which
made it a SIXTH copy of FLEX_SHARE rather than a replacement for five.
Shipping a destination without doing the repointing is worse than not
shipping it. This does the repointing.

What moves:

    FLEX_SHARE   byte-identical in draft_review, roster_snapshot, weekly
    FLEX_FILL    byte-identical in dynasty_value, roster_snapshot
    DEDICATED    the same nine-position tuple under two names:
                 DEDICATED_SLOTS in dynasty_value, DEDICATED in
                 roster_snapshot
    slot_plan    written twice, same logic, defaultdict vs dict

Each module keeps re-exporting the names it exported before, so
`from dynasty_value import slot_plan` (lineup_value:85) still resolves.
Nothing outside these four files changes.

Fail-closed, same as migrate.py: every edit is an exact string match
verified before a byte is written, the check suite runs before and
after, and any regression rolls back with git.
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


FLEX_SHARE_BLOCK = '''FLEX_SHARE = {"FLEX": {"RB": .40, "WR": .45, "TE": .15},
              "WRRB_FLEX": {"RB": .5, "WR": .5},
              "REC_FLEX": {"WR": .8, "TE": .2},
              "SUPER_FLEX": {"QB": .85, "RB": .05, "WR": .10}}'''

FLEX_SHARE_IMPORT = ('# One definition, in roster_shape.py. This block was '
                     'byte-identical in\n# draft_review, roster_snapshot and '
                     'weekly.\nfrom roster_shape import FLEX_SHARE  '
                     '# noqa: E402,F401')

DV_BLOCK = '''FLEX_FILL = {
    "FLEX": ("RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
    "REC_FLEX": ("WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    "IDP_FLEX": ("DL", "LB", "DB"),
}
DEDICATED_SLOTS = ("QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB")


def slot_plan(roster_positions):
    """(dedicated {pos: n}, flex [(slot, fills)], bench_n) from the league."""
    ded, flex, bench = {}, [], 0
    for s in roster_positions or []:
        if s == "BN":
            bench += 1
        elif s in ("TAXI", "IR"):
            continue
        elif s in DEDICATED_SLOTS:
            ded[s] = ded.get(s, 0) + 1
        elif s in FLEX_FILL:
            flex.append((s, FLEX_FILL[s]))
    return ded, flex, bench'''

DV_IMPORT = ('# Roster geometry lives in roster_shape.py. Re-exported here so\n'
             '# `from dynasty_value import slot_plan` (lineup_value:85) still\n'
             '# resolves — the callers do not need to know it moved.\n'
             'from roster_shape import (FLEX_FILL, DEDICATED_SLOTS,  '
             '# noqa: E402,F401\n                          slot_plan)')

RS_BLOCK = '''FLEX_FILL = {
    "FLEX": ("RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
    "REC_FLEX": ("WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    "IDP_FLEX": ("DL", "LB", "DB"),
}
DEDICATED = ("QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB")


def slot_plan(roster_positions):
    """(dedicated {pos: n}, flex [(slot, fills)], bench_n) from the league."""
    ded, flex, bench = defaultdict(int), [], 0
    for s in roster_positions or []:
        if s == "BN":
            bench += 1
        elif s in ("TAXI", "IR"):
            continue
        elif s in DEDICATED:
            ded[s] += 1
        elif s in FLEX_FILL:
            flex.append((s, FLEX_FILL[s]))
    return dict(ded), flex, bench'''

RS_IMPORT = ('# Roster geometry lives in roster_shape.py. DEDICATED was this\n'
             '# file\'s name for the tuple dynasty_value called '
             'DEDICATED_SLOTS;\n# both now point at the same object.\n'
             'from roster_shape import (FLEX_FILL, DEDICATED,  '
             '# noqa: E402,F401\n                          slot_plan)')

EDITS = [
    ("dynasty_value.py", DV_BLOCK, DV_IMPORT, 1),
    ("roster_snapshot.py", RS_BLOCK, RS_IMPORT, 1),
    ("roster_snapshot.py", FLEX_SHARE_BLOCK, FLEX_SHARE_IMPORT, 1),
    ("draft_review.py", FLEX_SHARE_BLOCK, FLEX_SHARE_IMPORT, 1),
    ("weekly.py", FLEX_SHARE_BLOCK, FLEX_SHARE_IMPORT, 1),
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
]


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def git(*a, check=True):
    r = subprocess.run(["git"] + list(a), cwd=str(REPO),
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
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
            for line in out.strip().splitlines()[-6:]:
                print(f"    {C_DIM}{line[:100]}{C_END}")
        else:
            print(f"  {C_OK if v[1] == 0 else C_BAD}{v[0]:3d} ok, "
                  f"{v[1]} failed{C_END}  {name}")
    return res


def main():
    if shutil.which("git") is None:
        sys.exit("git is not on PATH — no rollback available, refusing to run.")

    print(f"\n{'=' * 62}\nvalidating {len(EDITS)} edits\n{'=' * 62}")
    texts, problems = {}, []
    for fn, old, new, want in EDITS:
        p = REPO / fn
        if not p.exists():
            problems.append(f"{fn}: missing")
            continue
        t = texts.get(fn, read(p))
        norm = t.replace("\r\n", "\n")
        if "from roster_shape import" in norm and old not in norm:
            print(f"  {C_DIM}already applied{C_END}  {fn}: "
                  f"{old.splitlines()[0][:44]}…")
            texts[fn] = t
            continue
        n = norm.count(old)
        if n != want:
            problems.append(f"{fn}: expected {want} copy of "
                            f"'{old.splitlines()[0][:48]}…', found {n}")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(old, new)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        print(f"  {C_OK}ok{C_END}  {fn}: {old.splitlines()[0][:48]}…")

    if problems:
        print(f"\n{C_BAD}edits do not match the files on disk:{C_END}")
        for p in problems:
            print(f"  - {p}")
        sys.exit("\nNothing was written. The geometry blocks have changed "
                 "since this script was written — re-derive them.")

    if DRY:
        print(f"\n{C_WARN}--dry-run: nothing written.{C_END} "
              f"{len(texts)} file(s) would change.")
        return 0

    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        print(f"\n{C_WARN}working tree is dirty — committing it as the "
              f"rollback point{C_END}")
        git("add", "-A")
        git("-c", "user.email=dedupe@local", "-c", "user.name=dedupe",
            "commit", "-m", "pre-dedupe snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")
    if any(v is None or v[1] for v in before.values()):
        sys.exit(f"\n{C_BAD}the repo is not green before we start. "
                 f"Fix that first.{C_END}")

    for fn, t in texts.items():
        write(REPO / fn, t)
    print(f"\n{C_OK}rewrote {len(texts)} module(s){C_END}")

    after = run_checks("post-dedupe")
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
    git("-c", "user.email=dedupe@local", "-c", "user.name=dedupe",
        "commit", "-m",
        "dedupe: roster geometry has one definition\n\n"
        "FLEX_SHARE was byte-identical in three modules, FLEX_FILL in two,\n"
        "the dedicated-slot tuple carried two names, and slot_plan was\n"
        "written twice. All five now import from roster_shape.py, which\n"
        "until this commit was imported by nothing and therefore a sixth\n"
        "copy rather than a replacement for five.\n\n"
        "Each module re-exports what it exported before, so callers such\n"
        "as lineup_value:85 are unchanged.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
