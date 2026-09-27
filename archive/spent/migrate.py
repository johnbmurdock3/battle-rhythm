"""
migrate.py — phases A through D of the scaffold, in one reversible step.

    python migrate.py --dry-run     # print the whole plan, change nothing
    python migrate.py               # do it

What it does, in order:

    A  git init (if needed) and commit the current state as a rollback point
       baseline: run the full check suite and record every count
    B  paths.py, plus 16 edits across 11 modules so writers stop scattering
    C  leagues/_index.json and the per-league folders
    D  sweep: data/, data/measured/, docs/, archive/, out/

Fail-closed at every step. Every edit is an exact string match verified
BEFORE anything is written; one mismatch aborts with nothing changed. After
the moves it re-runs the checks and compares them to the baseline — any
count lower than it started, or any outright failure, and it runs
`git reset --hard` back to the rollback point and tells you which check
broke.

A count that goes DOWN means a check was deleted rather than fixed. That is
HANDOFF's rule and this script enforces it.

What it deliberately does NOT touch:

    roster.md          stays at the repo root, stays tracked. CLAUDE.md has a
                       standing rule to regenerate and read it before any pick
                       recommendation. If the writer moved and a reader did
                       not, the failure is a silently stale roster — the 8/11
                       failure that cost three consecutive picks. It moves
                       after 8/18, with the rule text, in its own commit.
    the 19 .py files   sleeper_client has 17 importers and 22 cross-module
                       symbols; draft_helper 15 and 22. Packaging them is the
                       most expensive move in the repo and it waits until the
                       8/18 board is closed.
    mcp_server.py      Claude Desktop holds its absolute path in an external
                       config and needs a full quit to retest.
    config.json        stays at the root, where sleeper_client's docstring
                       says to put it. paths.data() finds it either way.
"""

import io
import os
import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent
DRY = "--dry-run" in sys.argv
NO_VERIFY = "--no-verify" in sys.argv


# ------------------------------------------------------------------ output

class C:
    OK, WARN, BAD, DIM, END = "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[0m"


if os.name == "nt" and not os.environ.get("WT_SESSION"):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        C.OK = C.WARN = C.BAD = C.DIM = C.END = ""


def say(msg=""):
    print(msg, flush=True)


def head(t):
    say(f"\n{'=' * 66}\n{t}\n{'=' * 66}")


def die(msg):
    say(f"\n{C.BAD}ABORT{C.END}  {msg}")
    sys.exit(1)


# --------------------------------------------------------------- file i/o

def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def git(*args, check=True):
    r = subprocess.run(["git"] + list(args), cwd=str(REPO),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r


# ------------------------------------------------------------- the checks

CHECKS = [
    ("test_all.py", ["test_all.py"], "suite"),
    ("dynasty_value --selftest", ["dynasty_value.py", "--selftest"], "oks"),
    ("lineup_value --selftest", ["lineup_value.py", "--selftest"], "oks"),
    ("roster_snapshot --selftest", ["roster_snapshot.py", "--selftest"], "oks"),
    ("superflex_adp --selftest", ["superflex_adp.py", "--selftest"], "oks"),
    ("draft_review --selftest", ["draft_review.py", "--selftest"], "oks"),
]

POST_ONLY = [("paths --selftest", ["paths.py", "--selftest"], "oks")]


def run_checks(which, label):
    """{name: (passed, failed)}. None as the pair means the command itself
    blew up, which is a failure, not a zero."""
    say(f"\n{C.DIM}running {label} checks…{C.END}")
    res = {}
    for name, argv, kind in which:
        if not (REPO / argv[0]).exists():
            say(f"  {C.WARN}skip{C.END}  {name}  (file not present)")
            continue
        try:
            r = subprocess.run([sys.executable] + argv, cwd=str(REPO),
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            res[name] = None
            say(f"  {C.BAD}TIMEOUT{C.END}  {name}")
            continue
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
            say(f"  {C.BAD}UNREADABLE{C.END}  {name}  (exit {r.returncode})")
            tail = "\n".join(out.strip().splitlines()[-6:])
            say(f"{C.DIM}{tail}{C.END}")
        else:
            colour = C.OK if v[1] == 0 else C.BAD
            say(f"  {colour}{v[0]:3d} ok, {v[1]} failed{C.END}  {name}")
    return res


def compare(base, post):
    """Returns a list of regression strings. Empty means clean."""
    bad = []
    for name, b in base.items():
        p = post.get(name)
        if p is None:
            bad.append(f"{name}: no longer produces a readable result")
            continue
        if b is None:
            continue
        if p[1] > 0:
            bad.append(f"{name}: {p[1]} failing check(s)")
        if p[0] < b[0]:
            bad.append(f"{name}: {b[0]} passing before, {p[0]} now "
                       f"— a check was deleted, not fixed")
    for name, p in post.items():
        if p is not None and p[1] > 0 and name not in base:
            bad.append(f"{name}: {p[1]} failing check(s)")
        if p is None and name not in base:
            bad.append(f"{name}: produced no readable result")
    return bad


# ------------------------------------------------------------ the B edits

IMPORT_LINE = "import paths as _paths\n"
IMPORT_AFTER = "import pathlib\n"

NEEDS_IMPORT = ["sleeper_client.py", "dynasty_value.py", "keeper.py",
                "dashboard.py", "roster_snapshot.py", "room_bias.py",
                "dossier.py", "research_queue.py", "draft_helper.py",
                "lineup_value.py"]

# (file, old, new, expected occurrences)
EDITS = [
    ("sleeper_client.py",
     '    cfg = pathlib.Path(__file__).parent / "config.json"',
     '    cfg = _paths.data("config.json")', 1),

    ("sleeper_client.py",
     '            f = _pl.Path(path) if path else (_pl.Path(__file__).parent\n'
     '                                             / "byes.json")',
     '            f = _pl.Path(path) if path else _paths.data("byes.json")', 1),

    ("dynasty_value.py",
     '    P = json.loads((HERE / "ages.json").read_text())',
     '    P = json.loads(_paths.data("ages.json").read_text())', 1),

    ("keeper.py",
     '        _rules = _json.loads((pathlib.Path(__file__).parent /\n'
     '                              "keepers.json").read_text())',
     '        _rules = _json.loads(_paths.data("keepers.json").read_text())', 1),

    ("dashboard.py",
     'OUT = HERE / "dashboard.html"',
     'OUT = _paths.out("dashboard.html")', 1),

    ("dashboard.py",
     '    p = HERE / name',
     '    p = _paths.data(name)', 1),

    ("roster_snapshot.py",
     '    p = HERE / "keepers.json"',
     '    p = _paths.data("keepers.json")', 1),

    ("draft_review.py",
     '        keeper = bool(json.loads(\n'
     '            (__import__("pathlib").Path(__file__).parent /\n'
     '             "keepers.json").read_text()).get(str(lid), {}).get("keeper"))',
     '        keeper = bool(json.loads(__import__("paths").data("keepers.json")\n'
     '                      .read_text()).get(str(lid), {}).get("keeper"))', 1),

    ("room_bias.py",
     'OUT = HERE / "room_bias.json"',
     'OUT = _paths.measured("room_bias.json")', 1),

    ("dossier.py",
     'STORE = HERE / "dossiers"',
     'STORE = _paths.DOSSIERS', 1),

    ("dossier.py",
     '    out = pathlib.Path("refresh_list.json")',
     '    out = _paths.out("refresh_list.json")', 1),

    ("research_queue.py",
     '    path = pathlib.Path(out_path or f"research_queue_{fragment}.json")',
     '    path = (pathlib.Path(out_path) if out_path\n'
     '            else _paths.league_out(lid, "research_queue.json"))', 1),

    ("draft_helper.py",
     '    out = pathlib.Path(f"cheatsheet_{lg[\'name\'].strip().replace(\' \', \'_\')}.txt")',
     '    out = _paths.league_out(league_id, "cheatsheet.txt")', 1),

    ("lineup_value.py",
     '        keeper = bool(json.loads((HERE / "keepers.json").read_text())',
     '        keeper = bool(json.loads(_paths.data("keepers.json").read_text())', 1),

    ("lineup_value.py",
     '        cfg = json.loads((path or (HERE / "keepers.json")).read_text())',
     '        cfg = json.loads((path or _paths.data("keepers.json")).read_text())', 2),
]


def plan_edits():
    """Validate every edit against the files on disk. Returns {file: text}
    with all edits applied in memory. Dies on the first mismatch."""
    texts = {}
    problems = []

    for fn in NEEDS_IMPORT:
        p = REPO / fn
        if not p.exists():
            problems.append(f"{fn}: missing")
            continue
        t = texts.get(fn) or read(p)
        if IMPORT_LINE in t:
            texts[fn] = t
            continue
        if IMPORT_AFTER not in t:
            problems.append(f"{fn}: no bare 'import pathlib' line to anchor "
                            f"the paths import on")
            continue
        texts[fn] = t.replace(IMPORT_AFTER, IMPORT_AFTER + IMPORT_LINE, 1)

    for fn, old, new, want in EDITS:
        p = REPO / fn
        if not p.exists():
            problems.append(f"{fn}: missing")
            continue
        t = texts.get(fn)
        if t is None:
            t = read(p)
        old_n = t.replace("\r\n", "\n")
        if new.split("\n")[0].strip() in t and old not in old_n:
            say(f"  {C.DIM}already applied: {fn} :: "
                f"{old.strip().splitlines()[0][:52]}…{C.END}")
            texts[fn] = t
            continue
        n = old_n.count(old)
        if n != want:
            problems.append(f"{fn}: expected {want} occurrence(s) of\n"
                            f"      {old.strip().splitlines()[0][:70]}\n"
                            f"      found {n}")
            continue
        crlf = "\r\n" in t
        t2 = old_n.replace(old, new)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2

    if problems:
        say(f"\n{C.BAD}Edits do not match the files on disk:{C.END}")
        for pr in problems:
            say(f"  - {pr}")
        die("nothing was written. The code has changed since the plan was "
            "built — re-derive the edit list before running again.")
    return texts


# ---------------------------------------------------------- the D  moves

MOVES = [
    # authored truth
    ("keepers.json", "data/keepers.json"),
    ("keepers.template.json", "data/keepers.template.json"),
    ("ages.json", "data/ages.json"),
    ("byes.json", "data/byes.json"),
    ("fonts.json", "data/fonts.json"),
    # measured truth
    ("room_bias.json", "data/measured/room_bias.json"),
    # reference docs
    ("COLUMNS.md", "docs/COLUMNS.md"),
    ("design_brief.md", "docs/design_brief.md"),
    ("RESEARCH_PLAN.md", "docs/RESEARCH_PLAN.md"),
    ("MISPRICING.md", "docs/MISPRICING.md"),
    # per-league authored material
    ("lg05_brief.md", "leagues/lg05/brief.md"),
    ("lg05_emoji_brief.md", "leagues/lg05-emoji/brief.md"),
    # spent scratch
    ("endgame_plan.md", "archive/endgame_plan.md"),
    ("before.txt", "archive/before.txt"),
    ("after.txt", "archive/after.txt"),
    ("cowork-handoff-prompt.md", "archive/cowork-handoff-prompt.md"),
    ("next_session_prompt.md", "archive/next_session_prompt.md"),
    ("dossiers_lg05_all.json", "archive/bundles/dossiers_lg05_all.json"),
    ("dossiers_lg05_deep.json", "archive/bundles/dossiers_lg05_deep.json"),
    # renders
    ("dashboard.html", "out/dashboard.html"),
    ("research_queue_lg05.json", "out/lg05/research_queue.json"),
]

NEW_DIRS = ["data", "data/measured", "docs", "archive", "archive/bundles",
            "out", "leagues", "leagues/lg05", "leagues/lg05-emoji",
            "leagues/lg01", "leagues/lg04", "leagues/lg02"]

DELETE = ["__pycache__"]


# ------------------------------------------------------------------- main

def main():
    head("preconditions")
    for must in ("sleeper_client.py", "draft_helper.py", "test_all.py"):
        if not (REPO / must).exists():
            die(f"{must} not found — run this from the Sleeper repo root.")
    if shutil.which("git") is None:
        die("git is not on PATH. Install Git for Windows, reopen the shell, "
            "and run again. Phase A is the rollback point; nothing should "
            "move without it.")
    for need in ("paths.py", "leagues/_index.json"):
        if not (REPO / need).exists() and not (REPO / pathlib.Path(need).name).exists():
            die(f"{need} is missing. Save paths.py to the repo root and "
                f"_index.json to leagues/ before running.")
    say(f"  {C.OK}ok{C.END}  repo root, git, and the new files are present")
    if DRY:
        say(f"\n{C.WARN}--dry-run: nothing will be written.{C.END}")

    # ---------------------------------------------------------------- A
    head("A · rollback point")
    fresh = not (REPO / ".git").exists()
    if fresh:
        say("  no .git — initialising")
        if not DRY:
            git("init")
            git("add", "-A")
            git("-c", "user.email=migrate@local", "-c", "user.name=migrate",
                "commit", "-m", "pre-migration snapshot (2026-08-13)")
    else:
        dirty = git("status", "--porcelain").stdout.strip()
        if dirty and not DRY:
            say(f"  {C.WARN}working tree is dirty; committing it as the "
                f"rollback point{C.END}")
            git("add", "-A")
            git("-c", "user.email=migrate@local", "-c", "user.name=migrate",
                "commit", "-m", "pre-migration snapshot (2026-08-13)")
    base_sha = "" if DRY else git("rev-parse", "HEAD").stdout.strip()
    say(f"  rollback point: {C.OK}{base_sha[:10] or '(dry run)'}{C.END}")

    # ------------------------------------------------------------ baseline
    head("baseline")
    if NO_VERIFY:
        say(f"  {C.WARN}--no-verify: skipping. You are on your own.{C.END}")
        base = {}
    else:
        base = run_checks(CHECKS, "baseline")
        broken = [n for n, v in base.items() if v is None or v[1] > 0]
        if broken:
            die("the repo is not green before we start:\n      "
                + "\n      ".join(broken)
                + "\n\n      Fix these first. Migrating a broken repo means "
                  "you cannot tell what the migration broke.")
        say(f"  {C.OK}baseline is green{C.END}")

    # ---------------------------------------------------------------- B
    head("B · paths.py and 16 writer edits")
    texts = plan_edits()
    for fn in sorted(texts):
        say(f"  {C.OK}ok{C.END}  {fn}")
    if not DRY:
        for fn, t in texts.items():
            write(REPO / fn, t)
        say(f"\n  wrote {len(texts)} modules")

    # ---------------------------------------------------------------- C
    head("C · leagues/ and the league index")
    for d in NEW_DIRS:
        say(f"  mkdir  {d}/")
        if not DRY:
            (REPO / d).mkdir(parents=True, exist_ok=True)
    stray = REPO / "_index.json"
    if stray.exists() and not (REPO / "leagues" / "_index.json").exists():
        say("  move   _index.json -> leagues/_index.json")
        if not DRY:
            shutil.move(str(stray), str(REPO / "leagues" / "_index.json"))
    for d in NEW_DIRS:
        keep = REPO / d / ".gitkeep"
        if not DRY and not any((REPO / d).iterdir()):
            keep.touch()

    # ---------------------------------------------------------------- D
    head("D · sweep")
    moved = 0
    for src, dst in MOVES:
        s, t = REPO / src, REPO / dst
        if not s.exists():
            say(f"  {C.DIM}skip{C.END}   {src} (not present)")
            continue
        if t.exists():
            say(f"  {C.WARN}skip{C.END}   {src} -> {dst} (destination exists)")
            continue
        say(f"  move   {src} -> {dst}")
        moved += 1
        if not DRY:
            t.parent.mkdir(parents=True, exist_ok=True)
            r = git("mv", src, dst, check=False)
            if r.returncode != 0:
                shutil.move(str(s), str(t))
    for d in DELETE:
        p = REPO / d
        if p.exists():
            say(f"  delete {d}/")
            if not DRY:
                shutil.rmtree(p, ignore_errors=True)
    say(f"\n  {moved} file(s) to move")

    if DRY:
        head("dry run complete — nothing was changed")
        say("Run without --dry-run to apply.")
        return

    # ----------------------------------------------------------- verify
    head("verify")
    post = run_checks(CHECKS + POST_ONLY, "post-migration")
    bad = compare(base, post) if not NO_VERIFY else []

    if bad:
        say(f"\n{C.BAD}REGRESSION — rolling back{C.END}")
        for b in bad:
            say(f"  - {b}")
        git("reset", "--hard", base_sha)
        git("clean", "-fd")
        say(f"\n{C.OK}rolled back to {base_sha[:10]}{C.END}. The repo is "
            f"exactly as it was.")
        say("Send the lines above to the session that wrote this script.")
        sys.exit(1)

    git("add", "-A")
    git("-c", "user.email=migrate@local", "-c", "user.name=migrate",
        "commit", "-m",
        "scaffold: source / truth / render split (phases A-D)\n\n"
        "paths.py owns every location. Writers no longer emit to the\n"
        "current working directory. leagues/_index.json is the single\n"
        "league key and paths.py --selftest fails if it drifts from\n"
        "mcp_server.LEAGUE_IDS.\n\n"
        "roster.md, config.json, the 19 modules and mcp_server.py are\n"
        "deliberately unmoved — see DEPENDENCIES.md.")

    head("done")
    say(f"  {C.OK}all checks green, committed{C.END}")
    say(f"  rollback if you want it:  git reset --hard {base_sha[:10]}")
    say("")
    say("  Next, by hand:")
    say("    1. python dashboard.py           -> out/dashboard.html")
    say("    2. python roster_snapshot.py     -> roster.md (still at root)")
    say("    3. update the paths named in README.md and CLAUDE.md")
    say("    4. after 8/18: load_league_rules(), then package the modules")


if __name__ == "__main__":
    main()
