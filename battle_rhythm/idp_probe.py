"""idp_probe.py — does the projections feed actually carry IDP stats?

Everything else about the new league is already handled by design.
`score()` is a dot product over whatever keys a stat line contains, with
no whitelist, so idp_tkl and idp_sack price themselves the moment they
appear. `dashboard.POS_COLORS` and `DEPTH_POS` already know DL/LB/DB,
the chips follow each league's own slots, and `load_leagues(refresh=True)`
discovers the league without being told.

So the single open question is upstream of all of it: does Sleeper
project defensive players at all? If the weekly feed has no idp_* keys,
every defender scores zero, the board ranks them below a punter, and the
draft is unusable for eleven of sixteen rounds. No amount of downstream
correctness survives an empty numerator.

    python idp_probe.py                 # week 1, the IDP league
    python idp_probe.py --week 3
    python idp_probe.py --league <id>

Read the VERDICT line. Everything above it is evidence for it.
"""
import sys
from collections import Counter

IDP_LEAGUE = "9000000000000000022"
IDP_POS = ("DL", "LB", "DB")


def main(argv):
    week = int(argv[argv.index("--week") + 1]) if "--week" in argv else 1
    lid = argv[argv.index("--league") + 1] if "--league" in argv else IDP_LEAGUE

    from battle_rhythm.sleeper_client import get, players as player_table, score
    from battle_rhythm.draft_helper import weekly_projections

    tbl = player_table()
    lg = get(f"league/{lid}") or {}
    scoring = lg.get("scoring_settings") or {}
    print(f"\n== {lg.get('name')} — projections probe, week {week}")

    proj = weekly_projections(lg.get("season") or "2026", week)
    print(f"   {len(proj)} players in the week {week} feed")

    idp_keys = {k for k, v in scoring.items() if k.startswith("idp_") and v}
    print(f"   league scores {len(idp_keys)} idp_* keys: "
          f"{', '.join(sorted(idp_keys))}")

    defenders = {pid: line for pid, line in proj.items()
                 if (tbl.get(pid) or {}).get("position") in IDP_POS}
    print(f"   {len(defenders)} of them are DL/LB/DB")

    seen = Counter()
    scored = []
    for pid, line in defenders.items():
        hits = [k for k in line if k.startswith("idp_")]
        seen.update(hits)
        if hits:
            m = tbl.get(pid) or {}
            scored.append((score(line, scoring), m.get("full_name") or pid,
                           m.get("position"), m.get("team")))

    if seen:
        print("\n   idp_* keys present in the feed, and how many players "
              "carry each:")
        for k, n in seen.most_common():
            paid = "scored" if scoring.get(k) else "NOT scored here"
            print(f"     {k:<16} {n:>5} players   ({paid})")

    scored.sort(reverse=True)
    if scored:
        print(f"\n   top 10 defenders by THIS league's scoring, week {week}:")
        for pts, name, pos, team in scored[:10]:
            print(f"     {pts:>7.1f}  {pos:<3} {name} ({team})")
        print(f"\n   projected over 17 weeks, the best of them lands near "
              f"{scored[0][0] * 17:.0f} points.")

    print()
    if not defenders:
        print("   VERDICT: the feed contains NO DL/LB/DB players at all. "
              "The board\n   cannot rank a position it cannot see. Nothing "
              "downstream will help.")
        return 2
    if not seen:
        print("   VERDICT: defenders are in the feed but carry NO idp_* "
              "stats, so every\n   one of them scores zero. DL/LB/DB "
              "rounds would be drafted blind.")
        return 2
    if not scored or scored[0][0] <= 0:
        print("   VERDICT: idp_* keys exist but every defender still "
              "scores zero. The\n   league's scoring and the feed's "
              "vocabulary are not meeting.")
        return 2
    print("   VERDICT: IDP projections are real and this league's scoring "
          "prices them.\n   The existing engine handles it — no new scoring "
          "code needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
