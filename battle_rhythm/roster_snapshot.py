"""
roster_snapshot.py — write roster.md: what you hold, what you still need,
and what the hard constraints are, for every league.

    python roster_snapshot.py            # all leagues -> roster.md
    python roster_snapshot.py dynasty    # one league
    python roster_snapshot.py --selftest # offline

Why this exists: a session reading HANDOFF.md for roster context is
reading a snapshot someone typed by hand at some past pick. That went
wrong on 8/11 — three straight pick recommendations were made against a
roster 18 picks stale, and the real answer (five running backs already,
no defense, one quarterback) was sitting in the picks feed the whole
time.

Sleeper's roster endpoint returns EMPTY during a slow draft; the truth
lives in the picks feed until the draft completes. This merges both, the
same way roster_map.ownership does.

roster.md is regenerated, never edited by hand. If it disagrees with
your roster, rerun it.
"""

import json
import pathlib
from battle_rhythm import paths as _paths
import sys
from collections import defaultdict

# roster.md stays at the repo ROOT and stays tracked — CLAUDE.md
# explains why (its staleness fails quietly, so git status is the
# tell). Anchored to paths.REPO, not to this file's directory.
OUT = _paths.REPO / "roster.md"

# which real positions can fill a flex-ish slot
# Roster geometry lives in roster_shape.py. DEDICATED was this
# file's name for the tuple dynasty_value called DEDICATED_SLOTS;
# both now point at the same object.
from battle_rhythm.roster_shape import (FLEX_FILL, DEDICATED,  # noqa: E402,F401
                          slot_plan)


def fill(ded, flex, have):
    """Greedy: dedicated slots first, then flex from leftovers.
    Returns (filled {slot: (used, need)}, leftover {pos: n}, gaps [slot])."""
    pool = dict(have)
    filled, gaps = {}, []
    for pos, n in ded.items():
        used = min(pool.get(pos, 0), n)
        pool[pos] = pool.get(pos, 0) - used
        filled[pos] = (used, n)
        if used < n:
            gaps += [pos] * (n - used)
    for slot, fills in flex:
        took = None
        # spend the deepest position first so a scarce one is not wasted
        for p in sorted(fills, key=lambda p: -pool.get(p, 0)):
            if pool.get(p, 0) > 0:
                pool[p] -= 1
                took = p
                break
        filled[slot] = ((1, 1) if took else (0, 1))
        if not took:
            gaps.append(slot)
    return filled, {p: n for p, n in pool.items() if n > 0}, gaps


# how a flex slot's demand splits across the positions that can fill it
# One definition, in roster_shape.py. This block was byte-identical in
# draft_review, roster_snapshot and weekly.
from battle_rhythm.roster_shape import FLEX_SHARE  # noqa: E402,F401


def starters_per_team(pos, ded, flex):
    """How many players at `pos` a typical team starts, flex included."""
    n = float(ded.get(pos, 0))
    for slot, _fills in flex:
        n += FLEX_SHARE.get(slot, {}).get(pos, 0.0)
    return n


def thin_bar(totals, tbl, pos, teams, ded=None, flex=None):
    """Projection below which a 'filled' slot is filled in name only.

    THE BUG THIS FIXES. This file reported LG03-LG05 as QB 1/1 (Jalen
    Milroe, proj 15) with the slot green. Slot occupancy is not slot
    adequacy, and a file whose whole job is "what must still be filled"
    cannot count bodies.

    THE BUG THIS *ALSO* FIXES (8/11, second pass). The first bar was
    teams x 1 starter, so a 12-team league got a WR12 bar — a WR1-level
    line — in a league that starts two receivers plus two flexes and
    therefore starts about 35 of them. It flagged five of nine LG01 starters, including three perfectly ordinary ones. A warning
    that fires on the majority of a lineup is not a warning.

    The bar is now the (teams x starters-at-that-position)-th best
    projection, counting each flex slot at its positional share. Two WR
    slots plus two FLEX in a 12-team league is 12 x (2 + 2x0.45) = WR35.
    Superflex puts QB at 12 x (1 + 0.85) = QB22.
    """
    ranked = sorted((v for pid, v in totals.items()
                     if (tbl.get(pid) or {}).get("position") == pos),
                    reverse=True)
    if not ranked:
        return 0.0
    per = starters_per_team(pos, ded or {}, flex or [])
    n = max(1, int(round(float(teams) * (per if per > 0 else 1.0))))
    return ranked[min(n, len(ranked)) - 1]


def league_block(lg, tbl, mine, draft, picks_made, my_picks_left, rules,
                 totals=None, taxi_ids=None, picks_note=""):
    """`mine` is everyone you control; `taxi_ids` is the subset parked on
    the taxi squad.

    TAXI PLAYERS DO NOT FILL STARTING SLOTS. The first version merged
    taxi into the active roster and then used them to fill the lineup:
    LG03-LG05 came back QB 1/1 (Jalen Milroe) and RB 2/2 (Henry, Brashard
    Smith) with both of those names sitting on the taxi squad, unable to
    play. That turned two genuinely empty starting slots green in the one
    file whose job is to say what still needs filling. keepers.json has
    said "taxi players do NOT consume an active roster spot" the whole
    time; this code just did not read it."""
    rp = lg.get("roster_positions") or []
    # `load_leagues` does not carry a season, so this fell through to the
    # literal "current" and printed "a rookie YOU draft in current" (8/13).
    # "this year" reads correctly whether or not the season is known.
    season_hint = str(lg.get("season") or "").strip() or "this year"
    ded, flex, bench = slot_plan(rp)
    starters = sum(ded.values()) + len(flex)
    settings = lg.get("settings") or {}
    taxi = settings.get("taxi_slots") or 0
    active = starters + bench
    cap = active + taxi

    from battle_rhythm.dynasty_value import taxi_split
    taxi_ids = set(taxi_ids or ())
    # Taxi is a ONE-YEAR rookie redshirt. Anyone whose redshirt was last
    # season is coming OFF onto the active roster and his seat frees up
    # for this year's rookie class — he is a starter, not a stashed body.
    redshirt, expired, unknown = taxi_split(taxi_ids, tbl)
    redshirt |= unknown
    on_taxi = [(tbl.get(pid) or {}, pid) for pid in redshirt]
    coming_off = [(tbl.get(pid) or {}, pid) for pid in expired]
    act = [pid for pid in mine if pid not in redshirt]

    have = defaultdict(int)
    by_pos = defaultdict(list)
    for pid in act:
        m = tbl.get(pid) or {}
        p = m.get("position")
        if not p:
            continue
        have[p] += 1
        by_pos[p].append((m.get("full_name") or pid, m.get("team") or "FA",
                          m.get("age"), (totals or {}).get(pid, 0.0)))
    # BEST first, not roster order. The first run put Milroe (proj 15) in
    # the QB slot ahead of Jayden Daniels (proj 382) purely because he
    # sorted earlier, which made the one row that mattered read wrong.
    for p in by_pos:
        by_pos[p].sort(key=lambda x: -(x[3] or 0))
    filled, leftover, gaps = fill(ded, flex, have)
    teams_n = lg.get("total_teams") or 12
    bars = ({p: thin_bar(totals, tbl, p, teams_n, ded, flex) for p in by_pos}
            if totals else {})

    L = [f"## {lg.get('name')}"]
    status = lg.get("status") or "?"
    dstat = (draft or {}).get("status")
    rounds = ((draft or {}).get("settings") or {}).get("rounds")
    total_picks = (rounds or 0) * (lg.get("total_teams") or 12)
    L.append(f"`{lg.get('league_id')}` · {status}"
             + (f" · draft {dstat} {picks_made}/{total_picks}"
                if draft else "")
             + f" · {lg.get('total_teams')} teams")
    sflex = any(s == "SUPER_FLEX" for s, _f in flex) or ded.get("QB", 0) >= 2
    tags = []
    if (settings.get("type")) == 2:
        tags.append("dynasty-typed")
    if rules.get("keeper"):
        tags.append("LIMITED KEEPER — carries a few, churns the rest")
    if sflex:
        tags.append("SUPERFLEX (starts 2 QB)")
    if tags:
        L.append("**" + " · ".join(tags) + "**")
    L.append("")

    L.append("### Starting slots")
    L.append("")
    L.append("| slot | filled | who | proj |")
    L.append("|---|---|---|---|")
    thin_seen = []
    taken = {p: 0 for p in by_pos}

    def _label(nm, pr, pos):
        bar = bars.get(pos)
        if bar and pr < bar:
            thin_seen.append((nm, pos, pr, bar))
            return f"{nm} **THIN**", f"{pr:.0f} (bar {bar:.0f})"
        return nm, (f"{pr:.0f}" if totals else "—")

    for pos, n in ded.items():
        used, need = filled.get(pos, (0, n))
        picks_ = by_pos.get(pos, [])[:need]
        taken[pos] = taken.get(pos, 0) + len(picks_)
        cells = [_label(nm, pr, pos) for nm, _t, _a, pr in picks_]
        who = ", ".join(c[0] for c in cells)
        prj = ", ".join(c[1] for c in cells)
        mark = "" if used >= need else "  **EMPTY**"
        L.append(f"| {pos} x{need} | {used}/{need}{mark} | {who or '—'} "
                 f"| {prj or '—'} |")
    for slot, fills in flex:
        used, need = filled.get(slot, (0, 1))
        mark = "" if used else "  **EMPTY**"
        # NAME the flex occupant. The first run printed "from RB/WR/TE" even
        # at 1/1, hiding the starter on the row where it mattered most.
        best = None
        for p in fills:
            rest = by_pos.get(p, [])[taken.get(p, 0):]
            if rest and (best is None or (rest[0][3] or 0) > (best[1] or 0)):
                best, best_pos = (rest[0][0], rest[0][3]), p
        if used and best:
            taken[best_pos] = taken.get(best_pos, 0) + 1
            nm, prj = _label(best[0], best[1] or 0.0, best_pos)
            L.append(f"| {slot} | {used}/{need} | {nm} | {prj} |")
        else:
            L.append(f"| {slot} | {used}/{need}{mark} | — (from "
                     f"{'/'.join(fills)}) | — |")
    L.append("")
    if thin_seen:
        L.append("> **Slots filled in name only.** These count as filled "
                 "above but project below the replacement bar for the "
                 "position — treat them as OPEN when planning picks:")
        for nm, pos, pr, bar in thin_seen:
            L.append(f"> - {nm} ({pos}) projects {pr:.0f} vs a "
                     f"{pos}{max(1, int(round(teams_n * starters_per_team(pos, ded, flex))))}"
                     f" bar of {bar:.0f} — the last startable "
                     f"{pos} in a {teams_n}-team league")
        L.append("")

    L.append("### Capacity")
    L.append("")
    L.append(f"- starters **{starters}** + bench **{bench}** = active "
             f"**{active}**" + (f" · taxi **{taxi}**" if taxi else
                                " · taxi none reported"))
    # ACTIVE capacity is what draft picks compete for. Taxi is a separate
    # pool with its own seats; counting the two together hid two empty
    # starting slots behind two taxi bodies.
    L.append(f"- active capacity **{active}** · active rostered "
             f"**{len(act)}** · open **{active - len(act)}**")
    free = max(0, taxi - len(on_taxi))
    if taxi or on_taxi or coming_off:
        def _names(rows):
            return ", ".join(
                f"{(m.get('full_name') or pid)} ({m.get('position') or '?'}"
                + (f", proj {totals.get(pid, 0):.0f}" if totals else "")
                + ")" for m, pid in rows) or "—"
        L.append(f"- taxi **{len(on_taxi)}/{taxi} seats used** — "
                 f"{_names(on_taxi)}")
        L.append("  - a taxi seat is a ONE-YEAR rookie redshirt: free "
                 "storage, no bench spot, and he cannot play this season")
        if coming_off:
            L.append(f"- redshirt EXPIRED, now on your active roster — "
                     f"{_names(coming_off)}")
            L.append("  - counted as active above. Their seats are open "
                     "for THIS year's rookie class, and they arrive still "
                     "eligible for a drafted-rookie keeper slot")
        if free > 0:
            L.append(f"- **{free} taxi seat(s) open** — only a rookie YOU "
                     f"draft {season_hint} is eligible; a seat may be "
                     f"left empty at no cost")
    if my_picks_left is not None:
        # A TAXI SEAT IS AN OPTION, NOT A COMMITMENT. Corrected by the
        # user the same day this was written: seats must be filled by the
        # start of the season or they simply stay empty, an empty seat
        # costs nothing, and NEITHER draft is obliged to fill one. The
        # first version subtracted open seats from the pick count as
        # though they were already spent, understating the picks
        # available for the lineup by exactly the number of open seats.
        # Score on the raw count. The seats get their own line below,
        # because they compete for these picks without claiming them.
        short = (active - len(act)) - my_picks_left
        # Both Hybrids run TWO drafts: managers keep different numbers of
        # players, so the commissioner drafts 10 rounds and then holds a
        # second draft to fill rosters out. Finishing the first one under
        # capacity is the design, not a shortfall — and reading it as a
        # warning would push toward drafting for depth over value.
        if short > 0 and rules.get("supplemental_draft"):
            tail = (f"  — {short} slot(s) left for the SECOND draft "
                    f"(this league drafts in two stages; expected)")
        elif short > 0:
            tail = "  — you will finish UNDER capacity"
        elif short < 0 and free > 0:
            tail = (f"  — {-short} spare, and {free} open taxi seat(s) can "
                    f"absorb them")
        elif short < 0:
            tail = f"  — {-short} spare; some will be cuts"
        else:
            tail = "  — exactly filling out"
        L.append(f"- picks remaining **{my_picks_left}** for "
                 f"**{active - len(act)}** open ACTIVE slots" + tail)
        if free > 0:
            L.append(f"  - **{free}** taxi seat(s) compete for these same "
                     f"picks but do not claim them: a seat may be left "
                     f"empty at no cost, and can be filled from EITHER "
                     f"draft — but only with a rookie YOU draft this year")
        # WHERE THE COUNT CAME FROM, always. The caller knows whether it
        # read real ownership, walked a seat, or guessed one-per-round,
        # and this line is the only place that can say so. It used to be
        # bolted on afterwards with str.replace against an anchor string
        # — the same trick that silently dropped the bye block on 8/13
        # when the anchor moved.
        if picks_note:
            L.append(f"  - {picks_note}")
    L.append("")

    L.append("### Room by position")
    L.append("")
    # POSITIONS COME FROM THE LEAGUE, NOT FROM A LITERAL. This tuple used
    # to be hardcoded ("QB","RB","WR","TE","K","DEF"), so the IDP league's
    # DL, LB and DB — three of its eleven starting slots — were absent
    # from the one section that reports how many of each you hold. Same
    # defect as lineup_value's hardcoded `live` set, which recommended
    # six quarterbacks for a one-QB league (8/13).
    ordered = ["QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"]
    room_pos = [p for p in ordered
                if p in ded or p in {x for _s, f in flex for x in f}]
    room_pos += [p for p in sorted(ded) if p not in room_pos]
    for p in room_pos:
        n = have.get(p, 0)
        need = ded.get(p, 0)
        note = ""
        if n == 0 and need:
            note = "  ← **REQUIRED SLOT, NONE ROSTERED**"
        # BELOW REQUIREMENT MUST READ LOUDER THAN AT REQUIREMENT. This
        # branch did not exist, so a position holding 1 of 2 required
        # printed bare while a fully-staffed one got "no insurance" — the
        # emoji Hybrid's RB, its single worst hole, was the only line in
        # the section with no marker on it (8/13).
        elif need and n < need:
            note = f"  ← **SHORT {n} of {need}**"
        elif need and n == need:
            note = "  ← no insurance"
        elif n >= need + 3 and need:
            note = "  ← saturated"
        names = ", ".join(
            f"{nm} ({t} {a}" + (f", proj {pr:.0f}" if totals else "") + ")"
            for nm, t, a, pr in sorted(by_pos.get(p, []),
                                       key=lambda x: -(x[3] or 0)))
        L.append(f"- **{p} {n}**{note}")
        if names:
            L.append(f"  - {names}")
    L.append("")

    L.append("### What must still be filled")
    L.append("")
    if gaps:
        for g in gaps:
            L.append(f"- **{g}** — starting slot, unfilled")
    if thin_seen:
        for nm, pos, pr, _b in thin_seen:
            L.append(f"- **{pos}** — nominally filled by {nm} "
                     f"(proj {pr:.0f}); treat as unfilled")
    # DANGLING ELSE. This clause hung off `thin_seen` alone, so a roster
    # with real gaps and no thin starters printed eleven unfilled slots
    # and then "all starting slots covered" directly beneath them. Three
    # leagues did exactly that on 8/13. It is the all-clear, so it must
    # answer to BOTH lists.
    if not gaps and not thin_seen:
        L.append("- all starting slots covered; remaining picks are depth, "
                 "taxi, and future value")
    # SUPERFLEX BLIND SPOT: a skill player fills SUPER_FLEX, so a roster
    # with one quarterback never shows a gap even though it is starting a
    # receiver in a slot the whole league uses on a QB. Say it explicitly.
    if sflex and have.get("QB", 0) < 2:
        L.append(f"- **QB {have.get('QB', 0)} of 2 needed** — this is a "
                 "superflex league. A skill player can legally fill "
                 "SUPER_FLEX, so the slot table above shows no gap, but "
                 "you are giving up the position's scoring edge every week.")
    if have.get("QB", 0) == 1 and not sflex:
        L.append("- **only one QB rostered** — no insurance if he is hurt "
                 "or benched")
    if taxi and taxi - len(on_taxi) > 0:
        # THIS USED TO SAY "spend late picks on rookies", which inverts
        # the play. A rookie still on the board in the last rounds is by
        # definition one the room does not rate — exactly the player not
        # worth a free keeper next year. The user's own precedent is
        # Jayden Daniels: a rookie good enough to START, stashed for a
        # season, owned the next year outside the 3+2 keeper budget.
        L.append(f"- **{taxi - len(on_taxi)} taxi seat(s)** — eligible only "
                 f"to a rookie YOU draft {season_hint}, from either "
                 f"draft; may be left empty at no cost. The prize is that "
                 f"a taxi rookie carries over consuming NEITHER a keeper "
                 f"nor a drafted-rookie slot — a free keeper. So the seat "
                 f"is worth a REAL pick on a rookie good enough to start, "
                 f"not a leftover on one nobody rates. A rookie who will "
                 f"last until the second draft should be taken there "
                 f"instead; spend a first-draft pick only on one who "
                 f"will not")
    if rules.get("rules"):
        L.append(f"- keeper rules: {rules['rules']}")
    L.append("")
    return "\n".join(L)


def run(fragment=None):
    from battle_rhythm.sleeper_client import get, players, load_leagues, my_draft_picks
    from battle_rhythm.draft_helper import uid, my_next_picks, season_projection_totals

    tbl = players()
    data = load_leagues(refresh=True)
    rules_all = {}
    p = _paths.data("keepers.json")
    if p.exists():
        try:
            rules_all = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    me = uid()
    blocks = []
    for lg in data["leagues"]:
        if fragment and fragment.lower() not in (lg["name"] or "").lower():
            continue
        lid = lg["league_id"]
        full = get(f"league/{lid}") or {}
        # roster.md is the file CLAUDE.md tells every session to read
        # before recommending a pick, and mid-draft the picks feed is the
        # only truth. Reading the WRONG draft here reports an empty roster
        # and fails silently, which is precisely the 8/11 failure this
        # file exists to prevent.
        # WHICH draft for slot and pick geometry; EVERY draft for who is
        # gone. Both Hybrids run two a season, so one of them alone leaves
        # a stage-two pick looking like a free agent.
        from battle_rhythm.draft_helper import resolve_draft, season_picks
        draft, _live = resolve_draft(full)
        picks = season_picks(full) or _live

        # rosters are EMPTY mid-draft; the picks feed is the truth
        mine, taxi_ids = set(), set()
        my_roster_id = None
        for r in get(f"league/{lid}/rosters") or []:
            if str(r.get("owner_id")) == str(me):
                my_roster_id = r.get("roster_id")
                mine |= {x for x in (r.get("players") or []) if x}
                # keep the taxi subset SEPARATE — merging it made taxi
                # players fill starting slots and hid two real gaps
                taxi_ids |= {x for x in (r.get("taxi") or []) if x}
                mine |= taxi_ids
        for pk in picks:
            if pk.get("player_id") and str(pk.get("picked_by")) == str(me):
                mine.add(pk["player_id"])

        left, picks_note = None, ""
        if draft and draft.get("status") in ("drafting", "paused", "pre_draft"):
            rounds = (draft.get("settings") or {}).get("rounds") or 0
            # A TRADED PICK IS A PICK. my_next_picks walks my SEAT, which
            # is one pick per round by construction, so this line said TEN
            # in both Hybrids while he owned ELEVEN — and "picks remaining
            # vs open slots" is the sentence that decides whether to draft
            # for depth or for value late (8/13).
            owned, meta = [], {}
            if my_roster_id is not None:
                try:
                    owned, meta = my_draft_picks(draft, my_roster_id)
                except Exception:
                    owned, meta = [], {}
            if owned:
                left = len([pk for pk in owned if pk > len(picks)])
                bits = []
                if meta.get("gained"):
                    bits.append("gained " + ", ".join(
                        str(x) for x in meta["gained"]))
                if meta.get("lost"):
                    bits.append("lost " + ", ".join(
                        str(x) for x in meta["lost"]))
                picks_note = ("real ownership from /traded_picks — "
                              + "; ".join(bits)) if bits else \
                             "real ownership from /traded_picks — no trades"
            else:
                # my_next_picks walks draft_order, which Sleeper leaves unset
                # until a pre-draft league assigns slots. That returned 0 for
                # two pre_draft leagues on the first run and printed "picks
                # remaining 0 ... you will finish UNDER capacity" for a draft
                # that had not started. One pick per round is the floor.
                left = len(my_next_picks(draft, len(picks), rounds))
                if not left and not picks and rounds:
                    left = rounds
                    picks_note = ("ESTIMATE, 1/round — no draft order "
                                  "published yet, so traded picks are "
                                  "invisible and this may be low")
                elif left:
                    picks_note = ("seat walk — ownership could not be "
                                  "resolved, so any traded picks are NOT "
                                  "counted")
        scoring = full.get("scoring_settings") or lg.get(
            "scoring_settings") or {}
        season = lg.get("season") or full.get("season")
        try:
            totals = season_projection_totals(season, scoring)
        except Exception as e:            # never let a projection failure
            print(f"  (projections unavailable for {lg['name']}: {e})")
            totals = {}                   # cost him the roster map
        blocks.append(league_block(lg, tbl, mine, draft, len(picks), left,
                                   rules_all.get(lid) or {}, totals=totals,
                                   taxi_ids=taxi_ids, picks_note=picks_note))

    doc = ("# Roster snapshot\n\n"
           "GENERATED by `python roster_snapshot.py` — do not hand-edit.\n"
           "Rerun before any draft session; Sleeper's roster endpoint is "
           "empty mid-draft, so this merges rosters with the picks feed.\n\n"
           "Read this BEFORE recommending any pick. Position counts and "
           "open slots are the binding constraint late in a draft, not "
           "player talent.\n\n" + "\n---\n\n".join(blocks))
    OUT.write_text(doc, encoding="utf-8")
    print(doc)
    print(f"\nwrote {OUT}")


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    rp = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "DEF"] + ["BN"] * 10
    ded, flex, bench = slot_plan(rp)
    check("dedicated slots counted",
          ded == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "DEF": 1})
    check("two flex slots", len(flex) == 2)
    check("bench counted", bench == 10)

    # the 8/11 roster: 1 QB, 5 RB, 4 WR, 1 TE, no DEF
    have = {"QB": 1, "RB": 5, "WR": 4, "TE": 1}
    filled, leftover, gaps = fill(ded, flex, have)
    check("DEF flagged as an unfilled starting slot", "DEF" in gaps)
    check("both flexes filled from the RB/WR surplus",
          filled["FLEX"] == (1, 1) and len([g for g in gaps if g == "FLEX"]) == 0)
    check(f"leftover after starters is bench depth ({leftover})",
          sum(leftover.values()) == 11 - (sum(ded.values()) - 1 + 2))

    # superflex: a QB must be able to fill the SUPER_FLEX slot
    rp2 = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
    ded2, flex2, _b = slot_plan(rp2)
    f2, _l, g2 = fill(ded2, flex2, {"QB": 2, "RB": 2, "WR": 3, "TE": 1})
    check("superflex slot filled by the second QB", "SUPER_FLEX" not in g2)
    # exactly enough for the dedicated slots leaves BOTH flexes empty —
    # correct, there is nothing left to put in them
    f3, _l3, g3 = fill(ded2, flex2, {"QB": 1, "RB": 2, "WR": 3, "TE": 1})
    check("no leftovers leaves both flex slots gapped",
          "FLEX" in g3 and "SUPER_FLEX" in g3)
    # with surplus skill players, SUPER_FLEX fills WITHOUT a second QB —
    # which is why the superflex QB shortfall needs its own warning
    f3b, _l3b, g3b = fill(ded2, flex2, {"QB": 1, "RB": 3, "WR": 4, "TE": 1})
    check("a skill leftover silently fills SUPER_FLEX (the blind spot)",
          "SUPER_FLEX" not in g3b)
    f4, _l4, g4 = fill(ded2, flex2, {"QB": 0, "RB": 2, "WR": 3, "TE": 1})
    check("zero QBs flags the QB slot", "QB" in g4)

    # THE LG03-LG05 FAILURE. The first real run reported QB 1/1 (Milroe)
    # and RB 2/2 (Henry, Smith) with every slot green. Milroe projects
    # 15.3 and Smith 24.5 — two starting slots held by players who will
    # not play. Counting bodies is not counting starters.
    lg = {"name": "T", "league_id": "1", "total_teams": 12, "season": "2026",
          "roster_positions": ["QB", "RB", "RB", "WR", "WR", "WR", "TE",
                               "FLEX", "SUPER_FLEX"] + ["BN"] * 11,
          "settings": {"type": 2}}
    tbl = {"milroe": {"full_name": "Jalen Milroe", "position": "QB",
                      "team": "SEA", "age": 23},
           "jd": {"full_name": "Jayden Daniels", "position": "QB",
                  "team": "WAS", "age": 25},
           "henry": {"full_name": "Derrick Henry", "position": "RB",
                     "team": "BAL", "age": 32},
           "smith": {"full_name": "Brashard Smith", "position": "RB",
                     "team": "KC", "age": 23}}
    totals = {"milroe": 15.3, "jd": 382.0, "henry": 321.1, "smith": 24.5}
    for i in range(30):               # a credible league-wide QB/RB field
        tbl[f"q{i}"] = {"full_name": f"Q{i}", "position": "QB", "team": "X"}
        totals[f"q{i}"] = 400.0 - i * 10
        tbl[f"r{i}"] = {"full_name": f"R{i}", "position": "RB", "team": "X"}
        totals[f"r{i}"] = 330.0 - i * 10
    ded_t, flex_t, _bt = slot_plan(lg["roster_positions"])
    check(f"QB12 bar is the 12th-best QB "
          f"({thin_bar(totals, tbl, 'QB', 12):.0f})",
          thin_bar(totals, tbl, "QB", 12) == 300.0)
    # THE SECOND BUG. teams x 1 flagged five of nine LG01
    # starters, three of them ordinary. The bar must count every slot a
    # position actually starts, flex share included.
    check(f"superflex lifts the QB bar to QB22 "
          f"({thin_bar(totals, tbl, 'QB', 12, ded_t, flex_t):.0f})",
          thin_bar(totals, tbl, "QB", 12, ded_t, flex_t)
          < thin_bar(totals, tbl, "QB", 12))
    db = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "DEF"]
    d2, f2, _b2 = slot_plan(db)
    check("2 WR + 2 FLEX in a 12-team league prices WR35, not WR12",
          round(12 * starters_per_team("WR", d2, f2)) == 35)
    check("...and RB34", round(12 * starters_per_team("RB", d2, f2)) == 34)
    check("...and TE16", round(12 * starters_per_team("TE", d2, f2)) == 16)
    blk = league_block(lg, tbl, {"milroe", "jd", "henry", "smith"}, None,
                       0, None, {}, totals=totals)
    check("the QB slot shows the BEST QB, not roster order",
          "| QB x1 | 1/1 | Jayden Daniels" in blk)

    # THE REAL LG03-LG05 FAILURE: Milroe and Brashard Smith are on the
    # TAXI squad. They cannot start, and merging taxi into the active
    # roster turned two empty starting slots green.
    lg_t = dict(lg, settings={"type": 2, "taxi_slots": 2})
    tx = league_block(lg_t, tbl, {"milroe", "jd", "henry", "smith"}, None,
                      0, 10, {}, totals=totals,
                      taxi_ids={"milroe", "smith"})
    check("a taxi QB does NOT fill the superflex slot",
          "| SUPER_FLEX | 0/1  **EMPTY**" in tx)
    check("a taxi RB does NOT fill RB2", "| RB x2 | 1/2  **EMPTY**" in tx)
    check("RB2 and SUPER_FLEX both land in 'what must still be filled'",
          tx.count("starting slot, unfilled") >= 2)
    check("the taxi squad is reported separately, by name",
          "taxi **2/2 seats used**" in tx and "Jalen Milroe" in tx)
    check("...and says a redshirt cannot play this season",
          "cannot play this season" in tx)

    # TAXI IS A ONE-YEAR ROOKIE REDSHIRT. A man parked last season is
    # coming OFF onto the active roster in August, not sitting again —
    # and his seat is open for THIS year's class. Getting this wrong
    # produced a whole chain of bad advice on 8/11.
    tbl_y = {k: dict(v) for k, v in tbl.items()}
    tbl_y["milroe"]["years_exp"] = 1      # 2025 class -> redshirt done
    tbl_y["smith"]["years_exp"] = 1
    tbl_y["jd"]["years_exp"] = 2
    tbl_y["henry"]["years_exp"] = 10
    ex = league_block(lg_t, tbl_y, {"milroe", "jd", "henry", "smith"}, None,
                      0, 10, {}, totals=totals, taxi_ids={"milroe", "smith"})
    check("an EXPIRED redshirt is on the active roster, not the taxi",
          "redshirt EXPIRED" in ex and "taxi **0/2 seats used**" in ex)
    check("...and both seats read as open for this year's rookies",
          "2 taxi seat(s) open" in ex)
    check("...so his projection counts against the lineup again",
          "Jalen Milroe **THIN**" in ex)
    tbl_r = {k: dict(v) for k, v in tbl_y.items()}
    tbl_r["milroe"]["years_exp"] = 0      # actual current rookie
    rs = league_block(lg_t, tbl_r, {"milroe", "jd", "henry", "smith"}, None,
                      0, 10, {}, totals=totals, taxi_ids={"milroe"})
    check("a CURRENT rookie really is redshirting and cannot start",
          "taxi **1/2 seats used**" in rs
          and "| SUPER_FLEX | 0/1  **EMPTY**" in rs)
    check("...leaving one seat open, not two",
          "1 taxi seat(s) open" in rs)
    check("active capacity excludes the taxi bodies",
          "active rostered **2**" in tx)
    check("a taxi player is not double-counted as THIN",
          "Jalen Milroe **THIN**" not in tx)
    check("Milroe is flagged THIN, not counted as a starter",
          "Jalen Milroe **THIN**" in blk)
    check("...and Brashard Smith too", "Brashard Smith **THIN**" in blk)
    check("...with an explicit 'treat as OPEN' callout",
          "filled in name only" in blk and "treat them as OPEN" in blk)
    check("Derrick Henry is NOT flagged (321 clears the bar)",
          "Derrick Henry **THIN**" not in blk)
    check("the SUPER_FLEX row names its occupant, not 'from QB/RB/WR/TE'",
          "| SUPER_FLEX | 1/1 | Jalen Milroe" in blk)
    check("projections appear in the room list",
          "proj 382" in blk)
    plain = league_block(lg, tbl, {"jd"}, None, 0, None, {})
    check("no projections -> no THIN claims (back-compat)",
          "THIN" not in plain)

    # A two-stage league finishing the FIRST draft under capacity is the
    # commissioner's design (managers keep different numbers), not a
    # shortfall. Reading it as a warning argues for depth over value.
    one = league_block(lg, tbl, {"jd"}, None, 0, 10, {}, totals=totals)
    two = league_block(lg, tbl, {"jd"}, None, 0, 10,
                       {"supplemental_draft": True}, totals=totals)
    check("plain league warns about finishing under capacity",
          "finish UNDER capacity" in one)
    check("two-stage league calls it expected instead",
          "SECOND draft" in two and "UNDER capacity" not in two)

    # ---- picks remaining says WHERE ITS NUMBER CAME FROM
    #
    # The count used to be a seat walk, one pick per round, and it said
    # TEN in both Hybrids while he owned ELEVEN. The number is now real,
    # but a right number with no provenance is exactly the defect class
    # that has cost the most this month, so the note is part of the
    # contract and gets tested like one.
    noted = league_block(lg, tbl, {"jd"}, None, 0, 11, {}, totals=totals,
                         picks_note="real ownership from /traded_picks "
                                    "— gained 95")
    check("the picks-remaining line carries its provenance",
          "picks remaining **11**" in noted
          and "real ownership from /traded_picks — gained 95" in noted)
    check("provenance is absent when the caller has none to give",
          "/traded_picks" not in one)
    # The note used to be bolted on with str.replace against a literal
    # anchor. When that anchor moved, the line vanished silently and
    # nothing failed. It is a parameter now; keep it that way.
    # The needle is assembled at runtime so this line is not itself a
    # match — the first version failed against its own source text.
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    needle = "blk." + "replace(" + '"- picks'
    check("no anchor-string patching of the picks line survives",
          needle not in src)

    # ---- an open taxi seat is an OPTION, not a committed pick
    #
    # The first version of this subtracted open seats from the pick
    # count. Wrong, per the user the same day: a seat may be left empty
    # at no cost and can be filled from EITHER draft, so it never
    # reduces what is available for the lineup. It does compete for the
    # same picks — a different claim, and it gets a different sentence.
    tx2 = league_block(lg_t, tbl, {"jd", "henry"}, None, 0, 11, {},
                       totals=totals, taxi_ids=set())
    check("open taxi seats do NOT reduce the active pick count",
          "committed to open TAXI seats" not in tx2
          and "picks remaining **11**" in tx2)
    check("...they are reported as competing, not claiming",
          "compete for these same picks but do not claim them" in tx2)
    check("...with the narrow eligibility stated at the seat",
          "rookie YOU draft" in tx2)
    check("a league with no taxi says nothing about seats",
          "taxi seat(s) compete" not in one)
    # The old advice — "spend late picks on rookies" — inverts the play:
    # a rookie who lasts that long is one the room does not rate, which
    # is exactly the player not worth a free keeper next year.
    check("taxi guidance no longer recommends leftover picks",
          "spend late" not in tx2 and "worth a REAL pick" in tx2)
    check("...and names the free keeper that makes a seat worth anything",
          "NEITHER a keeper" in tx2)

    # ---- the all-clear must answer to gaps AND thin starters
    #
    # The clause hung off thin_seen alone, so an empty roster printed
    # every unfilled slot and then "all starting slots covered" directly
    # underneath. Three leagues did that in one run.
    empty = league_block(lg, tbl, set(), None, 0, None, {}, totals=totals)
    check("a roster with real gaps never claims all slots are covered",
          "starting slot, unfilled" in empty
          and "all starting slots covered" not in empty)
    full_lg = dict(lg, roster_positions=["QB", "RB", "RB"] + ["BN"] * 5)
    full = league_block(full_lg, tbl, {"jd", "henry", "smith"},
                        None, 0, None, {})
    check("...and the all-clear still prints when there is nothing to fill",
          "starting slot, unfilled" not in full
          and "all starting slots covered" in full)

    # ---- 'Room by position' covers whatever the league starts
    #
    # The position list was a literal that stopped at DEF, so the IDP
    # league's DL, LB and DB — three of its eleven starting slots — were
    # missing from the section that reports how many of each you hold.
    idp_lg = dict(lg, roster_positions=["QB", "RB", "WR", "TE", "K",
                                        "DL", "LB", "DB", "FLEX"] + ["BN"] * 5)
    idp = league_block(idp_lg, tbl, set(), None, 0, None, {})
    for p in ("DL", "LB", "DB", "K"):
        check(f"Room by position reports {p}", f"- **{p} 0**" in idp)
    check("...and does not invent positions the league never starts",
          "- **DEF 0**" not in idp)
    # 1 of 2 required is worse than 2 of 2, and used to print quieter.
    shortlg = dict(lg, roster_positions=["QB", "RB", "RB"] + ["BN"] * 5)
    sh = league_block(shortlg, tbl, {"jd", "henry"}, None, 0, None, {})
    check("a position below its requirement is marked SHORT",
          "- **RB 1**  ← **SHORT 1 of 2**" in sh)
    check("...and a position AT its requirement still reads 'no insurance'",
          "- **QB 1**  ← no insurance" in sh)

    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()
    run(a[0] if a else None)
