"""
backtest_probe.py — what historical data does Sleeper actually serve?

Read-only. Answers four questions before we build any beat-rate model:

  1. Do bulk ACTUALS exist per season/week, and for how many players?
  2. Do bulk PROJECTIONS exist for PAST seasons/weeks?
  3. How many players have BOTH in the same week (the joinable set)?
  4. THE REVISION TELL: for a completed week, are the stored
     "projections" suspiciously equal to the actuals? If Sleeper
     backfills projections with final numbers, every beat rate we
     compute is exactly zero by construction and the whole idea dies.
     Reported as pct_identical — anything above ~10% is a red flag.

Usage:
    python backtest_probe.py                 # seasons 2022-2025
    python backtest_probe.py 2023 2024       # specific seasons
    python backtest_probe.py --sample "bijan robinson" --league dynasty

Nothing is written outside ~/.sleeper_cache. No league is touched.
"""

import gzip
import json
import sys

from battle_rhythm.sleeper_client import _get, get, players, score, name_of, load_leagues
from battle_rhythm.draft_helper import _normalize, player_hits

BASE_PROJ = "https://api.sleeper.app/v1/projections/nfl/regular/{s}/{w}"
BASE_STAT = "https://api.sleeper.app/v1/stats/nfl/regular/{s}/{w}"
ALT_PROJ = "https://api.sleeper.com/projections/nfl/{s}/{w}?season_type=regular"
ALT_STAT = "https://api.sleeper.com/stats/nfl/{s}/{w}?season_type=regular"


_MEMO = {}


def hist_path(kind, season, week):
    """~/.sleeper_cache/hist_<kind>_<season>_<week>.json.gz"""
    from battle_rhythm.sleeper_client import CACHE
    return CACHE / f"hist_{kind}_{season}_{week}.json.gz"


def fetch(primary, alt, kind=None, season=None, week=None):
    """Bulk fetch with the app-internal host as fallback. {pid: stats}.

    PERSISTS TO DISK when told what it is fetching. The probe used to
    memoise per process only, so every run re-downloaded tens of MB and
    left nothing behind -- which mattered more than it looks: the only
    machine that can reach api.sleeper.app is John's PC. The device VM
    has no network and the cloud container's egress denies CONNECT to
    both Sleeper hosts, tested 9/3.

    So the network step has to happen once, on his machine, and land
    somewhere the analysis can read offline. ~/.sleeper_cache is already
    mounted. Gzipped because a season of both feeds is ~100MB raw and
    about a tenth of that compressed.

    Historical weeks are FINAL. Unlike projections there is no reason to
    ever refetch one, so a cache hit is always correct.
    """
    if primary in _MEMO:
        return _MEMO[primary]

    disk = hist_path(kind, season, week) if kind else None
    if disk and disk.exists():
        try:
            with gzip.open(disk, "rt", encoding="utf-8") as f:
                out = json.load(f)
            _MEMO[primary] = out
            return out
        except (OSError, ValueError):
            pass                      # corrupt cache: refetch rather than die

    raw = _get(primary)
    if not raw:
        raw = _get(alt)
    out = {}
    if raw:
        try:
            out = _normalize(raw)
        except SystemExit:
            out = {}
    if disk and out:
        disk.parent.mkdir(parents=True, exist_ok=True)
        tmp = disk.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(out, f)
        tmp.replace(disk)             # atomic: a half-written week is worse
                                      # than a missing one
    _MEMO[primary] = out
    return out


def harvest(seasons, weeks=range(1, 19)):
    """Pull and cache every actual + projection for these seasons.

    The one command that needs network. Run it on the PC; everything
    downstream reads the cache and runs anywhere.
    """
    from battle_rhythm.sleeper_client import CACHE
    got = miss = 0
    for s in seasons:
        for w in weeks:
            for kind, pri, alt in (
                    ("stat", BASE_STAT.format(s=s, w=w), ALT_STAT.format(s=s, w=w)),
                    ("proj", BASE_PROJ.format(s=s, w=w), ALT_PROJ.format(s=s, w=w))):
                d = fetch(pri, alt, kind=kind, season=s, week=w)
                if d:
                    got += 1
                    print(f"  {s} wk{w:>2} {kind}  {len(d):>5} records"
                          f"  -> {hist_path(kind, s, w).name}")
                else:
                    miss += 1
                    print(f"  {s} wk{w:>2} {kind}  EMPTY")
    print(f"\ncached {got} files, {miss} empty. Cache: {CACHE}")
    print("Everything after this runs offline.")


def scored(line, scoring):
    return score(line, scoring) if line else 0.0


def probe(seasons, scoring, weeks=(1, 5, 9, 14, 17)):
    print(f"{'season':>7}{'wk':>4}{'proj':>8}{'actual':>8}{'both':>7}"
          f"{'identical':>11}  verdict")
    for s in seasons:
        for w in weeks:
            proj = fetch(BASE_PROJ.format(s=s, w=w), ALT_PROJ.format(s=s, w=w))
            act = fetch(BASE_STAT.format(s=s, w=w), ALT_STAT.format(s=s, w=w))
            both = [p for p in proj if p in act]
            # scored under real league rules, so the comparison is the
            # same currency the board uses
            ident = 0
            for pid in both:
                pv, av = scored(proj[pid], scoring), scored(act[pid], scoring)
                if pv > 0 and abs(pv - av) < 0.01:
                    ident += 1
            pct = (100.0 * ident / len(both)) if both else 0.0
            if not proj:
                verdict = "NO PROJECTIONS — beat rate impossible this season"
            elif not act:
                verdict = "no actuals"
            elif pct > 10:
                verdict = f"SUSPECT: projections look backfilled"
            else:
                verdict = "usable"
            print(f"{s:>7}{w:>4}{len(proj):>8}{len(act):>8}{len(both):>7}"
                  f"{pct:>10.1f}%  {verdict}")


def integrity(s_old, s_new, scoring, week=1):
    """Does the projections endpoint actually honor the season param?

    The probe's projection count is ~9410 in EVERY season/week, which is
    also what you'd see if the endpoint ignored season/week and served
    one current payload. If that were true, every 'beat rate' would be
    2026 projections vs 2022 actuals — garbage that looks like signal.

    Test: for players projected in both seasons, how many have a
    byte-identical projected stat line across two seasons three years
    apart? A real feed: near zero (nobody is projected identically in
    2022 and 2025). A faked feed: near 100%.

    Reports pct_identical_lines. Above ~20% and the season param is
    being ignored — stop, the whole backtest is void."""
    a = fetch(BASE_PROJ.format(s=s_old, w=week), ALT_PROJ.format(s=s_old, w=week))
    b = fetch(BASE_PROJ.format(s=s_new, w=week), ALT_PROJ.format(s=s_new, w=week))
    both = [p for p in a if p in b]
    same = sum(1 for p in both if a[p] == b[p])
    nz = [p for p in both if scored(a[p], scoring) > 0
          or scored(b[p], scoring) > 0]
    same_nz = sum(1 for p in nz if a[p] == b[p])
    pct = (100.0 * same / len(both)) if both else 0.0
    pct_nz = (100.0 * same_nz / len(nz)) if nz else 0.0
    print(f"\nSEASON-PARAM INTEGRITY — {s_old} wk{week} vs {s_new} wk{week}")
    print(f"  players projected in both       {len(both)}")
    print(f"  identical stat lines            {same} ({pct:.1f}%)")
    print(f"  ...among non-zero projections   {same_nz}/{len(nz)} ({pct_nz:.1f}%)")
    if pct_nz > 20:
        print("  VERDICT: season param IGNORED — backtest is void")
    else:
        print("  VERDICT: seasons are distinct payloads — backtest is valid")
    # how much of the 9410 is real: projections that score above zero
    live = sum(1 for p in b if scored(b[p], scoring) > 0)
    print(f"  {s_new} wk{week}: {live}/{len(b)} projections score > 0 "
          f"(the rest are empty stubs — filter them out)")


def sample(season, query, scoring, tbl):
    """One player, week by week: projected vs actual under league scoring.
    Mechanical line-per-week output on purpose — no aggregates, so a
    weird week is visible instead of averaged away."""
    hits, _h = player_hits(tbl, query)
    if not hits:
        print(f"no player matching '{query}'")
        return
    pid, m = hits[0]
    print(f"\n{name_of(pid, tbl)} — {season}")
    print(f"{'wk':>4}{'proj':>9}{'actual':>9}{'diff':>9}{'ratio':>8}")
    tp = ta = 0.0
    for w in range(1, 19):
        proj = fetch(BASE_PROJ.format(s=season, w=w),
                     ALT_PROJ.format(s=season, w=w)).get(pid)
        act = fetch(BASE_STAT.format(s=season, w=w),
                    ALT_STAT.format(s=season, w=w)).get(pid)
        if proj is None and act is None:
            continue
        pv, av = scored(proj, scoring), scored(act, scoring)
        tp += pv
        ta += av
        ratio = f"{av / pv:>7.2f}" if pv > 0 else "      -"
        print(f"{w:>4}{pv:>9.1f}{av:>9.1f}{av - pv:>+9.1f}{ratio}")
    r = f"{ta / tp:.2f}" if tp > 0 else "-"
    print(f"{'sum':>4}{tp:>9.1f}{ta:>9.1f}{ta - tp:>+9.1f}{r:>8}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    frag = "dynasty"
    if "--league" in args:
        i = args.index("--league")
        frag = args[i + 1]
        del args[i:i + 2]
    q = None
    if "--sample" in args:
        i = args.index("--sample")
        q = args[i + 1]
        del args[i:i + 2]
    lgs = load_leagues()["leagues"]
    lg = next((l for l in lgs if frag.lower() in (l["name"] or "").lower()), None)
    if not lg:
        raise SystemExit(f"no league matching '{frag}'")
    scoring = lg.get("scoring_settings") or {}
    print(f"scoring: {lg['name']}\n")
    seasons = [a for a in args if a.isdigit()] or ["2022", "2023", "2024", "2025"]
    if "--harvest" in args:
        harvest(seasons)
        sys.exit()
    if "--integrity" in args:
        integrity(seasons[0], seasons[-1], scoring)
        sys.exit()
    probe(seasons, scoring)
    if q:
        sample(seasons[-1], q, scoring, players())
