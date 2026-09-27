"""
truth.py -- does the engine score what Sleeper scored? Every league,
every rostered player, every finished week.

    python br.py truth fetch --week 2        # NETWORK. Run on the PC.
    python br.py truth fetch --weeks 1-2
    python br.py truth compare --week 2      # offline, reads the snapshot
    python br.py truth compare --weeks 1-2
    python br.py truth fetch --last          # the two latest scored weeks (Tuesday, PC)
    python br.py truth compare --recent      # the two latest snapshotted weeks
    python br.py truth fetch --history       # NETWORK. Every scored week of each league's
                                             # previous season (the 2025 Hybrids), on the PC
    python br.py truth compare --season 2025 --all
    python br.py truth --selftest            # offline

HISTORY. 2026 only exercises the rules that happened to come up. A
league's previous season (settings: previous_league_id) carries a full
year of players_points under THAT season's own settings, so `--history`
tests the engine on the rare events -- special-teams and fumble-return
TDs, sub-20-yard kicks -- without waiting for them. Only leagues that
existed on Sleeper last year have one: the two Hybrids, as of 9/26.
The compare's RULE COVERAGE section says, per league, which paid keys
have been proven on an exact row and which have never been exercised.

TUESDAY. Windows Task Scheduler on the PC runs `truth fetch --last` at
6:30 AM Pacific: the week that just finished, plus the week before it
again, because Sleeper posts stat corrections after the first scoring
pass. The 7:00 AM research refresh then runs `truth compare --recent`
offline in the VM and puts the result in its report. A week with two
snapshots also reports every player whose Sleeper points moved between
them -- that is the stat-correction log.

WHY THIS EXISTS. ledger.py's "actual" is the stats feed rescored by our
own dot product. That is the engine grading itself: if a rule is wrong,
the rec and its outcome are wrong the same way and the ledger never
sees it. verify_scoring() in sleeper_client does compare against
Sleeper's own players_points, but for one roster, one week, one HTTP
call per player -- a spot check, not a check.

This is the full version. Sleeper publishes players_points in every
matchup row: the points IT awarded each rostered player, starters and
bench, under THAT league's settings. That is third-party ground truth
with no hand labelling. One row per (league, week, player):

    computed   score(stat line, league scoring_settings)  -- the engine
    sleeper    matchups[].players_points[pid]             -- the truth
    diff       computed - sleeper

NAMED truth, NOT diff, on purpose. `scoring_diff` already exists and
compares league RULES (which keys the leagues disagree on). It never
touches a result. Two tools called "diff" that answer different
questions is how the 9/26 conversation spent ten minutes on the wrong one.

TWO STEPS, BECAUSE ONLY ONE MACHINE HAS NETWORK. The device VM and the
cloud container are both denied CONNECT to Sleeper (9/3, re-tested 9/26).
So `fetch` does every network call, once, on John's PC, and writes one
snapshot: stats + every league's settings + matchups + positions, under
ONE timestamp. Fetching stats and matchups at different times would turn
a Tuesday stat correction into a fake engine miss. `compare` reads only
the snapshot, so it runs anywhere and reruns give the same answer.

WHAT IT DROPS. TEAM_* rows are whole-offense totals (100+ "points") and
are never rostered; they never enter the join because the join is
driven by players_points. Team defenses (HOU, NE) ARE rostered and ARE
scored.

WHAT IT DOES NOT DO. It does not change the engine. A miss is a
diagnosis for John to approve a fix against, one cause at a time
(9/4 rule: a fix you cannot attribute to a diagnosed cause is not a
result). Free agents are not in matchups, so waiver outcomes for
unrostered players still rest on the engine alone -- the `source`
column says which rows are Sleeper-backed.
"""

import csv
import gzip
import json
import sys
import time
from collections import defaultdict

from battle_rhythm import paths

EXACT = 0.005        # |diff| under this is an exact match
ROUNDING = 0.015     # under this is a one-cent rounding difference, not a rule
SEASON_DEFAULT = "2026"


# ------------------------------------------------------------ snapshot io

def _week_dir(season, week):
    return paths.truth(str(season), f"wk{int(week):02d}", "_").parent


def latest_snapshot(season, week):
    """Newest snapshot folder for a week, or None."""
    d = _week_dir(season, week)
    stamps = sorted(p for p in d.iterdir() if p.is_dir() and (p / "manifest.json").exists())
    return stamps[-1] if stamps else None


def snapshots(season, week):
    """Every snapshot folder for a week, oldest first."""
    d = _week_dir(season, week)
    return sorted(p for p in d.iterdir() if p.is_dir() and (p / "manifest.json").exists())


def recent_weeks(season, n=2):
    """The n latest weeks that have at least one snapshot."""
    root = paths.truth(str(season), "_").parent
    wks = sorted(int(p.name[2:]) for p in root.iterdir()
                 if p.is_dir() and p.name.startswith("wk") and snapshots(season, int(p.name[2:])))
    return wks[-n:]


def load_snapshot(folder):
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    with gzip.open(folder / "stats.json.gz", "rt", encoding="utf-8") as f:
        stats = json.load(f)
    leagues = {}
    for lid in man["leagues"]:
        leagues[lid] = json.loads((folder / f"league_{lid}.json").read_text(encoding="utf-8"))
    positions = json.loads((folder / "positions.json").read_text(encoding="utf-8"))
    return man, stats, leagues, positions


# ------------------------------------------------------------------ fetch

def _league_ids():
    """Every registered league we play in. The lg08 copy of LG06 is
    ignore:true and stays out -- identical rosters would double every row."""
    ign = paths.ignored_ids()
    return [str(m["id"]) for m in paths.leagues().values() if str(m["id"]) not in ign]


def last_scored_week(get=None, ids=None):
    """Latest week Sleeper has scored, read off the leagues themselves:
    settings.last_scored_leg, max across leagues. Not /state/nfl -- its
    week flips on its own calendar and says nothing about whether
    matchups carry final points yet."""
    from battle_rhythm import sleeper_client as sc
    get = get or sc.get
    legs = []
    for lid in (ids if ids is not None else _league_ids()):
        lg = get(f"league/{lid}") or {}
        v = (lg.get("settings") or {}).get("last_scored_leg")
        if isinstance(v, int) and v > 0:
            legs.append(v)
    if not legs:
        raise SystemExit("no league reports a last_scored_leg -- nothing scored yet, or the API is down")
    return max(legs)


def _log(msg):
    p = paths.out("truth", "fetch.log")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {msg}\n")


def fetch(season, week, get=None, get_url=None, players=None, league_ids=None):
    """Every network call, once, under one timestamp. Returns the folder,
    or None when no league had matchups that week (past a season's end)."""
    from battle_rhythm import sleeper_client as sc
    from battle_rhythm.backtest_probe import BASE_STAT, ALT_STAT
    from battle_rhythm.draft_helper import _normalize
    get = get or sc.get
    get_url = get_url or sc._get

    stamp = time.strftime("%Y%m%dT%H%M%S")
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    raw = get_url(BASE_STAT.format(s=season, w=week))
    host = "api.sleeper.app"
    if not raw:
        raw = get_url(ALT_STAT.format(s=season, w=week))
        host = "api.sleeper.com"
    stats = _normalize(raw) if raw else {}
    if not stats:
        raise SystemExit(f"stats feed empty for {season} wk{week} on both hosts -- nothing written")

    docs, rostered = {}, set()
    for lid in (league_ids if league_ids is not None else _league_ids()):
        lg = get(f"league/{lid}")
        mu = get(f"league/{lid}/matchups/{week}")
        if not lg or mu is None:
            print(f"  {lid}: league or matchups unreadable -- SKIPPED, not zero", file=sys.stderr)
            continue
        pts = [m for m in mu if m.get("players_points")]
        if not pts:
            continue                   # no games this week for this league, not an error
        docs[lid] = {"league_id": lid, "name": lg.get("name"), "season": lg.get("season"),
                     "scoring_settings": lg.get("scoring_settings") or {},
                     "roster_positions": lg.get("roster_positions") or [],
                     "matchups": mu}
        for m in pts:
            rostered |= set(m["players_points"].keys())
    if not docs:
        msg = f"{season} wk{week}: no league had scored matchups -- nothing written"
        print("  " + msg)
        _log(msg)
        return None

    folder = paths.truth(str(season), f"wk{int(week):02d}", stamp, "_").parent
    kept = sorted(docs)
    for lid, doc in docs.items():
        (folder / f"league_{lid}.json").write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")

    tbl = players() if players else sc.players()
    pos = {pid: (tbl.get(pid) or {}).get("position") or
           ("DEF" if pid.isalpha() and pid.isupper() else None) for pid in sorted(rostered)}
    (folder / "positions.json").write_text(json.dumps(pos, sort_keys=True), encoding="utf-8")

    with gzip.open(folder / "stats.json.gz", "wt", encoding="utf-8") as f:
        json.dump(stats, f, sort_keys=True)
    man = {"season": str(season), "week": int(week), "fetched_at": fetched_at,
           "stats_host": host, "stat_rows": len(stats), "leagues": kept}
    (folder / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    msg = (f"{season} wk{week}: {len(stats)} stat rows ({host}), {len(kept)} leagues, "
           f"{len(rostered)} rostered players -> {folder}")
    print("  " + msg)
    _log(msg)
    return folder


def history_leagues(get=None, ids=None):
    """{season: {"ids": [prev league ids], "last": last scored week}} for
    every registered league whose previous_league_id resolves on Sleeper.
    A league migrated from another platform (LG02) or started this
    year has none, and is simply absent -- not an error."""
    from battle_rhythm import sleeper_client as sc
    get = get or sc.get
    out = {}
    for lid in (ids if ids is not None else _league_ids()):
        cur = get(f"league/{lid}") or {}
        prev = str(cur.get("previous_league_id") or "")
        if not prev.isdigit() or prev == "0":
            continue
        p = get(f"league/{prev}") or {}
        season = str(p.get("season") or "")
        last = (p.get("settings") or {}).get("last_scored_leg")
        if not season or not isinstance(last, int) or last < 1:
            continue
        slot = out.setdefault(season, {"ids": [], "last": 0})
        slot["ids"].append(prev)
        slot["last"] = max(slot["last"], last)
    return out


def fetch_history(get=None, get_url=None, players=None):
    """One snapshot per scored week of each league's previous season. Stats
    are fetched once per week and shared by every league in that season."""
    hist = history_leagues(get=get)
    if not hist:
        raise SystemExit("no registered league has a previous season on Sleeper")
    folders = []
    for season, info in sorted(hist.items()):
        _log(f"--history {season}: leagues {info['ids']}, weeks 1-{info['last']}")
        print(f"  {season}: {len(info['ids'])} leagues, weeks 1-{info['last']}")
        for w in range(1, info["last"] + 1):
            f = fetch(season, w, get=get, get_url=get_url, players=players,
                      league_ids=info["ids"])
            if f:
                folders.append(f)
    return folders


# ---------------------------------------------------------------- compare

def contributions(line, scoring):
    """{key: points} for every scoring key this line actually moves."""
    out = {}
    for k, v in (line or {}).items():
        if isinstance(v, (int, float)) and scoring.get(k):
            out[k] = round(v * scoring[k], 4)
    return out


def candidate_keys(residual, line, scoring, max_n=5):
    """Scoring keys that would explain the miss on their own: the league
    pays k, this line carries no k, and n * scoring[k] == -residual for a
    small whole n. 'Sleeper paid 2 x pr_td we never saw' reads straight
    off this. Only a hint -- two keys can combine."""
    need = -residual            # what Sleeper had that we did not
    hits = []
    for k, w in scoring.items():
        if not w or (line or {}).get(k):
            continue
        n = need / w
        if 1 <= round(n) <= max_n and abs(n - round(n)) < 1e-6:
            hits.append(f"{round(n)}x {k} ({w:+g})")
    return sorted(hits)[:6]


def compare_snapshot(man, stats, leagues, positions):
    """One row per (league, player) in the snapshot's week."""
    from battle_rhythm.sleeper_client import score
    rows = []
    for lid, doc in leagues.items():
        sc = doc["scoring_settings"]
        for m in doc["matchups"]:
            starters = set(p for p in (m.get("starters") or []) if p and p != "0")
            for pid, pts in (m.get("players_points") or {}).items():
                line = stats.get(pid)
                ours = score(line, sc) if line else 0.0
                d = round(ours - float(pts), 2)
                ad = abs(ours - float(pts))
                status = ("exact" if ad < EXACT else
                          "rounding" if ad < ROUNDING else "miss")
                if status == "miss" and not line:
                    cause = "no stat line in feed"
                elif status == "miss":
                    cause = "; ".join(candidate_keys(d, line, sc)) or "unexplained"
                else:
                    cause = ""
                rows.append({
                    "season": man["season"], "week": man["week"], "league_id": lid,
                    "league": (doc.get("name") or "").strip(),
                    "roster_id": m.get("roster_id"), "player_id": pid,
                    "position": positions.get(pid) or "",
                    "slot": "starter" if pid in starters else "bench",
                    "computed": ours, "sleeper": round(float(pts), 2), "diff": d,
                    "status": status, "cause_hint": cause,
                    "custom_points": m.get("custom_points"),
                    "source": "sleeper_players_points",
                    "fetched_at": man["fetched_at"],
                })
    return rows


def feed_gaps(stats, leagues):
    """Per league: scoring keys it pays that NO player's line carried this
    week. Either the event did not happen league-wide (plausible for a
    blocked-punt TD) or the feed never publishes it (a real engine gap).
    Two weeks of the same gap is the second kind."""
    seen = set()
    for line in stats.values():
        seen |= {k for k, v in (line or {}).items() if v}
    return {lid: sorted(k for k, w in doc["scoring_settings"].items() if w and k not in seen)
            for lid, doc in leagues.items()}


def corrections(season, week):
    """Rows whose Sleeper points moved between the two newest snapshots of
    a week: [(league_id, player_id, before, after)]. Empty with one snapshot."""
    snaps = snapshots(season, week)
    if len(snaps) < 2:
        return [], None
    _, _, old, _ = load_snapshot(snaps[-2])
    _, _, new, _ = load_snapshot(snaps[-1])
    moved = []
    for lid, doc in new.items():
        before = {}
        for m in (old.get(lid) or {}).get("matchups") or []:
            before.update(m.get("players_points") or {})
        for m in doc["matchups"]:
            for pid, pts in (m.get("players_points") or {}).items():
                if pid in before and abs(float(before[pid]) - float(pts)) >= EXACT:
                    moved.append((lid, pid, round(float(before[pid]), 2), round(float(pts), 2)))
    return sorted(moved), snaps[-2].name


def coverage(stats, leagues, rows, into=None):
    """Which scoring rules this snapshot actually PROVED.

    A paid key is proven for a league when some rostered player's line
    carried it (non-zero) and that player's row matched Sleeper exactly.
    A key that only ever appears on miss rows is suspect, not proven.
    into = {league_id: {"name", "season", "paid", "proven", "suspect"}}."""
    into = {} if into is None else into
    status = {(r["league_id"], r["player_id"]): r["status"] for r in rows}
    for lid, doc in leagues.items():
        sc = doc["scoring_settings"]
        c = into.setdefault(lid, {"name": (doc.get("name") or "").strip(),
                                  "season": str(doc.get("season") or ""),
                                  "paid": set(), "proven": set(), "suspect": set()})
        c["paid"] |= {k for k, w in sc.items() if w}
        for m in doc["matchups"]:
            for pid in (m.get("players_points") or {}):
                st = status.get((lid, pid))
                for k, v in (stats.get(pid) or {}).items():
                    if v and sc.get(k) and isinstance(v, (int, float)):
                        (c["proven"] if st in ("exact", "rounding") else c["suspect"]).add(k)
    return into


def all_snapshot_weeks():
    """[(season, week)] for every week with a snapshot, every season."""
    root = paths.truth("_").parent
    out = []
    for sd in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        for wd in sorted(p for p in sd.iterdir() if p.is_dir() and p.name.startswith("wk")):
            if snapshots(sd.name, int(wd.name[2:])):
                out.append((sd.name, int(wd.name[2:])))
    return out


FIELDS = ["season", "week", "league_id", "league", "roster_id", "player_id", "position",
          "slot", "computed", "sleeper", "diff", "status", "cause_hint", "custom_points",
          "source", "fetched_at"]


def write_rows(rows, name="player_weeks.csv"):
    """The fact table, one file, every compared week. out/ -- it is
    rebuilt from the tracked snapshots in one command. Tableau points here."""
    p = paths.out("truth", name)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["season"], r["week"], r["league_id"],
                                             r["roster_id"] or 0, r["player_id"])):
            w.writerow(r)
    return p


def _span(wks):
    wks = sorted(wks)
    if len(wks) > 2 and wks == list(range(wks[0], wks[-1] + 1)):
        return f"{wks[0]}-{wks[-1]}"
    return ",".join(str(w) for w in wks)


def _labels(pairs):
    """{league_id: display name}. Both 2025 Hybrids were NAMED 'LG03-LG05'
    (LG03 was renamed in 2026), so a bare name is
    ambiguous in history; a colliding name gets the id's last four."""
    pairs = list(pairs)
    count = defaultdict(set)
    for lid, name in pairs:
        count[name].add(lid)
    return {lid: (f"{name} (..{lid[-4:]})" if len(count[name]) > 1 else name)
            for lid, name in pairs}


def summarize(rows, gaps_by_week, corr_by_week=None, cov=None):
    lines = []
    label = _labels({(r["league_id"], r["league"]) for r in rows})
    nmiss = sum(1 for r in rows if r["status"] == "miss")
    ncorr = sum(len(v[0]) for v in (corr_by_week or {}).values())
    seasons = sorted({str(r["season"]) for r in rows})
    wks = sorted({r["week"] for r in rows})
    lines.append(f"TRUTH: {'/'.join(seasons)} weeks {_span(wks)} -- {len(rows)} rows, "
                 f"{nmiss} misses, {ncorr} stat corrections\n")
    by_lw = defaultdict(list)
    for r in rows:
        by_lw[(r["league"], r["league_id"])].append(r)
    lines.append("| League | Rows | Exact | Rounding | Miss | Match rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    tot = defaultdict(int)
    for (name, lid), rs in sorted(by_lw.items(), key=lambda kv: label[kv[0][1]]):
        name = label[lid]
        c = defaultdict(int)
        for r in rs:
            c[r["status"]] += 1
        n = len(rs)
        for k in ("exact", "rounding", "miss"):
            tot[k] += c[k]
        tot["n"] += n
        rate = (c["exact"] + c["rounding"]) / n if n else 0
        lines.append(f"| {name} | {n} | {c['exact']} | {c['rounding']} | {c['miss']} | {rate:.1%} |")
    n = tot["n"] or 1
    lines.append(f"| **All** | {tot['n']} | {tot['exact']} | {tot['rounding']} | {tot['miss']} | "
                 f"{(tot['exact'] + tot['rounding']) / n:.1%} |")

    misses = [r for r in rows if r["status"] == "miss"]
    if misses:
        lines.append("\n## Misses, grouped by league and position\n")
        grp = defaultdict(list)
        for r in misses:
            grp[(r["league"], r["position"])].append(r)
        for (lg, pos), rs in sorted(grp.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"### {lg} -- {pos or '?'} ({len(rs)})\n")
            lines.append("| Wk | Player | Slot | Computed | Sleeper | Diff | Would explain it |")
            lines.append("|---:|---|---|---:|---:|---:|---|")
            for r in sorted(rs, key=lambda r: -abs(r["diff"]))[:15]:
                lines.append(f"| {r['week']} | {r['player_id']} | {r['slot']} | {r['computed']:.2f} | "
                             f"{r['sleeper']:.2f} | {r['diff']:+.2f} | {r['cause_hint']} |")
            if len(rs) > 15:
                lines.append(f"\n... {len(rs) - 15} more in the CSV")
            lines.append("")
    if corr_by_week:
        lines.append("\n## Stat corrections (Sleeper's points moved between snapshots)\n")
        for wk, (moved, since) in sorted(corr_by_week.items()):
            if since is None:
                lines.append(f"- wk{wk}: one snapshot, nothing to compare yet")
            elif not moved:
                lines.append(f"- wk{wk}: none since {since}")
            else:
                lines.append(f"- wk{wk}: {len(moved)} since {since}")
                for lid, pid, a, b in moved[:25]:
                    lines.append(f"  - {lid} {pid}: {a:.2f} -> {b:.2f}")
    if cov:
        lines.append("\n## Rule coverage (paid keys proven on an exact row)\n")
        lines.append("| League | Season | Proven | Paid | Never exercised |")
        lines.append("|---|---|---:|---:|---|")
        for lid, c in sorted(cov.items(), key=lambda kv: (kv[1]["season"], kv[1]["name"])):
            never = sorted(c["paid"] - c["proven"] - c["suspect"])
            lines.append(f"| {label.get(lid, c['name'])} | {c['season']} | {len(c['proven'] & c['paid'])} | "
                         f"{len(c['paid'])} | {', '.join(never) or '--'} |")
        sus = {lid: sorted(c["suspect"] - c["proven"]) for lid, c in cov.items()}
        if any(sus.values()):
            lines.append("\nOnly ever seen on MISS rows (suspect, not proven):")
            for lid, ks in sorted(sus.items()):
                if ks:
                    lines.append(f"- {label.get(lid, cov[lid]['name'])} {cov[lid]['season']}: {', '.join(ks)}")
    if len(gaps_by_week) <= 2:
        lines.append("\n## Keys a league pays that no player's line carried that week\n")
        for wk, gaps in sorted(gaps_by_week.items()):
            for lid, ks in sorted(gaps.items()):
                if ks:
                    lines.append(f"- wk{wk} {lid}: {', '.join(ks)}")
    return "\n".join(lines)


def fact_table(skip=None, have=()):
    """Every row from the newest snapshot of every week of every season --
    the whole fact table, so comparing 2025 never drops 2026 from the CSV
    Tableau reads. `have` + `skip` reuse rows the caller already built."""
    rows = list(have)
    s0, w0 = skip if skip else (None, set())
    for season, w in all_snapshot_weeks():
        if season == s0 and w in w0:
            continue
        man, stats, leagues, pos = load_snapshot(latest_snapshot(season, w))
        rows += compare_snapshot(man, stats, leagues, pos)
    return rows


def compare(season, weeks):
    rows, gaps, corr, cov = [], {}, {}, {}
    for w in weeks:
        snap = latest_snapshot(season, w)
        if not snap:
            print(f"  {season} wk{w}: no snapshot -- run `python br.py truth fetch --week {w}` on the PC")
            continue
        man, stats, leagues, pos = load_snapshot(snap)
        wrows = compare_snapshot(man, stats, leagues, pos)
        rows += wrows
        coverage(stats, leagues, wrows, into=cov)
        gaps[w] = feed_gaps(stats, leagues)
        corr[w] = corrections(season, w)
        print(f"  {season} wk{w}: snapshot {snap.name} ({man['fetched_at']})")
    if not rows:
        return None
    csvp = write_rows(fact_table(skip=(str(season), set(weeks)), have=rows))
    body = summarize(rows, gaps, corr, cov)
    tag = f"{min(weeks):02d}" if len(weeks) == 1 else f"{min(weeks):02d}-{max(weeks):02d}"
    rep = paths.out("truth", f"summary_{season}_wk{tag}.md")
    rep.write_text(f"# Engine vs Sleeper, {season} wk{tag}\n\n" + body + "\n", encoding="utf-8")
    print(body)
    print(f"\n  rows    -> {csvp}\n  summary -> {rep}")
    return rows


# ---------------------------------------------------------------- selftest

def selftest():
    """Offline. The two real anchors are LG03-LG05 wk2 2026, scored by
    hand on 9/26 and matching Sleeper to the cent: 6786 36.8, 9487 16.8.
    They pin the yardage-bucket reception scoring the Hybrids run on."""
    from battle_rhythm.sleeper_client import score
    ok = []

    def ck(name, cond):
        ok.append((name, bool(cond)))
        print(f"  {'ok' if cond else 'XX'}  {name}")

    fx = json.loads(paths.fixture("truth_lg05_wk2.json").read_text(encoding="utf-8"))
    sc = fx["scoring_settings"]
    for pid, case in fx["players"].items():
        ck(f"lg05 wk2 {pid}: engine {case['sleeper']} to the cent",
           abs(score(case["stats"], sc) - case["sleeper"]) < EXACT)

    # synthetic snapshot: one exact, one rounding, one miss the hint explains,
    # one rostered player with no stat line, and a TEAM_ row nobody rosters
    scs = {"rec": 1.0, "rec_yd": 0.1, "pr_td": 6.0, "kr_yd": 0.04}
    man = {"season": "2026", "week": 1, "fetched_at": "t", "leagues": ["L"]}
    stats = {"A": {"rec": 5, "rec_yd": 50},                 # 10.0
             "B": {"rec": 2, "rec_yd": 21},                 # 4.1
             "C": {"rec": 1, "rec_yd": 10},                 # 2.0, Sleeper paid a pr_td too
             "TEAM_BUF": {"rec": 20, "rec_yd": 248}}
    leagues = {"L": {"name": "Test", "scoring_settings": scs, "matchups": [
        {"roster_id": 1, "starters": ["A", "0"], "custom_points": None,
         "players_points": {"A": 10.0, "B": 4.11, "C": 8.0, "D": 0.0, "E": 3.0}}]}}
    rows = {r["player_id"]: r for r in compare_snapshot(man, stats, leagues, {"A": "WR"})}
    ck("exact row is exact", rows["A"]["status"] == "exact")
    ck("one-cent gap is rounding, not a miss", rows["B"]["status"] == "rounding")
    ck("6-point gap is a miss", rows["C"]["status"] == "miss" and rows["C"]["diff"] == -6.0)
    ck("hint names the missing key", "1x pr_td" in rows["C"]["cause_hint"])
    ck("no stat line and 0 points is exact, not a miss", rows["D"]["status"] == "exact")
    ck("no stat line and points is flagged as such",
       rows["E"]["cause_hint"] == "no stat line in feed")
    ck("TEAM_ totals never become rows", "TEAM_BUF" not in rows)
    ck("starter vs bench read off starters, '0' ignored",
       rows["A"]["slot"] == "starter" and rows["B"]["slot"] == "bench")
    ck("every row says its source", all(r["source"] == "sleeper_players_points"
                                        for r in rows.values()))
    g = feed_gaps(stats, leagues)["L"]
    ck("feed gaps list keys no line carried", g == ["kr_yd", "pr_td"])

    # last_scored_week reads the leagues, takes the max, ignores junk
    legs = {"league/a": {"settings": {"last_scored_leg": 3}},
            "league/b": {"settings": {"last_scored_leg": 2}},
            "league/c": {"settings": {}}}
    ck("last scored week is the max last_scored_leg",
       last_scored_week(get=lambda p: legs.get(p), ids=["a", "b", "c"]) == 3)

    # corrections: two snapshots of one week, one player's points moved
    import tempfile, pathlib
    saved = paths.DATA
    try:
        paths.DATA = pathlib.Path(tempfile.mkdtemp())
        for stamp, pts in (("20260929T063000", 8.0), ("20261006T063000", 14.0)):
            f = paths.truth("2026", "wk03", stamp, "_").parent
            (f / "manifest.json").write_text(json.dumps(
                {"season": "2026", "week": 3, "fetched_at": stamp, "leagues": ["L"]}))
            with gzip.open(f / "stats.json.gz", "wt") as g:
                json.dump({}, g)
            (f / "positions.json").write_text("{}")
            (f / "league_L.json").write_text(json.dumps({"scoring_settings": {}, "matchups": [
                {"roster_id": 1, "players_points": {"X": pts, "Y": 5.0}}]}))
        moved, since = corrections("2026", 3)
        ck("a stat correction is caught, and only the player who moved",
           moved == [("L", "X", 8.0, 14.0)] and since == "20260929T063000")
        ck("recent_weeks finds the snapshotted week", recent_weeks("2026") == [3])

        # history: previous_league_id -> that season, weeks 1..last_scored_leg;
        # a league with no previous season (or a "0") is skipped, not fatal
        api = {"league/H": {"previous_league_id": "9000000000000000006"},
               "league/N": {"previous_league_id": None},
               "league/Z": {"previous_league_id": "0"},
               "league/9000000000000000006": {"season": "2025",
                                              "settings": {"last_scored_leg": 17}}}
        h = history_leagues(get=lambda q: api.get(q), ids=["H", "N", "Z"])
        ck("history resolves only leagues with a previous season",
           h == {"2025": {"ids": ["9000000000000000006"], "last": 17}})

        # fetch past a season's end: no scored matchups -> nothing written
        sc0 = {"rec": 1.0}
        api2 = {"league/P": {"name": "Old", "season": "2025", "scoring_settings": sc0},
                "league/P/matchups/18": [{"roster_id": 1, "players_points": {}}],
                "league/P/matchups/5": [{"roster_id": 1, "starters": ["A"],
                                         "players_points": {"A": 4.0}}]}
        f18 = fetch("2025", 18, get=lambda q: api2.get(q), get_url=lambda u: {"A": {"rec": 4}},
                    players=lambda: {"A": {"position": "WR"}}, league_ids=["P"])
        ck("a week with no scored matchups writes nothing", f18 is None
           and not snapshots("2025", 18))
        f5 = fetch("2025", 5, get=lambda q: api2.get(q), get_url=lambda u: {"A": {"rec": 4}},
                   players=lambda: {"A": {"position": "WR"}}, league_ids=["P"])
        ck("a past-season week is snapshotted under its own season",
           f5 is not None and latest_snapshot("2025", 5) == f5)

        # the fact table spans seasons: comparing 2025 keeps 2026 rows
        ft = fact_table()
        ck("fact table carries every season's weeks",
           {(str(r["season"]), r["week"]) for r in ft} >= {("2025", 5)})

        # coverage: rec proven on an exact row; kr_yd paid, never carried
        man5, st5, lg5, pos5 = load_snapshot(f5)
        lg5["P"]["scoring_settings"] = {"rec": 1.0, "kr_yd": 0.04}
        rows5 = compare_snapshot(man5, st5, lg5, pos5)
        cv = coverage(st5, lg5, rows5)["P"]
        ck("coverage: a key on an exact row is proven, an unseen key is not",
           cv["proven"] == {"rec"} and cv["paid"] - cv["proven"] == {"kr_yd"})
        rows5[0]["status"] = "miss"
        cv2 = coverage(st5, lg5, rows5)["P"]
        ck("coverage: a key seen only on a miss is suspect, not proven",
           cv2["suspect"] == {"rec"} and not cv2["proven"])
    finally:
        paths.DATA = saved

    # invented names and short ids on purpose: a public copy rewrites real
    # league names and every Sleeper-length id, and this checks the labeller
    lb = _labels([("L4497", "Hybrid 9"), ("L0001", "Hybrid 9"), ("L0002", "Dynasty Crew")])
    ck("two leagues sharing a name are told apart by id; a unique name is left alone",
       lb["L4497"] == "Hybrid 9 (..4497)" and lb["L0002"] == "Dynasty Crew")

    bad = [n for n, c in ok if not c]
    print(f"\n{len(ok) - len(bad)}/{len(ok)} " + ("selftest PASSED" if not bad else "FAILED"))
    return 1 if bad else 0


# --------------------------------------------------------------------- cli

def _weeks(argv):
    for i, a in enumerate(argv):
        if a in ("--week", "--weeks") and i + 1 < len(argv):
            v = argv[i + 1]
            if "-" in v:
                a0, b0 = v.split("-", 1)
                return list(range(int(a0), int(b0) + 1))
            return [int(v)]
    return None


def main(argv):
    if "--selftest" in argv:
        return selftest()
    season = SEASON_DEFAULT
    if "--season" in argv:
        season = argv[argv.index("--season") + 1]
    weeks = _weeks(argv)
    if argv and argv[0] == "fetch" and "--last" in argv:
        last = last_scored_week()
        weeks = [w for w in (last - 1, last) if w >= 1]
        _log(f"--last resolved to weeks {weeks}")
    if argv and argv[0] == "compare" and "--recent" in argv:
        weeks = recent_weeks(season)
    if argv and argv[0] == "compare" and "--all" in argv:
        weeks = recent_weeks(season, n=99)
    if argv and argv[0] == "fetch" and "--history" in argv:
        n = len(fetch_history())
        print(f"\n  {n} history snapshots written. `python br.py truth compare --season <year> --all` "
              "runs anywhere from here.")
        return 0
    if not argv or argv[0] not in ("fetch", "compare") or not weeks:
        print(__doc__.split("\n\n")[1])
        return 2
    if argv[0] == "fetch":
        for w in weeks:
            fetch(season, w)
        print("\n  Snapshot written. `python br.py truth compare --weeks "
              f"{weeks[0]}-{weeks[-1]}` runs anywhere from here.")
        return 0
    return 0 if compare(season, weeks) is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
