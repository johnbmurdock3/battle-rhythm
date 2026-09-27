"""
Draft helper — live board + pre-draft cheat sheets, scored by each league's own rules.

Usage (on a networked machine):
  python draft_helper.py board 9000000000000000010        # live: LG01
  python draft_helper.py sheet 9000000000000000020        # pre-draft cheat sheet
  python draft_helper.py board <league_id> --pos QB       # filter one position

What it does:
  1. Pulls the league's draft, its picks so far, and every roster (startup drafts:
     picked = gone; established leagues: rostered = gone too).
  2. Builds season-long projections per player by summing Sleeper's weekly raw
     projection stat lines (weeks 1-18; bye weeks come back null and are skipped),
     then scoring each week with THIS league's scoring_settings via the verified
     dot-product engine. Generic ADP is wrong for the Hybrid leagues' bucket +
     first-down scoring; this isn't.
  3. Prints best-available with: projected points under league rules, ADP (PPR),
     age, and how many picks until your next turn.

Endpoint notes (verify on first run — flagged where unproven):
  - Bulk weekly projections: BASE /projections/nfl/regular/{season}/{week}
    UNVERIFIED shape — believed to be {player_id: {stat: val}}. If it comes back
    as a list of {player_id, stats} objects (api.sleeper.com shape), _normalize()
    handles that too. If both fail, the script tells you what it actually got.
  - Per-player season projection (ADP source): api.sleeper.com
    /projections/nfl/player/{pid}?grouping=season — VERIFIED live 2026-08-09.
"""

import json
from battle_rhythm import paths as _paths
import sys
import time
import pathlib
from collections import defaultdict

from battle_rhythm.sleeper_client import (get, _get, players, name_of, score, state,
                            BASE, STATS_BASE, CACHE, USERNAME)

PROJ_TTL = 60 * 60 * 6  # projections move; refetch every 6h


# ------------------------------------------------------------- projections

def _normalize(raw):
    """Accept either {pid: stats} or [{player_id, stats}, ...]; return {pid: stats}."""
    if isinstance(raw, dict):
        first = next(iter(raw.values()), None)
        if first is None or isinstance(first, dict):
            # could be {pid: stats} or {pid: {stats: {...}}}
            out = {}
            for pid, v in raw.items():
                out[str(pid)] = v.get("stats", v) if isinstance(v, dict) else {}
            return out
    if isinstance(raw, list):
        return {str(x.get("player_id")): (x.get("stats") or {})
                for x in raw if isinstance(x, dict) and x.get("player_id")}
    raise SystemExit(f"projections endpoint returned unexpected shape: {type(raw)} "
                     f"sample={str(raw)[:300]}")


def weekly_projections(season, week):
    """All players' raw projected stat lines for one week. Cached."""
    p = CACHE / f"proj_{season}_wk{week}.json"
    if p.exists() and time.time() - p.stat().st_mtime < PROJ_TTL:
        return json.loads(p.read_text(encoding="utf-8"))
    raw = get(f"projections/nfl/regular/{season}/{week}")
    if raw is None:
        # fallback: app-internal host, list shape
        raw = _get(f"{STATS_BASE}/projections/nfl/{season}/{week}?season_type=regular")
    data = _normalize(raw or {})
    p.write_text(json.dumps(data))
    return data


def season_aggregates(season):
    """Season-total projection stat lines (availability-adjusted by Rotowire)
    from the app's bulk endpoint, ~top 100 per position. Coarse keys only —
    no buckets/first downs — so these are used for the availability ratio,
    not for scoring."""
    p = CACHE / f"season_agg_{season}.json"
    if p.exists() and time.time() - p.stat().st_mtime < PROJ_TTL:
        return json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for pos in SEAT_POS:
        order = "idp_tkl" if pos in IDP_POS else "ppr"
        raw = _get(f"{STATS_BASE}/projections/nfl/{season}"
                   f"?season_type=regular&position[]={pos}"
                   f"&order_by={order}") or []
        for x in raw:
            if isinstance(x, dict) and x.get("player_id"):
                out[str(x["player_id"])] = x.get("stats") or {}
    p.write_text(json.dumps(out))
    return out


def _gen_pts(st):
    for k in ("pts_ppr", "pts_half_ppr", "pts_std"):
        if isinstance(st.get(k), (int, float)) and st[k] > 0:
            return st[k]
    return None


# A ratio needs enough weeks under it to mean anything. Six players carry
# ONE week in the feed; their raw ratio is 18.06 and the old clamp turned
# that into a tidy 1.05, so broken data arrived looking like a mild bonus.
MIN_RATIO_WEEKS = 8


def availability_ratios(season, weeks=18, _diag=None):
    """{pid: availability multiplier <= 1.0}, per WEEK, not per total.

    The weekly feed projects each game as if the player plays it; the
    season aggregate carries Rotowire's availability haircut. The ratio
    between them is meant to recover that haircut.

    IT WAS DIVIDING TWO DIFFERENT SPANS. The weekly feed omits every
    player's bye, so the summed weekly is a SEVENTEEN week number while
    the aggregate is a full season. 18/17 is 1.059 of pure denominator
    artifact before availability is considered at all, and it landed on
    top of every player:

        weeks in feed   players   median raw ratio
                   17       850             1.038
                   16        78             1.143   <- 18/16, not health
                    1         6            18.056

    The 16-week group is not 14% healthier than the field. The ratio was
    tracking weeks of coverage.

    Measured 9/3 on LG03-LG05: Brian Thomas came out at 1.062 -- 18/17
    almost exactly -- and was clamped to 1.05, so a fully available
    receiver was carrying a five percent BONUS on a field whose whole job
    is to take points away. Meanwhile DJ Moore's real haircut is 0.86 and
    the same inflation was hiding a third of it. Every haircut in the
    toolkit was understated by about six percent.

    Normalise per week and the artifact cancels: compare the aggregate's
    weekly average against the feed's own weekly average over the weeks it
    actually carries. Then clamp to 1.0, because nobody is more available
    than fully available.

    Players with fewer than MIN_RATIO_WEEKS of coverage get NO ratio and
    default to 1.0 at the call site -- better to decline than to publish a
    number from one week. Pass `_diag` (a dict) to get them back.
    """
    agg = season_aggregates(season)
    gen = defaultdict(float)
    seen = defaultdict(int)
    for wkn in range(1, weeks + 1):
        for pid, st in weekly_projections(season, wkn).items():
            if st:
                v = _gen_pts(st)
                if v:
                    gen[pid] += v
                    seen[pid] += 1
    ratios, thin = {}, []
    for pid, st in agg.items():
        s, w, n = _gen_pts(st), gen.get(pid), seen.get(pid, 0)
        if not (s and w):
            continue
        if n < MIN_RATIO_WEEKS:
            thin.append(pid)
            continue
        ratios[pid] = max(0.5, min(1.0, (s / weeks) / (w / n)))
    if _diag is not None:
        _diag["thin"] = thin
        _diag["counted"] = len(ratios)
    return ratios


def season_projection_totals(season, scoring, weeks=range(1, 19)):
    """{pid: projected season pts under `scoring`}: league-scored weekly sums
    (full stat detail) scaled by the feed's own availability ratio, so totals
    line up with what the app shows instead of assuming 17 healthy games."""
    totals = defaultdict(float)
    for wk in weeks:
        for pid, stats in weekly_projections(season, wk).items():
            if stats:
                totals[pid] += score(stats, scoring)
    ratios = availability_ratios(season)
    return {pid: round(v * ratios.get(pid, 1.0), 1) for pid, v in totals.items()}


# Position vocabulary. IDP: Sleeper projects defenders as LB, DL, and DB
# (corners and safeties both roll up to DB in the feed), with idp_* stat
# lines the scoring dot-product handles like any other stat. League slot
# names that are finer-grained than the feed (CB, S, DE...) alias to the
# feed's position so demand lands on players that actually exist.
OFF_POS = ("QB", "RB", "WR", "TE")
IDP_POS = ("DL", "LB", "DB")
SEAT_POS = OFF_POS + ("K", "DEF") + IDP_POS
SLOT_ALIAS = {"CB": "DB", "S": "DB", "FS": "DB", "SS": "DB",
              "DE": "DL", "DT": "DL", "NT": "DL", "EDGE": "DL",
              "MLB": "LB", "OLB": "LB", "ILB": "LB"}


def norm_pos(meta, rostered):
    """The position this player occupies IN THIS LEAGUE, or None to drop him.

    Sleeper carries TWO fields and they disagree on purpose. `position` is
    the real NFL position -- Myles Garrett is DE, Jeffery Simmons is DT --
    while `fantasy_positions` is the list of slots he is ELIGIBLE for, and
    for both of those it is ['DL'].

    The pool filter compared `position` against the league's aliased roster
    slots, so DE, DT, CB and the rest matched nothing and were dropped
    silently. Measured 9/7 against the live player table: 503 defenders
    invisible, including 314 of 458 linemen -- Garrett, Bosa, Crosby,
    Hunter, Burns, Simmons -- in a league whose card was built on "ten
    linemen above replacement for ten teams". SLOT_ALIAS was written to
    prevent exactly this and was applied to the league's slots only, never
    to the player: one side of a comparison, which is why it read as
    correct.

    STRICTLY ADDITIVE, AND IDP-ONLY. A position that already matches is
    returned untouched, so nothing that worked yesterday moves; only a
    player who was being dropped can now resolve.

    The `fantasy_positions` branch is deliberately restricted to IDP_POS,
    and that restriction was MEASURED INTO EXISTENCE rather than reasoned.
    Without it the branch also admitted fullbacks -- Sleeper position FB,
    fantasy_positions ['RB'] -- which moved the RB pool from 125 to 129 in
    a league drafted two days earlier. Arguably more correct; certainly not
    what "IDP fix" promised, and not a change to make to five settled
    leagues on the eve of a sixth draft. The FB question is logged, not
    answered here. Every SLOT_ALIAS key is already defensive, so with this
    restriction the five non-IDP leagues cannot change at all -- and that
    claim is now true rather than merely asserted.

    MEASURED 9/7 on LG06, pool with a projection above zero:
        DL  61 -> 162     DB 131 -> 176     LB 107 -> 107
        QB/WR/TE/K unchanged, and zero players reach two buckets.
    Thirteen of the new linemen are dual-eligible ['DL', 'LB'] edge
    rushers -- Hunter, Burns, Hines-Allen, Greenard -- and all thirteen
    land in DL. None went to LB or DB.

    Dual eligibility resolves to the FIRST listed slot this league rosters
    (Danielle Hunter is ['DL', 'LB'] and lands at DL). One player must sit
    in one bucket or the replacement bars double-count him. Deterministic,
    and it follows Sleeper's own ordering rather than ours.
    """
    pos = meta.get("position")
    if pos in rostered:
        return pos
    for fp in (meta.get("fantasy_positions") or ()):
        if fp in rostered and fp in IDP_POS:
            return fp
    aliased = SLOT_ALIAS.get(pos)
    return aliased if aliased in rostered else None

REDRAFT_ADP_KEYS = ("adp_dd_ppr", "adp_ppr", "adp_half_ppr", "adp_std")
# Dynasty market ADP (adp_dynasty_ppr etc.) diverges hard from redraft for
# rookies/young players. It is NOT in the bulk weekly feed — only the
# per-player season endpoint carries it — so dynasty lookups go per-player
# first (small throttled calls, cached forever) and only then fall back to
# bulk redraft ADP. A dynasty value never silently masquerades as redraft
# again: the fallback is marked with a trailing 'r' in the board display.
DYNASTY_ADP_KEYS = ("adp_dynasty_ppr", "adp_dynasty_half_ppr", "adp_dynasty_2qb",
                    "adp_dynasty_std")

# An IDP room drafts in a different market than everyone else, and it is the
# ONLY market that prices defenders at all. Without this, every DL/LB/DB in an
# IDP league reads as unpriced ("-" on the board) and every survival call about
# them is a guess -- Aidan Hutchinson showed no ADP in LG06 Burgers while the
# IDP board had him at 76. These keys live on the bulk SEASON endpoint, not the
# weekly feed, so they resolve through season_aggregates (one cached call) and
# never per-player: a pool-wide per-player walk is what wedged the MCP server
# once already.
IDP_ADP_KEYS = ("adp_idp_1qb", "adp_idp")
IDP_ADP_KEYS_SFLEX = ("adp_idp", "adp_idp_1qb")


# Keys the bulk weekly feed does NOT carry. They exist only on the
# per-player season endpoint, so a chain starting with one of these must
# ask the endpoint BEFORE it accepts a later key from the bulk feed.
PER_PLAYER_ONLY = ("adp_2qb", "adp_dynasty_ppr", "adp_dynasty_half_ppr",
                   "adp_dynasty_2qb", "adp_dynasty_std")


def _keeper_flag(league_id):
    """keepers.json's manual keeper flag, via the one reader.

    Sleeper's settings.type == 2 covers both a 3-keeper Hybrid and full
    dynasty; only this flag tells them apart (CLAUDE.md lesson 5).
    """
    try:
        from battle_rhythm.league_rules import is_keeper_league
        return is_keeper_league(league_id)
    except Exception:
        return False


def _pick(d, keys):
    return _pick_kv(d, keys)[0]


def _pick_kv(d, keys):
    """(value, key) for the first usable key in the chain, else (None, None).

    Returning the key is the point. `exact` was True whether adp_2qb
    answered or adp_dd_ppr did four keys later, so a superflex league
    reading 1QB prices looked exactly like one reading superflex prices.
    """
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and 0 < v < 999:
            return v, k
    return None, None


def _from_endpoint(pid, season, keys):
    """Ask the per-player season endpoint for the first key in the chain.

    superflex_adp has already fetched adp_2qb for the whole pool and
    cached it; read that rather than refetching seven hundred players.
    Imported lazily -- superflex_adp imports this module.
    """
    if "adp_2qb" in keys:
        try:
            from battle_rhythm.superflex_adp import cache_path
            f = cache_path(season)
            if f.exists():
                v = json.loads(f.read_text(encoding="utf-8") or "{}").get(str(pid))
                if isinstance(v, (int, float)) and 0 < v < 999:
                    return float(v), "adp_2qb"
        except Exception:
            pass
    try:
        data = _get(f"{STATS_BASE}/projections/nfl/player/{pid}"
                    f"?season_type=regular&season={season}&grouping=season") or {}
        return _pick_kv(data.get("stats") or {}, keys)
    except Exception:
        return None, None


def _from_season_agg(pid, season, keys):
    """IDP ADP off the bulk season aggregate. One cached call for the whole
    pool, so this stays safe to run across every player on the board."""
    try:
        return _pick_kv(season_aggregates(season).get(str(pid)) or {}, keys)
    except Exception:
        return None, None


def _adp(pid, season, keys, fallback=()):
    """Returns (value, exact) — exact=False means the fallback tier answered.

    THE POISONING THIS FIXED (8/13). The old order tried the whole chain
    against the bulk weekly feed and only asked the per-player endpoint
    if nothing matched. For ("adp_2qb",) + REDRAFT_ADP_KEYS that meant
    adp_dd_ppr — a 1QB price — answered for a superflex room, and it was
    stamped exact. Josh Allen read 29.0 in a league whose real 2QB
    market has him at 1.2, and every survival call in both Hybrids was
    made against it. superflex_adp.cache_path documents the same
    poisoning and routes around it; this removes the cause.

    Cache entries carry a third field now: which key actually answered.
    Two-field entries predate the fix and are re-derived on sight.
    """
    p = CACHE / f"adp_{season}_{keys[0]}.json"
    book = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    key = str(pid)
    if not isinstance(book.get(key), list) or len(book[key]) < 3:
        book.pop(key, None)          # scalar or pre-8/13 format: re-derive
    if key not in book:
        wk1 = weekly_projections(season, 1).get(key) or {}
        val = src = None
        if keys[0] in PER_PLAYER_ONLY:
            val, src = _from_endpoint(key, season, keys)
        if val is None and keys[0].startswith("adp_idp"):
            # BEFORE the bulk feed, not after. The bulk weekly feed carries
            # adp_dd_ppr but not adp_idp_*, so asking it first lets a 1QB
            # redraft price answer for an IDP room and get stamped exact --
            # Josh Allen read 35 in a league whose real market has him at 16.
            # This is the identical poisoning this function's docstring
            # describes for superflex, in a new market.
            val, src = _from_season_agg(key, season, keys)
        if val is None:
            val, src = _pick_kv(wk1, keys)
        if val is None:
            val, src = _from_endpoint(key, season, keys)
        exact = val is not None
        if val is None and fallback:
            val, src = _pick_kv(wk1, fallback)
            exact = False
        book[key] = [val, exact, src]
        p.write_text(json.dumps(book), encoding="utf-8")
    return tuple(book[key][:2])


def adp_source(pid, season, keys, fallback=()):
    """Which key supplied this ADP. None if he is unpriced.

    Ask this instead of trusting `exact` when the market matters.
    """
    _adp(pid, season, keys, fallback)
    p = CACHE / f"adp_{season}_{keys[0]}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))[str(pid)][2]
    except Exception:
        return None


def adp_keys_for(roster_positions, dynasty_typed, keeper=False):
    """(keys, fallback) — the ADP market this room actually drafts in.

    ONE definition. This decision used to be written seven times across
    the toolkit in two variants, and when the keeper correction landed
    on 8/13 it reached board_data and not find, rookies or recap — so
    Josh Allen carried three different prices in one league on the same
    afternoon.

    A keeper league churns everyone but the kept few, so it drafts in
    the REDRAFT market even where Sleeper types it dynasty. That is the
    keepers.json `keeper` flag's whole job (CLAUDE.md lesson 5).

    Superflex rooms live in the 2QB market: QBs price WAY earlier
    (Allen 1.2 in 2QB vs 28.2 in 1QB PPR), so the 2QB key leads and the
    1QB chains stay as fallback.
    """
    rp = roster_positions or []
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    idp = any(p in rp for p in IDP_POS) or "IDP_FLEX" in rp
    dyn = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS) if sflex
           else DYNASTY_ADP_KEYS)
    red = ((("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS)
    if idp:
        # Defenders are priced in one market only. Lead with it and keep the
        # offence-only chains behind it, so a DL gets a real number and a WR
        # still falls through to the board everyone else is reading.
        red = (IDP_ADP_KEYS_SFLEX if sflex else IDP_ADP_KEYS) + red
    if dynasty_typed and not keeper:
        return dyn, red
    return red, (dyn if dynasty_typed else ())


def adp_of(pid, season):
    return _adp(pid, season, REDRAFT_ADP_KEYS)[0]


# ------------------------------------------------------------------ draft

def resolve_draft(lg, fetch=None):
    """(draft, picks) for the draft this league ACTUALLY ran.

    league.draft_id points at ONE draft and a league season can hold several.
    keeper.py learned this live in August -- the 2024 Hybrid ran a 7-rounder
    alongside the real 10-round startup where Daniels and BTJ were taken --
    and enumerated them. Nothing else did, so board, recap, managers and
    review all kept trusting league.draft_id.

    On 9/2 that came due. LG03's draft_id resolved to a
    draft marked COMPLETE with zero picks while 265 players sat on rosters,
    and the board answered "your slot: 8, next pick overall 8, 7 picks
    away" for a draft that finished on 8/18. keeper had told him "10 picks
    left" the same morning for the same reason.

    The order matters and is not "whichever has the most picks":

      1. A LIVE draft always wins. Mid-draft the in-progress draft may hold
         nine picks while last year's completed one holds 264, and picking
         the fatter one would break the board on the clock. This is the
         branch that must never regress.
      2. Otherwise, if league.draft_id has picks, keep it. LG01
         already resolves correctly and nothing should move for it.
      3. Only when the named draft is finished-but-empty do we enumerate
         and take the fullest draft of the same season.
      4. An empty PRE-draft is a legitimate empty state, not a lookup
         failure. Do not go hunting.

    `fetch` is injected by the tests; it defaults to the live client.
    """
    fetch = fetch or get
    did = lg.get("draft_id")
    draft = fetch(f"draft/{did}") if did else None
    picks = (fetch(f"draft/{did}/picks") or []) if draft else []
    status = (draft or {}).get("status") or ""

    if status in ("drafting", "paused"):
        return draft, picks                      # 1 — live wins, always
    if picks or status == "pre_draft" or not draft:
        return draft, picks                      # 2 and 4

    best = (draft, picks)                        # 3
    season = str(lg.get("season") or "")
    for d in fetch(f"league/{lg.get('league_id')}/drafts") or []:
        odid = d.get("draft_id")
        if not odid or odid == did:
            continue
        if season and str(d.get("season") or season) != season:
            continue
        op = fetch(f"draft/{odid}/picks") or []
        if len(op) > len(best[1]):
            best = (d, op)
    return best


def season_drafts(lg, fetch=None):
    """[(draft, picks)] for EVERY draft this league ran this season.

    resolve_draft answers "which draft" -- the one whose slot and pick
    geometry you are drafting against. This answers a different question:
    what happened this season. Both Hybrids run a TWO-STAGE draft, which
    keepers.json has said since August: a 10-round draft first, then a
    second one to fill rosters out because managers keep different
    numbers of players.

    So "the fullest draft of the season" is not a draft, it is a guess
    between two real ones. The 9/2 recap of LG03 graded
    120 picks and called it the draft; stage two was never in it.

    Ordered oldest first by start_time, falling back to the order the API
    returns. Each pick carries `_draft_id`, because a pick_no of 1 means
    something different in stage two than in stage one and nothing should
    silently add them together.
    """
    fetch = fetch or get
    season = str(lg.get("season") or "")
    listed = fetch(f"league/{lg.get('league_id')}/drafts") or []
    drafts, seen_ids = [], set()
    for d in listed:
        did = d.get("draft_id")
        if not did or did in seen_ids:
            continue
        if season and str(d.get("season") or season) != season:
            continue
        seen_ids.add(did)
        drafts.append(d)
    # league.draft_id may not appear in the listing; it is still a draft.
    own = lg.get("draft_id")
    if own and own not in seen_ids:
        d = fetch(f"draft/{own}")
        # Check the id the object REPORTS, not the one we asked for. A
        # test stub returning a canned draft for any draft/* path exposed
        # this by producing "draft 3 of 3" out of two drafts, with one
        # league's picks graded twice.
        got = (d or {}).get("draft_id") or own
        if d and got not in seen_ids:
            seen_ids.add(got)
            drafts.append(d)
    drafts.sort(key=lambda d: (d.get("start_time") or 0))

    out = []
    for d in drafts:
        did = d.get("draft_id")
        picks = [dict(pk, _draft_id=did)
                 for pk in (fetch(f"draft/{did}/picks") or [])]
        if picks:
            out.append((d, picks))
    return out


def season_picks(lg, fetch=None):
    """Every player taken this season, across all of the league's drafts.

    For the "is he gone" question, where membership is all that matters
    and pick numbers do not. Deduped: a player can only be taken once,
    and if two drafts disagree the earlier one wins.
    """
    out, seen = [], set()
    for _d, picks in season_drafts(lg, fetch=fetch):
        for pk in picks:
            pid = pk.get("player_id")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            out.append(pk)
    return out


def league_draft(league_id):
    lg = get(f"league/{league_id}")
    if not lg:
        raise SystemExit(f"league {league_id} not found")
    draft, picks = resolve_draft(lg)
    return lg, draft, picks


def my_slot(draft):
    return ((draft or {}).get("draft_order") or {}).get(uid() or "")


def my_owned_next_picks(draft, picks_made, roster_id, count=2):
    """Next `count` picks I ACTUALLY own: [(overall, round), ...].

    my_next_picks walks my SEAT forward and is blind to trades. He holds
    eleven picks in each Hybrid and ten seats, so the live board told him
    ten — while CLAUDE.md's own rule is to reread the live board every
    pick rather than trust the card (8/13).

    Falls back to the seat walk when the roster is unknown or the draft
    order has not published, because a seat is still better than nothing
    and my_draft_picks returns nothing at all in that case.
    """
    if roster_id is None:
        return my_next_picks(draft, picks_made, count)
    try:
        from battle_rhythm.sleeper_client import my_draft_picks
        owned, meta = my_draft_picks(draft, roster_id)
    except Exception:
        return my_next_picks(draft, picks_made, count)
    if not owned:
        return my_next_picks(draft, picks_made, count)
    teams = ((draft or {}).get("settings") or {}).get("teams") or 12
    return [(pk, (pk - 1) // int(teams) + 1)
            for pk in owned if pk > picks_made][:count]


def my_next_picks(draft, picks_made, count=2):
    """My next `count` picks by SEAT: [(overall, round), ...].

    Blind to traded picks on purpose — see my_owned_next_picks, which is
    what the turn plan uses. This one answers "when does my seat come up"
    and is the fallback when ownership cannot be resolved.
    """
    out, n = [], picks_made
    while len(out) < count:
        r = my_next_pick(draft, n)
        if not r:
            break
        out.append(r)
        n = r[0]
    return out


def injury_tag(meta):
    """Compact injury string from the player table, e.g. 'Q-groin', 'IR-knee'.
    Table is cached; during a live draft the board refreshes it when >6h old."""
    st = meta.get("injury_status")
    if not st:
        return ""
    part = (meta.get("injury_body_part") or "").lower()
    abbrev = {"Questionable": "Q", "Doubtful": "D", "Out": "OUT", "IR": "IR",
              "PUP": "PUP", "Sus": "SUS", "COV": "COV", "NA": "NA", "DNR": "DNR"}
    return f"{abbrev.get(st, st[:3])}{('-' + part) if part else ''}"


def my_next_pick(draft, picks_made):
    """Next overall pick number belonging to my slot.

    Honours settings.reversal_round (see sleeper_client.round_is_forward).
    A plain snake is reversal_round=0; LG03-LG05 runs 3, which inverts
    every round from 3 down and used to be computed wrong here.

    Still does NOT account for traded picks — my_owned_picks() does that,
    but this walks forward from an arbitrary point in a live draft, so it
    answers "when does my SEAT come up", not "which picks do I hold".
    """
    from battle_rhythm.sleeper_client import round_is_forward
    slot, slots = my_slot(draft), draft["settings"].get("teams") or len(draft.get("draft_order") or {})
    if not slot:
        return None
    rounds = draft["settings"]["rounds"]
    rev = (draft.get("settings") or {}).get("reversal_round") or 0
    n = picks_made
    while n < rounds * slots:
        n += 1
        rnd = (n - 1) // slots + 1
        pos = (n - 1) % slots + 1
        pick_slot = pos if round_is_forward(rnd, rev) else slots - pos + 1
        if pick_slot == slot:
            return n, rnd
    return None


def unavailable_ids(lg, picks):
    """Players you can't draft: already picked this draft + already rostered."""
    gone = {p["player_id"] for p in picks if p.get("player_id")}
    for r in get(f"league/{lg['league_id']}/rosters") or []:
        gone |= set(r.get("players") or [])
    return gone


# ------------------------------------------------------------------ board

_uid_cache = [None]
_roster_id_cache = {}


def uid():
    if _uid_cache[0] is None:
        _uid_cache[0] = (get(f"user/{USERNAME}") or {}).get("user_id")
    return _uid_cache[0]


def my_roster_id(league_id):
    """My roster_id in this league, or None.

    Ownership of a traded pick is recorded against a ROSTER, not a user,
    so nothing can resolve traded picks without this. Cached per league
    because `watch` asks once a poll.
    """
    lid = str(league_id)
    if lid not in _roster_id_cache:
        rid = None
        try:
            for r in get(f"league/{lid}/rosters") or []:
                if str(r.get("owner_id")) == str(uid()):
                    rid = r.get("roster_id")
                    break
        except Exception:
            rid = None
        _roster_id_cache[lid] = rid
    return _roster_id_cache[lid]


def replacement_levels(by_pos, demand_team, teams, gone_by_pos=None,
                       demand_floor=None):
    """{pos: points of the last player the league still has to start}.

    THE ONE IMPLEMENTATION. lineup_value grew a second copy on 8/13 and
    it was wrong in a way that produced no error: it used TOTAL league
    demand against the ALREADY-DEPLETED pool, double-counting the kept
    players. In the no-emoji Hybrid that put QB replacement at roughly
    one point, so Jalen Milroe — the corpse the whole fix existed to
    neutralise — sat above it and was left alone. Dak Prescott came back
    at +359 for the second time. Three copies of the pick geometry is
    how all three ended up wrong; this is the same mistake in a new
    place, caught within the hour only because the emoji league behaved
    differently from its twin.

    by_pos:       {pos: [season points of AVAILABLE players, any order]}
    demand_team:  {pos: starters per team, flex share included}
    gone_by_pos:  {pos: how many at that position are already off the
                  board}. Remaining demand is total minus gone, because
                  a kept starter is demand that has already been met.
    """
    teams = int(teams or 12)
    gone_by_pos = gone_by_pos or {}
    floor = int(demand_floor if demand_floor is not None else max(1, teams // 2))
    out = {}
    for pos, vals in by_pos.items():
        vals = sorted((v for v in vals if v and v > 0), reverse=True)
        if not vals:
            continue
        total_n = max(1, round(float(demand_team.get(pos, 0)) * teams))
        n = max(floor, total_n - min(int(gone_by_pos.get(pos, 0)), total_n - 1))
        out[pos] = vals[n - 1] if len(vals) >= n else vals[-1]
    return out


def board_data(league_id, with_adp=True, depth=120):
    """
    THE single computation behind every draft view — CLI board, dashboard
    pre-draft scenarios, dashboard in-flight target. One source of truth so the
    two surfaces can never disagree again (they did once; that was the bug).

    Returns a dict:
      lg, draft, picks, season, tbl, dynasty, adp_hdr,
      totals        {pid: availability-adjusted season pts, league scoring}
      rows          top `depth` available players, each a dict:
                    vorp, need_vorp, pts, pid, meta, adp, exact, inj, name
                    (need_vorp = vorp scaled by MY roster's unfilled starter
                     slots: unfilled position -> x1.0, filled -> x0.5,
                     K/DEF -> x0.1 until the last 2 rounds)
      next_picks    [(overall, round), ...] my next two picks, [] if no draft
      turn          two-pick plan dict {picks, now, next, waiting} or None —
                    pairs this pick with the next: prefers the high-value
                    player whose market price says he WON'T survive, banking
                    a survivor for the next slot. Unknown ADP = won't survive.
      market        [{adp, exact, pid, pts, meta, inj, name}] market-priced
                    names missing from rows' top 30
      remaining     {pos: count of available players proj >= 120}
    """
    lg, draft, picks = league_draft(league_id)
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    ptable = CACHE / "players_nfl.json"
    stale = ptable.exists() and time.time() - ptable.stat().st_mtime > 6 * 3600
    tbl = players(force=stale and (draft or {}).get("status") in ("drafting", "paused"))

    totals = season_projection_totals(season, scoring)

    rosters = get(f"league/{league_id}/rosters") or []
    gone = {p["player_id"] for p in picks if p.get("player_id")}
    mine = {p["player_id"] for p in picks
            if p.get("player_id") and str(p.get("picked_by")) == str(uid())}
    my_roster_id = None
    for r in rosters:
        gone |= set(r.get("players") or [])
        if r.get("owner_id") == uid():
            my_roster_id = r.get("roster_id")
            mine |= set(r.get("players") or [])

    # league demand FIRST, so the board can exclude positions this league
    # doesn't roster at all (a no-K/no-DEF league must never show K/DEF —
    # they used to sneak in via a default of 1 starter slot and outrank
    # real players on fake scarcity)
    flex_share_early = {"FLEX": {"RB": .40, "WR": .45, "TE": .15},
                        "WRRB_FLEX": {"RB": .5, "WR": .5}, "REC_FLEX": {"WR": .8, "TE": .2},
                        "SUPER_FLEX": {"QB": .85, "RB": .05, "WR": .10},
                        "IDP_FLEX": {"LB": .5, "DL": .3, "DB": .2}}
    demand_team = {}
    for slot in lg.get("roster_positions") or []:
        slot = SLOT_ALIAS.get(slot, slot)
        if slot in SEAT_POS:
            demand_team[slot] = demand_team.get(slot, 0) + 1
        elif slot in flex_share_early:
            for _p, _sh in flex_share_early[slot].items():
                demand_team[_p] = demand_team.get(_p, 0) + _sh
    rostered_pos = {pos for pos, n in demand_team.items() if n > 0}

    allrows = []
    for pid, pts in totals.items():
        if pid in gone or pts <= 0:
            continue
        meta = tbl.get(pid) or {}
        npos = norm_pos(meta, rostered_pos)
        if npos:
            # A COPY. tbl is the cached player table shared by every caller;
            # correcting it in place would leak this league's slot mapping
            # into all of them. Everything downstream reads meta["position"]
            # off this row, so the bars, the need model, the --pos filter and
            # the row dicts all see the league position with no further edits.
            allrows.append((pts, pid, dict(meta, position=npos)))
    allrows.sort(reverse=True)

    # replacement = Nth-best AVAILABLE at each position, N = REMAINING starter
    # demand (league demand minus starters already drafted/rostered, capped).
    teams = lg.get("total_rosters") or 12
    gone_by_pos = {}
    for pid in gone:
        pos = norm_pos(tbl.get(pid) or {}, rostered_pos)
        if pos:
            gone_by_pos[pos] = gone_by_pos.get(pos, 0) + 1
    by_pos = {}
    for pts, pid, meta in allrows:
        by_pos.setdefault(meta["position"], []).append(pts)
    # Floor remaining demand at teams//2 per position: in keeper leagues the
    # kept starters consume nearly all nominal starter demand, which used to
    # drive replacement to the single best available player and flatline VORP
    # (McConkey 274 proj scoring 2.4). Draft capacity is real demand even when
    # starter slots are spoken for — half-a-league of picks per position keeps
    # the ranking meaningful without inventing scarcity.
    replacement = replacement_levels(by_pos, demand_team, teams, gone_by_pos)

    # my roster's need factors (used by need_vorp and the turn plan)
    filled = {}
    for p in mine:
        pos = norm_pos(tbl.get(p) or {}, rostered_pos)
        if pos:
            filled[pos] = filled.get(pos, 0) + 1
    d_settings = (draft or {}).get("settings") or {}
    d_teams = d_settings.get("teams") or teams
    rounds_left = (d_settings.get("rounds") or 0) - (len(picks) // d_teams)

    def need_factor(pos):
        if pos in ("K", "DEF"):
            return 1.0 if 0 < rounds_left <= 2 else 0.1
        # >= 0.5 unfilled slots counts as real need. Flex shares are fractional
        # (TE demand 1.3 etc.), so a strict > 0 test never marks a position
        # filled -- which is how a 36-year-old second TE once got recommended
        # at full weight over live needs. Half a slot is the line.
        return 1.0 if demand_team.get(pos, 0) - filled.get(pos, 0) >= 0.5 else 0.5

    settings = lg.get("settings") or {}
    dynasty = settings.get("type") == 2
    # SLEEPER'S OWN TYPE DOES NOT DISTINGUISH A KEEPER LEAGUE FROM A
    # DYNASTY ONE. Both Hybrids are type 2 and both churn everyone but
    # seven, so they price off the REDRAFT market, not dynasty. That
    # distinction lives in keepers.json's manual `keeper` flag, which
    # lineup_value has always read and this board never did — so the
    # board priced Derrick Henry at dADP 83 while the market he is
    # actually drafted in has him at 46, and depleted, at 12. A
    # 71-pick error on every survival call in both rooms (8/13).
    keeper = settings.get("type") == 1
    try:
        keeper = keeper or bool(json.loads(
            _paths.data("keepers.json").read_text(encoding="utf-8"))
            .get(str(league_id), {}).get("keeper"))
    except Exception as e:
        print(f"   WARNING: could not read keepers.json ({e}); if this is "
              f"a keeper league the ADP market below is the wrong one.")
    if dynasty and keeper:
        dynasty = False          # price it like the redraft it behaves as
    rp = lg.get("roster_positions") or []
    superflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    # One definition, in adp_keys_for(). `dynasty` has already been
    # flipped false above for keeper leagues, so pass keeper=False here
    # and let the flip stand rather than applying it twice.
    adp_keys, adp_fallback = adp_keys_for(rp, dynasty, keeper=False)
    adp_hdr = "dADP" if dynasty else "ADP"

    ranked = sorted(((round(pts - replacement[m["position"]], 1), pts, pid, m)
                     for pts, pid, m in allrows), reverse=True)
    rows = []
    for vorp, pts, pid, meta in ranked[:depth]:
        adp, exact = _adp(pid, season, adp_keys, adp_fallback) if with_adp else (None, True)
        # dynasty-typed leagues also carry the redraft market: the
        # dADP/rADP gap is the age premium. In superflex the honest
        # redraft comparator is the 2QB redraft market, not 1QB.
        radp_keys = ((("adp_2qb",) + REDRAFT_ADP_KEYS) if superflex
                     else REDRAFT_ADP_KEYS)
        radp = (_adp(pid, season, radp_keys)[0]
                if (with_adp and dynasty) else None)
        rows.append({"vorp": vorp, "pts": pts, "pid": pid, "meta": meta,
                     "adp": adp, "exact": exact, "radp": radp,
                     "inj": injury_tag(meta),
                     "name": name_of(pid, tbl),
                     "need_vorp": round(vorp * need_factor(meta["position"]), 1)})

    # KEEPER DEPLETION. ADP is a price from drafts where everyone was
    # available. These rooms remove ~5-7 players per team before a pick
    # is made, so a market price of 60 is really 60 minus the kept
    # players ranked above it — dozens of picks in a 12-team Hybrid, and
    # the difference between "he lasts to my turn" and "he went two
    # rounds ago". lineup_value has done this since 8/11; this board
    # never did, and told him Drake London would wait past pick 17 when
    # his depleted price is 5 (8/13). Keeps the market number as
    # 'adp_raw' so the display can show both.
    kept_adps, n_kept = [], 0
    if with_adp and gone:
        for pid in gone:
            m = tbl.get(pid) or {}
            if norm_pos(m, rostered_pos) is None:
                continue
            n_kept += 1
            v = _adp(pid, season, adp_keys, adp_fallback)[0]
            if v is not None:
                kept_adps.append(v)
        from battle_rhythm.lineup_value import deplete_adp
        deplete_adp(rows, kept_adps)
    depletion = {"kept": n_kept, "priced": len(kept_adps)}

    next_picks = (my_owned_next_picks(draft, len(picks), my_roster_id, 2)
                  if draft and my_slot(draft) else [])
    turn = None
    needs_open = [pos for pos in demand_team
                  if pos not in ("K", "DEF")
                  and demand_team.get(pos, 0) - filled.get(pos, 0) >= 0.5]
    # K and DEF are excluded from needs_open on purpose: you do not want the
    # need model chasing a defense in round 4. But needs_open ALSO gated the
    # depth-phase banner, so the banner printed "starters filled" with a
    # required slot empty -- it did that through two live LG01 picks
    # (ROADMAP P1 #5). Harmless in the Hybrids, which roster neither. LG02
    # Bros rosters BOTH. Two different questions, two different lists.
    required_open = [pos for pos in ("K", "DEF")
                     if demand_team.get(pos, 0) - filled.get(pos, 0) >= 0.5]
    if (draft and len(next_picks) == 2 and not needs_open and mine
            and draft.get("status") in ("drafting", "paused")):
        # DEPTH PHASE: every starting slot is covered. The turn-plan objective
        # (fill starters with points) is exhausted — recommending here would
        # just surface shallow-position leftovers (the Kelce/Kittle effect).
        # Hand off to judgment tools instead of pretending to have an answer.
        turn = {"phase": "depth", "picks": (next_picks[0][0], next_picks[1][0]),
                "required_open": required_open}
    elif draft and len(next_picks) == 2 and draft.get("status") in ("drafting", "paused", "pre_draft"):
        now_p, next_p = next_picks[0][0], next_picks[1][0]
        # SAME MARKET INPUT AS draft_live. Until 9/6 this module priced
        # survival off ADP while the live board priced it off consensus rank,
        # so `board lg04` called Saquon "priced to wait" (ADP 36) on the
        # morning `live` had him at 0% (consensus 13). He went 8th in LG02
        # Bros. One question, two answers, on a draft clock.
        from battle_rhythm import ext_tiers as _ext
        for _r in rows:
            _r["pos"] = _r["meta"]["position"]
        # Use annotate() and CHECK WHAT IT RETURNS. The first version of this
        # hand-rolled the lookup and threw the match count away -- which is
        # the one thing that would have caught it keying a decorated name
        # ("Saquon Barkley (RB, PHI)") and matching zero rows, silently, so
        # the board kept printing ADP while claiming to be aligned.
        _hit, _tot = _ext.annotate(rows)
        if _tot and not _hit:
            print("  ! no player matched the external tier board — survival "
                  "is falling back to ADP. Check data/tiers/.")
        for _r in rows:
            _r["mkt"] = _ext.market_pos(_r)
        pool = sorted(rows[:20], key=lambda r: -r["need_vorp"])[:15]

        # A player the market takes BEFORE your pick is not a plan, he is a
        # wish. Pre-draft this mattered and nothing checked it: with 0 picks
        # made and pick 10, the banner read "now: Jahmyr Gibbs" -- ADP 1.0,
        # nine picks ahead of the user's first. The board underneath was
        # right; the sentence on top named a player who could not be there.
        # (ROADMAP: "tests catch bad math, they do not catch a true number
        # with a false label".)
        #
        # The test is NOT adp < now_p. Mid-draft a still-available player
        # priced well above your pick has already been passed over by the
        # room -- he has fallen, and he is the value, not the wish. He is
        # presumed gone only if the market takes him in picks that have not
        # happened yet: between the picks already made and your turn.
        made = len(picks)

        def _presumed_gone(c):
            return bool(c["mkt"]) and made <= c["mkt"] < now_p

        reachable = [c for c in pool if not _presumed_gone(c)]
        falling = [c for c in pool if _presumed_gone(c)]
        survivors = [c for c in reachable if c["mkt"] and c["mkt"] >= next_p + 3]
        if survivors:
            best, best_val, best_partner = None, -1, None
            for c in reachable:
                others = [s for s in survivors if s["pid"] != c["pid"]]
                pr = max(others, key=lambda s: s["need_vorp"]) if others else None
                val = c["need_vorp"] + (pr["need_vorp"] if pr else 0)
                if val > best_val:
                    best, best_val, best_partner = c, val, pr
            # Exclude BOTH named picks, not just the partner. `waiting` means
            # "the market says he is still there at your next turn, so he is
            # not the reason to spend this pick" -- which is the opposite of
            # what "now:" means. Printing the same man in both lines is the
            # true-number/false-label class again: at LG02 pick 13 the
            # plan read "now: Derrick Henry" and "also priced to wait: Derrick
            # Henry (ADP 23)" three lines apart. The pick was right; the page
            # contradicted itself, and a draft clock is not when to work out
            # which line to believe.
            _named = {c["pid"] for c in (best, best_partner) if c}
            waiting = [c for c in survivors[:5] if c["pid"] not in _named]
            turn = {"picks": (now_p, next_p), "now": best,
                    "next": best_partner, "waiting": waiting[:4],
                    "falling": sorted(falling, key=lambda c: -c["need_vorp"])[:3]}

    market = []
    if with_adp:
        seen = {r["pid"] for r in rows[:30]}
        cands = []
        for pid, wk1 in weekly_projections(season, 1).items():
            if pid in gone or pid in seen:
                continue
            mkt_pos = OFF_POS + tuple(p for p in IDP_POS if p in rostered_pos)
            if norm_pos(tbl.get(pid) or {}, mkt_pos) is None:
                continue
            adp = _pick(wk1, adp_keys + adp_fallback)
            if adp:
                cands.append((adp, pid))
        cands.sort()
        for _, pid in cands[:20]:
            adp, exact = _adp(pid, season, adp_keys, adp_fallback)
            if adp:
                meta = tbl.get(pid) or {}
                market.append({"adp": adp, "exact": exact, "pid": pid,
                               "pts": totals.get(pid, 0.0), "meta": meta,
                               "inj": injury_tag(meta), "name": name_of(pid, tbl)})
        market.sort(key=lambda m: m["adp"])
        market = market[:12]

    remaining = defaultdict(int)
    for pts, pid, meta in allrows:
        if pts >= 120:
            remaining[meta.get("position")] += 1

    return {"lg": lg, "draft": draft, "picks": picks, "season": season,
            "tbl": tbl, "dynasty": dynasty, "keeper": keeper,
            "superflex": superflex, "adp_hdr": adp_hdr,
            "totals": totals, "rows": rows, "next_picks": next_picks,
            "turn": turn, "market": market, "remaining": dict(remaining),
            "depletion": depletion,
            "my_pids": mine, "gone": gone,
            # per-position replacement level (points of the Nth-best
            # available). Additive: consumed by dynasty_value's surplus
            # model; nothing inside board_data reads it back.
            "replacement": replacement}


def board(league_id, pos_filter=None, top=30, with_adp=True):
    d = board_data(league_id, with_adp=with_adp)
    lg, draft, picks, tbl = d["lg"], d["draft"], d["picks"], d["tbl"]
    adp_hdr = d["adp_hdr"]

    print(f"{lg['name']} — {draft['status'] if draft else 'no draft'} — "
          f"{len(picks)} picks made")
    print("   proj is AVAILABILITY-ADJUSTED: ~7-10% below what Sleeper "
          "displays,\n   which assumes every player plays every game "
          "(measured 8/13, nine QBs).")
    # SAY WHICH MARKET, ALWAYS. The board silently priced both Hybrids
    # off dynasty because Sleeper types them 2; they churn everyone but
    # seven and actually draft in the redraft market. A header that names
    # the market is the only way that shows up without a second tool to
    # compare against.
    mkt = ("DYNASTY" if d["dynasty"] else "REDRAFT")
    print(f"   ADP market: {mkt}"
          + (" 2QB/superflex" if d["superflex"] else " 1QB")
          + (" — keeper league, priced as redraft" if d["keeper"]
             and (lg.get("settings") or {}).get("type") == 2 else ""))
    dep = d.get("depletion") or {}
    if dep.get("priced"):
        print(f"   {dep['kept']} players are already rostered and never reach "
              f"the draft;\n   {dep['priced']} of them carry a price, so every "
              f"ADP below is SHIFTED EARLIER by\n   the kept players ranked "
              f"above it. These are depleted numbers, not market ones.")
    # A finished draft has no next pick. next_picks is arithmetic off the
    # seat and happily produces one anyway: on 9/2 a COMPLETE draft printed
    # "your slot: 8 — next pick: overall 8 (round 1), 7 picks away". The
    # numbers were all correct for a draft that was not happening.
    if (draft or {}).get("status") == "complete":
        print(f"this draft is DONE ({len(picks)} picks). There is no next pick.")
        print("   for what to do with it:  python br.py recap <league>")
    elif d["next_picks"]:
        n0 = d["next_picks"][0]
        print(f"your slot: {my_slot(draft)} — next pick: overall {n0[0]} (round {n0[1]}), "
              f"{n0[0] - len(picks) - 1} picks away")
    print()

    rows = [r for r in d["rows"]
            if not pos_filter or r["meta"].get("position") == pos_filter.upper()]
    print(f"{'#':>3} {'vorp':>7} {'proj':>7} {adp_hdr:>7} {'age':>4} {'inj':>9}  player")
    for i, r in enumerate(rows[:top], 1):
        adp_s = (f"{r['adp']:>6.1f}{' ' if r['exact'] else 'r'}"
                 if r["adp"] else "      -")
        print(f"{i:>3} {r['vorp']:>7.1f} {r['pts']:>7.1f} {adp_s} "
              f"{str(r['meta'].get('age') or '?'):>4} {r['inj']:>9}  {r['name']}")

    t = d["turn"]
    if t and t.get("phase") == "depth":
        ro = t.get("required_open") or []
        head = ("starters filled — DEPTH PHASE" if not ro else
                f"skill slots filled, {' and '.join(ro)} STILL EMPTY")
        print(f"\nTURN PLAN (picks {t['picks'][0]} and {t['picks'][1]}): {head}")
        if ro:
            print(f"  {' and '.join(ro)} is a required starting slot and you do")
            print("  not have one. It is still a late pick -- the need model")
            print("  leaves it out so the board does not chase it in round 4 --")
            print("  but do not read the line below as 'nothing left to do'.")
        print("  the need model has nothing left to optimize; from here value is")
        print("  deployment odds, age, and taxi fit — judgment calls. Use:")
        print("    rookies <league_id>   (taxi shelf & young upside)")
        print("    board --pos WR / RB   (deep positional value)")
        print("    dashboard depth board (Flex slicer for starter-beaters)")
    elif t:
        print(f"\nTURN PLAN (picks {t['picks'][0]} and {t['picks'][1]}, "
              "need-adjusted):")
        inj = f", {t['now']['inj']}" if t["now"]["inj"] else ""
        print(f"  now:  {t['now']['name']}  (need-vorp {t['now']['need_vorp']:.1f}{inj})")
        # Quote the number the DECISION used and name its source. Printing
        # ADP beside a call made on consensus rank is the true-number/false-
        # label failure one more time, and it is the reason this whole
        # section is being touched.
        def _src(c):
            return "ECR" if c.get("bc_rank") else adp_hdr

        if t["next"]:
            print(f"  next: {t['next']['name']}  (need-vorp {t['next']['need_vorp']:.1f}, "
                  f"{_src(t['next'])} {t['next']['mkt']:.1f} says he waits past "
                  f"pick {t['picks'][1]})")
        if t.get("falling"):
            print("  only if he falls: "
                  + ", ".join(f"{c['name'].split(' (')[0]} ({_src(c)} {c['mkt']:.0f})"
                              for c in t["falling"])
                  + f" — the market takes them before {t['picks'][0]}")
        if t["waiting"]:
            print("  also priced to wait: "
                  + ", ".join(f"{c['name'].split(' (')[0]} ({_src(c)} {c['mkt']:.0f})"
                              for c in t["waiting"]))

    if d["market"]:
        print(f"\nmarket board ({adp_hdr}-priced names NOT in the list above):")
        for m in d["market"]:
            print(f"    {adp_hdr} {m['adp']:>6.1f}{' ' if m['exact'] else 'r'} "
                  f"proj {m['pts']:>6.1f}  age {str(m['meta'].get('age') or '?'):>3} "
                  f"{m['inj']:>9}  {m['name']}")

    print("\nremaining by position (proj >= 120 season pts under this scoring):")
    print("   " + "  ".join(f"{p}:{n}" for p, n in sorted(d["remaining"].items())))
    return [(r["pts"], r["pid"], r["meta"]) for r in rows]



def sheet(league_id, top=200):
    """Pre-draft cheat sheet: full board to a file, no live-draft framing."""
    rows = board(league_id, top=top)
    lg = get(f"league/{league_id}")
    if not lg:
        raise SystemExit(f"league {league_id} not found")
    tbl = players()
    # out/<slug>/cheatsheet.txt. Keyed on the id, never the name:
    # both Hybrids normalize to the same string. paths.py --selftest
    # fails if this line ever goes back to a bare relative path.
    out = _paths.league_out(league_id, "cheatsheet.txt")
    season = lg.get("season")
    with out.open("w", encoding="utf-8") as f:
        f.write(f"{lg['name']} — season {season} — scored by this league's rules\n\n")
        for i, (pts, pid, meta) in enumerate(rows[:top], 1):
            adp = adp_of(pid, season)
            f.write(f"{i:>3}  {pts:>7.1f}  adp {adp or '-':>6}  {name_of(pid, tbl)}\n")
    print(f"\nwrote {out}")


_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _norm_name(s):
    """Suffix-stripped, punctuation-free, casefolded name key —
    'Kenneth Walker III' and 'kenneth walker' both -> 'kennethwalker'."""
    import unicodedata as _ud
    s = _ud.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if c.isalnum() or c.isspace()).casefold()
    return "".join(w for w in s.split() if w not in _NAME_SUFFIXES)


def player_hits(tbl, query):
    """Match players by normalized name, honoring a trailing position or team
    hint ('kenneth walker rb', 'walker kc'). Returns (hits, hint_desc)."""
    tokens = str(query or "").split()
    hint_pos = hint_team = None
    if tokens and tokens[-1].upper() in SEAT_POS and len(tokens) > 1:
        hint_pos = tokens.pop().upper()
    elif (tokens and len(tokens) > 1 and 2 <= len(tokens[-1]) <= 3
          and tokens[-1].isalpha() and tokens[-1].upper() == tokens[-1]
          and tokens[-1].lower() not in _NAME_SUFFIXES):
        hint_team = tokens.pop().upper()
    key = _norm_name(" ".join(tokens))
    if not key:
        return [], ""
    hits = []
    for pid, m in tbl.items():
        if not isinstance(m, dict) or norm_pos(m, SEAT_POS) is None:
            continue
        full = m.get("full_name") or f"{m.get('first_name', '')} {m.get('last_name', '')}"
        nk = _norm_name(full)
        if key == nk or key in nk:
            hits.append((pid, m))
    if hint_pos:
        hits = [(pid, m) for pid, m in hits
                if norm_pos(m, SEAT_POS) == hint_pos or m.get("position") == hint_pos]
    if hint_team:
        hits = [(pid, m) for pid, m in hits if m.get("team") == hint_team]
    active = [(pid, m) for pid, m in hits if m.get("team")]
    if active and len(active) < len(hits):
        hits = active
    hint = " ".join(x for x in (hint_pos, hint_team) if x)
    return hits, hint


def find(league_id, query):
    """Price specific players by name under one league's rules.
    python draft_helper.py find <league_id> "mcconkey" "brian thomas" ...
    Shows projection, dynasty/redraft ADP, age, and drafted/available status —
    for building queues from names, and for catching feed coverage holes
    (a star with proj 0.0 means the projections feed is missing him)."""
    lg, draft, picks = league_draft(league_id)
    assert lg is not None  # league_draft raises on missing league
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()
    totals = season_projection_totals(season, scoring)
    gone = unavailable_ids(lg, picks)
    dynasty = (lg.get("settings") or {}).get("type") == 2
    # Was `DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS` — no keeper
    # flag, no superflex key. In LG03-LG05 that answered adp_dynasty_ppr
    # and priced Josh Allen at 6.7 while the board said 29.0 and the real
    # 2QB market said 1.2.
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            _keeper_flag(league_id))

    for q in query:
        hits, _hint = player_hits(tbl, q)
        if not hits:
            print(f"  no player matching '{q}'")
            continue
        for pid, m in sorted(hits, key=lambda h: -totals.get(h[0], 0))[:5]:
            adp, exact = _adp(pid, season, keys, fb)
            adp_s = f"{adp:.1f}{'' if exact else 'r'}" if adp else "-"
            status = "GONE" if pid in gone else "available"
            proj = totals.get(pid, 0.0)
            hole = "   <-- proj 0: feed missing him?" if proj == 0 and status == "available" else ""
            inj = injury_tag(m)
            print(f"  {name_of(pid, tbl):<40} proj {proj:>6.1f}  "
                  f"{'dADP' if dynasty else 'adp'} {adp_s:>7}  "
                  f"age {str(m.get('age') or '?'):>3}  {inj:>9}  {status}{hole}")


def explain(league_id, query):
    """Decompose a player's season projection into per-stat contributions.
    python draft_helper.py explain <league_id> "higgins"
    Shows: each stat key the league scores, projected season volume, multiplier,
    and points contributed — so an 'inflated' total can be audited line by line
    against what the app shows. Keys projected but NOT scored by this league
    print at the bottom (they contribute zero; if the app disagrees, the
    difference lives in the scored list)."""
    lg = get(f"league/{league_id}")
    if not lg:
        raise SystemExit(f"league {league_id} not found")
    season = lg.get("season") or state().get("season")
    scoring = lg.get("scoring_settings") or {}
    tbl = players()
    hits, _hint = player_hits(tbl, query)
    if not hits:
        raise SystemExit(f"no player matching '{query}' — try adding position "
                         "or team, e.g. 'kenneth walker rb' or 'walker kc'")
    if len(hits) > 1:
        opts = "; ".join(name_of(pid, tbl) for pid, _m in hits[:6])
        raise SystemExit(f"'{query}' is ambiguous: {opts} — add position or team")
    from collections import defaultdict
    for pid, m in hits[:1]:
        vol = defaultdict(float)
        weeks = 0
        for wkn in range(1, 19):
            stats = weekly_projections(season, wkn).get(pid)
            if stats:
                weeks += 1
                for k, v in stats.items():
                    if isinstance(v, (int, float)):
                        vol[k] += v
        print(f"{name_of(pid, tbl)} — {lg.get('name')} — {weeks} projected weeks\n")
        rows = [(vol[k] * scoring[k], vol[k], scoring[k], k)
                for k in vol if scoring.get(k)]
        rows.sort(reverse=True)
        total = 0.0
        print(f"  {'stat':<16}{'season vol':>11}{'x mult':>8}{'points':>9}")
        for pts, v, mult, k in rows:
            total += pts
            print(f"  {k:<16}{v:>11.1f}{mult:>8.2f}{pts:>9.2f}")
        ratio = availability_ratios(season).get(pid, 1.0)
        print(f"  {'raw sum':<16}{'':>11}{'':>8}{total:>9.1f}")
        print(f"  {'availability':<16}{'':>11}{'':>8}{ratio:>9.2f}")
        print(f"  {'TOTAL (board)':<16}{'':>11}{'':>8}{total * ratio:>9.1f}")
        unscored = sorted(k for k in vol if not scoring.get(k))
        print(f"\n  projected but unscored here (0 pts): {', '.join(unscored)}")


def rookies(league_id, top=25):
    """
    python draft_helper.py rookies <league_id>
    Every AVAILABLE 2026-class rookie either feed knows about: league-scored
    projection (availability-adjusted), dynasty price (exact per-player), age,
    injury tag. Sorted by projection; the bottom section lists rookies the
    projections rate near zero but the market still prices — pure taxi
    lottery tickets. A rookie in neither feed is invisible to this tool:
    cross-check the app's own rankings in the last rounds.
    """
    d = board_data(league_id, with_adp=False, depth=50)
    tbl, season = d["tbl"], d["season"]
    dynasty = d["dynasty"]
    # board_data has already applied the keeper flip to d["dynasty"].
    keys, fb = adp_keys_for((d.get("lg") or {}).get("roster_positions"),
                            dynasty, keeper=False)
    adp_hdr = "dADP" if dynasty else "adp"
    wk1 = weekly_projections(season, 1)

    cands = []
    for pid, m in tbl.items():
        if not isinstance(m, dict) or m.get("years_exp") != 0:
            continue
        if m.get("position") not in ("QB", "RB", "WR", "TE"):
            continue
        if not m.get("team") or pid in d["gone"]:
            continue
        proj = d["totals"].get(pid, 0.0)
        bulk = _pick(wk1.get(pid) or {}, REDRAFT_ADP_KEYS)
        if proj <= 0 and not bulk:
            continue  # invisible to both feeds
        cands.append((proj, bulk, pid, m))
    cands.sort(key=lambda c: (-c[0], c[1] or 999))

    print(f"available 2026 rookies — {d['lg']['name']} scoring "
          f"({len(cands)} known to the feeds)\n")
    print(f"{'proj':>7} {adp_hdr:>7} {'age':>4} {'inj':>9}  player")
    shown = 0
    for proj, bulk, pid, m in cands:
        if shown >= top:
            break
        adp, exact = _adp(pid, season, keys, fb)
        adp_s = f"{adp:>6.1f}{' ' if exact else 'r'}" if adp else "      -"
        print(f"{proj:>7.1f} {adp_s} {str(m.get('age') or '?'):>4} "
              f"{injury_tag(m):>9}  {name_of(pid, tbl)}")
        shown += 1
    ghosts = [(bulk, pid, m) for proj, bulk, pid, m in cands if proj <= 25 and bulk]
    ghosts.sort()
    if ghosts:
        print("\nmarket-priced, near-zero projection (taxi lottery tickets):")
        for bulk, pid, m in ghosts[:10]:
            adp, exact = _adp(pid, season, keys, fb)
            adp_s = f"{adp:.1f}{'' if exact else 'r'}" if adp else f"{bulk:.1f}r"
            print(f"    {adp_hdr} {adp_s:>7}  age {str(m.get('age') or '?'):>3} "
                  f"{injury_tag(m):>9}  {name_of(pid, tbl)}")


def recap(league_id):
    """
    python draft_helper.py recap <league_id>
    Per-manager draft-behavior profile from picks made so far: average age
    drafted, average reach vs dynasty price (positive = paid picks-early),
    split by vets (27+) and youth (<=23). This is the trade-season map:
    vet-hungry managers are the market for your aging assets; youth-hoarders
    are who you buy veterans from at the deadline. Mid-draft samples are
    small — labels firm up as picks accumulate.
    """
    lg, draft, picks = league_draft(league_id)
    season = lg.get("season") or state().get("season")
    tbl = players()
    dynasty = (lg.get("settings") or {}).get("type") == 2
    keys, fb = adp_keys_for(lg.get("roster_positions"), dynasty,
                            _keeper_flag(league_id))
    users = {u.get("user_id"): (u.get("display_name") or "?")
             for u in (get(f"league/{league_id}/users") or [])}

    prof = {}
    for pk in picks:
        pid, who = pk.get("player_id"), str(pk.get("picked_by"))
        if not pid:
            continue
        meta = tbl.get(pid) or {}
        age = meta.get("age")
        adp, _ex = _adp(pid, season, keys, fb)
        reach = (adp - pk.get("pick_no", 0)) if adp else None
        rec = prof.setdefault(who, {"n": 0, "ages": [], "r_all": [],
                                    "r_vet": [], "r_yth": []})
        rec["n"] += 1
        if age:
            rec["ages"].append(age)
        if reach is not None:
            rec["r_all"].append(reach)
            if age and age >= 27:
                rec["r_vet"].append(reach)
            elif age and age <= 23:
                rec["r_yth"].append(reach)

    def avg(v):
        return sum(v) / len(v) if v else None

    def fmt(v):
        return f"{v:+5.1f}" if v is not None else "    -"

    print(f"{lg.get('name')} — manager profiles after {len(picks)} picks")
    print("reach = dynasty price minus pick taken (positive = paid early)\n")
    print(f"{'manager':<18}{'picks':>6}{'avg age':>9}{'reach':>7}"
          f"{'vets27+':>9}{'yth<=23':>9}  read")
    rows = []
    for who, rec in prof.items():
        a, r, rv, ry = avg(rec["ages"]), avg(rec["r_all"]), avg(rec["r_vet"]), avg(rec["r_yth"])
        label = ""
        if rv is not None and ry is not None:
            if rv - ry > 8:
                label = "vet-hungry — sell them your aging assets"
            elif ry - rv > 8:
                label = "youth-hoarder — buy their vets cheap"
        elif rv is not None and rv > 8:
            label = "vet-hungry — sell them your aging assets"
        elif ry is not None and ry > 8:
            label = "youth-hoarder — buy their vets cheap"
        rows.append((rv if rv is not None else -999, who, rec, a, r, rv, ry, label))
    rows.sort(reverse=True)
    me = uid()
    for _, who, rec, a, r, rv, ry, label in rows:
        name = users.get(who, who[:12])
        star = " (you)" if who == str(me) else ""
        print(f"{(name + star):<18}{rec['n']:>6}{(f'{a:.1f}' if a else '-'):>9}"
              f"{fmt(r):>7}{fmt(rv):>9}{fmt(ry):>9}  {label}")


def watch(league_id, pos_filter=None, interval=90):
    """
    python draft_helper.py watch <league_id> [--every 60]
    Live-draft watch: polls the draft, reprints the board only when new picks
    land, and rings the terminal bell when you're within 3 picks (insistently
    when you're ON the clock). Ctrl+C to stop. Poll cost is ~3 small API calls
    per interval — far under the rate limit at any sane setting.
    """
    last = -1
    print(f"watching draft (every {interval}s, Ctrl+C to stop)...")
    while True:
        try:
            lg, draft, picks = league_draft(league_id)
        except Exception as e:
            print(f"[watch] fetch failed ({e}); retrying in {interval}s")
            time.sleep(interval)
            continue
        n = len(picks)
        status = (draft or {}).get("status")
        if n != last:
            stamp = time.strftime("%H:%M:%S")
            if last >= 0:
                tbl = players()
                for pk in picks[last:]:
                    print(f"[{stamp}] pick {pk.get('pick_no')}: "
                          f"{name_of(pk.get('player_id'), tbl)}")
            print(f"\n{'='*72}\n[{stamp}] {n} picks — rebuilding board\n")
            board(league_id, pos_filter=pos_filter)
            last = n
            # THE ALARM MUST KNOW ABOUT TRADED PICKS. my_next_picks walks
            # my seat, so a pick traded TO me never rings — he owns 8.11
            # in the no-emoji Hybrid, three behind his own 8.8, and would
            # have been on the clock with no sound while running a second
            # draft in another window (8/13).
            nxts = (my_owned_next_picks(draft, n, my_roster_id(league_id), 1)
                    if my_slot(draft) else [])
            if nxts:
                away = nxts[0][0] - n - 1
                if away == 0:
                    print(f"\a\a\a*** YOU ARE ON THE CLOCK — pick {nxts[0][0]} ***")
                elif away <= 3:
                    print(f"\a*** {away} picks until you are up (pick {nxts[0][0]}) ***")
        if status == "complete":
            print("draft complete.")
            return
        time.sleep(interval)


def cli_league(arg):
    """Accept a slug, an alias, or a raw id -- same as every other entry point.

    This module took a raw league id and nothing else, so
    `br.py board lg04` asked Sleeper for a league literally NAMED
    "lg04" and exited "league lg04 not found", while
    `br.py live --league lg04` resolved it fine. One identity, two
    resolvers, different answers -- the exact split leagues/_index.json was
    created to close, surviving here because the id path is what gets typed
    in testing and the slug is what gets typed on draft morning. CLAUDE.md
    tells you to run `board <league>` before the draft.

    Digits pass through untouched: id_for() only knows slugs and aliases,
    and a 19-digit id is not one.
    """
    if str(arg).isdigit():
        return arg
    from battle_rhythm import paths as _p
    hit = _p.id_for(arg)
    if not hit:
        raise SystemExit(f"no league matching {arg!r}. known: "
                         + ", ".join(sorted(_p.leagues())))
    return hit


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("board", "sheet", "find", "explain", "watch", "rookies", "recap"):
        raise SystemExit(__doc__)
    lid = cli_league(sys.argv[2])
    if sys.argv[1] == "find":
        find(lid, sys.argv[3:] or [""])
        sys.exit()
    if sys.argv[1] == "explain":
        explain(lid, " ".join(sys.argv[3:]))
        sys.exit()
    if sys.argv[1] == "rookies":
        rookies(lid)
        sys.exit()
    if sys.argv[1] == "recap":
        recap(lid)
        sys.exit()
    pos = None
    if "--pos" in sys.argv:
        pos = sys.argv[sys.argv.index("--pos") + 1]
    if sys.argv[1] == "watch":
        every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 90
        watch(lid, pos_filter=pos, interval=every)
    elif sys.argv[1] == "board":
        board(lid, pos_filter=pos)
    else:
        sheet(lid)
