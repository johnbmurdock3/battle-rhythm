"""
keeper.py — keeper recommendations for the Hybrid leagues.

  python keeper.py                      # both Hybrid leagues
  python keeper.py <league_2026_id>     # one league

Rules (per John, both Hybrids, no round cost):
  - 3 keepers, at most 1 QB
  - plus 2 drafted rookies (2025 rookie class), at most 1 QB
  - taxi: drafted rookies not on the active roster carry over automatically
  ASSUMPTION flagged in output: rookie keepers are IN ADDITION to the 3.

Method: pull your roster from the league's previous (2025) season, project every
player for 2026 under the 2026 league's own scoring (the verified engine),
then greedily fill each keeper slot with the best projection that satisfies the
QB caps. Rookie = player table years_exp == 1 in the 2026 data (the 2025 class).
Everything prints with projections so you can overrule any line — projections
don't know locker-room context; you do.
"""

import pathlib
from battle_rhythm import paths as _paths
import sys
from battle_rhythm.sleeper_client import get, players, name_of, state, USERNAME
from battle_rhythm.draft_helper import (season_projection_totals, _adp, adp_keys_for,
                          DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS)

HYBRIDS = ("9000000000000000019", "9000000000000000013")


def pick_constrained(cands, n, max_qb, tbl):
    """Best n by projection with at most max_qb QBs. cands: [(proj, pid)] sorted desc."""
    out, qbs = [], 0
    for proj, pid in cands:
        if len(out) == n:
            break
        is_qb = (tbl.get(pid) or {}).get("position") == "QB"
        if is_qb and qbs >= max_qb:
            continue
        out.append((proj, pid))
        qbs += is_qb
    return out


def dr_eligible(league_2026_id, tbl, uid, base_season):
    """
    Drafted-Rookie eligibility, per the actual rule: any player YOU drafted in
    THIS league during his NFL rookie season — keepable via DR slots in later
    years too (that's how Daniels, a 2024 rookie, stays DR-eligible in 2026).
    Walks the previous-league chain, collects your draft picks each season,
    keeps those whose rookie year (base_season - years_exp) matches the season
    they were drafted.
    """
    elig, lid, hops = set(), league_2026_id, 0
    while lid and hops < 12:
        lg = get(f"league/{lid}")
        if not lg:
            break
        try:
            season = int(lg.get("season") or 0)
        except ValueError:
            season = 0
        # A league season can hold MULTIPLE drafts, and league.draft_id points
        # at only one of them (learned live: 2024 Hybrid ran a 7-rounder AND
        # the real 10-round startup where Daniels/BTJ were actually taken).
        # Enumerate them all.
        drafts = get(f"league/{lid}/drafts") or []
        draft_ids = {d.get("draft_id") for d in drafts if d.get("draft_id")}
        if lg.get("draft_id"):
            draft_ids.add(lg["draft_id"])
        if season:
            for did in draft_ids:
                for p in get(f"draft/{did}/picks") or []:  # draft-id-ok: this IS the enumeration
                    pid = p.get("player_id")
                    if not pid or str(p.get("picked_by")) != str(uid):
                        continue
                    yexp = (tbl.get(pid) or {}).get("years_exp")
                    if yexp is not None and base_season - yexp == season:
                        elig.add(pid)
        lid = lg.get("previous_league_id")
        hops += 1
    return elig


def upcoming_picks(lg, uid, max_show=10, roster_id=None):
    """My overall pick numbers in the league's upcoming draft.

    Returns (picks, slot_estimated). Honours settings.reversal_round and,
    when roster_id is supplied, applies traded picks. Both were missing
    until 8/13: the two Hybrids run different formats (0 and 3) and he
    owns a traded round-8 pick in each, so this printed a pick list that
    was neither his shape nor his count.
    """
    from battle_rhythm.sleeper_client import round_is_forward, traded_deltas
    from battle_rhythm.draft_helper import resolve_draft
    # league.draft_id alone pointed at a draft marked COMPLETE with zero
    # picks in LG03, so this listed the entire schedule
    # as upcoming and told him "10 picks left" on 9/2 for a draft that
    # finished 8/18. This module already knew a season can hold several
    # drafts -- see drafted_rookie_eligible above, which enumerates them --
    # and this function did not use that knowledge.
    draft, made_picks = resolve_draft(lg)
    if not draft:
        return [], False
    st = draft.get("settings") or {}
    teams = st.get("teams") or lg.get("total_rosters") or 12
    rounds = st.get("rounds") or 0
    rev = st.get("reversal_round") or 0
    slot = (draft.get("draft_order") or {}).get(str(uid))
    est = slot is None
    if est:
        slot = (teams + 1) // 2
    picks = []
    for rnd in range(1, min(rounds, max_show) + 1):
        pos = slot if round_is_forward(rnd, rev) else teams - slot + 1
        picks.append((rnd - 1) * teams + pos)
    # TRADED PICKS NEVER FIRED. traded_deltas needs a roster_id and BOTH
    # callers passed None, so the parameter existed and did nothing — his
    # acquired round-8 pick in each Hybrid was absent from every list this
    # printed, and the live Sleeper board showed a count his own tool did
    # not (8/17). Resolve it here instead of threading it through callers.
    if roster_id is None and lg.get("league_id"):
        for r in (get(f"league/{lg['league_id']}/rosters") or []):
            if r.get("owner_id") == uid:
                roster_id = r.get("roster_id")
                break
    if roster_id is not None and not est:
        gained, lost = traded_deltas(draft.get("draft_id"), roster_id, teams,
                                     rev, draft.get("slot_to_roster_id"))
        picks = sorted((set(picks) - lost) | {p for p in gained
                                              if p <= rounds * teams})

    # SPENT PICKS ARE NOT UPCOMING. This returned the whole schedule, so
    # mid-draft it kept offering pick 6 as a place to reclaim a keeper
    # after Etienne had already been taken with it. Overall pick numbers
    # are 1-based and sequential, so anything at or below the count made
    # is gone. redraft_at() walks this list backwards — leaving spent
    # picks in it told him a player was reclaimable in the past.
    status = draft.get("status") or lg.get("status")
    if status in ("drafting", "paused"):
        picks = [p for p in picks if p > len(made_picks)]
    elif status == "complete":
        # A finished draft has no upcoming picks at all. The old code only
        # filtered while status was "drafting", so a completed draft kept
        # its whole schedule and redraft_at() walked a list of picks that
        # were spent weeks ago.
        picks = []

    return picks, est


def actual_kept(league_2026_id):
    """The players every team has ALREADY retained — observed, not guessed.

    Once keepers lock, each team's current-season roster IS its keeper
    set (here: 3 keepers + 2 drafted rookies + taxi, max 7). Those
    players never enter the draft, so they are exactly the depletion.
    Estimating them from last season's rosters, which is what this did
    until 8/11, was solving a problem the API had already answered.

    Returns (kept_ids, rosters). Empty kept set means keepers are not
    locked yet and the caller should fall back to estimate_kept."""
    rosters = get(f"league/{league_2026_id}/rosters") or []
    kept = set()
    for r in rosters:
        kept |= {p for p in (r.get("players") or []) if p}
        kept |= {p for p in (r.get("taxi") or []) if p}
    return kept, rosters


def estimate_kept(rosters, tbl, totals, taxi_by_roster=None,
                  vet_slots=3, dr_slots=2):
    """Best guess at every player the LEAGUE will retain.

    Rosters are public, so we do not have to hand-wave the depletion: for
    each team, the players they keep are almost certainly their highest
    projecting ones under the slot rules. Take each roster's top
    `vet_slots` (max 1 QB, the league rule) plus `dr_slots` more as the
    rookie slots. It will be wrong at the margins — someone keeps a
    favourite, someone else keeps for age instead of points — but it is
    vastly closer than assuming nobody is kept at all.

    Returns a set of player_ids."""
    kept = set()
    for r in rosters:
        pool = [p for p in (r.get("players") or []) if p]
        taxi = set((taxi_by_roster or {}).get(r.get("roster_id")) or
                   (r.get("taxi") or []))
        pool = [p for p in pool if p not in taxi]
        ranked = sorted(((totals.get(p, 0.0), p) for p in pool), reverse=True)
        kept |= {p for _, p in pick_constrained(ranked, vet_slots, 1, tbl)}
        left = [(pr, p) for pr, p in ranked if p not in kept]
        kept |= {p for _, p in pick_constrained(left, dr_slots, 1, tbl)}
    return kept


def league_kept_adps(prev_id, tbl, totals, season, keys, fb, lg,
                     current_id=None):
    """Sorted ADPs of the players the league keeps. Observed when the
    current rosters already show them; estimated only as a fallback."""
    kept = set()
    if current_id:
        kept, _r = actual_kept(current_id)
    if not kept:
        rosters = get(f"league/{prev_id}/rosters") or []
        if not rosters:
            return []
        kept = estimate_kept(rosters, tbl, totals)
    out = []
    for p in kept:
        adp, _ = _adp(p, season, keys, fb)
        if adp:
            out.append(adp)
    out.sort()
    return out


def show_keepers(league_2026_id):
    """python keeper.py <league> --kept — every team's locked keepers.

    This is the ground truth the whole depletion model rests on, so it
    should be readable rather than inferred from a count."""
    lg = get(f"league/{league_2026_id}") or {}
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()
    totals = season_projection_totals(season, scoring)
    kept, rosters = actual_kept(league_2026_id)
    users = {u.get("user_id"): (u.get("display_name") or "?")
             for u in (get(f"league/{league_2026_id}/users") or [])}
    dynasty = (lg.get("settings") or {}).get("type") == 2
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # Was gated on `dynasty` alone while adjusted_board 70 lines below
    # gated on `dynasty and not short_horizon` — one file, one league,
    # two markets. These are other teams' locked keepers; price them in
    # the market this room actually drafts in, same as everything else.
    from battle_rhythm.league_rules import is_keeper_league
    keys, fb = adp_keys_for(rp, dynasty, is_keeper_league(league_2026_id))

    print(f"\n══ {lg.get('name')} — locked keepers, {len(kept)} players "
          f"across {len(rosters)} teams\n")
    by_pos = {}
    for r in sorted(rosters, key=lambda x: users.get(x.get("owner_id"), "")):
        name = users.get(r.get("owner_id"), str(r.get("owner_id"))[:8])
        ps = [p for p in (r.get("players") or []) if p]
        taxi = {p for p in (r.get("taxi") or []) if p}
        rows = sorted(((totals.get(p, 0.0), p) for p in set(ps) | taxi),
                      reverse=True)
        tot = sum(pr for pr, _ in rows)
        print(f"── {name}  ({len(rows)} kept, {tot:.0f} proj pts)")
        for pr, p in rows:
            m = tbl.get(p) or {}
            pos = m.get("position") or "?"
            by_pos[pos] = by_pos.get(pos, 0) + 1
            adp, _ = _adp(p, season, keys, fb)
            tag = "  (taxi)" if p in taxi else ""
            print(f"     {pos:<4}{(m.get('full_name') or p)[:24]:<26}"
                  f"proj {pr:>6.0f}  adp {adp:>5.0f}{tag}"
                  if adp else
                  f"     {pos:<4}{(m.get('full_name') or p)[:24]:<26}"
                  f"proj {pr:>6.0f}  adp     -{tag}")
        print()
    print("kept by position: "
          + "  ".join(f"{p}:{n}" for p, n in sorted(by_pos.items())))
    print("a position heavily kept is one nobody needs to draft — that is "
          "why it falls, and it is not the same as the room mispricing it.")


def adjusted_board(league_2026_id, top=12):
    """python keeper.py <league> --board

    What is ACTUALLY on the board at each of your picks, once the
    league's kept players are removed.

    Global ADP comes from drafts where nobody is kept. In a league
    retaining 5 per team, ~60 players never appear, and every remaining
    player slides earlier by the number of kept players ahead of him.
    A brief written off raw ADP will tell you a name is available two
    rounds after he is actually gone. This prints both numbers so the
    size of the correction is visible rather than assumed."""
    lg = get(f"league/{league_2026_id}")
    if not lg:
        raise SystemExit(f"league {league_2026_id} not found")
    prev_id = lg.get("previous_league_id")
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()
    totals = season_projection_totals(season, scoring)
    dynasty = (lg.get("settings") or {}).get("type") == 2
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # MARKET CHOICE. Sleeper types these leagues as dynasty, but a
    # 3-keeper league carries 7 players and churns the rest, so it drafts
    # far closer to redraft. Dynasty ADP applies an age penalty this room
    # does not, which shows up as veterans looking "available late" when
    # they are not — Dak, Kittle, Mike Evans and Davante Adams all
    # surfaced 40+ picks past where they will actually go.
    try:
        import json as _json
        _rules = _json.loads(_paths.data("keepers.json").read_text(encoding="utf-8"))
    except Exception:
        _rules = {}
    short_horizon = bool((_rules.get(str(league_2026_id)) or {}).get("keeper"))
    keys, fb = adp_keys_for(rp, dynasty, short_horizon)
    if dynasty and not short_horizon:
        market = "dynasty" + (" 2QB" if superflex else "")
    else:
        market = ("redraft" + (" 2QB" if superflex else "")
                  + " — limited-keeper league, dynasty ADP over-penalizes age")
    uid = get(f"user/{USERNAME}")["user_id"]
    my_picks, slot_est = upcoming_picks(lg, uid)

    # OBSERVED keepers beat estimated ones. Fall back only if nothing is
    # locked yet.
    kept, rosters = actual_kept(league_2026_id)
    source = "observed from current rosters"
    if not kept:
        rosters = get(f"league/{prev_id}/rosters") or [] if prev_id else []
        kept = estimate_kept(rosters, tbl, totals) if rosters else set()
        source = "ESTIMATED from last season (keepers not locked yet)"
    kept_adps = []
    for p in kept:
        a, _ = _adp(p, season, keys, fb)
        if a:
            kept_adps.append(a)
    kept_adps.sort()

    # room bias stacks ON TOP of depletion: a scarce position is both kept
    # more often AND drafted earlier by a room that knows it is scarce.
    try:
        from battle_rhythm import room_bias
        bias = {p: room_bias.shift_for(league_2026_id, p)
                for p in ("QB", "RB", "WR", "TE")}
    except Exception:
        bias = {}

    # positional demand REMAINING: kept players remove demand as well as
    # supply. If ten teams already kept a TE, tight ends fall because two
    # teams need one — which is a different fact from "this room
    # undervalues TEs", and it changes whether YOU should pay up.
    # OPEN SLOTS, not positions-held. A team holding one quarterback
    # counted as QB-filled, in a league that starts a QB AND a
    # SUPER_FLEX. That printed QB:0/12 for LG03-LG05 above a note saying
    # a position nobody needs falls — five days before a plan built on
    # taking a quarterback at pick 8. slot_plan knows SUPER_FLEX.
    from battle_rhythm.roster_shape import slot_plan
    ded, flex_slots, _bn = slot_plan(lg.get("roster_positions"))
    need = {p: 0 for p in ("QB", "RB", "WR", "TE")}
    for r in rosters:
        held = {}
        for _pid in (r.get("players") or []):
            _pos = (tbl.get(_pid) or {}).get("position")
            if _pos:
                held[_pos] = held.get(_pos, 0) + 1
        for p in need:
            need[p] += max(0, ded.get(p, 0) - held.get(p, 0))
    flex_open = len(flex_slots) * len(rosters)

    raw = []
    for pid, pr in totals.items():
        if pid in kept or pr <= 0:
            continue
        m = tbl.get(pid) or {}
        if m.get("position") not in ("QB", "RB", "WR", "TE"):
            continue
        a, _ = _adp(pid, season, keys, fb)
        if a:
            raw.append((pr, a, pid, m))
    # rank within position by projection — needed for the elite taper
    pos_rank, counters = {}, {}
    for pr, a, pid, m in sorted(raw, reverse=True):
        p = m["position"]
        counters[p] = counters.get(p, 0) + 1
        pos_rank[pid] = counters[p]

    def eff(adp, pos=None, rank=99):
        depleted = adp - sum(1 for a in kept_adps if a < adp)
        # ELITE TAPER. Measured positional bias is an average dominated by
        # replaceable players. The best one or two at a position get taken
        # on absolute value, not positional convention, so they do not
        # inherit the crowd's discount. Full bias by about the 7th at a
        # position, none at all for the top one.
        taper = min(1.0, max(0.0, (rank - 1) / 6.0))
        return max(1, depleted - (bias.get(pos) or 0.0) * taper)

    pool = [(eff(a, m["position"], pos_rank.get(pid, 99)), a, pr, pid, m)
            for pr, a, pid, m in raw]
    pool.sort()

    print(f"\n══ {lg.get('name')} — keeper-adjusted draft board")
    print(f"   {len(kept)} players kept league-wide across {len(rosters)} "
          f"teams — {source}")
    print(f"   ({len(kept_adps)} of them carry a market price and shift "
          f"the board)")
    print(f"   pricing market: {market}")
    live = {p: v for p, v in bias.items() if v}
    if live:
        print("   room bias (measured, room_bias.py): "
              + ", ".join(f"{p} {v:+.0f}" for p, v in live.items()))
    else:
        print("   room bias: not measured — run "
              "'python room_bias.py <league>' to add it")
    print("   dedicated starting slots still open, league-wide: "
          + "  ".join(f"{p}:{n}" for p, n in need.items()))
    # A superflex league has ONE dedicated QB slot, so counting dedicated
    # slots alone still prints QB:0 while twelve teams need a second
    # quarterback. The demand is real and it lives in the flex slots.
    # FLEX_SHARE already encodes where the model thinks each flex slot
    # goes (SUPER_FLEX is 85% QB), so say it rather than leaving the
    # reader to infer it from a raw flex count.
    if flex_slots:
        from battle_rhythm.roster_shape import FLEX_SHARE
        implied = {}
        for _slot, _fills in flex_slots:
            for _p, _share in (FLEX_SHARE.get(_slot) or {}).items():
                implied[_p] = implied.get(_p, 0.0) + _share * len(rosters)
        print(f"   flex slots ({len(flex_slots) * len(rosters)} league-wide: "
              + ", ".join(s for s, _f in flex_slots) + ") imply: "
              + "  ".join(f"{p}:{v:.0f}" for p, v in
                          sorted(implied.items(), key=lambda kv: -kv[1])))
    print("   (a position most teams already kept falls because nobody "
          "needs it, not because the room misprices it)")
    print("   eff = where he actually goes here.  adp = global market.")
    print("   bias is TAPERED by positional rank — the best player at a "
          "position is taken on value, not convention.\n")
    # A shortlist ranked by WHERE A PLAYER GOES surfaces anyone the market
    # prices early and the projection feed does not know. Pick 68 led with
    # a quarterback projected for 1 point, above a tight end at 225.
    # draft_helper.find documents the same trap: "a star with proj 0.0
    # means the projections feed is missing him." 120 is the board's own
    # threshold for a startable season.
    FLOOR = 120
    for n in my_picks[:6]:
        here = [x for x in pool if x[0] >= n]
        shown = [x for x in here if x[2] >= FLOOR][:top]
        cut = sum(1 for x in here[:top] if x[2] < FLOOR)
        span = (f"global adp {min(x[1] for x in shown):.0f}"
                f"\u2013{max(x[1] for x in shown):.0f}"
                if shown else "nothing left above the floor")
        print(f"── PICK {n}   best available ({span})")
        for e, a, pr, pid, m in shown:
            gap = a - e
            print(f"     eff {e:>5.0f}  adp {a:>5.0f}  (-{gap:>3.0f})"
                  f"  proj {pr:>5.0f}  {name_of(pid, tbl)}")
        if cut:
            print(f"     ({cut} suppressed: projected under {FLOOR} — "
                  f"marginal, or missing from the feed)")
        gone = [x for x in pool if x[0] < n][-6:]
        if gone:
            print("     GONE BY NOW despite a later global price: "
                  + ", ".join(f"{name_of(p, tbl).split(' (')[0]} "
                              f"(adp {a:.0f})" for _e, a, _pr, p, _m in gone))
        print()


def analyze(league_2026_id):
    lg = get(f"league/{league_2026_id}")
    if not lg:
        raise SystemExit(f"league {league_2026_id} not found")
    prev_id = lg.get("previous_league_id")
    if not prev_id:
        raise SystemExit(f"{lg.get('name')}: no previous season league linked")
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()

    uid = get(f"user/{USERNAME}")["user_id"]
    rosters = get(f"league/{prev_id}/rosters") or []
    mine = next((r for r in rosters if r.get("owner_id") == uid), None)
    if not mine:
        raise SystemExit(f"{lg.get('name')}: no roster of yours in previous league {prev_id}")
    taxi = [p for p in (mine.get("taxi") or []) if p]
    # Taxi players carry over automatically and cost NO keeper slot (they were
    # locked to taxi all season to earn that). They never compete for slots.
    pool = [p for p in (mine.get("players") or []) if p and p not in set(taxi)]

    # WHAT HE ACTUALLY KEPT beats what the model would have chosen. Keepers
    # locked 7/1, but this re-derived the optimal set against the live pool
    # every run — so on 8/17 it printed "KEEP Mike Evans" while Evans sat on
    # the live draft board and DJ Moore, the player actually retained, showed
    # up under "next" as a candidate passed over. Reading a recommendation as
    # a roster is how you misread your own team.
    #
    # league/{id}/rosters on the CURRENT league is the retention record, and
    # mid-draft it still excludes in-draft picks — which is exactly the set
    # we want here. (discover() merges picks in; this deliberately does not.)
    now_rosters = get(f"league/{league_2026_id}/rosters") or []
    now_mine = next((r for r in now_rosters if r.get("owner_id") == uid), None)
    retained = {str(p) for p in ((now_mine or {}).get("players") or []) if p}
    now_taxi = {str(p) for p in ((now_mine or {}).get("taxi") or []) if p}
    locked = bool(retained)

    totals = season_projection_totals(season, scoring)
    dynasty = (lg.get("settings") or {}).get("type") == 2
    # Had neither the keeper flag nor the superflex key — in a Hybrid it
    # answered adp_dynasty_ppr, the 1QB dynasty market.
    from battle_rhythm.league_rules import is_keeper_league
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            is_keeper_league(league_2026_id))

    elig = dr_eligible(league_2026_id, tbl, uid, int(season))

    ranked = sorted(((totals.get(p, 0.0), p) for p in pool), reverse=True)
    rookies = [(pr, p) for pr, p in ranked if p in elig]
    vets = [(pr, p) for pr, p in ranked if p not in elig]
    # a DR-eligible player CAN also be kept as a regular keeper if that fills
    # better; the greedy below fills DR first (scarcer slots), then regular
    # keepers from everyone left over including unused DR-eligibles
    keep_rookies = pick_constrained(rookies, 2, 1, tbl)
    kept_dr = {p for _, p in keep_rookies}
    vets = sorted(vets + [(pr, p) for pr, p in rookies if p not in kept_dr],
                  reverse=True)

    keep_vets = pick_constrained(vets, 3, 1, tbl)

    print(f"\n══ {lg.get('name')} — keeper analysis (2026 proj, this league's scoring)")
    print("   Structure (confirmed by John's actual 2025 retention of 7):")
    print("   3 keepers (max 1 QB) + 2 drafted-rookies (max 1 QB, must be YOUR")
    print("   draft pick in the player's NFL rookie year — trades don't qualify)")
    print("   + taxi riders, which carry free.\n")

    # --- re-draftability: keeping a player the draft would hand back wastes a
    # slot. Compare each candidate's ADP against YOUR upcoming picks (order
    # from the 2026 draft when published; estimated middle slot otherwise).
    my_picks, slot_est = upcoming_picks(lg, uid)
    kept_adps = league_kept_adps(prev_id, tbl, totals, season, keys, fb, lg,
                                 current_id=league_2026_id)

    def effective_pick(adp):
        """Where a player with this global ADP actually goes IN THIS DRAFT.

        Global ADP comes from leagues where nobody is kept. Here, 12 teams
        retain 5 players each, so ~60 of the best players never reach the
        board and everyone behind them slides EARLIER by the number of
        kept players ahead of them. Comparing raw ADP to a pick number —
        which is what this did until 8/11 — systematically overstates who
        will still be there, and the error grows the deeper you go. It
        told John that Derrick Henry (adp 74) would be reclaimable at
        pick 65 when roughly 30 kept players sit ahead of him."""
        ahead = sum(1 for a in kept_adps if a < adp)
        return max(1, adp - ahead)

    def redraft_at(p):
        """(overall_pick, round) of your LATEST pick where p is likely still
        on the board — the cheapest slot that reclaims him. None = won't return
        before your first pick."""
        adp, _ = _adp(p, season, keys, fb)
        if not adp:
            return None
        eff = effective_pick(adp)
        teams_n = lg.get("total_rosters") or 12
        for n in reversed(my_picks):
            if eff >= n + 3:
                return n, (n - 1) // teams_n + 1
        return None

    if my_picks:
        note = " (slot estimated — order not published)" if slot_est else ""
        shown = ", ".join(str(n) for n in my_picks[:6])
        more = ", ..." if len(my_picks) > 6 else ""
        print(f"   your remaining picks{note}: {shown}{more}"
              f"   [{len(my_picks)} left]\n")
    else:
        # SAY IT. Printing nothing where a pick list used to be reads as
        # "no picks worth mentioning", not "this draft is over"; the whole
        # re-draftable analysis below is retrospective once it is.
        print("   this draft is DONE — nothing below is a live plan. The "
              "re-draftable\n   prices are what the market WOULD have "
              "charged, kept for next year.\n")
    if kept_adps:
        print(f"   keeper depletion: ~{len(kept_adps)} players league-wide "
              f"never reach this draft, so a global ADP of 75 actually goes "
              f"around pick {max(1, 75 - sum(1 for a in kept_adps if a < 75))}. "
              f"'re-draftable' below is adjusted for that.\n")

    def show(title, picks, from_pool, max_qb=1):
        suffix = "  — RETENTION LOCKED; verbs below are what happened" if locked else ""
        print(f"   {title}{suffix}:")
        for pr, p in picks:
            adp, exact = _adp(p, season, keys, fb)
            adp_s = f"  adp {adp:.0f}{'' if exact else 'r'}" if adp else ""
            rd = redraft_at(p)
            tag = f"   <- likely re-draftable at ~pick {rd[0]} (rd {rd[1]})" if rd else ""
            # KEEP is a recommendation and reads like an instruction. Once the
            # window has closed it is neither — say which of the two it is.
            verb = "KEEP" if not locked else (
                "KEPT" if str(p) in retained else "PASS")
            print(f"     {verb}  {pr:>6.1f}{adp_s}  {name_of(p, tbl)}{tag}")
        chosen = {p for _, p in picks}
        bubble = [(pr, p) for pr, p in from_pool if p not in chosen][:3]
        for pr, p in bubble:
            rd = redraft_at(p)
            gone = "" if rd else "   <- won't return before your first pick"
            print(f"     next  {pr:>6.1f}  {name_of(p, tbl)}{gone}")
        # SWAP advisory — the Moore-over-Evans logic: when a kept player can be
        # reclaimed LATER in the draft than a close-behind candidate, keeping
        # the scarcer one and reclaiming the other preserves more total value
        # (upside: retain both). Respects the QB cap. Advisory only; your call.
        qb_kept = sum((tbl.get(p) or {}).get("position") == "QB" for _, p in picks)
        for pr, p in picks:
            rd_p = redraft_at(p)
            if not rd_p:
                continue
            p_is_qb = (tbl.get(p) or {}).get("position") == "QB"
            for qr, q in bubble:
                q_is_qb = (tbl.get(q) or {}).get("position") == "QB"
                if q_is_qb and qb_kept >= max_qb and not p_is_qb:
                    continue  # swapping q in would break the QB cap
                rd_q = redraft_at(q)
                n_q = rd_q[0] if rd_q else -1
                if n_q < rd_p[0] - 12 and qr >= pr - 75:
                    back = (f"reclaimable at ~pick {n_q}" if rd_q
                            else "NOT reclaimable")
                    print(f"     SWAP? keep {name_of(q, tbl).split(' (')[0]} "
                          f"({qr:.0f}, {back}) over "
                          f"{name_of(p, tbl).split(' (')[0]} ({pr:.0f}) — "
                          f"{name_of(p, tbl).split(' (')[0]} waits until "
                          f"~pick {rd_p[0]}; upside is keeping both")
                    break

    show("keepers (3, max 1 QB)", keep_vets, vets)
    print()
    show("drafted-rookie keepers (2, max 1 QB)", keep_rookies, rookies)

    # RECONCILIATION. The two show() blocks print the model's optimal set.
    # Anything he actually retained that the model did not pick never appeared
    # anywhere except under "next", which reads as "passed over" — the exact
    # inversion of the truth for DJ Moore.
    if locked:
        modeled = {str(p) for _, p in keep_vets} | {str(p) for _, p in keep_rookies}
        extra = [p for p in retained if p not in modeled and p not in now_taxi]
        if extra:
            extra.sort(key=lambda p: -totals.get(p, 0.0))
            print("\n   RETAINED but not in the model's set — these are on your"
                  " roster right now:")
            for p in extra:
                print(f"     HELD  {totals.get(p, 0.0):>6.1f}  {name_of(p, tbl)}")
            print("     (the model re-solves against today's pool; the window"
                  " closed 7/1, so treat its picks as hindsight, not advice)")

    if taxi:
        print("\n   taxi (2025 riders — a player may sit on taxi ONLY in the"
              " season he was drafted):")
        for p in taxi:
            if str(p) in now_taxi:
                where = "still on taxi — carries free, cannot be started"
            elif str(p) in retained:
                where = "CARRIED OVER — occupies an active roster spot now, not free"
            else:
                where = "no longer on your roster"
            print(f"     {totals.get(p, 0.0):>6.1f}  {name_of(p, tbl)}   <- {where}")
    else:
        print("\n   taxi: none listed on 2025 roster")

    marg = [pr for pr, _ in keep_vets] + [pr for pr, _ in keep_rookies]
    print(f"\n   total kept projection: {sum(marg):.1f} pts across {len(marg)} slots")


LG04_2026 = "9000000000000000017"
LG04_2025 = "9000000000000000012"  # 2026 league has previous_league_id null;
                                       # the 2025 season lives in metadata.copy_from_league_id


def analyze_priced(league_2026_id=LG04_2026, prev_id=LG04_2025):
    """
    LG04 rule: keeping costs the round the player was drafted last year.
    Keeper value = proj(player) - proj(typical player available at that round's
    pick), where 'typical' = players whose ADP sits near the round's midpoint
    overall pick (draft order for 2026 isn't set, so midpoint is the estimate —
    stated, not hidden). Positive surplus = the keep beats using the pick;
    the best keep is the biggest surplus, NOT the best player.
    Undrafted 2025 players (waiver adds) have no defined cost under this rule —
    they print flagged; confirm with the commissioner what they cost.
    """
    lg = get(f"league/{league_2026_id}")
    prev = get(f"league/{prev_id}")
    if not lg or not prev:
        raise SystemExit("league lookup failed")
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    teams = lg.get("total_rosters") or 12
    tbl = players()

    uid = get(f"user/{USERNAME}")["user_id"]
    rosters = get(f"league/{prev_id}/rosters") or []
    mine = next((r for r in rosters if r.get("owner_id") == uid), None)
    if not mine:
        raise SystemExit("no roster of yours in the 2025 LG04 league")

    from battle_rhythm.draft_helper import resolve_draft
    _pd, picks = resolve_draft(prev)
    drafted_round = {p["player_id"]: p.get("round") for p in picks if p.get("player_id")}

    totals = season_projection_totals(season, scoring)

    # what a pick in round R typically buys: mean projection of players whose
    # redraft ADP falls inside that round's overall-pick window
    adp_pool = []
    from battle_rhythm.draft_helper import weekly_projections, _pick
    for pid, wkstats in weekly_projections(season, 1).items():
        adp = _pick(wkstats or {}, REDRAFT_ADP_KEYS)
        if adp and totals.get(pid):
            adp_pool.append((adp, totals[pid]))
    adp_pool.sort()

    def round_buys(rnd):
        lo, hi = (rnd - 1) * teams + 1, rnd * teams
        window = [pr for adp, pr in adp_pool if lo <= adp <= hi]
        return sum(window) / len(window) if window else 0.0

    print(f"\n══ {lg.get('name')} — keeper value (cost = round drafted in 2025)")
    print("   surplus = 2026 proj − what that round's pick typically buys (ADP window)\n")
    rows = []
    for p in (mine.get("players") or []):
        rnd = drafted_round.get(p)
        proj = totals.get(p, 0.0)
        if rnd:
            surplus = proj - round_buys(rnd)
            rows.append((surplus, proj, rnd, p, False))
        else:
            rows.append((None, proj, None, p, True))
    rows.sort(key=lambda r: (r[0] is None, -(r[0] or 0)))
    for surplus, proj, rnd, p, undrafted in rows:
        if undrafted:
            print(f"     ?        proj {proj:>6.1f}  undrafted 2025 — cost rule unknown"
                  f"  {name_of(p, tbl)}")
        else:
            tag = "KEEP?" if surplus == max(r[0] for r in rows if r[0] is not None) else "     "
            print(f"     {tag} rd {rnd:>2}  proj {proj:>6.1f}  surplus {surplus:>+7.1f}"
                  f"  {name_of(p, tbl)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    board_mode = "--board" in args
    kept_mode = "--kept" in args
    args = [a for a in args if a not in ("--board", "--kept")]
    if args and args[0] == "lg04":
        analyze_priced()
    elif kept_mode:
        for lid in (args or HYBRIDS):
            show_keepers(lid)
    elif board_mode:
        for lid in (args or HYBRIDS):
            adjusted_board(lid)
    else:
        for lid in (args or HYBRIDS):
            analyze(lid)
