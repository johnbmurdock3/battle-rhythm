"""
draft_review.py — what you took vs what the model would take now.

    python draft_review.py dynasty            # your last 12 picks
    python draft_review.py dynasty --last 20
    python draft_review.py dynasty --all
    python draft_review.py --selftest

For each of your picks it rebuilds the board AS IT STOOD at that pick —
everyone drafted before it removed, positional replacement recomputed
from the pool that was actually left — then scores the survivors with
dynasty_value and your roster context at that moment, and reports what
you took against the best alternatives.

HONEST CAVEAT, stated in the output too: this uses TODAY'S projections,
research and model. Some of it was not knowable at the time, and the
model itself changed several times on 8/11. This answers "what would we
do now with this board", which is useful for calibration and for the
next draft. It is not a scorecard of decisions made with less.
"""

import json
import sys
from collections import defaultdict

# One definition, in roster_shape.py. This block was byte-identical in
# draft_review, roster_snapshot and weekly.
from battle_rhythm.roster_shape import FLEX_SHARE  # noqa: E402,F401


def demand_by_pos(roster_positions, teams):
    d = defaultdict(float)
    for s in roster_positions or []:
        if s in ("QB", "RB", "WR", "TE", "K", "DEF"):
            d[s] += 1
        elif s in FLEX_SHARE:
            for p, sh in FLEX_SHARE[s].items():
                d[p] += sh
    return {p: max(1, round(v * teams)) for p, v in d.items()}


def replacement_at(avail_by_pos, demand, gone_by_pos, teams):
    """Same rule board_data uses: Nth best available, N = remaining
    starter demand, floored at half a league of draft capacity."""
    floor = max(1, teams // 2)
    out = {}
    for pos, vals in avail_by_pos.items():
        total = demand.get(pos, 0)
        if not total:
            continue
        n = max(floor, total - min(gone_by_pos.get(pos, 0), max(0, total - 1)))
        out[pos] = vals[n - 1] if len(vals) >= n else (vals[-1] if vals else 0.0)
    return out


def review(picks, my_uid, totals, tbl, rp, teams, P, dv, roster_adjust,
           horizon, last=12, adp_of=None, damp=None, blend=None,
           disagree=None):
    from collections import defaultdict as dd
    demand = demand_by_pos(rp, teams)
    curves = set(P["curves"])
    mine_order = [pk for pk in picks
                  if pk.get("player_id") and str(pk.get("picked_by")) == str(my_uid)]
    mine_order = mine_order[-last:] if last else mine_order
    rows = []
    for pk in mine_order:
        n = pk.get("pick_no")
        gone = {p["player_id"] for p in picks
                if p.get("player_id") and (p.get("pick_no") or 0) < n}
        my_before = [p["player_id"] for p in picks
                     if p.get("player_id") and (p.get("pick_no") or 0) < n
                     and str(p.get("picked_by")) == str(my_uid)]

        avail_by_pos, gone_by_pos = dd(list), dd(int)
        for pid in gone:
            pos = (tbl.get(pid) or {}).get("position")
            if pos:
                gone_by_pos[pos] += 1
        pool = []
        for pid, pr in totals.items():
            if pid in gone or pr <= 0:
                continue
            m = tbl.get(pid) or {}
            if m.get("position") not in curves:
                continue
            avail_by_pos[m["position"]].append(pr)
            pool.append((pid, m, pr))
        for pos in avail_by_pos:
            avail_by_pos[pos].sort(reverse=True)
        repl = replacement_at(avail_by_pos, demand, gone_by_pos, teams)
        # shrink cross-position gaps the same way the board does
        if damp:
            repl = damp(repl, P, {p: len(v) for p, v in avail_by_pos.items()})

        cand = []
        for pid, m, pr in pool:
            v = dv(m["position"], m.get("age"), pr, P,
                   repl.get(m["position"], 0.0), horizon=horizon)
            cand.append({"pid": pid, "meta": m, "proj": pr,
                         "model_v": v, "value": v,
                         "adp": adp_of(pid) if adp_of else None})
        # THE BUG THIS REVIEW SHIPPED WITH: dashboard VALUE is 65% model
        # + 35% market, and the review used pure model. Two different
        # numbers wearing the same name, which is how it ended up
        # recommending a 22-year-old TE over Justin Jefferson.
        if blend:
            ladder = sorted((c["model_v"] for c in cand), reverse=True)
            blend(cand, P, ladder)
        roster_adjust(cand, my_before, tbl, P,
                      roster_positions=rp, repl=repl)
        if disagree:
            disagree(cand)
        cand.sort(key=lambda c: -c["value"])
        rank = {c["pid"]: i + 1 for i, c in enumerate(cand)}
        took = next((c for c in cand if c["pid"] == pk["player_id"]), None)
        rows.append({"pick": n, "took": pk["player_id"],
                     "took_row": took, "rank": rank.get(pk["player_id"]),
                     "best": cand[:4], "pool": len(cand)})
    return rows


def run(fragment, last=12):
    from battle_rhythm.sleeper_client import players, get, state
    from battle_rhythm.draft_helper import (uid, season_projection_totals, _adp,
                              DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)
    from battle_rhythm.dynasty_value import (load_params, dynasty_value, roster_adjust,
                               horizon_for, resolve_league, blend_market,
                               damped_replacement, market_disagreement)
    P = load_params()
    lid = resolve_league(fragment)
    lg = get(f"league/{lid}") or {}
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()
    totals = season_projection_totals(season, scoring)
    from battle_rhythm.draft_helper import resolve_draft
    _draft, picks = resolve_draft(lg)
    if not picks:
        raise SystemExit("no picks in this draft yet")
    teams = lg.get("total_rosters") or 12
    rp = lg.get("roster_positions") or []
    dyn = (lg.get("settings") or {}).get("type") == 2
    try:
        keeper = bool(json.loads(__import__("battle_rhythm.paths", fromlist=["paths"]).data("keepers.json")
                      .read_text(encoding="utf-8")).get(str(lid), {}).get("keeper"))
    except Exception:
        keeper = False
    hz = horizon_for(P, dynasty=dyn, keeper=keeper)

    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    from battle_rhythm.draft_helper import adp_keys_for
    keys, fb = adp_keys_for(rp, dyn, keeper)

    _cache = {}

    def adp_of(pid):
        if pid not in _cache:
            try:
                _cache[pid] = _adp(pid, season, keys, fb)[0]
            except Exception:
                _cache[pid] = None
        return _cache[pid]

    rows = review(picks, uid(), totals, tbl, rp, teams, P, dynasty_value,
                  roster_adjust, hz, last, adp_of=adp_of,
                  damp=damped_replacement, blend=blend_market,
                  disagree=market_disagreement)

    damp = (P.get("roster") or {}).get("scarcity_damp", 0)
    blend_w = P.get("market_blend", 0)
    print(f"\n══ {lg.get('name')} — review of your last {len(rows)} picks")
    print("   Scored with TODAY'S projections, research and model, against "
          "the board as it\n   actually stood at each pick. Not a scorecard "
          "of what was knowable then.")
    rises = " ".join(f"{p}{c.get('rise')}" for p, c in
                     sorted((P.get("curves") or {}).items()))
    print(f"   VALUE = {1 - blend_w:.0%} model + {blend_w:.0%} market · "
          f"scarcity damping {damp} · horizon {hz}")
    print(f"   rise {rises}")
    if P.get("_override"):
        print("   ** ENV OVERRIDE ACTIVE: " + ", ".join(P["_override"])
              + " (ages.json unchanged)")
    print("   [!] marks a pick where model and market disagree sharply — "
          "look before trusting.\n")
    total_gap, flagged = 0.0, 0
    for r in rows:
        t = r["took_row"]
        nm = (tbl.get(r["took"]) or {}).get("full_name") or r["took"]
        pos = (tbl.get(r["took"]) or {}).get("position") or "?"
        best = r["best"][0]
        gap = (best["value"] - (t["value"] if t else 0.0))
        total_gap += max(0.0, gap)
        flag = "  <-- best available" if r["rank"] == 1 else ""
        print(f"── pick {r['pick']}   you took {nm} ({pos})"
              f"   value {t['value'] if t else 0:.0f}"
              f"   rank {r['rank']}/{r['pool']}{flag}")
        if r["rank"] != 1:
            for c in r["best"][:3]:
                cn = c["meta"].get("full_name") or c["pid"]
                bits = []
                if c.get("note"):
                    bits.append(c["note"])
                if c.get("disagree"):
                    bits.append("[!] " + c["disagree"][2])
                    flagged += 1
                adp_s = f"adp {c['adp']:>5.0f}" if c.get("adp") else "adp    -"
                print(f"      would take: {cn:<24}"
                      f"{c['meta'].get('position'):>3} "
                      f"age {str(c['meta'].get('age') or '?'):>3}  "
                      f"proj {c['proj']:>6.0f}  {adp_s}  "
                      f"value {c['value']:>6.0f}")
                for b in bits:
                    print(f"          {b}")
            print(f"      gap to best: {gap:+.0f}")
        print()
    print(f"cumulative value left on the board: {total_gap:.0f}")
    if flagged:
        print(f"{flagged} of the suggested alternatives carry a model/market "
              "disagreement flag.")
        print("Where those two diverge there is either an edge or a bug. "
              "The first version of\nthis review had no market term at all "
              "and recommended a 22-year-old TE over\nJustin Jefferson — "
              "treat a flagged suggestion as a question, not an answer.")
    print("(gaps are only real if you accept ages.json — the curves are "
          "priors, not fitted)")


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    rp = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "DEF"]
    d = demand_by_pos(rp, 12)
    check(f"RB demand includes flex share ({d.get('RB')})", d.get("RB") == 34)
    check("QB demand is one per team", d.get("QB") == 12)

    avail = {"RB": [200.0, 180.0, 160.0, 140.0, 120.0, 100.0, 80.0]}
    r0 = replacement_at(avail, {"RB": 34}, {}, 12)
    check("thin pool falls back to the worst available", r0["RB"] == 80.0)
    r1 = replacement_at(avail, {"RB": 5}, {"RB": 0}, 12)
    check(f"demand 5 floored at teams//2=6 -> 6th best ({r1['RB']})",
          r1["RB"] == 100.0)

    # a pick is scored against the board AS IT STOOD, not today's board
    P = {"curves": {"RB": {"peak": [23, 26], "rise": .92, "decline": .87,
                           "cliff": [28, .70], "end": 32}},
         "discount": 0.85, "roster": {}, "horizons": {"dynasty": 20}}

    def dv(pos, age, proj, P_, repl=0.0, horizon=None):
        return max(0.0, proj - repl)

    def noadj(rows, mine, tbl, P_, **_kw):
        for r in rows:
            r.setdefault("value", r["model_v"])
        return rows

    tbl = {"a": {"position": "RB", "age": 25, "full_name": "Took Him"},
           "b": {"position": "RB", "age": 25, "full_name": "Better Guy"}}
    totals = {"a": 150.0, "b": 200.0}
    picks = [{"pick_no": 1, "player_id": "a", "picked_by": "me"}]
    rows = review(picks, "me", totals, tbl, ["RB", "RB"], 2, P, dv, noadj,
                  20, last=12)
    check("reviewed the pick", len(rows) == 1)
    check("better available player identified",
          rows[0]["best"][0]["pid"] == "b")
    check("taken player ranked behind him", rows[0]["rank"] == 2)

    # and a player drafted EARLIER must not appear as an alternative
    picks2 = [{"pick_no": 1, "player_id": "b", "picked_by": "them"},
              {"pick_no": 2, "player_id": "a", "picked_by": "me"}]
    rows2 = review(picks2, "me", totals, tbl, ["RB", "RB"], 2, P, dv, noadj,
                   20, last=12)
    check("already-drafted player excluded from alternatives",
          all(c["pid"] != "b" for c in rows2[0]["best"]))
    check("...leaving your pick as best available", rows2[0]["rank"] == 1)
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


def active_league():
    """The league currently drafting — the sensible default so running
    this with no arguments does the useful thing instead of printing
    usage at someone who is mid-draft."""
    from battle_rhythm.sleeper_client import load_leagues
    lgs = load_leagues()["leagues"]
    for want in ("drafting", "paused", "pre_draft"):
        for l in lgs:
            if (l.get("status") or "") == want:
                return l["name"]
    return None


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        selftest()
    last = 0 if "--all" in a else 12
    if "--last" in a:
        last = int(a[a.index("--last") + 1])
    frag = next((x for x in a if not x.startswith("--") and not x.isdigit()),
                None)
    if not frag:
        frag = active_league()
        if not frag:
            sys.exit("no league is drafting — name one: "
                     "python draft_review.py dynasty")
        print(f"(no league given — using the one that's drafting: {frag})")
    run(frag, last)
