"""
paths.py — the only file that knows where things go.

Files are sorted by how hard they are to get back, not by topic:

    SOURCE   the .py files. They are the program.
    TRUTH    data/ (authored), data/measured/ (measured off real drafts),
             dossiers/ (447 accumulated research records), fixtures/.
             Rebuilding any of these costs a research pass, a season, or
             is impossible. All tracked in git.
    RENDER   out/. One command, under a minute, deterministic. Gitignored.

The test for the line between TRUTH and RENDER: can you rebuild it with
one command in under a minute? dashboard.html can. dossiers/ cannot.

roster.md deliberately stays at the repo root and stays tracked. CLAUDE.md
carries a standing rule to regenerate and read it before any pick
recommendation; if the writer moved and a reader did not, the failure
would be a silently stale roster, which is the 8/11 failure that cost
three consecutive picks. It moves after the 8/18 draft, together with the
rule text.

Read-side resolvers fall back to the repo root so a half-finished move
never breaks a read. Write-side always targets the new location.

Nothing here imports a project module, and nothing here touches the
network. Every other module imports this one — keep it that way.

    python paths.py --selftest
"""

import json
import os
import pathlib
import re
import unicodedata

# paths.py lives INSIDE battle_rhythm/, so the repo is one level up.
# This is the single most dangerous line in the package move: get it
# wrong and out() cheerfully creates a second out/ inside the package
# and writes there, with nothing raising. selftest() asserts the
# location rather than trusting the arithmetic.
PKG = pathlib.Path(__file__).resolve().parent
REPO = PKG.parent

DATA = REPO / "data"
MEASURED = DATA / "measured"
LEAGUES = REPO / "leagues"
DOSSIERS = REPO / "dossiers"
FIXTURES = REPO / "fixtures"
ARCHIVE = REPO / "archive"
DOCS = REPO / "docs"
REPORTS = REPO / "reports"

# SLEEPER_OUT lets you send a whole run somewhere else without touching
# code — useful for a throwaway comparison you do not want in the repo.
OUT = pathlib.Path(os.environ.get("SLEEPER_OUT") or (REPO / "out"))

INDEX = LEAGUES / "_index.json"


# ----------------------------------------------------------------- truth

def config():
    """config.json — the Sleeper username. Repo ROOT, not data/, because
    it is per-install and not authored truth; keepers/ages/byes/fonts are.
    Here so sleeper_client stops resolving it as a sibling of its own
    source, which stops being true the moment the code is packaged."""
    return REPO / "config.json"


def data(name):
    """Authored truth: keepers.json, ages.json, byes.json, fonts.json,
    config.json. Prefers data/, falls back to the repo root.

    THE FALLBACK IS A TRAP, AND IT SPRANG ON 8/13. Both copies of
    keepers.json existed. data/ won silently while a whole session's
    edits — a corrected taxi rule and the registration of the entire IDP
    league — went into the root copy, which nothing reads. Two runs of
    roster_snapshot then printed the superseded rules with no sign that
    anything was wrong. A shadowed file is a decoy; say so out loud
    rather than resolving it quietly."""
    p = DATA / name
    if p.exists():
        shadow = REPO / name
        try:
            dead = shadow.exists() and shadow.resolve() != p.resolve()
        except OSError:
            dead = False
        if dead:
            import sys
            print(f"  WARNING: {name} exists in BOTH data/ and the repo "
                  f"root. data/ wins — the root copy is DEAD and edits to "
                  f"it do nothing. Delete {shadow}", file=sys.stderr)
        return p
    return REPO / name


def measured(name):
    """Measured truth — expensive or time-bound to reproduce. room_bias.json
    was taken against a completed 2025 draft; it is not a render."""
    p = MEASURED / name
    if p.exists():
        return p
    legacy = REPO / name
    if legacy.exists():
        return legacy
    MEASURED.mkdir(parents=True, exist_ok=True)
    return p


def ledger(name):
    """data/ledger/<name> — the in-season recommendation ledger, TRACKED.

    Truth by the CLAUDE.md test: a recommendation made in week 3 with the
    week-3 projection behind it cannot be rebuilt once week 3 has played.
    It is the 9/4 eval's fact table (computed advice vs actual result,
    per league, per week), so it sits beside measured/ rather than in
    out/. See battle_rhythm/ledger.py."""
    d = DATA / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def truth(*parts):
    """data/truth/<season>/wkNN/<stamp>/... -- snapshots of what Sleeper
    itself scored, TRACKED.

    Truth by the CLAUDE.md test: a week's stats get corrected after the
    fact, so the as-of-Tuesday state of stats + matchups cannot be
    fetched again once Sleeper rewrites it. The engine check
    (battle_rhythm/truth.py) compares against these, never against a
    live call, so a rerun on any machine gives the same answer."""
    p = (DATA / "truth").joinpath(*[str(x) for x in parts])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fixture(name):
    return FIXTURES / name


# ---------------------------------------------------------------- render

def out(*parts):
    """A path under out/, with parent directories created. Everything here
    is disposable and gitignored."""
    p = OUT.joinpath(*[str(x) for x in parts])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def league_out(league_id, filename):
    """out/<slug>/<filename>. Keyed by league id, never by name — both
    Hybrids normalize to the same string and would collide."""
    return out(slug_for(league_id), filename)


def report(name):
    """reports/<name> — a dated research diff, TRACKED in git.

    Not out/ and not the repo root, and both halves of that matter.

    out/ is renders: one command, under a minute, deterministic,
    gitignored, and never an input to a decision. A weekly refresh is
    none of those — it costs a 200-300 player research pass, cannot be
    rebuilt at any price once the week has passed, and its whole purpose
    is to change a lineup or waiver decision. By the Truth/Render test in
    CLAUDE.md it is Truth, so it is tracked.

    The repo root is worse: roster.md is the ONE file allowed there, and
    smoke.py's last check snapshots the root and fails if anything else
    appears. A weekly writer aimed at the root would have broken smoke
    every Tuesday."""
    REPORTS.mkdir(parents=True, exist_ok=True)
    return REPORTS / name


# ---------------------------------------------------------------- leagues

_INDEX_CACHE = {}


def index():
    """leagues/_index.json, parsed. {} if it is missing."""
    if "d" not in _INDEX_CACHE:
        try:
            _INDEX_CACHE["d"] = json.loads(INDEX.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _INDEX_CACHE["d"] = {}
    return _INDEX_CACHE["d"]


def leagues():
    return (index().get("leagues") or {})


def ignored_ids():
    """League ids registered with "ignore": true — known to the index so
    smoke does not report them as NEW, but skipped by every in-season
    view. First member: the 🪓 LG08 (9/12)."""
    return {str(m.get("id")) for m in leagues().values() if m.get("ignore")}


def slug_for(league_id):
    """Canonical folder slug for a league id. Unknown ids get a stable
    fallback rather than an exception — a render should never be the thing
    that fails a draft-day command."""
    lid = str(league_id or "").strip()
    for s, meta in leagues().items():
        if str(meta.get("id")) == lid:
            return s
    return f"league-{lid}" if lid else "unknown-league"


def id_for(slug_or_alias):
    """Resolve a slug or alias to a league id, or None."""
    q = _norm(slug_or_alias)
    for s, meta in leagues().items():
        if q == _norm(s) or q in [_norm(a) for a in (meta.get("aliases") or [])]:
            return str(meta.get("id"))
    return None


def league_dir(league_id):
    """leagues/<slug>/ — authored per-league material: the draft brief,
    notes, anything hand-written. Not created here; the sweep makes it."""
    return LEAGUES / slug_for(league_id)


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if c.isalnum() or c.isspace() or c == "-")
    return re.sub(r"[\s-]+", " ", s).strip().casefold()


# ------------------------------------------------------------ guardrails

# Files that MUST live in data/. config.json is deliberately not here --
# sleeper_client's docstring tells you to put it next to the scripts.
AUTHORED = ("keepers.json", "ages.json", "byes.json", "fonts.json")

# Scripts that legitimately contain path literals as DATA rather than as
# code: they are migration/repair tools whose edit strings quote the very
# lines this lint is looking for.
# migrate.py, dedupe_shape.py and fix_writers.py were archived 9/2;
# they are no longer globbed and no longer need skipping.
_LINT_SKIP = {"paths.py"}

_CWD_WRITE = re.compile(
    r"""(?:pathlib\.)?Path\(\s*f?["'](?![/\\])(?![A-Za-z]:)""")


def shadowed():
    """Authored files that exist in BOTH data/ and the repo root.

    data() prefers data/, so a root copy is dead weight that silently
    absorbs edits. On 8/13 a whole session's work -- a corrected taxi rule
    and the IDP league's registration -- went into a shadowed keepers.json
    and two roster_snapshot runs printed the superseded rules without a
    murmur. The runtime warning in data() is the seatbelt; this is the
    check that stops you needing it.
    """
    out = []
    for name in AUTHORED:
        a, b = DATA / name, REPO / name
        if a.exists() and b.exists():
            out.append(name)
    return out


_DRAFT_PICKS = re.compile(r"""draft/\{[^}]*\}/picks""")


def draft_id_reads():
    """Source lines that fetch a draft's picks without resolving the draft.

    league.draft_id names ONE draft and a league season can hold several.
    keeper.py learned that in August and wrote it down; the knowledge never
    left the file. On 9/2 the cost came due everywhere at once --
    LG03's draft_id pointed at a draft marked COMPLETE
    with zero picks while 120 real picks sat under another id, so board
    offered a next pick on a finished draft and keeper reported ten picks
    left. Five modules were doing it. `recap` shipped the same morning with
    the same bug, written after the shared path had already been fixed.

    Fixing five call sites does not stop a sixth. draft_helper.resolve_draft
    is the one implementation; everything else goes through it. Put
    `# draft-id-ok` on a line to exempt it, and say why.

    Returns [(filename, lineno, text)].
    """
    ok = {"draft_helper.py"}          # owns resolve_draft
    hits = []
    for f in sorted(PKG.glob("*.py")):
        if f.name in ok:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            st = line.strip()
            if st.startswith("#") or "draft-id-ok" in line:
                continue
            if _DRAFT_PICKS.search(line):
                hits.append((f.name, i, st[:88]))
    return hits


def cwd_writes():
    """Source lines that build a path relative to the current directory.

    A writer with no anchor lands wherever the shell happened to be
    standing. Three of them did before 8/13; research_queue_lg05.json
    sat in the repo root purely because that is where it was run. One of
    the three came BACK on 8/13 when draft_helper's sheet function was
    rewritten -- the convention was in a comment and the comment did not
    hold, exactly as lineup_value:1484 says about comments and traps.

    Returns [(filename, lineno, text)]. Put `# cwd-ok` on a line to
    exempt it deliberately.
    """
    hits = []
    # Was REPO.glob("*.py"). After the package move that is three
    # entry points and the lint would have passed by seeing almost
    # nothing -- "a vacuous check cleared a real bug" (HANDOFF 8/13).
    # selftest() asserts the file count so it cannot go quiet again.
    for f in sorted([*PKG.rglob("*.py"), *REPO.glob("*.py")]):
        if f.name in _LINT_SKIP:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            st = line.strip()
            if st.startswith("#") or "cwd-ok" in line:
                continue
            if "__file__" in line or "_paths." in line or "paths." in line:
                continue
            if _CWD_WRITE.search(line):
                hits.append((f.name, i, st[:88]))
    return hits


# --------------------------------------------------------------- selftest

def selftest():
    """Also checks that leagues/_index.json and mcp_server.LEAGUE_IDS agree.

    They disagreed on 8/13 — mcp_server carried lg02 and keepers.json
    had never heard of it. Two sources of league identity that drift in
    silence is how a tool ends up confidently pointing at the wrong league.
    """
    checks = []

    def ck(name, cond):
        checks.append((name, bool(cond)))

    # REPO used to be this file's own directory. After the 9/2 package
    # move it is one level up, and the failure mode if that is wrong is
    # silent: out() would create a second out/ inside the package.
    # Assert the landmarks that only the real repo root has.
    ck("REPO is the repo root, not the package",
       (REPO / "battle_rhythm" / "paths.py").exists()
       and DATA.is_dir() and INDEX.exists()
       and REPO.name != "battle_rhythm")
    ck("the cwd lint still sees the toolkit",
       len(list(PKG.glob("*.py"))) >= 20)
    ck("data() falls back to root when data/ is empty",
       data("__nope__.json") == REPO / "__nope__.json")
    ck("out() creates its parent", out("_selftest", "x.txt").parent.is_dir())
    ck("report() lands in tracked reports/, not out/ and not the root",
       report("_x.md").parent == REPORTS and REPORTS.parent == REPO
       and REPORTS.is_dir() and OUT not in report("_x.md").parents)

    lg = leagues()
    ck("_index.json parses and is non-empty", bool(lg))
    ck("every league has an id", all(str(m.get("id") or "").isdigit()
                                     for m in lg.values()))
    ids = [str(m.get("id")) for m in lg.values()]
    ck("league ids are unique", len(ids) == len(set(ids)))
    ck("slug_for round-trips", all(slug_for(m["id"]) == s
                                   for s, m in lg.items()))
    ck("unknown id gets a stable fallback",
       slug_for("999") == "league-999")
    ck("id_for resolves an alias",
       id_for("lg02") == id_for("lg02") is not None
       if id_for("lg02") else True)

    sh = shadowed()
    ck(f"no authored file is shadowed at the repo root"
       + (f" (SHADOWED: {', '.join(sh)})" if sh else ""), not sh)

    dr = draft_id_reads()
    ck("no module reads a draft's picks without resolving the draft"
       + (f" ({'; '.join(f'{a}:{b}' for a, b, _ in dr)})" if dr else ""),
       not dr)

    cw = cwd_writes()
    ck("no writer builds a path relative to the current directory"
       + (f" ({len(cw)} found)" if cw else ""), not cw)
    for fn, ln, txt in cw:
        print(f"      {fn}:{ln}  {txt}")

    # cross-source agreement
    # WAS: a drift check between _index.json and a hand-typed
    # mcp_server.LEAGUE_IDS. That is two copies maintained by hand, and
    # comparing two stale copies is not a check -- it is how LG07
    # stayed invisible for weeks while both files agreed with each other.
    # As of 9/2 mcp_server derives its ids from this file, so drift is
    # not possible and asking about it would be vacuous. Check the things
    # that CAN still be wrong instead.
    seen = {}
    dupe = None
    for slug, m in lg.items():
        for a in [slug, *(m.get("aliases") or [])]:
            k = _norm(a)
            if k in seen and seen[k] != str(m["id"]):
                dupe = a
            seen[k] = str(m["id"])
    ck(f"no alias points at two leagues"
       + (f" (AMBIGUOUS: {dupe})" if dupe else ""), dupe is None)
    ck("every league has a folder",
       all((LEAGUES / s_).is_dir() for s_ in lg))
    try:
        import mcp_server
        ck("mcp_server sees every league in the index",
           set(mcp_server.LEAGUE_IDS.values()) == {str(m["id"])
                                                   for m in lg.values()})
    except Exception as e:
        ck(f"mcp_server importable ({type(e).__name__})", False)
    try:
        kp = json.loads(data("keepers.json").read_text(encoding="utf-8"))
        known = {k for k in kp if not k.startswith("_")}
        ck("every keepers.json id is in _index.json", not (known - set(ids)))
    except Exception as e:
        ck(f"keepers.json readable ({type(e).__name__})", False)

    for name, cond in checks:
        print(f"  {'ok' if cond else 'XX'}  {name}")
    ok = all(c for _, c in checks)
    print(f"\nselftest {'PASSED' if ok else 'FAILED'}  "
          f"({sum(1 for _, c in checks if c)}/{len(checks)})")
    return ok


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(f"REPO      {REPO}")
    print(f"DATA      {DATA}")
    print(f"MEASURED  {MEASURED}")
    print(f"DOSSIERS  {DOSSIERS}")
    print(f"LEAGUES   {LEAGUES}")
    print(f"OUT       {OUT}")
    for s, m in leagues().items():
        print(f"  {s:16s} {m.get('id'):22s} {m.get('name')}")
