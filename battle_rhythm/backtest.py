"""
backtest.py — how much is a projection edge actually worth?

  python br.py calibrate                 # rebuild data/measured/calibration.json
  python br.py calibrate --selftest      # offline, no cache needed

Every start/sit call this toolkit makes is a projection gap: start him
over him, he is worth 1.7 more points. Until 2026-09-03 nothing had ever
asked whether a 1.7 point gap means anything, and the honest answer is
that it barely does.

Measured on 2025, all 18 weeks, 40,456 joined player-weeks, priced under
a real league's scoring:

    projection edge     pairs   favourite actually outscores him
            0-1 pts    21361                              50.1%
            1-2 pts    20351                              53.4%
            2-3 pts    18892                              56.3%
            3-5 pts    33534                              61.9%
            5-8 pts    37436                              70.8%
           8-12 pts    28628                              79.9%
            12+ pts    14574                              88.3%

A one point edge is a coin flip. That is not a defect in Sleeper's
projections -- they are close to unbiased in aggregate, +0.06 points
across the population -- it is the irreducible variance of one football
game. Mean absolute error is 5.13 points against a mean projection of
9.52, and it is worst where the toolkit is least careful: TE at 68% of
the mean, WR 60%, RB 52%, QB 37%.

WHAT IT IS FOR. A recommendation that says "+1.7" invites the reader to
treat 1.7 as the thing he wins. He does not. He wins 1.7 points 53% of
the time and loses some other number 47% of the time. Printing the hit
rate beside the gap is the difference between advice and arithmetic.

The gate this had to pass first: if Sleeper backfilled its stored
projections with final numbers once a week completed, every gap would be
zero by construction and none of the above would mean anything. Measured
0.09% identical on the startable population -- 0.00% on the raw stat
lines. The feed is honest history.
"""

import gzip
import json
import statistics
import sys

POS = ("QB", "RB", "WR", "TE")
# Edge buckets in points. Fine at the bottom because that is where the
# decisions live and where the answer changes fastest.
BUCKETS = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 12), (12, 999)]
# A player projected and scoring under this is not a start/sit candidate;
# including him buries the signal under thousands of 0-vs-0 rows. The
# first run of this analysis reported 81% "identical" for exactly that
# reason, which looked like Sleeper backfilling and was not.
STARTABLE = 3.0


def _load(cache, kind, season, week):
    p = cache / f"hist_{kind}_{season}_{week}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def pairs_from(weeks, scoring, tbl, score_fn):
    """[(pos, gap, favourite_won)] over every same-position same-week pair.

    weeks: {week: (projections, actuals)}. Pure — no disk, no network.
    """
    out = []
    for wk, (P, S) in weeks.items():
        bypos = {}
        for pid in S:
            if pid not in P:
                continue
            pos = (tbl.get(pid) or {}).get("position")
            if pos not in POS:
                continue
            pr, ac = score_fn(P[pid], scoring), score_fn(S[pid], scoring)
            if pr < STARTABLE and ac < STARTABLE:
                continue
            bypos.setdefault(pos, []).append((pr, ac))
        for pos, v in bypos.items():
            for i in range(len(v)):
                for j in range(i + 1, len(v)):
                    (p1, a1), (p2, a2) = v[i], v[j]
                    gap = abs(p1 - p2)
                    if gap == 0:
                        continue
                    won = (a1 > a2) if p1 > p2 else (a2 > a1)
                    out.append((pos, gap, won))
    return out


def tabulate(pairs, by_position=False):
    """{bucket: (n, hit_rate)} — or {(pos, bucket): ...} when split."""
    acc = {}
    for pos, gap, won in pairs:
        for b in BUCKETS:
            if b[0] <= gap < b[1]:
                key = (pos, b) if by_position else b
                n, w = acc.get(key, (0, 0))
                acc[key] = (n + 1, w + (1 if won else 0))
                break
    return {k: (n, w / n) for k, (n, w) in acc.items() if n}


def confidence(gap, table):
    """Hit rate for a projection edge of `gap` points, or None.

    None when the bucket is too thin to quote — better to say nothing
    than to publish a rate off forty pairs.
    """
    for b in BUCKETS:
        if b[0] <= abs(gap) < b[1]:
            hit = table.get(f"{b[0]}-{b[1]}")
            if hit and hit.get("n", 0) >= 500:
                return hit["rate"]
            return None
    return None


def build(season, scoring, tbl, cache, score_fn):
    weeks = {}
    for w in range(1, 19):
        P, S = _load(cache, "proj", season, w), _load(cache, "stat", season, w)
        if P and S:
            weeks[w] = (P, S)
    if not weeks:
        raise SystemExit(
            f"no cached history for {season}. Run this on a networked machine:\n"
            f"    python br.py backtest {season} --harvest")
    pairs = pairs_from(weeks, scoring, tbl, score_fn)
    overall = tabulate(pairs)
    bypos = tabulate(pairs, by_position=True)
    return {
        "season": season,
        "weeks": sorted(weeks),
        "pairs": len(pairs),
        "overall": {f"{b[0]}-{b[1]}": {"n": n, "rate": round(r, 4)}
                    for b, (n, r) in sorted(overall.items())},
        "by_position": {f"{p}|{b[0]}-{b[1]}": {"n": n, "rate": round(r, 4)}
                        for (p, b), (n, r) in sorted(bypos.items())},
    }


def run(argv):
    from battle_rhythm import paths
    from battle_rhythm.sleeper_client import score, CACHE, players, load_leagues
    from battle_rhythm.dynasty_value import resolve_league
    frag = "dynasty"
    if "--league" in argv:
        frag = argv[argv.index("--league") + 1]
    season = next((a for a in argv if a.isdigit()), "2025")
    lid = resolve_league(frag)
    lg = next(l for l in load_leagues()["leagues"] if l["league_id"] == lid)
    out = build(season, lg.get("scoring_settings") or {}, players(), CACHE, score)
    dest = paths.measured("calibration.json")
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"calibrated on {lg['name']}, {season}, weeks "
          f"{out['weeks'][0]}-{out['weeks'][-1]}, {out['pairs']:,} pairs\n")
    print(f"{'projection edge':>16} {'pairs':>9} {'favourite wins':>15}")
    for k, v in out["overall"].items():
        lab = k.replace("-999", "+")
        print(f"{lab:>13} pts {v['n']:>9,} {100*v['rate']:>14.1f}%")
    print(f"\nwrote {dest}")


def selftest():
    n = 0

    def check(label, cond):
        nonlocal n
        print(f"  {'ok ' if cond else 'XX '} {label}")
        assert cond, label
        n += 1

    tbl = {"a": {"position": "WR"}, "b": {"position": "WR"},
           "c": {"position": "TE"}, "junk": {"position": "K"}}
    sc = lambda st, scoring: st.get("pts", 0.0)

    # one week: a projected 10 who scores 20, a projected 8 who scores 5.
    # gap 2 -> the 2-3 bucket, favourite won.
    weeks = {1: ({"a": {"pts": 10.0}, "b": {"pts": 8.0}, "c": {"pts": 9.0},
                  "junk": {"pts": 30.0}},
                 {"a": {"pts": 20.0}, "b": {"pts": 5.0}, "c": {"pts": 1.0},
                  "junk": {"pts": 30.0}})}
    pr = pairs_from(weeks, {}, tbl, sc)
    check("only same-position pairs are compared",
          len(pr) == 1 and pr[0][0] == "WR")
    check("kickers are not in the population",
          all(p[0] != "K" for p in pr))
    check("the gap is the projection gap", abs(pr[0][1] - 2.0) < 1e-9)
    check("and the favourite winning is recorded", pr[0][2] is True)

    # the 0-vs-0 tail must be excluded, or it drowns everything. This is
    # the filter whose absence made the first run report 81% "identical"
    # and look like Sleeper was backfilling actuals into projections.
    tail = {1: ({"x": {"pts": 0.0}, "y": {"pts": 0.0}},
                {"x": {"pts": 0.0}, "y": {"pts": 0.0}})}
    check("players who neither project nor score are dropped",
          pairs_from(tail, {}, {"x": {"position": "WR"},
                                "y": {"position": "WR"}}, sc) == [])

    fake = [("WR", 0.5, True)] * 600 + [("WR", 0.5, False)] * 600
    t = tabulate(fake)
    check("a coin flip tabulates as a coin flip",
          abs(t[(0, 1)][1] - 0.5) < 1e-9 and t[(0, 1)][0] == 1200)

    tbl_json = {"0-1": {"n": 1200, "rate": 0.501},
                "1-2": {"n": 40, "rate": 0.99}}
    check("a real bucket answers", confidence(0.5, tbl_json) == 0.501)
    check("a thin bucket declines rather than quoting 99% off 40 pairs",
          confidence(1.5, tbl_json) is None)
    check("an unmeasured gap declines", confidence(500, tbl_json) is None)

    print(f"\nselftest PASSED  ({n})")
    raise SystemExit(0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()
    run(a)
