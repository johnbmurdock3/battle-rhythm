"""
add_drop_flag.py — `lineup_value --drop "<name>"`, so an intended cut is testable.

    python add_drop_flag.py --dry-run
    python add_drop_flag.py

WHY. HANDOFF says Jalen Milroe and Brashard Smith get cut after the
draft. `lineup_value` reads the live roster, so it prices every pick
against a lineup that still holds them. floored_roster already stops
that from inflating a quarterback's value — Milroe's 1 point is floored
to replacement before anything is measured — but "what does my board
look like if I cut him" is still a question you cannot ask, and it is
one you will have at every draft.

    python lineup_value.py 9000000000000000014 --slot 8 --drop "milroe"
    python lineup_value.py 9000000000000000014 --slot 8 --drop "milroe,smith"

Names are matched with draft_helper.player_hits, the same resolver `find`
uses, so a fragment or a "name pos" hint both work. Anyone dropped is
named in the output — an invisible roster change would be worse than no
flag at all.

Fail-closed: exact match verified before writing, suite before and after,
rollback on regression.
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


BUILD_SIG_OLD = ("def build(fragment=None, sims=DEFAULT_SIMS, pos=None, "
                 "top=40, include_all=False):")
BUILD_SIG_NEW = ("def build(fragment=None, sims=DEFAULT_SIMS, pos=None, "
                 "top=40, include_all=False,\n          drop=None):")

ROSTER_OLD = '''    roster = [mk(p) for p in mine
              if p not in redshirt
              and (tbl.get(p) or {}).get("position") in live]
    roster = [p for p in roster if p["proj"] > 0]'''

ROSTER_NEW = '''    # --drop: price the roster you INTEND to draft, not the one you hold.
    # HANDOFF has Milroe and Brashard Smith as post-draft cuts; without
    # this the plan is built against bodies you are about to release.
    # Every hit is named in the output — a silent roster change would be
    # worse than no flag.
    dropped_names = []
    if drop:
        from draft_helper import player_hits
        _mine = set(mine)
        for q in ([drop] if isinstance(drop, str) else list(drop)):
            for _q in str(q).split(","):
                _q = _q.strip()
                if not _q:
                    continue
                hits, _hint = player_hits(tbl, _q)
                hit = [h for h in hits if h[0] in _mine]
                if not hit:
                    print(f"   --drop {_q!r}: nobody on your roster matches. "
                          f"Ignored.")
                    continue
                for pid, m in hit:
                    _mine.discard(pid)
                    dropped_names.append(m.get("full_name") or pid)
        # STAYS A SET. line 667 does `kept | mine | gone`; a list there
        # is a TypeError, and no selftest would catch it — build() needs
        # the live API, so all 99 of them and all 33 in test_all avoid it.
        mine = _mine
    roster = [mk(p) for p in mine
              if p not in redshirt
              and (tbl.get(p) or {}).get("position") in live]
    roster = [p for p in roster if p["proj"] > 0]'''

MARKET_OLD = '''    return (lg, rp, roster, rows, base, taxi, tbl, rounds,
            teams, top, market)'''

MARKET_NEW = '''    market["dropped"] = dropped_names
    return (lg, rp, roster, rows, base, taxi, tbl, rounds,
            teams, top, market)'''

REPORT_SIG_OLD = '''def report(fragment=None, sims=DEFAULT_SIMS, pos=None, top=40,
           include_all=False, slot=None, shave=None):
    (lg, rp, roster, rows, base, taxi, tbl, rounds, teams, top,
     market) = build(fragment, sims, pos, top, include_all)'''

REPORT_SIG_NEW = '''def report(fragment=None, sims=DEFAULT_SIMS, pos=None, top=40,
           include_all=False, slot=None, shave=None, drop=None):
    (lg, rp, roster, rows, base, taxi, tbl, rounds, teams, top,
     market) = build(fragment, sims, pos, top, include_all, drop)'''

BANNER_OLD = '''    if market.get("floored"):'''

BANNER_NEW = '''    if market.get("dropped"):
        print(f"   --drop: priced WITHOUT {', '.join(market['dropped'])}. "
              f"This is a hypothetical\\n   roster; the league still has "
              f"them on your team.")
    if market.get("floored"):'''

MAIN_OLD = '''    TAKES_VALUE = ("--pos", "--top", "--sims", "--slot",
                   "--shave")'''

MAIN_NEW = '''    TAKES_VALUE = ("--pos", "--top", "--sims", "--slot",
                   "--shave", "--drop")'''

CALL_OLD = '''    report(frag, sims=opt("--sims", DEFAULT_SIMS, int),
           pos=opt("--pos"), top=opt("--top", 40, int),
           include_all="--all" in a, slot=opt("--slot", None, int),
           shave=opt("--shave", None, int))'''

CALL_NEW = '''    report(frag, sims=opt("--sims", DEFAULT_SIMS, int),
           pos=opt("--pos"), top=opt("--top", 40, int),
           include_all="--all" in a, slot=opt("--slot", None, int),
           shave=opt("--shave", None, int), drop=opt("--drop"))'''

EDITS = [
    ("lineup_value.py", BUILD_SIG_OLD, BUILD_SIG_NEW, 1),
    ("lineup_value.py", ROSTER_OLD, ROSTER_NEW, 1),
    ("lineup_value.py", MARKET_OLD, MARKET_NEW, 1),
    ("lineup_value.py", REPORT_SIG_OLD, REPORT_SIG_NEW, 1),
    ("lineup_value.py", BANNER_OLD, BANNER_NEW, 1),
    ("lineup_value.py", MAIN_OLD, MAIN_NEW, 1),
    ("lineup_value.py", CALL_OLD, CALL_NEW, 1),
]

CHECKS = [
    ("test_all.py", ["test_all.py"], "suite"),
    ("lineup_value --selftest", ["lineup_value.py", "--selftest"], "oks"),
    ("dynasty_value --selftest", ["dynasty_value.py", "--selftest"], "oks"),
    ("roster_snapshot --selftest", ["roster_snapshot.py", "--selftest"], "oks"),
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
        sys.exit("git is not on PATH — refusing to run without a rollback.")

    print(f"\n{'=' * 64}\nvalidating\n{'=' * 64}")
    texts, problems = {}, []
    for fn, old, new, want in EDITS:
        p = REPO / fn
        t = texts.get(fn) or (read(p) if p.exists() else None)
        if t is None:
            problems.append(f"{fn}: missing")
            continue
        norm = t.replace("\r\n", "\n")
        if "--drop" in norm and old not in norm:
            print(f"  {C_DIM}already applied{C_END}  "
                  f"{old.strip().splitlines()[0][:48]}…")
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
        print(f"  {C_OK}ok{C_END}  {old.strip().splitlines()[0][:52]}…")

    if problems:
        print(f"\n{C_BAD}edits do not match the file on disk:{C_END}")
        for pr in problems:
            print(f"  - {pr}")
        sys.exit("\nNothing was written.")

    if DRY:
        print(f"\n{C_WARN}--dry-run:{C_END} lineup_value.py would change.")
        return 0

    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("-c", "user.email=fix@local", "-c", "user.name=fix",
            "commit", "-m", "pre-drop-flag snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")
    if any(v is None or v[1] for v in before.values()):
        sys.exit(f"\n{C_BAD}not green before we start.{C_END}")

    for fn, t in texts.items():
        write(REPO / fn, t)
    print(f"\n{C_OK}rewrote lineup_value.py{C_END}")

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
        "lineup_value: --drop, so an intended cut is testable\n\n"
        "HANDOFF has Milroe and Brashard Smith as post-draft cuts, and the\n"
        "plan was being priced against a roster that still holds them.\n"
        "floored_roster already prevents that from inflating a QB's value,\n"
        "but the hypothetical was not askable. Dropped players are named in\n"
        "the output; a silent roster change would be worse than no flag.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    print(f"\n  Try it: {C_WARN}python lineup_value.py 9000000000000000014 "
          f"--slot 8 --drop \"milroe\"{C_END}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
