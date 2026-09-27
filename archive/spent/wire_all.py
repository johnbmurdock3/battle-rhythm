"""
wire_all.py — one ADP market per league, resolved from the right feed.

    python wire_all.py --dry-run
    python wire_all.py

THE BUG, IN ONE LINE. `_adp` only asked the per-player endpoint when
NOTHING in the key chain matched the bulk weekly feed. A superflex chain
is ("adp_2qb",) + REDRAFT_ADP_KEYS; `adp_2qb` is absent from the bulk
feed but `adp_dd_ppr` sits two keys later and is present, so `_pick`
returned a 1QB number, the endpoint holding the real superflex price was
never called, and the result was stamped exact=True.

Measured on LG03-LG05, 8/13:

    player            board    find   lineup_value   REAL 2QB
    Josh Allen         29.0     6.7          29.0        1.2
    Justin Herbert     90.0    54.2          90.0       24.9
    Trevor Lawrence    80.0    66.3          80.0       32.0
    Amon-Ra St. Brown   5.0     7.8           5.0       16.3

Three code paths, three prices, none of them the market that room
drafts in. `superflex_adp.cache_path` already calls the on-disk book
"poisoned with 1QB values written under the superflex key" and routes
around it rather than fixing the cause. This fixes the cause.

WHAT CHANGES

1. `_adp` asks the per-player endpoint FIRST for keys that only exist
   there, and reuses superflex_adp's 500 already-fetched `adp_2qb`
   prices rather than refetching. Cache entries grow a third field --
   which key actually answered -- and any 2-field entry from before
   today is re-derived, because those may be poisoned.

2. `adp_keys_for(roster_positions, dynasty_typed, keeper)` -- one
   definition of which market a room drafts in, used by board_data,
   find, rookies and recap. The keeper fix landed in board_data only;
   the other three had never heard of it, which is why `find` said 6.7
   while the board said 29.0.

3. `adp_source()` so any caller can ask which key answered instead of
   trusting a boolean that was true either way.

Fail-closed: every edit is an exact string match verified before a byte
is written, the suite runs before and after, any regression rolls back.

AFTER THIS RUNS the first board rebuild will refetch ADPs for players
whose cached entry predates the fix. Roughly a minute, once, cached
permanently.
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


# ----------------------------------------------------------- 1. _adp

OLD_ADP = '''def _pick(d, keys):
    return next((d[k] for k in keys
                 if isinstance(d.get(k), (int, float)) and 0 < d[k] < 999), None)


def _adp(pid, season, keys, fallback=()):
    """Returns (value, exact) — exact=False means it came from the fallback tier."""
    p = CACHE / f"adp_{season}_{keys[0]}.json"
    book = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    key = str(pid)
    if not isinstance(book.get(key), list):  # old scalar cache format: re-derive
        book.pop(key, None)
    if key not in book:
        wk1 = weekly_projections(season, 1).get(key) or {}
        val, exact = _pick(wk1, keys), True
        if val is None:
            try:
                data = _get(f"{STATS_BASE}/projections/nfl/player/{key}"
                            f"?season_type=regular&season={season}&grouping=season") or {}
                val = _pick(data.get("stats") or {}, keys)
            except Exception:
                val = None
        if val is None and fallback:
            val, exact = _pick(wk1, fallback), False
        book[key] = [val, exact]
        p.write_text(json.dumps(book))
    return tuple(book[key])'''

NEW_ADP = '''# Keys the bulk weekly feed does NOT carry. They exist only on the
# per-player season endpoint, so a chain starting with one of these must
# ask the endpoint BEFORE it accepts a later key from the bulk feed.
PER_PLAYER_ONLY = ("adp_2qb", "adp_dynasty_ppr", "adp_dynasty_half_ppr",
                   "adp_dynasty_2qb", "adp_dynasty_std")


def _pick(d, keys):
    return _pick_kv(d, keys)[0]


def _pick_kv(d, keys):
    """(value, key) for the first usable key in the chain, else (None, None).

    Returning the key is the point. `exact` was True whether adp_2qb
    answered or adp_dd_ppr did four keys later, so a superflex league
    reading 1QB prices looked exactly like one reading superflex prices.
    """
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and 0 < v < 999:
            return v, k
    return None, None


def _from_endpoint(pid, season, keys):
    """Ask the per-player season endpoint for the first key in the chain.

    superflex_adp has already fetched adp_2qb for the whole pool and
    cached it; read that rather than refetching seven hundred players.
    Imported lazily -- superflex_adp imports this module.
    """
    if "adp_2qb" in keys:
        try:
            from superflex_adp import cache_path
            f = cache_path(season)
            if f.exists():
                v = json.loads(f.read_text(encoding="utf-8") or "{}").get(str(pid))
                if isinstance(v, (int, float)) and 0 < v < 999:
                    return float(v), "adp_2qb"
        except Exception:
            pass
    try:
        data = _get(f"{STATS_BASE}/projections/nfl/player/{pid}"
                    f"?season_type=regular&season={season}&grouping=season") or {}
        return _pick_kv(data.get("stats") or {}, keys)
    except Exception:
        return None, None


def _adp(pid, season, keys, fallback=()):
    """Returns (value, exact) — exact=False means the fallback tier answered.

    THE POISONING THIS FIXED (8/13). The old order tried the whole chain
    against the bulk weekly feed and only asked the per-player endpoint
    if nothing matched. For ("adp_2qb",) + REDRAFT_ADP_KEYS that meant
    adp_dd_ppr — a 1QB price — answered for a superflex room, and it was
    stamped exact. Josh Allen read 29.0 in a league whose real 2QB
    market has him at 1.2, and every survival call in both Hybrids was
    made against it. superflex_adp.cache_path documents the same
    poisoning and routes around it; this removes the cause.

    Cache entries carry a third field now: which key actually answered.
    Two-field entries predate the fix and are re-derived on sight.
    """
    p = CACHE / f"adp_{season}_{keys[0]}.json"
    book = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    key = str(pid)
    if not isinstance(book.get(key), list) or len(book[key]) < 3:
        book.pop(key, None)          # scalar or pre-8/13 format: re-derive
    if key not in book:
        wk1 = weekly_projections(season, 1).get(key) or {}
        val = src = None
        if keys[0] in PER_PLAYER_ONLY:
            val, src = _from_endpoint(key, season, keys)
        if val is None:
            val, src = _pick_kv(wk1, keys)
        if val is None:
            val, src = _from_endpoint(key, season, keys)
        exact = val is not None
        if val is None and fallback:
            val, src = _pick_kv(wk1, fallback)
            exact = False
        book[key] = [val, exact, src]
        p.write_text(json.dumps(book), encoding="utf-8")
    return tuple(book[key][:2])


def adp_source(pid, season, keys, fallback=()):
    """Which key supplied this ADP. None if he is unpriced.

    Ask this instead of trusting `exact` when the market matters.
    """
    _adp(pid, season, keys, fallback)
    p = CACHE / f"adp_{season}_{keys[0]}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))[str(pid)][2]
    except Exception:
        return None


def adp_keys_for(roster_positions, dynasty_typed, keeper=False):
    """(keys, fallback) — the ADP market this room actually drafts in.

    ONE definition. This decision used to be written seven times across
    the toolkit in two variants, and when the keeper correction landed
    on 8/13 it reached board_data and not find, rookies or recap — so
    Josh Allen carried three different prices in one league on the same
    afternoon.

    A keeper league churns everyone but the kept few, so it drafts in
    the REDRAFT market even where Sleeper types it dynasty. That is the
    keepers.json `keeper` flag's whole job (CLAUDE.md lesson 5).

    Superflex rooms live in the 2QB market: QBs price WAY earlier
    (Allen 1.2 in 2QB vs 28.2 in 1QB PPR), so the 2QB key leads and the
    1QB chains stay as fallback.
    """
    rp = roster_positions or []
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    dyn = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS) if sflex
           else DYNASTY_ADP_KEYS)
    red = ((("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS)
    if dynasty_typed and not keeper:
        return dyn, red
    return red, (dyn if dynasty_typed else ())'''


BD_OLD = '''    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # superflex leagues live in the 2QB market: QBs price WAY earlier
    # (Allen: 1.2 in 2QB vs 28.2 in 1QB PPR). Prefer that key when the
    # roster says so; the 1QB chains stay as fallback.
    if dynasty:
        adp_keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                    if superflex else DYNASTY_ADP_KEYS)
        adp_fallback = ((("adp_2qb",) + REDRAFT_ADP_KEYS)
                        if superflex else REDRAFT_ADP_KEYS)
    else:
        adp_keys = ((("adp_2qb",) + REDRAFT_ADP_KEYS)
                    if superflex else REDRAFT_ADP_KEYS)
        adp_fallback = ()
    adp_hdr = "dADP" if dynasty else "ADP"'''

BD_NEW = '''    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # One definition, in adp_keys_for(). `dynasty` has already been
    # flipped false above for keeper leagues, so pass keeper=False here
    # and let the flip stand rather than applying it twice.
    adp_keys, adp_fallback = adp_keys_for(rp, dynasty, keeper=False)
    adp_hdr = "dADP" if dynasty else "ADP"'''

FIND_OLD = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    keys = DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS
    fb = REDRAFT_ADP_KEYS if dynasty else ()

    for q in query:'''

FIND_NEW = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    # Was `DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS` — no keeper
    # flag, no superflex key. In LG03-LG05 that answered adp_dynasty_ppr
    # and priced Josh Allen at 6.7 while the board said 29.0 and the real
    # 2QB market said 1.2.
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            _keeper_flag(league_id))

    for q in query:'''

ROOKIES_OLD = '''    dynasty = d["dynasty"]
    keys = DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS
    fb = REDRAFT_ADP_KEYS if dynasty else ()
    adp_hdr = "dADP" if dynasty else "adp"'''

ROOKIES_NEW = '''    dynasty = d["dynasty"]
    # board_data has already applied the keeper flip to d["dynasty"].
    keys, fb = adp_keys_for((d.get("lg") or {}).get("roster_positions"),
                            dynasty, keeper=False)
    adp_hdr = "dADP" if dynasty else "adp"'''

RECAP_OLD = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    keys = DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS
    fb = REDRAFT_ADP_KEYS if dynasty else ()
    users = {u.get("user_id"): (u.get("display_name") or "?")'''

RECAP_NEW = '''    dynasty = (lg.get("settings") or {}).get("type") == 2
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            _keeper_flag(league_id))
    users = {u.get("user_id"): (u.get("display_name") or "?")'''

KEEPER_FLAG_OLD = '''def _pick(d, keys):
    return _pick_kv(d, keys)[0]'''

KEEPER_FLAG_NEW = '''def _keeper_flag(league_id):
    """keepers.json's manual keeper flag, via the one reader.

    Sleeper's settings.type == 2 covers both a 3-keeper Hybrid and full
    dynasty; only this flag tells them apart (CLAUDE.md lesson 5).
    """
    try:
        from league_rules import is_keeper_league
        return is_keeper_league(league_id)
    except Exception:
        return False


def _pick(d, keys):
    return _pick_kv(d, keys)[0]'''

EDITS = [
    ("draft_helper.py", OLD_ADP, NEW_ADP, 1),
    ("draft_helper.py", KEEPER_FLAG_OLD, KEEPER_FLAG_NEW, 1),
    ("draft_helper.py", BD_OLD, BD_NEW, 1),
    ("draft_helper.py", FIND_OLD, FIND_NEW, 1),
    ("draft_helper.py", ROOKIES_OLD, ROOKIES_NEW, 1),
    ("draft_helper.py", RECAP_OLD, RECAP_NEW, 1),
]

# dead since the 8/13 migration moved every data read to paths.data()
DEAD_HERE = ["dashboard.py", "dossier.py", "dynasty_value.py",
             "research_queue.py", "room_bias.py", "superflex_adp.py"]
HERE_LINE = "HERE = pathlib.Path(__file__).parent\n"

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
        if new.split("\n")[0].strip() in norm and old not in norm:
            print(f"  {C_DIM}already applied{C_END}  {fn}: "
                  f"{old.splitlines()[0][:44]}…")
            texts[fn] = t
            continue
        n = norm.count(old)
        if n != want:
            problems.append(f"{fn}: expected {want} copy of "
                            f"'{old.splitlines()[0][:52]}…', found {n}")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(old, new)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        print(f"  {C_OK}ok{C_END}  {fn}: {old.splitlines()[0][:52]}…")

    dead = []
    for fn in DEAD_HERE:
        p = REPO / fn
        if not p.exists():
            continue
        t = texts.get(fn) or read(p)
        norm = t.replace("\r\n", "\n")
        if HERE_LINE not in norm:
            continue
        uses = len(re.findall(r"\bHERE\b", norm))
        if uses > 1:
            print(f"  {C_WARN}skip{C_END}  {fn}: HERE used {uses}x, not dead")
            continue
        crlf = "\r\n" in t
        t2 = norm.replace(HERE_LINE, "", 1)
        texts[fn] = t2.replace("\n", "\r\n") if crlf else t2
        dead.append(fn)
        print(f"  {C_OK}ok{C_END}  {fn}: dead HERE removed")

    if problems:
        print(f"\n{C_BAD}edits do not match the files on disk:{C_END}")
        for pr in problems:
            print(f"  - {pr}")
        sys.exit("\nNothing was written.")

    if DRY:
        print(f"\n{C_WARN}--dry-run:{C_END} {len(texts)} file(s) would change "
              f"({len(dead)} dead HERE removed).")
        return 0

    if git("status", "--porcelain").stdout.strip():
        git("add", "-A")
        git("-c", "user.email=wire@local", "-c", "user.name=wire",
            "commit", "-m", "pre-wire snapshot")
    base = git("rev-parse", "HEAD").stdout.strip()
    print(f"\nrollback point: {C_OK}{base[:10]}{C_END}")

    before = run_checks("baseline")
    if any(v is None or v[1] for v in before.values()):
        sys.exit(f"\n{C_BAD}not green before we start. Fix that first.{C_END}")

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
        "adp: ask the feed that actually carries the key\n\n"
        "_adp only consulted the per-player endpoint when nothing in the\n"
        "chain matched the bulk weekly feed. adp_2qb is absent from that\n"
        "feed and adp_dd_ppr sits two keys later, so a superflex room got\n"
        "1QB prices stamped exact. Josh Allen read 29.0 against a real 2QB\n"
        "price of 1.2, and both Hybrids made every survival call on it.\n\n"
        "Per-player-only keys now hit the endpoint first, reusing the 500\n"
        "adp_2qb prices superflex_adp had already fetched. Cache entries\n"
        "record which key answered; pre-fix entries are re-derived.\n\n"
        "adp_keys_for() is the single definition of which market a room\n"
        "drafts in — board_data, find, rookies and recap all use it. The\n"
        "8/13 keeper correction had reached board_data only, which is why\n"
        "one player carried three prices in one league.")
    print(f"\n{C_OK}done — committed{C_END}")
    print(f"  rollback: git reset --hard {base[:10]}")
    print(f"\n  Next: {C_WARN}python adp_probe.py lg05{C_END} — the three "
          f"columns should now agree with 'real 2QB'.")
    print(f"  Then re-read leagues/lg05/brief.md: the numbers under the "
          f"plan have moved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
