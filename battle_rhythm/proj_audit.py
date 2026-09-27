"""proj_audit.py — why our projection differs from the one Sleeper shows.

The board number is not the app number, and the difference is not a bug
until you know which knob made it. Our pipeline is:

    weekly_sum = sum(score(week_stats, league_scoring) for weeks 1..18)
    board      = weekly_sum * availability_ratio

`availability_ratio` comes from `draft_helper.availability_ratios`: the
season aggregate's generic points divided by the summed weekly generic
points, clamped to [0.5, 1.05]. Its docstring is explicit that the
aggregate covers roughly the top 100 per position, and that anyone
outside it DEFAULTS TO 1.0.

That default is the thing to watch. A player nobody aggregates takes no
injury haircut at all while the players around him take a real one, so
he floats up the board for no reason anybody intended. In a league that
starts DL, LB and DB it matters a great deal whether the aggregate
covers defenders — if it does not, every defender is priced without a
haircut against offensive players who have one.

    python proj_audit.py <league_id>                  # by position, all players
    python proj_audit.py <league_id> "Josh Allen" "Jack Campbell"
    python proj_audit.py <league_id> --top 15         # top 15 on the board

Read the DEFAULTED column first. Then compare `board` against whatever
your screen says, and the row tells you which stage owns the gap.
"""
import sys
from collections import defaultdict


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    lid = argv[0]
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 0
    names = [a for a in argv[1:] if not a.startswith("--")
             and not a.isdigit()]

    from battle_rhythm.sleeper_client import get, players as player_table, score
    from battle_rhythm.draft_helper import (weekly_projections, availability_ratios,
                              season_aggregates, SEAT_POS)

    tbl = player_table()
    lg = get(f"league/{lid}") or {}
    season = lg.get("season") or "2026"
    scoring = lg.get("scoring_settings") or {}
    print(f"\n== {lg.get('name')} — projection audit, season {season}")

    weekly = defaultdict(float)
    for wk in range(1, 19):
        for pid, st in weekly_projections(season, wk).items():
            if st:
                weekly[pid] += score(st, scoring)

    ratios = availability_ratios(season)
    agg = season_aggregates(season)
    print(f"   {len(weekly)} players carry a weekly projection")
    print(f"   {len(agg)} players appear in the season aggregate "
          f"(the haircut's source)")

    # ---- the systemic question: who gets a haircut at all, by position
    cov = defaultdict(lambda: [0, 0])
    for pid, wsum in weekly.items():
        if wsum <= 0:
            continue
        pos = (tbl.get(pid) or {}).get("position")
        if pos not in SEAT_POS:
            continue
        cov[pos][1] += 1
        if pid in agg:
            cov[pos][0] += 1
    print(f"\n   HAIRCUT COVERAGE — how many projected players the season "
          f"aggregate reaches")
    print(f"   {'pos':<6}{'covered':>9}{'projected':>11}{'coverage':>10}"
          f"   mean ratio applied")
    for pos in sorted(cov, key=lambda p: -cov[p][1]):
        got, tot = cov[pos]
        rs = [ratios.get(pid, 1.0) for pid, w in weekly.items()
              if w > 0 and (tbl.get(pid) or {}).get("position") == pos]
        mean = sum(rs) / len(rs) if rs else 1.0
        flag = "  <== NO HAIRCUT AT ALL" if got == 0 else (
               "  <== barely covered" if tot and got / tot < 0.10 else "")
        print(f"   {pos:<6}{got:>9}{tot:>11}{(got/tot if tot else 0):>9.0%}"
              f"   {mean:>6.3f}{flag}")

    # ---- per-player detail
    rows = []
    if names:
        low = [n.lower() for n in names]
        for pid, m in tbl.items():
            full = (m.get("full_name") or "").lower()
            if any(n in full for n in low) and weekly.get(pid):
                rows.append(pid)
    else:
        rows = sorted(weekly, key=lambda p: -weekly[p])[:max(top, 20)]

    print(f"\n   {'player':<24}{'pos':<5}{'weekly sum':>11}{'ratio':>8}"
          f"{'board':>9}   source of the ratio")
    for pid in rows:
        m = tbl.get(pid) or {}
        w = weekly[pid]
        r = ratios.get(pid, 1.0)
        src = "aggregate" if pid in agg else "DEFAULTED 1.0 (not aggregated)"
        print(f"   {(m.get('full_name') or pid)[:23]:<24}"
              f"{str(m.get('position')):<5}{w:>11.1f}{r:>8.3f}"
              f"{w * r:>9.1f}   {src}")

    print("\n   If your screen matches the WEEKLY SUM column, the app is "
          "showing an\n   unadjusted projection and our haircut is the whole "
          "difference.")
    print("   If it matches BOARD, we agree and the gap is elsewhere "
          "(week range,\n   scoring key, or a stale cache — projections "
          "refetch every 6h).")
    print("   If a position shows NO HAIRCUT AT ALL above, its players are "
          "being\n   compared against haircut offensive players and are "
          "systematically\n   flattered on the board.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
