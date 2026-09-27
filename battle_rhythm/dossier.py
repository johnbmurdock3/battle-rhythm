"""
dossier.py — the player research store.

One JSON file per player under dossiers/, keyed by Sleeper player_id.
One file per player is deliberate: names collide, and parallel
researchers never write the same file.

    python dossier.py show "jordan mason"
    python dossier.py show "gainwell" --league dynasty
    python dossier.py stats                # coverage + staleness report
    python dossier.py stale --days 14      # what needs a refresh
    python dossier.py --selftest           # offline

The stable/volatile split is the thing that keeps this affordable.
Team history, career workload, contract, and scheme hold for a
season. Injury status and camp reports decay in days. Compile stable
once; refresh volatile the morning of a draft.

Staleness is displayed, never hidden. A three-week-old camp report
presented as current is worse than no dossier at all.
"""

import json
import pathlib
from battle_rhythm import paths as _paths
import re
import sys
from datetime import date, datetime

STORE = _paths.DOSSIERS

# how long each half stays trustworthy
FRESH_DAYS = {"stable": 120, "volatile": 10}

SCHEMA_KEYS = ("player_id", "name", "as_of", "stable", "volatile",
               "sources", "confidence")


def _today():
    return date.today().isoformat()


def _age_days(iso):
    try:
        d = datetime.fromisoformat(str(iso)[:10]).date()
    except (ValueError, TypeError):
        return None
    return (date.today() - d).days


def blank(player_id, name):
    return {"player_id": str(player_id), "name": name, "as_of": _today(),
            "stable": {"team_history": [], "workload": [], "contract": {},
                       "scheme": {}, "competition": [], "notes": []},
            "volatile": {"injury": {}, "camp": [], "projected_share": None,
                         "as_of": _today()},
            "timeline": [],
            "sources": [], "confidence": "low"}


# ------------------------------------------------------------ timeline

TIMELINE_KEYS = ("date", "snap_pct", "route_pct", "target_share", "touches",
                 "injury", "role", "note", "source")


def append_observation(doc, obs):
    """Append a dated weekly observation. NEVER overwrites.

    The whole point of a weekly refresh is slope, not state. A player at
    71% snaps means one thing; a player who went 45 -> 58 -> 71 over
    three weeks means something the projection feed cannot show you.
    Overwriting `volatile` each week would throw exactly that away.

    Same-date observations replace each other (a re-run corrects itself);
    different dates accumulate. Kept sorted by date."""
    if not obs.get("date"):
        raise ValueError("observation needs a date")
    tl = [o for o in (doc.get("timeline") or []) if o.get("date") != obs["date"]]
    tl.append({k: obs.get(k) for k in TIMELINE_KEYS if obs.get(k) is not None})
    doc["timeline"] = sorted(tl, key=lambda o: str(o.get("date")))
    # volatile mirrors the newest observation so existing readers still work
    newest = doc["timeline"][-1]
    vol = doc.setdefault("volatile", {})
    vol["as_of"] = newest["date"]
    if newest.get("injury"):
        vol["injury"] = (newest["injury"] if isinstance(newest["injury"], dict)
                         else {"status": newest["injury"],
                               "as_of": newest["date"]})
    doc["as_of"] = max(str(doc.get("as_of") or ""), str(newest["date"]))
    return doc


def trend(doc, field="snap_pct", window=3):
    """(direction, delta, points) over the last `window` observations.
    direction: 'up' | 'down' | 'flat' | None when there isn't enough data.
    Two observations is the minimum for a slope — one is a fact, not a
    trend, and reporting it as one is how you talk yourself into a bad
    waiver claim."""
    vals = [(o.get("date"), o.get(field)) for o in (doc.get("timeline") or [])
            if isinstance(o.get(field), (int, float))]
    vals = vals[-window:]
    if len(vals) < 2:
        return None, None, vals
    delta = vals[-1][1] - vals[0][1]
    thresh = 0.05 if vals[-1][1] <= 1.0 else 5.0   # fraction vs percent
    direction = "up" if delta > thresh else "down" if delta < -thresh else "flat"
    return direction, round(delta, 3), vals


def validate(doc):
    """Returns list of problems. Empty list = usable."""
    bad = []
    for k in SCHEMA_KEYS:
        if k not in doc:
            bad.append(f"missing key: {k}")
    if doc.get("confidence") not in ("high", "medium", "low", None):
        bad.append(f"bad confidence: {doc.get('confidence')}")
    for s in doc.get("sources") or []:
        if not isinstance(s, dict) or not s.get("url"):
            bad.append("source without url")
    # a dossier with no sources is a dossier of assertions
    if doc.get("confidence") in ("high", "medium") and not doc.get("sources"):
        bad.append("confidence claimed without any source")
    return bad


def path_for(player_id):
    return STORE / f"{player_id}.json"


def save(doc):
    problems = validate(doc)
    if problems:
        raise ValueError("; ".join(problems))
    STORE.mkdir(exist_ok=True)
    path_for(doc["player_id"]).write_text(json.dumps(doc, indent=1))
    return path_for(doc["player_id"])


def load(player_id):
    p = path_for(player_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def all_docs():
    if not STORE.exists():
        return []
    out = []
    for p in sorted(STORE.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"  (unreadable: {p.name})")
    return out


def freshness(doc):
    """(stable_days, volatile_days, worst_label)."""
    sd = _age_days(doc.get("as_of"))
    vd = _age_days((doc.get("volatile") or {}).get("as_of") or doc.get("as_of"))
    label = "current"
    if vd is not None and vd > FRESH_DAYS["volatile"]:
        label = f"volatile stale ({vd}d)"
    if sd is not None and sd > FRESH_DAYS["stable"]:
        label = f"stale ({sd}d)"
    return sd, vd, label


def render(doc):
    sd, vd, label = freshness(doc)
    L = [f"{doc.get('name')}  [{doc.get('confidence') or '?'} confidence"
         f" · {label}]"]
    st = doc.get("stable") or {}
    th = st.get("team_history") or []
    if th:
        L.append("  teams:  " + " -> ".join(
            f"{t.get('season')} {t.get('team')}" for t in th))
    for w in st.get("workload") or []:
        bits = [f"{k} {v}" for k, v in w.items()
                if k not in ("season", "team") and v not in (None, "")]
        L.append(f"  {w.get('season')} {w.get('team', '')}: "
                 + ", ".join(bits))
    if st.get("contract"):
        c = st["contract"]
        L.append("  contract: " + (c.get("note")
                 or f"{c.get('years', '?')}yr signed {c.get('signed', '?')}"))
    if st.get("scheme"):
        s = st["scheme"]
        L.append("  scheme: " + (s.get("note") or str(s.get("oc") or "")))
    for c in st.get("competition") or []:
        L.append(f"  ahead/behind: {c.get('name')} "
                 f"({c.get('age', '?')}) {c.get('status', '')} "
                 f"{c.get('note', '')}".rstrip())
    vol = doc.get("volatile") or {}
    inj = vol.get("injury") or {}
    if inj:
        L.append(f"  injury: {inj.get('status', '?')} "
                 f"(as of {inj.get('as_of', '?')})")
    if vol.get("projected_share") is not None:
        L.append(f"  projected share: {vol['projected_share']}")
    for c in (vol.get("camp") or [])[:4]:
        L.append(f"  camp [{c.get('date', '?')}] {c.get('who', '')}: "
                 f"\"{c.get('quote', '')}\"")
    tl = doc.get("timeline") or []
    if tl:
        L.append(f"  timeline ({len(tl)} obs):")
        for o in tl[-4:]:
            bits = [f"{k} {o[k]}" for k in ("snap_pct", "route_pct",
                                            "target_share", "touches", "role")
                    if o.get(k) not in (None, "")]
            inj = o.get("injury")
            if inj:
                bits.append(f"inj {inj if isinstance(inj, str) else inj.get('status')}")
            L.append(f"    {o.get('date')}  " + " · ".join(bits))
            if o.get("note"):
                L.append(f"      {o['note']}")
        for f in ("snap_pct", "target_share"):
            d, delta, pts = trend(doc, f)
            if d and d != "flat":
                L.append(f"  TREND {f}: {d} {delta:+} over "
                         f"{len(pts)} obs ({pts[0][0]} -> {pts[-1][0]})")
    for n in st.get("notes") or []:
        L.append(f"  note: {n}")
    for s in (doc.get("sources") or [])[:6]:
        L.append(f"  src: {s.get('url')}  ({s.get('fetched', '?')})")
    return "\n".join(L)


# ------------------------------------------------- opportunity flags

# Word-boundary matched, ALWAYS. The first version used plain substring
# tests and "nfi" matched inside "confirmed" while "ir " matched the end
# of "their" — which flagged Saquon Barkley as injured on the strength of
# the word "confirmed". Short medical abbreviations are exactly the tokens
# that hide inside ordinary words; never substring-match them.
SEVERE = (r"\bacl\b", r"\bachilles\b", r"\bpup\b", r"\bnfi\b", r"\bir\b",
          r"no timetable", r"no return timetable", r"long way away",
          r"season[- ]ending", r"\btorn\b", r"\bindefinitely\b",
          r"out for the season", r"tore (his|a|an)")
# Departure needs DIRECTION, not just the verb. Bare "traded" matched
# "Rams traded up for him" (acquisition) and "Traded from Detroit to
# Jacksonville" (arrival at the player's own team). Both read as
# vacancies. Require the direction word.
DEPARTED = (r"traded away", r"traded to\b", r"\breleased\b", r"left for ",
            r"left in free agency", r"\bdeparted\b", r"no longer (with|on)",
            r"\bwaived\b", r"signed elsewhere", r"\bgone to\b",
            r"\bdeparture\b")
# Past seasons. 2026 is the season being drafted, so a clause naming an
# earlier year is history, not current status.
PAST = r"\b(20[01]\d|202[0-5])\b"
HISTORY = r"(history|previously|last season|career|bounced|entering the season)"
# Recovery language, so a competitor described as BACK from an injury is
# not read as currently out.
CLEARED = (r"\bcleared\b", r"full[- ]go", r"no restrictions", r"fully recovered",
           r"full participant", r"full speed", r"\brecovered\b",
           r"returned from", r"\bback from\b", r"no setbacks", r"healthy")


def _blob(*parts):
    return " ".join(str(p or "") for p in parts).lower()


def _hit(pattern_list, text):
    """First pattern that matches on a word boundary, else None."""
    for p in pattern_list:
        m = re.search(p, text)
        if m:
            return m.group(0).strip()
    return None


def _current_hit(pattern_list, text):
    """Like _hit, but CLAUSE BY CLAUSE, skipping history and recoveries.

    Competitor notes are biographies, and a biography names other
    people's injuries and old seasons. Three real false positives this
    fixes:
      - Wan'Dale Robinson's note mentions *Malik Nabers'* ACL tear
      - Chris Olave's note lists his 2023/2024 concussion history
      - Travis Hunter's note describes a 2025 season-ending LCL injury
        he has since fully recovered from
    A clause naming a season before 2026, carrying history language, or
    carrying recovery language is not a current-status clause."""
    for clause in re.split(r"[.;]|(?<=\))\s+(?=[A-Z])", text or ""):
        if not clause or not clause.strip():
            continue
        if re.search(PAST, clause) or re.search(HISTORY, clause):
            continue
        if _hit(CLEARED, clause):
            continue
        h = _hit(pattern_list, clause)
        if h:
            return h
    return None


def opportunity_flags(doc):
    """Flags with ATTRIBUTION — whose body the injury is in decides the sign.

    A keyword scan across a whole dossier ranks the beneficiaries next to
    the casualties: Nabers shows 'torn ACL' because he tore his, Tyler
    Warren shows it because Alec Pierce did. The schema already separates
    these — volatile.injury is the player's own, stable.competition[] is
    everyone else's — so attribution is structural, not guesswork.
    See MISPRICING.md, 'the attribution trap'.

    Returns list of (tag, detail):
      BLOCKED     his own injury is severe -> the market's flat tag is
                  understating the risk
      INHERITING  someone ahead of him is hurt or gone -> opportunity the
                  ADP has not repriced
      WATCH       conflicting or thin reporting -> look before you act
    """
    out = []
    vol = doc.get("volatile") or {}
    inj = vol.get("injury") or {}
    # His OWN injury field is a current-status field by schema definition,
    # so a past year in it is a start date, not history: "torn ACL
    # suffered Week 4, 2025, still rehabbing" is current. Clause-filtering
    # this the way we filter competitor biographies silently dropped
    # Malik Nabers, the single most important flag in the set. Only the
    # recovery check applies here.
    own = _blob(inj.get("status"), inj.get("note"), inj.get("body_part"))
    sev = _hit(SEVERE, own)
    if sev and not _hit(CLEARED, own):
        out.append(("BLOCKED", f"own injury: {sev}"))

    for c in (doc.get("stable") or {}).get("competition") or []:
        name = c.get("name")
        if not name:
            continue
        # status is the current-state field; note is a biography. Both are
        # clause-filtered, but status carries the signal.
        ct = _blob(c.get("status"), c.get("note"))
        csev, cgone = _current_hit(SEVERE, ct), _current_hit(DEPARTED, ct)
        if csev:
            out.append(("INHERITING", f"{name} out ({csev})"))
        elif cgone:
            out.append(("INHERITING", f"{name} gone ({cgone})"))

    txt = _blob(*(doc.get("stable") or {}).get("notes") or [])
    if doc.get("confidence") == "low":
        out.append(("WATCH", "thin reporting"))
    elif any(k in txt for k in ("conflict", "unresolved", "unclear",
                                "needs verification", "sources conflict")):
        out.append(("WATCH", "sources conflict"))
    return out


def headline(doc, maxlen=88):
    """One line for a board cell: the flags, else the freshest real note."""
    flags = opportunity_flags(doc)
    if flags:
        s = " · ".join(f"{t}: {d}" for t, d in flags[:2])
    else:
        notes = (doc.get("stable") or {}).get("notes") or []
        inj = ((doc.get("volatile") or {}).get("injury") or {}).get("status")
        s = (inj or (notes[0] if notes else "")) or ""
    s = " ".join(str(s).split())
    return s[:maxlen - 1] + "…" if len(s) > maxlen else s


def load_all_headlines(maxlen=88):
    """{player_id: (headline, [tags], stale_days)} — one read for a render.
    maxlen is the caller's column budget: a cramped cell wants 88, the
    wide dynasty board can carry a full sentence."""
    out = {}
    for d in all_docs():
        _s, vd, _l = freshness(d)
        out[str(d.get("player_id"))] = (headline(d, maxlen),
                                        [t for t, _ in opportunity_flags(d)],
                                        vd)
    return out


def cmd_preflight(league_frag, window=60):
    """python dossier.py preflight <league> — the morning-of ritual.

    Everything in your likely pick range that the research flags, plus
    anything whose volatile half has aged out. This is the check the
    Hybrid brief tells you to run and never made concrete."""
    from battle_rhythm.draft_helper import board_data
    from battle_rhythm.dynasty_value import resolve_league
    lid = resolve_league(league_frag)
    d = board_data(lid, depth=200)
    heads = load_all_headlines()
    picks = [p[0] for p in (d.get("next_picks") or [])]
    print(f"{d['lg']['name']} — preflight"
          + (f" · next picks {picks}" if picks else " · pre-draft"))
    lo = min(picks) if picks else 1
    hot, stale, missing = [], [], []
    for r in d["rows"]:
        adp = r.get("adp")
        if adp and adp > lo + window:
            continue
        h = heads.get(r["pid"])
        if h is None:
            missing.append(r)
            continue
        head, tags, vd = h
        if tags:
            hot.append((adp or 999, r, head, tags))
        if vd is not None and vd > FRESH_DAYS["volatile"]:
            stale.append((adp or 999, r, vd))
    print(f"\nFLAGGED in range (next {window} picks):")
    for adp, r, head, tags in sorted(hot)[:25]:
        mark = "!!" if "BLOCKED" in tags else "++" if "INHERITING" in tags else "??"
        print(f"  {mark} {(f'{adp:.0f}' if adp < 999 else '-'):>5}  "
              f"{r['name'].split(' (')[0][:22]:<22} {head}")
    if stale:
        print(f"\nSTALE research (>{FRESH_DAYS['volatile']}d), re-check before drafting:")
        for adp, r, vd in sorted(stale)[:12]:
            print(f"     {(f'{adp:.0f}' if adp < 999 else '-'):>5}  "
                  f"{r['name'].split(' (')[0][:22]:<22} {vd}d old")
    if missing:
        print(f"\nNO DOSSIER ({len(missing)} in range): "
              + ", ".join(r["name"].split(" (")[0] for r in missing[:8]))


def cmd_show(query, league=None):
    from battle_rhythm.sleeper_client import players
    from battle_rhythm.draft_helper import player_hits
    tbl = players()
    hits, _h = player_hits(tbl, query)
    if not hits:
        print(f"no player matching '{query}'")
        return
    found = 0
    for pid, m in hits[:5]:
        doc = load(pid)
        if doc:
            print(render(doc) + "\n")
            found += 1
    if not found:
        names = ", ".join(
            (m.get("full_name") or pid) for pid, m in hits[:5])
        print(f"no dossier yet for: {names}")


def cmd_import(bundle_path):
    """Explode a research bundle into the per-player store.

    Research runs produce one bundle file so a single transfer carries
    a whole wave; the store itself stays one-file-per-player. Existing
    dossiers are only overwritten by a NEWER as_of, so re-importing an
    old wave cannot clobber fresher work."""
    doc = json.loads(pathlib.Path(bundle_path).read_text(encoding="utf-8"))
    incoming = doc.get("dossiers") or {}
    STORE.mkdir(exist_ok=True)
    new = upd = skip = bad = 0
    for pid, d in incoming.items():
        probs = validate(d)
        if probs:
            print(f"  REJECT {pid}: {'; '.join(probs)}")
            bad += 1
            continue
        cur = load(pid)
        if cur is None:
            save(d)
            new += 1
        elif str(d.get("as_of")) >= str(cur.get("as_of")):
            save(d)
            upd += 1
        else:
            skip += 1
    print(f"imported {new} new, {upd} updated, {skip} older-skipped, "
          f"{bad} rejected  ->  {STORE}")


def refresh_list(rostered, waiver_pool, days=7):
    """Who needs a weekly refresh — deliberately NOT everyone.

    447 players a week is unaffordable and mostly wasted: a deep-bench
    back's situation does not change, and if it does you will hear about
    it. Three groups earn a weekly look:

      own      every player you roster, in any league — your lineup and
               trade decisions all run through these
      waiver   the top available players by board rank in each league —
               the only outsiders you can actually act on
      open     anyone whose dossier carries an unresolved question: on
               PUP/NFI/IR, a conflicting report, or confidence "low"

    Returns (list of dicts, counts). Everything else keeps its stable
    facts and ages out of the volatile half honestly."""
    own, wai, opn = set(map(str, rostered)), set(map(str, waiver_pool)), set()
    for d in all_docs():
        pid = str(d.get("player_id"))
        inj = ((d.get("volatile") or {}).get("injury") or {})
        blob = " ".join(str(x) for x in (inj.get("status"), inj.get("note"),
                                         *(d["stable"].get("notes") or []))).lower()
        if (d.get("confidence") == "low"
                or any(k in blob for k in ("pup", "nfi", " ir", "no timetable",
                                           "conflict", "unresolved", "unclear",
                                           "long way away", "no return"))):
            opn.add(pid)
    rows = []
    for pid in sorted(own | wai | opn):
        d = load(pid)
        _s, vd, label = freshness(d) if d else (None, None, "no dossier")
        why = [w for w, s in (("own", own), ("waiver", wai), ("open", opn))
               if pid in s]
        if d is not None and vd is not None and vd < days and "own" not in why \
                and "open" not in why:
            continue          # waiver-only and still fresh: skip
        rows.append({"player_id": pid, "name": (d or {}).get("name", "?"),
                     "reason": ",".join(why), "stale_days": vd,
                     "has_dossier": d is not None})
    return rows, {"own": len(own), "waiver": len(wai), "open": len(opn),
                  "to_refresh": len(rows)}


def cmd_refresh_list(league_frag=None, days=7):
    """python dossier.py refresh-list [league] — this week's work list."""
    from battle_rhythm.sleeper_client import load_leagues
    from battle_rhythm.draft_helper import board_data
    rostered, pool = set(), set()
    for lg in load_leagues()["leagues"]:
        if league_frag and league_frag.lower() not in (lg["name"] or "").lower():
            continue
        rostered |= {p for p in (lg.get("my_players") or []) if p}
        try:
            d = board_data(lg["league_id"], with_adp=False, depth=40)
            pool |= {r["pid"] for r in d["rows"][:40]}
        except Exception as e:
            print(f"  (board failed for {lg['name']}: {e})")
    rows, counts = refresh_list(rostered, pool, days)
    print(f"rostered {counts['own']} · waiver-relevant {counts['waiver']} · "
          f"open questions {counts['open']}  ->  refresh {counts['to_refresh']}")
    print(f"\n{'reason':<14}{'stale':>7}  player")
    for r in rows:
        sd = f"{r['stale_days']}d" if r["stale_days"] is not None else "new"
        print(f"{r['reason']:<14}{sd:>7}  {r['name']} ({r['player_id']})")
    out = _paths.out("refresh_list.json")
    out.write_text(json.dumps({"generated": _today(), "counts": counts,
                               "players": rows}, indent=1))
    print(f"\nwrote {out}")


def cmd_stats():
    docs = all_docs()
    if not docs:
        print("no dossiers yet")
        return
    conf, stale_v, stale_s = {}, 0, 0
    for d in docs:
        conf[d.get("confidence") or "?"] = conf.get(
            d.get("confidence") or "?", 0) + 1
        sd, vd, label = freshness(d)
        if label.startswith("volatile"):
            stale_v += 1
        elif label.startswith("stale"):
            stale_s += 1
    print(f"{len(docs)} dossiers")
    print("  confidence: " + "  ".join(f"{k}:{v}" for k, v in sorted(conf.items())))
    print(f"  volatile stale (>{FRESH_DAYS['volatile']}d): {stale_v}")
    print(f"  fully stale (>{FRESH_DAYS['stable']}d): {stale_s}")
    nosrc = sum(1 for d in docs if not d.get("sources"))
    print(f"  without sources: {nosrc}")


def cmd_stale(days):
    for d in all_docs():
        _sd, vd, _l = freshness(d)
        if vd is not None and vd >= days:
            print(f"{vd:>4}d  {d.get('name')}  ({d.get('player_id')})")


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'ok' if cond else 'XX'}  {name}")
        ok = ok and cond

    b = blank("123", "Test Player")
    check("blank validates", validate(b) == [])
    b["confidence"] = "high"
    check("high confidence without sources is rejected",
          any("without any source" in p for p in validate(b)))
    b["sources"] = [{"url": "https://x", "fetched": "2026-08-11"}]
    check("...accepted once sourced", validate(b) == [])
    b["sources"] = [{"fetched": "2026-08-11"}]
    check("source without url rejected",
          any("without url" in p for p in validate(b)))
    del b["stable"]
    check("missing schema key caught",
          any("missing key: stable" in p for p in validate(b)))

    old = blank("9", "Stale Guy")
    old["volatile"]["as_of"] = "2026-01-01"
    _s, _v, label = freshness(old)
    check(f"stale volatile flagged ({label})", "stale" in label)

    fresh = blank("8", "Fresh Guy")
    _s, _v, label2 = freshness(fresh)
    check("today's dossier reads current", label2 == "current")

    r = render(blank("7", "Render Guy"))
    check("render works on an empty dossier", "Render Guy" in r)

    # timeline: append accumulates, never overwrites
    d = blank("5", "Trend Guy")
    for date, snap in (("2026-09-15", 0.45), ("2026-09-22", 0.58),
                       ("2026-09-29", 0.71)):
        append_observation(d, {"date": date, "snap_pct": snap,
                               "source": "https://x"})
    check("three observations accumulate", len(d["timeline"]) == 3)
    dirn, delta, pts = trend(d, "snap_pct")
    check(f"rising snap share reads as up ({dirn} {delta})", dirn == "up")
    check("volatile mirrors the newest date",
          d["volatile"]["as_of"] == "2026-09-29")
    # same-date re-run corrects rather than duplicates
    append_observation(d, {"date": "2026-09-29", "snap_pct": 0.68})
    check("same-date re-run replaces, no duplicate", len(d["timeline"]) == 3)
    check("...and keeps the corrected value",
          d["timeline"][-1]["snap_pct"] == 0.68)
    # one observation is a fact, not a trend
    d2 = blank("6", "One Point")
    append_observation(d2, {"date": "2026-09-15", "snap_pct": 0.9})
    check("single observation reports no trend",
          trend(d2, "snap_pct")[0] is None)
    check("flat is flat",
          trend({"timeline": [{"date": "a", "snap_pct": .70},
                              {"date": "b", "snap_pct": .71}]},
                "snap_pct")[0] == "flat")
    # appended docs still validate
    d["sources"] = [{"url": "https://x", "fetched": "2026-09-29"}]
    d["confidence"] = "high"
    check("timeline docs still pass validation", validate(d) == [])

    # THE ATTRIBUTION TRAP: same keywords, opposite meaning, decided
    # entirely by whose body the injury is in.
    def sourced(pid, name):
        # blank() is confidence "low", which correctly earns its own WATCH
        # flag. Researched players are not low, so set it here or the
        # attribution assertions test the wrong thing.
        d = blank(pid, name)
        d["confidence"] = "high"
        d["sources"] = [{"url": "https://x", "fetched": _today()}]
        return d

    casualty = sourced("10", "Casualty")
    casualty["volatile"]["injury"] = {"status": "Torn ACL, out for the season"}
    tags = [t for t, _ in opportunity_flags(casualty)]
    check("own torn ACL reads as BLOCKED", tags == ["BLOCKED"])

    beneficiary = sourced("11", "Beneficiary")
    beneficiary["stable"]["competition"] = [
        {"name": "Starter Ahead", "age": 28, "status": "PUP, no timetable"}]
    tags2 = [t for t, _ in opportunity_flags(beneficiary)]
    check("competitor's PUP reads as INHERITING", tags2 == ["INHERITING"])
    check("the two never collapse together", tags != tags2)

    departed = sourced("12", "Vacancy")
    departed["stable"]["competition"] = [
        {"name": "Old Guy", "status": "traded to BUF in March"}]
    check("competitor traded away reads as INHERITING",
          [t for t, _ in opportunity_flags(departed)] == ["INHERITING"])

    cleared = sourced("13", "Cleared Guy")
    cleared["volatile"]["injury"] = {"status": "Torn ACL 2025, fully cleared, "
                                               "no restrictions"}
    check("a cleared severe injury is NOT flagged blocked",
          "BLOCKED" not in [t for t, _ in opportunity_flags(cleared)])

    thin = blank("14", "Thin Guy")
    check("low confidence reads as WATCH",
          [t for t, _ in opportunity_flags(thin)] == ["WATCH"])

    # THE SUBSTRING BUG: "nfi" hides in "confirmed", "ir" hides in
    # "their". v1 substring-matched and flagged Saquon Barkley as
    # injured off the word "confirmed".
    fp = sourced("15", "False Positive")
    fp["volatile"]["injury"] = {"status": "no current injury confirmed; "
                                          "their staff expects him ready"}
    check("'confirmed'/'their' no longer trip the injury flags",
          opportunity_flags(fp) == [])
    fp2 = sourced("16", "Comp False Positive")
    fp2["stable"]["competition"] = [
        {"name": "Healthy Guy", "status": "role confirmed, their WR1"}]
    check("...and not via a competitor either", opportunity_flags(fp2) == [])
    real = sourced("17", "Real IR")
    real["volatile"]["injury"] = {"status": "placed on IR"}
    check("a real 'IR' still fires",
          [t for t, _ in opportunity_flags(real)] == ["BLOCKED"])

    # DIRECTION: a competitor SIGNING WITH your team is arrival, not exit
    arrival = sourced("18", "More Competition")
    arrival["stable"]["competition"] = [
        {"name": "New Guy", "status": "signed with the team in March"}]
    check("a competitor arriving is not an inheritance",
          opportunity_flags(arrival) == [])
    exit_ = sourced("19", "Real Vacancy")
    exit_["stable"]["competition"] = [
        {"name": "Old Guy", "status": "traded to BUF"}]
    check("a competitor actually leaving still fires",
          [t for t, _ in opportunity_flags(exit_)] == ["INHERITING"])
    recovered = sourced("20", "Comp Recovered")
    recovered["stable"]["competition"] = [
        {"name": "Rival", "status": "returned from ACL, fully recovered"}]
    check("a recovered competitor is not an inheritance",
          opportunity_flags(recovered) == [])

    # HISTORY vs CURRENT, the four real false positives from the live run
    third = sourced("21", "Third Party")
    third["stable"]["competition"] = [
        {"name": "Healthy Starter", "status": "starting slot WR",
         "note": "posted a 1,000-yd season in 2025 after Malik Nabers' "
                 "Week 4 ACL tear"}]
    check("another player's injury inside a bio is not an inheritance",
          opportunity_flags(third) == [])
    hist = sourced("22", "Old News")
    hist["stable"]["competition"] = [
        {"name": "Extended Guy", "status": "starting WR1, recently extended",
         "note": "concussion history: 2023 grade 1, 2024 season-ending"}]
    check("a competitor's injury HISTORY is not an inheritance",
          opportunity_flags(hist) == [])
    arrived = sourced("23", "Arrival")
    arrived["stable"]["competition"] = [
        {"name": "New Depth", "status": "added depth",
         "note": "Traded from Detroit to Jacksonville, adding size"}]
    check("a competitor traded TO the team is not an inheritance",
          opportunity_flags(arrived) == [])
    acquired = sourced("24", "Acquisition")
    acquired["stable"]["competition"] = [
        {"name": "Young Back", "status": "RB on roster (pick the Rams "
                                         "traded up for)"}]
    check("'traded up for' is acquisition, not departure",
          opportunity_flags(acquired) == [])

    # ...and the false NEGATIVE that fix nearly caused: an ongoing injury
    # naming the season it started in is still current.
    ongoing = sourced("25", "Still Hurt")
    ongoing["volatile"]["injury"] = {
        "status": "Recovering from torn ACL suffered Week 4, 2025; "
                  "cleanup procedure in spring 2026, ~70-80% through rehab"}
    check("an ongoing injury dated to a past season still fires",
          [t for t, _ in opportunity_flags(ongoing)] == ["BLOCKED"])
    check("headline is a single short line",
          "\n" not in headline(casualty) and len(headline(casualty)) <= 88)

    # refresh triage: rostered and open always in, fresh waiver-only out
    import tempfile
    global STORE
    _orig = STORE
    STORE = pathlib.Path(tempfile.mkdtemp())
    try:
        mine = blank("100", "My Guy")
        mine["volatile"]["as_of"] = _today()
        save(mine)
        fresh_w = blank("200", "Fresh Waiver")
        fresh_w["volatile"]["as_of"] = _today()
        fresh_w["confidence"] = "medium"
        fresh_w["sources"] = [{"url": "https://x"}]
        save(fresh_w)
        hurt = blank("300", "PUP Guy")
        hurt["volatile"]["as_of"] = _today()
        hurt["volatile"]["injury"] = {"status": "On PUP, no timetable"}
        hurt["confidence"] = "high"
        hurt["sources"] = [{"url": "https://x"}]
        save(hurt)
        rows, counts = refresh_list(["100"], ["200", "300"])
        ids = {r["player_id"] for r in rows}
        check("rostered player always refreshed", "100" in ids)
        check("open-question player always refreshed", "300" in ids)
        check("fresh waiver-only player skipped", "200" not in ids)
    finally:
        STORE = _orig
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--selftest":
        selftest()
    if args[0] == "show":
        cmd_show(" ".join(a for a in args[1:] if not a.startswith("--")))
    elif args[0] == "import":
        if len(args) < 2:
            sys.exit("usage: python dossier.py import <bundle.json>")
        cmd_import(args[1])
    elif args[0] == "preflight":
        if len(args) < 2:
            sys.exit("usage: python dossier.py preflight <league>")
        cmd_preflight(args[1])
    elif args[0] == "refresh-list":
        n = int(args[args.index("--days") + 1]) if "--days" in args else 7
        lg = next((a for a in args[1:] if not a.startswith("--")
                   and not a.isdigit()), None)
        cmd_refresh_list(lg, n)
    elif args[0] == "stats":
        cmd_stats()
    elif args[0] == "stale":
        n = int(args[args.index("--days") + 1]) if "--days" in args else 10
        cmd_stale(n)
    else:
        sys.exit(__doc__)
