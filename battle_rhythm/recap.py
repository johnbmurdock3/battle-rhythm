"""
Draft recap — the morning after, once per league.

  python br.py recap lg04
  python br.py recap lg04 --json out.json
  python br.py recap --selftest          # offline, no network

draft_review.py rebuilds the board at each past pick and answers "what did
the model think at the time." This answers the question a manager actually
asks the next morning: where did I beat the board, where did I reach, which
picks did the room disagree with, and what does my roster look like against
the league.

Two independent yardsticks, and they disagree on purpose:

  vs BOARD   what was still available when you picked, by points over
             replacement. Measures selection: did you take the best player
             sitting there.

  vs MARKET  the player's ADP against the pick you spent. Measures price:
             did you pay less than the room would have.

A pick can beat the market and lose to the board (you got a bargain on the
wrong player) or beat the board and lose to the market (you paid up for the
right one). Reporting one number would hide which happened, and which
happened is the whole lesson.

Rest-of-season value is NOT what this scores. It scores the decision with
the information available on draft day, because that is the only thing a
recap can fairly grade. Whether the player is good is next season's
question and ages.json's problem.
"""

import json
import sys

# Reach/steal thresholds, in picks. A round is 10-14 picks depending on the
# league, so half a round is the smallest gap worth a sentence. These are
# labels on a continuous number, not a model.
REACH_PICKS = 12
STEAL_PICKS = 12


def recap_rows(picks, my_uid, value_of, adp_of, name_of_pid, teams):
    """One row per pick of mine. Pure: no network, no globals.

    value_of(pid)   -> points over replacement at draft time, or None
    adp_of(pid)     -> market ADP, or None (defenders in IDP have none)
    name_of_pid(pid)-> display name

    `available` is every player who was still undrafted at that pick, which
    the caller supplies as the pool; we walk the pick list forward so the
    pool shrinks exactly as the draft did.
    """
    taken = set()
    mine = []
    for i, pk in enumerate(picks):
        pid = pk.get("player_id")
        overall = pk.get("pick_no") or (i + 1)
        if pk.get("picked_by") == my_uid and pid:
            mine.append({"overall": overall, "pid": pid,
                         "name": name_of_pid(pid),
                         "round": pk.get("round"),
                         "taken_before": set(taken)})
        if pid:
            taken.add(pid)
    return mine


def grade(row, pool, value_of, adp_of, name_of_pid, offset=0):
    """Attach board and market verdicts to one pick.

    `offset` is how many players left the board before this draft started.
    In a two-stage league the second draft numbers its picks from 1 again,
    and ADP is a single global market -- so comparing stage-two pick 65 to
    an ADP of 664 read as "600 picks of value" when the player was really
    the 185th off the board. Same arithmetic, wrong denominator.
    """
    pid = row["pid"]
    mine_val = value_of(pid)
    # The pool INCLUDES the player I took. "Best available" has to mean the
    # best player on the board, or taking him would score as if I had
    # passed on myself: the first version excluded him, so a perfect pick
    # graded +20 against the second-best name instead of 0. The number
    # people want is how much they LEFT, and leaving nothing is zero.
    avail = [(value_of(p), p) for p in pool if p not in row["taken_before"]]
    avail = [(v, p) for v, p in avail if v is not None]
    avail.sort(reverse=True)

    best = avail[0] if avail else None
    row["value"] = mine_val
    # negative = someone better was sitting there; 0 = you took the best
    row["vs_board"] = (None if mine_val is None or not best
                       else round(mine_val - best[0], 1))
    row["best_available"] = ((name_of_pid(best[1]), best[0])
                             if best and best[1] != pid else None)

    adp = adp_of(pid)
    row["adp"] = adp
    # positive = he was still there later than the market said, so you paid
    # less than his price
    row["board_pos"] = row["overall"] + offset
    # SIGN. board_pos - adp, not adp - board_pos.
    #
    # Value is getting a player LATER than the room prices him: his ADP is
    # 40 and he lasts to 66, so you paid 26 picks less than his price and
    # vs_market is +26. A reach is the mirror -- ADP 183 taken at 56 is 127
    # picks of overpayment and reads -127.
    #
    # It shipped inverted, and the tests agreed with it, so all three 9/2
    # recaps printed exactly backwards. Geno Smith at 56 on an ADP of 183
    # was reported as "127 picks of value" when it is the largest reach in
    # the draft, and Xavier Worthy at board 128 on an ADP of 127 -- market
    # price to the pick -- was called the biggest reach.
    row["vs_market"] = (None if adp is None
                        else round(row["board_pos"] - adp, 1))
    return row


def verdict(row):
    """One short sentence per pick, or None when there is nothing to say."""
    b, m, v = row.get("vs_board"), row.get("vs_market"), row.get("value")
    bits = []
    if b is not None and b <= -1.0 and row.get("best_available"):
        bits.append(f"left {abs(b):.0f} on the board "
                    f"({row['best_available'][0].split(' (')[0]})")
    # Same gate as value, for the same reason. Stage two exists to fill
    # roster slots, and every body taken there is worth 0.0 over
    # replacement with an ADP in the hundreds -- which printed as
    # "reached 480 picks" on Ryquell Armstead. You cannot reach for
    # something that has no price worth paying.
    if m is not None and m <= -REACH_PICKS and (v or 0) > 0:
        bits.append(f"reached {abs(m):.0f} picks")
    # "600 picks of value" on a player worth 0.0 over replacement is a true
    # number saying a false thing. Getting a replacement-level body later
    # than his price is not a bargain, it is a late pick. Price only counts
    # as value when there is something to be valued.
    if m is not None and m >= STEAL_PICKS and (v or 0) > 0:
        bits.append(f"{m:.0f} picks of value")
    return "; ".join(bits) or None


def summarize(rows):
    """The three lines a manager reads first."""
    graded = [r for r in rows if r.get("vs_board") is not None]
    # Only players actually worth something can be a good or bad PRICE.
    # Without this the headline read "best price: Ryquell Armstead, 600
    # picks of value" -- a free agent worth zero, taken late, in a draft
    # whose whole purpose was filling roster slots.
    priced = [r for r in rows if r.get("vs_market") is not None
              and (r.get("value") or 0) > 0]
    out = {"picks": len(rows), "graded": len(graded), "priced": len(priced)}
    if graded:
        worst = min(graded, key=lambda r: r["vs_board"])
        out["worst_selection"] = worst if worst["vs_board"] <= -1.0 else None
        # NOT a sum. vs_board can only be zero or negative -- you cannot
        # take a player better than the best available -- so summing it
        # produced "net against the board: -2861.6 points", a true number
        # that measures nothing but how many picks you made.
        out["best_available_taken"] = sum(1 for r in graded
                                          if r["vs_board"] >= -1.0)
    if priced:
        out["best_price"] = max(priced, key=lambda r: r["vs_market"])
        out["worst_price"] = min(priced, key=lambda r: r["vs_market"])
        out["market_total"] = round(sum(r["vs_market"] for r in priced), 1)
    return out


def roster_shape_report(rows, pos_of, roster_positions):
    """What you drafted against what the league makes you start."""
    from battle_rhythm.roster_shape import slot_plan
    have = {}
    for r in rows:
        p = pos_of(r["pid"])
        if p:
            have[p] = have.get(p, 0) + 1
    need = {}
    for slot in roster_positions:
        if slot in ("BN", "IR", "TAXI"):
            continue
        need[slot] = need.get(slot, 0) + 1
    return have, need, slot_plan


# ------------------------------------------------------------------ runner

def run(fragment, as_json=None):
    from battle_rhythm.sleeper_client import players, get, state, name_of
    from battle_rhythm.draft_helper import (uid, season_projection_totals, _adp,
                                            adp_keys_for)
    from battle_rhythm.draft_review import demand_by_pos, replacement_at
    from battle_rhythm.dynasty_value import (load_params, dynasty_value,
                                             horizon_for)
    from battle_rhythm.dynasty_value import resolve_league

    lid = resolve_league(fragment)
    lg = get(f"league/{lid}") or {}
    season = lg.get("season") or state().get("season")
    tbl = players()
    totals = season_projection_totals(season, lg.get("scoring_settings") or {})
    # resolve_draft, not lg["draft_id"]. This module shipped with the bug
    # it was written to expose: the shared path was fixed and this one kept
    # asking the league for a draft id that names a COMPLETE draft with no
    # picks in it. See the drafts_by_id lint in paths.py.
    # Both Hybrids run TWO drafts a season -- a 10-rounder, then a second
    # to fill rosters out, because managers keep different numbers of
    # players (keepers.json, August). resolve_draft answers "which draft",
    # which between two real drafts is a guess; the 9/2 recap graded 120
    # picks and stage two was never in it. Grade them all, separately,
    # because a pick_no of 1 means something different in each.
    from battle_rhythm.draft_helper import season_drafts
    stages = season_drafts(lg)
    if not stages:
        raise SystemExit(f"{lg.get('name')}: no picks yet — nothing to recap")
    picks = [pk for _d, pks in stages for pk in pks]

    rp = lg.get("roster_positions") or []
    teams = lg.get("total_rosters") or 12
    dyn = (lg.get("settings") or {}).get("type") == 2
    keys, fb = adp_keys_for(rp, dyn, False)

    def pos_of(pid):
        return (tbl.get(pid) or {}).get("position")

    # ONE replacement bar for the whole recap, computed off the PRE-DRAFT
    # pool. draft_review recomputes it at every pick, which is right for
    # "what did the model think at the time"; a recap wants one yardstick so
    # the value column compares across picks instead of drifting under them.
    # Same rule the board uses -- demand_by_pos and replacement_at, not a
    # third copy. Three copies of the pick geometry is how all three ended
    # up wrong (draft_helper:450).
    avail_by_pos = {}
    for pid, pts in totals.items():
        ps = pos_of(pid)
        if ps:
            avail_by_pos.setdefault(ps, []).append(pts)
    for v in avail_by_pos.values():
        v.sort(reverse=True)
    demand = demand_by_pos(rp, teams)
    rep = replacement_at(avail_by_pos, demand, {}, teams)

    # A position the league does not START has no demand, so replacement_at
    # skips it, so rep.get(pos, 0.0) handed it a replacement bar of ZERO and
    # its raw projection became its value over replacement.
    #
    # Live consequence, 9/2: LG01 rosters no kicker, and the recap
    # named Brandon Aubrey the best player available at twenty of twenty-two
    # picks -- "worth 257 more" than the man he actually took. Every line of
    # that report was arithmetically correct and the whole thing was
    # nonsense. A player at a position you cannot start is not a candidate;
    # he is not on the board at all.
    STARTABLE = {p for p in demand if demand.get(p)}

    # In a DYNASTY or keeper league a one-season projection is the wrong
    # yardstick and it fails in one direction: it calls every young pick a
    # mistake. The first version graded LG01 on 2026 points alone
    # and reported taking Brock Bowers at 9 over Christian McCaffrey as
    # "left 44 on the board" -- Bowers is 23 and McCaffrey is 30 in a
    # league you keep forever. HANDOFF has said since 8/13 to read the
    # one-season model BESIDE dynasty_value, never instead of it, and this
    # tool did the thing the warning names.
    P = load_params()
    keeper_lg = False
    try:
        keeper_lg = bool(json.loads(
            __import__("battle_rhythm.paths", fromlist=["paths"])
            .data("keepers.json").read_text(encoding="utf-8"))
            .get(str(lid), {}).get("keeper"))
    except Exception:
        pass
    hz = horizon_for(P, dynasty=dyn, keeper=keeper_lg)
    multi = dyn or keeper_lg
    horizon_note = ("multi-season (dynasty curves, horizon %d)" % hz if multi
                    else "this season only")

    def value_of(pid):
        pts, ps = totals.get(pid), pos_of(pid)
        if pts is None or ps not in rep:
            return None          # no bar for this position = not a candidate
        if not multi:
            return round(pts - rep[ps], 1)
        age = (tbl.get(pid) or {}).get("age")
        return round(dynasty_value(ps, age, pts, P, repl=rep[ps], horizon=hz), 1)

    _ac = {}

    def raw_adp(pid):
        if pid not in _ac:
            try:
                _ac[pid] = _adp(pid, season, keys, fb)[0]
            except Exception:
                _ac[pid] = None
        return _ac[pid]

    def adp_of(pid):
        return _depleted.get(pid, raw_adp(pid))

    def nm(pid):
        return name_of(pid, tbl)

    # KEPT PLAYERS WERE NEVER ON THE BOARD.
    #
    # They are also never in the pick list, which is what this pool
    # subtracts from -- so the first version left every keeper in the
    # league "available" forever and named Jahmyr Gibbs the best player on
    # the board at all eleven of his picks in LG03. Gibbs
    # has been on another manager's roster since July.
    #
    # HOW MANY. The Hybrids keep 3 plus 2 drafted rookies plus taxi, so
    # roughly seven a team -- about 84 in a 12-team league, not the 265
    # an earlier version of this comment claimed. 265 is every rostered
    # player in that league, which is the right number for the board's ADP
    # header and the wrong one here. LG01 is the exception: full
    # dynasty, the whole roster carries, and there the depletion really is
    # nearly everything rostered. One league's number is not a rule
    # (CLAUDE.md lesson 6).
    #
    # The first version said kept = rostered - drafted, which swept every
    # in-season waiver add in with the keepers. That bias runs one way: it
    # thins the board, so your picks look better against it. The worst
    # possible direction for a tool whose whole job is grading you.
    #
    # A keeper was on the roster BEFORE the draft. A waiver add was not.
    # previous_league_id gives exactly that set, and keeper.py already
    # walks the chain for drafted-rookie eligibility. Intersecting the two
    # seasons is the discriminator; a startup has no previous season and
    # correctly keeps nobody.
    kept, kept_how = set(), ""
    if multi:
        try:
            from battle_rhythm.keeper import actual_kept
            now_rostered, _ = actual_kept(lid)
            drafted = {str(pk.get("player_id")) for pk in picks
                       if pk.get("player_id")}
            undrafted = {str(p) for p in now_rostered} - drafted
            prev_id = lg.get("previous_league_id")
            prev_rostered = ({str(p) for p in actual_kept(prev_id)[0]}
                             if prev_id else set())
            if prev_rostered:
                kept = undrafted & prev_rostered
                kept_how = ("on your league's rosters both seasons and "
                            "drafted in neither")
            else:
                # FALL BACK, do not give up. LG01 returned nothing
                # for the previous season on 9/2, the intersection came out
                # empty, and the recap then offered Colston Loveland -- who
                # is on his own roster -- as the player he should have taken
                # instead, at three separate picks.
                #
                # Rostered-and-undrafted over-counts by the league's
                # in-season waiver adds. That is a real bias and it is a far
                # smaller error than putting every kept player in a full
                # dynasty league back on the board. Say which rule ran so
                # the number can be read for what it is.
                kept = undrafted
                kept_how = ("on a roster and drafted in neither of this "
                            "season's drafts;\n   no previous season to "
                            "check against, so in-season adds are counted "
                            "with them")
        except Exception:
            kept = set()

    pool = [p for p in totals if pos_of(p) in STARTABLE and p not in kept]

    # DEPLETED ADP, not market ADP.
    #
    # ADP is priced in drafts where everyone was available. This league
    # removes 77 players before a pick is made, so a name the market calls
    # 60 really goes around 60 minus however many keepers rank above him.
    # Comparing a global price to a depleted draft's pick numbers makes
    # EVERY pick look like a reach, which is exactly what the 9/2 recap
    # printed: 20 of 20 negative, including picks that were obviously fine.
    #
    # The board has done this since 8/13 and says so in its own header;
    # lineup_value since 8/11; keeper.py learned it on 8/11 when it called
    # Derrick Henry reclaimable at 65 with thirty keepers ranked above him.
    # Same deplete_adp, not a fourth version of the idea.
    _depleted = {}
    if kept:
        from battle_rhythm.lineup_value import deplete_adp
        # ONLY THE PICKS. The first version depleted every player in the
        # pool -- thousands of _adp lookups for a number nothing reads.
        # grade() asks for the ADP of the player you took and of nobody
        # else; the board comparison ranks on value, not price. It wedged
        # the MCP server, which answers calls one at a time, so the next
        # request queued behind it and `leagues` timed out too.
        #
        # Do the work the output needs, not the work the idea suggests.
        mine_pids = {str(pk.get("player_id")) for pk in picks
                     if pk.get("player_id") and pk.get("picked_by") == uid()}
        rows_for_shift = [{"pid": pid, "adp": raw_adp(pid)}
                          for pid in mine_pids]
        kept_adps = [a for a in (raw_adp(k) for k in kept) if a is not None]
        deplete_adp(rows_for_shift, kept_adps)
        _depleted = {r["pid"]: r["adp"] for r in rows_for_shift
                     if r.get("adp") is not None}


    # Feed each stage the picks that came BEFORE it, so taken_before knows
    # stage one emptied the board for stage two, then keep only the rows
    # belonging to the stage being graded.
    rows, by_stage, prior = [], [], []
    me = uid()
    for d, spicks in stages:
        did = d.get("draft_id")
        stage_rows = [r for r in recap_rows(prior + spicks, me, value_of,
                                            adp_of, nm, teams)
                      if r["pid"] and any(pk.get("_draft_id") == did
                                          and pk.get("player_id") == r["pid"]
                                          for pk in spicks)]
        for r in stage_rows:
            grade(r, pool, value_of, adp_of, nm, offset=len(prior))
        by_stage.append((d, stage_rows))
        rows.extend(stage_rows)
        prior = prior + spicks
    s = summarize(rows)

    print(f"\n══ {lg.get('name')} — draft recap ({len(picks)} picks, "
          f"{len(rows)} yours)")
    print("   vs BOARD: what was still available when you picked (selection)")
    print("   vs MARKET: his ADP against the pick you spent (price).")
    print("      + means he lasted past his price; - means you took him "
          "early.")
    print(f"   value is {horizon_note}.")
    if kept:
        print(f"   {len(kept)} kept players -- {kept_how} -- are off the "
              f"board,")
        print("   and every ADP below is SHIFTED EARLIER by the keepers "
              "ranked above it.\n   Depleted numbers, not market ones.")
    if len(stages) > 1:
        print(f"   {len(stages)} drafts this season; each is graded on its "
              f"own pick numbers.")
    print("   Graded on draft-day information only. Whether he is good is "
          "next season's question.\n")
    for i, (d, stage_rows) in enumerate(by_stage, 1):
        if len(by_stage) > 1:
            print(f"  ── draft {i} of {len(by_stage)} "
                  f"({d.get('settings', {}).get('rounds') or '?'} rounds, "
                  f"{len(stage_rows)} of them yours)")
        if not stage_rows:
            print("     nothing of yours in this one.\n")
            continue
        print(f"{'pick':>5} {'rd':>3}  {'value':>7} {'board':>7} "
              f"{'market':>7}  player")
        for r in sorted(stage_rows, key=lambda r: r["overall"]):
            v = f"{r['value']:>7.1f}" if r["value"] is not None else "      -"
            b = (f"{r['vs_board']:>+7.1f}" if r["vs_board"] is not None
                 else "      -")
            m = (f"{r['vs_market']:>+7.0f}" if r["vs_market"] is not None
                 else "      -")
            bp = ("" if r.get("board_pos", r["overall"]) == r["overall"]
                  else f" [board {r['board_pos']}]")
            print(f"{r['overall']:>5} {r['round'] or '-':>3}  {v} {b} {m}  "
                  f"{r['name']}{bp}")
            note = verdict(r)
            if note:
                print(f"{'':>27}  {note}")
        print()

    print()
    if s.get("best_price"):
        r = s["best_price"]
        print(f"  best price:  {r['name']} at board {r['board_pos']}, "
              f"ADP {r['adp']:.0f} — {r['vs_market']:.0f} picks of value")
    if s.get("worst_price") and (s["worst_price"]["vs_market"] or 0) < 0:
        r = s["worst_price"]
        print(f"  biggest reach: {r['name']} at board {r['board_pos']}, "
              f"ADP {r['adp']:.0f}")
    if s.get("worst_selection"):
        r = s["worst_selection"]
        print(f"  worst selection: {r['name']} at {r['overall']} — "
              f"{r['best_available'][0]} was there, worth "
              f"{abs(r['vs_board']):.0f} more")
    if s.get("market_total") is not None:
        print(f"  net against the market: {s['market_total']:+.0f} picks "
              f"across {s['priced']} priced picks")
    if s.get("best_available_taken") is not None:
        print(f"  took the best player on the board: "
              f"{s['best_available_taken']} of {s['graded']} picks")

    have, need, _ = roster_shape_report(rows, pos_of, rp)
    print("\n  what you drafted:  "
          + "  ".join(f"{p}{n}" for p, n in sorted(have.items())))
    print("  what you start:    "
          + "  ".join(f"{p}{n}" for p, n in sorted(need.items())))
    unfilled = [p for p, n in need.items()
                if p in ("K", "DEF") and have.get(p, 0) < n]
    if unfilled:
        print(f"  *** REQUIRED SLOT EMPTY: {', '.join(unfilled)} — "
              "pick one up before week 1")

    if as_json:
        with open(as_json, "w") as f:
            json.dump({"league": lg.get("name"), "league_id": lid,
                       "picks": [{k: v for k, v in r.items()
                                  if k != "taken_before"} for r in rows],
                       "summary": {k: (v if not isinstance(v, dict)
                                       else {kk: vv for kk, vv in v.items()
                                             if kk != "taken_before"})
                                   for k, v in s.items()}}, f, indent=2)
        print(f"\nwrote {as_json}")


# ----------------------------------------------------------------- selftest

def selftest():
    n = 0

    def check(label, cond):
        nonlocal n
        print(f"  {'ok ' if cond else 'XX '} {label}")
        assert cond, label
        n += 1

    VAL = {"a": 100.0, "b": 60.0, "c": 40.0, "d": 10.0, "e": 5.0}
    ADP = {"a": 1.0, "b": 2.0, "c": 30.0, "d": 4.0, "e": 5.0}
    NAME = {p: f"P{p.upper()} (RB, X)" for p in VAL}
    picks = [{"player_id": "a", "picked_by": "them", "pick_no": 1, "round": 1},
             {"player_id": "b", "picked_by": "me",   "pick_no": 2, "round": 1},
             {"player_id": "d", "picked_by": "them", "pick_no": 3, "round": 1},
             {"player_id": "c", "picked_by": "me",   "pick_no": 4, "round": 1}]
    pool = list(VAL)
    rows = recap_rows(picks, "me", VAL.get, ADP.get, NAME.get, 2)
    check("only my picks are graded", [r["pid"] for r in rows] == ["b", "c"])

    for r in rows:
        grade(r, pool, VAL.get, ADP.get, NAME.get)
    by = {r["pid"]: r for r in rows}

    # pick 2: A was gone, B (60) was the best left. Perfect selection.
    check("taking the best available scores 0 vs board",
          by["b"]["vs_board"] == 0.0)
    # pick 4: D (10) was gone too, so C (40) was the best left.
    check("board pool shrinks with the draft, not with my picks",
          by["c"]["vs_board"] == 0.0)
    # B at pick 2 with ADP 2 is exactly market price.
    check("paying market price scores 0 vs market",
          by["b"]["vs_market"] == 0.0)
    # C at pick 4 with an ADP of 30: the room takes him around 30 and this
    # took him at 4. That is a REACH of 26 picks, and the first version of
    # this test asserted it as value -- the test agreed with the bug, which
    # is why the sign survived to print three backwards recaps.
    check("taking a player 26 picks before his ADP is a reach, not value",
          by["c"]["vs_market"] == -26.0)
    check("and it is called out", "reached 26 picks" in (verdict(by["c"]) or ""))

    # The mirror: a player who LASTS past his price is the bargain.
    late = {"overall": 40, "pid": "b", "name": NAME["b"], "round": 4,
            "taken_before": {"a"}}
    grade(late, pool, VAL.get, ADP.get, NAME.get)
    check("a player who lasts 38 picks past his ADP is 38 picks of value",
          late["vs_market"] == 38.0)
    check("and that is what the sentence says",
          "38 picks of value" in (verdict(late) or ""))

    # The two yardsticks must be able to disagree. Take the cheap wrong guy.
    picks2 = [{"player_id": "c", "picked_by": "me", "pick_no": 1, "round": 1}]
    r2 = recap_rows(picks2, "me", VAL.get, ADP.get, NAME.get, 2)
    grade(r2[0], pool, VAL.get, ADP.get, NAME.get)
    check("reaching for the wrong player is reported as both",
          r2[0]["vs_market"] == -29.0 and r2[0]["vs_board"] == -60.0)
    v = verdict(r2[0])
    check("and the sentence says both", "left 60 on the board" in v
          and "reached 29 picks" in v)

    # A pick with no ADP (every IDP defender) must not crash or be graded.
    picks3 = [{"player_id": "z", "picked_by": "me", "pick_no": 1, "round": 1}]
    r3 = recap_rows(picks3, "me", VAL.get, ADP.get, NAME.get, 2)
    grade(r3[0], pool, VAL.get, ADP.get, NAME.get)
    check("an unpriced player yields no market verdict rather than a zero",
          r3[0]["vs_market"] is None and r3[0]["value"] is None)
    check("and summarize counts him out instead of averaging him in",
          summarize(r3)["priced"] == 0)

    # ---- run() end to end, with the network stubbed.
    #
    # The pure functions above passed while run() still called
    # replacement_levels(totals, tbl, rp, teams) -- four positional
    # arguments to a function that takes (by_pos, demand_team, teams).
    # It parsed, it imported, and it would have raised on draft morning,
    # which is the one morning it gets used. Exercising the wiring is the
    # only thing that catches a wrong call in a branch nothing runs.
    import io
    import contextlib
    from battle_rhythm import sleeper_client as sc
    from battle_rhythm import draft_helper as dh
    from battle_rhythm import dynasty_value as dv

    tbl = {"a": {"position": "RB", "full_name": "A Back", "team": "X"},
           "b": {"position": "WR", "full_name": "B Wide", "team": "X"},
           "c": {"position": "QB", "full_name": "C Arm", "team": "X"},
           "d": {"position": "DEF", "full_name": "D Def", "team": "X"},
           # a second quarterback, so the one he took is worth something
           # over replacement. With one QB in the pool the replacement bar
           # lands on him, his value is 0, and the value-pick check then
           # fails for the right reason -- the new guard suppresses
           # "picks of value" on a player worth nothing.
           "e": {"position": "QB", "full_name": "E Backup", "team": "X"}}
    lg = {"name": "Stub", "season": "2026", "scoring_settings": {"x": 1},
          "total_rosters": 2, "draft_id": "d1", "settings": {"type": 0},
          "roster_positions": ["QB", "RB", "WR", "DEF", "BN"]}
    saved = (sc.get, sc.players, sc.state, dh.get, dh.uid,
             dh.season_projection_totals, dh._adp, dv.resolve_league)
    try:
        picks = [{"player_id": "a", "picked_by": "me", "pick_no": 1, "round": 1},
                 {"player_id": "b", "picked_by": "you", "pick_no": 2, "round": 1},
                 {"player_id": "c", "picked_by": "me", "pick_no": 3, "round": 2}]

        # The stub must answer draft/<id> AND draft/<id>/picks separately
        # now: run() resolves the draft object before reading picks. The
        # first version returned the pick LIST for both and blew up with
        # "'list' object has no attribute 'get'" -- which is the stub
        # being wrong about the API, not the code.
        d1 = {"draft_id": "d1", "status": "complete", "season": "2026",
              "start_time": 1, "settings": {"rounds": 2}}

        def fake_get(path):
            if path.endswith("/drafts"):
                return [d1]
            if path.endswith("/picks"):
                return picks
            if path.startswith("draft/"):
                return d1
            if path.startswith("league/"):
                return lg
            return {}

        sc.get = dh.get = fake_get
        sc.players = lambda force=False: tbl
        sc.state = lambda: {"season": "2026"}
        dh.uid = lambda: "me"
        dh.season_projection_totals = lambda season, scoring, **kw: {
            "a": 300.0, "b": 250.0, "c": 400.0, "d": 90.0, "e": 100.0}
        dh._adp = lambda pid, season, keys, fb=(): (
            {"a": (1.0, True), "b": (2.0, True), "c": (40.0, True),
             "d": (None, False), "e": (200.0, True)}[pid])
        dv.resolve_league = lambda frag: "L1"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run("stub")
        text = buf.getvalue()
    finally:
        (sc.get, sc.players, sc.state, dh.get, dh.uid,
         dh.season_projection_totals, dh._adp, dv.resolve_league) = saved

    check("run() completes against a stubbed league", "draft recap" in text)
    check("a redraft league is graded on this season only",
          "this season only" in text)
    check("it grades only my two picks", "2 yours" in text)
    check("it names the value pick", "picks of value" in text)
    check("it reports the roster shape", "what you drafted" in text)
    check("and it names a required slot nobody drafted",
          "REQUIRED SLOT EMPTY" in text and "DEF" in text)

    # ---- the DYNASTY branch, which the redraft stub above never enters.
    #
    # The kicker bug and the replacement_levels signature bug both lived in
    # code that no test executed. A branch selected by league type is a
    # branch, and the first version of this tool graded a dynasty draft on
    # one-season points and called every young pick a mistake.
    # keeper.py did `from ... import get` at import time, so keeper.get is
    # its OWN binding. Patching sleeper_client.get does not reach it, and
    # the depletion branch then behaved differently standalone (real get,
    # network error, swallowed) than inside test_all (a get some earlier
    # test had already rebound). A branch whose result depends on which
    # suite is running is not tested. Patch the binding that is actually
    # called.
    from battle_rhythm import keeper as kp
    saved2 = (sc.get, sc.players, sc.state, dh.get, dh.uid,
              dh.season_projection_totals, dh._adp, dv.resolve_league, kp.get)
    try:
        # four rosters and two filler backs, so the RB replacement bar
        # sits well BELOW the two players under test. With two teams and
        # two equal backs the bar lands on them and both surplus to zero,
        # which looks like a passing test and proves nothing.
        dyn_lg = dict(lg, settings={"type": 2}, name="Stub Dynasty",
                      total_rosters=4, previous_league_id="L1",
                      league_id="L2", draft_id="s1")
        # same projection, different ages. In a dynasty league the 23-year
        # old must outrank the 31-year old; in redraft they tie.
        young, old_ = "y", "o"
        tbl2 = {young: {"position": "RB", "age": 23, "full_name": "Young Back",
                        "team": "X"},
                old_: {"position": "RB", "age": 31, "full_name": "Old Back",
                       "team": "X"},
                "f1": {"position": "RB", "age": 27, "full_name": "Filler One",
                       "team": "X"},
                "f2": {"position": "RB", "age": 27, "full_name": "Filler Two",
                       "team": "X"},
                # rostered since July, never in this draft's picks. The
                # best player alive, and he must not appear as "available".
                "kept": {"position": "RB", "age": 24, "full_name": "Kept Star",
                         "team": "X"}}
        dpicks = [{"player_id": young, "picked_by": "me", "pick_no": 1,
                   "round": 1},
                  {"player_id": old_, "picked_by": "me", "pick_no": 2,
                   "round": 1}]

        # TWO stages, so the per-stage grading is actually exercised.
        s1 = {"draft_id": "s1", "status": "complete", "season": "2026",
              "start_time": 1, "settings": {"rounds": 1}}
        s2 = {"draft_id": "s2", "status": "complete", "season": "2026",
              "start_time": 2, "settings": {"rounds": 1}}
        stage2 = [{"player_id": "f1", "picked_by": "me", "pick_no": 1,
                   "round": 1}]

        def fake_get2(path):
            if path.endswith("/drafts"):
                return [s2, s1]                 # unordered on purpose
            if path == "draft/s1/picks":
                return dpicks
            if path == "draft/s2/picks":
                return stage2
            if path.endswith("/picks"):
                return dpicks
            if path.endswith("/rosters"):
                # "kept" is on BOTH seasons' rosters and in neither draft.
                return [{"roster_id": 1, "owner_id": "them",
                         "players": ["kept"], "taxi": []}]
            if path.startswith("draft/"):
                return s1
            if path.startswith("league/"):
                return dyn_lg
            return {}

        sc.get = dh.get = kp.get = fake_get2
        sc.players = lambda force=False: tbl2
        sc.state = lambda: {"season": "2026"}
        dh.uid = lambda: "me"
        dh.season_projection_totals = lambda season, scoring, **kw: {
            young: 400.0, old_: 400.0, "f1": 100.0, "f2": 50.0,
            "kept": 900.0}
        dh._adp = lambda pid, season, keys, fb=(): (10.0, True)
        dv.resolve_league = lambda frag: "L2"

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            run("stub-dynasty")
        dtext = buf2.getvalue()
    finally:
        (sc.get, sc.players, sc.state, dh.get, dh.uid,
         dh.season_projection_totals, dh._adp, dv.resolve_league,
         kp.get) = saved2

    check("a dynasty league says it is graded over multiple seasons",
          "multi-season" in dtext and "dynasty curves" in dtext)
    vals = {}
    for line in dtext.splitlines():
        for who in ("Young Back", "Old Back"):
            if line.rstrip().endswith(f"{who} (RB, X)"):
                vals[who] = float(line.split()[2])
    check("both players were actually valued above replacement",
          len(vals) == 2 and min(vals.values()) > 0)
    check("and the 23-year-old outvalues the 31-year-old on equal projection",
          vals["Young Back"] > vals["Old Back"])
    # The real 9/2 symptom: a kept player named as best-available at every
    # pick. He is rostered and absent from the picks, so he was never on
    # the board -- and he is the highest projection in the fixture, so if
    # the depletion is skipped he WILL show up.
    check("a kept player is not offered as the player you should have taken",
          "Kept Star" not in dtext)
    check("and the recap says how many were kept",
          "kept players" in dtext)
    # Which rule produced the number changes how it should be read, so it
    # has to be on the page. Silence here is what let LG01 report
    # zero keepers in a league where the whole roster carries over.
    # Comparing a global ADP to a keeper-depleted draft made all 20 of his
    # LG03 picks read as reaches. The board has depleted
    # since 8/13 and says so in its header; this must too, and must say so.
    check("a keeper league's ADPs are depleted, and the header says so",
          "SHIFTED EARLIER" in dtext)
    check("and says HOW it decided they were kept",
          "both seasons" in dtext or "no previous season" in dtext)
    check("both stages of a two-stage draft are graded",
          "draft 1 of 2" in dtext and "draft 2 of 2" in dtext)
    check("the stage-two pick is in there",
          "Filler One" in dtext)
    # Stage two renumbers from 1, and ADP is one global market. Without the
    # offset a stage-two pick 1 was compared to ADP as though it were the
    # first player off the board, which read as hundreds of picks of value
    # on free agents. The board position must be shown and must differ.
    check("a later stage's picks carry their real board position",
          "[board " in dtext)

    print(f"\nselftest PASSED  ({n})")
    raise SystemExit(0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        selftest() if a else sys.exit(__doc__)
    out = a[a.index("--json") + 1] if "--json" in a else None
    run(a[0], as_json=out)
