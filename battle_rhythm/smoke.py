"""
smoke.py — does every writer still put its output where it says?

    python smoke.py                 # default league: lg03
    python smoke.py lg05
    python smoke.py --quick         # skip the two slow ones

Needs the network and takes a couple of minutes. This is the coverage
the repo does not otherwise have: test_all.py exercises the dashboard's
RENDER functions but never OUT.write_text, and no selftest anywhere
writes a file. After the 8/13 scaffold migration, five writers were
edited and none of their write paths were covered by anything.

The check that matters most is the last one. It snapshots the repo root
before and after and fails if ANY new file appeared there. Three writers
used to emit to the current working directory, so output landed wherever
the shell happened to be standing; research_queue_lg05.json sat in
the root only because that is where it was run. If that ever comes back,
this is what catches it.

roster.md is the one allowed exception at the root, on purpose — see
CLAUDE.md.
"""

import io
import os
import pathlib
import subprocess
import sys
import time

from battle_rhythm import paths

REPO = paths.REPO
QUICK = "--quick" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
LEAGUE = ARGS[0] if ARGS else "lg03"

ROOT_ALLOWED_NEW = {"roster.md"}

C_OK, C_BAD, C_WARN, C_DIM, C_END = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        C_OK = C_BAD = C_WARN = C_DIM = C_END = ""

results = []


def root_snapshot():
    return {p.name for p in REPO.iterdir() if p.is_file()}


def run_writer(label, argv, expect, slow=False):
    """expect: a Path that must exist and be newer than the start time."""
    if slow and QUICK:
        print(f"  {C_DIM}skip{C_END}   {label} (--quick)")
        return
    t0 = time.time() - 2
    print(f"  {C_DIM}...{C_END}    {label}", flush=True)
    # encoding is explicit on purpose. On Windows text=True decodes with
    # the locale codec (cp1252), and this toolkit prints em dashes and box
    # characters. The reader thread died on roster_snapshot's output the
    # first time this ran — and it did not fail the test, because stdout is
    # only read when a writer FAILS. The check passed while the diagnostic
    # under it was broken, which is the exact shape of "a vacuous check
    # cleared a real bug" in CLAUDE.md.
    r = subprocess.run([sys.executable] + argv, cwd=str(REPO),
                       capture_output=True, text=True, timeout=900,
                       encoding="utf-8", errors="replace")
    p = pathlib.Path(expect)
    if not p.exists():
        results.append((label, False,
                        f"expected {p.relative_to(REPO)} — not written "
                        f"(exit {r.returncode})"))
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-8:]
        for line in tail:
            print(f"         {C_DIM}{line[:100]}{C_END}")
        return
    if p.stat().st_mtime < t0:
        results.append((label, False,
                        f"{p.relative_to(REPO)} exists but was not rewritten "
                        f"— the writer wrote somewhere else"))
        return
    kb = p.stat().st_size // 1024
    results.append((label, True, f"{p.relative_to(REPO)}  ({kb} KB)"))


def check(label, cond, detail=""):
    results.append((label, bool(cond), detail))


def main():
    lid = paths.id_for(LEAGUE)
    if not lid:
        sys.exit(f"unknown league '{LEAGUE}'. Known: "
                 f"{', '.join(paths.leagues())}")
    slug = paths.slug_for(lid)
    print(f"\nsmoke test — league {slug} ({lid})")
    print(f"repo {REPO}\n")

    before = root_snapshot()

    print("writers:")
    run_writer("dashboard.py", ["dashboard.py"],
               paths.OUT / "dashboard.html", slow=True)
    run_writer("roster_snapshot.py", ["roster_snapshot.py"],
               REPO / "roster.md", slow=True)
    run_writer("draft_helper.py sheet", ["draft_helper.py", "sheet", lid],
               paths.OUT / slug / "cheatsheet.txt")
    run_writer("research_queue.py", ["research_queue.py", lid],
               paths.OUT / slug / "research_queue.json", slow=True)
    run_writer("dossier.py refresh-list",
               ["dossier.py", "refresh-list", lid],
               paths.OUT / "refresh_list.json")

    # room_bias is NOT run: it merges into measured truth, and re-running it
    # against a pre-draft league would append a meaningless entry beside the
    # real 2025 LG03-LG05 measurement. Verify the path resolves instead.
    print("\nmeasured truth (read-only):")
    rb = paths.measured("room_bias.json")
    check("room_bias.json resolves and parses", rb.exists() and
          rb.read_text(encoding="utf-8").strip().startswith("{"),
          str(rb.relative_to(REPO)) if rb.exists() else "MISSING")

    # config.json belongs at the root by design (sleeper_client's docstring
    # says so). The rest belong in data/ — one at the root means either the
    # move was undone or someone dropped a second copy there, and data()
    # prefers data/, so a root copy would be silently ignored.
    print("\nauthored truth resolves:")
    for name, want in (("keepers.json", "data"), ("ages.json", "data"),
                       ("byes.json", "data"), ("fonts.json", "data"),
                       ("config.json", "root")):
        p = paths.data(name)
        here = "data" if p.parent.name == "data" else "root"
        ok = p.exists() and here == want
        detail = f"{here}/" if ok else (
            "MISSING" if not p.exists()
            else f"in {here}/, expected {want}/ — a stray copy would be ignored")
        check(name, ok, detail)

    # The check paths.py cannot make. Its selftest compares _index.json
    # against mcp_server.LEAGUE_IDS -- two hand-maintained files. On 8/13 a
    # sixth league (the IDP one ROADMAP was waiting for) had been sitting in
    # the refreshed cache and neither file knew. A drift check between two
    # stale copies is not a check; this one asks the API.
    print("\nleague list matches leagues/_index.json:")
    from battle_rhythm.sleeper_client import load_leagues
    known = {str(m.get("id")) for m in paths.leagues().values()}
    live = {str(l["league_id"]): l for l in load_leagues().get("leagues", [])}
    new_ids = set(live) - known
    gone = known - set(live)
    for lid in sorted(new_ids):
        lg = live[lid]
        print(f"    NEW  {lid}  {lg.get('name')!r}  "
              f"{lg.get('total_teams')} teams  {lg.get('status')}")
    check("_index.json knows every league the API returns", not new_ids,
          "in sync" if not new_ids else f"{len(new_ids)} unknown")
    check("_index.json has no league the API does not", not gone,
          "in sync" if not gone else f"stale: {', '.join(sorted(gone))}")

    # Placement is a rule, not a one-time sort. migrate.py sorted this repo
    # on the morning of 8/13 and by that evening two league briefs were back
    # at the root as second copies. organize.py --check is the rule; running
    # it here is what makes it hold.
    print("\nper-league material is where the index says:")
    r = subprocess.run([sys.executable, "organize.py", "--check"],
                       cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    ok = r.returncode == 0
    if not ok:
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("-"):
                print(f"      {line.strip()}")
    check("organize.py --check passes", ok,
          "in place" if ok else "run: python organize.py")

    print("\nnothing scattered:")
    after = root_snapshot()
    new = (after - before) - ROOT_ALLOWED_NEW
    check("no new files in the repo root", not new,
          "clean" if not new else f"APPEARED: {', '.join(sorted(new))}")

    print(f"\n{'-' * 62}")
    npass = sum(1 for _, ok, _ in results if ok)
    for label, ok, detail in results:
        mark = f"{C_OK}ok{C_END}" if ok else f"{C_BAD}XX{C_END}"
        print(f"  {mark}  {label:28s} {detail}")
    bad = len(results) - npass
    print(f"\nsmoke {'PASSED' if not bad else 'FAILED'}  ({npass}/{len(results)})")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
