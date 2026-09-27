"""bonus_audit.py — the thirteen scoring rules the board pays zero for.

LG06 scores bonuses Sleeper's projection feed never projects, so
they are silently worth nothing on the board:

    bonus_rec_yd_100  10   bonus_rush_yd_100  10   bonus_pass_yd_300  10
    bonus_rec_yd_200   5   bonus_rush_yd_200   5   bonus_pass_yd_400   5
    bonus_tkl_10p      5   bonus_sack_2p       5   idp_pass_def_3p     5
    idp_def_td        10

They are per-GAME thresholds. A season total cannot say how often a player
crossed one, which is exactly why the feed omits them and why the board
cannot infer them.

SO THIS DOES NOT MODEL. It counts. For every player it pulls his real 2025
week-by-week lines and asks how many games actually cleared each threshold,
then prices those games at this league's own rates. Backward-looking
evidence, not a projection.

READ IT WITH THE OBVIOUS CAVEATS. 2025 is not 2026: rookies have no history
and print as blank, a player who changed teams or role carries his old
usage, and last year's health is not this year's. The number is "what these
bonuses were worth to this player the last time we watched him play a
season", which is a far better prior than the zero the board uses now.

    python bonus_audit.py              # top 40 by board VORP
    python bonus_audit.py --top 80
    python bonus_audit.py --pos DL
"""
import json
import sys

from battle_rhythm.sleeper_client import get, CACHE, players
from battle_rhythm.draft_helper import board_data
from battle_rhythm import paths as _paths

HIST = 2025
WEEKS = range(1, 19)

# (stat key, threshold, scoring key). Only rules THIS league actually pays.
RULES = [
    ("rec_yd",       100.0, "bonus_rec_yd_100"),
    ("rec_yd",       200.0, "bonus_rec_yd_200"),
    ("rush_yd",      100.0, "bonus_rush_yd_100"),
    ("rush_yd",      200.0, "bonus_rush_yd_200"),
    ("pass_yd",      300.0, "bonus_pass_yd_300"),
    ("pass_yd",      400.0, "bonus_pass_yd_400"),
    ("idp_tkl",       10.0, "bonus_tkl_10p"),
    ("idp_sack",       2.0, "bonus_sack_2p"),
    ("idp_pass_def",   3.0, "idp_pass_def_3p"),
]


def history():
    """Every 2025 week, one bulk call each, cached. Only one machine can
    fetch this; the cache is what makes a second run instant."""
    p = CACHE / f"weekstats_{HIST}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for wk in WEEKS:
        data = get(f"stats/nfl/regular/{HIST}/{wk}")
        if not data:
            print(f"   week {wk}: nothing returned", file=sys.stderr)
            continue
        out[str(wk)] = data
        print(f"   fetched {HIST} week {wk} ({len(data)} players)", file=sys.stderr)
    if not out:
        raise SystemExit("no history returned -- check the endpoint before trusting a zero")
    p.write_text(json.dumps(out))
    return out


def main(argv):
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 40
    posf = argv[argv.index("--pos") + 1].upper() if "--pos" in argv else None

    lid = json.loads((_paths.REPO / "leagues" / "_index.json")
                     .read_text(encoding="utf-8"))["leagues"]["lg06"]["id"]
    d = board_data(lid)
    sc = d["lg"].get("scoring_settings") or {}
    active = [(k, thr, sk) for k, thr, sk in RULES if sc.get(sk)]
    print(f"bonus rules this league pays and the board ignores: "
          f"{', '.join(sk for _, _, sk in active)}\n")

    print("pulling 2025 week-by-week actuals ...", file=sys.stderr)
    hist = history()

    rows = [r for r in d["rows"]
            if not posf or r["meta"].get("position") == posf][:top]
    out = []
    for r in rows:
        pid = r["pid"]
        games = seen = 0
        pts = 0.0
        detail = {}
        for wk, wkdata in hist.items():
            line = (wkdata or {}).get(pid)
            if not line:
                continue
            seen += 1
            hit = False
            for key, thr, skey in active:
                if (line.get(key) or 0) >= thr:
                    pts += sc[skey]
                    detail[skey] = detail.get(skey, 0) + 1
                    hit = True
            games += 1 if hit else 0
        out.append((pts, seen, games, detail, r))

    print(f"{'#':>3} {'vorp':>7} {'+bonus':>7} {'adj':>7} {'g':>3} {'gp':>3}  player")
    print(f"{'':>3} {'':>7} {'':>7} {'':>7} {'':>3} {'':>3}  "
          f"(+bonus = what 2025 would have paid; g = games that cleared any)")
    for i, (pts, seen, games, detail, r) in enumerate(
            sorted(out, key=lambda x: -(x[4]["vorp"] + x[0])), 1):
        tag = "" if seen else "   <-- no 2025 games: rookie, or missed the year"
        bits = " ".join(f"{k.replace('bonus_','').replace('idp_','')}x{v}"
                        for k, v in sorted(detail.items()))
        print(f"{i:>3} {r['vorp']:>7.1f} {pts:>7.1f} {r['vorp']+pts:>7.1f} "
              f"{games:>3} {seen:>3}  {r['name']}{tag}")
        if bits:
            print(f"{'':>32}{bits}")


if __name__ == "__main__":
    main(sys.argv[1:])
