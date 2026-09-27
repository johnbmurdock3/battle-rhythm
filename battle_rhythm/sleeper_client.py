"""
Sleeper multi-league client — iteration 2.

Iteration 1 goals, now confirmed against the live API (2026-08-09):
  1. One username resolves to all leagues.       VERIFIED — 5 leagues for dirtymurdock.
  2. Player table caches to disk.                 Unchanged; DEF shape verified (see name_of).
  3. Scoring computed from each league's rules.   VERIFIED — dot product matches Sleeper's
     own players_points exactly on 4 ground-truth cases: QB w/ first-down scoring (18.03),
     RB w/ reception buckets (29.20), two DEFs incl. a negative total (5.00, -3.00).
     Stat keys and scoring_settings keys share one vocabulary. Keys present in a stat
     line but absent from a league's scoring_settings contribute 0, which is correct —
     stat lines carry non-scoring junk (pos_rank_*, pts_ppr, snap counts, fan_pts_allow_*).

What changed since iteration 1:
  - SEASON now defaults to /state/nfl at runtime instead of a hardcoded string.
  - name_of(): team defenses ARE in the player table, keyed by abbreviation
    ("SF" -> {position: "DEF", first_name: "San Francisco", ...}). The old guard
    stays only as a fallback for table-miss.
  - FAAB display gated on settings.waiver_type == 2. LG02 carries a
    waiver_budget of 100 but waiver_type 0 (reverse standings order) — the budget
    number is meaningless there. waiver_budget / waiver_budget_used both confirmed real.
  - League status handled: pre_draft / drafting leagues have thin or empty rosters.
  - verify_scoring(): repeatable harness that re-proves the dot product on any
    finished league-week by diffing our score() against Sleeper's players_points.
    Raw per-player stat lines come from api.sleeper.com (the host the app itself
    uses; undocumented but stable in practice — flag if it drifts).

Run:  python sleeper_client.py            # report
      python sleeper_client.py verify     # scoring harness vs 2025 Hybrid 14 wk 17
"""

import json
import os
import sys
import time
from battle_rhythm import paths as _paths
import pathlib
import urllib.request
import urllib.error
from collections import defaultdict


def _force_utf8_stdout():
    """Windows: make stdout UTF-8 so redirecting to a file doesn't crash.

    The console reports UTF-8, so `python draft_review.py` prints the box
    characters fine — but `python draft_review.py > out.txt` switches
    stdout to the locale codepage (cp1252) and the first box-drawing
    character raises UnicodeEncodeError before any output lands. It looks
    like the script broke; it is only the redirect.

    Every CLI here prints em dashes, arrows or box rules, so this belongs
    at the shared base rather than in each entry point. errors='replace'
    means an exotic glyph degrades to '?' instead of killing a draft
    review mid-run.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if (getattr(stream, "encoding", "") or "").lower() not in (
                    "utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # piped, wrapped or already closed — not worth failing over


_force_utf8_stdout()


def _load_username():
    """Shippable: friends set SLEEPER_USERNAME or drop a config.json
    ({"username": "..."}) next to the scripts. Everything else — leagues,
    scoring, rosters — auto-discovers from the username."""
    if os.environ.get("SLEEPER_USERNAME"):
        return os.environ["SLEEPER_USERNAME"]
    cfg = _paths.config()
    if cfg.exists():
        try:
            name = json.loads(cfg.read_text(encoding="utf-8")).get("username")
            if name:
                return name
        except (json.JSONDecodeError, OSError):
            pass
    return "dirtymurdock"


USERNAME = _load_username()
SPORT = "nfl"

BASE = "https://api.sleeper.app/v1"
STATS_BASE = "https://api.sleeper.com"  # app-internal host; per-player stats live here
CACHE = pathlib.Path.home() / ".sleeper_cache"
CACHE.mkdir(exist_ok=True)

PLAYERS_TTL = 60 * 60 * 24  # players file is large; once a day is the documented guidance
# leagues.json carries roster shape, status and my_players — all of which move
# DURING a draft. load_leagues() used to return the file forever once it existed,
# so any caller that did not pass refresh=True (mcp_server.py) served whatever was
# last written while dashboard.py, which does pass it, stayed current. Same file,
# two different truths depending on who asked (8/17).
LEAGUES_TTL = 60 * 5
MIN_INTERVAL = 0.08  # ~750 calls/min ceiling, under Sleeper's 1000 limit

_last_call = [0.0]


def _get(url, retries=3):
    gap = time.time() - _last_call[0]
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; personal-sleeper-client)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _last_call[0] = time.time()
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return None


def get(path, retries=3):
    """GET {BASE}/{path} as JSON, self-throttled."""
    return _get(f"{BASE}/{path.lstrip('/')}", retries)


# ---------------------------------------------------------------- discovery

def state():
    return get(f"state/{SPORT}") or {}


def current_season():
    return state().get("season") or "2026"


def discover(username=USERNAME, season=None):
    """username -> every league, with your roster located inside each."""
    season = season or current_season()
    user = get(f"user/{username}")
    if not user:
        raise SystemExit(f"No Sleeper user '{username}'")
    uid = user["user_id"]

    leagues = get(f"user/{uid}/leagues/{SPORT}/{season}") or []
    out = {"user_id": uid, "username": username, "season": season, "leagues": []}

    for lg in leagues:
        lid = lg["league_id"]
        rosters = get(f"league/{lid}/rosters") or []
        mine = next((r for r in rosters if r.get("owner_id") == uid), None)
        roster_id = mine.get("roster_id") if mine else None
        my_players = list((mine or {}).get("players") or [])
        drafted, picks_made = [], 0

        # league/{id}/rosters DOES NOT CONTAIN IN-DRAFT PICKS. Sleeper folds a
        # drafted player into the roster only when the draft COMPLETES, so during
        # a live draft this list is frozen at the pre-draft roster — keepers, or
        # empty in a startup. LG01 reported "0 rostered" through fourteen
        # rounds; hero reported seven keepers after Etienne went at 1.6. Every
        # roster-derived view (need model, holes, bye pressure, keeper analysis)
        # silently ran a turn or a draft behind. draft/{id}/picks is the live
        # truth, and it is the same endpoint board has always read — which is
        # exactly why board stayed correct while everything else drifted (8/17).
        draft_id = lg.get("draft_id")
        if draft_id and lg.get("status") == "drafting":
            # draft-id-ok: guarded by status == "drafting", where
            # league.draft_id IS the live draft by definition. This module
            # also cannot import draft_helper -- draft_helper imports it.
            picks = get(f"draft/{draft_id}/picks") or []  # draft-id-ok
            picks_made = len(picks)
            if roster_id is not None:
                for p in picks:
                    pid = p.get("player_id")
                    try:
                        same = int(p.get("roster_id")) == int(roster_id)
                    except (TypeError, ValueError):
                        same = False
                    if same and pid:
                        drafted.append(str(pid))
                for pid in drafted:
                    if pid not in my_players:
                        my_players.append(pid)

        out["leagues"].append({
            "league_id": lid,
            "name": lg.get("name"),
            "status": lg.get("status"),  # pre_draft | drafting | in_season | complete
            "draft_id": draft_id,
            "previous_league_id": lg.get("previous_league_id"),
            "total_teams": lg.get("total_rosters"),
            "roster_positions": lg.get("roster_positions"),
            "scoring_settings": lg.get("scoring_settings"),
            "settings": lg.get("settings"),
            "my_roster_id": roster_id,
            "my_players": my_players,
            # kept separate so a caller can SAY "7 kept + 1 drafted" rather than
            # present a merged list the user cannot reconcile against Sleeper.
            "my_drafted": drafted,
            "picks_made": picks_made,
            "my_starters": (mine or {}).get("starters") or [],
            "my_faab_used": (mine or {}).get("settings", {}).get("waiver_budget_used"),
        })

    (CACHE / "leagues.json").write_text(json.dumps(out, indent=2))
    return out


def load_leagues(refresh=False):
    p = CACHE / "leagues.json"
    if refresh or not p.exists():
        return discover()
    if time.time() - p.stat().st_mtime > LEAGUES_TTL:
        try:
            return discover()
        except Exception:
            pass  # network hiccup on a live board: stale beats crashing
    return json.loads(p.read_text(encoding="utf-8"))


def remaining_picks(owned, picks_made):
    """Owned picks that have NOT been used yet.

    my_draft_picks() answers "which picks do I own", trades included, and it
    answers it correctly. It does not answer "which do I still have", so
    keeper.py printed 'your upcoming picks: 6, 19, 30 ...' while pick 6 was
    already Etienne. Overall pick numbers are 1-based and sequential, so every
    pick at or below the count already made is spent.
    """
    return [o for o in owned if int(o) > int(picks_made or 0)]


# ------------------------------------------------------------ player table

def players(force=False):
    """Sleeper IDs are meaningless without this. Cached hard."""
    p = CACHE / "players_nfl.json"
    if not force and p.exists() and time.time() - p.stat().st_mtime < PLAYERS_TTL:
        return json.loads(p.read_text(encoding="utf-8"))
    data = get(f"players/{SPORT}")
    if not data:
        raise SystemExit("players/nfl returned nothing — network hiccup, rerun")
    p.write_text(json.dumps(data))
    return data


def name_of(pid, tbl):
    """
    Team defenses are IN the player table, keyed by abbreviation:
      tbl["SF"] == {"position": "DEF", "first_name": "San Francisco",
                    "last_name": "49ers", "team": "SF", ...}
    (verified live). So the table lookup handles them; the fallback below only
    fires on a genuine miss.
    """
    p = tbl.get(str(pid))
    if not p:
        s = str(pid)
        return f"{s} (DEF)" if s.isalpha() and s.isupper() and len(s) <= 3 else s
    full = p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
    return f"{full} ({p.get('position')}, {p.get('team') or 'FA'})"


# --------------------------------------------------------------- scoring

def score(stat_line, scoring_settings):
    """
    Fantasy points = dot product of the raw stat line and the league's
    scoring_settings. Same key vocabulary on both sides — verified against
    Sleeper's own players_points for QB/RB/DEF cases, exact to the 0.01.
    """
    return round(sum(
        v * scoring_settings.get(k, 0.0)
        for k, v in stat_line.items()
        if isinstance(v, (int, float))
    ), 2)


def score_across_leagues(stat_line, leagues):
    """Same stat line, every league's valuation. Shows WHY values differ."""
    return {lg["name"]: score(stat_line, lg["scoring_settings"] or {}) for lg in leagues}


def scoring_diff(leagues):
    """Where the leagues actually disagree. Ignores rules they share."""
    keys = set()
    for lg in leagues:
        keys |= set((lg["scoring_settings"] or {}).keys())
    rows = {}
    for k in sorted(keys):
        vals = [(lg["scoring_settings"] or {}).get(k, 0.0) for lg in leagues]
        if len(set(vals)) > 1:
            rows[k] = vals
    return rows


# ------------------------------------------------------- stats + verification

def player_week_stats(pid, season, week, season_type="regular"):
    """
    Raw stat line for one player-week from api.sleeper.com (the app's own host).
    Returns the bare stats dict or None. Small responses; fine for spot lookups.
    For bulk work, /v1/stats/{sport}/{season_type}/{season}/{week} on BASE
    returns every player at once — one big call instead of N small ones.
    """
    data = _get(f"{STATS_BASE}/stats/{SPORT}/player/{pid}"
                f"?season_type={season_type}&season={season}&grouping=week")
    if not data:
        return None
    wk = data.get(str(week))
    return (wk or {}).get("stats")


def verify_scoring(league_id, week, season=None, roster_id=None, tolerance=0.01):
    """
    Re-prove the scoring engine on real ground truth: for each player on one
    roster in a finished week, compute score(raw stats, league scoring) and diff
    against Sleeper's own players_points. Returns list of (pid, ours, sleepers, ok).
    """
    lg = get(f"league/{league_id}")
    if not lg:
        raise SystemExit(f"league {league_id} not found")
    season = season or lg.get("season")
    scoring = lg.get("scoring_settings") or {}

    matchups = get(f"league/{league_id}/matchups/{week}") or []
    if roster_id is None:
        user = get(f"user/{USERNAME}")
        if not user:
            raise SystemExit(f"user lookup for '{USERNAME}' failed — retry")
        uid = user["user_id"]
        rosters = get(f"league/{league_id}/rosters") or []
        mine = next((r for r in rosters if r.get("owner_id") == uid), None)
        if not mine:
            raise SystemExit("no roster of yours in that league")
        roster_id = mine["roster_id"]
    m = next((x for x in matchups if x.get("roster_id") == roster_id), None)
    if not m:
        raise SystemExit(f"no matchup for roster {roster_id} in week {week}")

    tbl = players()
    results = []
    print(f"{lg.get('name')} — season {season} week {week} — roster {roster_id}\n")
    for pid, sleeper_pts in sorted(m.get("players_points", {}).items(),
                                   key=lambda kv: -kv[1]):
        stats = player_week_stats(pid, season, week)
        ours = score(stats, scoring) if stats else 0.0
        ok = abs(ours - sleeper_pts) <= tolerance
        results.append((pid, ours, sleeper_pts, ok))
        flag = "" if ok else "   <-- MISMATCH"
        print(f"  {'ok' if ok else 'XX'}  ours {ours:>7.2f}  sleeper {sleeper_pts:>7.2f}"
              f"  {name_of(pid, tbl)}{flag}")
    bad = [r for r in results if not r[3]]
    print(f"\n{len(results) - len(bad)}/{len(results)} exact"
          + (f" — {len(bad)} MISMATCHES, scoring engine NOT sound for this league" if bad else ""))
    return results


# ------------------------------------------------------------------ report

def report():
    st = state()
    data = load_leagues()
    lgs = data["leagues"]
    tbl = players()

    print(f"{data['username']} — {len(lgs)} leagues — "
          f"season {st.get('season')} week {st.get('week')} ({st.get('season_type')})\n")

    for lg in lgs:
        pos = defaultdict(int)
        for slot in (lg["roster_positions"] or []):
            pos[slot] += 1
        shape = " ".join(f"{k}x{v}" for k, v in pos.items())

        settings = lg["settings"] or {}
        if settings.get("waiver_type") == 2:  # FAAB; other types bid nothing
            budget, used = settings.get("waiver_budget"), lg["my_faab_used"]
            faab = f"{budget - (used or 0)}/{budget}" if budget else "n/a"
        else:
            faab = "no FAAB (waiver order)"

        print(f"── {lg['name']}  ({lg['total_teams']} teams, roster {lg['my_roster_id']},"
              f" {lg.get('status')})")
        print(f"   FAAB left: {faab}   slots: {shape}")
        if lg["my_starters"]:
            print(f"   starters: {', '.join(name_of(p, tbl) for p in lg['my_starters'] if p and p != '0')}")
        print(f"   ({len(lg['my_players'])} rostered)\n")

    print("── where the leagues disagree on scoring")
    hdr = [(lg["name"] or "?").strip()[:14] for lg in lgs]
    print(f"   {'rule':<18}" + "".join(f"{h:>16}" for h in hdr))
    for k, vals in scoring_diff(lgs).items():
        print(f"   {k:<18}" + "".join(f"{v:>16g}" for v in vals))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        # default ground truth: 2025 Hybrid 14, week 17 (finished season)
        lid = sys.argv[2] if len(sys.argv) > 2 else "9000000000000000006"
        wk = int(sys.argv[3]) if len(sys.argv) > 3 else 17
        verify_scoring(lid, wk)
    else:
        report()


# ---------------------------------------------------------------- draft shape
#
# ONE implementation of pick geometry for the whole toolkit. Three files
# used to carry their own snake arithmetic (draft_helper.my_next_pick,
# keeper.upcoming_picks, lineup_value.snake_picks) and all three were
# wrong in the same two ways on 8/13:
#
#   1. They assumed a PLAIN snake. Sleeper supports a reversal, almost
#      always at round 3, where round R repeats round R-1's order instead
#      of flipping. LG03-LG05 runs reversal_round=3 and the emoji Hybrid
#      runs 0, so the two rooms do not share a format and every pick
#      number from round 3 down was wrong in one of them.
#   2. They ignored TRADED picks entirely. He owns an extra round-8 pick
#      in each Hybrid; no tool knew.
#
# Both failures are silent: the numbers look plausible, they are just not
# his. Read the shape from the draft object, never infer it.

def round_is_forward(rnd, reversal_round=0):
    """Does this round run 1..N (True) or N..1 (False)?"""
    rnd, R = int(rnd), int(reversal_round or 0)
    if not R or rnd < R:
        return rnd % 2 == 1
    prev_fwd = ((R - 1) % 2 == 1)          # direction of the round before R
    return prev_fwd != ((rnd - R) % 2 == 1)   # R repeats it, then alternates


def slot_picks(slot, rounds, teams, reversal_round=0):
    """Overall pick numbers belonging to `slot`, before any trades."""
    slot, teams = int(slot), int(teams)
    return [(r - 1) * teams + (slot if round_is_forward(r, reversal_round)
                               else teams - slot + 1)
            for r in range(1, int(rounds) + 1)]


def overall_of(rnd, slot, teams, reversal_round=0):
    """The overall pick number for (round, slot)."""
    slot, teams = int(slot), int(teams)
    pos = slot if round_is_forward(rnd, reversal_round) else teams - slot + 1
    return (int(rnd) - 1) * teams + pos


def traded_deltas(draft_id, my_roster_id, teams, reversal_round,
                  slot_to_roster, get_fn=None):
    """(gained, lost) overall pick numbers from /draft/<id>/traded_picks.

    Sleeper records one row per traded pick with the ORIGINAL owner in
    `roster_id` and the current holder in `owner_id`, so a pick traded
    twice still resolves to its final owner from the last row.
    """
    get_fn = get_fn or get
    r2s = {int(r): int(s) for s, r in (slot_to_roster or {}).items()}
    gained, lost = set(), set()
    for t in (get_fn(f"draft/{draft_id}/traded_picks") or []):
        try:
            rnd, orig, now = int(t["round"]), int(t["roster_id"]), int(t["owner_id"])
        except (KeyError, TypeError, ValueError):
            continue
        slot = r2s.get(orig)
        if not slot:
            continue
        pk = overall_of(rnd, slot, teams, reversal_round)
        if now == int(my_roster_id):
            gained.add(pk)
        elif orig == int(my_roster_id):
            lost.add(pk)
    return gained, lost


def my_draft_picks(draft, my_roster_id, rounds=None, teams=None, get_fn=None):
    """Every overall pick this roster actually owns, trades included.

    Returns (picks, meta) where meta carries reversal_round, gained and
    lost so a caller can SAY what changed rather than silently differ
    from the arithmetic a user did in their head.
    """
    st = (draft or {}).get("settings") or {}
    teams = int(teams or st.get("teams") or 12)
    rounds = int(rounds or st.get("rounds") or 0)
    rev = int(st.get("reversal_round") or 0)
    # A DRAFT ORDER THAT HAS NOT BEEN SET IS NOT A DRAFT ORDER. Before
    # the commissioner randomises, Sleeper still ships slot_to_roster_id
    # as an IDENTITY map (slot 1 -> roster 1, slot 2 -> roster 2 ...) and
    # leaves draft_order null. Reading a slot off that placeholder is how
    # the IDP league reported "slot 4 of 10" for a draft whose order does
    # not exist yet, with a full pick list built on it (8/13). draft_order
    # is the field that says the order is real; require it.
    s2r = (draft or {}).get("slot_to_roster_id") or {}
    published = bool((draft or {}).get("draft_order"))
    slot = next((int(s) for s, r in s2r.items()
                 if int(r) == int(my_roster_id)), None) if published else None
    if not slot or not rounds:
        return [], {"reversal_round": rev, "slot": slot,
                    "published": published,
                    "gained": [], "lost": []}
    base = set(slot_picks(slot, rounds, teams, rev))
    gained, lost = traded_deltas((draft or {}).get("draft_id"), my_roster_id,
                                 teams, rev, s2r, get_fn=get_fn)
    return sorted((base - lost) | gained), {
        "reversal_round": rev, "slot": slot, "teams": teams,
        "published": published,
        "rounds": rounds, "gained": sorted(gained), "lost": sorted(lost)}


# ------------------------------------------------------------------- byes
#
# Bye weeks are SEASON data with no Sleeper endpoint: the player table
# does not carry a bye_week field, and there is no public schedule route
# in v1. So they live in byes.json, same as ages.json and keepers.json,
# and they must be replaced every year. A stale file corrupts every bye
# warning silently, which is why load_byes() checks the season key and
# says so rather than returning numbers it cannot vouch for.

_BYES = None
_BYES_ERR = ""


def load_byes(season=None, path=None):
    """({TEAM: week}, note). Empty dict if the file is missing or stale.

    The note carries the ACTUAL failure — path and exception — because
    "missing or unreadable" told me nothing when it fired on one league
    and not another in the same run (8/13).
    """
    global _BYES, _BYES_ERR
    import json as _json
    import pathlib as _pl
    if _BYES is None or path:
        # AUTHORED DATA LIVES IN data/. This built its own path from
        # the module directory, where byes.json does not exist — only
        # data/byes.json does — so every bye lookup failed into the
        # empty dict and the note nobody was printing (8/13).
        if path:
            f = _pl.Path(path)
        else:
            from battle_rhythm import paths as _paths
            f = _paths.data("byes.json")
        try:
            _BYES = _json.loads(f.read_text(encoding="utf-8"))
            _BYES_ERR = ""
        except Exception as e:
            _BYES = {"season": None, "byes": {}}
            _BYES_ERR = f"{type(e).__name__}: {e} (looked in {f})"
    have = str(_BYES.get("season") or "")
    if season and have and str(season) != have:
        return {}, (f"byes.json is for {have}, not {season} — bye checks "
                    f"skipped. Update the file.")
    if not _BYES.get("byes"):
        return {}, (f"byes.json unusable — bye checks skipped. "
                    f"{_BYES_ERR or 'file parsed but carried no byes'}")
    return dict(_BYES["byes"]), ""


def bye_of(team, season=None, path=None):
    """Bye week for an NFL team abbreviation, or None if unknown."""
    b, _ = load_byes(season, path)
    return b.get((team or "").upper())


def bye_pressure(roster_byes, starters):
    """{week: available} for every week that has anybody out.

    roster_byes is an iterable of bye weeks, one per rostered player who
    could start. A week where `available` drops below `starters` is a
    slot you cannot fill — the model prices season totals and will walk
    you into one without noticing. On 8/13 its own line put six players
    out in week 13 of a 14-man roster: eight bodies for nine slots.
    """
    from collections import Counter
    # Materialise ONCE. The first version filtered into a list and then
    # called len(list(roster_byes)) on the original, which returns 0 for
    # any generator — every week would have reported negative slack.
    rows = list(roster_byes)
    out = Counter(b for b in rows if b)
    return {wk: len(rows) - n for wk, n in sorted(out.items())}
