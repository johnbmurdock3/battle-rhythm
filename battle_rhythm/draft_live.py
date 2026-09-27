"""Live draft server. The board re-plans itself every time a pick lands.

    python br.py live --league lg06 [--port 8788] [--every 2] [--slot N]
                                           [--poll-ms N]   page refresh, defaults to --every

Then open http://localhost:8788. This process polls Sleeper; the page polls
this process. Nothing is written back to Sleeper -- the toolkit stays read-only
and every action is a link into the app.

WHY THIS IS NOT THE PUBLISHED CARD. An artifact page is sandboxed off the
network: it cannot reach api.sleeper.app, so it can never see a pick land. The
pre-draft card is a plan; this is the live one, and it has to run where the
network is.

WHAT CHANGES AS PICKS LAND. Three things, and the third is the point:
  1. drafted players leave the pool;
  2. replacement level rises, because a starting slot someone else filled is
     demand the league no longer has -- so VORP is recomputed against REMAINING
     demand, never total (see replacement_levels, which is the one
     implementation and documents what happens when a second copy disagrees);
  3. the plan is re-simulated over the picks that are actually left, with every
     seat's real roster in hand. Before the draft the room is a guess; by round
     six it is mostly known, so the advice gets sharper, not staler.
"""
import collections, json, math, os, random, sys, threading, time

from battle_rhythm import ext_tiers as _ext
from battle_rhythm.draft_helper import (
    IDP_POS, SLOT_ALIAS, _adp, adp_keys_for, league_draft, my_roster_id,
    my_owned_next_picks, my_slot, players, replacement_levels,
    season_projection_totals,
)

FLEX_SETS = {"FLEX": ("RB", "WR", "TE"), "WRRB_FLEX": ("RB", "WR"),
             "REC_FLEX": ("WR", "TE"), "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
             "IDP_FLEX": IDP_POS}
# MEASURED, not guessed. Fitted to 241 priced picks from LG01 -- the
# room sharing the most managers with the weekend leagues -- comparing an
# additive model (spread constant in picks) against a multiplicative one
# (spread proportional to ADP), with the likelihood computed in pick space so
# the lognormal carries its Jacobian. Multiplicative won by 82 log units, and
# by 62 and 55 in the other two rooms. The shape was right; the constant was
# close (0.220 guessed against 0.205 measured).
#
# The per-position split is the part worth having: quarterbacks move about 45%
# more than receivers, so a quarterback tier is less safe than the flat number
# implied. Caveat on transfer -- only 3 of LG02' 14 managers appear in the
# calibration room, and it drafts off dynasty ADP.
SIGMA = 0.205
SIGMA_POS = {"QB": 0.266, "RB": 0.185, "WR": 0.180, "TE": 0.188}


def sig(pos=None):
    return SIGMA_POS.get(pos, SIGMA)
BENCH_CREDIT = 0.35

# How many players the snapshot carries. The LIVE server re-plans every pick
# off the full pool, so it only ever needed enough rows to look at -- 120 was
# plenty. The FROZEN card cannot re-plan: it is one pre-draft snapshot, and a
# 14x13 room drafts 182 players. Measured on LG02 9/5, every one of the
# 120 was gone by pick 128, so the fallback advised nothing for the last four
# turns -- silently, with a full-looking board that was entirely drafted. That
# is the exact scenario the frozen card exists for: the live server died on a
# 60-second clock with autopick on. Carry the whole draft plus slack.
BOARD_ROWS = 400


# ─────────────────────────────────────────────────────────── league shape
def shape(lg):
    """(required-slot list, flex slot list, bench count, teams, rounds)."""
    rp = list(lg.get("roster_positions") or [])
    req = [SLOT_ALIAS.get(p, p) for p in rp
           if p not in FLEX_SETS and p not in ("BN", "IR", "TAXI")]
    flex = [FLEX_SETS[p] for p in rp if p in FLEX_SETS]
    bench = sum(1 for p in rp if p == "BN")
    teams = int(lg.get("total_teams") or (lg.get("settings") or {}).get("num_teams") or 10)
    return req, flex, bench, teams, len(req) + len(flex) + bench


def demand_per_team(req, flex):
    """{pos: starters per team}, flex spread over the positions it accepts."""
    d = collections.Counter(req)
    for opts in flex:
        for p in opts:
            d[p] += 1.0 / len(opts)
    return dict(d)


# ─────────────────────────────────────────────────────────── static pool
def build_pool(lg, season):
    """Every player with a projection, priced under THIS league's scoring."""
    tbl = players()
    scoring = lg.get("scoring_settings") or {}
    totals = season_projection_totals(season, scoring)
    keys, fb = adp_keys_for(lg.get("roster_positions"), False)
    req, flex, _, _, _ = shape(lg)
    seats = set(req) | {p for opts in flex for p in opts}
    out = {}
    for pid, pts in totals.items():
        p = tbl.get(pid) or {}
        pos = SLOT_ALIAS.get(p.get("position"), p.get("position"))
        if pos not in seats or not pts or pts <= 0:
            continue
        try:
            adp, _ = _adp(pid, season, keys, fb)
        except Exception:
            adp = None
        out[pid] = {"pid": pid, "name": p.get("full_name") or pid, "pos": pos,
                    "team": p.get("team"), "proj": round(float(pts), 1),
                    "adp": float(adp) if isinstance(adp, (int, float)) and adp < 400 else 999.0,
                    "inj": p.get("injury_status")}
    info = _bonus_overlay(out)
    if info:
        print(f"   bonus overlay: {info[0]} applied to {info[1]} of {info[2]} "
              f"players (per-game rules the projection feed omits)")
    return out



# ─────────────────────────────────────────── the bonus overlay (IDP league)
# data/measured FIRST. out/ is gitignored render by design -- "nothing here is
# ever an input to a decision" (CLAUDE.md) -- and on 9/8 this overlay made an
# out/fz file an input to every value on the live board. Cleaning out/ would
# have silently reverted the server to unadjusted numbers with no error. The
# counts come from 18 weeks of 2025 game logs only one machine can fetch, so
# they are measured truth. out/fz stays as a fallback for a board built before
# the move.
BONUS_OVERLAY = (("data", "measured", "lg06_bonus_2025.json"),
                 ("out", "fz", "board_adj_rate.json"),
                 ("out", "fz", "board_adj.json"))


def _bonus_overlay(pool):
    """Add the per-game bonus rules Sleeper never projects, if a board that
    prices them exists. No file, no change.

    LG06 pays nine per-GAME thresholds -- 100/200 receiving and
    rushing yards, 300/400 passing, a 10-tackle game, a 2-sack game, 3 passes
    defensed. A season projection cannot say how often a player crossed one,
    so the feed omits them and this server scored them at zero, while the
    pre-draft plan (out/fz) counted them off real 2025 game logs. Measured
    9/8: Cook +95, JSN +90, Henry +85, Campbell +45, Hutchinson +15.

    Two tools, one question, opposite answers. On 9/8 this server recommended
    a tight end in round 3 from a late seat while the card -- built on the
    same league's real scoring -- said take a third running back, because the
    bonuses are worth far more to the marginal RB than to the first TE. That
    is the defect class this repo keeps shipping, and a draft clock is not
    when to work out which screen to believe.

    ADDED TO `proj`, NOT TO `vorp`, and that is the whole point. reprice()
    rebuilds replacement from proj on every poll, so the bars rise with the
    pool -- the replacement-level man earns bonuses too, fewer, which is why
    the top of the board still gains. Adding to vorp would skip the bars and
    overstate everyone by roughly the bar's own move (RB +11, LB +28).

    Guarded: leagues without the file are untouched, so LG04, LG02,
    the Hybrids, LG01 and Best Ball see exactly what they saw before.
    Delete the file to revert.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for parts in BONUS_OVERLAY:
        name = parts[-1]
        path = os.path.join(here, os.pardir, *parts)
        if not os.path.exists(path):
            continue
        try:
            adj = json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
        hit = 0
        for pid, row in adj.items():
            b = row.get("bonus_2025")
            p = pool.get(pid)
            if p and b:
                p["proj"] = round(p["proj"] + float(b), 1)
                p["bonus"] = round(float(b), 1)
                hit += 1
        return (name, hit, len(pool))
    return None

# ───────────────────────────────────────────────────── live re-pricing
def reprice(pool, taken, demand, teams):
    """VORP against REMAINING demand. A slot someone else already filled is
    demand the league no longer has, so replacement rises as the draft runs."""
    gone = collections.Counter(pool[p]["pos"] for p in taken if p in pool)
    avail = [p for pid, p in pool.items() if pid not in taken]
    by_pos = collections.defaultdict(list)
    for p in avail:
        by_pos[p["pos"]].append(p["proj"])
    lv = replacement_levels(by_pos, demand, teams, gone_by_pos=gone)
    for p in avail:
        p["vorp"] = round(p["proj"] - lv.get(p["pos"], 0.0), 1)
    return avail, lv


# ──────────────────────────────────────────────────────────── the planner
def mkt(p):
    """Market position for the planner. One definition, shared with
    draft_helper -- see ext_tiers.market_pos for the measurement and for why
    DEF and K keep ADP. 999 here means "treat an unknown as never surviving",
    which is this module's convention; draft_helper uses None for the same
    idea in its own predicates."""
    return _ext.market_pos(p, 999.0)


def survives(adp, pick, pos=None):
    if adp >= 400 or pick <= 0:
        return 1.0
    z = math.log(pick / adp) / sig(pos)
    return 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))


def lineup_slots(team, req, flex, bench=0):
    """[(slot label, player or None)] -- every seat on the roster, in order.

    The panel used to show one chip per REQUIRED position and nothing else,
    so a league starting RB2 + FLEX2 rendered four chips for six seats a
    back can occupy, and the bench did not exist on screen at all. You
    cannot read "how many picks do I still owe" off that, which is the one
    question the panel is there to answer late in a draft.

    Assignment mirrors lineup_vorp exactly -- required slots first, best
    VORP into each, then flex from whoever is spare, then bench by value.
    If the two ever disagree the panel is lying about which players are
    actually scoring, so they share this shape deliberately.
    """
    byp = collections.defaultdict(list)
    for p in team:
        byp[p["pos"]].append(p)
    for v in byp.values():
        v.sort(key=lambda p: -p.get("vorp", 0))
    used, out, seen = set(), [], collections.Counter()
    total = collections.Counter(req)
    for pos in req:
        seen[pos] += 1
        label = pos if total[pos] == 1 else f"{pos}{seen[pos]}"
        pick = next((p for p in byp[pos] if id(p) not in used), None)
        if pick:
            used.add(id(pick))
        out.append((label, pick))
    for i, opts in enumerate(flex, 1):
        label = "FLEX" if len(flex) == 1 else f"FLEX{i}"
        pool = [p for p in team if id(p) not in used and p["pos"] in opts]
        pick = max(pool, key=lambda p: p.get("vorp", 0)) if pool else None
        if pick:
            used.add(id(pick))
        out.append((label, pick))
    spare = sorted((p for p in team if id(p) not in used),
                   key=lambda p: -p.get("vorp", 0))
    for i in range(bench):
        out.append((f"BN{i + 1}", spare[i] if i < len(spare) else None))
    for extra in spare[bench:]:          # over-full is a real state; show it
        out.append(("OVER", extra))
    return out


def lineup_vorp(team, req, flex):
    byp = collections.defaultdict(list)
    for p in team:
        byp[p["pos"]].append(p)
    for v in byp.values():
        v.sort(key=lambda p: -p["vorp"])
    used, total, cur = set(), 0.0, collections.Counter()
    for pos in req:
        pool = [p for p in byp[pos] if p["pid"] not in used]
        if pool:
            best = pool[0]
            used.add(best["pid"]); total += best["vorp"]
        cur[pos] += 1
    for opts in flex:
        pool = [p for p in team if p["pid"] not in used and p["pos"] in opts]
        if pool:
            best = max(pool, key=lambda p: p["vorp"])
            used.add(best["pid"]); total += best["vorp"]
    return total


# Cover for the weeks a starter is simply not available. A bye is not a risk,
# it is a certainty: with exactly two receivers in a two-receiver league there
# is a guaranteed week with an unfillable slot, and the optimiser will happily
# leave you there because a bench receiver scores no points in expectation.
# Positions that can be covered out of the flex need less of this.
BYE_COVER = {"WR": 1, "RB": 1}      # everything else: 0, via .get below


def owed(roster, req, flex, depth=False):
    """Slots still to fill, as position-sets.

    depth=False is the feasibility question -- can I still field a legal
    lineup -- and must count starters only, or the endgame check refuses
    picks it should allow. depth=True is the planning question and includes
    bye cover, which gets assigned to late picks like any other slot.
    """
    have = collections.Counter(roster)
    out = []
    for pos, n in collections.Counter(req).items():
        for _ in range(max(0, n - have[pos])):
            out.append((pos,))
    # Allocate spares to flex slots one at a time. Recomputing the same spare
    # count per slot marks EVERY flex filled as soon as one spare exists --
    # LG04 starts two, and read as complete a man short.
    spare = {q: max(0, have[q] - req.count(q))
             for opts in flex for q in opts}
    for opts in flex:
        took = next((q for q in opts if spare.get(q, 0) > 0), None)
        if took is None:
            out.append(tuple(opts))
        else:
            spare[took] -= 1
    if depth:
        for pos in set(req):
            extra = BYE_COVER.get(pos, 0)
            room = req.count(pos) + extra - have[pos]
            for _ in range(max(0, min(extra, room))):
                out.append((pos,))
    return out


def expected_best(by_pos, want, pick):
    """E[value of the best player at these positions still there at `pick`].

    Not max(vorp * P(available)) -- that prefers a mediocre certainty to a
    strong maybe and understates a position with several good options, any
    one of which will do.
    """
    c = []
    for pos in want:
        c.extend(by_pos.get(pos, ()))
    c.sort(key=lambda p: -p["vorp"])
    total, left = 0.0, 1.0
    for p in c[:35]:
        pa = survives(mkt(p), pick, p["pos"])
        total += p["vorp"] * pa * left
        left *= (1.0 - pa)
        if left < 1e-4:
            break
    return total


def _hungarian(cost):
    """Minimum-cost assignment of every row to a distinct column. O(n^3).

    Rows are roster slots, columns are my remaining picks. This has to be
    solved, not approximated: taking the best remaining cell each time is
    what pushed receivers to pick 145 while a kicker sat at 76. Kicker and
    defender value barely decays, so a greedy pass hands them early picks
    they lose nothing by giving up, and the positions that DO decay pay for
    it. Only a real assignment sees that trade.
    """
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, -1
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    return {p[j] - 1: j - 1 for j in range(1, m + 1) if p[j]}


def assign(avail, mypicks, roster, req, flex):
    """Match owed roster slots to my remaining picks, maximising the total.

    Picking one turn at a time is what makes a draft agent take six running
    backs and then start a replacement-level receiver: every single decision
    looks right and the position quietly empties. Planning the whole rest of
    the draft is what stops it -- but only if the plan is actually optimal,
    which is why this solves the assignment instead of walking sorted cells.
    """
    o = owed(roster, req, flex, depth=True)
    if not o or not mypicks:
        return {}
    by_pos = collections.defaultdict(list)
    for p in avail:
        by_pos[p["pos"]].append(p)
    if len(o) > len(mypicks):            # cannot fill everything; keep the best
        o = sorted(o, key=lambda w: -max(expected_best(by_pos, w, k)
                                         for k in mypicks))[:len(mypicks)]
    # A position whose value does not decay -- kicker is 21 points at pick 3
    # and at pick 98 -- leaves the solver indifferent about WHERE to put it,
    # and an indifferent solver returns an arbitrary pick. That is how a
    # kicker landed at 63. Rewarding later picks by a hair breaks the tie
    # toward the end for flat slots and leaves steep ones alone, since their
    # decay dwarfs it.
    cost = [[-(expected_best(by_pos, w, k) + 0.02 * i)
             for i, k in enumerate(mypicks)] for w in o]
    return {mypicks[j]: o[i] for i, j in _hungarian(cost).items() if i < len(o)}


# How many of a position is it ever worth owning. This is not a style choice:
# a third quarterback in a one-QB league cannot start, so his VORP -- which can
# be large -- is entirely unrealisable. Bench picks are chosen on VORP, so
# without a cap the tail of the draft stacks backups at exactly the positions
# where a backup is worthless. A rehearsal draft ended QB3/LB3 before this.
# Depth is only worth owning where a backup can actually enter the lineup.
# Running backs and receivers rotate through the flex and absorb byes and
# injuries, so depth there is real. A second kicker or a fifth team defense is
# a wasted roster spot. Defaulting an unlisted position to the flex allowance
# is how LG02 -- which starts one DEF -- came out entitled to five.
DEPTH = {"RB": 4, "WR": 4, "QB": 1, "TE": 1, "DL": 1, "LB": 1, "DB": 1,
         "K": 0, "DEF": 0}
DEPTH_DEFAULT = 1


def caps(req, bench):
    c = collections.Counter()
    for pos in set(req):
        c[pos] = req.count(pos) + DEPTH.get(pos, DEPTH_DEFAULT)
    return c


def simulate(avail, picks_made, my_picks, my_roster, seat_rosters, req, flex,
             bench, teams, total_rounds, rng, forced=None, my_team=()):
    """Play out the rest of the room once. Returns [(my_pick_no, player)]."""
    order = sorted(avail,
                   key=lambda p: mkt(p) * math.exp(rng.gauss(0, sig(p["pos"]))))
    taken, cap = set(), caps(req, bench)
    rosters = {s: collections.Counter(v) for s, v in seat_rosters.items()}
    mine, mypos = [], collections.Counter(my_roster)
    myteam = list(my_team)      # players already drafted count toward my lineup
    myset = set(my_picks)
    for n in range(picks_made + 1, teams * total_rounds + 1):
        rnd = (n - 1) // teams + 1
        seat = (n - 1) % teams + 1 if rnd % 2 else teams - (n - 1) % teams
        left_for_seat = sum(1 for x in range(n, teams * total_rounds + 1)
                            if ((x - 1) % teams + 1 if ((x - 1) // teams + 1) % 2
                                else teams - (x - 1) % teams) == seat)

        def ok(roster, pos):
            if roster[pos] >= cap.get(pos, 2):
                return False
            r2 = collections.Counter(roster); r2[pos] += 1
            return left_for_seat - 1 >= len(owed(r2, req, flex))

        if n in myset:
            cand = [p for p in avail if p["pid"] not in taken and ok(mypos, p["pos"])]
            if not cand:
                continue
            want = assign(cand, [k for k in my_picks if k >= n], mypos, req, flex).get(n)
            if forced:
                want = forced.get((n - 1) // teams + 1) or want
            pool = [p for p in cand if p["pos"] in want] if want else cand
            pool = pool or cand
            pick = max(pool, key=(lambda p: p["vorp"]) if want
                       else (lambda p: p["vorp"] * BENCH_CREDIT))
            mine.append((n, pick)); mypos[pick["pos"]] += 1; myteam.append(pick)
        else:
            r = rosters.setdefault(seat, collections.Counter())
            pick = next((p for p in order if p["pid"] not in taken and ok(r, p["pos"])), None)
            if pick is None:
                continue
            r[pick["pos"]] += 1
        taken.add(pick["pid"])
    return mine, lineup_vorp(myteam, req, flex)


def advise(avail, picks_made, my_picks, my_roster, seat_rosters, req, flex,
           bench, teams, total_rounds, n=90, seed=None, my_team=()):
    """Run the rest of the draft n times; report what I take and how often."""
    rng = random.Random(seed if seed is not None else picks_made * 7919 + 13)
    took = collections.defaultdict(collections.Counter)
    scores = []
    for _ in range(n):
        mine, sc = simulate(avail, picks_made, my_picks, my_roster, seat_rosters,
                            req, flex, bench, teams, total_rounds, rng,
                            my_team=my_team)
        scores.append(sc)
        for k, p in mine:
            took[k][p["pid"]] += 1
    by = {p["pid"]: p for p in avail}
    out = []
    for k in my_picks:
        rows = [{"pct": round(100 * c / n),
                 **{f: by[pid][f] for f in ("name", "pos", "team", "vorp", "adp", "inj")}}
                for pid, c in took[k].most_common(4) if c / n >= 0.04]
        out.append({"pick": k, "round": (k - 1) // teams + 1, "targets": rows})
    return out, (round(sum(scores) / len(scores)) if scores else 0)


# tiers ---------------------------------------------------------------------
def tier_up(rows, depth=26):
    """Split a position into tiers wherever the drop between neighbours is
    large relative to the ordinary step at that position.

    Tiers are the honest unit of a draft decision. Inside one the choice
    barely matters; across one it does. A flat ranking hides that -- it says
    RB7 beats RB8 without saying whether the difference is one point or
    thirty. The threshold is relative because positions have different
    shapes: the median step between running backs here is 9 points and
    between kickers 1.8, so any fixed cutoff would either make every kicker
    his own tier or lump every back into one.
    """
    rows = sorted(rows, key=lambda p: -p["vorp"])[:depth]
    if len(rows) < 3:
        return [rows] if rows else []
    gaps = [rows[i]["vorp"] - rows[i + 1]["vorp"] for i in range(len(rows) - 1)]
    med = sorted(gaps)[len(gaps) // 2] or 1.0
    cut = max(6.0, 1.7 * med)
    out, cur = [], [rows[0]]
    for i, g in enumerate(gaps):
        if g >= cut:
            out.append(cur)
            cur = []
        cur.append(rows[i + 1])
    out.append(cur)
    return [t for t in out if t]


def tier_watch(avail, next_pick):
    """Per position: the tier on the clock, and whether it survives my turn.

    This is the answer to "fill the empty slot, or take the value". A tier
    nobody else wants -- six defensive backs inside fifteen points of each
    other, none drafted before pick 145 -- costs nothing to defer. A tier
    about to break costs the whole gap down to the next one. `cost_to_wait`
    is that number: what skipping this position now is expected to cost by
    my next turn.
    """
    by = collections.defaultdict(list)
    for p in avail:
        by[p["pos"]].append(p)
    out = {}
    for pos, rows in by.items():
        ts = tier_up(rows)
        if not ts:
            continue
        top = ts[0]
        nxt = ts[1] if len(ts) > 1 else []
        if not next_pick:                    # no turn left to measure against
            out[pos] = {"n": len(top), "hi": round(top[0]["vorp"], 1),
                        "lo": round(top[-1]["vorp"], 1), "next_tier": None,
                        "drop": 0.0, "hold": None, "cost_to_wait": None,
                        "names": [q["name"] for q in top[:5]]}
            continue
        gone = 1.0
        for q in top:
            gone *= (1.0 - survives(mkt(q), next_pick, q["pos"]))
        hold = 1.0 - gone                       # P(at least one survives)
        drop = (top[-1]["vorp"] - nxt[0]["vorp"]) if nxt else 0.0
        out[pos] = {
            "n": len(top),
            "hi": round(top[0]["vorp"], 1), "lo": round(top[-1]["vorp"], 1),
            "next_tier": round(nxt[0]["vorp"], 1) if nxt else None,
            "drop": round(drop, 1),
            "hold": round(hold, 3),
            "cost_to_wait": round(drop * (1.0 - hold), 1),
            "names": [q["name"] for q in top[:5]],
        }
    return out


# rehearsal mode ------------------------------------------------------------
class Sim:
    """A fake draft that lands picks on a timer, so the live path can be run
    end to end without waiting for Wednesday.

    Everything downstream of this class is the real code: the same refresh(),
    the same repricing, the same planner, the same page. Only the fetch is
    replaced, because the untested path was "picks arrive and everything
    updates", not "urllib works".

    The room drafts off ADP with the same reach noise the planner assumes. On
    my seat it stalls for three times as long, so the ON THE CLOCK state is
    actually observable, then takes the plan's own top target and moves on.
    """

    def __init__(self, lg, pool, slot, teams, rounds, speed=2.0, rng=None):
        self.lg, self.pool, self.slot = lg, pool, slot
        self.teams, self.rounds, self.speed = teams, rounds, speed
        self.rng = rng or random.Random(20260909)
        self.picks, self.t0, self.taken = [], time.time(), set()
        self.order = sorted(pool.values(),
                            key=lambda p: mkt(p) * math.exp(
                                self.rng.gauss(0, sig(p["pos"]))))
        self.advise_cb = None

    def seat_at(self, n):
        r = (n - 1) // self.teams + 1
        return ((n - 1) % self.teams + 1 if r % 2
                else self.teams - (n - 1) % self.teams)

    def due(self):
        """Picks that should have landed by now, with a stall on my turn."""
        elapsed, n, spent = time.time() - self.t0, 0, 0.0
        while n < self.teams * self.rounds:
            cost = self.speed * (3.0 if self.seat_at(n + 1) == self.slot else 1.0)
            if spent + cost > elapsed:
                break
            spent += cost
            n += 1
        return n

    def advance(self):
        while len(self.picks) < self.due():
            n = len(self.picks) + 1
            seat = self.seat_at(n)
            pick = None
            if seat == self.slot and self.advise_cb:
                pick = self.advise_cb()
            if pick is None:
                pick = next((q for q in self.order if q["pid"] not in self.taken), None)
            if pick is None:
                break
            self.taken.add(pick["pid"])
            # no roster_id: in a rehearsal the only true identifier is the
            # seat, and a fake roster_id collides with a real one
            self.picks.append({"pick_no": n, "draft_slot": seat,
                               "roster_id": None, "player_id": pick["pid"]})

    def snapshot(self):
        self.advance()
        done = len(self.picks) >= self.teams * self.rounds
        draft = {"status": "complete" if done else "drafting",
                 "settings": {"rounds": self.rounds, "teams": self.teams},
                 "draft_order": None, "season": "2026"}
        return self.lg, draft, list(self.picks)


# ──────────────────────────────────────────────────────────── live state
class Live:
    def __init__(self, league_id, slot_override=None, every=5, mocks=90, sim=None):
        self.lid, self.every, self.mocks = league_id, every, mocks
        self.slot_override = slot_override
        self.override_source = "you set it" if slot_override else None
        self.sim = sim
        self.last_targets = {}      # pick -> [names the plan named last refresh]
        self.lock = threading.Lock()
        self.snap = {"status": "starting", "picks_made": -1}
        self.pool = None
        self.err = None

    def refresh(self, force=False):
        lg, draft, picks = self.sim.snapshot() if self.sim else league_draft(self.lid)
        season = str(lg.get("season") or draft.get("season") or "2026")
        if self.pool is None:
            self.pool = build_pool(lg, season)
        req, flex, bench, teams, rounds = shape(lg)
        rounds = int((draft or {}).get("settings", {}).get("rounds") or rounds)
        demand = demand_per_team(req, flex)

        n = len(picks)
        with self.lock:
            if not force and n == self.snap.get("picks_made"):
                # Nothing new to price, but the poll DID succeed -- record that.
                # `ts` was only written after this return, so it was really a
                # last-pick-changed stamp wearing an "updated" label, and a
                # quiet room was indistinguishable from a dead server. That is
                # the one signal you need during a draft.
                self.snap["checked"] = time.strftime("%H:%M:%S")
                self.snap["ts"] = self.snap["checked"]
                self.snap["stale_picks_for"] = int(
                    time.time() - self.snap.get("picks_at", time.time()))
                return
        taken = {str(p.get("player_id")) for p in picks if p.get("player_id")}
        avail, lv = reprice(self.pool, taken, demand, teams)
        avail.sort(key=lambda p: -p["vorp"])

        seat_rosters = collections.defaultdict(collections.Counter)
        my_roster, my_team, feed = collections.Counter(), [], []
        try:
            rid = my_roster_id(self.lid)
        except Exception:
            rid = None
        published = my_slot(draft)
        slot = self.slot_override or published
        slot_source = (self.override_source if self.slot_override
                       else ("Sleeper draft order" if published else None))
        for pk in picks:
            pid = str(pk.get("player_id") or "")
            p = self.pool.get(pid)
            s = pk.get("draft_slot") or pk.get("roster_id")
            if p and s:
                seat_rosters[int(s)][p["pos"]] += 1
            mine = (rid is not None and pk.get("roster_id") == rid) or \
                   (slot and pk.get("draft_slot") == slot)
            if p and mine:
                my_roster[p["pos"]] += 1
                my_team.append({**p, "vorp": round(p["proj"] - lv.get(p["pos"], 0.0), 1)})
            feed.append({"no": pk.get("pick_no"), "slot": s, "mine": bool(mine),
                         "name": (p or {}).get("name", "—"),
                         "pos": (p or {}).get("pos", "?"),
                         "team": (p or {}).get("team")})

        my_picks = []
        if rid is not None:
            try:
                my_picks = [k for k, _ in my_owned_next_picks(draft, n, rid, 40)]
            except Exception:
                my_picks = []
        if not my_picks and slot:
            my_picks = [(r - 1) * teams + (slot if r % 2 else teams - slot + 1)
                        for r in range(1, rounds + 1)]
            my_picks = [k for k in my_picks if k > n]

        # MUST run before advise() and tier_watch(): mkt() reads bc_rank and
        # both plan off it. Annotating after them leaves mkt() falling back
        # to ADP for the whole plan while the board still SHOWS the tiers --
        # working display, silently unchanged recommendations, no error.
        _hit, _tot = _ext.annotate(avail)
        self.ext_match = (_hit, _tot)

        plan, exp = ([], 0)
        if my_picks:
            plan, exp = advise(avail, n, my_picks, my_roster, seat_rosters, req,
                               flex, bench, teams, rounds, self.mocks,
                               my_team=my_team)

        tiernum, _by = {}, collections.defaultdict(list)
        for q in avail:
            _by[q["pos"]].append(q)
        for _rows in _by.values():
            for _i, _t in enumerate(tier_up(_rows), 1):
                for _q in _t:
                    tiernum[_q["pid"]] = _i

        # A target does not "disappear"; it gets DRAFTED. Without saying so,
        # the plan silently reshuffles and the names change under you -- which
        # on a sixty-second clock reads as the tool being flaky rather than the
        # board moving. Compare what the plan named last time against who has
        # since come off the board.
        lost = []
        if plan:
            gone_names = {p["name"] for pid, p in self.pool.items()
                          if pid in taken}
            nxt = plan[0]
            prev = self.last_targets.get(nxt["pick"]) or []
            still = [t["name"] for t in nxt["targets"]]
            for nm in prev:
                if nm in gone_names and nm not in still:
                    lost.append(nm)
            self.last_targets = {t["pick"]: [x["name"] for x in t["targets"]]
                                 for t in plan}
        else:
            self.last_targets = {}

        with self.lock:
            self.snap = {
                "status": (draft or {}).get("status"), "picks_made": n,
                "teams": teams, "rounds": rounds, "slot": slot,
                "simulated": bool(self.sim),
                "slot_source": slot_source,
                "draft_order_published": published is not None,
                # pre_draft, pick 1 is trivially "next" -- that is not the
                # clock, and a red ON THE CLOCK banner hours early is worse
                # than no banner at all.
                "live": (draft or {}).get("status") == "drafting",
                "on_clock": bool(my_picks and my_picks[0] == n + 1
                                 and (draft or {}).get("status") == "drafting"),
                "away": (my_picks[0] - n - 1) if my_picks else None,
                "next_pick": my_picks[0] if my_picks else None,
                "slots": [{"slot": lab,
                           "name": (pl or {}).get("name"),
                           "pos": (pl or {}).get("pos"),
                           "team": (pl or {}).get("team"),
                           "vorp": (pl or {}).get("vorp")}
                          for lab, pl in lineup_slots(my_team, req, flex, bench)],
                "my_roster": dict(my_roster), "req": req,
                "flex": [list(f) for f in flex], "bench": bench,
                "owed": [list(o) for o in owed(my_roster, req, flex)],
                "expected": exp,
                "lost_targets": lost,
                "have": round(lineup_vorp(my_team, req, flex)),
                "plan": plan,
                "feed": feed[-12:][::-1],
                "board": [{**{k: p[k] for k in
                              ("name", "pos", "team", "vorp", "proj", "adp",
                               "inj", "bc_tier", "bc_rank", "bc_sd",
                               "bc_sd_rel")},
                            "tier": tiernum.get(p["pid"])}
                          for p in avail[:BOARD_ROWS]],
                "ext_match": list(getattr(self, "ext_match", (0, 0))),
                "replacement": {k: round(v, 1) for k, v in lv.items()},
                "tiers": tier_watch(avail, my_picks[0] if my_picks else 0),
                "ts": time.strftime("%H:%M:%S"),
                "checked": time.strftime("%H:%M:%S"),
                "picks_at": time.time(), "stale_picks_for": 0, "err": None,
            }

    def loop(self):
        while True:
            try:
                self.refresh()
                self.err = None
            except Exception as e:
                self.err = f"{type(e).__name__}: {e}"
                with self.lock:
                    self.snap["err"] = self.err
            time.sleep(self.every)

    def set_slot(self, n, source="you set it"):
        """Sleeper does not publish the draft order until shortly before the
        draft, so my_slot() is None right up to the point it matters. Rather
        than make the seat a restart-only flag, the page can set it."""
        self.slot_override = int(n) if n else None
        self.override_source = source if self.slot_override else None
        self.refresh(force=True)

    def state(self):
        with self.lock:
            return dict(self.snap)


# ────────────────────────────────────────────────────────────── the page
PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live draft — Battle Rhythm</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{--ground:#F6F5F1;--surface:#fff;--raise:#FBFAF7;--ink:#14181B;--body:#33393D;
--muted:#6A6E72;--faint:#8E9296;--rule:#DCD9D1;--soft:#E9E6DF;--accent:#A8331E;
--RB:#146B4C;--WR:#23578F;--TE:#8A5514;--QB:#5F3B93;--K:#6A6E72;--DL:#9E2B44;
--LB:#B85C15;--DB:#1A6E77;--good:#146B4C;--bar:#C9C5BB}
@media(prefers-color-scheme:dark){:root{--ground:#131719;--surface:#1A1F22;--raise:#20262A;
--ink:#EDEBE6;--body:#C9CCCE;--muted:#969B9F;--faint:#767B7F;--rule:#2C3337;--soft:#242B2F;
--accent:#E4694C;--RB:#4FBF8E;--WR:#6BA6E6;--TE:#D9A040;--QB:#A88AD8;--K:#969B9F;
--DL:#E4718A;--LB:#E5913F;--DB:#4FC0CC;--good:#4FBF8E;--bar:#3A4247}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--body);
font:15px/1.55 "IBM Plex Sans",system-ui,sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:0 22px 70px}
h1,h2,h3,.disp{font-family:"Barlow Condensed",sans-serif;color:var(--ink);margin:0}
.mono{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.bar{position:sticky;top:0;z-index:9;background:var(--ground);border-bottom:2px solid var(--ink);
padding:12px 0;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}
.bar h1{font-size:26px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
.bar .s{font-size:13px;color:var(--muted)}
.bar .s b{color:var(--ink)}
.clock{margin:18px 0;padding:16px 18px;border-radius:4px;border:1px solid var(--rule);
background:var(--surface)}
.clock.now{background:var(--accent);border-color:var(--accent);color:#fff}
.clock.now h2,.clock.now .lab{color:#fff}
.clock h2{font-size:23px;font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.lab{font-family:"Barlow Condensed",sans-serif;text-transform:uppercase;letter-spacing:.12em;
font-size:12px;font-weight:600;color:var(--muted)}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:30px;align-items:start}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:4px;
padding:14px 16px;margin-bottom:14px}
.panel h3{font-size:15px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
margin-bottom:8px}
.chip{font-family:"Barlow Condensed",sans-serif;text-transform:uppercase;letter-spacing:.09em;
font-size:12px;font-weight:600;padding:2px 7px;border-radius:2px;color:#fff}
.rec{display:grid;grid-template-columns:1fr 58px 66px;gap:12px;align-items:center;
padding:7px 0;border-bottom:1px solid var(--soft)}
.rec:last-child{border-bottom:none}
.rec .nm{font-size:15px;color:var(--ink);font-weight:500}
.rec .nm .t{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);margin-left:7px}
.rec .v{text-align:right;font-family:"IBM Plex Mono",monospace;color:var(--ink)}
.pctbar{display:flex;align-items:center;gap:5px}
.pctbar .tr{flex:1;height:4px;background:var(--bar);border-radius:2px;overflow:hidden}
.pctbar .fi{height:100%;background:var(--good)}
.pctbar .p{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--faint);width:24px}
.turn{padding:9px 0;border-bottom:1px solid var(--soft)}
.turn:last-child{border-bottom:none}
.turn .h{display:flex;gap:9px;align-items:baseline;margin-bottom:3px}
.turn .r{font-family:"Barlow Condensed",sans-serif;font-size:19px;font-weight:700;color:var(--ink)}
.turn .k{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint)}
.turn .n{font-size:13.5px}
.slots{display:flex;flex-direction:column;gap:0}
.sr{display:grid;grid-template-columns:46px minmax(0,1fr) 42px;gap:8px;align-items:center;
  padding:3px 0;border-bottom:1px solid var(--soft);font-size:13px}
.sr:last-child{border-bottom:none}
.sr .lb{font-family:"Barlow Condensed",sans-serif;font-size:12.5px;font-weight:700;
  letter-spacing:.07em;padding:1px 6px;border-radius:2px;text-align:center}
.sr.on .lb{background:var(--ink);color:var(--ground)}
.sr.off .lb{border:1px solid var(--accent);color:var(--accent)}
.sr.bn .lb{border:1px solid var(--rule);color:var(--faint);background:none}
.sr .who{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.sr .who .t{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--faint);margin-left:6px}
.sr.off .who{color:var(--faint)}
.sr .vv{text-align:right;font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--muted)}
.feed{font-size:13px}
.feed div{padding:3px 0;border-bottom:1px solid var(--soft);display:flex;gap:8px}
.feed div:last-child{border-bottom:none}
.feed .no{font-family:"IBM Plex Mono",monospace;color:var(--faint);width:30px;font-size:11.5px}
.feed .me{color:var(--accent);font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-family:"Barlow Condensed",sans-serif;text-transform:uppercase;letter-spacing:.1em;
font-size:12px;color:var(--muted);text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule)}
th.r,td.r{text-align:right}
td{padding:5px 10px;border-bottom:1px solid var(--soft)}
/* The board wrapper and a tier-watch ROW both used .tw, and the row rule
   comes second, so the wrapper inherited display:grid with the row's five
   columns and dropped its table into a 44px cell. Separate names. */
.bw{overflow-x:auto;border:1px solid var(--rule);border-radius:4px;background:var(--surface)}
.bwfoot{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);
  padding:6px 2px 0;display:flex;justify-content:space-between;align-items:baseline;gap:12px}
th.so{cursor:pointer;user-select:none}
th.so:hover{color:var(--accent)}
th.so[aria-sort]{color:var(--accent)}
th.so .ar{font-size:9px;margin-left:3px}
.rst{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--accent);
  cursor:pointer;border:none;background:none;padding:0;text-decoration:underline}
.rst[hidden]{display:none}
.pp{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:13px;letter-spacing:.06em}
.err{background:var(--accent);color:#fff;padding:9px 14px;border-radius:3px;margin:12px 0;font-size:13.5px}
.tw{display:grid;grid-template-columns:44px 34px minmax(0,1fr) 66px 92px;gap:10px;
align-items:center;padding:6px 8px 6px 0;border-bottom:1px solid var(--soft);font-size:13.5px}
.tw:last-child{border-bottom:none}
.tw .p{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:15px;letter-spacing:.06em}
.tw .n{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--faint)}
.tw .who{color:var(--muted);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tw .hold{font-family:"IBM Plex Mono",monospace;font-size:12px;text-align:right}
.tw .cost{display:flex;align-items:center;gap:6px;justify-content:flex-end}
.tw .cost .b{height:8px;border-radius:1px;background:var(--accent);min-width:2px}
.tw .cost .v{font-family:"IBM Plex Mono",monospace;font-size:13px;font-weight:500;
color:var(--ink);width:30px;text-align:right}
.tw.safe .cost .b{background:var(--rule)}
.tw.safe .p,.tw.safe .who{opacity:.55}
.tierbadge{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--faint)}
.colhead{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--faint);padding:0 0 5px;border-bottom:none}
.rec.colhead .v,.rec.colhead .nm{color:var(--faint);font-weight:400;font-size:10px}
.tw.colhead{background:none;border-bottom:1px solid var(--rule);padding-bottom:5px}
.tw.colhead span{color:var(--faint)}
.rec,tbody tr{cursor:pointer}
.rec.gone,tr.gone td{opacity:.32;text-decoration:line-through}
.wipe{background:none;border:1px solid var(--rule);color:var(--muted);cursor:pointer;
font:inherit;font-size:12px;padding:2px 9px;border-radius:2px;margin-left:8px}
.wipe:hover{border-color:var(--faint);color:var(--body)}
.lostbar{background:var(--LB);color:#fff;padding:10px 14px;border-radius:3px;
margin:12px 0;font-size:14px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.lostbar b{font-family:"Barlow Condensed",sans-serif;text-transform:uppercase;
letter-spacing:.1em;font-size:12.5px;opacity:.85}
.slotrow{display:flex;gap:6px;flex-wrap:wrap}
.sb{flex:1 1 54px;min-width:54px;padding:7px 4px;border:1px solid var(--rule);background:var(--surface);
border-radius:3px;cursor:pointer;font-family:"Barlow Condensed",sans-serif;font-size:20px;
font-weight:700;color:var(--ink)}
.sb:hover{border-color:var(--accent);color:var(--accent)}
.sb[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.f{font-family:"Barlow Condensed",sans-serif;text-transform:uppercase;letter-spacing:.09em;
font-size:13px;font-weight:600;padding:3px 11px;border:1px solid var(--rule);background:var(--surface);
color:var(--muted);border-radius:2px;cursor:pointer;margin-right:4px}
.f[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:var(--ground)}
.sechead{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid var(--ink);
padding-bottom:5px;margin:26px 0 12px}
.sechead h2{font-size:20px;font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.sechead .n{margin-left:auto;font-size:12.5px;color:var(--muted)}
</style></head><body><div class="wrap">
<div class="bar"><h1>Live draft</h1>
<span class="s" id="hdr">connecting…</span>
<span class="s" style="margin-left:auto" id="ts"></span></div>
<div id="err"></div><div id="simbar"></div><div id="lost"></div>
<div class="clock" id="clock"><h2>waiting for the draft</h2></div>
<div class="panel" id="seatpick"><h3 id="seathead">Which seat are you?</h3>
<div style="font-size:13px;color:var(--muted);margin-bottom:4px" id="seatnote"></div>
<div style="font-size:12px;margin-bottom:9px" id="seatsrc"></div>
<div class="slotrow" id="slotrow"></div></div>
<div class="cols">
<main>
  <div class="sechead"><h2>Tier watch</h2>
    <span class="n">what skipping each position costs by your next turn</span></div>
  <div class="tw colhead"><span>pos</span><span>in tier</span>
    <span>value range &middot; who is in the top tier still on the board</span>
    <span style="text-align:right" title="chance AT LEAST ONE member of this tier is still there when you next pick. Members are treated as independent, which held up: adjacent same-position runs tested as chance in all three measured rooms.">&ge;1 left</span>
    <span style="text-align:right" title="drop to the next tier multiplied by the chance this tier is gone. Low can mean two things - the tier survives, or the next tier is nearly as good. Either way, do not spend the pick here.">cost to wait</span></div>
  <div id="tierwatch" style="margin-bottom:26px"></div>
  <div class="sechead"><h2>Your remaining picks</h2>
    <span class="n" id="exp"></span></div>
  <div class="rec colhead"><span class="nm">player</span>
    <span class="v" title="points above the last startable player at this position, given what the league still has to fill">value</span>
    <span title="how often this was the pick at this turn across the rollouts. NOT his chance of being available - these are one decision's outcomes, which is why a turn's percentages sum to 100.">% of rollouts</span></div>
  <div id="plan"></div>
  <div class="sechead"><h2>Best available</h2>
    <span class="n">click any name to cross it off
      <button class="wipe" id="wipe">clear</button></span>
    <span class="n"><span id="filters"></span></span></div>
  <div class="bw"><table><thead><tr><th style="width:40px">#</th>
  <th class="so" data-k="name">Player</th>
  <th class="so" data-k="pos" style="width:48px">Pos</th>
  <th class="so" data-k="team" style="width:48px">Tm</th>
  <th class="so r" data-k="vorp" style="width:72px" title="points above the last startable player at this position, under THIS league's scoring and remaining demand. Not in Sleeper.">Value</th>
  <th class="so" data-k="tier" style="width:44px" title="value tier for this league - where the cliff is in points">Tier</th>
  <th class="so r" data-k="bc_rank" style="width:54px" title="consensus rank: where the room is expected to take him. Drives every survival number. Beat this feed's ADP by half on residual spread, measured on the completed LG02 draft.">ECR</th>
  <th class="so r" data-k="bc_sd_rel" style="width:46px" title="spread of expert rank. Sorts on that ratio, not the raw number. Highlighted when it is 1.8x the norm FOR THAT RANK - raw sd is useless as a flag because it scales with rank. A split panel means the situation is unresolved; check for a dated status event before reading it as upside, not after.">sd</th>
  </tr></thead><tbody id="board"></tbody></table></div>
  <div class="bwfoot"><button class="rst" id="bsort" hidden>reset sort (back to VORP)</button><span id="bcount"></span></div>
</main>
<aside>
  <div class="panel"><h3>Your roster</h3><div class="slots" id="roster"></div>
    <div style="margin-top:9px;font-size:12.5px;color:var(--muted)" id="owed"></div></div>
  <div class="panel"><h3>Replacement level</h3><div id="repl"></div></div>
  <div class="panel"><h3>Picks as they land</h3><div class="feed" id="feed"></div></div>
</aside></div></div>
<script>
let filter='ALL', LOST=[];
// Cross players off by hand. The live server does this from the pick feed, but
// the frozen card cannot see a pick land -- without this it is a snapshot you
// cannot mark up, which is worthless ten picks into a draft.
let GONE=new Set();
try{const v=localStorage.getItem('br_gone');if(v)GONE=new Set(JSON.parse(v));}catch(e){}
function saveGone(){try{localStorage.setItem('br_gone',JSON.stringify([...GONE]));}catch(e){}}
function strike(k){if(!k)return;GONE.has(k)?GONE.delete(k):GONE.add(k);saveGone();tick();}
const C=p=>`var(--${p})`;
function pct(p){return `<span class="pctbar"><span class="tr"><span class="fi" style="width:${p}%"></span></span><span class="p">${p}%</span></span>`;}
function key(n,p){return n+'|'+p;}
function row(t){const k=key(t.name,t.pos);
 return `<div class="rec${GONE.has(k)?' gone':''}" data-k="${k}"><span class="nm">${t.name}<span class="t">${t.pos} ${t.team||''}${t.inj?' · '+t.inj:''}</span></span>`
 +`<span class="v">${t.vorp>0?'+':''}${Math.round(t.vorp)}</span>${pct(t.pct)}</div>`;}
async function setSeat(n){
 document.getElementById('slotrow').querySelectorAll('.sb').forEach(b=>
   b.setAttribute('aria-pressed', b.dataset.n==n));
 try{ await fetch('/slot?n='+n); }catch(e){}
 tick();
}
function drawSeats(cur, teams){
 const row=document.getElementById('slotrow');
 if(row.children.length!=teams){
   row.innerHTML='';
   for(let i=1;i<=teams;i++){
     const b=document.createElement('button');
     b.className='sb'; b.dataset.n=i; b.textContent=i;
     b.setAttribute('aria-pressed', i==cur);
     b.onclick=()=>setSeat(i);
     row.appendChild(b);
   }
 } else {
   row.querySelectorAll('.sb').forEach(b=>b.setAttribute('aria-pressed', b.dataset.n==cur));
 }
}
async function tick(){
 let s; try{ s=await (await fetch('/state')).json(); }catch(e){
   document.getElementById('err').innerHTML='<div class="err">server gone — restart with <code>python br.py live</code></div>'; return;}
 document.getElementById('err').innerHTML = s.err?`<div class="err">${s.err}</div>`:'';
 const gone=s.lost_targets||[];
 if(gone.length) LOST=[...new Set([...LOST,...gone])].slice(-4);
 const nowTop=((s.plan||[])[0]||{}).targets||[];
 document.getElementById('lost').innerHTML = LOST.length
  ? `<div class="lostbar"><b>gone</b><span>${LOST.join(', ')}</span>`
    +(nowTop.length?`<span style="margin-left:auto;opacity:.9">now: `
      +`<b style="font-size:14px;letter-spacing:0;text-transform:none">`
      +`${nowTop[0].name}</b> (${nowTop[0].pos})</span>`:'')+`</div>`
  : '';
 document.getElementById('simbar').innerHTML = s.simulated
  ? '<div class="err" style="background:var(--LB)">REHEARSAL — these picks are fake. '
    +'Nothing here is your real draft.</div>' : '';
 const stale=s.stale_picks_for||0;
 document.getElementById('ts').textContent =
  `checked ${s.checked||s.ts||''}` + (stale>90?`  ·  no new pick for ${Math.floor(stale/60)}m`:'');
 document.getElementById('hdr').innerHTML =
  `<b>${s.picks_made}</b> picks · ${s.status||'—'} · ${s.teams||'?'} teams × ${s.rounds||'?'} rounds`
  + (s.slot?` · your seat <b>${s.slot}</b>`:' · <b>seat unknown</b>');
 const c=document.getElementById('clock');
 if(s.on_clock){c.className='clock now';
   const t=(s.plan&&s.plan[0]&&s.plan[0].targets)||[];
   c.innerHTML=`<div class="lab">you are on the clock — pick ${s.next_pick}</div>`
    +`<h2>${t.length?'Take '+t[0].name:'—'}</h2>`
    +(t.length>1?`<div style="margin-top:6px;font-size:13.5px;opacity:.9">then ${t.slice(1).map(x=>x.name).join(' · ')}</div>`:'');
 } else if(!s.live && s.next_pick){c.className='clock';
   c.innerHTML=`<div class="lab">not started — ${s.status||'pre draft'}</div>`
    +`<h2>You pick at ${(s.plan||[]).slice(0,5).map(p=>p.pick).join(', ')}…</h2>`;
 } else if(s.away!=null){c.className='clock';
   c.innerHTML=`<div class="lab">next turn</div><h2>${s.away} pick${s.away==1?'':'s'} away — pick ${s.next_pick}</h2>`;
 } else if(s.status=='complete'){c.className='clock';
   c.innerHTML=`<div class="lab">draft complete &mdash; ${s.picks_made} picks</div>`
    +`<h2>Lineup value ${s.have||0}</h2>`;
 } else {c.className='clock';c.innerHTML='<h2>waiting for the draft</h2>';}
 drawSeats(s.slot, s.teams||10);
 document.getElementById('seatpick').hidden = false;
 document.getElementById('seathead').textContent = s.slot ? 'Your seat' : 'Which seat are you?';
 document.getElementById('seatnote').textContent = s.slot
  ? 'Change it any time — the plan rebuilds, no restart.'
  : 'Sleeper has not published the draft order yet. Set it the moment you know.';
 const src=document.getElementById('seatsrc');
 src.textContent = s.slot ? `seat ${s.slot} — from ${s.slot_source}` : '';
 src.style.color = (s.slot && s.slot_source==='Sleeper draft order')
   ? 'var(--good)' : 'var(--muted)';
 const tw=s.tiers||{}, rowsT=Object.entries(tw)
   .sort((a,b)=>(b[1].cost_to_wait??-1)-(a[1].cost_to_wait??-1));
 const maxc=Math.max(1,...rowsT.map(r=>r[1].cost_to_wait||0));
 document.getElementById('tierwatch').innerHTML = rowsT.map(([pos,d])=>{
  const unk=d.cost_to_wait==null;
  const safe=(!unk && d.cost_to_wait<1)?' safe':'';
  const fmt=v=>(v<0?'\u2212':'')+Math.abs(Math.round(v));
  const val=d.n==1?fmt(d.hi):`${fmt(d.hi)} to ${fmt(d.lo)}`;
  return `<div class="tw${safe}"><span class="p" style="color:${C(pos)}">${pos}</span>`
   +`<span class="n">${d.n} left</span>`
   +`<span class="who">${val} &middot; ${d.names.slice(0,3).join(', ')}`
   +`${d.next_tier!=null?` &rarr; next tier ${fmt(d.next_tier)}`:''}</span>`
   +`<span class="hold" style="color:${(!unk&&d.hold<0.35)?'var(--accent)':'var(--muted)'}">`
   +`${unk?'&mdash;':Math.round(d.hold*100)+'% holds'}</span>`
   +`<span class="cost"><span class="b" style="width:${unk?0:Math.round(46*d.cost_to_wait/maxc)}px">`
   +`</span><span class="v">${unk?'&mdash;':Math.round(d.cost_to_wait)}</span></span></div>`;
 }).join('') || '<div style="color:var(--faint)">no tiers yet</div>';
 document.getElementById('exp').textContent = s.expected
  ? `lineup value ${s.have||0} now → ${s.expected} projected`
  : (s.have ? `final lineup value ${s.have}` : '');
 document.getElementById('plan').innerHTML = (s.plan||[]).slice(0,6).map(p=>
  `<div class="turn"><div class="h"><span class="r">R${p.round}</span>`
  +`<span class="k">pick ${p.pick}</span></div>`
  +(p.targets.length?p.targets.map(row).join(''):'<div class="n" style="color:var(--faint)">no clear target</div>')
  +`</div>`).join('') || '<div style="color:var(--faint)">no picks left</div>';
 const R=s.my_roster||{}, req=s.req||[];
 const filled=[]; const cnt={};
 req.forEach(p=>{cnt[p]=(cnt[p]||0)+1; filled.push([p,(R[p]||0)>=cnt[p]]);});
 // a flex slot is filled when some position in it has a spare beyond its
 // own starters -- it was hardcoded open and stayed orange on a full roster
 const spare={};
 (s.flex||[]).forEach(f=>f.forEach(q=>{
   spare[q]=Math.max(0,(R[q]||0)-req.filter(x=>x==q).length);}));
 (s.flex||[]).forEach(f=>{
   const q=f.find(x=>(spare[x]||0)>0);
   if(q) spare[q]--;
   filled.push([f.join('/'), !!q]);
 });
 const slots = s.slots || filled.map(([p,done])=>({slot:p,name:done?'':null}));
 document.getElementById('roster').innerHTML = slots.map(x=>{
   const bn = /^BN/.test(x.slot), on = !!x.name;
   const cls = on ? 'on' : (bn ? 'bn' : 'off');
   const who = on
     ? `${x.name}<span class="t">${x.pos||''} ${x.team||''}</span>`
     : (bn ? '<span style="color:var(--faint)">—</span>'
           : '<span style="color:var(--accent)">open</span>');
   const v = (on && x.vorp!=null) ? ((x.vorp>0?'+':'')+Math.round(x.vorp)) : '';
   return `<div class="sr ${cls}"><span class="lb">${x.slot}</span>`
        + `<span class="who">${who}</span><span class="vv">${v}</span></div>`;
 }).join('');
 document.getElementById('owed').textContent = (s.owed&&s.owed.length)
   ? 'still to fill: '+s.owed.map(o=>o.join('/')).join(', ') : 'lineup complete';
 document.getElementById('repl').innerHTML = Object.entries(s.replacement||{})
  .sort((a,b)=>b[1]-a[1]).map(([p,v])=>
   `<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:13px">`
   +`<span class="pp" style="color:${C(p)}">${p}</span><span class="mono">${v}</span></div>`).join('');
 document.getElementById('feed').innerHTML=(s.feed||[]).length? (s.feed||[]).map(f=>
  `<div><span class="no">${f.no}</span><span class="${f.mine?'me':''}">${f.name}</span>`
  +`<span style="color:var(--faint);font-size:11.5px;margin-left:auto" class="mono">${f.pos} ${f.team||''}</span></div>`).join('')
  : '<div style="color:var(--faint);border:none">nothing drafted yet</div>';
 const poss=['ALL',...new Set((s.board||[]).map(b=>b.pos))];
 document.getElementById('filters').innerHTML=poss.map(p=>
  `<button class="f" data-p="${p}" aria-pressed="${p==filter}">${p}</button>`).join('');
 let shown=(s.board||[]).filter(b=>filter=='ALL'||b.pos==filter);
 if(SORT.k){
   const k=SORT.k, d=SORT.dir, txt=(k=='name'||k=='pos'||k=='team');
   // Missing values sink in BOTH directions. Treating null as 0 would put
   // every unranked player at the top of an ascending ECR sort, which is
   // the opposite of what the column is for.
   shown=shown.slice().sort((a,b)=>{
     const x=a[k], y=b[k], xn=(x==null||x===''), yn=(y==null||y==='');
     if(xn&&yn) return b.vorp-a.vorp;
     if(xn) return 1;
     if(yn) return -1;
     if(txt) return String(x).localeCompare(String(y))*d;
     return (x-y)!==0 ? (x-y)*d : b.vorp-a.vorp;
   });
 }
 document.querySelectorAll('th.so').forEach(th=>{
   const on=SORT.k===th.dataset.k;
   if(on) th.setAttribute('aria-sort', SORT.dir<0?'descending':'ascending');
   else th.removeAttribute('aria-sort');
   const lab=th.getAttribute('data-lab') || (th.setAttribute('data-lab',th.textContent.trim()), th.textContent.trim());
   th.innerHTML = lab + (on?`<span class="ar">${SORT.dir<0?'&#9660;':'&#9650;'}</span>`:'');
 });
 document.getElementById('bsort').hidden = !SORT.k;
 document.getElementById('bcount').textContent = shown.length>BOARD_SHOW
   ? `showing ${BOARD_SHOW} of ${shown.length} available — filter by position to see deeper`
   : `${shown.length} available`;
 document.getElementById('board').innerHTML=shown.slice(0,BOARD_SHOW).map((b,i)=>
  `<tr class="${GONE.has(key(b.name,b.pos))?'gone':''}" data-k="${key(b.name,b.pos)}">`
  +`<td class="mono" style="color:var(--faint);font-size:12px">${i+1}</td><td>${b.name}</td>`
  +`<td class="pp" style="color:${C(b.pos)}">${b.pos}</td>`
  +`<td class="mono" style="color:var(--faint);font-size:12px">${b.team||''}</td>`
  +`<td class="r mono" style="color:var(--ink);font-weight:600">${b.vorp>0?'+':''}${Math.round(b.vorp)}</td>`
  +`<td class="tierbadge">${b.tier?('T'+b.tier):''}</td>`
  +`<td class="r tierbadge" title="${b.bc_tier?('consensus tier '+b.bc_tier):'not on the external board'}">${b.bc_rank?b.bc_rank:'&mdash;'}</td>`
  +`<td class="r tierbadge" style="color:${b.bc_sd_rel>=1.8?'#c8873a':'var(--faint)'};font-weight:${b.bc_sd_rel>=1.8?600:400}" title="${b.bc_sd_rel!=null?('spread is '+b.bc_sd_rel+'x the norm for this rank'):''}">${b.bc_sd!=null?Math.round(b.bc_sd):''}</td>`
  +`</tr>`).join('');
}
document.getElementById('plan').addEventListener('click',e=>{
 const r=e.target.closest('.rec'); if(r) strike(r.dataset.k);
});
document.getElementById('board').addEventListener('click',e=>{
 const r=e.target.closest('tr'); if(r&&r.dataset.k) strike(r.dataset.k);
});
document.getElementById('wipe').addEventListener('click',()=>{
 GONE=new Set(); saveGone(); tick();
});
document.getElementById('filters').addEventListener('click',e=>{
 const b=e.target.closest('.f'); if(!b)return; filter=b.dataset.p; tick();});
document.querySelector('.bw thead').addEventListener('click',e=>{
 const th=e.target.closest('th.so'); if(!th)return;
 const k=th.dataset.k, first=LOWFIRST.has(k)?1:-1;
 if(SORT.k!==k) SORT={k:k,dir:first};
 else if(SORT.dir===first) SORT.dir=-first;
 else SORT={k:null,dir:-1};
 tick();});
document.getElementById('bsort').addEventListener('click',()=>{SORT={k:null,dir:-1};tick();});
const POLL_MS=3000;   // rewritten by serve()
// How many rows the board draws. The payload carries BOARD_ROWS (400); this
// is a reading limit, not a data one, and the footer says which so a cut
// list is never mistaken for an exhausted position.
const BOARD_SHOW=150;
// null key = server order, which is VORP descending. A header click cycles
// desc -> asc -> off, so the third click IS the reset; the footer carries a
// visible one too rather than relying on that being discoverable.
let SORT={k:null,dir:-1};
const LOWFIRST=new Set(['bc_rank','tier']);   // a rank reads best ascending
tick(); setInterval(tick, POLL_MS);
</script></body></html>"""



def card(league_id, slot=None, mocks=220, out_path=None, port_note=8788):
    """Freeze the board to a standalone HTML file.

    The live server is a single point of failure on a draft with a 60-second
    clock and autopick switched on: if it dies, Sleeper starts drafting for
    you. This writes the same page with the state baked in, so it opens from
    disk with nothing running. It is a snapshot -- it cannot see picks land --
    which is exactly why it says so at the top.
    """
    live = Live(league_id, slot_override=slot, mocks=mocks)
    print("building the board …")
    live.refresh(force=True)
    st = live.state()
    st["frozen_at"] = time.strftime("%a %d %b %H:%M")

    html = PAGE.replace(
        "let s; try{ s=await (await fetch('/state')).json(); }catch(e){",
        "let s; try{ s=FROZEN; }catch(e){", 1)
    html = html.replace("tick(); setInterval(tick, POLL_MS);", "tick();", 1)
    # The picker is dead on a snapshot -- there is no server to tell. It used
    # to be stubbed while the note underneath still read "Change it any time
    # -- the plan rebuilds, no restart", so the buttons silently did nothing
    # and the page insisted they worked. Disable it and SAY so.
    html = html.replace("async function setSeat(n){",
                        "async function setSeat(n){ return; //frozen\n", 1)
    html = html.replace(
        "? 'Change it any time \u2014 the plan rebuilds, no restart.'",
        "? 'Baked into this snapshot. Rebuild the card, or run the live "
        "server, to change it.'", 1)
    banner = ("<div class=\"err\" style=\"background:var(--TE)\">FROZEN SNAPSHOT &mdash; "
              "taken " + st["frozen_at"] + ". It cannot see picks land. Use the live "
              "server if it is running; this is the fallback.</div>")
    html = html.replace('<div id="err"></div>', '<div id="err"></div>' + banner, 1)
    html = html.replace("<script>", "<script>\nconst FROZEN=" + json.dumps(st) + ";", 1)

    out_path = out_path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out",
        f"draft-card-{league_id}.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  {out_path}")
    print(f"  seat {st.get('slot')} ({st.get('slot_source')}), "
          f"{len(st.get('plan') or [])} turns planned, "
          f"{len(st.get('board') or [])} players on the board")
    print("  open it in a browser. No server needed.")
    return out_path


def serve(league_id, port=8788, every=2, slot=None, mocks=90,
          simulate=False, speed=2.0, poll_ms=None):
    """`every` is how often the SERVER asks Sleeper; `poll_ms` is how often
    the BROWSER asks the server. They are different clocks and the slower
    one governs -- setting the page to 2s against a 5s fetch loop buys
    nothing but wasted requests, which is what the old 3s/5s pairing did.
    poll_ms defaults to `every`, so one flag moves both.

    2s is safe on rate: a live refresh costs 3 calls (league, draft, picks)
    = 90/min against sleeper_client's ~750/min ceiling. And refresh()
    returns early when the pick count has not moved, so the 90-mock replan
    only runs when a pick actually lands, not on every tick."""
    import http.server
    poll_ms = int(poll_ms if poll_ms else every * 1000)
    page = PAGE.replace("const POLL_MS=3000;", f"const POLL_MS={poll_ms};", 1)
    live = Live(league_id, slot_override=slot, every=every, mocks=mocks)
    print(f"priming board for league {league_id} …")
    if simulate:
        lg, draft, _ = league_draft(league_id)
        season = str(lg.get("season") or (draft or {}).get("season") or "2026")
        pool = build_pool(lg, season)
        req, flex, bench, teams, rounds = shape(lg)
        rounds = int((draft or {}).get("settings", {}).get("rounds") or rounds)
        # Read the real seat BEFORE the fake draft replaces the real one.
        # The Sim's draft object carries no draft_order, so my_slot() cannot
        # find a seat once it is installed -- the rehearsal drafted for seat 1
        # while "my roster" collected another seat's picks by roster_id.
        published = my_slot(draft)
        real_slot = slot or published or 1
        sim = Sim(lg, pool, real_slot, teams, rounds, speed=speed)
        live.set_slot(real_slot,
                      source=("Sleeper draft order" if real_slot == published
                              and not slot else "you set it"))

        def my_pick():
            """Take whatever the board is currently telling me to take, so the
            rehearsal exercises the advice instead of second-guessing it."""
            snap = live.state()
            plan = snap.get("plan") or []
            if plan and plan[0].get("targets"):
                want = plan[0]["targets"][0]["name"]
                for q in pool.values():
                    if q["name"] == want and q["pid"] not in sim.taken:
                        return q
            return None

        sim.advise_cb = my_pick
        live.sim = sim
        live.every = min(live.every, 2)
        print(f"REHEARSAL: fake picks every {speed}s from seat {real_slot}. "
              f"Nothing is read from or written to the live draft.")
    live.refresh(force=True)
    threading.Thread(target=live.loop, daemon=True).start()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/slot"):
                import urllib.parse as up
                q = up.parse_qs(up.urlparse(self.path).query)
                try:
                    live.set_slot((q.get("n") or [None])[0])
                except Exception as e:
                    print(f"set_slot failed: {e}")
                self._send(json.dumps(live.state()).encode(), "application/json")
            elif self.path.startswith("/draft"):
                try:
                    # always the REAL draft, even mid-rehearsal: this endpoint
                    # exists to answer questions about the actual draft (when
                    # it starts, whether the order is published), and the fake
                    # one has nothing useful to say about either
                    lg, dr, pk = league_draft(live.lid)
                    _st = (dr or {}).get("start_time")
                    body = {"status": (dr or {}).get("status"),
                            "start_time": _st,
                            "starts": (time.strftime("%a %d %b %H:%M:%S %Z",
                                                     time.localtime(_st / 1000))
                                       if _st else None),
                            "draft_order": (dr or {}).get("draft_order"),
                            "slot_to_roster_id": (dr or {}).get("slot_to_roster_id"),
                            "settings": (dr or {}).get("settings"),
                            "picks": len(pk),
                            "my_slot_from_order": my_slot(dr),
                            "slot_override": live.slot_override,
                            "rehearsal_running": bool(live.sim)}
                except Exception as e:
                    body = {"error": f"{type(e).__name__}: {e}"}
                self._send(json.dumps(body, indent=1).encode(), "application/json")
            elif self.path.startswith("/state"):
                self._send(json.dumps(live.state()).encode(), "application/json")
            else:
                self._send(page.encode(), "text/html; charset=utf-8")

    print(f"\n  http://localhost:{port}\n")
    print(f"  server polls Sleeper every {every}s; page refreshes every "
          f"{poll_ms/1000:g}s — Ctrl+C to stop")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def _arg(args, flag, cast=str, default=None):
    if flag in args:
        i = args.index(flag)
        return cast(args[i + 1])
    return default


if __name__ == "__main__":
    a = sys.argv[1:]
    from battle_rhythm.sleeper_client import load_leagues
    frag = _arg(a, "--league", str, "lg06")
    lgs = load_leagues()["leagues"]
    lg = next((l for l in lgs if frag.lower() in (l["name"] or "").lower()
               or frag == str(l.get("league_id"))), None)
    if not lg:
        raise SystemExit(f"no league matching '{frag}'")
    print(f"league: {lg['name']}")
    if "--card" in a:
        card(str(lg["league_id"]), slot=_arg(a, "--slot", int, None),
             mocks=_arg(a, "--mocks", int, 220),
             out_path=_arg(a, "--out", str, None))
        sys.exit()
    serve(str(lg["league_id"]), port=_arg(a, "--port", int, 8788),
          every=_arg(a, "--every", int, 2), slot=_arg(a, "--slot", int, None),
          mocks=_arg(a, "--mocks", int, 90), simulate="--simulate" in a,
          speed=_arg(a, "--speed", float, 2.0),
          poll_ms=_arg(a, "--poll-ms", int, None))
