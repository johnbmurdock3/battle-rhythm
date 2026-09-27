"""
Weekly ops — every league in one pass: lineup check, two-tier waiver targets,
and trade flags. All values are rest-of-season (ROS) projections scored by each
league's OWN rules via the verified dot-product engine.

Usage (networked machine):
  python weekly.py                 # full brief, all leagues
  python weekly.py <league_id>     # one league
  python weekly.py --json out.json # machine-readable snapshot (MCP later)

Logic, as agreed:
  Waiver TIER 1 (spend FAAB): FA's ROS projection beats one of your projected
    starters at a slot they can fill. These change lineups.
  Waiver TIER 2 (churn): FA beats your worst bench player at their position.
    Stashes and upside; bid minimum or pick up free.
  Trade flags:
    - surplus/deficit: 3+ above-replacement players at one position while your
      best-of-position ranks bottom-half among that league's starters elsewhere.
    - bye pileup: 3+ projected starters sharing a bye week.
    - playoff leverage: sum of weeks 15-17 projections (opponents are already
      baked into weekly projections) — flags starters who crater in your
      playoff window.
    - value gap: rank under THIS league's scoring vs PPR ADP rank. Big positive
      gap = this league's rules like them more than the market does (buy/hold);
      big negative = market darling your rules dislike (sell candidate).
Replacement level per position = the Nth-ranked ROS player, N = starter demand
(teams x dedicated slots, flex allocated by historical share RB/WR/TE 40/45/15,
superflex mostly QB). Crude but stated; tune later.

Added 9/11 — waivers v2, every item a defect John caught by hand first:
  - RESERVE IS NOT BENCH. Sleeper's roster carries `reserve` (IR) and
    `taxi` lists. Every drop suggestion came from `bench = mine - starters`,
    which includes them, so James Conner (in reserve, costing no active
    spot) was the named drop in every LG04 claim. Excluded now.
  - THE MODEL HAD NO DEPTH CHART. Tyrone Tracy at +78.9 over Jacob
    Saylors: the feed still priced Tracy as the Giants' lead back after
    New York drafted Skattebo and signed Najee Harris. The player table
    already carries depth_chart_position / depth_chart_order; nothing
    read them. Every waiver row now prints the depth slot and flags a
    projection that prices a role the chart says he no longer holds.
    Handcuffs (a backup whose starter is on MY roster) are named too.
  - FAAB BIDS ARE SIZED, not just "spend". Stated formula in faab_bid();
    the ledger records the bid so the claim history can correct it.
  - ORDER-BASED LEAGUES show your waiver position. LG02 has no FAAB
    and one premium claim before you are last in a 14-team room.
  - EVERY RECOMMENDATION IS RECORDED (ledger.py) and scored the next
    Tuesday. --no-record skips it. This is the 9/4 eval, not a feature.
"""

import json
import sys
from collections import defaultdict

from battle_rhythm.sleeper_client import (get, players, name_of, score, state,
                            load_leagues, USERNAME)
from battle_rhythm.draft_helper import (weekly_projections, adp_of, _adp, availability_ratios,
                          injury_tag, DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)

FLEX_ELIG = {"FLEX": ("RB", "WR", "TE"), "WRRB_FLEX": ("RB", "WR"),
             "REC_FLEX": ("WR", "TE"), "SUPER_FLEX": ("QB", "RB", "WR", "TE")}
# One definition, in roster_shape.py. This block was byte-identical in
# draft_review, roster_snapshot and weekly.
from battle_rhythm.roster_shape import FLEX_SHARE  # noqa: E402,F401
CORE = ("QB", "RB", "WR", "TE", "K", "DEF")
PLAYOFF_WEEKS = (15, 16, 17)


def ros_totals(season, scoring, start_week):
    """{pid: ROS fantasy pts under scoring}, and playoff-window pts.
    Both scaled by the feed's per-player availability ratio (see
    draft_helper.availability_ratios) so totals track the app."""
    ros, playoff = defaultdict(float), defaultdict(float)
    for wk in range(start_week, 19):
        for pid, stats in weekly_projections(season, wk).items():
            if stats:
                pts = score(stats, scoring)
                ros[pid] += pts
                if wk in PLAYOFF_WEEKS:
                    playoff[pid] += pts
    ratios = availability_ratios(season)
    return ({p: round(v * ratios.get(p, 1.0), 1) for p, v in ros.items()},
            {p: round(v * ratios.get(p, 1.0), 1) for p, v in playoff.items()})


# Cannot play this week. Doubtful and Questionable are left alone: they are
# probabilities, the pip already shows them, and zeroing a Questionable
# would bench half the league every Sunday.
CANNOT_PLAY = ("Out", "IR", "PUP", "Sus", "NA", "DNR", "COV")


_CALIB = [None]


def calibration():
    """data/measured/calibration.json, or {} — measured, never assumed.

    Lives in data/measured/ beside room_bias.json because it is the same
    kind of thing: a number taken off real results rather than reasoned
    into existence. Absent file means every confidence reads None and the
    output simply omits the odds, which is the correct behaviour for a
    machine that has not measured anything yet.
    """
    if _CALIB[0] is None:
        try:
            from battle_rhythm import paths
            import json as _j
            _CALIB[0] = _j.loads(paths.measured("calibration.json")
                                 .read_text(encoding="utf-8"))
        except Exception:
            _CALIB[0] = {}
    return _CALIB[0]


def edge_confidence(gap):
    """How often a projection edge of this size actually wins. None if
    unmeasured — a gap with no odds beside it is better than a made-up
    one."""
    try:
        from battle_rhythm.backtest import confidence
        return confidence(gap, (calibration() or {}).get("overall") or {})
    except Exception:
        return None


def week_points(season, scoring, week, tbl):
    """{pid: this WEEK's league-scored projection}, zero for anyone ruled out.

    A LINEUP IS A ONE-WEEK DECISION AND THIS MODULE WAS ANSWERING A
    SEASON ONE. optimal_starters ran on rest-of-season totals, which carry
    the availability haircut -- a probability spread across eighteen weeks.
    This week a player either suits up or he does not; if he suits up you
    get his week number, and if he is going to miss time in November you
    can bench him in November.

    Found 9/3 by John, from the lineup: Brian Thomas starting over DJ
    Moore in the emoji Hybrid's FLEX. Moore out-projects him EVERY week --
    14.5 to 12.8 in week 1, ahead in all six before the bye -- and loses
    only after a season-long durability discount is applied to a single
    Sunday. Three of his four in-season leagues had a start/sit that
    flipped this way in week 1 alone.

    ROS stays the right objective for waivers and trades, which are
    hold-him-or-not questions. It is the wrong one for who to start.
    """
    out = {}
    for pid, stats in weekly_projections(season, week).items():
        if not stats:
            continue
        st = (tbl.get(pid) or {}).get("injury_status")
        out[pid] = 0.0 if st in CANNOT_PLAY else score(stats, scoring)
    return out


_LOCKED = {}


def locked_teams(season, week, tbl, fetch=None):
    """Teams whose game this week has already kicked off. Every player on
    such a team is LOCKED in Sleeper -- cannot be benched, cannot be
    started -- and the optimiser did not know that until 9/12: it told
    John to bench A.J. Brown, who had been hurt on Thursday night and
    could not be moved.

    The signal is the current week's stats feed. Sleeper writes a line
    for a player only once his game is under way, so a team with ANY
    stat line this week has started. Fetched fresh every run and never
    written to the hist_ cache, because that cache is for finished
    weeks and this one is not. Empty on a network miss, which means
    "nothing locked" -- the pre-9/12 behaviour, not a crash."""
    key = (str(season), int(week))
    if key in _LOCKED:
        return _LOCKED[key]
    teams = set()
    try:
        if fetch is not None:
            raw = fetch(season, week)
        else:
            from battle_rhythm.sleeper_client import _get, BASE, STATS_BASE
            from battle_rhythm.draft_helper import _normalize
            raw = _get(f"{BASE}/stats/nfl/regular/{season}/{week}")
            if not raw:
                raw = _get(f"{STATS_BASE}/stats/nfl/{season}/{week}?season_type=regular")
            raw = _normalize(raw or {})
        for pid, line in (raw or {}).items():
            if not line:
                continue
            if any(isinstance(v, (int, float)) and v for v in line.values()):
                team = (tbl.get(str(pid)) or {}).get("team")
                if team:
                    teams.add(team)
    except Exception:
        teams = set()
    _LOCKED[key] = teams
    return teams


def starter_demand(roster_positions, teams):
    """{pos: league-wide starter slots}, flex spread by assumed share."""
    d = defaultdict(float)
    for slot in roster_positions or []:
        if slot in CORE:
            d[slot] += 1
        elif slot in FLEX_SHARE:
            for pos, share in FLEX_SHARE[slot].items():
                d[pos] += share
    return {pos: max(1, round(n * teams)) for pos, n in d.items()}


def optimal_starters(pids, roster_positions, ros, tbl):
    """Greedy fill: dedicated slots best-first, then flex. Returns [(slot, pid)]."""
    pool = sorted((p for p in pids if p in ros), key=lambda p: -ros[p])
    used, out = set(), []
    slots = [s for s in roster_positions if s != "BN"]
    for slot in [s for s in slots if s in CORE]:
        pick = next((p for p in pool if p not in used
                     and (tbl.get(p) or {}).get("position") == slot), None)
        if pick:
            used.add(pick); out.append((slot, pick))
    for slot in [s for s in slots if s in FLEX_ELIG]:
        elig = FLEX_ELIG[slot]
        pick = next((p for p in pool if p not in used
                     and (tbl.get(p) or {}).get("position") in elig), None)
        if pick:
            used.add(pick); out.append((slot, pick))
    return out


# ------------------------------------------------------------ depth chart
#
# Sleeper's player table carries `depth_chart_position` (QB, RB, TE, and
# for receivers the SLOT: LWR / RWR / SWR) and `depth_chart_order`
# (1-based within that slot). So "LWR 1" is a starter and "RB 3" is not.
# The order at which a full-season projection stops being believable
# is per position: a second quarterback plays only on injury, a third
# back is a special-teamer.
#
# RECEIVERS ARE NOT FLAGGED. First live run, LG04 9/12: the flag fired
# on six of eight rows -- Keenan Allen RWR3, Bateman LWR2, Jennings SWR3.
# Sleeper stacks several men under each receiver slot, so "order 2 at a
# slot" is not WR4; it is the chart's filing system. A flag on 75% of
# rows is noise. The slot still prints; the reader decides. This was the
# lesson-6 error (a rule generalised from two backs) and it lasted one
# run.
DEPTH_STALE = {"QB": 2, "RB": 3, "TE": 2}


def depth_of(meta):
    """'RB2', 'LWR1', '' when the chart has nothing. Display string."""
    pos, order = meta.get("depth_chart_position"), meta.get("depth_chart_order")
    if not pos or not order:
        return ""
    return f"{pos}{order}"


def role_is_stale(meta):
    """True when the chart puts him below the depth a starter's projection
    could survive. Not a verdict — a prompt to read the situation. The
    two sightings (Tracy, MarShawn Lloyd) were both order >= 3 backs."""
    pos = meta.get("position")
    order = meta.get("depth_chart_order")
    if not pos or not order or pos not in DEPTH_STALE:
        return False
    return int(order) >= DEPTH_STALE[pos]


def team_starters(tbl, pos="RB"):
    """{team: pid} for the depth-chart order-1 player at `pos`. One scan
    of the table; RB only by default because that is where handcuff
    value lives."""
    out = {}
    for pid, m in tbl.items():
        if (m.get("position") == pos and m.get("team")
                and m.get("depth_chart_position") == pos
                and m.get("depth_chart_order") == 1):
            out[m["team"]] = str(pid)
    return out


def handcuff_of(meta, my_rb1_by_team):
    """The pid of MY starter this player backs up, or None."""
    if (meta.get("position") == "RB" and meta.get("depth_chart_position") == "RB"
            and meta.get("depth_chart_order") == 2):
        return my_rb1_by_team.get(meta.get("team"))
    return None


# ---------------------------------------------------------------- FAAB
#
# A STATED heuristic, not a measured one. It is written down so the
# ledger can prove it wrong: every bid is recorded, the transactions
# feed says what actually won, and the number that keeps losing gets
# raised. Until there is a season of claims behind it, this is a prior.
#
#   reserve   = budget x 0.5 x (weeks left / 17)   hold-back that decays
#   spendable = budget - reserve
#   share     = this add's gap / sum of tier-1 gaps in THIS league THIS week
#   bid       = spendable x share, at least 1, never over the budget
#
# The share term is the point: FAAB competes with the other claims you
# could make this week, not with an abstract "how good is he". One tier-1
# add in a week gets the whole spendable slice; four split it.
WEEKS_END = PLAYOFF_WEEKS[-1]


def faab_bid(gap, gaps_this_week, budget_left, week):
    if not budget_left or budget_left <= 0 or gap <= 0:
        return 0, "no budget" if not budget_left else "no edge"
    weeks_left = max(WEEKS_END - int(week) + 1, 1)
    reserve = budget_left * 0.5 * (weeks_left / 17.0)
    spendable = max(budget_left - reserve, 0.0)
    total = sum(g for g in gaps_this_week if g > 0) or gap
    share = gap / total
    bid = int(min(max(round(spendable * share), 1), budget_left))
    why = (f"{budget_left} left, hold back {reserve:.0f} for {weeks_left} more weeks, "
           f"this add is {100 * share:.0f}% of this week's tier-1 value")
    return bid, why


# Sleeper's settings.waiver_type. 2 is FAAB and is verified (budget and
# budget_used both real, 8/9). 0 and 1 are order-based; the labels below
# are Sleeper's UI names as best I know them and are NOT verified against
# a league page -- LG02 (type 0 in the feed) is described by John as
# rolling-reset-to-back. Read the position, not the label.
WAIVER_MODE = {2: "FAAB", 1: "rolling order", 0: "waiver order"}


def faab_comps(league_id, week, get_fn=None):
    """Winning FAAB bids in this league so far this season, all managers.
    [] when there is no history yet (four of the seven leagues are 2026
    startups) or the feed cannot be read. Weeks before `week` only --
    the current week's claims have not processed."""
    get_fn = get_fn or get
    bids = []
    for w in range(1, max(int(week), 1)):
        try:
            txs = get_fn(f"league/{league_id}/transactions/{w}") or []
        except Exception:
            break
        for t in txs:
            if t.get("type") == "waiver" and t.get("status") == "complete":
                b = (t.get("settings") or {}).get("waiver_bid")
                if isinstance(b, (int, float)) and b > 0:
                    bids.append(int(b))
    return sorted(bids)


def league_brief(lg, season, week, tbl, out):
    scoring = lg["scoring_settings"] or {}
    ros, playoff = ros_totals(season, scoring, max(week, 1))
    teams = lg["total_teams"]
    demand = starter_demand(lg["roster_positions"], teams)

    rosters = get(f"league/{lg['league_id']}/rosters") or []
    rostered = set()
    for r in rosters:
        rostered |= set(r.get("players") or [])
    mine = set(lg["my_players"])

    # RESERVE AND TAXI ARE NOT BENCH. They cost no active spot, so they
    # are never the drop for a claim and never the "worst bench player"
    # a tier-2 add has to beat. Read off MY roster row, found below by
    # owner id; empty until then and re-derived once my_row is known.
    parked = set()

    pos_of = lambda p: (tbl.get(p) or {}).get("position")
    by_pos = defaultdict(list)
    for pid, pts in ros.items():
        if pos_of(pid) in CORE:
            by_pos[pos_of(pid)].append((pts, pid))
    for v in by_pos.values():
        v.sort(reverse=True)

    replacement = {pos: (v[demand.get(pos, 1) - 1][0] if len(v) >= demand.get(pos, 1) else 0.0)
                   for pos, v in by_pos.items()}

    # WHAT YOU ACTUALLY HAVE STARTED, not what you should.
    #
    # Every in-season view in this toolkit computed the OPTIMAL lineup and
    # stopped there, which quietly assumes you set it. The one thing a
    # Thursday brief exists to catch -- a bench player who out-projects a
    # starter you left in -- was therefore invisible. Sleeper's roster
    # object carries a `starters` array, positional against
    # roster_positions, "0" for an empty slot.
    slots_named = [x for x in (lg["roster_positions"] or [])
                   if x not in ("BN", "IR", "TAXI")]
    my_row = None
    try:
        from battle_rhythm.draft_helper import uid as _uid
        me = _uid()
        my_row = next((r for r in rosters
                       if str(r.get("owner_id")) == str(me)), None)
    except Exception:
        pass
    if my_row is None and rosters:          # fall back on roster overlap
        my_row = max(rosters, key=lambda r: len(set(r.get("players") or []) & mine),
                     default=None)
        if my_row is not None and not (set(my_row.get("players") or []) & mine):
            my_row = None
    if my_row:
        parked = {str(p) for p in (my_row.get("reserve") or [])} \
               | {str(p) for p in (my_row.get("taxi") or [])}
    active = mine - parked

    # THE LINEUP IS SOLVED ON THIS WEEK, not on the season. See week_points.
    # Solved on the ACTIVE roster: a reserve player cannot be started.
    wkpts = week_points(season, scoring, max(week, 1), tbl)
    starters = optimal_starters(active, lg["roster_positions"] or [], wkpts, tbl)
    starter_ids = {p for _, p in starters}
    # The season answer is still worth having beside it -- it is what
    # waivers and trades are solved on, and where the two disagree is
    # itself information.
    ros_starters = optimal_starters(active, lg["roster_positions"] or [], ros, tbl)
    ros_starter_ids = {p for _, p in ros_starters}
    bench = active - starter_ids
    worst_bench_at = {}
    for p in bench:
        pos = pos_of(p)
        if pos and (pos not in worst_bench_at or ros.get(p, 0) < ros.get(worst_bench_at[pos], 0)):
            worst_bench_at[pos] = p

    actual_pairs = []
    if my_row:
        for i, pid in enumerate(my_row.get("starters") or []):
            if not pid or str(pid) == "0":
                continue
            actual_pairs.append((slots_named[i] if i < len(slots_named) else "?",
                                 str(pid)))
    actual_ids = [p for _, p in actual_pairs]

    L = {"league": lg["name"], "league_id": lg["league_id"], "status": lg.get("status"),
         "optimal_starters": [], "waivers_tier1": [], "waivers_tier2": [],
         "trade_flags": [], "trades": [], "roster_ranked": [],
         "actual_starters": [], "lineup_diff": [], "lineup_gap": 0.0,
         "lineup_known": bool(actual_pairs),
         "parked": sorted(parked), "waiver": {}}

    # --- the waiver situation: what you can spend, or where you stand
    settings = lg.get("settings") or {}
    wtype = settings.get("waiver_type")
    W = {"mode": WAIVER_MODE.get(wtype, f"type {wtype}"), "type": wtype,
         "faab_left": None, "faab_budget": None, "position": None,
         "comps": []}
    if wtype == 2 and settings.get("waiver_budget"):
        used = (my_row or {}).get("settings", {}).get("waiver_budget_used")
        if used is None:
            used = lg.get("my_faab_used") or 0
        W["faab_budget"] = settings["waiver_budget"]
        W["faab_left"] = settings["waiver_budget"] - (used or 0)
        W["comps"] = faab_comps(lg["league_id"], week)
    elif my_row:
        W["position"] = (my_row.get("settings") or {}).get("waiver_position")
    L["waiver"] = W

    for slot, pid in actual_pairs:
        L["actual_starters"].append(
            {"slot": slot, "player": name_of(pid, tbl), "pid": pid,
             "ros": ros.get(pid, 0.0), "optimal": pid in starter_ids,
             "inj": injury_tag(tbl.get(pid) or {})})

    # The swaps. optimal_starters already solved the optimum, so the diff is
    # simply the symmetric difference -- anyone the optimum starts and you do
    # not, against anyone you start and it does not. Paired by rank so the
    # biggest gain reads first; the pairing is presentational, the TOTAL is
    # the honest number and it is reported separately.
    locked = locked_teams(season, max(week, 1), tbl)
    is_locked = lambda p: (tbl.get(p) or {}).get("team") in locked
    L["locked"] = sorted(p for p in mine if is_locked(p))
    if actual_pairs:
        # A locked player is on neither list: you cannot sit him and you
        # cannot start him. The gap below is what you can still close.
        sit = sorted((p for p in actual_ids if p not in starter_ids and not is_locked(p)),
                     key=lambda p: ros.get(p, 0.0))
        start = sorted((p for p in starter_ids if p not in set(actual_ids) and not is_locked(p)),
                       key=lambda p: -ros.get(p, 0.0))
        # PAIR BY POSITION, NOT BY RANK. Zipping the two lists printed
        # "start Jayden Reed (WR) over Jayden Daniels (QB), +-7.2, 75%"
        # in a superflex league on 9/12: the real swaps were Reed for a
        # ruled-out A.J. Brown and Geno for Daniels at SUPER_FLEX. The
        # total was right; every line under it was wrong -- a receiver
        # over a quarterback, a negative gain with a plus sign, odds
        # taken on the absolute value. Same position first, then anyone
        # left; the gap and the odds belong to the pair actually printed.
        pairs, left = [], list(sit)
        for in_p in start:
            same = [q for q in left if pos_of(q) == pos_of(in_p)]
            out_p = same[0] if same else (left[0] if left else None)
            if out_p is None:
                break
            left.remove(out_p)
            pairs.append((out_p, in_p))
        for out_p, in_p in pairs:
            L["lineup_diff"].append(
                {"out": name_of(out_p, tbl), "in": name_of(in_p, tbl),
                 "out_pid": out_p, "in_pid": in_p,
                 "out_ros": round(wkpts.get(out_p, 0.0), 1),
                 "in_ros": round(wkpts.get(in_p, 0.0), 1),
                 "gain": round(wkpts.get(in_p, 0.0) - wkpts.get(out_p, 0.0), 1),
                 # odds only for an edge in the printed direction; a
                 # negative pair is a cross-position artefact of the
                 # optimiser rebalancing flex, not a call to make
                 "conf": (edge_confidence(wkpts.get(in_p, 0.0) - wkpts.get(out_p, 0.0))
                          if wkpts.get(in_p, 0.0) > wkpts.get(out_p, 0.0) else None),
                 "in_inj": injury_tag(tbl.get(in_p) or {})})
        # THIS WEEK's points, because that is what the swap wins or loses --
        # and only the swaps you can still make. A locked player's
        # shortfall is sunk, not advice.
        L["lineup_gap"] = round(sum(d["gain"] for d in L["lineup_diff"]), 1)

    slot_of_optimal = {p: slot for slot, p in starters}
    for p in sorted(mine, key=lambda x: -ros.get(x, 0)):
        L["roster_ranked"].append({"player": name_of(p, tbl), "pid": p,
                                   "pos": pos_of(p) or "",
                                   "ros": ros.get(p, 0.0),
                                   "playoff": playoff.get(p, 0.0),
                                   "inj": injury_tag(tbl.get(p) or {}),
                                   "wk": round(wkpts.get(p, 0.0), 1),
                                   "starter": p in starter_ids,
                                   "ros_starter": p in ros_starter_ids,
                                   "slot": slot_of_optimal.get(p, "")
                                           or ("IR" if p in parked else ""),
                                   "parked": p in parked,
                                   "depth": depth_of(tbl.get(p) or {}),
                                   "stale_role": role_is_stale(tbl.get(p) or {}),
                                   "started": p in set(actual_ids)})

    # the drop for any claim: lowest-ROS ACTIVE bench player. Reserve and
    # taxi are excluded above; projections still don't know about a
    # healthy stash you are holding on purpose -- overrule freely, that's
    # why the name is shown.
    droppable = sorted(bench, key=lambda p: ros.get(p, 0.0))
    drop_pid = droppable[0] if droppable else None
    drop_name = name_of(drop_pid, tbl) if drop_pid else None

    for slot, p in starters:
        L["optimal_starters"].append(
            {"slot": slot, "player": name_of(p, tbl),
             "wk": round(wkpts.get(p, 0.0), 1), "ros": ros.get(p, 0),
             "playoff_1517": playoff.get(p, 0)})

    # --- waivers
    fas = [(pts, pid) for pid, pts in ros.items()
           if pid not in rostered and pos_of(pid) in CORE and pts > 0]
    fas.sort(reverse=True)
    # depth-chart context: who my backs' handcuffs are, and the top few
    # free agents at each position (the ones other managers also see)
    rb1_by_team = team_starters(tbl, "RB")
    my_rb1_by_team = {t: p for t, p in rb1_by_team.items() if p in mine}
    fa_rank_at = defaultdict(int)
    for pts, pid in fas[:150]:
        pos = pos_of(pid)
        meta = tbl.get(pid) or {}
        fa_rank_at[pos] += 1
        cuff = handcuff_of(meta, my_rb1_by_team)
        row = {"add": name_of(pid, tbl), "add_pid": pid, "ros": pts,
               "drop": drop_name, "drop_pid": drop_pid,
               "inj": injury_tag(meta),
               "depth": depth_of(meta), "stale_role": role_is_stale(meta),
               "handcuff_to": name_of(cuff, tbl) if cuff else None,
               "contested": fa_rank_at[pos] <= 3}
        # tier 1: beats a current projected starter at an eligible slot
        beaten = [(slot, sp) for slot, sp in starters
                  if pos == slot or (slot in FLEX_ELIG and pos in FLEX_ELIG[slot])
                  if pts > ros.get(sp, 0)]
        if beaten:
            slot, sp = min(beaten, key=lambda x: ros.get(x[1], 0))
            row.update({"over": name_of(sp, tbl), "over_pid": sp,
                        "gap": round(pts - ros.get(sp, 0), 1)})
            L["waivers_tier1"].append(row)
        elif pos in worst_bench_at and pts > ros.get(worst_bench_at[pos], 0):
            wb = worst_bench_at[pos]
            row.update({"over": name_of(wb, tbl), "over_pid": wb,
                        "gap": round(pts - ros.get(wb, 0), 1)})
            L["waivers_tier2"].append(row)
    L["waivers_tier1"] = L["waivers_tier1"][:8]
    L["waivers_tier2"] = L["waivers_tier2"][:8]

    # bids: tier 1 competes for the spendable slice; tier 2 is a dollar,
    # because churn that costs more than a dollar is not churn.
    if W["faab_left"] is not None:
        gaps = [w["gap"] for w in L["waivers_tier1"]]
        for w in L["waivers_tier1"]:
            w["bid"], w["bid_why"] = faab_bid(w["gap"], gaps, W["faab_left"], week)
        for w in L["waivers_tier2"]:
            w["bid"], w["bid_why"] = (1 if W["faab_left"] > 0 else 0), "churn: minimum"
    else:
        for w in L["waivers_tier1"] + L["waivers_tier2"]:
            w["bid"], w["bid_why"] = None, (
                f"order league, you are #{W['position']}" if W["position"]
                else "order league")

    # --- trade flags
    above_rep = defaultdict(list)
    for p in mine:
        pos = pos_of(p)
        if pos and ros.get(p, 0) > replacement.get(pos, 0):
            above_rep[pos].append(p)
    surplus = {pos: ps for pos, ps in above_rep.items() if len(ps) >= 3}
    for pos, v in by_pos.items():
        if pos in ("K", "DEF") or pos not in demand:
            continue
        mine_at = sorted((ros.get(p, 0) for p in mine if pos_of(p) == pos), reverse=True)
        starters_at = [pts for pts, _ in v[:demand[pos]]]
        if starters_at and (not mine_at or mine_at[0] < starters_at[len(starters_at) // 2]):
            if surplus:
                L["trade_flags"].append(
                    {"type": "surplus_deficit",
                     "note": f"deficit at {pos} (best={mine_at[0] if mine_at else 0}, "
                             f"median starter={starters_at[len(starters_at)//2]}); "
                             f"surplus at {'/'.join(surplus)} to trade from"})

    byes = defaultdict(list)
    for _, p in starters:
        wk_stats = [w for w in range(max(week, 1), 19)
                    if not weekly_projections(season, w).get(p)]
        # a missing single mid-season week ~ bye
        for w in wk_stats:
            byes[w].append(p)
    for w, ps in sorted(byes.items()):
        if len(ps) >= 3:
            L["trade_flags"].append(
                {"type": "bye_pileup",
                 "note": f"week {w}: {len(ps)} starters out — "
                         + ", ".join(name_of(p, tbl).split(' (')[0] for p in ps)})

    weak_playoff = [(playoff.get(p, 0), p) for _, p in starters
                    if pos_of(p) not in ("K", "DEF")]
    weak_playoff.sort()
    if weak_playoff:
        pts, p = weak_playoff[0]
        L["trade_flags"].append(
            {"type": "playoff_leverage",
             "note": f"weakest playoff window (wk15-17): {name_of(p, tbl)} projects {pts}"})

    # --- trade finder: 1-for-1 swaps where BOTH optimal-lineup totals improve.
    # Search my top players against each other roster's top players; a swap
    # qualifies only if each side's greedy-optimal starter total goes up by
    # more than TRADE_MIN points ROS. Both-sides-gain keeps the list to trades
    # a real manager might accept.
    TRADE_MIN = 5.0
    positions = lg["roster_positions"] or []

    def lineup_total(pids):
        return sum(ros.get(p, 0.0) for _, p in optimal_starters(pids, positions, ros, tbl))

    users = {u.get("user_id"): (u.get("display_name") or "?")
             for u in (get(f"league/{lg['league_id']}/users") or [])}
    base_me = lineup_total(mine)
    my_top = sorted(mine, key=lambda p: -ros.get(p, 0))[:12]
    for r in rosters:
        if set(r.get("players") or []) == mine or not r.get("players"):
            continue
        theirs = set(r["players"])
        base_them = lineup_total(theirs)
        partner = users.get(r.get("owner_id"), f"roster {r.get('roster_id')}")
        for a in my_top:
            for b in sorted(theirs, key=lambda p: -ros.get(p, 0))[:12]:
                gain_me = lineup_total((mine - {a}) | {b}) - base_me
                if gain_me <= TRADE_MIN:
                    continue
                gain_them = lineup_total((theirs - {b}) | {a}) - base_them
                if gain_them > TRADE_MIN:
                    L["trades"].append(
                        {"give": name_of(a, tbl), "get": name_of(b, tbl),
                         "give_pid": a, "get_pid": b,
                         "partner": partner, "my_gain": round(gain_me, 1),
                         "their_gain": round(gain_them, 1)})
    L["trades"].sort(key=lambda t: -t["my_gain"])
    L["trades"] = L["trades"][:6]

    # Dynasty leagues: ROS points are half the currency. Annotate each side of
    # every proposal with age and dynasty market price so the asset exchange is
    # visible next to the points exchange. Shown, not scored — your judgment.
    dynasty_lg = (lg.get("settings") or {}).get("type") == 2
    season_s = str(season)
    for t in L["trades"]:
        for side in ("give", "get"):
            pid = t[f"{side}_pid"]          # kept: the ledger keys on it
            t[f"{side}_age"] = (tbl.get(pid) or {}).get("age")
            if dynasty_lg:
                try:
                    adp, _ex = _adp(pid, season_s, DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)
                except Exception:
                    adp = None
                t[f"{side}_dadp"] = adp

    # value gaps on MY roster: league rank vs ADP rank
    ranked = sorted(((pts, pid) for pid, pts in ros.items() if pos_of(pid) in CORE),
                    reverse=True)
    lg_rank = {pid: i + 1 for i, (_, pid) in enumerate(ranked)}
    for p in sorted(mine, key=lambda x: -ros.get(x, 0))[:12]:
        adp = adp_of(p, season)
        if adp and lg_rank.get(p):
            gap = adp - lg_rank[p]  # positive: your rules like them more than market
            if abs(gap) >= 25:
                L["trade_flags"].append(
                    {"type": "value_gap",
                     "note": f"{name_of(p, tbl)}: rank {lg_rank[p]} here vs ADP {adp:.0f} "
                             f"({'hold/buy — market underrates in this format' if gap > 0 else 'sell-high — market pays more than your rules do'})"})
    out["leagues"].append(L)
    return L


def _waiver_line(w):
    tags = []
    if w.get("depth"):
        tags.append(w["depth"])
    if w.get("stale_role"):
        tags.append("ROLE? projection may price a job the chart says he lost")
    if w.get("handcuff_to"):
        tags.append(f"handcuff to your {w['handcuff_to'].split(' (')[0]}")
    if w.get("contested"):
        tags.append("contested")
    if w.get("inj"):
        tags.append(w["inj"])
    bid = f"bid {w['bid']:>3}  " if w.get("bid") is not None else ""
    return (f"    +{w['gap']:>5.1f}  {bid}add {w['add']}  drop {w.get('drop') or '—'}"
            f"  (over {w['over']})" + (f"  [{'; '.join(tags)}]" if tags else ""))


def print_waivers(L):
    W = L.get("waiver") or {}
    if W.get("faab_left") is not None:
        comps = W.get("comps") or []
        c = (f"; winning bids so far: {len(comps)}, median {comps[len(comps) // 2]},"
             f" max {comps[-1]}" if comps else "; no claim history yet")
        print(f"  waivers: FAAB {W['faab_left']}/{W['faab_budget']}{c}")
    else:
        pos = f", you are #{W['position']}" if W.get("position") else ""
        print(f"  waivers: {W.get('mode', '?')}{pos}")
    if L.get("parked"):
        print(f"  reserve/taxi (never a drop): {len(L['parked'])} player(s)")
    if L["waivers_tier1"]:
        print("  TIER 1 waivers — beats a starter (spend FAAB):")
        for w in L["waivers_tier1"]:
            print(_waiver_line(w))
        if L["waivers_tier1"][0].get("bid_why"):
            print(f"    bid logic: {L['waivers_tier1'][0]['bid_why']}")
    if L["waivers_tier2"]:
        print("  tier 2 waivers — beats worst bench (churn):")
        for w in L["waivers_tier2"]:
            print(_waiver_line(w))
    if not L["waivers_tier1"] and not L["waivers_tier2"]:
        print("  no free agent clears either bar this week")


def print_lineup(L):
    """What you have started against what the week says to start.

    The dashboard's ROSTER tab has shown this since 9/3; the terminal
    brief never did, so the one Sunday-morning item -- a bench player
    out-projecting a starter you left in -- was invisible from the CLI
    and the MCP tool. Found 9/12 when the ledger recorded two lineup
    calls nobody could see."""
    if not L.get("lineup_known"):
        print("  lineup: Sleeper has not published your starters yet")
        return
    nlock = len(L.get("locked") or [])
    lk = f" ({nlock} locked, game under way)" if nlock else ""
    if not L.get("lineup_diff"):
        print(f"  lineup: matches this week's optimum{lk}")
        return
    print(f"  LINEUP — you are leaving {L['lineup_gap']:.1f} pts on the bench this week{lk}:")
    for d in L["lineup_diff"]:
        odds = f"  ({100 * d['conf']:.0f}% an edge this size wins)" if d.get("conf") else ""
        inj = f"  [{d['in_inj']}]" if d.get("in_inj") else ""
        print(f"    start {d['in']}{inj} {d['in_ros']:.1f}  over {d['out']} {d['out_ros']:.1f}"
              f"  {d['gain']:+.1f}{odds}")


def print_brief(L):
    print(f"\n══ {L['league']} ({L['status']})")
    print_lineup(L)
    print("  optimal starters (ROS | wk15-17):")
    for s in L["optimal_starters"]:
        print(f"    {s['slot']:<11} {s['ros']:>7.1f} | {s['playoff_1517']:>6.1f}  {s['player']}")
    print_waivers(L)
    if L["trades"]:
        print("  trade candidates (both sides gain, ROS lineup pts):")
        for t in L["trades"]:
            def tag(side):
                bits = []
                if t.get(f"{side}_age"):
                    bits.append(f"age {t[f'{side}_age']}")
                if t.get(f"{side}_dadp"):
                    bits.append(f"dADP {t[f'{side}_dadp']:.0f}")
                return f" ({', '.join(bits)})" if bits else ""
            print(f"    give {t['give']}{tag('give')}  ->  get {t['get']}{tag('get')}"
                  f"  [{t['partner']}]  me +{t['my_gain']}, them +{t['their_gain']}")
    for t in L["trade_flags"]:
        print(f"  [{t['type']}] {t['note']}")


def main():
    """python br.py weekly [league] [--lineup] [--waivers] [--no-record] [--json out.json]

    A league is an id, slug, or alias (resolved through draft_helper.cli_league,
    the same resolver `board` uses). --waivers prints only the claim section.
    Every recommendation is written to the ledger unless --no-record.
    """
    args = sys.argv[1:]
    from battle_rhythm import ledger
    if "--no-record" in args:
        ledger.ENABLED[0] = False
    waivers_only = "--waivers" in args
    lineup_only = "--lineup" in args
    st = state()
    season, week = st.get("season"), max(st.get("week") or 1, 1)
    data = load_leagues(refresh=True)
    tbl = players()
    positional = [a for i, a in enumerate(args)
                  if not a.startswith("-") and (i == 0 or args[i - 1] != "--json")]
    only = positional[0] if positional else None
    if only and not only.isdigit():
        from battle_rhythm.draft_helper import cli_league
        only = cli_league(only)
    out = {"season": season, "week": week, "leagues": []}
    recorded = 0
    from battle_rhythm import paths as _paths
    ignored = _paths.ignored_ids()
    for lg in data["leagues"]:
        if only and lg["league_id"] != only:
            continue
        if lg["league_id"] in ignored and not only:
            print(f"\n══ {lg['name']} — skipped: ignore:true in leagues/_index.json")
            continue
        # weekly analysis is meaningless before a league has drafted: the "FA
        # pool" is every undrafted player and the roster is last year's carryover
        if (lg.get("status") or "") in ("pre_draft", "drafting", "paused"):
            print(f"\n══ {lg['name']} ({lg.get('status')}) — skipped: not in season "
                  "(use dashboard/board for draft views)")
            continue
        # Best ball has no lineup to set, no waivers and no trades. Every
        # section of this brief would produce confident advice about
        # decisions the format does not let you make. LG07 was live
        # and unregistered until 9/2, so this ran against nothing; it will
        # run against a real league the next time weekly fires.
        if (lg.get("settings") or {}).get("best_ball"):
            print(f"\n══ {lg['name']} — skipped: best ball. No lineup to set, "
                  "no waivers, no trades. The draft was the whole game.")
            continue
        L = league_brief(lg, season, week, tbl, out)
        if waivers_only or lineup_only:
            print(f"\n══ {L['league']} ({L['status']})")
            if lineup_only:
                print_lineup(L)
            if waivers_only:
                print_waivers(L)
        else:
            print_brief(L)
        recorded += ledger.record_brief(L, season, week)
    if ledger.ENABLED[0]:
        print(f"\nledger: {recorded} new recommendation(s) recorded for week {week}"
              " — `python br.py ledger score` next Tuesday grades them")
    if "--json" in args:
        path = args[args.index("--json") + 1]
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
