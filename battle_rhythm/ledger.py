"""
ledger.py — every in-season recommendation, written down, then scored.

  python br.py ledger                    # what the ledger says so far
  python br.py ledger score              # score every rec whose weeks have played
  python br.py ledger --league lg04   # one league
  python br.py ledger list [--league x] [--week n]   # every rec with its id
  python br.py ledger prune --league <id> # drop every rec for a league that was not real
  python br.py ledger prune --rec <id> [<id>...]     # drop advice that was never actionable
  python br.py ledger --selftest         # offline

WHY THIS EXISTS. On 9/4 the rule for the next four weeks was "no new
features, the eval is the deliverable." On 9/11 John asked for the
in-season tools — waivers, moves, trades. Those are the same thing only
if every recommendation is recorded WITH the projection it was made on
and scored against what actually happened. Without that, four weeks from
now there is a nicer waiver tab and no baseline, which is the outcome
the 9/4 rule exists to prevent. So `weekly` records by default and this
module is where the record lives.

WHAT A RECORD IS. One line of JSON in data/ledger/recs.jsonl:

    kind        lineup | waiver | trade
    league_id   the id, never the name (both Hybrids normalise the same)
    season, week
    made_at     ISO timestamp of the run that produced it
    subject     the player(s) the advice is about, by Sleeper id
    over        the player(s) the advice displaces, by Sleeper id
    proj        the numbers the advice was priced on, as printed
    id          sha1 of (kind, league, season, week, subject, over) — so a
                brief that runs three times on a Tuesday writes the rec
                ONCE, as of its first run, which is when it was actionable

WHAT AN OUTCOME IS. One line in data/ledger/outcomes.jsonl, keyed by rec
id, written by `score` once the weeks the advice covered have played:

    weeks       the weeks actually scored (rec.week .. through)
    actual      {pid: points under THIS league's scoring} from the stats
                feed, rescored by the verified dot product — the same
                ground truth verify_scoring() proves the engine against
    delta       actual(subject) - actual(over), summed over the weeks
    won         delta > 0
    acted       for waivers: did MY roster add the subject that week
                (from league transactions); None if unknown

Outcomes are recomputed every time `score` runs — an outcome is a
function of final stats and the rec, so rewriting it is safe. Recs are
never rewritten.

WHAT IT IS NOT. It is not a claim that a rec was right because it won:
backtest.py already measured that a one-point projection edge wins 50%
of the time. The ledger is the raw fact table; the beat rate BY GAP
BUCKET is the eval, and the calibration table is its prior. Where the
ledger's rate for a bucket falls well under the calibration rate, the
engine is worse than the feed — that is the diagnosis the four weeks are
meant to produce. Where it lands above, the league-specific rescoring is
doing work the generic feed cannot.

Truth tier: data/ledger/ is tracked in git. A rec cannot be re-derived
once the week has passed, which is the CLAUDE.md test.
"""

import hashlib
import json
import sys
import time
from collections import defaultdict

from battle_rhythm import paths as _paths

KINDS = ("lineup", "waiver", "trade")
ENABLED = [True]          # weekly.main flips this off for --no-record

# Same buckets as backtest.py so the two tables read side by side.
BUCKETS = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 12), (12, 999)]


# ------------------------------------------------------------------ paths

# Only paths.py knows where the ledger lives (CLAUDE.md rule 1). The
# indirection through _dir() exists so the selftest can point both files
# at a temp directory without touching paths.
def _dir():
    return _paths.ledger("recs.jsonl").parent


def recs_path():
    return _dir() / "recs.jsonl"


def outcomes_path():
    return _dir() / "outcomes.jsonl"


def _read(p):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue              # a torn line is skipped, not fatal
    return out


def _append(p, rows):
    if not rows:
        return
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


# ------------------------------------------------------------------ recs

def rec_id(kind, league_id, season, week, subject, over):
    key = "|".join([kind, str(league_id), str(season), str(week),
                    ",".join(sorted(map(str, subject))),
                    ",".join(sorted(map(str, over)))])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def make_rec(kind, league_id, season, week, subject, over, proj, note=""):
    """Build one record. subject/over are lists of Sleeper ids."""
    assert kind in KINDS, kind
    subject = [str(x) for x in subject if x]
    over = [str(x) for x in over if x]
    return {"id": rec_id(kind, league_id, season, week, subject, over),
            "kind": kind, "league_id": str(league_id),
            "season": str(season), "week": int(week),
            "made_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "subject": subject, "over": over,
            "proj": proj, "note": note}


def recs_from_brief(L, season, week):
    """Every recommendation a weekly.league_brief() carries, as records.

    Pure: reads the brief dict, returns rows, touches nothing on disk.
    The brief already carries pids for the lineup diff and trades; the
    waiver rows carry them as of 9/11 (add_pid / over_pid / drop_pid).
    """
    lid = L["league_id"]
    rows = []
    for d in L.get("lineup_diff") or []:
        if d.get("in_pid") and d.get("out_pid"):
            rows.append(make_rec(
                "lineup", lid, season, week, [d["in_pid"]], [d["out_pid"]],
                {"in_wk": d.get("in_ros"), "out_wk": d.get("out_ros"),
                 "gain": d.get("gain"), "conf": d.get("conf")},
                note=f"start {d['in']} over {d['out']}"))
    for tier, key in ((1, "waivers_tier1"), (2, "waivers_tier2")):
        for w in L.get(key) or []:
            if not w.get("add_pid"):
                continue
            rows.append(make_rec(
                "waiver", lid, season, week, [w["add_pid"]],
                [x for x in (w.get("over_pid"),) if x],
                {"tier": tier, "add_ros": w.get("ros"), "gap": w.get("gap"),
                 "drop_pid": w.get("drop_pid"), "bid": w.get("bid"),
                 "depth": w.get("depth"), "stale_role": w.get("stale_role")},
                note=f"add {w['add']} over {w['over']}"
                     + (f", drop {w['drop']}" if w.get("drop") else "")))
    for t in L.get("trades") or []:
        if t.get("get_pid") and t.get("give_pid"):
            rows.append(make_rec(
                "trade", lid, season, week, [t["get_pid"]], [t["give_pid"]],
                {"my_gain": t.get("my_gain"), "their_gain": t.get("their_gain"),
                 "partner": t.get("partner")},
                note=f"get {t['get']} for {t['give']} [{t['partner']}]"))
    return rows


def record(rows):
    """Append rows whose id is not already on file. Returns how many landed."""
    if not ENABLED[0] or not rows:
        return 0
    have = {r["id"] for r in _read(recs_path())}
    new = [r for r in rows if r["id"] not in have]
    _append(recs_path(), new)
    return len(new)


def record_brief(L, season, week):
    return record(recs_from_brief(L, season, week))


# --------------------------------------------------------------- outcomes

def _actual_week(season, week, fetch=None):
    """{pid: raw stat line} for a finished week. Cached gzipped by
    backtest_probe.fetch, which is the one function in the toolkit that
    already knows both stats hosts and the atomic-write rule."""
    if fetch is not None:
        return fetch(season, week) or {}
    from battle_rhythm import backtest_probe as bp
    return bp.fetch(bp.BASE_STAT.format(s=season, w=week),
                    bp.ALT_STAT.format(s=season, w=week),
                    kind="stat", season=season, week=week) or {}


def _my_adds(league_id, week, roster_id, get=None):
    """Player ids MY roster added via waiver/free agent in `week`, or None
    if the transactions feed could not be read. Sleeper's transaction
    `adds` is {pid: roster_id}; `settings.waiver_bid` is the FAAB paid."""
    if get is None:
        from battle_rhythm.sleeper_client import get as _g
        get = _g
    try:
        txs = get(f"league/{league_id}/transactions/{week}") or []
    except Exception:
        return None
    out = {}
    for t in txs:
        if t.get("status") != "complete":
            continue
        if t.get("type") not in ("waiver", "free_agent"):
            continue
        for pid, rid in (t.get("adds") or {}).items():
            if roster_id is not None and int(rid) == int(roster_id):
                out[str(pid)] = (t.get("settings") or {}).get("waiver_bid")
    return out


def score(through_week, scoring_by_league, fetch=None, get=None,
          roster_by_league=None, recs=None, horizon=None):
    """Score every rec whose weeks have played. Returns the outcome rows.

    through_week       last COMPLETED week
    scoring_by_league  {league_id: scoring_settings}
    horizon            weeks a rec is scored over: 1 for lineup (it is a
                       one-week call), else FIRST_SCORED_WEEK..through_week

    WHEN A REC STARTS COUNTING. A lineup call is about the week it was
    made in. A waiver or trade made in week N cannot score for you in
    week N: claims process Tuesday night, trades clear on review, and
    the player suits up for you in week N+1 at the earliest. The first
    live run (9/12, week 1) would have credited every waiver add with a
    game the manager could not have started him in. Waivers and trades
    are scored from N+1; a rec whose N+1 has not played yet is skipped.

    Everything network-shaped is injectable so the selftest runs offline.
    """
    recs = _read(recs_path()) if recs is None else recs
    outcomes = []
    cache = {}
    for r in recs:
        wk0 = int(r["week"]) + (0 if r["kind"] == "lineup" else 1)
        if wk0 > through_week:
            continue
        sc = scoring_by_league.get(str(r["league_id"]))
        if sc is None:
            continue
        h = horizon if horizon is not None else (1 if r["kind"] == "lineup" else None)
        last = wk0 if h == 1 else (min(through_week, wk0 + h - 1) if h else through_week)
        weeks = list(range(wk0, last + 1))
        actual = defaultdict(float)
        played = defaultdict(int)
        for w in weeks:
            key = (r["season"], w)
            if key not in cache:
                cache[key] = _actual_week(r["season"], w, fetch=fetch)
            stats = cache[key]
            for pid in r["subject"] + r["over"]:
                line = stats.get(pid)
                if line:
                    from battle_rhythm.sleeper_client import score as _score
                    actual[pid] += _score(line, sc)
                    played[pid] += 1
        subj = sum(actual[p] for p in r["subject"])
        over = sum(actual[p] for p in r["over"])
        row = {"rec_id": r["id"], "kind": r["kind"], "league_id": r["league_id"],
               "season": r["season"], "week": int(r["week"]), "weeks": weeks,
               "actual": {p: round(v, 2) for p, v in actual.items()},
               "played": dict(played),
               "delta": round(subj - over, 2), "won": (subj - over) > 0,
               "proj_gap": _proj_gap(r), "acted": None,
               "scored_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if r["kind"] == "waiver":
            rid = (roster_by_league or {}).get(str(r["league_id"]))
            adds = (_my_adds(r["league_id"], int(r["week"]), rid, get=get)
                    if rid is not None else None)
            if adds is not None:
                row["acted"] = any(p in adds for p in r["subject"])
                row["paid"] = next((adds[p] for p in r["subject"] if p in adds), None)
        outcomes.append(row)
    return outcomes


def _proj_gap(r):
    p = r.get("proj") or {}
    for k in ("gain", "gap", "my_gain"):
        if isinstance(p.get(k), (int, float)):
            return float(p[k])
    return None


def prune(league_id):
    """Remove every rec and outcome for one league id. For a league that
    turned out not to be real -- the API returned two LG06 on
    9/12 with identical rosters, and the first weekly run recorded both.
    Rewrites both files; returns (recs removed, outcomes removed)."""
    lid = str(league_id)
    recs = _read(recs_path())
    keep = [r for r in recs if r["league_id"] != lid]
    gone = {r["id"] for r in recs if r["league_id"] == lid}
    outs = _read(outcomes_path())
    keep_o = [o for o in outs if o["rec_id"] not in gone]
    recs_path().write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in keep),
                           encoding="utf-8")
    if outs:
        outcomes_path().write_text(
            "".join(json.dumps(o, sort_keys=True) + "\n" for o in keep_o), encoding="utf-8")
    return len(recs) - len(keep), len(outs) - len(keep_o)


def prune_ids(ids):
    """Remove specific recs (and their outcomes) by id. For advice that was
    not actionable when given -- the 9/12 'bench A.J. Brown' call, made
    after his Thursday game had locked him. Scoring it would book a loss
    against a move nobody could make."""
    ids = {str(i) for i in ids}
    recs = _read(recs_path())
    keep = [r for r in recs if r["id"] not in ids]
    outs = _read(outcomes_path())
    keep_o = [o for o in outs if o["rec_id"] not in ids]
    recs_path().write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in keep),
                           encoding="utf-8")
    if outs:
        outcomes_path().write_text(
            "".join(json.dumps(o, sort_keys=True) + "\n" for o in keep_o), encoding="utf-8")
    return len(recs) - len(keep), len(outs) - len(keep_o)


def print_list(recs, league_id=None, week=None):
    """Every rec, one line: id, week, kind, note. The id is what prune
    takes."""
    slug = None
    try:
        slug = _paths.slug_for
    except Exception:
        pass
    for r in recs:
        if league_id and r["league_id"] != str(league_id):
            continue
        if week and int(r["week"]) != int(week):
            continue
        lg = slug(r["league_id"]) if slug else r["league_id"]
        print(f"  {r['id']}  wk{r['week']:<2} {r['kind']:<6} {lg:<16} {r.get('note', '')}")


def write_outcomes(rows):
    """Outcomes are a function of final stats and the rec: rewrite the
    whole file rather than append, so re-scoring never double-counts."""
    if not rows:
        return
    p = outcomes_path()
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                 encoding="utf-8")


# ---------------------------------------------------------------- report

def _bucket(gap):
    if gap is None:
        return None
    for lo, hi in BUCKETS:
        if lo <= abs(gap) < hi:
            return f"{lo}-{hi if hi < 999 else '+'}"
    return None


def summarize(recs, outcomes, calibration=None):
    """{kind: {bucket: (n, won, calib_rate)}} plus totals. Pure."""
    by_id = {o["rec_id"]: o for o in outcomes}
    table = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    totals = defaultdict(lambda: [0, 0, 0])        # recs, scored, won
    acted = defaultdict(lambda: [0, 0])            # waivers acted, acted+won
    for r in recs:
        totals[r["kind"]][0] += 1
        o = by_id.get(r["id"])
        if not o:
            continue
        totals[r["kind"]][1] += 1
        totals[r["kind"]][2] += int(bool(o["won"]))
        b = _bucket(o.get("proj_gap"))
        if b:
            table[r["kind"]][b][0] += 1
            table[r["kind"]][b][1] += int(bool(o["won"]))
        if r["kind"] == "waiver" and o.get("acted"):
            acted["waiver"][0] += 1
            acted["waiver"][1] += int(bool(o["won"]))
    calib = {}
    for lo, hi in BUCKETS:
        b = f"{lo}-{hi if hi < 999 else '+'}"
        row = ((calibration or {}).get("overall") or {}).get(f"{lo}-{hi}") \
            or ((calibration or {}).get("overall") or {}).get(b)
        if isinstance(row, dict) and row.get("n"):
            calib[b] = row.get("rate") or (row.get("won", 0) / row["n"])
    return {"table": {k: dict(v) for k, v in table.items()},
            "totals": dict(totals), "acted": dict(acted), "calib": calib}


def print_report(recs, outcomes, calibration=None, league_id=None):
    if league_id:
        recs = [r for r in recs if r["league_id"] == str(league_id)]
        ids = {r["id"] for r in recs}
        outcomes = [o for o in outcomes if o["rec_id"] in ids]
    S = summarize(recs, outcomes, calibration)
    if not recs:
        print("ledger is empty — run `python br.py weekly` once a week and it fills")
        return
    print(f"ledger: {len(recs)} recommendations, {len(outcomes)} scored")
    for kind in KINDS:
        n, s, w = S["totals"].get(kind, (0, 0, 0))
        if not n:
            continue
        rate = f"{100 * w / s:.0f}% won" if s else "none scored yet"
        print(f"\n  {kind:<7} {n:>4} recs  {s:>4} scored  {rate}")
        rows = S["table"].get(kind) or {}
        for lo, hi in BUCKETS:
            b = f"{lo}-{hi if hi < 999 else '+'}"
            if b not in rows:
                continue
            bn, bw = rows[b]
            c = S["calib"].get(b)
            cal = f"   feed prior {100 * c:.0f}%" if c else ""
            print(f"    edge {b:>5} pts  {bn:>4}  {100 * bw / bn:>3.0f}% won{cal}")
    a = S["acted"].get("waiver")
    if a and a[0]:
        print(f"\n  waivers you actually claimed: {a[0]}, {100 * a[1] / a[0]:.0f}% won")
    print("\n  won = the recommended side outscored the displaced side under this"
          " league's scoring over the weeks the advice covered. A rate near the"
          " feed prior means the rescoring adds nothing; above it, it does.")


# ---------------------------------------------------------------- CLI

def _calibration():
    try:
        return json.loads(_paths.measured("calibration.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    lid = None
    if "--league" in argv:
        from battle_rhythm.draft_helper import cli_league
        lid = cli_league(argv[argv.index("--league") + 1])
    if "prune" in argv:
        if "--rec" in argv:
            ids = [a for a in argv[argv.index("--rec") + 1:] if not a.startswith("-")]
            n, m = prune_ids(ids)
            print(f"pruned {n} rec(s) and {m} outcome(s): {', '.join(ids)}")
            return 0
        if not lid:
            raise SystemExit("ledger prune needs --league <slug or id> or --rec <id...>")
        n, m = prune(lid)
        print(f"pruned {n} rec(s) and {m} outcome(s) for league {lid}")
        return 0
    recs = _read(recs_path())
    if "list" in argv:
        wk = int(argv[argv.index("--week") + 1]) if "--week" in argv else None
        print_list(recs, league_id=lid, week=wk)
        return 0
    if "score" in argv:
        from battle_rhythm.sleeper_client import state, load_leagues
        st = state()
        # the current week has not played; everything before it has
        through = max((st.get("week") or 1) - 1, 0)
        data = load_leagues()
        scoring = {lg["league_id"]: lg["scoring_settings"] or {} for lg in data["leagues"]}
        rosters = {lg["league_id"]: lg.get("my_roster_id") for lg in data["leagues"]}
        rows = score(through, scoring, roster_by_league=rosters, recs=recs)
        write_outcomes(rows)
        print(f"scored {len(rows)} recs through week {through} -> {outcomes_path()}")
    print_report(recs, _read(outcomes_path()), _calibration(), league_id=lid)
    return 0


# ---------------------------------------------------------------- selftest

def selftest():
    """Offline: a brief becomes recs, recs dedupe, outcomes score against
    an injected stats feed, and the report buckets the way backtest does."""
    import tempfile, pathlib
    n = 0

    def ok(cond, msg):
        nonlocal n
        assert cond, msg
        n += 1

    L = {"league_id": "L1",
         "lineup_diff": [{"in": "A", "out": "B", "in_pid": "a", "out_pid": "b",
                          "in_ros": 14.5, "out_ros": 12.8, "gain": 1.7, "conf": 0.53}],
         "waivers_tier1": [{"add": "F", "add_pid": "f", "over": "B", "over_pid": "b",
                            "drop": "D", "drop_pid": "d", "ros": 120.0, "gap": 30.0,
                            "bid": 37, "depth": "RB2", "stale_role": False}],
         "waivers_tier2": [{"add": "G", "add_pid": None, "over": "x", "gap": 1.0}],
         "trades": [{"give": "A", "get": "C", "give_pid": "a", "get_pid": "c",
                     "partner": "P", "my_gain": 9.0, "their_gain": 6.0}]}
    rows = recs_from_brief(L, "2026", 2)
    ok([r["kind"] for r in rows] == ["lineup", "waiver", "trade"],
       "one rec per recommendation; a waiver row without a pid is skipped")
    ok(rows[1]["subject"] == ["f"] and rows[1]["over"] == ["b"], "waiver keys")
    ok(rows[0]["id"] == rec_id("lineup", "L1", "2026", 2, ["a"], ["b"]), "id is deterministic")

    # dedupe: the same brief twice writes once
    global _dir
    saved_dir = _dir
    tmp = pathlib.Path(tempfile.mkdtemp())
    _dir = lambda: tmp
    try:
        ok(record(rows) == 3, "first write lands three")
        ok(record(rows) == 0, "second write of the same brief lands none")
        ok(len(_read(recs_path())) == 3, "three on disk")

        # score against an injected feed: week 2 and 3 stats, scoring {x: 1}
        # recs are week 2. Lineup scores on week 2; waiver and trade start
        # at week 3, because a week-2 claim cannot play in week 2.
        feed = {2: {"a": {"x": 10}, "b": {"x": 12}, "f": {"x": 9}, "c": {"x": 20}},
                3: {"a": {"x": 30}, "b": {"x": 1}, "f": {"x": 15}, "c": {"x": 5}}}
        got = score(3, {"L1": {"x": 1.0}}, fetch=lambda s, w: feed.get(w, {}),
                    get=lambda path: [{"status": "complete", "type": "waiver",
                                       "adds": {"f": 4}, "settings": {"waiver_bid": 37}}],
                    roster_by_league={"L1": 4}, recs=rows)
        by = {o["kind"]: o for o in got}
        ok(by["lineup"]["weeks"] == [2] and by["lineup"]["delta"] == -2.0
           and by["lineup"]["won"] is False,
           "lineup is scored on its one week only, and this one lost")
        ok(by["waiver"]["weeks"] == [3] and by["waiver"]["delta"] == 14.0
           and by["waiver"]["won"] is True and by["waiver"]["week"] == 2,
           "waiver is scored from the week AFTER the claim, keyed on its own week")
        ok(by["waiver"]["acted"] is True and by["waiver"]["paid"] == 37,
           "the transactions feed says I claimed him and what I paid")
        ok(by["trade"]["delta"] == -25.0, "trade: week 3 only, get c (5) minus give a (30)")
        ok(not [o for o in score(2, {"L1": {"x": 1.0}},
                                 fetch=lambda s, w: feed.get(w, {}), recs=rows)
                if o["kind"] != "lineup"],
           "through week 2, a week-2 waiver has nothing to score yet")
        write_outcomes(got)
        write_outcomes(got)
        ok(len(_read(outcomes_path())) == 3, "outcomes are rewritten, never doubled")

        S = summarize(rows, got, {"overall": {"1-2": {"n": 100, "rate": 0.534}}})
        ok(S["table"]["lineup"]["1-2"] == [1, 0], "bucketed by the projected edge")
        ok(abs(S["calib"]["1-2"] - 0.534) < 1e-9, "calibration prior joins by bucket")
        ok(S["acted"]["waiver"] == [1, 1], "acted waivers counted separately")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(rows, got, {"overall": {"1-2": {"n": 100, "rate": 0.534}}})
        ok("feed prior 53%" in buf.getvalue(), "report prints the prior beside the rate")
        ENABLED[0] = False
        ok(record(recs_from_brief(L, "2026", 3)) == 0, "--no-record writes nothing")
        ENABLED[0] = True
        record([make_rec("waiver", "DEAD", "2026", 2, ["z"], ["y"], {})])
        ok(prune("DEAD") == (1, 0) and len(_read(recs_path())) == 3,
           "prune removes one league's recs and nothing else")
    finally:
        _dir = saved_dir
    print(f"ledger selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
