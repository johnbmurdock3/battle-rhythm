"""superflex_adp.py — a 2QB draft market where Sleeper does not give one.

THE PROBLEM. Sleeper's weekly projection feed carries adp_ppr, adp_std,
adp_half_ppr and adp_dd_ppr. It does NOT carry adp_2qb: on 8/11, 33 of 33
quarterbacks came back without the field. draft_helper's key list puts
"adp_2qb" first and then falls straight through to the 1QB keys, so a
superflex league silently drafts off a single-quarterback market. Josh
Allen priced at 29 while Jahmyr Gibbs sat at 1 — a board where no
quarterback goes in the first round, in a league that starts two.

That is not a rounding error. It says Patrick Mahomes survives to pick
128 in a room where twenty-four quarterbacks start. Acting on it means
passing on quarterbacks that will be gone and reaching for skill players
that will not.

TWO WAYS TO FIX IT, in preference order.

1. FIND a real 2QB market. The per-player season endpoint carries fields
   the bulk weekly feed omits — that is already how dynasty ADP is
   sourced. probe() asks it directly. If adp_2qb lives there, we cache
   it and this module is a fetcher, nothing more.

2. DERIVE one. If Sleeper has no 2QB market anywhere, build a board
   instead of pretending. The derivation keeps the part of the market
   that is real and changes only the part that is wrong:

     - Skill players keep their 1QB ORDER. Twelve managers ranking
       running backs and receivers do not rank them differently because
       quarterbacks moved; superflex changes WHEN a position goes, not
       which back is better.
     - Quarterbacks are re-priced by surplus. In a 12-team superflex
       league 24 quarterbacks start, so QB replacement is QB24 rather
       than QB12 — a much lower bar, and every starter's surplus over it
       is correspondingly larger.
     - Each quarterback is then inserted among the skill players at the
       point where his surplus matches theirs, and everyone's pick
       number is recomputed from the merged order.

   The result is a MODEL, not a market, and every consumer is told so.
   It answers "roughly when does this position go in a room that starts
   two quarterbacks," which is the question the 1QB board answers wrong
   by fifty picks.

WHAT IT IS NOT. It does not know this specific room. Twelve managers who
all wait on quarterback would make it wrong in the other direction —
room_bias.py measures that once picks exist, and the derived board is
only the prior.

Usage (his machine, networked):
  python superflex_adp.py --probe [season]   # does Sleeper have adp_2qb?
  python superflex_adp.py "LG03-LG05"        # build + show the board
  python superflex_adp.py --selftest         # offline
"""

import json
import pathlib
import sys


# 12-team superflex starts 24 QBs. The other counts match the flex-share
# priors in roster_snapshot; they only set the replacement bar.
DEFAULT_STARTERS = {"QB": 2.0, "RB": 2.8, "WR": 2.9, "TE": 1.3}


def cache_path(season):
    from battle_rhythm.sleeper_client import CACHE
    # deliberately NOT adp_<season>_adp_2qb.json — that file was poisoned
    # with 1QB values written under the superflex key.
    return CACHE / f"sflex_adp_{season}.json"


def probe(season, pids):
    """Ask the per-player season endpoint whether a 2QB market exists.

    Returns {pid: {field: value}} for whichever 2QB-ish fields are found.
    An empty dict for every player means Sleeper has no such market and
    derive_board() is the only honest option.
    """
    from battle_rhythm.sleeper_client import _get, STATS_BASE
    want = ("adp_2qb", "adp_dynasty_2qb", "adp_sf", "adp_superflex")
    out = {}
    for pid in pids:
        try:
            d = _get(f"{STATS_BASE}/projections/nfl/player/{pid}"
                     f"?season_type=regular&season={season}"
                     f"&grouping=season") or {}
            st = d.get("stats") or {}
        except Exception:
            st = {}
        out[str(pid)] = {k: st[k] for k in want
                         if isinstance(st.get(k), (int, float))
                         and 0 < st[k] < 999}
    return out


def replacement_bars(rows, teams, starters=None):
    """{pos: projection of the last startable player} for THIS format."""
    st = starters or DEFAULT_STARTERS
    bars = {}
    for pos in {r["pos"] for r in rows if r.get("pos")}:
        ranked = sorted((r["proj"] for r in rows if r["pos"] == pos),
                        reverse=True)
        if not ranked:
            continue
        n = max(1, int(round(teams * st.get(pos, 1.0))))
        bars[pos] = ranked[min(n, len(ranked)) - 1]
    return bars


def derive_board(rows, teams, starters=None):
    """Fill in players with no real 2QB price, ON THE REAL SCALE.

    rows need: pid, pos, proj, adp (1QB), and optionally sflex_adp for
    those we fetched. Sets sflex_adp / sflex_src for everyone.

    THE BUG THIS REPLACES. The first version numbered derived players
    1, 2, 3... by merged rank while fetched players kept their true
    ADP, so the board mixed two scales: Josh Allen and Jahmyr Gibbs both
    read "1", Lamar Jackson collided with De'Von Achane at 11. Pick
    numbers from different rulers cannot be compared, and every
    "reachable at pick N" call downstream was built on the comparison.

    Now a player without a real price is placed BETWEEN the two priced
    players his surplus falls between, interpolating their ADPs. One
    ruler, no collisions, and the anchors are real market data.
    """
    bars = replacement_bars(rows, teams, starters)
    for r in rows:
        r["surplus"] = r["proj"] - bars.get(r["pos"], 0.0)

    known = sorted([r for r in rows if r.get("sflex_adp") is not None],
                   key=lambda r: -r["surplus"])
    unknown = [r for r in rows if r.get("sflex_adp") is None]
    if not known:
        # nothing real to anchor to: fall back to the 1QB order for skill
        # and surplus order for everyone, which is the old behaviour and
        # is clearly labelled as a model
        order = sorted(rows, key=lambda r: (-r["surplus"],))
        for i, r in enumerate(order):
            r["sflex_adp"], r["sflex_src"] = float(i + 1), "derived"
        return sorted(rows, key=lambda r: r["sflex_adp"])

    worst = max(r["sflex_adp"] for r in known)
    for r in unknown:
        above = [k for k in known if k["surplus"] >= r["surplus"]]
        below = [k for k in known if k["surplus"] < r["surplus"]]
        if above and below:
            lo = min(above, key=lambda k: k["surplus"])
            hi = max(below, key=lambda k: k["surplus"])
            span = (lo["surplus"] - hi["surplus"]) or 1.0
            f = (lo["surplus"] - r["surplus"]) / span
            r["sflex_adp"] = lo["sflex_adp"] + f * (hi["sflex_adp"]
                                                    - lo["sflex_adp"])
        elif above:
            r["sflex_adp"] = worst + 1.0
        else:
            r["sflex_adp"] = 1.0
        r["sflex_src"] = "derived"

    # break exact ties so two players never claim the same pick
    out = sorted(rows, key=lambda r: (r["sflex_adp"], -r["surplus"]))
    last = 0.0
    for r in out:
        if r["sflex_adp"] <= last:
            r["sflex_adp"] = last + 0.01
        last = r["sflex_adp"]
    return out


def apply_market(rows, teams, real=None, starters=None):
    """Real 2QB prices where we have them, interpolated where we do not."""
    real = {str(k): v for k, v in (real or {}).items()}
    for r in rows:
        v = real.get(str(r["pid"]))
        r["sflex_adp"] = float(v) if v is not None else None
        r["sflex_src"] = "sleeper_2qb" if v is not None else None
    out = derive_board(rows, teams, starters)
    return out, sum(1 for r in out if r["sflex_src"] == "sleeper_2qb")


def fetch_all(season, pids, cache, save_every=25, log=print):
    """Fetch adp_2qb for every pid we do not already have. Incremental.

    ~0.08s per call, so a 450-player pool is well under a minute and the
    cache is permanent. Saving every 25 means a Ctrl-C keeps the work.
    """
    from battle_rhythm.sleeper_client import _get, STATS_BASE
    todo = [p for p in pids if str(p) not in cache]
    if not todo:
        return cache, 0
    log(f"   fetching adp_2qb for {len(todo)} players "
        f"(~{len(todo) * 0.09:.0f}s, cached permanently)...")
    got = 0
    for n, pid in enumerate(todo, 1):
        try:
            d = _get(f"{STATS_BASE}/projections/nfl/player/{pid}"
                     f"?season_type=regular&season={season}"
                     f"&grouping=season") or {}
            v = (d.get("stats") or {}).get("adp_2qb")
        except Exception:
            v = None
        if isinstance(v, (int, float)) and 0 < v < 999:
            cache[str(pid)] = float(v)
            got += 1
        else:
            cache[str(pid)] = None          # remember the miss, do not refetch
        if n % save_every == 0:
            yield_cache(cache)
            log(f"     {n}/{len(todo)} ... {got} with a 2QB price")
    return cache, got


_CACHE_FILE = {"path": None}


def yield_cache(cache):
    if _CACHE_FILE["path"]:
        _CACHE_FILE["path"].write_text(json.dumps(cache))


# ------------------------------------------------------------------- CLI

def run(fragment=None, show=40, limit=500):
    from battle_rhythm.sleeper_client import get, players as player_table, load_leagues
    from battle_rhythm.draft_helper import (season_projection_totals, _adp,
                              REDRAFT_ADP_KEYS)
    from battle_rhythm.dynasty_value import resolve_league

    tbl = player_table()
    data = load_leagues(refresh=True)
    lid = resolve_league(fragment)
    lg = next(l for l in data["leagues"] if str(l["league_id"]) == str(lid))
    full = get(f"league/{lid}") or {}
    rp = full.get("roster_positions") or lg.get("roster_positions") or []
    if not ("SUPER_FLEX" in rp or rp.count("QB") >= 2):
        raise SystemExit(f"{lg['name']} is not superflex — nothing to do")
    season = lg.get("season") or full.get("season")
    scoring = full.get("scoring_settings") or lg.get("scoring_settings") or {}
    teams = lg.get("total_rosters") or lg.get("total_teams") or 12
    totals = season_projection_totals(season, scoring)

    rows = []
    for pid, pts in totals.items():
        m = tbl.get(pid) or {}
        if m.get("position") not in ("QB", "RB", "WR", "TE") or pts <= 0:
            continue
        try:
            a = _adp(pid, season, REDRAFT_ADP_KEYS)[0]
        except Exception:
            a = None
        rows.append({"pid": pid, "name": m.get("full_name") or pid,
                     "pos": m["position"], "proj": float(pts), "adp": a})
    rows.sort(key=lambda r: -r["proj"])
    rows = rows[:limit]

    cp = cache_path(season)
    _CACHE_FILE["path"] = cp
    cache = {}
    if cp.exists():
        try:
            cache = json.loads(cp.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            cache = {}
    # EVERY player, not just quarterbacks. Fetching QBs alone left the
    # board on two rulers — real ADPs for QBs, derived ranks for skill —
    # and Josh Allen tied Jahmyr Gibbs at pick 1.
    cache, got = fetch_all(season, [r["pid"] for r in rows], cache)
    yield_cache(cache)
    real = {k: v for k, v in cache.items() if v is not None}

    board, n_real = apply_market(rows, teams, real)
    print(f"\n== {lg.get('name')} — superflex board")
    print(f"   {teams} teams x 2 QB = {teams * 2} starting quarterbacks; "
          f"replacement is QB{teams * 2}, not QB{teams}")
    print(f"   {n_real}/{len(board)} carry a REAL adp_2qb; the rest are "
          f"interpolated onto\n   that same scale by surplus and marked *\n")
    print(f"   {'player':22} {'pos':4} {'proj':>6} {'1QB':>5} "
          f"{'SFLEX':>6}  {'move':>6}")
    for r in board[:show]:
        old = f"{r['adp']:.0f}" if r.get("adp") is not None else "—"
        mv = (f"{r['adp'] - r['sflex_adp']:+.0f}"
              if r.get("adp") is not None else "—")
        star = "" if r["sflex_src"] == "sleeper_2qb" else "*"
        print(f"   {r['name'][:22]:22} {r['pos']:4} {r['proj']:6.0f} "
              f"{old:>5} {r['sflex_adp']:6.0f}{star:1}  {mv:>6}")
    rd1 = [r for r in board if r["sflex_adp"] <= teams]
    old1 = sorted([r for r in rows if r.get("adp") is not None],
                  key=lambda r: r["adp"])[:teams]
    print(f"\n   Round 1 under the 2QB market: "
          f"{sum(1 for r in rd1 if r['pos'] == 'QB')} quarterbacks "
          f"(the 1QB board had "
          f"{sum(1 for r in old1 if r['pos'] == 'QB')}).")
    print(f"   Cached at {cp} — permanent, delete to refetch.")


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    rows = []
    for i in range(30):
        rows.append({"pid": f"q{i}", "name": f"QB{i}", "pos": "QB",
                     "proj": 400.0 - i * 8, "adp": 29.0 + i * 4})
    for i in range(60):
        rows.append({"pid": f"r{i}", "name": f"RB{i}", "pos": "RB",
                     "proj": 320.0 - i * 4, "adp": 1.0 + i * 2})
    for i in range(60):
        rows.append({"pid": f"w{i}", "name": f"WR{i}", "pos": "WR",
                     "proj": 330.0 - i * 4, "adp": 2.0 + i * 2})
    for i in range(20):
        rows.append({"pid": f"t{i}", "name": f"TE{i}", "pos": "TE",
                     "proj": 300.0 - i * 9, "adp": 17.0 + i * 6})

    bars = replacement_bars([dict(r) for r in rows], 12)
    check(f"QB replacement is the 24th QB in superflex ({bars['QB']:.0f})",
          bars["QB"] == 400.0 - 23 * 8)

    # ONE RULER. The first board gave fetched players their true ADP and
    # derived players a 1,2,3 rank, so Josh Allen and Jahmyr Gibbs both
    # read "pick 1" and Lamar Jackson collided with De'Von Achane at 11.
    real = {"q0": 1.0, "q1": 11.0, "q2": 4.0, "r0": 2.0, "w0": 3.0}
    board, n = apply_market([dict(r) for r in rows], 12, real)
    check(f"real prices are used where they exist ({n} of them)", n == 5)
    adps = [r["sflex_adp"] for r in board]
    check("NO two players claim the same pick number",
          len({round(a, 2) for a in adps}) == len(adps))
    check("...and the board is returned in pick order",
          adps == sorted(adps))
    check("a fetched player keeps his exact market price",
          next(r for r in board if r["pid"] == "q0")["sflex_adp"] == 1.0)
    check("...and is labelled as real",
          next(r for r in board
               if r["pid"] == "q1")["sflex_src"] == "sleeper_2qb")

    # an unfetched player must land BETWEEN the real anchors his surplus
    # falls between, not at the end and not at pick 1
    q3 = next(r for r in board if r["pid"] == "q3")
    check(f"an interpolated QB lands on the real scale "
          f"(pick {q3['sflex_adp']:.0f}, between his anchors)",
          1.0 < q3["sflex_adp"] < 60 and q3["sflex_src"] == "derived")
    check("interpolation never invents a price above the best anchor",
          min(adps) >= 1.0)

    # with no real data at all it must still produce a usable board
    b2, n2 = apply_market([dict(r) for r in rows], 12, {})
    check("no market at all still yields a complete, unique board",
          n2 == 0 and len({round(r["sflex_adp"], 2) for r in b2}) == len(b2))
    check("...ordered by surplus, quarterbacks included",
          b2[0]["surplus"] >= b2[-1]["surplus"])

    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()
    if a and a[0] == "--probe":
        season = a[1] if len(a) > 1 else None
        from battle_rhythm.sleeper_client import state
        from battle_rhythm.draft_helper import season_projection_totals
        season = season or state().get("season")
        from battle_rhythm.sleeper_client import players as _pt
        tbl = _pt()
        qb = [p for p, m in tbl.items() if (m or {}).get("position") == "QB"]
        res = probe(season, qb[:10])
        hit = {p: v for p, v in res.items() if v}
        print(f"probed 10 quarterbacks for {season}: "
              f"{len(hit)} carry a 2QB field")
        for p, v in list(hit.items())[:10]:
            print(" ", (tbl.get(p) or {}).get("full_name"), v)
        if not hit:
            print("  Sleeper has no 2QB market on this endpoint. "
                  "Run without --probe to derive one.")
        sys.exit(0)
    run(a[0] if a else None)
