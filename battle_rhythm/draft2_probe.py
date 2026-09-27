"""draft2_probe.py — is the second draft actually deep enough?

THE ASSUMPTION THIS TESTS. Both Hybrid cards were rebuilt on 8/13 around
one claim: draft 1 carries no obligation to fill roster slots, because a
second draft backfills anything you skip at negligible cost. That claim
is what justifies the replacement floor in lineup_value, and the floor is
what moved pick 8 in the no-emoji league off a quarterback. If it is
wrong, both cards are wrong at the top.

It has never been measured. This measures it.

    python draft2_probe.py 9000000000000000013
    python draft2_probe.py 9000000000000000019
    python draft2_probe.py <id> --rounds 10      # draft-1 length

The method, deliberately crude and stated so you can argue with it:

  1. Everyone already rostered is gone. That is the keeper set.
  2. Draft 1 takes the next `teams x rounds` players. Ranked by DEPLETED
     ADP where a player has one, then by projection — because the room
     drafts roughly to market, and an unpriced player is one the market
     is not chasing.
  3. Whatever is left is draft 2's pool.

Then the only question that matters: at each position, how does draft 2's
BEST AVAILABLE compare to the replacement level the floor assumes?

  best available >= replacement   -> the floor is honest, cards stand
  best available <  replacement   -> the floor is too high. Skipping a
                                     slot in draft 1 costs real points,
                                     and the cards should tilt back
                                     toward filling holes.

Read the VERDICT line. Everything above it is the evidence.
"""
import sys


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    lid = argv[0]
    rounds = int(argv[argv.index("--rounds") + 1]) if "--rounds" in argv else 0

    from battle_rhythm.sleeper_client import get, players as player_table
    from battle_rhythm.draft_helper import board_data, replacement_levels

    d = board_data(lid)
    lg, tbl, rows = d["lg"], d["tbl"], d["rows"]
    teams = lg.get("total_rosters") or 12
    full = get(f"league/{lid}") or {}
    did = full.get("draft_id")
    draft = get(f"draft/{did}") if did else None
    rounds = rounds or ((draft or {}).get("settings") or {}).get("rounds") or 10

    print(f"\n== {lg.get('name')} — how deep is draft 2?")
    print(f"   {teams} teams x {rounds} rounds = {teams * rounds} players "
          f"leave the board in draft 1")
    print(f"   {len(d['gone'])} are already rostered and never enter it")

    # board_data's rows are the TOP `depth` only; go wider for the tail
    wide = board_data(lid, depth=1200)["rows"]
    print(f"   {len(wide)} priced, projected players available in total")

    # ---- who draft 1 takes: depleted ADP first, then projection
    def key(r):
        a = r.get("adp")
        return (0, a) if a is not None else (1, -r["pts"])
    ordered = sorted(wide, key=key)
    taken = ordered[:teams * rounds]
    left = ordered[teams * rounds:]
    print(f"   -> draft 2 pool: {len(left)} players\n")

    # ---- replacement, exactly as the floor computes it
    by_pos_all, by_pos_left = {}, {}
    for r in wide:
        by_pos_all.setdefault(r["meta"].get("position"), []).append(r["pts"])
    for r in left:
        by_pos_left.setdefault(r["meta"].get("position"), []).append(r["pts"])
    rep = d.get("replacement") or {}

    print(f"   {'pos':<5}{'replacement':>13}{'d2 best':>10}{'gap':>8}"
          f"{'d2 left':>9}   read")
    verdict_ok, verdict_bad = [], []
    for pos in sorted(by_pos_all, key=lambda p: -(rep.get(p) or 0)):
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        r_ = rep.get(pos)
        vals = sorted(by_pos_left.get(pos, []), reverse=True)
        if not r_ or not vals:
            continue
        best = vals[0]
        gap = best - r_
        if gap >= 0:
            read, ok = "draft 2 covers it", True
        elif gap > -0.15 * r_:
            read, ok = "close — within 15%", True
        else:
            read, ok = "**SHORT** — skipping costs points", False
        (verdict_ok if ok else verdict_bad).append(pos)
        print(f"   {pos:<5}{r_:>13.0f}{best:>10.0f}{gap:>+8.0f}"
              f"{len(vals):>9}   {read}")

    print()
    if not verdict_bad:
        print("   VERDICT: draft 2 can fill any slot you skip at or near "
              "replacement.\n   The floor is honest and both cards' "
              '"draft for value, not for holes"\n   holds. Skipping a '
              "starting slot in draft 1 is cheap.")
        return 0
    print(f"   VERDICT: draft 2 comes up SHORT at {', '.join(verdict_bad)}. "
          f"The replacement\n   floor is set too high at those positions, so "
          f"lineup_value is UNDER-\n   valuing anyone who fills one of them "
          f"and both cards tilt too far\n   toward pure value. Filling "
          f"{'/'.join(verdict_bad)} in draft 1 is worth more\n   than the "
          f"boards currently say.")
    print("\n   What this does NOT prove: the ordering above assumes the room "
          "drafts\n   to depleted ADP. A room that reaches, or one that runs "
          "on a position,\n   empties the tail differently. Rerun with "
          "room_bias.py's measured shave\n   once Tuesday's picks land.")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
