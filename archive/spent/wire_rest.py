"""
wire_rest.py — the last hand-written ADP branches onto adp_keys_for.

    python wire_rest.py --dry-run
    python wire_rest.py

wire_all.py put board_data, find, rookies and recap on one definition.
This finishes the job for the modules that still decide for themselves:

    keeper.py       show_keepers, adjusted_board, analyze   (3 branches)
    draft_review.py run                                     (1)
    room_bias.py    run                                     (1)
    dynasty_value.py run                                    (1)

Only the two Hybrids diverge — they are the only leagues where
dynasty-typed, keeper and superflex all hold at once — and they are the
two drafting Tuesday. `keeper.py --board` is the tool that produced the
keeper analysis the draft card rests on, so it is the one that matters.

Note the three branches inside keeper.py disagreed with each other:
show_keepers and analyze gated on `dynasty` alone, adjusted_board gated
on `dynasty and not short_horizon`. Same file, same league, two answers.
After this they cannot.

NOT TOUCHED, deliberately:

    lineup_value.py  Its chain already lands on adp_2qb, and it carries
                     the qb_bad repair that swaps in superflex_adp's
                     derived board. That repair is the only reason its
                     numbers were right all along. Changing anything
                     around it five days before a draft trades a working
                     path for a tidier one.
    draft_helper:627 The radp comparator — a deliberate second chain that
                     prices the redraft market alongside the dynasty one
                     so the gap can be shown as the age premium. It is
                     not the room's market and should not use it.

Fail-closed: exact string matches verified before any write, suite runs
before and after, regression rolls back.
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


K_SHOW_OLD = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    if dynasty:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if superflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
        fb = ()'''

K_SHOW_NEW = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # Was gated on `dynasty` alone while adjusted_board 70 lines below
    # gated on `dynasty and not short_horizon` — one file, one league,
    # two markets. These are other teams' locked keepers; price them in
    # the market this room actually drafts in, same as everything else.
    from league_rules import is_keeper_league
    keys, fb = adp_keys_for(rp, dynasty, is_keeper_league(league_2026_id))'''

K_BOARD_OLD = '''    short_horizon = bool((_rules.get(str(league_2026_id)) or {}).get("keeper"))
    if dynasty and not short_horizon:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if superflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
        market = "dynasty" + (" 2QB" if superflex else "")
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
        fb = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
              if superflex else DYNASTY_ADP_KEYS) if dynasty else ()
        market = ("redraft" + (" 2QB" if superflex else "")
                  + " — limited-keeper league, dynasty ADP over-penalizes age")'''

K_BOARD_NEW = '''    short_horizon = bool((_rules.get(str(league_2026_id)) or {}).get("keeper"))
    keys, fb = adp_keys_for(rp, dynasty, short_horizon)
    if dynasty and not short_horizon:
        market = "dynasty" + (" 2QB" if superflex else "")
    else:
        market = ("redraft" + (" 2QB" if superflex else "")
                  + " — limited-keeper league, dynasty ADP over-penalizes age")'''

K_ANALYZE_OLD = '''    totals = season_projection_totals(season, scoring)
    dynasty = (lg.get("settings") or {}).get("type") == 2
    keys = DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS
    fb = REDRAFT_ADP_KEYS if dynasty else ()'''

K_ANALYZE_NEW = '''    totals = season_projection_totals(season, scoring)
    dynasty = (lg.get("settings") or {}).get("type") == 2
    # Had neither the keeper flag nor the superflex key — in a Hybrid it
    # answered adp_dynasty_ppr, the 1QB dynasty market.
    from league_rules import is_keeper_league
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            is_keeper_league(league_2026_id))'''

DR_OLD = '''    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    if dyn and not keeper:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if sflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
        fb = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
              if sflex else DYNASTY_ADP_KEYS) if dyn else ()'''

DR_NEW = '''    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    from draft_helper import adp_keys_for
    keys, fb = adp_keys_for(rp, dyn, keeper)'''

RB_OLD = '''    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    if dynasty:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if superflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex else REDRAFT_ADP_KEYS
        fb = ()'''

RB_NEW = '''    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # room_bias measures how far a room drafts from the market. Measuring
    # against the wrong market invents a bias that is not there — this
    # file's own comment above says exactly that about the 2QB key.
    from draft_helper import adp_keys_for
    from league_rules import is_keeper_league
    keys, fb = adp_keys_for(rp, dynasty, is_keeper_league(lg.get("league_id")))'''

DV_OLD = '''    keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
            if (d["dynasty"] and d["superflex"]) else
            DYNASTY_ADP_KEYS if d["dynasty"] else REDRAFT_ADP_KEYS)
    fb = REDRAFT_ADP_KEYS if d["dynasty"] else ()'''

DV_NEW = '''    # board_data has already applied the keeper flip to d["dynasty"].
    from draft_helper import adp_keys_for
    keys, fb = adp_keys_for((d.get("lg") or {}).get("roster_positions"),
                            d["dynasty"], keeper=False)'''

EDITS = [
    ("keeper.py", K_SHOW_OLD, K_SHOW_NEW, 1),
    ("keeper.py", K_BOARD_OLD, K_BOARD_NEW, 1),
    ("keeper.py", K_ANALYZE_OLD, K_ANALYZE_NEW, 1),
    ("draft_review.py", DR_OLD, DR_NEW, 1),
    ("room_bias.py", RB_OLD, RB_NEW, 1),
    ("dynasty_value.py", DV_OLD, DV_NEW, 1),
]

# keeper.py imports the key tuples directly; it needs adp_keys_for too.
IMPORT_FIX = [
    ("keeper.py",
     "from draft_helper import season_projection_totals, _adp, "
     "DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS",
     "from draft_helper import (season_projection_totals, _adp, "
     "adp_keys_for,\n                          DYNASTY_ADP_KEYS, "
     "REDRAFT_ADP_KEYS)"),
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

    for fn, old, new in IMPORT_FIX:
        p = REPO / fn
        if not p.exists():
            continue
        t = read(p)
        norm = t.replace("\r\n", "\n")
        if "adp_keys_for" in norm.split("\n\n")[0] or new.split("\n")[0] in norm:
            texts[fn] = t
            continue
        if old not in norm:
            problems.append(f"{fn}: import line not found to extend")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(old, new, 1)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        print(f"  {C_OK}ok{C_END}  {fn}: import adp_keys_for")

    for fn, old, new, want in EDITS:
        p = REPO / fn
        t = texts.get(fn) or (read(p) if p.exists() else None)
        if t is None:
            problems.append(f"{fn}: missing")
            continue
        norm = t.replace("\r\n", "\n")
        if "adp_keys_for(" in norm and old not in norm:
            print(f"  {C_DIM}already applied{C_END}  {fn}: "
                  f"{old.splitlines()[0].strip()[:44]}…")
            texts[fn] = t
            continue
        n = norm.count(old)
        if n != want:
            problems.append(f"{fn}: expected {want} copy of "
                            f"'{old.splitlines()[0].strip()[:52]}…', found {n}")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(old, new)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        print(f"  {C_OK}ok{C_END}  {fn}: {old.splitlines()[0].strip()[:52]}…")

    if problems:
        print(f"\n{C_BAD}edits do not match the files on disk:{C_END}")
        for pr in problems:
            print(f"  - {pr}")
        sys.exit("\nNothing was written.")

    if DRY:
        print(f"\n{C_WARN}--dry-run:{C_END} {len(texts)} file(s) would change.")
        return 0

    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("-c", "user.email=wire@local", "-c", "user.name=wire",
            "commit", "-m", "pre-wire-rest snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")
    if any(v is None or v[1] for v in before.values()):
        sys.exit(f"\n{C_BAD}not green before we start.{C_END}")

    for fn, t in texts.items():
        write(REPO / fn, t)
    print(f"\n{C_OK}rewrote {len(texts)} module(s){C_END}")

    after = run_checks("post-wire")
    bad = []
    for name, b in before.items():
        a = after.get(name)
        if a is None:
            bad.append(f"{name}: no readable result")
        elif a[1]:
            bad.append(f"{name}: {a[1]} failing")
        elif b and a[0] < b[0]:
            bad.append(f"{name}: {b[0]} passing before, {a[0]} now")

    left = 0
    for f in sorted(REPO.glob("*.py")):
        if f.name in ("wire_all.py", "wire_rest.py", "adp_probe.py",
                      "migrate.py", "lineup_value.py", "draft_helper.py"):
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"(adp_keys|keys)\s*=\s*.*"
                         r"(DYNASTY_ADP_KEYS|REDRAFT_ADP_KEYS)", line):
                left += 1
    if left:
        print(f"\n{C_WARN}{left} hand-written ADP chain(s) still outside "
              f"draft_helper/lineup_value{C_END}")

    if bad:
        print(f"\n{C_BAD}REGRESSION — rolling back{C_END}")
        for b in bad:
            print(f"  - {b}")
        git("reset", "--hard", base)
        git("clean", "-fd")
        print(f"\n{C_OK}rolled back to {base[:10]}{C_END}")
        return 1

    git("add", "-A")
    git("-c", "user.email=wire@local", "-c", "user.name=wire", "commit", "-m",
        "adp: keeper, draft_review, room_bias and dynasty_value onto "
        "adp_keys_for\n\n"
        "keeper.py carried three branches that disagreed with each other:\n"
        "show_keepers and analyze gated on `dynasty` alone while\n"
        "adjusted_board gated on `dynasty and not short_horizon`. One file,\n"
        "one league, two markets — and adjusted_board is what produces the\n"
        "keeper analysis the Hybrid draft card rests on.\n\n"
        "lineup_value is deliberately unchanged: its chain already lands on\n"
        "adp_2qb and it carries the qb_bad repair that made its numbers the\n"
        "only correct ones before today.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    print(f"\n  Check it:  {C_WARN}python keeper.py lg05 --board{C_END}")
    print(f"  The market line should read redraft 2QB, not dynasty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
