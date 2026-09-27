"""lineup_value.py — what a player is worth to THIS roster, not to a rank.

The question every other view in this toolkit answers is "how much better
is he than replacement at his position." That is the right question for a
startup draft and the wrong one for a keeper draft, where you already own
seven players and the draft is about upgrading a lineup you have.

The question this file answers is: if I add him, how many more points
does my STARTING LINEUP score this season?

    value = E[lineup points | roster + him] - E[lineup points | roster]

Three cases fall out of that one definition instead of needing three
rules:

  empty slot        nothing to displace, so he is worth ~his whole
                    projection
  weak incumbent    he is worth his projection MINUS the incumbent's.
                    A new WR is not worth his surplus over WR36; he is
                    worth his surplus over Jayden Higgins, because
                    Higgins is who leaves the lineup
  strong incumbent  he is worth his surplus over the WEAKEST starter he
                    could displace across every slot he is eligible for,
                    which for a good roster is small

and a fourth the others cannot express at all:

  bench depth       a player who never cracks the lineup still has value,
                    because starters miss games. He is worth what he adds
                    in the weeks the man above him is out.

That last one is why this is a simulation and not arithmetic. Each week
every player is available with his own probability, the best legal lineup
is filled from whoever is up, and the season is the sum. Run it a few
hundred times and the average is the answer.

WHERE THE AVAILABILITY ODDS COME FROM. Not invented. draft_helper's
availability_ratios() is Rotowire's own per-player haircut, already
verified against the app (Lamb weekly-sum ~296 vs season 270.5). A ratio
of 0.88 means the feed expects him to miss about two games. That is the
only injury input, and it is the same number season_projection_totals
already uses -- so this file adds no new assumption, it just stops
throwing the information away by collapsing it into one season total.

WHAT THIS IS NOT. It is a ONE-SEASON model. It says nothing about age,
dynasty horizon or 2027 value, so it does not replace dynasty_value.py --
it answers a different question and the two should be read together. In a
full-dynasty league weight dynasty_value; in a 2-keeper Hybrid, weight
this.

Usage (his machine, networked):
  python lineup_value.py <league fragment> [--pos WR] [--top 40]
                         [--sims 300] [--all]
  python lineup_value.py "LG03-LG05" --slot 8      # per-pick draft plan
  python lineup_value.py --selftest        # offline, no network

Restart discipline: none. No server, no cache of its own.
"""

import json
from battle_rhythm import paths as _paths
import pathlib
import sys
from collections import defaultdict

try:
    import numpy as np
except ImportError:                                    # pragma: no cover
    np = None

WEEKS = 17
DEFAULT_SIMS = 300


# ------------------------------------------------------------------ slots

def lineup_shape(roster_positions):
    """(dedicated {pos: n}, flex [(slot, eligible_positions)]).

    Reuses dynasty_value's vocabulary so SUPER_FLEX, WRRB_FLEX and the
    rest stay defined in exactly one place.
    """
    from battle_rhythm.dynasty_value import slot_plan
    ded, flex, _bench = slot_plan(roster_positions)
    return ded, flex


# ------------------------------------------------------------- simulation

def _order(players, ded, flex):
    """Precompute the index bookkeeping the vectorised fill needs.

    players: list of dicts with 'pos' and 'ppg'.
    Returns (pos_index, flex_index, flex_slots) where pos_index maps a
    position to the player indices at it sorted best-first, and
    flex_index is every flex-eligible player index sorted best-first
    across positions.
    """
    by_pos = defaultdict(list)
    for i, p in enumerate(players):
        by_pos[p["pos"]].append(i)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda i: -players[i]["ppg"])

    # ONE INDEX PER FLEX SLOT, not one pooled list. FLEX takes RB/WR/TE;
    # SUPER_FLEX also takes QB. Pooling them let a quarterback start in
    # the plain FLEX — this roster was starting THREE QBs in a league
    # that allows two, which inflated every quarterback on the board by
    # roughly a full starter's points.
    #
    # Most-restrictive slot first. That is optimal while eligibility sets
    # are nested (FLEX subset of SUPER_FLEX), which is true of every
    # league here. It is NOT optimal for crossing sets like WRRB_FLEX
    # alongside REC_FLEX; none of his leagues has that pair, and if one
    # ever does this needs a real assignment solver.
    slots = []
    for slot, fills in sorted(flex, key=lambda sf: len(sf[1])):
        idx = [i for i, p in enumerate(players) if p["pos"] in fills]
        idx.sort(key=lambda i: -players[i]["ppg"])
        slots.append((slot, idx))
    return dict(by_pos), slots


def expected_points(players, ded, flex, avail):
    """E[season starting-lineup points] over the trials in `avail`.

    avail: bool array (trials, n_players) — is this player up this week.
    Returns (mean points per trial, starter_share array).

    Dedicated slots first, then each flex slot in turn against its OWN
    eligibility list. Every slot scores a player's points identically,
    so taking the top d_pos available at each dedicated slot and then
    the best remaining eligible player per flex maximises the total.
    (That stops being true the moment a league scores one slot
    differently from another.)
    """
    n = len(players)
    if n == 0 or avail.shape[1] != n:
        return 0.0, np.zeros(n)
    ppg = np.array([p["ppg"] for p in players], dtype=float)
    by_pos, flex_slots = _order(players, ded, flex)

    started = np.zeros_like(avail, dtype=bool)
    for pos, need in ded.items():
        idx = by_pos.get(pos)
        if not idx or need <= 0:
            continue
        sub = avail[:, idx]                       # trials x players_at_pos
        rank = np.cumsum(sub, axis=1)             # 1-based among available
        started[:, idx] = sub & (rank <= need)

    for _slot, idx in flex_slots:
        if not idx:
            continue
        sub = avail[:, idx] & ~started[:, idx]
        rank = np.cumsum(sub, axis=1)
        started[:, idx] |= sub & (rank == 1)      # exactly one per slot

    per_week = started @ ppg
    return float(per_week.mean()) * WEEKS, started.mean(axis=0)


def draws(avails, trials, seed):
    """Independent weekly availability draws, one column per player."""
    rng = np.random.default_rng(seed)
    u = rng.random((trials, len(avails)))
    return u < np.asarray(avails, dtype=float)[None, :]


def replacement_level(cands, roster_positions, teams, gone_by_pos=None):
    """{pos: points of the last player the league still has to start}.

    Delegates to draft_helper.replacement_levels so the VORP board and
    this model cannot drift apart. The first version of this function
    reimplemented it and got remaining demand wrong — see that
    function's docstring for what that cost.
    """
    from battle_rhythm.dynasty_value import slot_plan
    from battle_rhythm.draft_helper import replacement_levels
    from battle_rhythm.roster_snapshot import FLEX_SHARE
    ded, flex, _b = slot_plan(roster_positions)
    demand_team = {}
    for pos, n in ded.items():
        demand_team[pos] = float(n)
    for slot, _f in flex:
        for pos, share in FLEX_SHARE.get(slot, {}).items():
            demand_team[pos] = demand_team.get(pos, 0.0) + share
    by_pos = {}
    for c in cands:
        by_pos.setdefault(c["pos"], []).append(float(c.get("proj") or 0.0))
    return replacement_levels(by_pos, demand_team, teams, gone_by_pos)


def floored_roster(roster, roster_positions, replacement, weeks=WEEKS):
    """The roster you end up with by doing NOTHING clever.

    WHY THIS EXISTS (8/13). Marginal value asks "what does this player
    add to the lineup I have?" — and answers it correctly. But it is the
    wrong question for a draft, because not taking him does not leave the
    slot as it is: you fill it with a later pick. Against a SUPER_FLEX
    held by Jalen Milroe at 1 projected point, the model priced Dak
    Prescott at +361 and ranked him first, while the VORP board had him
    eleventh at +42. Nearly all of that 361 was Milroe's emptiness, not
    Dak's edge over the quarterback available twenty picks later.

    So the baseline is not the roster as it stands. It is the roster with
    every startable slot held by at least a REPLACEMENT-level player —
    what the draft hands you for free. Value measured against that is
    the edge you actually buy, and it converges on VORP exactly where
    the slot is empty or held by a corpse, while keeping real
    displacement value where the incumbent is genuinely good.

    Both Hybrids run a second draft that backfills anything skipped at
    negligible cost, so the floor is not even a hypothetical there.
    """
    from battle_rhythm.dynasty_value import slot_plan
    ded, flex, _b = slot_plan(roster_positions)
    out = [dict(p) for p in roster]
    # 1. upgrade anyone starting below replacement to replacement
    for p in out:
        rep = replacement.get(p["pos"])
        if rep and p.get("ppg", 0) * weeks < rep:
            p["ppg"] = rep / float(weeks)
            p["_floored"] = True
    # 2. fill empty DEDICATED slots with a replacement-level phantom
    have = {}
    for p in out:
        have[p["pos"]] = have.get(p["pos"], 0) + 1
    for pos, n in ded.items():
        rep = replacement.get(pos)
        if not rep:
            continue
        for _ in range(max(0, n - have.get(pos, 0))):
            out.append({"pid": f"_repl_{pos}_{len(out)}",
                        "name": f"replacement {pos}", "pos": pos,
                        "ppg": rep / float(weeks), "avail": 1.0,
                        "_floored": True})
            have[pos] = have.get(pos, 0) + 1
    # 3. and every flex slot, from its most likely filler
    from battle_rhythm.roster_snapshot import FLEX_SHARE
    for slot, elig in flex:
        share = FLEX_SHARE.get(slot, {})
        pos = max(elig, key=lambda q: (share.get(q, 0.0),
                                       replacement.get(q, 0.0)))
        rep = replacement.get(pos)
        if not rep:
            continue
        out.append({"pid": f"_repl_{slot}_{len(out)}",
                    "name": f"replacement {pos}", "pos": pos,
                    "ppg": rep / float(weeks), "avail": 1.0,
                    "_floored": True})
    return out


def marginal_values(roster, candidates, roster_positions,
                    sims=DEFAULT_SIMS, seed=20260811):
    """[{...candidate, 'value', 'displaces'}] sorted best-first.

    roster/candidates: dicts with pid, name, pos, ppg, avail.

    COMMON RANDOM NUMBERS. Every candidate is scored against the SAME
    incumbent injury draws and gets the SAME reserved stream for his own
    availability. Without that, two players a point apart trade places
    on simulation noise and the ranking is unreadable.
    """
    if np is None:                                     # pragma: no cover
        raise RuntimeError("lineup_value needs numpy")
    # COPY SEMANTICS, STATED AT THE SOURCE. Every row returned here is a
    # NEW dict built from the candidate. Mutating a candidate after this
    # call cannot reach the caller's rows — that bug landed twice on
    # 8/11, once on the superflex ADP and once on the rookies' dynasty
    # ADP, and cost three debugging rounds the second time.
    ded, flex = lineup_shape(roster_positions)
    trials = int(sims) * WEEKS

    base_av = draws([p["avail"] for p in roster], trials, seed)
    base, base_share = expected_points(roster, ded, flex, base_av)

    # one reserved stream, reused for every candidate
    cand_u = np.random.default_rng(seed + 1).random((trials, 1))

    out = []
    for c in candidates:
        players = roster + [c]
        av = np.concatenate([base_av, cand_u < float(c["avail"])], axis=1)
        total, share = expected_points(players, ded, flex, av)
        drop = base_share - share[:len(roster)]        # who lost starts
        j = int(np.argmax(drop)) if len(roster) else -1
        out.append({**c, "value": round(total - base, 1),
                    "start_share": round(float(share[-1]), 3),
                    "displaces": (roster[j]["name"]
                                  if j >= 0 and drop[j] > 0.01 else None),
                    "displaces_by": (round(float(drop[j]), 3)
                                     if j >= 0 and drop[j] > 0.01 else 0.0)})
    out.sort(key=lambda r: -r["value"])
    return out, base


# -------------------------------------------------------------- live data

def build(fragment=None, sims=DEFAULT_SIMS, pos=None, top=40, include_all=False,
          drop=None):
    from battle_rhythm.sleeper_client import get, players as player_table, load_leagues
    from battle_rhythm.draft_helper import (uid, season_projection_totals,
                              availability_ratios, _adp, weekly_projections,
                              DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)
    from battle_rhythm.dynasty_value import resolve_league, taxi_split

    tbl = player_table()
    data = load_leagues(refresh=True)
    # resolve_league takes the fragment only and returns an ID, not a
    # league dict — exact-name-wins lives in there so both Hybrids stay
    # selectable despite one name being a substring of the other.
    lid = resolve_league(fragment)
    lg = next((l for l in data["leagues"]
               if str(l["league_id"]) == str(lid)), None)
    if lg is None:
        raise SystemExit(f"league {lid} not in the discovered list")
    full = get(f"league/{lid}") or {}
    rp = full.get("roster_positions") or lg.get("roster_positions") or []
    season = lg.get("season") or full.get("season")
    scoring = full.get("scoring_settings") or lg.get("scoring_settings") or {}

    totals = season_projection_totals(season, scoring)
    ratios = availability_ratios(season)

    # ADP under the RIGHT market. A superflex league prices quarterbacks
    # nothing like a 1QB league, and reading the wrong key produced a
    # bogus +151 positional bias in room_bias.py earlier. Keeper Hybrids
    # price off REDRAFT, not dynasty — they churn everyone but seven.
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    dyn = (lg.get("settings") or {}).get("type") == 2
    # AUTHORED DATA LIVES IN data/, VIA paths.data(). This read used
    # HERE / "keepers.json" — the repo root — which lost to data/ and
    # then vanished when the dead root copy was deleted on 8/13. Every
    # one of these is wrapped in a bare except, so the failure was a
    # silent default, not an error: `keeper` went False for both
    # Hybrids, which flips the ADP market from redraft to dynasty and
    # moves every survival flag on the card.
    try:
        keeper = bool(json.loads(_paths.data("keepers.json")
                                 .read_text(encoding="utf-8"))
                      .get(str(lid), {}).get("keeper"))
    except Exception as e:
        print(f"  WARNING: could not read keepers.json ({e}); treating "
              f"league {lid} as NON-keeper, which selects the DYNASTY "
              f"ADP market. Survival flags will be wrong if it is a "
              f"keeper league.")
        keeper = False
    if dyn and not keeper:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if sflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
        fb = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
              if sflex else DYNASTY_ADP_KEYS) if dyn else ()
    _ac, _exact = {}, {}

    def adp_of(pid):
        if pid not in _ac:
            try:
                v, ex = _adp(pid, season, keys, fb)
                _ac[pid], _exact[pid] = v, bool(ex)
            except Exception:
                _ac[pid], _exact[pid] = None, False
        return _ac[pid]

    me = uid()
    # EVERY roster, not just his. Before a keeper draft the rosters
    # endpoint holds what each manager KEPT, and those players never
    # reach the board. Scoring them as candidates recommended rivals'
    # keepers; leaving them in the ADP ladder made everyone else look
    # available later than they are.
    # THE ROSTERS ARE THE KEEPER SETS. The purge landed around July 1,
    # so a rostered player is a kept player and the draftable pool is
    # everyone else. Do NOT infer cuts from an over-limit roster: that
    # is the commissioner's call, not the board's (user, 8/13). The
    # census below reports overages and changes nothing.
    rules = keeper_rules(lid)
    capped = bool(rules.get("keeper"))
    _tx_slots = ((full.get("settings") or {}).get("taxi_slots")
                 or (lg.get("settings") or {}).get("taxi_slots") or 0)
    ceiling = 3 + 2 + int(_tx_slots)
    rosters_raw = get(f"league/{lid}/rosters") or []
    mine, taxi, kept = set(), set(), set()
    my_roster_id = None
    for r in rosters_raw:
        held = {x for x in (r.get("players") or []) if x}
        rtaxi = {x for x in (r.get("taxi") or []) if x}
        held |= rtaxi
        if str(r.get("owner_id")) == str(me):
            my_roster_id = r.get("roster_id")
            taxi |= rtaxi
            mine |= held
        else:
            kept |= held
    census = []
    if capped:
        try:
            names = {str(u.get("user_id")): (u.get("display_name") or "?")
                     for u in (get(f"league/{lid}/users") or [])}
        except Exception:
            names = {}
        census = roster_census(rosters_raw, tbl, me, names, ceiling)
    from battle_rhythm.draft_helper import resolve_draft, season_picks
    _d, _live = resolve_draft(full)
    picks = season_picks(full) or _live
    gone = {p["player_id"] for p in picks if p.get("player_id")}
    for pk in picks:
        if pk.get("player_id") and str(pk.get("picked_by")) == str(me):
            mine.add(pk["player_id"])

    _dc = {}

    def dadp_of(pid):
        """DYNASTY adp — the market's view of a player's FUTURE, which is
        the only thing that matters for a taxi stash. A rookie's 2026
        projection says he will not play; that is the point of parking
        him, not an argument against him."""
        if pid not in _dc:
            try:
                _dc[pid] = _adp(pid, season, DYNASTY_ADP_KEYS,
                                REDRAFT_ADP_KEYS)[0]
            except Exception:
                _dc[pid] = None
        return _dc[pid]

    def mk(pid):
        m = tbl.get(pid) or {}
        a = max(0.05, min(1.0, float(ratios.get(pid, 1.0))))
        tot = float(totals.get(pid, 0.0))
        return {"pid": pid, "name": m.get("full_name") or pid,
                "pos": m.get("position"), "team": m.get("team") or "FA",
                "bye": _bye(m.get("team")),
                "age": m.get("age"), "proj": tot, "adp": adp_of(pid),
                "rookie": (m.get("years_exp") in (0, "0")),
                "dadp": None,   # filled lazily for rookies only
                # undo the availability haircut: what he scores WHEN he
                # plays. The simulation re-applies the risk week by week,
                # so leaving it in would charge him for it twice.
                "ppg": (tot / a) / WEEKS, "avail": a}

    from battle_rhythm.sleeper_client import bye_of as _bye_of, load_byes
    _byes_tbl, _byes_note = load_byes(season)   # stashed on market below,
                                                # which does not exist yet

    def _bye(team):
        return _byes_tbl.get((team or "").upper())

    teams_n = lg.get("total_rosters") or lg.get("total_teams") or 12
    # WHICH POSITIONS THIS LEAGUE ACTUALLY STARTS, read from its own
    # roster_positions. Hardcoding {"QB","RB","WR","TE"} silently deleted
    # every kicker and every defender from both the roster and the
    # candidate pool. In the IDP league that meant a board with no DL,
    # LB or DB on it at all, and a sixteen-round plan that drafted SIX
    # quarterbacks for a one-QB league while leaving three starting
    # slots empty. The filter did exactly what it said; what it said was
    # written for four-position leagues and never revisited (8/13).
    # lineup_shape already parses roster_positions into dedicated slots
    # and flex eligibility, so ask it rather than re-deriving the
    # vocabulary a third time.
    _ded, _flex = lineup_shape(rp)
    live = set(_ded)
    for _slot, _elig in _flex:
        live |= set(_elig)
    live -= {"BN", "IR", "TAXI"}
    if not live:                       # unknown shape: fall back, loudly
        live = {"QB", "RB", "WR", "TE"}
        print("   (roster_positions unreadable — falling back to "
              "QB/RB/WR/TE only)")
    # TAXI IS A ONE-YEAR ROOKIE REDSHIRT, and the year expires. A player
    # parked LAST season is on the active roster now and starts like
    # anyone else; only a current rookie is actually sitting. There is no
    # "activate him" decision to price — I invented one and priced it
    # twice before he corrected me. Redshirts are dropped from both the
    # lineup and the candidate pool because they cannot score in 2026.
    redshirt, expired, unknown = taxi_split(taxi, tbl)
    redshirt |= unknown
    # --drop: price the roster you INTEND to draft, not the one you hold.
    # HANDOFF has Milroe and Brashard Smith as post-draft cuts; without
    # this the plan is built against bodies you are about to release.
    # Every hit is named in the output — a silent roster change would be
    # worse than no flag.
    dropped_names = []
    if drop:
        from battle_rhythm.draft_helper import player_hits
        _mine = set(mine)
        for q in ([drop] if isinstance(drop, str) else list(drop)):
            for _q in str(q).split(","):
                _q = _q.strip()
                if not _q:
                    continue
                hits, _hint = player_hits(tbl, _q)
                hit = [h for h in hits if h[0] in _mine]
                if not hit:
                    print(f"   --drop {_q!r}: nobody on your roster matches. "
                          f"Ignored.")
                    continue
                for pid, m in hit:
                    _mine.discard(pid)
                    dropped_names.append(m.get("full_name") or pid)
        # STAYS A SET. line 667 does `kept | mine | gone`; a list there
        # is a TypeError, and no selftest would catch it — build() needs
        # the live API, so all 99 of them and all 33 in test_all avoid it.
        mine = _mine
    roster = [mk(p) for p in mine
              if p not in redshirt
              and (tbl.get(p) or {}).get("position") in live]
    roster = [p for p in roster if p["proj"] > 0]

    # Build the FULL pool first — rivals' keepers included. They must be
    # priced on the same board as everyone else, because they are what
    # shifts everyone else's pick number earlier. Splitting them out
    # before the market is applied would have left them on the 1QB scale
    # and made the depletion arithmetic compare two different rulers,
    # which is the mistake this file already made once today.
    pool = []
    for pid, tot in totals.items():
        if pid in mine:
            continue
        m = tbl.get(pid) or {}
        if m.get("position") not in live:
            continue
        # A TAXI-PROFILE ROOKIE PROJECTS ~NOTHING. That is the whole
        # point of parking him, and it is why filtering the pool by
        # projection erased every one of them: the shortlist is the top
        # ~240 by 2026 points, and a redshirt is nowhere near it. The
        # 8/11 plan reported "no reachable rookie left" at both taxi
        # picks while the entire rookie class sat outside the cut.
        rook = m.get("years_exp") in (0, "0")
        if tot <= 0 and not rook:
            continue
        if not include_all and pid in gone:
            continue
        pool.append(mk(pid))
    pool.sort(key=lambda c: -c["proj"])
    keep_rows = [c for c in pool if c["pid"] in kept]
    avail = [c for c in pool if c["pid"] not in kept
             and (not pos or c["pos"] == pos.upper())]
    head = avail[:max(top * 6, 120)]       # sim only plausible names
    seen = {c["pid"] for c in head}
    # ...but never let a rookie fall off the bottom: he is not competing
    # on 2026 points, he is competing for a taxi seat.
    rookies_out = [c for c in avail if c["rookie"] and c["pid"] not in seen]
    cands = head + rookies_out
    cands += keep_rows                     # priced together, split after


    # ADP MUST BE SETTLED BEFORE THE SIMULATION RUNS. marginal_values
    # returns {**c, ...} — a COPY of each candidate — so rewriting
    # cands[i]['adp'] afterwards changed nothing the plan or the table
    # ever read. That is why the 8/11 board announced it had replaced
    # the market with a superflex one and then printed Josh Allen at
    # adp 29 anyway, and planned every pick off the 1QB numbers.

    # THE 'exact' FLAG DOES NOT MEAN WHAT I USED IT FOR. _adp marks a
    # value inexact only when it falls through to the FALLBACK tuple —
    # but `keys` is ("adp_2qb", "adp_dd_ppr", "adp_ppr", ...), so when
    # adp_2qb is missing _pick simply returns the next key, a 1QB PPR
    # number, and reports exact=True. My "no warning fired, therefore
    # these are superflex prices" was proof of nothing. Ask the feed
    # directly instead: is the adp_2qb field actually present.
    #
    # It matters because a 1QB ADP prices quarterbacks tens of picks too
    # LATE. "Mahomes lasts to 128" in a room that starts two QBs is a
    # fiction that would cost the draft.
    wk1 = weekly_projections(season, 1) if sflex else {}
    def has_2qb(pid):
        v = (wk1.get(str(pid)) or {}).get("adp_2qb")
        return isinstance(v, (int, float)) and 0 < v < 999
    qbs = [c for c in cands if c["pos"] == "QB"]
    qb_bad = [c["name"] for c in qbs if sflex and not has_2qb(c["pid"])]
    for c in cands:
        c["adp_true"] = (not sflex) or has_2qb(c["pid"])
    market = {"sflex": sflex, "keys": keys[0], "qb_fallback": qb_bad,
              "n_qb": len(qbs), "derived": False}

    # NO 2QB MARKET -> BUILD ONE. A 1QB board in a superflex room is not
    # "approximately right": it says no quarterback goes in round 1 of a
    # league that starts twenty-four of them. superflex_adp derives a
    # board that keeps the skill market's ORDER (real signal) and
    # re-prices quarterbacks off QB24 instead of QB12.
    # Use the 2QB board whenever ANY quarterback lacks a real superflex
    # price — not only when all of them do. A board where eleven QBs are
    # priced by the 2QB market and twenty-two by the 1QB market is worse
    # than either, because the two are not the same ruler.
    if sflex and qb_bad:
        try:
            from battle_rhythm.superflex_adp import apply_market
            from battle_rhythm.superflex_adp import cache_path
            real = {}
            f = cache_path(season)
            if f.exists():
                real = json.loads(f.read_text(encoding="utf-8") or "{}")
            merged, n_real = apply_market(list(cands), teams_n, real)
            by_id = {c["pid"]: c for c in merged}
            for c in cands:                    # mutate the SAME objects
                m = by_id.get(c["pid"])
                if m is not None:
                    c["adp"] = m["sflex_adp"]
                    c["adp_true"] = (m["sflex_src"] == "sleeper_2qb")
            market["derived"] = True
            market["n_real"] = n_real
        except Exception as e:
            print(f"   (superflex ADP derivation unavailable: {e})")
    # KEEPER DEPLETION, on the settled market, before the simulation.
    kept_adps = [c.get("adp") for c in keep_rows]
    cands = [c for c in cands if c["pid"] not in kept]   # split them back out
    if kept_adps:
        deplete_adp(cands, kept_adps)
    market["byes_note"] = _byes_note
    market["kept"] = len(keep_rows)
    market["kept_priced"] = sum(1 for a in kept_adps if a is not None)
    market["census"] = census
    market["ceiling"] = ceiling

    # EVERYTHING WRITTEN ONTO A CANDIDATE MUST BE WRITTEN BEFORE
    # marginal_values RUNS. It returns {**c, ...} — copies — so a
    # field set afterwards never reaches the plan. I documented that
    # trap when the superflex ADP hit it, then set 'dadp' after the
    # simulation anyway and spent three rounds hunting the wrong
    # filters while every rookie carried dadp=None into taxi_pick.
    # TAXI SEATS ARE A DRAFT-DAY ALLOCATION. A seat left empty cannot be
    # filled mid-season, and a 2026 rookie parked there carries into 2027
    # free WITHOUT consuming a keeper or drafted-rookie slot. That makes
    # the last picks a different job from the rest of the draft.
    from battle_rhythm.dynasty_value import taxi_split
    red, _exp, unk = taxi_split(taxi, tbl)
    taxi_slots = ((full.get("settings") or {}).get("taxi_slots")
                  or (lg.get("settings") or {}).get("taxi_slots") or 0)
    open_taxi = max(0, int(taxi_slots) - len(red | unk))
    for c in cands:
        if c["rookie"]:
            c["dadp"] = dadp_of(c["pid"])
    market["open_taxi"] = open_taxi
    market["rookies"] = sum(1 for c in cands if c["rookie"])
    market["rookies_priced"] = sum(1 for c in cands
                                   if c["rookie"] and c["dadp"] is not None)

    # which of HIS players are drafted-rookie eligible — dropping one
    # destroys that status permanently, so it belongs on screen
    try:
        from battle_rhythm.keeper import dr_eligible
        dr = dr_eligible(lid, tbl, me, int(season))
    except Exception:
        dr = set()
    market["dr"] = sorted((tbl.get(p) or {}).get("full_name") or p
                          for p in (dr & set(mine)))


    # VALUE IS MEASURED AGAINST THE FLOOR, NOT AGAINST THE ROSTER.
    # See floored_roster: not taking a player does not leave his slot as
    # it is, you fill it with a later pick. Without this the model put
    # Dak Prescott at +361 (all of it Milroe's 1 point) where the VORP
    # board had him eleventh (8/13).
    teams_n = lg.get("total_rosters") or 12
    # REMAINING demand, not total. `cands` is already the post-keeper
    # pool, so the kept players must be subtracted from demand too or
    # they are counted twice — which drove QB replacement to ~1 point in
    # the no-emoji Hybrid and left the Milroe corpse standing (8/13).
    # EVERYONE ALREADY OFF THE BOARD, mine included. Counting only
    # rivals' keepers left my own seven starters in the demand pool, so
    # remaining demand ran high, n ran deep, and replacement came back
    # BELOW what the VORP board computed on the same rosters. The board
    # has always used picks + every roster; match it exactly or the two
    # models cannot be compared (8/13).
    _gone_by_pos = {}
    for _pid in (kept | mine | gone):
        _pos = (tbl.get(_pid) or {}).get("position")
        if _pos:
            _gone_by_pos[_pos] = _gone_by_pos.get(_pos, 0) + 1
    market["replacement"] = replacement_level(cands, rp, teams_n, _gone_by_pos)
    floor = floored_roster(roster, rp, market["replacement"])
    market["floored"] = sum(1 for p in floor if p.get("_floored"))
    rows, base = marginal_values(floor, cands, rp, sims=sims)
    draft = get(f"draft/{did}") if did else None
    _ds = (draft or {}).get("settings") or {}
    rounds = _ds.get("rounds") or 0
    market["reversal_round"] = int(_ds.get("reversal_round") or 0)
    # THE PICK LIST IS DATA, NOT ARITHMETIC. Derive the slot from the
    # published draft order and apply traded picks, rather than trusting
    # a --slot the user typed and a snake the league may not run. Both
    # assumptions were wrong on 8/13 in the same league.
    market["owned_picks"], market["pick_meta"] = [], {}
    if draft and my_roster_id is not None:
        try:
            from battle_rhythm.sleeper_client import my_draft_picks
            pk, meta = my_draft_picks(draft, my_roster_id)
            market["owned_picks"], market["pick_meta"] = pk, meta
        except Exception as e:
            print(f"   (traded-pick resolution unavailable: {e})")
    teams = lg.get("total_rosters") or lg.get("total_teams") or 12
    market["dropped"] = dropped_names
    return (lg, rp, roster, rows, base, taxi, tbl, rounds,
            teams, top, market)


def deplete_adp(rows, kept_adps):
    """Shift every ADP earlier by the kept players ranked ahead of it.

    ADP is a market price from drafts where everyone was available. A
    keeper league removes ~5 players per team before a pick is made, so
    a player the market calls pick 60 is really pick 60 minus however
    many kept players sit above him. In a 12-team Hybrid that is dozens
    of picks — the difference between "he lasts to my turn" and "he was
    gone two rounds ago."

    This is the same mistake keeper.py made on 8/11, when it said Derrick
    Henry was reclaimable at pick 65 with roughly thirty kept players
    ranked ahead of him.

    kept_adps: sorted ADPs of players who will never reach the draft.
    Sets 'adp_raw' alongside the adjusted 'adp'.
    """
    import bisect
    ladder = sorted(a for a in kept_adps if a is not None)
    for r in rows:
        a = r.get("adp")
        if a is None:
            continue
        r["adp_raw"] = a
        r["adp"] = max(1.0, a - bisect.bisect_right(ladder, a))
    return rows


def taxi_pick(cands, taken, pick, sh, startable_bar):
    """Best 2026 rookie to PARK, from those still reachable.

    A taxi seat wants the opposite of what the rest of the draft wants.
    Ranking by 2026 points puts a backup quarterback worth eight points
    ahead of a first-round rookie who will not play this year and then
    carries into next season free — the 8/11 plan did exactly that, and
    spent picks 104 and 113 on Geno Smith and Chig Okonkwo.

    So: rookies only, ranked by DYNASTY adp (the market's view of their
    future), and a rookie good enough to START in 2026 is deliberately
    excluded — he belongs on the active roster, where a seat is not the
    constraint.
    """
    cands_ok = []
    for c in cands:
        if c["pid"] in taken or not c.get("rookie"):
            continue
        # A REDSHIRT HAS NO REDRAFT PRICE, AND THAT IS THE SIGNAL.
        # Requiring adp >= pick threw out every rookie whose ADP is None
        # — which is precisely the population a taxi seat is for. If the
        # redraft market does not rank him, nobody in this room is
        # spending a pick on his 2026 production, so he lasts. Only an
        # explicit ADP earlier than the pick means he is gone.
        if c.get("adp") is not None and c["adp"] - sh < pick:
            continue
        # A BAR OF ZERO IS NOT A BAR. Guarding here as well as in
        # startable_bar because this filter fails CLOSED — a degenerate
        # bar silently empties the pool instead of raising.
        if startable_bar > 0 and c["proj"] >= startable_bar:
            continue
        cands_ok.append(c)
    # RANK BY DYNASTY ADP, BUT NEVER REQUIRE IT. Dropping the priceless
    # rookies is the same mistake as the redraft filter above, one layer
    # down: of 300 rookies only 117 carry a dynasty price, and the other
    # 183 ARE the redshirt population — a player nobody drafts is a
    # player no market ranks. Both Hybrids reported "no rookie qualifies"
    # at all four taxi picks on 8/13 because of this line.
    #
    # Priced rookies still win, because a price is real information. Only
    # when none is priced do the unpriced ones compete, ranked youngest
    # first and then by name so the answer is stable run to run.
    priced = [c for c in cands_ok if c.get("dadp") is not None]
    if priced:
        return min(priced, key=lambda c: c["dadp"])
    if not cands_ok:
        return None
    return min(cands_ok, key=lambda c: (c.get("age") or 99,
                                        c.get("name") or ""))


def taxi_funnel(cands, taken, pick, sh, startable_bar):
    """Why taxi_pick found nobody. Counts, not a guess.

    Added 8/13 after the message "no rookie qualifies" survived a fix
    that should have removed it. Rather than reason about which filter
    was eating the pool, report every stage — the answer is one live run
    away instead of one more theory.
    """
    n = {"rows": len(cands), "rookies": 0, "not_taken": 0,
         "reachable": 0, "under_bar": 0, "priced": 0}
    for c in cands:
        if not c.get("rookie"):
            continue
        n["rookies"] += 1
        if c["pid"] in taken:
            continue
        n["not_taken"] += 1
        if c.get("adp") is not None and c["adp"] - sh < pick:
            continue
        n["reachable"] += 1
        if startable_bar > 0 and c["proj"] >= startable_bar:
            continue
        n["under_bar"] += 1
        if c.get("dadp") is not None:
            n["priced"] += 1
    return n


def startable_bar(cands, pos_counts, teams):
    """Roughly the worst projection that starts anywhere in this league.

    A POSITION THINNER THAN ITS OWN DEMAND CANNOT SET THE BAR. The old
    version clamped with min(n, len(r)) and took the WORST player at a
    short position, which in a superflex league where most quarterbacks
    are kept meant reading the 20th of 20 QBs — a zero-projection rookie
    — and then min() propagated that 0.0 to every position.

    The consequence was silent and total: taxi_pick excludes anyone with
    proj >= bar, and every player has proj >= 0, so both Hybrids reported
    "no rookie qualifies" at all four taxi seats. It survived two rounds
    of fixes aimed at the wrong filter, and was only found by printing a
    funnel of survivors per stage (8/13).

    A short position means demand outruns supply — the true replacement
    level sits BELOW the worst man available, so that position cannot
    lower a bar it has no player to define. Skip it. Zero is likewise
    never a bar, it is the absence of one.
    """
    vals = []
    for pos, per in pos_counts.items():
        r = sorted((c["proj"] for c in cands if c["pos"] == pos),
                   reverse=True)
        n = max(1, int(round(teams * per)))
        if len(r) >= n and r[n - 1] > 0:
            vals.append(r[n - 1])
    return min(vals) if vals else 0.0


def room_shave(league_id, override=None, path=None):
    """Picks to subtract from ADP when asking "will he last to my turn."

    This is a property of the ROOM, not of the market, so it is per-league
    data in keepers.json and never a global default. I shipped it as a
    hardcoded 10 for every league on 8/11 by generalising a LG01
    observation — that room buys veterans about ten picks early
    (CLAUDE.md lesson 6). His correction: the Hybrid rooms draft close to
    market, "these guys know what they're doing, for the most part."

    Once a draft has picks on the board room_bias.py MEASURES this; the
    stored number is only the pre-draft prior. An explicit --shave wins
    over both.
    """
    if override is not None:
        return int(override)
    try:
        cfg = json.loads((path or _paths.data("keepers.json"))
                         .read_text(encoding="utf-8"))
        v = (cfg.get(str(league_id)) or {}).get("room_shave")
        return int(v) if v is not None else 0
    except Exception:
        return 0


def snake_picks(slot, rounds, teams, reversal_round=0):
    """Overall pick numbers from `slot`, honouring a round reversal.

    reversal_round=0 is a plain snake: odd rounds run forward, even
    rounds run back. Sleeper also supports a REVERSAL, almost always at
    round 3 ("3RR"), where round R repeats round R-1's direction instead
    of flipping, and the alternation continues from there. It exists to
    compensate late-slot pickers, and from round R onward it inverts
    every pick number a plain snake would predict.

    WHY THIS EXISTS (user, 8/13). He gave me his real card as
    1.8 2.5 3.5 4.8 5.5 6.8 7.5 8.8 9.5 10.8 and said it should be
    telling me something. A plain snake from slot 8 gives 3.8 and 4.5;
    his league gives 3.5 and 4.8. `settings.reversal_round` is 3 in
    LG03-LG05 and 0 in the emoji league — the two rooms do not share a
    format, and the toolkit assumed both were plain snakes. Every pick
    number from round 3 down was wrong in one of his two leagues, and
    silently: the numbers look plausible, they are just not his.

    Read it from the draft settings. Never infer it from the slot.
    """
    # Delegates to sleeper_client so the toolkit has ONE implementation
    # of pick geometry. Three copies is how all three ended up wrong.
    from battle_rhythm.sleeper_client import slot_picks
    return slot_picks(slot, rounds, teams, reversal_round)


def keeper_rules(league_id, path=None):
    """This league's entry in keepers.json, or {} if it has none."""
    try:
        cfg = json.loads((path or _paths.data("keepers.json"))
                         .read_text(encoding="utf-8"))
        return cfg.get(str(league_id)) or {}
    except Exception:
        return {}


def roster_census(rosters, tbl, me, names=None, ceiling=7):
    """Per-team roster count against the ceiling. REPORTS, never culls.

    Asked for directly (user, 8/13): "there should be a max of 7 players
    per team ... I want to make sure we're tracking it appropriately."

    WHAT THIS DELIBERATELY DOES NOT DO, and why (his correction, same
    day): "we will not be culling anyone's roster if they're over.
    That's the commissioner's job."

    The purge already happened around July 1. These rosters ARE the
    keeper sets, so every rostered player is kept and the draftable pool
    is simply everyone else. An earlier version of this file inferred
    which players an over-limit team would drop — best-by-projection
    under the slot rules — and handed them back to the board as
    draftable. That was a guess stacked on a guess, and worse, it was
    the board quietly overruling a human decision that had not been made
    yet. A team over the limit is a commissioner problem and a line of
    output, not an input to anybody's draft plan.

    The 7 is also flatter than I first modelled it. Taxi players can be
    MOVED, so a team at seven with an empty taxi is perfectly legal —
    the internal split between keepers, drafted rookies and taxi is the
    manager's business and can shift. Only the total binds.
    """
    out, names = [], (names or {})
    for r in rosters or []:
        oid = str(r.get("owner_id"))
        held = {x for x in (r.get("players") or []) if x}
        rtaxi = {x for x in (r.get("taxi") or []) if x}
        held |= rtaxi
        if not held:
            continue
        out.append({"owner": oid, "name": names.get(oid, oid[:8]),
                    "mine": oid == str(me), "rostered": len(held),
                    "taxi": len(rtaxi),
                    "over": max(0, len(held) - int(ceiling))})
    out.sort(key=lambda x: (-x["over"], -x["rostered"]))
    return out


def taxi_line(n_active, taxi_ids, tbl, sims):
    """The roster header line. Splits the taxi field by redshirt status.

    THE BUG THIS EXISTS TO KILL. The header used to read
    "{len(roster)} active players simulated x {sims} seasons ·
    {len(taxi)} on taxi (cannot start, excluded)". Both numbers were
    computed correctly and the sentence was still false: build() keeps
    EXPIRED redshirts in `roster`, while Sleeper's taxi field still
    lists them. On a seven-man roster holding two expired redshirts it
    printed "7 active · 2 on taxi (cannot start, excluded)" — nine
    players, two of them counted twice and described as unable to start
    while they were in the starting lineup.

    That is HANDOFF bug #5 wearing a different hat. Not a wrong lineup
    this time, but a report that asserts the opposite of the code
    beneath it, which is worse in one specific way: the lineup was
    right, so nothing looked broken, and a future session reading the
    header would have re-derived the wrong roster from it.

    Unknown years_exp is reported as still sitting, never guessed
    active — the same convention taxi_split uses.
    """
    from battle_rhythm.dynasty_value import taxi_split
    red, expired, unknown = taxi_split(taxi_ids, tbl)
    red |= unknown
    s = f"{n_active} active players simulated x {sims} seasons"
    if expired:
        s += (f" (incl. {len(expired)} off EXPIRED redshirts — "
              f"on the active roster this season, and starting)")
    if red:
        s += f" · {len(red)} still redshirting on taxi (cannot start)"
    return s


def report(fragment=None, sims=DEFAULT_SIMS, pos=None, top=40,
           include_all=False, slot=None, shave=None, drop=None):
    (lg, rp, roster, rows, base, taxi, tbl, rounds, teams, top,
     market) = build(fragment, sims, pos, top, include_all, drop)
    ded, flex = lineup_shape(rp)
    print(f"\n== {lg.get('name')} — value to YOUR lineup")
    print(f"   E[season starting points] as rostered: {base:,.0f}")
    print("   Projections here are AVAILABILITY-ADJUSTED and will read "
          "about 7-10%\n   BELOW the number Sleeper shows. The app "
          "projects every player as if he\n   plays every game; ours "
          "applies the feed's own injury discount. Measured\n   8/13 "
          "across nine quarterbacks: mean error to the app is -0.7% "
          "before the\n   haircut and -9.4% after. Neither is wrong; "
          "they answer different questions.")
    print("   slots: " + " ".join(f"{p}x{n}" for p, n in ded.items())
          + " " + " ".join(s for s, _f in flex))
    print("   " + taxi_line(len(roster), taxi, tbl, sims))
    print(f"   ADP market: {market['keys']}"
          + (" (SUPERFLEX)" if market["sflex"] else " (1QB)"))
    if market["qb_fallback"]:
        n = len(market["qb_fallback"])
        print(f"   Sleeper's weekly feed carries no adp_2qb for any of "
              f"{market['n_qb']} quarterbacks\n   (a 1QB price in a room "
              f"that starts two is tens of picks too LATE).")
        if market.get("derived"):
            nr = market.get("n_real", 0)
            print(f"   -> using superflex_adp.py's board instead: {nr} "
                  f"REAL adp_2qb prices from the\n      per-player endpoint, "
                  f"the rest interpolated onto that same scale by\n"
                  f"      surplus and marked * / [interp].")
        else:
            print("   ** Run superflex_adp.py to build a 2QB board — this "
                  "one is 1QB.")
    if market.get("kept"):
        print(f"   {market['kept']} players are KEPT by rivals: excluded "
              f"from the board, and\n   every remaining ADP shifted "
              f"earlier by the keepers ranked above it.")
        print("   Rosters are taken as the keeper sets — the purge landed "
              "in July, so\n   everyone rostered is kept and the draftable "
              "pool is everyone else.")
    # NAME THIS ANYTHING BUT `rows`. `rows` is the candidate board,
    # unpacked from build() above and read by the draft plan 200 lines
    # below. Binding the census to it here crashed the plan with
    # KeyError 'pid' — the report printed perfectly, then died. A
    # display-only block silently redefining a caller's data is the
    # cheapest possible bug and it still cost a live run.
    if market.get("census"):
        ceil = market.get("ceiling", 7)
        cen = market["census"]
        over = [c for c in cen if c["over"]]
        print(f"\n   ROSTER CENSUS — ceiling {ceil} per team")
        print(f"   {'team':<18}{'rostered':>9}{'taxi':>6}{'over':>6}")
        for c in cen:
            tag = "  <- you" if c["mine"] else (
                "  OVER — commissioner's call" if c["over"] else "")
            print(f"   {c['name'][:18]:<18}{c['rostered']:>9}"
                  f"{c['taxi']:>6}{c['over'] or '':>6}{tag}")
        if over:
            print(f"   {len(over)} team(s) over the limit. NOT modelled — "
                  f"nobody's roster gets\n   culled here. If the "
                  f"commissioner forces cuts, those names hit the\n   pool "
                  f"late and this board will not have seen them coming.")
        else:
            print("   Every team is at or under the limit.")
        print("   Taxi players can be moved, so the split between keepers, "
              "drafted\n   rookies and taxi is the manager's business. "
              "Only the total binds.\n")
    if not roster:
        print("\n   *** YOUR ROSTER IS EMPTY, SO THIS BOARD IS NOT A "
              "RANKING YOU CAN DRAFT FROM. ***\n"
              "   Marginal value is measured against the lineup you "
              "already have. With\n   nothing to displace, every "
              "candidate 'fills an empty slot' and his value\n   is just "
              "his projection — so the board sorts by raw points and puts\n"
              "   twenty-five quarterbacks on top of a league that starts "
              "one.\n"
              "   Use the VORP board instead, which prices against "
              "replacement:\n"
              f"       python draft_helper.py board "
              f"{lg.get('league_id')}          # all positions\n"
              f"       python draft_helper.py board "
              f"{lg.get('league_id')} --pos LB   # one position\n"
              "   Come back to this tool once you have players, or to "
              "compare a specific\n   addition against a roster that "
              "exists.\n")
    print("   value = points ADDED OVER REPLACEMENT, not over your "
          "current lineup")
    if market.get("dropped"):
        print(f"   --drop: priced WITHOUT {', '.join(market['dropped'])}. "
              f"This is a hypothetical\n   roster; the league still has "
              f"them on your team.")
    if market.get("floored"):
        print(f"   {market['floored']} starting slot(s) were empty or held "
              f"BELOW replacement and have\n   been floored to replacement "
              f"level for this measurement. Not taking a\n   player does not "
              f"leave his slot as it is — you fill it with a later pick,\n"
              f"   and in this league with an entire second draft. Measured "
              f"the old way\n   Dak Prescott scored +361, almost all of it "
              f"Jalen Milroe's 1 point, and\n   ranked first while the VORP "
              f"board had him eleventh (8/13).")
    print()

    meta = market.get("pick_meta") or {}
    real_slot = meta.get("slot")
    if meta and not meta.get("published"):
        print("\n   *** THE DRAFT ORDER IS NOT PUBLISHED. Sleeper ships a "
              "placeholder\n   slot_to_roster_id before the commissioner "
              "randomises, so any slot\n   read from it is fiction. Pick "
              "numbers below come from --slot and are\n   a guess until "
              "the order is set. ***")
    if real_slot and slot and int(real_slot) != int(slot):
        print(f"\n   *** SLOT MISMATCH. You passed --slot {slot}; the "
              f"published draft order\n   puts you at slot {real_slot}. "
              f"Using {real_slot}. ***")
    slot = real_slot or slot
    if slot:
        sh = room_shave(lg.get("league_id"), shave)
        rev = int(market.get("reversal_round") or 0)
        picks = market.get("owned_picks") or snake_picks(slot, rounds,
                                                         teams, rev)
        gained, lost = meta.get("gained") or [], meta.get("lost") or []
        why = (f"shaved by {sh} — this room buys ahead of market"
               if sh else "no shave — this room drafts close to market")
        fmt = (f"snake, REVERSAL at round {rev}" if rev else "plain snake")
        print(f"   DRAFT PLAN — slot {slot} of {teams}, {rounds} rounds "
              f"({fmt}). Your {len(picks)} picks:"
              f" {', '.join(str(x) for x in picks)}")
        if rev:
            print(f"   Round {rev} repeats round {rev-1}'s order instead of "
                  f"flipping, so every pick\n   from there down is NOT what "
                  f"plain-snake arithmetic predicts.")
        if gained:
            print(f"   TRADED IN: {', '.join(str(x) for x in gained)} — "
                  f"already in the list above.")
        if lost:
            print(f"   TRADED AWAY: {', '.join(str(x) for x in lost)} — "
                  f"removed from the list above.")
        if not market.get("owned_picks"):
            print("   (no draft object — pick list is arithmetic from "
                  "--slot, trades NOT applied)")
        for a, b in zip(picks, picks[1:]):
            if b - a == 1:
                print(f"   BACK TO BACK at {a} and {b}: you can gamble on "
                      f"survival at {a},\n   because {b} catches you if "
                      f"you are wrong.")
        if market.get("byes_note"):
            print(f"   {market['byes_note']}")
        print(f"   Reachable = ADP past the pick, {why}\n"
              f"   (per-league, keepers.json room_shave). ADP is a "
              f"distribution, not a\n   deadline — treat these as odds, "
              f"not promises.\n")

        # THE ROSTER MUST GROW AS THE PLAN WALKS. The first version only
        # struck the chosen player from the shortlist and re-read values
        # computed against the ORIGINAL roster, so every pick was scored
        # as though the SUPER_FLEX were still held by a 15-point
        # quarterback. It recommended ten quarterbacks in a row and the
        # "each row assumes you took the row above" caveat I printed was
        # simply false. Re-simulate after every pick.
        cur = list(roster)
        # BYE SHAPE, tracked as the plan walks. The roster this plan
        # builds is what actually has to field nine starters in week 13,
        # and the season-total model has no idea that is a constraint.
        _plan_byes = [c.get("bye") for c in roster]
        pool = {r["pid"]: r for r in rows}
        plan_sims = max(60, int(sims) // 3)     # 10 re-sims, keep it quick
        # The LAST open_taxi picks do a different job: park rookies who
        # carry into next season free. Reserve them up front rather than
        # hoping something is left, because a seat cannot be filled once
        # the season starts.
        n_taxi = min(market.get("open_taxi", 0), max(0, len(picks) - 4))
        taxi_at = set(picks[len(picks) - n_taxi:]) if n_taxi else set()
        bar = startable_bar(rows, {"QB": 2.0, "RB": 2.8, "WR": 2.9,
                                   "TE": 1.3}, teams)
        if taxi_at:
            print(f"   {market.get('rookies', 0)} rookies on the board, "
                  f"{market.get('rookies_priced', 0)} with a dynasty price.")
            print(f"   {n_taxi} taxi seat(s) open -> picks "
                  f"{', '.join(str(x) for x in sorted(taxi_at))} are "
                  f"reserved for\n   2026 rookies who will NOT play this "
                  f"year, ranked by dynasty ADP.\n   They carry into next "
                  f"season free and cost no keeper slot.\n")
        taken_taxi = set()
        for n, pk in enumerate(picks):
            if pk in taxi_at:
                already = taken_taxi | {c["pid"] for c in cur}
                t = taxi_pick(rows, already, pk, sh, bar)
                if t:
                    price = (f"dynasty adp {t['dadp']:.0f}"
                             if t.get("dadp") is not None
                             else "UNPRICED — no dynasty market, which is "
                                  "the redshirt signal")
                    print(f"   pick {pk:>3}  ->  TAXI: {t['name']} "
                          f"({t['pos']}, rookie, {price}, "
                          f"2026 proj {t['proj']:.0f})")
                    taken_taxi.add(t["pid"])
                    pool.pop(t["pid"], None)
                else:
                    _f = taxi_funnel(rows, already, pk, sh, bar)
                    print(f"   pick {pk:>3}  ->  TAXI: none. FUNNEL "
                          f"rows={_f['rows']} rookies={_f['rookies']} "
                          f"not_taken={_f['not_taken']} "
                          f"reachable={_f['reachable']} "
                          f"under_bar(={bar:.0f})={_f['under_bar']} "
                          f"priced={_f['priced']}")
                    print(f"              legacy note: "
                          f"Of {market.get('rookies', 0)} rookies, "
                          f"{market.get('rookies_priced', 0)} have a "
                          f"dynasty price;\n              the rest are "
                          f"unrankable. Spend it on depth and stash off "
                          f"waivers.")
                continue
            nxt = picks[n + 1] if n + 1 < len(picks) else None
            here = [c for c in pool.values()
                    if c.get("adp") is not None and c["adp"] - sh >= pk]
            if not here:
                print(f"   pick {pk:>3}: nothing in the shortlist projects "
                      f"to last this long")
                continue
            here.sort(key=lambda c: -c["proj"])
            scored, _b = marginal_values(
                floored_roster(cur, rp, market["replacement"]),
                here[:60], rp, sims=plan_sims)

            def survives(c):
                return nxt is None or c["adp"] - sh >= nxt

            # TWO-PICK LOOKAHEAD. Taking the highest-value player on the
            # board wastes the pick when he would still be there next
            # turn. The 8/11 plan spent pick 8 on Josh Allen at ADP 29 —
            # a man who survives to 17 and probably to 29 — and got
            # Bowers at 17 anyway. Compare the two paths:
            #   take the expiring guy now  -> value(G) + value(best S)
            #   take the survivor now      -> value(S) + value(2nd S)
            # so reach for the expiring player exactly when he beats the
            # SECOND-best survivor. Values are pre-pick estimates: after
            # a quarterback lands, every other quarterback collapses, so
            # this understates how much the ordering matters.
            gone = [c for c in scored if not survives(c)]
            stay = [c for c in scored if survives(c)]
            lead, why = scored[0], ""
            if gone and len(stay) >= 2 and gone[0]["value"] >= stay[1]["value"]:
                if lead is not gone[0]:
                    why = (f"  [reach: {stay[0]['name']} keeps to "
                           f"{nxt}, {gone[0]['name']} does not]")
                lead = gone[0]

            def _tag(c):
                # NOT "[1QB]" — these are interpolated onto the superflex
                # scale, not left on the single-QB market. Mislabelling
                # them would make a correct number look like a known bug.
                mark = "" if c.get("adp_true", True) else " [interp]"
                return mark + ("" if survives(c)
                               else f"  <- GONE by {nxt}, take him now")
            print(f"   pick {pk:>3}  ->  {lead['name']} ({lead['pos']}, "
                  f"adp {lead['adp']:.0f}, +{lead['value']:.0f})"
                  f"{_tag(lead)}{why}")
            for alt in [c for c in scored if c is not lead][:2]:
                print(f"             or  {alt['name']} ({alt['pos']}, "
                      f"adp {alt['adp']:.0f}, +{alt['value']:.0f})"
                      f"{_tag(alt)}")
            cur.append(lead)
            _plan_byes.append(lead.get("bye"))
            pool.pop(lead["pid"], None)
        filled = [c["name"] for c in cur[len(roster):]]
        print(f"\n   Resulting roster adds: {', '.join(filled)}")
        market["_plan_byes"] = _plan_byes
        if taken_taxi:
            names = [r["name"] for r in rows if r["pid"] in taken_taxi]
            print(f"   Taxi stashes: {', '.join(names)} — they do not "
                  f"consume an active\n   spot, carry into next season "
                  f"free, and stay drafted-rookie eligible\n   as long as "
                  f"you never drop them.")
        if market.get("dr"):
            print(f"\n   Drafted-rookie eligible on your roster: "
                  f"{', '.join(market['dr'])}")
            print("   Dropping one of these destroys that status "
                  "PERMANENTLY — it is not\n   re-earnable, so a cut is a "
                  "keeper decision, not a roster decision.")
        print("   Every pick is re-simulated against the roster built by "
              "the picks\n   above it. It still assumes a static market — "
              "no other manager's\n   run on a position moves these "
              "ADPs.\n")

    print(f"   {'player':22} {'pos':4} {'proj':>6} {'adp':>6} "
          f"{'starts':>7} {'+pts':>7}  displaces")
    for r in rows[:top]:
        d = (f"{r['displaces']} ({r['displaces_by']:.0%} of his starts)"
             if r["displaces"] else "fills an empty slot")
        adp = (f"{r['adp']:.0f}" if r.get("adp") is not None else "—")
        if not r.get("adp_true", True):
            adp += "*"
        if r.get("adp_raw") and abs(r["adp_raw"] - r["adp"]) >= 1:
            adp = f"{r['adp']:.0f}<{r['adp_raw']:.0f}"
        print(f"   {r['name'][:22]:22} {r['pos'] or '?':4} {r['proj']:6.0f} "
              f"{adp:>6} {r['start_share']:6.0%} {r['value']:7.1f}  {d}")
    if market.get("_plan_byes"):
        from battle_rhythm.sleeper_client import bye_pressure
        starters = sum(ded.values()) + len(flex)
        pb = market["_plan_byes"]
        pressure = bye_pressure(pb, starters)
        short = {w: a for w, a in pressure.items() if a < starters}
        print(f"\n   BYE SHAPE of the roster this plan builds "
              f"({len(pb)} players, {starters} starting slots):")
        for wk, avail in pressure.items():
            n = len(pb) - avail
            flag = (f"  <== SHORT {starters - avail}, cannot fill the lineup"
                    if avail < starters else
                    "  <== no slack" if avail == starters else "")
            print(f"     week {wk:>2}: {n} out, {avail:>2} available{flag}")
        if short:
            print("   A short week is a forfeited slot. This model prices "
                  "SEASON totals\n   and cannot see it — swap a pick whose "
                  "bye is already crowded.")
        else:
            print("   No week leaves you short. Nothing to design around.")
    elif market.get("byes_note"):
        print(f"\n   {market['byes_note']}")

    print("\n   One-season model. It knows nothing about age or 2027 — "
          "read it\n   alongside dynasty_value.py, do not replace it.")
    print("   With empty starting slots, most candidates 'fill an empty "
          "slot' and\n   this collapses toward raw projection. It bites "
          "where you have an\n   incumbent to displace, not where you "
          "have a hole.\n")


# --------------------------------------------------------------- selftest

def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    if np is None:                                     # pragma: no cover
        print("XX  numpy missing")
        sys.exit(1)

    RP = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
    ded, flex = lineup_shape(RP)
    check("slots parsed", ded["WR"] == 3 and len(flex) == 2)

    def P(name, pos, ppg, avail=1.0):
        return {"pid": name, "name": name, "pos": pos, "ppg": ppg,
                "proj": ppg * WEEKS, "avail": avail}

    # a full, healthy roster: 1 QB, 2 RB, 3 WR, 1 TE + 2 for the flexes
    roster = [P("QB1", "QB", 20), P("RB1", "RB", 15), P("RB2", "RB", 12),
              P("WR1", "WR", 18), P("WR2", "WR", 14), P("WR3", "WR", 9),
              P("TE1", "TE", 10), P("RB3", "RB", 11), P("WR4", "WR", 8)]
    av = draws([1.0] * len(roster), 20, 1)
    base, share = expected_points(roster, ded, flex, av)
    # everyone healthy and exactly 9 slots for 9 players -> all start
    check(f"all nine start when nobody is hurt ({base:.0f} pts)",
          abs(base - sum(p["ppg"] for p in roster) * WEEKS) < 1e-6)
    check("...and each has a 100% start share", share.min() == 1.0)

    # DISPLACEMENT: a WR better than WR3 is worth the DIFFERENCE, not his
    # whole projection. This is the Higgins case.
    rows, _b = marginal_values(roster, [P("NewWR", "WR", 16)], RP, sims=60)
    got = rows[0]["value"]
    want = (16 - 8) * WEEKS      # he starts, WR4 (the flex) leaves
    check(f"a WR who displaces the weakest flex is worth the delta "
          f"({got:.0f} vs {want})", abs(got - want) < 1.0)
    check("...and the report names who left",
          rows[0]["displaces"] == "WR4")

    # EMPTY SLOT: same player on a roster with an open WR slot is worth
    # his whole projection, with no rule change.
    thin = [p for p in roster if p["name"] not in ("WR4", "WR3")]
    rows2, _ = marginal_values(thin, [P("NewWR", "WR", 16)], RP, sims=60)
    # ---- the replacement FLOOR: value is the edge you buy, not the
    # emptiness you inherit. A corpse in a starting slot used to make
    # any real player look like a franchise pick (Dak +361 over Milroe's
    # 1 point, eleventh on the VORP board).
    RPS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]
    pool = ([P(f"q{i}", "QB", 22.0 - i * 0.5) for i in range(30)]
            + [P(f"r{i}", "RB", 20.0 - i * 0.4) for i in range(40)]
            + [P(f"w{i}", "WR", 19.0 - i * 0.3) for i in range(60)]
            + [P(f"t{i}", "TE", 15.0 - i * 0.4) for i in range(20)])
    rep = replacement_level(pool, RPS, 12)
    check(f"replacement is the last startable, not the best available "
          f"(QB {rep['QB']:.0f})",
          0 < rep["QB"] < max(c["proj"] for c in pool if c["pos"] == "QB"))
    corpse = [P("Corpse", "QB", 0.06)]          # ~1 point on the season
    floor = floored_roster(corpse, RPS, rep)
    check("a corpse in a starting slot is floored up to replacement",
          any(x.get("_floored") for x in floor)
          and floor[0]["ppg"] > corpse[0]["ppg"])
    check("...and every empty starting slot gets a replacement body",
          len(floor) >= 9)
    star = P("Star", "QB", 24.0)
    raw, _ = marginal_values(corpse, [star], RPS, sims=60)
    fl, _ = marginal_values(floor, [star], RPS, sims=60)
    # The floor should remove exactly one replacement player's worth of
    # credit — that is the whole claim, so assert the quantity, not a
    # vague "much smaller". (The first version asserted < half and
    # failed at 212 vs 408 with replacement 196: arithmetically perfect,
    # and the test was the thing that was wrong.)
    check(f"the floor removes one replacement QB's worth of credit "
          f"({raw[0]['value']:.0f} - {fl[0]['value']:.0f} "
          f"= {raw[0]['value'] - fl[0]['value']:.0f}, "
          f"replacement {rep['QB']:.0f})",
          abs((raw[0]["value"] - fl[0]["value"]) - rep["QB"])
          < 0.15 * rep["QB"])
    check("...and is still positive — he is a real upgrade, just not a "
          "franchise one", fl[0]["value"] > 0)
    # a GOOD incumbent is not floored, so genuine displacement survives
    good = [P("Good", "QB", 21.0)]
    gfloor = floored_roster(good, RPS, rep)
    check("a good incumbent is left alone by the floor",
          gfloor[0]["ppg"] == good[0]["ppg"])

    check(f"the SAME player into an empty slot is worth his whole "
          f"projection ({rows2[0]['value']:.0f})",
          abs(rows2[0]["value"] - 16 * WEEKS) < 1.0)
    check("...and displaces nobody", rows2[0]["displaces"] is None)

    # BENCH DEPTH: a player who never starts is worth ~0 with a healthy
    # roster, and strictly more once the man above him misses games.
    rows3, _ = marginal_values(roster, [P("Backup", "WR", 6)], RP, sims=200)
    hurt = [dict(p, avail=0.6) if p["name"] == "WR1" else p for p in roster]
    rows4, _ = marginal_values(hurt, [P("Backup", "WR", 6)], RP, sims=200)
    check(f"a sub-lineup backup is worth ~nothing behind healthy starters "
          f"({rows3[0]['value']:.0f})", rows3[0]["value"] < 1.0)
    check(f"...and MORE when the starter ahead misses games "
          f"({rows4[0]['value']:.0f})", rows4[0]["value"] > rows3[0]["value"])

    # SUPERFLEX. The premium is not that a QB outranks an equal skill
    # player — with identical ppg and both flex-eligible they are worth
    # exactly the same, and asserting otherwise would be testing a
    # superstition. The real claim is that the SAME quarterback is worth
    # far more in superflex than in a 1QB league, where he cannot reach
    # the field at all behind a healthy starter.
    RP1 = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX"]
    sf, _ = marginal_values(roster, [P("QB2", "QB", 13)], RP, sims=200)
    oq, _ = marginal_values(roster, [P("QB2", "QB", 13)], RP1, sims=200)
    check(f"the same QB2 is worth more in superflex than 1QB "
          f"({sf[0]['value']:.0f} vs {oq[0]['value']:.0f})",
          sf[0]["value"] > oq[0]["value"] + 20)
    check(f"...and in 1QB he barely plays "
          f"({oq[0]['start_share']:.0%} of weeks)",
          oq[0]["start_share"] < 0.15)
    both, _ = marginal_values(roster, [P("QB2", "QB", 13),
                                       P("RBx", "RB", 13)], RP, sims=200)
    v = {x["name"]: x["value"] for x in both}
    check(f"equal ppg, both flex-eligible -> equal value, no QB bonus "
          f"({v['QB2']:.0f} vs {v['RBx']:.0f})",
          abs(v["QB2"] - v["RBx"]) < 1.0)

    # ILLEGAL LINEUPS. FLEX takes RB/WR/TE, SUPER_FLEX also takes QB.
    # Pooling the two let a third quarterback start in the plain FLEX,
    # which is what made every QB on the 8/11 board look like a
    # 400-point addition to a roster that already had two elite ones.
    twoqb = [P("QBa", "QB", 25), P("QBb", "QB", 24), P("RBz", "RB", 10),
             P("WRz", "WR", 9), P("WRy", "WR", 8)]
    av2 = draws([1.0] * len(twoqb), 40, 3)
    tot, sh = expected_points(twoqb, ded, flex, av2)
    started_qbs = sum(1 for i, p in enumerate(twoqb)
                      if p["pos"] == "QB" and sh[i] > 0.99)
    check(f"a superflex league starts at most TWO quarterbacks "
          f"(started {started_qbs})", started_qbs == 2)
    three = twoqb + [P("QBc", "QB", 23)]
    av3 = draws([1.0] * len(three), 40, 3)
    tot3, sh3 = expected_points(three, ded, flex, av3)
    check("...and a third QB adds nothing", abs(tot3 - tot) < 1e-6)
    check("...so he shows a 0% start share",
          sh3[-1] < 0.01)
    # the real case: two elite QBs already rostered, a better one offered
    elite = [P("Lamar", "QB", 24), P("Daniels", "QB", 22),
             P("Walker", "RB", 18), P("Thomas", "WR", 14),
             P("Moore", "WR", 12)]
    got, _ = marginal_values(elite, [P("Allen", "QB", 25)], RP, sims=100)
    check(f"an upgrade QB is worth the DELTA over the man he benches "
          f"({got[0]['value']:.0f}, not {25 * WEEKS})",
          abs(got[0]["value"] - (25 - 22) * WEEKS) < 1.0)
    check("...and the report names the QB who loses the slot",
          got[0]["displaces"] == "Daniels")

    # availability must be a real input, not decoration
    a, _ = marginal_values(roster, [P("Iron", "WR", 16, 1.0)], RP, sims=200)
    b, _ = marginal_values(roster, [P("Glass", "WR", 16, 0.6)], RP, sims=200)
    check(f"the same player with worse availability is worth less "
          f"({a[0]['value']:.0f} vs {b[0]['value']:.0f})",
          b[0]["value"] < a[0]["value"])

    # common random numbers: the ranking must be reproducible
    x1, _ = marginal_values(roster, [P("A", "WR", 16), P("B", "WR", 15.5)],
                            RP, sims=80)
    x2, _ = marginal_values(roster, [P("A", "WR", 16), P("B", "WR", 15.5)],
                            RP, sims=80)
    check("same inputs give the same numbers (seeded)",
          [r["value"] for r in x1] == [r["value"] for r in x2])
    check("...and a 0.5 ppg edge is not lost in simulation noise",
          x1[0]["name"] == "A")

    # THE PLAN MUST NOT REPEAT ITSELF. Scoring every pick against the
    # ORIGINAL roster made the 8/11 LG03-LG05 plan recommend ten
    # quarterbacks in a row: each one "displaced Jalen Milroe (15)"
    # because the simulated roster never gained the QB taken one pick
    # earlier. Walking the plan must grow the roster.
    # His real LG03-LG05 shape: one real quarterback plus a 15-point
    # body holding the SUPER_FLEX. The FIRST upgrade is worth a fortune
    # because it evicts the body; the SECOND is worth almost nothing
    # because it can only out-point a genuine starter. Scoring both
    # against the ORIGINAL roster hid that and produced a plan that
    # said "take a quarterback" ten picks running.
    thin = [P("Daniels", "QB", 22), P("Milroe", "QB", 1),
            P("RB1", "RB", 18), P("RB2", "RB", 15), P("WR1", "WR", 17),
            P("WR2", "WR", 14), P("WR3", "WR", 12), P("TE1", "TE", 11)]
    ups = [P("BigQB", "QB", 25), P("MidQB", "QB", 24)]
    first, _ = marginal_values(thin, ups, RP, sims=100)
    check(f"evicting a 1-point SUPER_FLEX is worth a fortune "
          f"(+{first[0]['value']:.0f})", first[0]["value"] > 350)
    check("...and the report says whom he evicted",
          first[0]["displaces"] == "Milroe")
    after = thin + [dict(first[0])]
    second, _ = marginal_values(after, [c for c in ups
                                        if c["name"] != first[0]["name"]],
                                RP, sims=100)
    check(f"...but the NEXT quarterback is worth almost nothing "
          f"(+{second[0]['value']:.0f}), not the same again",
          second[0]["value"] < first[0]["value"] / 8)
    check("...because he can now only out-point a real starter",
          second[0]["displaces"] == "Daniels")

    # _adp's 'exact' flag cannot detect a 1QB price inside `keys`.
    # keys = ("adp_2qb", "adp_dd_ppr", "adp_ppr", ...), and _pick returns
    # the FIRST key present — so a missing adp_2qb yields a 1QB number
    # marked exact=True. Any check built on that flag is vacuous; the
    # only honest test is whether the adp_2qb field itself is there.
    from battle_rhythm.draft_helper import _pick
    keys_sflex = ("adp_2qb", "adp_dd_ppr", "adp_ppr")
    no2qb = {"adp_ppr": 29.0}                 # a 1QB price, no adp_2qb
    yes2qb = {"adp_2qb": 4.0, "adp_ppr": 29.0}
    check("_pick silently returns the 1QB price when adp_2qb is absent",
          _pick(no2qb, keys_sflex) == 29.0)
    check("...and the correct one when it is present",
          _pick(yes2qb, keys_sflex) == 4.0)
    check("so presence of the FIELD is the only usable test",
          ("adp_2qb" in yes2qb) and ("adp_2qb" not in no2qb))

    # TWO-PICK LOOKAHEAD: do not spend an early pick on a man who lasts.
    def C(name, pos, ppg, adp):
        d = P(name, pos, ppg)
        d["adp"] = adp
        return d
    board = [C("Lasts", "WR", 20, 60), C("Expires", "WR", 19, 9),
             C("Also", "WR", 18, 61), C("Deep", "WR", 5, 200)]
    sc = sorted(board, key=lambda c: -c["ppg"])
    gone = [c for c in sc if c["adp"] < 17]
    stay = [c for c in sc if c["adp"] >= 17]
    check("the expiring player is taken when he beats the 2nd survivor",
          gone and len(stay) >= 2 and gone[0]["ppg"] >= stay[1]["ppg"])
    board2 = [C("Lasts", "WR", 20, 60), C("Expires", "WR", 8, 9),
              C("Also", "WR", 18, 61)]
    sc2 = sorted(board2, key=lambda c: -c["ppg"])
    g2 = [c for c in sc2 if c["adp"] < 17]
    s2 = [c for c in sc2 if c["adp"] >= 17]
    check("...and NOT taken when the second survivor is better",
          not (g2[0]["ppg"] >= s2[1]["ppg"]))

    # KEEPER DEPLETION. ADP comes from drafts where everyone was
    # available; a Hybrid removes ~5 per team before a pick is made.
    rows_d = [{"pid": "a", "adp": 10.0}, {"pid": "b", "adp": 61.0},
              {"pid": "c", "adp": 200.0}, {"pid": "d", "adp": None}]
    kept = [1.0, 2.0, 3.0, 40.0, 55.0] + [float(x) for x in range(70, 100)]
    deplete_adp(rows_d, kept)
    by = {r["pid"]: r for r in rows_d}
    check(f"3 keepers ahead of pick 10 -> he really goes "
          f"{by['a']['adp']:.0f}", by["a"]["adp"] == 7.0)
    check(f"5 keepers ahead of pick 61 -> he really goes "
          f"{by['b']['adp']:.0f}", by["b"]["adp"] == 56.0)
    check(f"all 35 ahead of pick 200 -> he really goes "
          f"{by['c']['adp']:.0f}", by["c"]["adp"] == 165.0)
    check("the raw market number is kept for display",
          by["a"]["adp_raw"] == 10.0)
    check("a player with no ADP is left alone, not shifted to pick 1",
          by["d"]["adp"] is None and "adp_raw" not in by["d"])
    edge = [{"pid": "x", "adp": 2.0}]
    deplete_adp(edge, [1.0, 1.5, 1.8, 1.9])
    check("depletion never produces a pick before 1",
          edge[0]["adp"] == 1.0)

    # marginal_values RETURNS COPIES. A field set on a candidate after
    # the call never reaches the rows the plan reads. Assert it once so
    # the next person does not rediscover it twice like I did.
    src = [P("Guy", "WR", 12.0)]
    out, _b = marginal_values(roster, src, RP, sims=40)
    src[0]["late_field"] = "set after the call"
    check("a field set on a candidate AFTER marginal_values does not "
          "reach its row", "late_field" not in out[0])
    src2 = [dict(P("Guy2", "WR", 12.0), early_field="set before")]
    out2, _b2 = marginal_values(roster, src2, RP, sims=40)
    check("...and a field set BEFORE does",
          out2[0].get("early_field") == "set before")

    # TAXI PICKS ARE A DIFFERENT JOB. Ranking a stash by 2026 points put
    # Geno Smith (+8) ahead of a first-round rookie who carries free into
    # next season. Rookies only, dynasty ADP, and anyone good enough to
    # start now is excluded — he belongs on the active roster.
    def R(name, pos, proj, adp, rookie, dadp):
        return {"pid": name, "name": name, "pos": pos, "proj": proj,
                "adp": adp, "rookie": rookie, "dadp": dadp}
    board = [R("VetQB", "QB", 262.0, 134.0, False, None),
             R("StudRook", "WR", 40.0, 120.0, True, 14.0),
             R("MehRook", "RB", 30.0, 118.0, True, 90.0),
             R("GoodNowRook", "RB", 300.0, 119.0, True, 8.0),
             R("EarlyRook", "WR", 35.0, 40.0, True, 5.0)]
    t = taxi_pick(board, set(), 110, 0, startable_bar=250.0)
    check(f"the taxi pick is the rookie with the best DYNASTY adp "
          f"({t['name']})", t["name"] == "StudRook")
    check("...not the veteran worth more points this season",
          t["pos"] != "QB")
    # the population a taxi seat exists for: unranked by the redraft
    # market entirely. Demanding an ADP excluded all of them.
    board.append(R("Redshirt", "TE", 0.0, None, True, 3.0))
    t0 = taxi_pick(board, set(), 110, 0, startable_bar=250.0)
    check(f"a rookie with NO redraft ADP is reachable, not skipped "
          f"({t0['name']})", t0["name"] == "Redshirt")
    check("...and he wins on dynasty price", t0["dadp"] == 3.0)
    board.pop()
    t2 = taxi_pick(board, {"StudRook"}, 110, 0, startable_bar=250.0)
    check("an already-taken stash is not offered twice",
          t2["name"] == "MehRook")
    check("a rookie good enough to START now is not wasted on the taxi",
          all(taxi_pick(board, tk, 110, 0, 250.0) is None
              or taxi_pick(board, tk, 110, 0, 250.0)["name"]
              != "GoodNowRook"
              for tk in [set(), {"StudRook"}, {"StudRook", "MehRook"}]))
    check("a rookie already gone by this pick is not offered",
          taxi_pick(board, {"StudRook", "MehRook"}, 110, 0, 250.0) is None)

    # AN UNPRICED ROOKIE IS STILL A TAXI CANDIDATE. Of 300 rookies only
    # 117 carry a dynasty price; the other 183 ARE the redshirt
    # population, because a player nobody drafts is a player no market
    # ranks. Requiring dadp made both Hybrids report "no rookie
    # qualifies" at all four taxi seats on 8/13.
    RK = lambda pid, age, dadp, proj=0.0: {
        "pid": pid, "name": pid, "pos": "WR", "proj": proj, "adp": None,
        "rookie": True, "dadp": dadp, "age": age}
    unpriced = [RK("OldNoPrice", 24, None), RK("YoungNoPrice", 21, None)]
    got = taxi_pick(unpriced, set(), 110, 0, 250.0)
    check(f"with nobody priced, an unpriced rookie is still offered "
          f"({got and got['pid']})", got is not None)
    check("...and the youngest wins the tiebreak",
          got["pid"] == "YoungNoPrice")
    mixed = unpriced + [RK("Priced", 26, 300.0)]
    check("but a PRICED rookie still beats them — a price is real "
          "information", taxi_pick(mixed, set(), 110, 0, 250.0)["pid"] == "Priced")
    check("a startable rookie is still excluded even with no price",
          taxi_pick([RK("Startable", 21, None, proj=260.0)], set(), 110, 0,
                    250.0) is None)
    check("no rookies at all still returns None, not a crash",
          taxi_pick([], set(), 110, 0, 250.0) is None)
    _fn2 = taxi_funnel(unpriced + [RK("Startable", 21, None, proj=260.0)],
                       {"OldNoPrice"}, 110, 0, 250.0)
    check(f"the funnel counts every stage ({_fn2})",
          _fn2["rows"] == 3 and _fn2["rookies"] == 3
          and _fn2["not_taken"] == 2 and _fn2["under_bar"] == 1
          and _fn2["priced"] == 0)
    check("funnel and picker agree on who survives",
          (taxi_pick(unpriced + [RK("Startable", 21, None, proj=260.0)],
                     {"OldNoPrice"}, 110, 0, 250.0) is not None)
          == (_fn2["under_bar"] > 0))
    bar = startable_bar([R("a", "QB", 300.0, 1, False, None),
                         R("b", "QB", 100.0, 2, False, None)],
                        {"QB": 1.0}, 2)
    check(f"the startable bar is the last starter's projection ({bar:.0f})",
          bar == 100.0)

    # A THIN POSITION MUST NOT SET THE BAR TO ZERO. This is the bug that
    # made both Hybrids report "no rookie qualifies" at all four taxi
    # seats: most quarterbacks were kept, only 20 remained against a
    # superflex demand of 24, and the old clamp read the 20th of 20 — a
    # zero-projection rookie — then min() spread that 0.0 everywhere.
    _thin = ([{"pos": "QB", "proj": float(p), "pid": f"q{p}", "name": f"q{p}",
               "rookie": False, "adp": None, "dadp": None}
              for p in range(360, 190, -10)]
             + [{"pos": "QB", "proj": 0.0, "pid": f"qr{i}", "name": f"qr{i}",
                 "rookie": True, "adp": None, "dadp": None} for i in range(3)]
             + [{"pos": "WR", "proj": float(300 - i), "pid": f"w{i}",
                 "name": f"w{i}", "rookie": False, "adp": None,
                 "dadp": None} for i in range(90)])
    _pc = {"QB": 2.0, "WR": 2.9}
    _qbs = sum(1 for c in _thin if c["pos"] == "QB")
    _bar = startable_bar(_thin, _pc, 12)
    check(f"{_qbs} QBs against a demand of 24 does NOT drag the bar to 0 "
          f"(bar {_bar:.0f})", _bar > 0)
    check("...the bar comes from the position deep enough to define one",
          _bar == sorted((c["proj"] for c in _thin if c["pos"] == "WR"),
                         reverse=True)[34])
    check("a rookie is therefore still taxi-eligible under that bar",
          taxi_pick(_thin, set(), 110, 0, _bar) is not None)
    check("and even a degenerate bar of 0 cannot empty the pool",
          taxi_pick(_thin, set(), 110, 0, 0.0) is not None)
    check("every position too thin -> no bar at all, reported as 0",
          startable_bar([{"pos": "QB", "proj": 5.0}], {"QB": 2.0}, 12) == 0.0)

    # ROOM SHAVE is per-league DATA, never a default. Shipping a global
    # 10 generalised a LG01 habit onto rooms that draft at market.
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"DB": {"room_shave": 10}, "HY": {"room_shave": 0},
                            "NO": {}}))
    tp = pathlib.Path(tmp)
    check("a room that reaches carries its own shave",
          room_shave("DB", path=tp) == 10)
    check("a room that drafts at market shaves nothing",
          room_shave("HY", path=tp) == 0)
    check("a league with no entry defaults to 0, not to someone else's 10",
          room_shave("NO", path=tp) == 0 and room_shave("???", path=tp) == 0)
    check("an explicit --shave overrides the stored value",
          room_shave("DB", override=3, path=tp) == 3)
    check("a missing keepers.json does not crash the plan",
          room_shave("DB", path=pathlib.Path("/nope/nope.json")) == 0)
    os.unlink(tmp)

    # THE CENSUS REPORTS. IT DOES NOT CULL. Seven with an empty taxi is
    # LEGAL — taxi players can be moved, so only the total binds. The
    # previous version of these checks asserted that such a roster
    # "releases 2", which encoded a rule the league does not have and
    # would have handed two of a rival's keepers back to the board.
    _t = {f"p{i}": {"position": "WR"} for i in range(1, 14)}
    _t["t1"] = {"position": "TE"}
    _ros = [{"owner_id": "A", "players": [f"p{i}" for i in range(1, 8)],
             "taxi": []},                          # 7 rostered, 0 taxi: fine
            {"owner_id": "B", "players": ["p1", "p2", "p3"], "taxi": []},
            {"owner_id": "C", "players": list(_t)[:12], "taxi": ["t1"]}]
    _cen = roster_census(_ros, _t, "Z", ceiling=7)
    _by = {c["owner"]: c for c in _cen}
    check("7 rostered with an empty taxi is legal, not an overage",
          _by["A"]["rostered"] == 7 and _by["A"]["over"] == 0)
    check("a 3-man roster is under and flagged as nothing",
          _by["B"]["over"] == 0)
    check(f"a 13-man roster is flagged {_by['C']['over']} over, and only "
          f"flagged", _by["C"]["over"] == 6)
    check("the census sorts the worst overage first",
          _cen[0]["owner"] == "C")
    check("the census returns counts only — no player is ever named "
          "for release",
          all("released" not in c and "qb_released" not in c
              for c in _cen))

    # THE HEADER MUST NOT DOUBLE-COUNT AN EXPIRED REDSHIRT. These four
    # fail against the previous header, which printed len(roster) and
    # len(taxi) as disjoint groups when they overlap. That is the
    # known-bad case: his 8/12 roster is seven players, two of them off
    # expired redshirts, and the old line called it "7 active · 2 on
    # taxi (cannot start, excluded)".
    _tx = {"gadsden": {"years_exp": 1}, "kwilliams": {"years_exp": 1},
           "true_rookie": {"years_exp": 0}, "no_data": {}}
    _l = taxi_line(7, {"gadsden", "kwilliams"}, _tx, 300)
    check(f"expired redshirts read as active, not excluded ({_l[:34]}...)",
          "7 active" in _l and "2 off EXPIRED" in _l
          and "cannot start" not in _l)
    check("a player still redshirting is reported as unable to start",
          "1 still redshirting" in taxi_line(5, {"true_rookie"}, _tx, 300))
    check("missing years_exp is treated as sitting, never guessed active",
          "1 still redshirting" in taxi_line(5, {"no_data"}, _tx, 300))
    check("an empty taxi prints no taxi clause at all",
          "taxi" not in taxi_line(9, set(), _tx, 300))

    # A DISPLAY BLOCK MUST NOT REBIND build()'s DATA. The census printer
    # bound its list to `rows`, which is the candidate board unpacked
    # from build() and read by the draft plan far below. The report
    # printed perfectly and then died on KeyError 'pid'. Rather than
    # trust a comment not to be ignored, walk report() and assert that
    # nothing build() hands over is ever reassigned inside it. This
    # catches the whole class, not the one instance.
    import ast as _ast
    _src = pathlib.Path(__file__).read_text(encoding="utf-8")
    _fn = next(n for n in _ast.walk(_ast.parse(_src))
               if isinstance(n, _ast.FunctionDef) and n.name == "report")
    _unpacked = set()
    for _n in _fn.body[:3]:
        if isinstance(_n, _ast.Assign) and isinstance(_n.targets[0],
                                                      _ast.Tuple):
            _unpacked = {e.id for e in _n.targets[0].elts
                         if isinstance(e, _ast.Name)}
            break
    _rebound = {t.id for _n in _ast.walk(_fn)
                if isinstance(_n, _ast.Assign)
                for t in _n.targets
                if isinstance(t, _ast.Name) and t.id in _unpacked}
    check(f"report() never rebinds what build() handed it "
          f"({len(_unpacked)} names checked)",
          bool(_unpacked) and not _rebound)

    # NOTHING MAY TOUCH `market` BEFORE build() CREATES IT. I added the
    # byes lookup near the top of build() and stashed the note on market
    # in the same breath — 150 lines before the dict exists. Every
    # selftest passed, because the whole 85 of them and all 26 in
    # test_all avoid build(): it needs the live API, so it is the one
    # function with no coverage at all. It crashed on his first real run.
    #
    # Same static-walk trick as the report() rebinding check. It catches
    # the class rather than the instance, and it does not need a network.
    _b = next(n for n in _ast.walk(_ast.parse(_src))
              if isinstance(n, _ast.FunctionDef) and n.name == "build")
    _made = min([n.lineno for n in _ast.walk(_b)
                 if isinstance(n, _ast.Assign)
                 for t in n.targets
                 if isinstance(t, _ast.Name) and t.id == "market"] or [0])
    _early = [n.lineno for n in _ast.walk(_b)
              if isinstance(n, _ast.Subscript)
              and isinstance(n.value, _ast.Name) and n.value.id == "market"
              and _made and n.lineno < _made]
    check(f"build() never writes to `market` before creating it "
          f"(created line {_made})", bool(_made) and not _early)

    # BYE PRESSURE. The 8/13 emoji plan put six of fourteen players out
    # in week 13 — four of them Baltimore — leaving eight bodies for nine
    # slots. That is a forfeited starting slot, and a season-total model
    # cannot see it. These pin the arithmetic that surfaces it.
    from battle_rhythm.sleeper_client import bye_pressure, load_byes, bye_of
    _r = [13, 7, 5, 7, 7, 7, 13, 13, 13, 13, 13, 8, 10, 5]   # 14, six on 13
    _pr = bye_pressure(_r, 9)
    check(f"a six-man bye week leaves 8 of 14 available ({_pr.get(13)})",
          _pr[13] == 8)
    check("...which is SHORT of nine starters", _pr[13] < 9)
    check("the four-man week 7 is tight but fillable", _pr[7] == 10)
    check("every week with anybody out is reported, and only those",
          set(_pr) == {5, 7, 8, 10, 13})
    check("a roster with no byes at all reports nothing",
          bye_pressure([None, None], 9) == {})
    check("a GENERATOR is counted correctly, not consumed to zero",
          bye_pressure((b for b in [13, 13, 7]), 9) == {7: 2, 13: 1})
    check("byes.json covers all 32 teams", len(load_byes()[0]) == 32)
    check("...and the ones this session verified are right",
          bye_of("BAL") == 13 and bye_of("WAS") == 7 and bye_of("KC") == 5
          and bye_of("JAX") == 7 and bye_of("LAC") == 7 and bye_of("BUF") == 7)
    check("an unknown team is None, never a guess", bye_of("ZZZ") is None)
    check("a stale byes.json refuses to answer rather than lying",
          load_byes("2099")[0] == {} and "not 2099" in load_byes("2099")[1])

    # snake geometry — slot 8 of 12 must alternate 8 / 17 / 32 / 41 ...
    pk = snake_picks(8, 10, 12)
    check(f"snake picks from slot 8 of 12 ({pk[:4]}...)",
          pk == [8, 17, 32, 41, 56, 65, 80, 89, 104, 113])
    check("...ten rounds, ten picks", len(pk) == 10)
    check("slot 1 opens every odd round", snake_picks(1, 4, 12)[:2] == [1, 24])

    # THIRD-ROUND REVERSAL. His real LG03-LG05 card, given verbatim:
    # 1.8 2.5 3.5 4.8 5.5 6.8 7.5 8.8 9.5 10.8. A plain snake from slot 8
    # gives 3.8 and 4.5. settings.reversal_round is 3 there and 0 in the
    # emoji league, so the two rooms do not share a format and every
    # number from round 3 down was wrong in one of them.
    rr = snake_picks(8, 10, 12, reversal_round=3)
    check(f"3RR from slot 8 of 12 matches his card ({rr[:4]}...)",
          rr == [8, 17, 29, 44, 53, 68, 77, 92, 101, 116])
    check("...and it differs from a plain snake everywhere after round 2",
          snake_picks(8, 10, 12)[2:] != rr[2:]
          and snake_picks(8, 10, 12)[:2] == rr[:2])
    check("reversal_round=0 is the plain snake, unchanged",
          snake_picks(8, 10, 12, reversal_round=0) == snake_picks(8, 10, 12))
    check("the emoji league (reversal 0, slot 6) is unaffected",
          snake_picks(6, 10, 12, 0) == [6, 19, 30, 43, 54, 67, 78, 91, 102, 115])
    # the reversal compensates the late-slot picker: round 3 comes EARLIER
    check("a late slot gains at round 3 under a reversal",
          snake_picks(8, 3, 12, 3)[2] < snake_picks(8, 3, 12)[2])
    check("...and an early slot pays for it",
          snake_picks(2, 3, 12, 3)[2] > snake_picks(2, 3, 12)[2])
    check("slot 12 closes every odd round",
          snake_picks(12, 4, 12)[:2] == [12, 13])

    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()

    TAKES_VALUE = ("--pos", "--top", "--sims", "--slot",
                   "--shave", "--drop")

    def opt(flag, default=None, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    # walk once so a flag's VALUE is never mistaken for the league name
    frag, skip = None, False
    for i, tok in enumerate(a):
        if skip:
            skip = False
            continue
        if tok in TAKES_VALUE:
            skip = True
        elif tok.startswith("--"):
            continue
        elif frag is None:
            frag = tok
        else:
            frag += " " + tok
    report(frag, sims=opt("--sims", DEFAULT_SIMS, int),
           pos=opt("--pos"), top=opt("--top", 40, int),
           include_all="--all" in a, slot=opt("--slot", None, int),
           shave=opt("--shave", None, int), drop=opt("--drop"))
