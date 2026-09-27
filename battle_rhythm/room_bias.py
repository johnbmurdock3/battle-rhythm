"""
room_bias.py — measure how a specific room drafts, by position.

Global ADP is the average of thousands of drafts. Your room is not the
average. LG01 buys veterans about ten picks early (CLAUDE.md
lesson 6) and LG03-LG05 keys on running backs because the position is
thin. Both facts came from watching, and both are testable against the
room's own completed draft.

    python room_bias.py dynasty          # measure, print, write config
    python room_bias.py "LG03-LG05"
    python room_bias.py --selftest

Method: take the PREVIOUS season's completed draft, look up each drafted
player's ADP for THAT season, and compute reach = adp - pick_no. Positive
means the room paid early. Group by position, report n and spread so a
six-pick sample cannot masquerade as a rule.

Writes room_bias.json, keyed by league_id, which keeper.py --board reads
to shift effective draft position on top of keeper depletion. Config as
data, same as ages.json and keepers.json — tune it by hand if the
measurement disagrees with what you watched.

CAVEAT worth keeping in view: this measures the room's behaviour in a
DIFFERENT season with a different player pool. It is evidence, not law,
and a position with fewer than ~15 samples should be treated as noise.
"""

import json
import pathlib
from battle_rhythm import paths as _paths
import statistics
import sys

OUT = _paths.measured("room_bias.json")
MIN_N = 15


def measure(picks, adp_of, tbl):
    """{pos: {...}} plus a 'BASELINE' entry.

    Reported bias is RELATIVE, and that is the whole methodology.

    In a keeper league every position drafts early against global ADP,
    because ~60 players never reach the board and everyone slides. The
    absolute reach therefore measures depletion, which keeper.py already
    accounts for separately — counting it twice would double-shift the
    board. What is left after removing the room's own median reach is
    positional PREFERENCE: does this room take backs ahead of receivers,
    and by how much.

    'raw' is kept for inspection; 'bias' is the number to tune on."""
    by = {}
    for pk in picks:
        pid, n = pk.get("player_id"), pk.get("pick_no")
        if not pid or not n:
            continue
        pos = (tbl.get(pid) or {}).get("position")
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        adp = adp_of(pid)
        if not adp:
            continue
        by.setdefault(pos, []).append(adp - n)

    allvals = [v for vals in by.values() for v in vals]
    baseline = round(statistics.median(allvals), 1) if allvals else 0.0
    out = {"BASELINE": {"median": baseline, "n": len(allvals),
                        "note": "room-wide reach; depletion lives here and "
                                "keeper.py handles it separately"}}
    for pos, vals in by.items():
        if not vals:
            continue
        med = statistics.median(vals)
        out[pos] = {
            "raw_mean": round(statistics.mean(vals), 1),
            "raw_median": round(med, 1),
            "bias": round(med - baseline, 1),
            "n": len(vals),
            "stdev": round(statistics.stdev(vals), 1) if len(vals) > 1 else 0.0,
            "reliable": len(vals) >= MIN_N,
        }
    return out


def run(fragment):
    from battle_rhythm.sleeper_client import get, players, state
    from battle_rhythm.draft_helper import _adp, DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS
    from battle_rhythm.dynasty_value import resolve_league

    lid = resolve_league(fragment)
    lg = get(f"league/{lid}") or {}
    prev = lg.get("previous_league_id")
    if not prev:
        raise SystemExit(f"{lg.get('name')}: no previous season linked — "
                         "nothing to measure")
    plg = get(f"league/{prev}") or {}
    pseason = plg.get("season") or str(int(lg.get("season") or
                                           state().get("season")) - 1)
    # A PREVIOUS season can hold several drafts too -- that is literally
    # the case keeper.py recorded (the 2024 Hybrid ran a 7-rounder beside
    # the real 10-round startup), and measuring room bias off the wrong
    # one measures the wrong room.
    from battle_rhythm.draft_helper import resolve_draft
    _pdraft, picks = resolve_draft(plg)
    if not picks:
        raise SystemExit("previous draft returned no picks")

    tbl = players()
    dynasty = (lg.get("settings") or {}).get("type") == 2
    # SUPERFLEX FIRST. In a 2QB room, quarterbacks go far earlier than
    # their 1QB price, so comparing draft behaviour to adp_dynasty_ppr
    # makes every QB look ~100 picks "early" and reports a room quirk
    # that does not exist. board_data already prepends the 2QB key for
    # this reason; this file must too.
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # room_bias measures how far a room drafts from the market. Measuring
    # against the wrong market invents a bias that is not there — this
    # file's own comment above says exactly that about the 2QB key.
    from battle_rhythm.draft_helper import adp_keys_for
    from battle_rhythm.league_rules import is_keeper_league
    keys, fb = adp_keys_for(rp, dynasty, is_keeper_league(lg.get("league_id")))
    if superflex:
        print("   (superflex room — pricing QBs off the 2QB market)")

    def adp_of(pid):
        # ADP for the season the pick was actually made in
        try:
            return _adp(pid, pseason, keys, fb)[0]
        except Exception:
            return None

    res = measure(picks, adp_of, tbl)
    base = res["BASELINE"]
    print(f"{lg.get('name')} — room bias measured from the {pseason} draft "
          f"({len(picks)} picks)")
    print(f"room-wide median reach: {base['median']:+.1f} picks "
          f"— that is mostly keeper depletion, which keeper.py already")
    print("applies. BIAS below is measured against that baseline, so it is")
    print("positional preference only. Positive = taken earlier than the")
    print("room's own norm.\n")
    print(f"{'pos':>4}{'bias':>8}{'raw med':>9}{'n':>5}{'stdev':>7}  read")
    for pos in ("QB", "RB", "WR", "TE"):
        r = res.get(pos)
        if not r:
            print(f"{pos:>4}{'-':>8}")
            continue
        if not r["reliable"]:
            read = f"only {r['n']} samples — noise, do not tune on this"
        elif r["stdev"] > 45:
            read = (f"spread too wide (sd {r['stdev']:.0f}) — direction only, "
                    "no usable number")
        elif r["bias"] > 5:
            read = f"taken ~{r['bias']:.0f} picks ahead of the room's norm"
        elif r["bias"] < -5:
            read = f"falls ~{abs(r['bias']):.0f} picks past the norm"
        else:
            read = "no positional preference"
        print(f"{pos:>4}{r['bias']:>8.1f}{r['raw_median']:>9.1f}"
              f"{r['n']:>5}{r['stdev']:>7.1f}  {read}")

    book = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    prev_manual = (book.get(lid) or {}).get("manual")
    book[lid] = {"league": lg.get("name"), "measured_from": pseason,
                 "picks": len(picks), "by_position": res,
                 # hand-tuned, never overwritten by a re-measure
                 "manual": prev_manual or {
                     "_note": "your read, not measured. edit freely.",
                     "by_position": {},
                     "by_tag": {"rookie_qb": 0, "value_hunt": 0}}}
    OUT.write_text(json.dumps(book, indent=1))
    print(f"\nwrote {OUT}  (keeper.py --board reads this)")
    # BASELINE is a summary row, not a position — and the key is 'bias'
    # now, not 'mean'. Both wrong in one line; it crashed after the file
    # was already written, which is why the data survived.
    hi = [p for p, r in res.items()
          if p != "BASELINE" and r.get("reliable")
          and (r.get("stdev") or 0) <= 45 and (r.get("bias") or 0) > 8]
    if hi:
        print("NOTE: " + ", ".join(hi) + " go meaningfully early here. "
              "That stacks on top of keeper depletion — a scarce position "
              "is both kept more often AND drafted earlier.")
    return res


def manual_shift(league_id, pos, tags=(), book=None):
    """Hand-set shifts the measurement cannot see.

    Some room behaviour has no signal in last year's draft because the
    cause is this year's context. Two John flagged on 8/11 for the
    Hybrid rooms, which share managers:

      rookie_qb  he won with Lamar and then Jayden Daniels, and the room
                 noticed. Rookie QBs now get bid up preemptively.
      value_hunt the room actively hunts outsized value-to-price gaps,
                 so the LARGEST mispricings are the least likely to
                 survive to a late pick. Planning to "wait for" the best
                 bargain on the board is the plan most likely to fail.

    Edit room_bias.json by hand:
      "manual": {"by_position": {"QB": 6}, "by_tag": {"rookie_qb": 12}}
    Nothing here is measured. It is your read, written down so it applies
    consistently instead of being remembered at the wrong moment."""
    book = book if book is not None else (
        json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {})
    man = (book.get(str(league_id)) or {}).get("manual") or {}
    total = float((man.get("by_position") or {}).get(pos) or 0.0)
    for t in tags:
        total += float((man.get("by_tag") or {}).get(t) or 0.0)
    return total


def shift_for(league_id, pos, book=None):
    """Picks to subtract from a player's effective draft slot.

    Returns the RELATIVE bias, never the raw reach — keeper.py already
    subtracts depletion, and using raw here would shift the board twice.
    Returns 0 when the sample is thin or the spread is so wide the
    median means nothing; an unreliable number is worse than none."""
    book = book if book is not None else (
        json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {})
    r = ((book.get(str(league_id)) or {}).get("by_position") or {}).get(pos)
    if not r or not r.get("reliable") or (r.get("stdev") or 0) > 45:
        return 0.0
    return float(r.get("bias") or 0.0)


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    # WR is the bulk of any draft, so the room-wide median sits in the WR
    # range. RBs go 20 picks ahead of their price, WRs at it, one lone TE.
    tbl = {f"wr{i}": {"position": "WR"} for i in range(40)}
    tbl.update({f"rb{i}": {"position": "RB"} for i in range(20)})
    tbl["te1"] = {"position": "TE"}
    picks = ([{"player_id": f"wr{i}", "pick_no": 40 + i} for i in range(40)]
             + [{"player_id": f"rb{i}", "pick_no": 10 + i} for i in range(20)]
             + [{"player_id": "te1", "pick_no": 5}])
    adps = {f"wr{i}": 40 + i for i in range(40)}
    adps.update({f"rb{i}": 30 + i for i in range(20)})
    adps["te1"] = 60
    res = measure(picks, lambda p: adps.get(p), tbl)
    check("raw RB reach is +20", res["RB"]["raw_median"] == 20.0)
    check("raw WR reach is 0", res["WR"]["raw_median"] == 0.0)
    # BASELINE removal: the room-wide reach is shared by every position and
    # is depletion, which keeper.py already subtracts. Only the difference
    # between positions is preference.
    check(f"baseline sits with the bulk of picks "
          f"({res['BASELINE']['median']})",
          res["BASELINE"]["median"] == 0.0)
    check("RB bias survives baseline removal", res["RB"]["bias"] == 20.0)
    check("WR bias is zero — it IS the baseline", res["WR"]["bias"] == 0.0)
    check("RB sample marked reliable", res["RB"]["reliable"] is True)
    check("single-sample TE marked UNreliable",
          res["TE"]["n"] == 1 and res["TE"]["reliable"] is False)

    book = {"L": {"by_position": res}}
    check("shift_for returns the RELATIVE bias, never raw reach",
          shift_for("L", "RB", book) == 20.0)
    check("unreliable position yields NO shift — an unreliable number "
          "is worse than none", shift_for("L", "TE", book) == 0.0)
    check("unknown position yields no shift", shift_for("L", "K", book) == 0.0)
    # a wildly-spread sample is direction-only, never a tuning number
    wide = {"L2": {"by_position": {"QB": {"bias": 94.0, "n": 53,
                                          "stdev": 141.0, "reliable": True}}}}
    check("huge-spread position yields no shift despite a big median",
          shift_for("L2", "QB", wide) == 0.0)

    # manual overrides: reads the measurement cannot see
    man = {"L3": {"manual": {"by_position": {"QB": 6},
                             "by_tag": {"rookie_qb": 12, "value_hunt": 5}}}}
    check("manual positional override applies",
          manual_shift("L3", "QB", (), man) == 6.0)
    check("tags stack on top of the position",
          manual_shift("L3", "QB", ("rookie_qb",), man) == 18.0)
    check("multiple tags stack",
          manual_shift("L3", "QB", ("rookie_qb", "value_hunt"), man) == 23.0)
    # tags are caller-supplied labels; passing rookie_qb for a back is
    # caller error, not something this function second-guesses
    check("a position with no override and no tags gets no shift",
          manual_shift("L3", "RB", (), man) == 0.0)
    check("unknown league means no shift",
          manual_shift("nope", "QB", ("rookie_qb",), man) == 0.0)
    # a re-measure must never clobber a hand-tuned block
    check("manual block is preserved shape",
          set(man["L3"]["manual"]) == {"by_position", "by_tag"})
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        selftest() if a else sys.exit(__doc__)
    run(a[0])
