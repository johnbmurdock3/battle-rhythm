"""
Dynasty value board — standalone, read-only, additive.

Does NOT touch board_data() or any live-draft path. Imports the same
projection plumbing draft_helper uses and layers a multi-year value model
on top:

  value = sum over remaining seasons t of
            proj_2026 * curve(age + t) / curve(age) * discount^t

curve() is the positional aging curve in ages.json (peak plateau, rise
before it, decline after, cliff, hard end). Dividing by curve(age) makes
the 2026 projection the anchor: a 21-year-old's future seasons scale UP
toward his peak, a 28-year-old RB's scale down fast. This is the term
that fixes rookies — year-1 points stop being the whole number.

Because the model can't see role changes (a committee back who breaks
out), a configurable share of the final number comes from the market:
the dADP-implied value is the model value of the player RANKED where the
market prices him. market_blend in ages.json sets the weight.

Tiers: sorted by blended value, a tier break is a gap between adjacent
players >= gap_factor * median gap (floor min_gap). Cliffs, not ranks.

Usage (his machine, networked):
  python dynasty_value.py <league fragment> [--pos RB] [--top 40] [--all]
      --all includes drafted/rostered players (default: available only)
  python dynasty_value.py --selftest        # offline math check, no network

Tuning: edit ages.json and rerun. No restart discipline applies — this
script has no server and no cache of its own.
"""

import json
import os
import pathlib
from battle_rhythm import paths as _paths
import sys



def load_params():
    """ages.json, with optional env overrides for A/B testing a knob.

    Editing ages.json to compare two settings means a commit-and-revert
    cycle and a real risk of leaving the experiment in place. These let
    you run the same command twice:

        SLEEPER_RISE=0.96 python draft_review.py     # every position
        SLEEPER_RISE=TE:0.96 python draft_review.py  # one position
        SLEEPER_DAMP=0.5 python draft_review.py

    Windows cmd: set SLEEPER_RISE=0.96 && python draft_review.py
    Nothing is written back. Every caller goes through load_params(),
    so the override reaches the dashboard and room_bias too — but the
    dashboard needs a --serve restart to pick up the environment.
    """
    P = json.loads(_paths.data("ages.json").read_text(encoding="utf-8"))
    over = []
    raw = (os.environ.get("SLEEPER_RISE") or "").strip()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            pos, _, val = part.rpartition(":")
            targets = [pos] if pos else list(P["curves"])
            for t in targets:
                if t in P["curves"]:
                    P["curves"][t]["rise"] = float(val)
                    over.append(f"{t} rise {float(val)}")
    raw = (os.environ.get("SLEEPER_DAMP") or "").strip()
    if raw:
        P.setdefault("roster", {})["scarcity_damp"] = float(raw)
        over.append(f"scarcity_damp {float(raw)}")
    if over:
        P["_override"] = over
    return P


# ------------------------------------------------------------------ curve

def curve(pos, age, P):
    """Positional age multiplier, peak = 1.0. Zero outside the career."""
    c = P["curves"].get(pos)
    if not c or not age:
        return 1.0  # unknown position/age: no adjustment, be honest elsewhere
    lo, hi = c["peak"]
    cliff_age, cliff_rate = c["cliff"]
    if age >= c["end"]:
        return 0.0
    if age < lo:
        return c["rise"] ** (lo - age)
    if age <= hi:
        return 1.0
    m = 1.0
    for a in range(hi + 1, age + 1):
        m *= cliff_rate if a >= cliff_age else c["decline"]
    return m


def horizon_for(P, dynasty=True, keeper=False):
    """Seasons to price. A 3-keeper league carries 7 players; the rest
    churns, so a veteran's age-33 season is not yours to pay for."""
    h = P.get("horizons") or {}
    if keeper:
        return int(h.get("keeper", 2))
    if dynasty:
        return int(h.get("dynasty", 20))
    return int(h.get("redraft", 1))


def dynasty_value(pos, age, proj, P, repl=0.0, horizon=None):
    """Discounted multi-year SURPLUS anchored on this season's projection.

    Each future season contributes max(0, aged_projection - repl):
    points above the positional replacement level, not raw points.
    Raw points made the board a QB list — a 250-point QB in a 1QB league
    where the 14th QB scores 230 is worth 20, not 250, and compounding
    the 250 over an 18-year curve buried every RB and WR on the board.
    Years below replacement contribute zero (an aging vet's tail, a
    young riser's first season) but don't end the loop — a riser can
    climb back above the line."""
    if proj <= 0:
        return 0.0
    base = curve(pos, age, P)
    if base <= 0:
        return 0.0
    # horizon caps how many seasons count. Past it the player is gone —
    # traded, or shuffled off a 7-man keeper roster — so pricing those
    # years is pricing something you will never own.
    span = 20 if horizon is None else max(0, int(horizon))
    total, t = 0.0, 0
    while t <= span:
        m = curve(pos, (age or 0) + t, P)
        if m <= 0:
            break
        surplus = proj * (m / base) - repl
        if surplus > 0:
            total += surplus * (P["discount"] ** t)
        t += 1
    return round(total, 1)


def damped_replacement(repl_by_pos, P, weights=None):
    """Pull each position's replacement toward a global bar.

    Pure positional VORP is why a 22-year-old TE outscores Justin
    Jefferson 3.7 to 1 in this model: a one-TE league puts TE
    replacement on a far worse player than WR replacement, and the
    multi-year sum multiplies that gap by ~5 before you see it. The
    effect is real — scarce positions ARE worth more — but the market
    prices those two players within a few picks of each other, and a
    model that disagrees with thousands of drafters by 4x on the two
    most-analysed players in the sport is the thing that needs
    explaining.

    damp = 0.0  pure positional replacement (original behaviour)
    damp = 1.0  every position measured against one global bar
    Anything between shrinks cross-position gaps without erasing
    scarcity. Tunable in ages.json; NOT fitted to anything.

    DAMPING IS ONE-SIDED: it raises bars that sit BELOW the global
    average and never lowers a bar that sits above it. Two-sided
    damping was a real bug (8/11). It exists to stop a SCARCE
    position — low bar, because replacement there is a bad player —
    from inflating. A DEEP position has a high bar for the opposite
    reason: in a 1QB league QB12 is a genuine starter, ~300 points.
    Pulling that bar down toward the mean manufactured ~43 points of
    surplus per season for every quarterback, and the 20-season
    discounted sum multiplied it by ~6.6 — about 285 points of value
    from nothing. The board answered with Dart, Purdy, Nix and Love
    at every mid-round pick in a league that starts one QB. Raising
    the floor for scarcity is the goal; subsidising abundance is not.
    """
    d = float((P.get("roster") or {}).get("scarcity_damp",
              P.get("scarcity_damp", 0.0)) or 0.0)
    if d <= 0 or not repl_by_pos:
        return dict(repl_by_pos)
    w = weights or {p: 1.0 for p in repl_by_pos}
    tot = sum(w.get(p, 1.0) for p in repl_by_pos) or 1.0
    global_bar = sum(v * w.get(p, 1.0) for p, v in repl_by_pos.items()) / tot
    return {p: max(v, v + d * (global_bar - v))
            for p, v in repl_by_pos.items()}


def market_disagreement(rows, ratio=3.0, min_gap=12):
    """Flag rows where the model and the market rank a player very
    differently. Sets r['disagree'] = (model_rank, market_rank, note).

    The test is a RATIO, not a fixed number of ranks. A fixed cut is
    meaningless across a 500-player board: 25 ranks apart at the top is
    an enormous disagreement, the same 25 ranks at pick 300 is noise.
    The case this exists to catch — the model ranking Colston Loveland
    #1 while the market has him near #28 — is a 28x disagreement and
    only 27 ranks, so any absolute threshold big enough to avoid noise
    at the bottom would have missed it entirely.

    min_gap stops rank 1 vs rank 3 (a 3x ratio, 2 ranks) from flagging.

    Where these two diverge there is either an edge or a bug, and the
    honest default is to look rather than assume the first.
    """
    ranked = sorted([r for r in rows if r.get("value") is not None],
                    key=lambda r: -r["value"])
    mrank = {id(r): i + 1 for i, r in enumerate(ranked)}
    priced = sorted([r for r in rows if r.get("adp")], key=lambda r: r["adp"])
    krank = {id(r): i + 1 for i, r in enumerate(priced)}
    for r in rows:
        r["disagree"] = None
        mr, kr = mrank.get(id(r)), krank.get(id(r))
        if not mr or not kr:
            continue
        hi, lo = max(mr, kr), max(1, min(mr, kr))
        if hi / lo >= ratio and abs(kr - mr) >= min_gap:
            side = "model loves him" if kr > mr else "market loves him"
            r["disagree"] = (mr, kr,
                             f"{side}: model #{mr} vs market #{kr} "
                             f"({hi / lo:.0f}x)")
    return rows


def years_left(pos, age, P):
    c = P["curves"].get(pos)
    if not c or not age:
        return None
    return max(0, c["end"] - age)


# ------------------------------------------------------- market blend, tiers

def blend_market(rows, P, ladder=None):
    """rows: dicts with model_v and adp (overall dADP or None).
    Market-implied value = model value of the player ranked where the
    market prices him. `ladder` is the full-pool model-value ranking to
    map dADP ranks onto; defaults to the rows themselves, which is only
    honest when rows ARE the full pool (the CLI case). Callers holding a
    subset (the dashboard) must pass the full ladder or the blend lies.
    Blended in place -> r['value']."""
    w = P.get("market_blend", 0.0)
    if ladder is None:
        ladder = sorted((r["model_v"] for r in rows), reverse=True)
    for r in rows:
        if w and r["adp"] and ladder:
            i = min(len(ladder) - 1, max(0, int(round(r["adp"])) - 1))
            market_v = ladder[i]
            r["value"] = round((1 - w) * r["model_v"] + w * market_v, 1)
        else:
            r["value"] = r["model_v"]
    return rows


# Roster geometry lives in roster_shape.py. Re-exported here so
# `from dynasty_value import slot_plan` (lineup_value:85) still
# resolves — the callers do not need to know it moved.
from battle_rhythm.roster_shape import (FLEX_FILL, DEDICATED_SLOTS,  # noqa: E402,F401
                          slot_plan)


def taxi_split(taxi_ids, tbl):
    """(redshirting, expired, unknown) — taxi is a ONE-YEAR rookie redshirt.

    A player may only be parked on the taxi squad during his NFL rookie
    season, and only for that one season. So Sleeper showing a man on
    the taxi in August does NOT mean he sits this year — if his redshirt
    was last season he is coming OFF, onto the active roster, and his
    seat frees up for a member of THIS year's rookie class.

    This is the correction to a whole chain of wrong advice on 8/11. The
    tools first counted taxi players as active starters (they were not),
    then excluded them entirely (also wrong), then priced "activating"
    one as a decision with a cost (there is no such decision — the
    redshirt simply expires). What the taxi seat actually buys is a year
    of free storage: the player never occupied a bench spot, and he
    arrives the following season still eligible for a drafted-rookie
    keeper slot.

    Rookie = years_exp 0 in the current table; the 2025 class reads 1 in
    2026 data (same convention keeper.py uses). Missing years_exp is
    reported as unknown rather than guessed — assuming either way would
    silently move a player between "can start" and "cannot."
    """
    red, done, unk = set(), set(), set()
    for pid in taxi_ids or ():
        y = (tbl.get(pid) or {}).get("years_exp")
        if y is None:
            unk.add(pid)
        elif int(y) <= 0:
            red.add(pid)
        else:
            done.add(pid)
    return red, done, unk


def saturation_bar(pos, roster_positions, repl):
    """The bar a SURPLUS player at `pos` is really measured against.

    Positional replacement answers "how much better is he than the
    worst startable player at his position." That is the right question
    only while you still have an empty slot at that position. Once the
    dedicated slots are full, the next player there is not taking a
    <pos> slot — he is taking a flex slot, and his real competition is
    every other position that can fill it.

    Returns (bar, kind):
      (max repl over flex-eligible positions, 'flex')  he can flex
      (None, 'bench')                                  he cannot

    This is the third appearance of one bug. The QB wall was "you can
    only start one quarterback." The 22-year-old-TE-over-Jefferson
    result was "you can only start one tight end" — and it survived a
    scarcity-damping fix and a rise fix because both treated it as a
    magnitude problem. It was a slot problem. A second elite TE does
    not unlock a second TE slot; he competes with your receivers and
    backs for a flex, and the flex bar is far higher than TE12.
    """
    _ded, flex, _bn = slot_plan(roster_positions)
    fills = set()
    for _slot, f in flex:
        if pos in f:
            fills.update(f)
    if not fills:
        return None, "bench"
    bars = [repl[p] for p in fills if p in repl]
    return (max(bars) if bars else None), "flex"


def roster_adjust(rows, my_pids, tbl, P, roster_positions=None, repl=None):
    """Roster-context pass, shared by CLI and dashboard. In place.

    Positional saturation (needs roster_positions + repl, else skipped):
    once you already roster as many players at a position as the league
    gives you dedicated slots, the next one is a flex or bench body.
    His value is rescaled from surplus-over-his-position to
    surplus-over-the-flex-bar:

        mult = (proj - flex_bar) / (proj - own_bar)

    which is exact, not a fudge factor — it is the same VORP with the
    correct replacement substituted. A position with no flex path (QB
    in a 1QB league, DEF, K) falls back to roster.bench_mult, which IS
    a fudge factor: a backup QB is not worthless (injury cover, trade
    bait) but he starts zero games, and nothing here can price that.

    Target collision: a WR/TE on a team where you already roster a
    pass catcher shares one QB's throws with your guy — his projection
    overstates what he adds to YOUR roster. Value takes the
    collision_mult haircut. This is the general form of the GB/Watson
    rule: it's about the shared QB, not about Green Bay.

    Handcuff: an RB behind your own RB gets handcuff_mult ONLY when he
    has standalone value (model surplus > 0 — he beats replacement on
    his own, Stevenson-style). Pure insurance backs pass through
    untouched: owning the backfield is worth nothing if the backup
    only matters when your starter is hurt.

    Rows need meta (team/position), model_v, value. Sets r['note']."""
    R = P.get("roster") or {}
    coll = R.get("collision_mult", 0.6)
    # A tight end and a receiver compete for the same quarterback but not
    # the same routes or personnel groupings, so a cross-position
    # collision is real but softer than WR-on-WR.
    coll_x = R.get("collision_mult_cross", 0.8)
    cuff = R.get("handcuff_mult", 1.15)
    # team -> [(name, position)] of MY pass catchers, so the warning can
    # name the player. "your LV pass catcher" made a correct flag look
    # like a bug; "shares targets with Brock Bowers" is checkable at a
    # glance.
    bench_mult = R.get("bench_mult", 0.25)
    pass_teams, rb_teams = {}, {}
    mine_by_pos = {}
    for pid in my_pids or ():
        m = tbl.get(pid) or {}
        who = m.get("full_name") or str(pid)
        pos = m.get("position")
        if pos:
            mine_by_pos.setdefault(pos, []).append(who)
        team = m.get("team")
        if not team:
            continue
        if pos in ("WR", "TE"):
            pass_teams.setdefault(team, []).append((who, pos))
        elif pos == "RB":
            rb_teams.setdefault(team, []).append((who, "RB"))

    ded = slot_plan(roster_positions)[0] if roster_positions else {}
    sat_cache = {}

    for r in rows:
        m = r.get("meta") or {}
        team, pos = m.get("team"), m.get("position")
        notes = []
        if pos in ("WR", "TE") and team in pass_teams:
            mates = pass_teams[team]
            same_pos = [w for w, p in mates if p == pos]
            mult = coll if same_pos else coll_x
            named = ", ".join(w for w, _p in mates[:2])
            kind = "same position" if same_pos else "TE/WR"
            r["value"] = round(r["value"] * mult, 1)
            notes.append(f"target collision ({kind}) — shares {team} "
                         f"targets with {named}")
        elif pos == "RB" and team in rb_teams:
            behind = ", ".join(w for w, _p in rb_teams[team][:2])
            if r.get("model_v", 0) > 0:
                r["value"] = round(r["value"] * cuff, 1)
                notes.append(f"handcuff w/ standalone value — backs up "
                             f"your {behind}")
            else:
                notes.append(f"handcuff only, no standalone value — "
                             f"backs up your {behind}")

        # --- positional saturation ---------------------------------
        held = len(mine_by_pos.get(pos, ()))
        slots = ded.get(pos, 0)
        if roster_positions and repl and pos and held >= slots > 0:
            if pos not in sat_cache:
                sat_cache[pos] = saturation_bar(pos, roster_positions, repl)
            bar, kind = sat_cache[pos]
            own = repl.get(pos)
            proj = r.get("proj")
            who = ", ".join(mine_by_pos[pos][:2])
            if kind == "bench":
                r["value"] = round(r["value"] * bench_mult, 1)
                notes.append(f"no starting slot — you hold {held} at {pos} "
                             f"for {slots} slot(s) ({who}); bench body")
            elif (bar is not None and own is not None and proj
                  and proj > own and bar > own):
                mult = max(0.0, min(1.0, (proj - bar) / (proj - own)))
                r["value"] = round(r["value"] * mult, 1)
                notes.append(f"{pos} slot full ({who}) — priced vs the flex "
                             f"bar {bar:.0f}, not the {pos} bar {own:.0f}")
        if notes:
            r["note"] = " · ".join(notes)
    return rows


def tier_breaks(values, P):
    """Indices i where a tier ends AFTER position i (values sorted desc).

    The threshold must be SCALE-FREE. The first version used a fixed
    min_gap of 25.0, which was calibrated when values ran in the
    hundreds. Switching to surplus-over-replacement collapsed them to
    double digits, so a 25-point floor became wider than the entire
    board and every player landed in Tier 1. A tiering rule that breaks
    when you change the units of its input is not a tiering rule.

    Threshold = the largest of:
      gap_factor x median gap   — a break is an unusually big drop
      min_gap_pct x total spread — floor that scales with the data
      min_gap_abs               — stops noise when everything is flat
    """
    T = P.get("tiers") or {}
    gaps = [values[i] - values[i + 1] for i in range(len(values) - 1)]
    if not gaps:
        return set()
    srt = sorted(gaps)
    med = srt[len(srt) // 2]
    spread = max(values) - min(values) if values else 0.0
    cut = max(T.get("gap_factor", 2.5) * max(med, 0.01),
              T.get("min_gap_pct", 0.06) * spread,
              T.get("min_gap_abs", 1.0))
    return {i for i, g in enumerate(gaps) if g >= cut}


# ------------------------------------------------------------------ board

def resolve_league(fragment):
    """Fragment / exact name / league_id -> league_id.

    Exact name and id win over substring. Two of his leagues are named
    'LG03-LG05' and 'LG03-LG05 <emoji>', so the shorter name is a
    substring of the longer one and NO fragment can select it by
    substring alone. Exact-match-first fixes that; the ambiguity error
    prints ids so there is always an unambiguous fallback."""
    from battle_rhythm.sleeper_client import load_leagues
    frag = str(fragment).strip().lower()
    lgs = load_leagues()["leagues"]
    for l in lgs:
        if frag == str(l["league_id"]):
            return l["league_id"]
    # SLUGS AND ALIASES, before any name matching. leagues/_index.json is
    # the league key and carries every nickname -- lg05, hero, lg06,
    # lg02, lg03. mcp_server has resolved through it since 9/2 and this
    # function did not, so `recap lg05` worked when Claude asked and
    # failed from the command line with "no league matching 'lg05'".
    # One identity, two resolvers, different answers: the exact split
    # _index.json exists to close.
    try:
        from battle_rhythm import paths as _p
        by_alias = _p.id_for(frag)
        if by_alias and any(str(l["league_id"]) == str(by_alias) for l in lgs):
            return str(by_alias)
    except Exception:
        pass

    exact = [l for l in lgs if (l["name"] or "").strip().lower() == frag]
    if len(exact) == 1:
        return exact[0]["league_id"]
    if len(exact) > 1:
        raise SystemExit("two leagues share that exact name — use an id:\n  "
                         + "\n  ".join(f"{l['league_id']}  {l['name']}"
                                       for l in exact))
    hits = [l for l in lgs if frag in (l["name"] or "").lower()]
    if not hits:
        raise SystemExit(f"no league matching '{fragment}'. known:\n  "
                         + "\n  ".join(f"{l['league_id']}  {l['name']}"
                                       for l in lgs))
    if len(hits) > 1:
        raise SystemExit(
            f"'{fragment}' is ambiguous. Use the exact name or an id:\n  "
            + "\n  ".join(f"{l['league_id']}  {l['name']}" for l in hits))
    return hits[0]["league_id"]


def run(fragment, pos_filter=None, top=40, include_gone=False):
    from battle_rhythm.sleeper_client import name_of
    from battle_rhythm.draft_helper import (board_data, injury_tag, _adp,
                              DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)
    P = load_params()
    lid = resolve_league(fragment)
    # same engine the dashboard uses — one source of truth, per the
    # architecture rule. board_data hands back totals, replacement
    # levels, availability, and dADP-priced rows in one shot.
    d = board_data(lid)
    lg, tbl, season = d["lg"], d["tbl"], d["season"]
    repl = d.get("replacement") or {}
    curves = set(P["curves"])
    # board_data has already applied the keeper flip to d["dynasty"].
    from battle_rhythm.draft_helper import adp_keys_for
    keys, fb = adp_keys_for((d.get("lg") or {}).get("roster_positions"),
                            d["dynasty"], keeper=False)

    def rowify(pid, m, proj, adp, exact, gone):
        pos, age = m.get("position"), m.get("age")
        return {"pid": pid, "meta": m, "pos": pos, "age": age,
                "proj": proj, "adp": adp, "exact": exact,
                "model_v": dynasty_value(pos, age, proj, P,
                                         repl.get(pos, 0.0)),
                "yrs": years_left(pos, age, P), "gone": gone}

    # full-pool ladder (available AND drafted): dADP is an overall-market
    # rank, so the blend must map onto everyone, or a half-drafted board
    # shifts every market-implied value (display-artifact trap)
    ladder = []
    for pid, proj in d["totals"].items():
        m = tbl.get(pid) or {}
        if m.get("position") in curves and proj > 0:
            ladder.append(dynasty_value(m["position"], m.get("age"), proj,
                                        P, repl.get(m["position"], 0.0)))
    ladder.sort(reverse=True)

    rows = [rowify(r["pid"], r["meta"], r["pts"], r["adp"], r["exact"], False)
            for r in d["rows"] if r["meta"].get("position") in curves]
    if include_gone:
        for pid in d["gone"]:
            m = tbl.get(pid) or {}
            proj = d["totals"].get(pid, 0.0)
            if m.get("position") in curves and proj > 0:
                adp, exact = _adp(pid, season, keys, fb)
                rows.append(rowify(pid, m, proj, adp, exact, True))
    blend_market(rows, P, ladder)
    roster_adjust(rows, d.get("my_pids"), tbl, P)

    rows = [r for r in rows
            if not pos_filter or r["pos"] == pos_filter.upper()]
    rows.sort(key=lambda r: -r["value"])
    rows = rows[:top]

    print(f"{lg['name']} — dynasty value board "
          f"(discount {P['discount']}, market blend {P['market_blend']})")
    print("value = multi-year surplus over positional replacement, "
          "age-curved, market-blended.\n")
    hdr = f"{'tier':>4} {'value':>7} {'model':>7} {'proj26':>7} {'dADP':>7} " \
          f"{'age':>4} {'yrs':>4} {'inj':>9}  player"
    print(hdr)
    breaks = tier_breaks([r["value"] for r in rows], P)
    tier = 1
    for i, r in enumerate(rows):
        adp_s = (f"{r['adp']:>6.1f}{' ' if r['exact'] else 'r'}"
                 if r["adp"] else "      -")
        flag = " *gone*" if r["gone"] else ""
        print(f"{tier:>4} {r['value']:>7.1f} {r['model_v']:>7.1f} "
              f"{r['proj']:>7.1f} {adp_s} {str(r['age'] or '?'):>4} "
              f"{str(r['yrs'] if r['yrs'] is not None else '?'):>4} "
              f"{injury_tag(r['meta']):>9}  {name_of(r['pid'], tbl)}{flag}"
              + (f"  · {r['note']}" if r.get("note") else ""))
        if i in breaks:
            tier += 1
            print(f"{'':>4} {'-' * 64}")


# ---------------------------------------------------------------- selftest

def selftest():
    """Offline math checks. No network, no cache."""
    P = load_params()
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'ok' if cond else 'XX'}  {name}")
        ok = ok and cond

    check("peak plateau is 1.0", curve("RB", 24, P) == 1.0)
    check("young riser below peak", 0 < curve("RB", 21, P) < 1.0)
    check("RB 29 below RB 27", curve("RB", 29, P) < curve("RB", 27, P))
    check("career end is zero", curve("RB", 32, P) == 0.0)
    check("QB ages slower than RB at 30",
          curve("QB", 30, P) > curve("RB", 30, P))

    # the rookie fix: equal 2026 projections, 22yo RB must beat 27yo RB
    v_young = dynasty_value("RB", 22, 150.0, P)
    v_old = dynasty_value("RB", 27, 150.0, P)
    check(f"22yo RB {v_young} > 27yo RB {v_old} on equal proj",
          v_young > v_old)
    # and a WR outlasts an RB of the same age and projection
    check("26yo WR > 26yo RB on equal proj",
          dynasty_value("WR", 26, 150.0, P) > dynasty_value("RB", 26, 150.0, P))

    # the QB-wall fix: surplus over replacement, not raw points. A QB
    # projecting 250 where the replacement QB scores 230 must be worth
    # LESS than an RB projecting 150 over a 100-point replacement —
    # raw points said the opposite and turned the board into a QB list.
    v_qb = dynasty_value("QB", 26, 250.0, P, 230.0)
    v_rb = dynasty_value("RB", 24, 150.0, P, 100.0)
    check(f"20-surplus QB {v_qb} < 50-surplus RB {v_rb}", v_qb < v_rb)
    check("below-replacement vet is worth 0",
          dynasty_value("RB", 29, 90.0, P, 100.0) == 0.0)
    # a young riser below replacement TODAY can still have value:
    # his aged projection climbs above the line in later seasons
    check("young riser below the line today still has value",
          dynasty_value("RB", 21, 95.0, P, 100.0) > 0.0)

    # HORIZON, and the rule it has to encode: never pass on elite talent
    # for a lesser younger player just because of age. A big projection
    # gap should beat an age gap at ANY horizon; only a narrow gap should
    # let the horizon decide.
    big_old = dynasty_value("WR", 30, 300.0, P, 150.0, horizon=2)
    big_young = dynasty_value("WR", 24, 200.0, P, 150.0, horizon=2)
    check(f"100-pt gap: elite 30yo wins on a 2-yr horizon "
          f"({big_old} > {big_young})", big_old > big_young)
    check("...and STILL wins over a full career — a 100-point projection "
          "gap is not something six years of age overcomes",
          dynasty_value("WR", 30, 300.0, P, 150.0) >
          dynasty_value("WR", 24, 200.0, P, 150.0))

    # Structural property, true for any curve shape: lengthening the
    # horizon always shifts the comparison TOWARD the younger player,
    # because his extra seasons are the only thing a longer horizon adds.
    # (Asserting a specific crossover would be testing ages.json's curve
    # priors, which are tunable guesses, not behaviour.)
    def ratio(h):
        return (dynasty_value("WR", 24, 200.0, P, 150.0, horizon=h)
                / max(0.01, dynasty_value("WR", 29, 220.0, P, 150.0,
                                          horizon=h)))
    r1, r2, r10 = ratio(1), ratio(3), ratio(10)
    check(f"a longer horizon always favours youth "
          f"(1yr {r1:.2f} -> 3yr {r2:.2f} -> 10yr {r10:.2f})",
          r1 <= r2 <= r10)
    check("a 1-year horizon is nearly pure current production",
          dynasty_value("WR", 29, 220.0, P, 150.0, horizon=0) == 70.0)
    check("shorter horizon never exceeds longer",
          dynasty_value("WR", 26, 200.0, P, 100.0, horizon=2) <=
          dynasty_value("WR", 26, 200.0, P, 100.0, horizon=10))
    check("keeper horizon read from config",
          horizon_for(P, dynasty=True, keeper=True) == 2
          and horizon_for(P, dynasty=True, keeper=False) == 20)

    # roster context: collision haircuts a same-QB pass catcher; the
    # handcuff bump fires only with standalone value
    tbl = {"mine_wr": {"position": "WR", "team": "GB",
                       "full_name": "My Receiver"},
           "mine_rb": {"position": "RB", "team": "TB",
                       "full_name": "My Back"},
           "mine_te": {"position": "TE", "team": "LV",
                       "full_name": "Brock Bowers"}}
    rr = [{"meta": {"position": "WR", "team": "GB"},
           "model_v": 50.0, "value": 100.0},
          {"meta": {"position": "RB", "team": "TB"},
           "model_v": 20.0, "value": 100.0},
          {"meta": {"position": "RB", "team": "TB"},
           "model_v": 0.0, "value": 40.0},
          {"meta": {"position": "WR", "team": "KC"},
           "model_v": 50.0, "value": 100.0},
          # THE CASE THAT LOOKED LIKE A BUG: an LV receiver flagged
          # because the user rosters an LV TIGHT END. Correct, but the
          # note has to name him or it reads as nonsense.
          {"meta": {"position": "WR", "team": "LV"},
           "model_v": 50.0, "value": 100.0}]
    roster_adjust(rr, ["mine_wr", "mine_rb", "mine_te"], tbl, P)
    check("same-QB pass catcher haircut", rr[0]["value"] < 100.0)
    check("handcuff with standalone value bumped", rr[1]["value"] > 100.0)
    check("insurance-only handcuff NOT bumped", rr[2]["value"] == 40.0)
    check("unrelated WR untouched", rr[3]["value"] == 100.0)
    check("a WR collides with my TE on the same team",
          rr[4]["value"] < 100.0)
    check("...and the note NAMES him rather than saying 'your LV guy'",
          "Brock Bowers" in rr[4]["note"])
    check("cross-position collision is softer than same-position",
          rr[4]["value"] > rr[0]["value"])
    check("same-position note says so", "same position" in rr[0]["note"])
    check("handcuff note names the back it backs up",
          "My Back" in rr[1]["note"])

    # POSITIONAL SATURATION. The Loveland-over-Jefferson result survived
    # a damping fix and a rise fix because both treated it as a
    # magnitude problem. It was a slot problem: he already held Bowers,
    # and a 1-TE league does not give a second elite TE a second slot.
    RP = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "DEF", "BN"]
    REPL = {"QB": 300.0, "RB": 150.0, "WR": 165.0, "TE": 100.0}
    bar, kind = saturation_bar("TE", RP, REPL)
    check(f"a saturated TE is priced vs the flex bar ({bar:.0f}), not "
          f"TE ({REPL['TE']:.0f})", kind == "flex" and bar == 165.0)
    check("a saturated QB in a 1QB league has no flex path",
          saturation_bar("QB", RP, REPL)[1] == "bench")
    check("...but in superflex he does",
          saturation_bar("QB", RP[:-2] + ["SUPER_FLEX"], REPL)[1] == "flex")

    tbl2 = {"bowers": {"position": "TE", "team": "LV",
                       "full_name": "Brock Bowers"}}
    def te_row():
        return [{"meta": {"position": "TE", "team": "CHI"}, "proj": 215.0,
                 "model_v": 273.0, "value": 273.0}]
    free = te_row()
    roster_adjust(free, [], tbl2, P, roster_positions=RP, repl=REPL)
    blocked = te_row()
    roster_adjust(blocked, ["bowers"], tbl2, P,
                  roster_positions=RP, repl=REPL)
    # (215-165)/(215-100) = 0.435
    check(f"TE behind Bowers rescaled {free[0]['value']:.0f} -> "
          f"{blocked[0]['value']:.0f}", blocked[0]["value"] < 125)
    check("...by the exact VORP ratio, not a fudge factor",
          abs(blocked[0]["value"] - 273.0 * (215 - 165) / (215 - 100)) < 0.1)
    check("...and the note names who blocks him",
          "Brock Bowers" in blocked[0]["note"])
    check("an unsaturated TE is untouched", free[0]["value"] == 273.0)
    check("...and carries no note", not free[0].get("note"))

    # a WR at the position that SETS the flex bar must not be haircut:
    # his own bar already is the flex bar, so the ratio is exactly 1.
    wr = [{"meta": {"position": "WR", "team": "MIN"}, "proj": 250.0,
           "model_v": 200.0, "value": 200.0}]
    tbl3 = {"a": {"position": "WR", "full_name": "WR One", "team": "SF"},
            "b": {"position": "WR", "full_name": "WR Two", "team": "KC"}}
    roster_adjust(wr, ["a", "b"], tbl3, P, roster_positions=RP, repl=REPL)
    check("a 3rd WR is NOT haircut — WR already sets the flex bar",
          wr[0]["value"] == 200.0)

    # QB2 in a 1QB league: no flex path, so bench_mult, not the ratio.
    qb = [{"meta": {"position": "QB", "team": "NYG"}, "proj": 265.0,
           "model_v": 165.0, "value": 165.0}]
    tbl4 = {"q": {"position": "QB", "full_name": "My QB", "team": "NYG"}}
    roster_adjust(qb, ["q"], tbl4, P, roster_positions=RP, repl=REPL)
    check(f"QB2 in a 1QB league cut to bench value "
          f"({qb[0]['value']:.0f})", qb[0]["value"] < 60)
    check("...and says he has no starting slot",
          "no starting slot" in qb[0]["note"])

    # saturation must stay OFF for callers that don't pass the league
    old = te_row()
    roster_adjust(old, ["bowers"], tbl2, P)
    check("no roster_positions/repl -> saturation skipped (back-compat)",
          old[0]["value"] == 273.0)

    # market blend: a zero-model rookie priced at dADP 5 must gain value
    rows = ([{"model_v": float(v), "adp": None} for v in range(300, 0, -10)]
            + [{"model_v": 0.0, "adp": 5.0}])
    blend_market(rows, P)
    rook = rows[-1]
    check(f"dADP-5 rookie blends up from 0 to {rook['value']}",
          rook["value"] > 0)

    # SCARCITY DAMPING: a one-TE league puts TE replacement far below
    # WR replacement, and the multi-year sum multiplies the gap. Real
    # effect, implausible magnitude.
    repl = {"TE": 80.0, "WR": 200.0, "RB": 120.0, "QB": 238.0}
    wts = {"TE": 40, "WR": 160, "RB": 90, "QB": 60}
    dp = damped_replacement(repl, P, wts)
    spread0 = max(repl.values()) - min(repl.values())
    spread1 = max(dp.values()) - min(dp.values())
    check(f"damping narrows the cross-position spread "
          f"({spread0:.0f} -> {spread1:.0f})", spread1 < spread0)
    check("scarce position's bar rises", dp["TE"] > repl["TE"])
    r_before = (208 - repl["TE"]) / (250 - repl["WR"])
    r_after = (208 - dp["TE"]) / (250 - dp["WR"])
    check(f"elite TE / elite WR surplus ratio shrinks "
          f"({r_before:.1f}x -> {r_after:.1f}x)", r_after < r_before)
    check("damp 0 is a no-op",
          damped_replacement(repl, {"roster": {"scarcity_damp": 0}}) == repl)

    # ONE-SIDED. Damping must never LOWER a bar. A deep position's bar
    # is high because replacement there is a real player; pulling it
    # down invents surplus. Two-sided damping cut the 1QB bar by ~43
    # points a season and the discounted sum turned that into ~285
    # points handed to every quarterback on the board (8/11 bug).
    check("deep position's bar is left alone", dp["WR"] == repl["WR"])
    check("above-average bar never falls",
          all(dp[p] >= repl[p] for p in repl))
    q = {"QB": 300.0, "RB": 150.0, "WR": 160.0, "TE": 95.0}
    dq = damped_replacement(q, P)
    check(f"1QB bar holds at {dq['QB']:.0f}, not subsidised",
          dq["QB"] == q["QB"])
    span = sum(P["discount"] ** t for t in range(20))
    check(f"...worth ~{(300 - 256.7) * span:.0f} pts of phantom QB "
          f"surplus avoided", (q["QB"] - dq["QB"]) * span == 0)

    # DISAGREEMENT must be a RATIO. The case it exists to catch is the
    # model at #1 vs the market near #28 — only 27 ranks apart, which any
    # absolute cut large enough to ignore bottom-of-board noise misses.
    pool = [{"value": 1000.0 - i, "adp": float(i + 1)} for i in range(300)]
    loveland = {"value": 1001.0, "adp": 28.0}      # model #1, market ~#28
    noise = {"value": 700.0, "adp": 320.0}         # deep, small ratio
    rows = [loveland] + pool + [noise]
    market_disagreement(rows)
    check("model-#1 vs market-#28 is flagged",
          loveland["disagree"] is not None)
    check("...and reads as a multiple",
          "x)" in (loveland["disagree"][2] if loveland["disagree"] else ""))
    check("a deep player 20 ranks off is NOT flagged",
          noise["disagree"] is None)
    near = [{"value": 10.0, "adp": 1.0}, {"value": 9.0, "adp": 3.0}]
    market_disagreement(near)
    check("rank 1 vs rank 3 does not flag on ratio alone",
          all(r["disagree"] is None for r in near))

    # tiers: one obvious cliff -> exactly one break at it
    vals = [300.0, 295.0, 290.0, 180.0, 176.0, 173.0]
    br = tier_breaks(vals, P)
    check(f"cliff detected at index 2 only (got {sorted(br)})", br == {2})

    # SCALE-FREE: the same shape at 1/10th the magnitude must tier the
    # same way. An absolute floor put every player in Tier 1 once values
    # became surplus-over-replacement.
    small = [v / 10.0 for v in vals]
    check(f"same shape at 1/10 scale tiers identically "
          f"(got {sorted(tier_breaks(small, P))})",
          tier_breaks(small, P) == br)
    tiny = [v / 100.0 for v in vals]
    check("...and at 1/100 scale", tier_breaks(tiny, P) == br)

    # the real board that failed: 83 down to 28, no gap over 16
    live = [83.0, 67.0, 51.0, 51.0, 44.0, 41.0, 39.0, 37.0, 35.0, 34.0, 28.0]
    lb = tier_breaks(live, P)
    check(f"a real double-digit board produces MORE than one tier "
          f"(breaks at {sorted(lb)})", len(lb) >= 1)
    check("...and not a break at every row", len(lb) < len(live) - 2)

    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--selftest":
        selftest() if args else sys.exit(__doc__)
    pos = args[args.index("--pos") + 1] if "--pos" in args else None
    top = int(args[args.index("--top") + 1]) if "--top" in args else 40
    run(args[0], pos_filter=pos, top=top, include_gone="--all" in args)
