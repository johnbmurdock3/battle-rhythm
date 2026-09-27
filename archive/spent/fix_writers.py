"""
fix_writers.py — re-anchor the writer that came loose, and sweep what it left.

    python fix_writers.py --dry-run
    python fix_writers.py

WHAT HAPPENED. migrate.py repointed three cwd-relative writers at
paths.out() on the morning of 8/13. By that evening draft_helper's
`sheet` function had been rewritten and line 711 was back to

    out = pathlib.Path(f"cheatsheet_{lg['name']...}.txt")

so `python smoke.py` dropped `cheatsheet_Hybrid_12.txt` in the repo root
and the stale copy in out/lg05/ sat there looking current. smoke's
root-drift check caught it on its first enforced run, and the commit
right after it had already tracked the stray file.

The convention lived in a comment. lineup_value:1484 says it plainly:
"Rather than trust a comment not to be ignored, walk report() and assert
that nothing build() hands over is ever reassigned inside it." So this
fix ships with `paths.cwd_writes()`, a source scan wired into
`paths.py --selftest`, which fails on any path built relative to the
current directory. A comment did not hold for six hours. A check will.

Fail-closed: the edit is an exact string match verified before anything
is written, the check suite runs before and after, any regression rolls
back with git.
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

OLD = ('    out = pathlib.Path(f"cheatsheet_'
       '{lg[\'name\'].strip().replace(\' \', \'_\')}.txt")')
NEW = ('    # out/<slug>/cheatsheet.txt. Keyed on the id, never the name:\n'
       '    # both Hybrids normalize to the same string. paths.py --selftest\n'
       '    # fails if this line ever goes back to a bare relative path.\n'
       '    out = _paths.league_out(league_id, "cheatsheet.txt")')

CHECKS = [
    ("test_all.py", ["test_all.py"], "suite"),
    ("dynasty_value --selftest", ["dynasty_value.py", "--selftest"], "oks"),
    ("lineup_value --selftest", ["lineup_value.py", "--selftest"], "oks"),
    ("roster_snapshot --selftest", ["roster_snapshot.py", "--selftest"], "oks"),
    ("superflex_adp --selftest", ["superflex_adp.py", "--selftest"], "oks"),
    ("draft_review --selftest", ["draft_review.py", "--selftest"], "oks"),
    ("roster_shape --selftest", ["roster_shape.py", "--selftest"], "oks"),
    ("league_rules --selftest", ["league_rules.py", "--selftest"], "oks"),
]


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
        print(f"  {C_BAD}UNREADABLE{C_END}  {name}" if v is None else
              f"  {C_OK if v[1] == 0 else C_BAD}{v[0]:3d} ok, "
              f"{v[1]} failed{C_END}  {name}")
    return res


def strays():
    """Renders sitting at the repo root, with where each belongs."""
    out = []
    for p in sorted(REPO.glob("cheatsheet_*.txt")):
        frag = p.stem[len("cheatsheet_"):].replace("_", " ")
        lid = paths.id_for(frag)
        out.append((p, paths.OUT / paths.slug_for(lid) / "cheatsheet.txt"
                    if lid else paths.OUT / p.name))
    for p in sorted(REPO.glob("research_queue_*.json")):
        frag = p.stem[len("research_queue_"):].replace("_", " ")
        lid = paths.id_for(frag)
        out.append((p, paths.OUT / paths.slug_for(lid) / "research_queue.json"
                    if lid else paths.OUT / p.name))
    p = REPO / "refresh_list.json"
    if p.exists():
        out.append((p, paths.OUT / "refresh_list.json"))
    return out


def main():
    if shutil.which("git") is None:
        sys.exit("git is not on PATH — no rollback available, refusing to run.")

    print(f"\n{'=' * 62}\nthe writer\n{'=' * 62}")
    f = REPO / "draft_helper.py"
    src = io.open(f, encoding="utf-8", newline="").read()
    norm = src.replace("\r\n", "\n")
    already = "league_out(league_id" in norm and OLD not in norm
    if already:
        print(f"  {C_DIM}already anchored{C_END}  draft_helper.py")
        new_src = None
    elif norm.count(OLD) != 1:
        sys.exit(f"{C_BAD}ABORT{C_END} draft_helper.py: expected 1 copy of the "
                 f"cheatsheet line, found {norm.count(OLD)}. Nothing written.")
    else:
        print(f"  {C_OK}ok{C_END}  draft_helper.py: cheatsheet write -> "
              f"paths.league_out()")
        t = norm.replace(OLD, NEW)
        new_src = t.replace("\n", "\r\n") if "\r\n" in src else t

    st = strays()
    print(f"\n{'=' * 62}\nstray renders at the root\n{'=' * 62}")
    if not st:
        print("  none")
    for p, dest in st:
        print(f"  {p.name} -> {dest.relative_to(REPO)}")

    lint = paths.cwd_writes()
    print(f"\n{'=' * 62}\nsource scan\n{'=' * 62}")
    if lint:
        for fn, ln, txt in lint:
            print(f"  {C_WARN}{fn}:{ln}{C_END}  {txt}")
    else:
        print("  clean")

    if DRY:
        print(f"\n{C_WARN}--dry-run: nothing written.{C_END}")
        return 0

    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        git("add", "-A")
        git("-c", "user.email=fix@local", "-c", "user.name=fix",
            "commit", "-m", "pre-fix snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")

    if new_src is not None:
        io.open(f, "w", encoding="utf-8", newline="").write(new_src)
        print(f"\n{C_OK}rewrote draft_helper.py{C_END}")

    for p, dest in st:
        # untrack first: the stray was committed, and .gitignore does not
        # apply to files already in the index.
        git("rm", "--cached", "-q", str(p.relative_to(REPO)), check=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest))
        print(f"  moved {p.name} -> {dest.relative_to(REPO)}")

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

    lint_after = paths.cwd_writes()
    if lint_after:
        bad.append(f"{len(lint_after)} cwd-relative write(s) still present")

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
        "writers: re-anchor the cheatsheet write, and make the rule checkable\n\n"
        "draft_helper's sheet function was rewritten after the 8/13\n"
        "migration and line 711 went back to a bare relative path, so\n"
        "smoke.py dropped cheatsheet_Hybrid_12.txt in the repo root and\n"
        "the commit after it tracked the file.\n\n"
        "paths.cwd_writes() now scans every module for a path built\n"
        "relative to the current directory, and paths.py --selftest fails\n"
        "on any hit. The convention was a comment for six hours and did\n"
        "not survive one rewrite.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
