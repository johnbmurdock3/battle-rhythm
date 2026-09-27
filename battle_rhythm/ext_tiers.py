"""External tier boards — a second opinion the internal board cannot give.

`tier_up()` derives tiers from THIS league's VORP curve, which is the right
unit for pricing but says nothing about what the room believes. An outside
consensus board says where other drafters see the cliffs, and Boris Chen's
carries best/worst/avg/sd of expert rank -- an empirical spread the toolkit
has no equivalent for.

Measured 9/6 against the completed LG02 draft: RotoWire RB tier order
predicted draft-position drift monotonically (tier 1 went on time, tier 7
went 40 picks early), which ADP alone did not show.

READ THE sd COLUMN WITH CARE. A large sd has two causes that point opposite
ways:

  1. stale ranker files colliding with a dated availability event -- the
     spread is measurement error, and the optimistic end is a file that
     predates the news. Josh Jacobs sat at rank 155 with a best rank of 37
     a week AFTER going on the Commissioner's Exempt List.
  2. genuine role or durability ambiguity, outcome undetermined -- the
     spread is real optionality, and the optimistic end is a live outcome.
     MarShawn Lloyd, rank 88, best 52, inheriting a backfield.

Only case 2 is a buy. The discriminator is whether a dated status event
exists, which is what dossiers/ holds -- so an sd column is trustworthy
only after it is joined against current status. Do not skip that join.

Files: data/tiers/<source>_<YYYY-MM-DD>_<tag>.tsv, tab-separated, with a
header. Required columns: player, tier. Optional: rank, pos, sd.
"""
import bisect
import csv
import pathlib
import re
from battle_rhythm import paths as _paths

DIR = _paths.DATA / "tiers"

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")

TEAM_ABBR = {
    "arizona cardinals": "ARI", "atlanta falcons": "ATL", "baltimore ravens": "BAL",
    "buffalo bills": "BUF", "carolina panthers": "CAR", "chicago bears": "CHI",
    "cincinnati bengals": "CIN", "cleveland browns": "CLE", "dallas cowboys": "DAL",
    "denver broncos": "DEN", "detroit lions": "DET", "green bay packers": "GB",
    "houston texans": "HOU", "indianapolis colts": "IND", "jacksonville jaguars": "JAX",
    "kansas city chiefs": "KC", "las vegas raiders": "LV", "los angeles chargers": "LAC",
    "los angeles rams": "LAR", "miami dolphins": "MIA", "minnesota vikings": "MIN",
    "new england patriots": "NE", "new orleans saints": "NO", "new york giants": "NYG",
    "new york jets": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT",
    "san francisco 49ers": "SF", "seattle seahawks": "SEA", "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN", "washington commanders": "WAS",
}


def norm(name):
    """Match key. Suffixes are the whole problem: the same player is
    'James Cook III' on one board and 'James Cook' on another, and a join
    that misses him silently drops the third-best back off the sheet."""
    # periods are DELETED, not spaced: "D.K. Metcalf" is "dk metcalf" on
    # one board and "DK Metcalf" on another. Spacing them splits the name.
    # Board rows carry a DECORATED name -- name_of() returns
    # "Saquon Barkley (RB, PHI)" -- and keying that gave
    # "saquon barkley rb phi", which matched nothing, for every row, with no
    # error. Strip a trailing parenthetical so a decorated name and a bare
    # one land on the same key whichever caller supplies it.
    s = re.sub(r"\s*\(.*$", "", str(name or ""))
    s = s.lower().replace(".", "").replace("'", "")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _key(name, pos=None):
    """Defenses arrive as a full name on a ranking board ("Houston Texans")
    and as an abbreviation on Sleeper's ("HOU"). Both have to land on the
    same key, uppercased -- lowercasing one side silently drops every
    defense off the join, which is how this first shipped."""
    n = norm(name)
    if pos == "DEF" or n in TEAM_ABBR:
        return TEAM_ABBR.get(n, n.upper())
    return n


def load(source=None):
    """{match key: row} across every OVERALL board in data/tiers/.

    A file must carry a `rank` column to be loaded, and that is a
    correctness guard, not a formality. Two shapes of tier board exist and
    they are not interchangeable:

      overall     one list, every position, rank 1..200 -- comparable to a
                  pick number, which is what mkt() and survives() need
      per-position  RB tier 3, WR tier 3 -- same label, unrelated meaning

    data/tiers/ currently holds both. The RotoWire files are per-position
    and were being skipped only because they happen to be .txt against a
    .tsv glob. That is luck, not design: rename one to .tsv and its RB
    tier 3 would silently overwrite an overall tier 3, and every ECR on the
    board would be wrong with no error anywhere. Requiring `rank` makes the
    exclusion explicit and survives the rename.
    """
    out = {}
    if not DIR.is_dir():
        return out
    for f in sorted(DIR.glob("*.tsv")):
        if source and not f.name.startswith(source):
            continue
        with f.open(encoding="utf-8") as fh:
            rdr = csv.DictReader(fh, delimiter="\t")
            if "rank" not in (rdr.fieldnames or []):
                continue                    # per-position board; not comparable
            for r in rdr:
                if not r.get("player") or not r.get("tier") or not r.get("rank"):
                    continue
                pos = (r.get("pos") or "").upper()
                if pos in ("DST", "D/ST"):
                    pos = "DEF"
                try:
                    rec = {"tier": int(r["tier"]),
                           "rank": int(r["rank"]) if r.get("rank") else None,
                           "sd": float(r["sd"]) if r.get("sd") else None,
                           "pos": pos or None, "src": f.name}
                except ValueError:
                    continue
                out[_key(r["player"], pos)] = rec
    return out


SD_WINDOW = 25          # ranks either side, for the local norm
SD_FLAG = 1.8           # multiples of it that count as "the panel is split"


def market_pos(p, default=None):
    """Where the room is expected to take this player.

    ONE DEFINITION, because two tools asking the same question and answering
    differently is how `br.py board` told John that Saquon Barkley was
    "priced to wait" at ADP 36 on the morning `br.py live` had him at 0% --
    consensus rank 13, and he went 8th in the LG02 room. Both numbers
    were computed correctly. Only one was right, and a draft clock is not
    when to work out which.

    Measured on the completed LG02 draft, 101 players ranked by both:
    residual sd of log(actual/estimate) is 0.431 against this feed's ADP and
    0.284 against consensus rank, so consensus is the better answer for
    skill positions.

    DEF and K keep ADP: defenses are the tightest thing in that table
    against ADP (0.063) and get worse under consensus (0.157, -0.324 shift),
    because a skill-heavy board ranks them later than rooms take them.

    `default` is what an unknown resolves to, and callers disagree on it by
    design: draft_live wants 999 (never survives), draft_helper wants None
    (falsy, "unknown ADP = won't survive" in its own predicates).
    """
    pos = p.get("pos") or (p.get("meta") or {}).get("position")
    if pos in ("DEF", "K"):
        return p.get("adp") or default
    r = p.get("bc_rank")
    if r:
        return float(r)
    return p.get("adp") or default


def annotate(rows, table=None):
    """Add bc_tier / bc_rank / bc_sd / bc_sd_rel to board rows in place.
    Returns (matched, total) so a bad join is visible instead of silently
    empty.

    bc_sd_rel is the one to read. RAW sd IS USELESS AS A FLAG because it
    scales with rank -- a player ranked 180 has room to vary that a player
    ranked 8 does not:

        rank   1-50   median sd  6.3
        rank  51-100  median sd 12.8
        rank 101-150  median sd 18.1
        rank 151-200  median sd 29.3

    A flat cutoff at sd>=25 therefore highlighted 42 of 197 players -- most
    of the tail, and nothing at the top. Dividing by rank fails the other
    way: at rank 1 an sd of 1 is 100% of rank, so it lights up the entire
    first round.

    So compare each player to the MEDIAN SD OF HIS RANK NEIGHBOURHOOD. No
    functional form to get wrong, and it degrades gracefully at both ends.
    On LG04's board 1.8x flags four players out of 197.
    """
    t = load() if table is None else table
    hit = 0
    for p in rows:
        rec = t.get(_key(p.get("name"), p.get("pos")))
        if rec:
            hit += 1
            p["bc_tier"], p["bc_rank"], p["bc_sd"] = rec["tier"], rec["rank"], rec["sd"]
        else:
            p.setdefault("bc_tier", None)
            p.setdefault("bc_rank", None)
            p.setdefault("bc_sd", None)
        p.setdefault("bc_sd_rel", None)

    known = sorted((p for p in rows if p.get("bc_sd") is not None
                    and p.get("bc_rank")), key=lambda p: p["bc_rank"])
    sds = [p["bc_sd"] for p in known]
    ranks = [p["bc_rank"] for p in known]
    for p in known:
        lo = bisect.bisect_left(ranks, p["bc_rank"] - SD_WINDOW)
        hi = bisect.bisect_right(ranks, p["bc_rank"] + SD_WINDOW)
        near = sorted(sds[lo:hi])
        if not near:
            continue
        med = near[len(near) // 2] if len(near) % 2 else (
            (near[len(near) // 2 - 1] + near[len(near) // 2]) / 2.0)
        p["bc_sd_rel"] = round(p["bc_sd"] / med, 2) if med else None
    return hit, len(rows)


def selftest():
    ok = True

    def ck(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  {'ok ' if cond else 'FAIL'} {label}")

    ck("suffixes collapse", norm("James Cook III") == norm("James Cook")
       == norm("James Cook Jr.") == "james cook")
    ck("Mahomes II", norm("Patrick Mahomes II") == "patrick mahomes")
    ck("apostrophes", norm("Ja'Marr Chase") == "jamarr chase")
    ck("periods", norm("D.K. Metcalf") == "dk metcalf")
    ck("a decorated board name keys the same as a bare one",
       norm("Saquon Barkley (RB, PHI)") == norm("Saquon Barkley")
       == "saquon barkley")
    ck("a real surname containing a suffix token is untouched",
       norm("Vic Beasley") == "vic beasley")
    ck("team name -> abbrev", _key("Houston Texans", "DEF") == "HOU")
    ck("board abbrev and board full name meet on one key",
       _key("HOU", "DEF") == _key("Houston Texans", "DEF") == "HOU")
    t = load()
    ck(f"loaded a board ({len(t)} players)", len(t) > 100)
    ck("every loaded player carries an overall rank",
       all(v.get("rank") for v in t.values()))
    rows = [{"name": "James Cook", "pos": "RB"},
            {"name": "Houston Texans", "pos": "DEF"},
            {"name": "Nobody At All", "pos": "WR"}]
    hit, tot = annotate(rows, t)
    ck("known player annotated", rows[0]["bc_tier"] is not None)
    ck("defense annotated", rows[1]["bc_tier"] is not None)
    ck("unknown player gets nulls, not a crash", rows[2]["bc_tier"] is None)
    ck("match count reported", (hit, tot) == (2, 3))
    # sd must be judged against its rank neighbourhood, not a flat cutoff
    synth = [{"name": f"P{i}", "pos": "RB", "bc_rank": i, "bc_sd": i * 0.17}
             for i in range(1, 201)]
    synth[159]["bc_sd"] = 160 * 0.17 * 3      # rank 160, triple the local norm
    for q in synth:
        q["bc_tier"] = 1
    annotate(synth, {})
    for q in synth:
        q["bc_sd_rel"] = None
    tbl = {_key(q["name"], "RB"): {"tier": 1, "rank": q["bc_rank"],
                                   "sd": q["bc_sd"], "pos": "RB", "src": "x"}
           for q in synth}
    annotate(synth, tbl)
    outlier = synth[159]
    ck("a locally extreme sd is flagged", outlier["bc_sd_rel"] > 2.5)
    ck("an ordinary tail sd is not",
       all(abs(q["bc_sd_rel"] - 1.0) < 0.25 for q in synth[50:150]))
    ck("rank 1 is not flagged just for being rank 1",
       synth[0]["bc_sd_rel"] < 1.8)
    print("\nselftest", "PASSED" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    t = load()
    print(f"{len(t)} players across data/tiers/")
    for k, v in list(t.items())[:5]:
        print(" ", k, v)
