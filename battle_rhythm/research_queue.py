"""
research_queue.py — who is worth researching, and how deeply.

Read-only, offline except for the board it already builds. Emits a
ranked, tiered work list so a research pass covers the whole draftable
universe without spending equal effort on a QB1 and a fifth-string TE.

    python research_queue.py lg05
    python research_queue.py lg03 --out queue_lg03.json
    python research_queue.py dynasty --limit 400
    python research_queue.py --selftest        # offline, no network

research_score = stakes x uncertainty x proximity

  stakes      how much value is at risk, under whichever view rates him
              higher: his share of the best model value, or rank decay
              on his market price. An unpriced player scores 0 on the
              market side, because no price means no endorsement — not
              a last-place endorsement. This term is why a WR6
              projecting 6 points cannot reach the top of the queue no
              matter how murky his situation is: nothing you learn
              about him changes a pick.
  uncertainty divergence between our rank and the market's, plus role
              flags (rookie, injured, buried on the depth chart, no
              team, past the age cliff). Unpriced players are ranked
              LAST by the market rather than given max divergence, so
              "our model loves him and the market has never heard of
              him" scores high while "nobody rates him" scores low.
  proximity   how close he is to a pick we own, when the draft order is
              known. Falls back to 1.0 pre-draft instead of a constant
              that flattens the whole term.

The first version of this multiplied divergence x proximity x
volatility with unpriced players pinned at divergence 1.0. It ranked
447 players and put a buried injured rookie TE first. Maximum
uncertainty, zero stakes. The stakes term exists to prevent exactly
that, and t_research_queue_ranks_stars_first guards it.

Tiers by rank, so effort tracks stakes:
  deep    top 40   — full dossier: team history, competition, scheme,
                     contract, injuries, camp reports
  medium  41-150   — role, competition, injury, one or two sources
  light   151+     — a single pass: what changed, is he starting

Team changes are deliberately NOT an input flag. We cannot see last
season's team offline without a fragile inference, and a team change
is something the research DISCOVERS — it was the whole Gainwell
finding. Don't filter on the answer.
"""

import json
import pathlib
from battle_rhythm import paths as _paths
import sys


TIERS = ((40, "deep"), (150, "medium"))


def tier_for(rank):
    for cutoff, name in TIERS:
        if rank <= cutoff:
            return name
    return "light"


def volatility(meta, adp, model_v, P):
    """0..1. Reasons a projection may be stale — ROLE uncertainty only.

    'unpriced' and 'sub-replacement' were flags in v1 and are gone:
    both are stakes signals, not uncertainty signals, and together they
    handed every scrub a near-max score. Unpriced is now expressed as a
    last-place market rank inside divergence; sub-replacement suppresses
    stakes on its own."""
    flags, score = [], 0.0
    pos, age = meta.get("position"), meta.get("age")
    if meta.get("years_exp") == 0:
        flags.append("rookie")
        score += 0.40
    elif isinstance(meta.get("years_exp"), int) and meta["years_exp"] <= 2:
        flags.append("early-career")
        score += 0.15
    if meta.get("injury_status"):
        flags.append(f"injury:{meta['injury_status']}")
        score += 0.30
    order = meta.get("depth_chart_order")
    if isinstance(order, int) and order >= 2:
        flags.append(f"depth:{order}")
        score += 0.20
    if not meta.get("team"):
        flags.append("no-team")
        score += 0.30
    c = (P.get("curves") or {}).get(pos)
    if c and isinstance(age, int):
        if age >= c["cliff"][0]:
            flags.append(f"past-cliff:{age}")
            score += 0.25
    if adp is None:
        flags.append("unpriced")          # recorded, deliberately unscored
    if model_v is not None and model_v <= 0:
        flags.append("sub-replacement")   # recorded, deliberately unscored
    return min(1.0, score), flags


def stakes_of(best_rank, half=25.0):
    """Rank decay: 1 at the very top, 0.5 at `half`, tailing to ~0.
    The point is that stakes fall off fast — the difference between
    pick 5 and pick 50 matters far more than 300 vs 350."""
    return round(1.0 / (1.0 + max(0, best_rank - 1) / half), 4)


def build(rows, next_picks, P, repl, dv):
    """rows: board_data rows. Returns list of queue entries, ranked."""
    scored = []
    for r in rows:
        pos = r["meta"].get("position")
        model_v = (dv(pos, r["meta"].get("age"), r["pts"], P,
                      repl.get(pos, 0.0))
                   if pos in (P.get("curves") or {}) else None)
        scored.append({"r": r, "model_v": model_v})

    n = len(scored) or 1
    by_model = sorted(scored, key=lambda x: -(x["model_v"] or -1))
    model_rank = {id(x["r"]): i + 1 for i, x in enumerate(by_model)}
    priced = [x for x in scored if x["r"].get("adp")]
    by_mkt = sorted(priced, key=lambda x: x["r"]["adp"])
    mkt_rank = {id(x["r"]): i + 1 for i, x in enumerate(by_mkt)}

    my_pick = next_picks[0][0] if next_picks else None
    max_mv = max([x["model_v"] for x in scored
                  if x["model_v"] is not None] or [0.0]) or 1.0
    out = []
    for x in scored:
        r = x["r"]
        mr = model_rank[id(r)]
        kr = mkt_rank.get(id(r))
        # unpriced = ranked last by the market, NOT max divergence.
        # "we rate him, the market doesn't" then scores high, while
        # "neither of us rates him" correctly scores near zero.
        kr_eff = kr if kr is not None else n + 1
        div = min(1.0, abs(mr - kr_eff) / (n * 0.5))
        # Stakes: how much value is at risk, under whichever view rates
        # him higher. Model side is his share of the best model value;
        # market side is rank decay. Unpriced means NO market
        # endorsement, so market stakes are 0 — not the stakes of a
        # last-place rank. That distinction is what stopped unpriced
        # scrubs from floating to the top of the queue.
        s_model = (max(0.0, x["model_v"]) / max_mv
                   if x["model_v"] is not None else 0.0)
        s_market = stakes_of(kr) if kr is not None else 0.0
        stakes = round(max(s_model, s_market), 4)
        if my_pick and r.get("adp"):
            prox = max(0.6, 1.0 - abs(r["adp"] - my_pick) / 200.0)
        else:
            prox = 1.0          # draft order unknown: don't flatten it
        vol, flags = volatility(r["meta"], r.get("adp"), x["model_v"], P)
        uncertainty = min(1.0, 0.25 + 0.5 * div + 0.5 * vol)
        score = round(stakes * uncertainty * prox, 4)
        out.append({
            "stakes": stakes, "uncertainty": round(uncertainty, 3),
            "player_id": r["pid"],
            "name": r["name"].split(" (")[0],
            "position": r["meta"].get("position"),
            "team": r["meta"].get("team"),
            "age": r["meta"].get("age"),
            "years_exp": r["meta"].get("years_exp"),
            "injury": r.get("inj") or "",
            "depth_chart": r["meta"].get("depth_chart_order"),
            "proj": round(r["pts"], 1),
            "adp": r.get("adp"),
            "model_value": x["model_v"],
            "model_rank": mr, "market_rank": kr,
            "divergence": round(div, 3), "proximity": round(prox, 3),
            "volatility": round(vol, 3), "flags": flags,
            "research_score": score,
        })
    out.sort(key=lambda e: -e["research_score"])
    for i, e in enumerate(out, 1):
        e["rank"] = i
        e["tier"] = tier_for(i)
    return out


def run(fragment, out_path=None, limit=500):
    from battle_rhythm.dynasty_value import load_params, dynasty_value, resolve_league
    from battle_rhythm.draft_helper import board_data
    P = load_params()
    lid = resolve_league(fragment)
    d = board_data(lid, depth=limit)
    q = build(d["rows"], d.get("next_picks") or [], P,
              d.get("replacement") or {}, dynasty_value)
    meta = {"league": d["lg"]["name"], "league_id": lid,
            "season": d["season"], "superflex": d.get("superflex"),
            "dynasty": d.get("dynasty"), "picks_made": len(d["picks"]),
            "next_picks": [p[0] for p in (d.get("next_picks") or [])],
            "count": len(q)}
    doc = {"meta": meta, "queue": q}
    path = (pathlib.Path(out_path) if out_path
            else _paths.league_out(lid, "research_queue.json"))
    path.write_text(json.dumps(doc, indent=1))

    counts = {}
    for e in q:
        counts[e["tier"]] = counts.get(e["tier"], 0) + 1
    print(f"{meta['league']} — {len(q)} draftable players")
    print("  " + "  ".join(f"{k}:{v}" for k, v in sorted(counts.items())))
    print(f"  wrote {path}\n")
    print(f"{'#':>4} {'score':>7} {'stake':>6} {'unc':>5} {'tier':>7} "
          f"{'pos':>4} {'age':>4} {'proj':>6} {'adp':>6}  player / flags")
    for e in q[:25]:
        adp_s = f"{e['adp']:.0f}" if e["adp"] else "-"
        print(f"{e['rank']:>4} {e['research_score']:>7.3f} "
              f"{e['stakes']:>6.2f} {e['uncertainty']:>5.2f} {e['tier']:>7} "
              f"{str(e['position']):>4} {str(e['age'] or '?'):>4} "
              f"{e['proj']:>6.0f} {adp_s:>6}"
              f"  {e['name']}  {','.join(e['flags'])}")


def selftest():
    P = {"curves": {"RB": {"peak": [23, 26], "rise": .92, "decline": .87,
                           "cliff": [28, .70], "end": 32}},
         "discount": 0.85}

    def dv(pos, age, proj, P, repl=0.0):
        return max(0.0, proj - repl)

    def row(pid, pos, age, pts, adp, **meta):
        m = {"position": pos, "age": age, "team": "X"}
        m.update(meta)
        return {"pid": pid, "name": f"{pid} ({pos}, X)", "meta": m,
                "pts": pts, "adp": adp, "inj": ""}

    rows = [row("star", "RB", 24, 300, 8.0),          # elite, agreed
            row("split", "RB", 24, 290, 260.0),       # elite, market hates
            row("rook", "RB", 22, 250, 30.0, years_exp=0),   # good rookie
            row("cliff", "RB", 30, 200, 20.0),        # past cliff
            row("scrub", "WR", 25, 6, None, depth_chart_order=6,
                years_exp=1)]                          # THE v1 BUG CASE
    # pad the pool so ranks and the stakes decay are meaningful
    rows += [row(f"f{i}", "RB", 26, 120 - i, 100.0 + i) for i in range(40)]
    q = build(rows, [], P, {"RB": 50.0}, dv)
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'ok' if cond else 'XX'}  {name}")
        ok = ok and cond

    by = {e["player_id"]: e for e in q}
    check("every player scored", len(q) == len(rows))
    check("ranks are 1..n",
          [e["rank"] for e in q] == list(range(1, len(rows) + 1)))
    # THE REGRESSION: v1 ranked a buried unpriced scrub #1 of 447
    check(f"buried unpriced scrub does NOT outrank the star "
          f"(scrub #{by['scrub']['rank']}, star #{by['star']['rank']})",
          by["scrub"]["rank"] > by["star"]["rank"])
    check("scrub lands in the bottom half",
          by["scrub"]["rank"] > len(rows) / 2)
    check("model/market split outranks the agreed star",
          by["split"]["research_score"] > by["star"]["research_score"])
    check("a good rookie outranks an equally-priced known vet",
          by["rook"]["research_score"] > by["f10"]["research_score"])
    check("stakes fall with rank",
          by["star"]["stakes"] > by["scrub"]["stakes"])
    check("unpriced is recorded but unscored",
          "unpriced" in by["scrub"]["flags"])
    check("past-cliff flagged", any(f.startswith("past-cliff")
                                    for f in by["cliff"]["flags"]))
    check("sorted descending by score",
          all(q[i]["research_score"] >= q[i + 1]["research_score"]
              for i in range(len(q) - 1)))
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--selftest":
        selftest() if args else sys.exit(__doc__)
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    lim = 500
    if "--limit" in args:
        i = args.index("--limit")
        lim = int(args[i + 1])
        del args[i:i + 2]
    run(args[0], out, lim)
