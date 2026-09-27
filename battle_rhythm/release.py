"""
release.py -- the gate between this private repo and a public one.

    python br.py release scan-key            # is the Sleeper push key anywhere in git history?
    python br.py release leagues [--fetch]   # propose surrogate keys (LG01...) for every league
    python br.py release managers --fetch    # every manager in every league, from Sleeper -> MGR01...
    python br.py release inventory           # what a public copy would expose, and what is undecided
    python br.py release export <dest>       # a scrubbed copy of HEAD, ready to push publicly
    python br.py release verify <dest>       # prove nothing private survived the scrub
    python br.py release update <clone>      # refresh the public clone in place; stages, never commits
    python br.py release --selftest          # offline, builds its own throwaway git repo

--fetch needs the network, so it runs on the PC like `truth fetch`.

WHY. The 9/4 plan put the repo public at the end of week one, gated on two
things: scan the WHOLE git history for the push key, and decide what to do
with league ids and friends' team and roster data. John, 9/26: his private
leagues must not be published, his friends' names must be safeguarded, and
he wants a surrogate key he can cite in public ("LG05 pays return yards").
A public repo is every commit, not just HEAD, so the public repo is never
this repo made public. It is a fresh repo built from `export`, one commit,
after `scan-key` comes back clean.

SURROGATE KEYS. Each league gets LGnn, numbered by league id (so creation
order), and its past seasons share the key. Each manager gets MGRnn,
numbered by Sleeper user id, and his team names become "Team MGRnn". The
keys are stable: re-running `leagues` or `managers` keeps every existing
key and only appends new ones, so a key cited in a write-up keeps meaning
the same league. The mapping lives in data/release/ (tracked, private) and
data/release/ is NEVER exported -- it is the one folder that would undo
the scrub.

WHAT EXPORT CHANGES:
  - every 17-20 digit Sleeper id (leagues, users, drafts, transactions)
    becomes a fake id starting 9000..., ORDER-PRESERVING (code compares
    ids: a newer draft has a larger id). Same real id -> same fake id in
    every file and filename, so _index.json, tests and snapshots stay
    consistent and the suite still passes on the copy.
  - every league name, former name, slug and identifying alias becomes
    its key: "The Oakwood Senate" and "Oakwood" -> "LG05", the slug
    "oakwood" -> "lg05", in text, filenames AND folder names
    (leagues/oakwood/ -> leagues/lg05/). Generic format words (dynasty,
    hybrid, idp, best ball...) are left alone; they describe a format, not
    a league. A string two leagues share (one league's former name that is
    another's current name) becomes both keys, "LG03-LG04".
  - every manager display name and username becomes MGRnn, team names
    "Team MGRnn". Names that are also ordinary words ("Will") are
    replaced only in their exact capitalisation, and inventory flags them.
  - names in data/release/redact.json "names" (friends' real names that
    only appear in prose) become "Person NN". "keep" names stay.
  - only TRACKED files at HEAD are exported (git archive): out/, caches and
    anything gitignored never leave. data/release/ is dropped.
  - the real-id map is written to out/release/ in THIS repo (gitignored),
    never into the export.
Binary files (.gz, images) are copied as-is and listed.

THE PUSH KEY IS NEVER TYPED INTO CHAT, A FILE, OR AN ARGUMENT. scan-key
reads it with getpass, holds it in memory for one scan, and prints only
WHERE it was found, never the value. (CLAUDE.md: never ask for it, never
store it.)
"""

import getpass
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter, defaultdict

from battle_rhythm import paths

# not part of a longer number and not a decimal: "league_<id>.json" must match,
# "0.1234567890123456789" must not
ID_RE = re.compile(r"(?<!\d)(?<!\d\.)\d{17,20}(?!\d)(?!\.\d)")
FAKE_BASE = 9000000000000000027
NAME_FIELDS = ("display_name", "username", "team_name", "owner_name", "manager")
BINARY_EXT = {".gz", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2",
              ".ttf", ".parquet", ".zip", ".tgz", ".xlsx", ".pyc"}
PRIVATE_DIR = "data/release"            # never exported
# format words, not league identity -- left alone in the public copy
GENERIC_ALIASES = {"dynasty", "hybrid", "idp", "bb", "best ball", "bestball", "best-ball",
                   "hero", "superhero", "hybrid_hero", "keeper", "redraft", "superflex"}
# a manager name that is also an everyday word is replaced case-sensitively only
COMMON_WORDS = {"will", "mike", "bill", "rob", "mark", "pat", "art", "sue", "max", "jack",
                "chase", "hunter", "grant", "frank", "king", "ace", "boss", "champ", "coach",
                "the", "and", "man", "guy", "team", "bro", "bros", "dude", "big", "lil"}


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True)


def _repo():
    return paths.REPO


def _release_dir(root=None):
    return pathlib.Path(root or _repo()) / PRIVATE_DIR


def _load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------- scan-key

def scan_history(key, repo=None):
    """Every place `key` appears: all commits on all refs (added OR removed
    lines), stashes, and the working tree including untracked files.
    Returns [(where, path, line_no_or_None)]. Never returns the key."""
    repo = pathlib.Path(repo or _repo())
    if not key or len(key) < 6:
        raise ValueError("refusing to scan for an empty or very short string")
    hits = []
    needles = {key, key.lower(), key.upper()}

    proc = subprocess.Popen(["git", "log", "-p", "--all", "--no-color", "--format=commit %H"],
                            cwd=str(repo), stdout=subprocess.PIPE)
    commit, path = None, None
    for raw in io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace"):
        if raw.startswith("commit "):
            commit = raw.split()[1][:12]
            continue
        if raw.startswith("diff --git"):
            path = None
        if raw.startswith("+++ b/"):
            path = raw[6:].rstrip("\n")
            continue
        if raw.startswith("--- a/") and path is None:
            path = raw[6:].rstrip("\n")
        if any(n in raw for n in needles):
            hits.append((f"history {commit}", path or "?", None))
    proc.wait()

    st = _git(["stash", "list", "--format=%H"], repo)
    for h in st.stdout.decode().split():
        show = _git(["stash", "show", "-p", h], repo).stdout.decode("utf-8", "replace")
        if any(n in show for n in needles):
            hits.append((f"stash {h[:12]}", "?", None))

    ls = _git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], repo)
    for rel in [p for p in ls.stdout.decode("utf-8", "replace").split("\0") if p]:
        f = repo / rel
        if not f.is_file() or f.suffix.lower() in BINARY_EXT:
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if any(n in line for n in needles):
                    hits.append(("working tree", rel, i))
        except OSError:
            continue
    seen, out = set(), []
    for h in hits:
        k = (h[0], h[1]) if h[2] is None else h
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def cmd_scan_key():
    print("Paste the Sleeper push key and press Enter. It is not echoed, not")
    print("saved, and not printed -- only the places it appears are reported.")
    key = getpass.getpass("push key: ").strip()
    try:
        hits = scan_history(key)
    finally:
        key = None
    n = len(_git(["rev-list", "--all"], _repo()).stdout.split())
    if not hits:
        print(f"\nCLEAN: not found in {n} commits, any stash, or the working tree.")
        return 0
    print(f"\nFOUND in {len(hits)} place(s) across {n} commits:")
    for where, rel, line in hits:
        print(f"  {where:<22} {rel}" + (f":{line}" if line else ""))
    print("\nThis repo must not go public as-is. The public copy is built with")
    print("`release export`, which starts a fresh history -- but ROTATE THE KEY in")
    print("Sleeper anyway: it has been in a git object, and objects get copied.")
    return 1


# ------------------------------------------------------- surrogate: leagues

def _truth_league_docs(root=None):
    """(league_id, name, season) from every truth snapshot league file."""
    base = pathlib.Path(root or _repo()) / "data" / "truth"
    out = set()
    if base.is_dir():
        for f in base.rglob("league_*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            out.add((str(d.get("league_id") or f.stem[7:]), (d.get("name") or "").strip(),
                     str(d.get("season") or "")))
    return out


def propose_leagues(index_leagues, truth_docs=(), chains=None, existing=None):
    """Merge a surrogate map. Existing keys are never renumbered.

    index_leagues  {slug: {id, name, aliases, former_names}} from _index.json
    truth_docs     {(league_id, name, season)} from snapshots
    chains         {current_id: [(past_id, past_name), ...]} from --fetch
    existing       the current data/release/leagues.json, or None
    """
    ex = existing or {"leagues": []}
    by_id = {}
    entries = []
    for e in ex.get("leagues", []):
        e = dict(e, ids=list(e.get("ids", [])), replace=list(e.get("replace", [])))
        entries.append(e)
        for i in e["ids"]:
            by_id[i] = e

    def entry_for(lid):
        if lid in by_id:
            return by_id[lid]
        n = max([int(e["key"][2:]) for e in entries] + [0]) + 1
        e = {"key": f"LG{n:02d}", "ids": [lid], "replace": [], "format": ""}
        entries.append(e)
        by_id[lid] = e
        return e

    def add(e, s):
        s = (s or "").strip()
        if s and s.lower() not in GENERIC_ALIASES and s not in e["replace"]:
            e["replace"].append(s)

    for slug, m in sorted(index_leagues.items(), key=lambda kv: int(kv[1]["id"])):
        e = entry_for(str(m["id"]))
        if not e.get("format"):
            e["format"] = f"{m.get('type') or 'league'}, {m.get('teams') or '?'} teams"
        for s in [m.get("name"), slug, *(m.get("aliases") or []), *(m.get("former_names") or [])]:
            add(e, s)
    for cur, past in (chains or {}).items():
        e = entry_for(str(cur))
        for pid, pname in past:
            if pid not in e["ids"]:
                e["ids"].append(pid)
            by_id[pid] = e
            add(e, pname)
    for lid, name, _season in sorted(truth_docs):
        add(entry_for(lid), name)
    entries.sort(key=lambda e: e["key"])
    return {"_note": "Surrogate keys for the public copy. Keys never renumber. 'replace' lists "
                     "every string that identifies the league; each becomes the key (or the "
                     "lowercase key where the match is lowercase, e.g. a slug). Edit freely; "
                     "add strings, drop any that are not identifying.",
            "leagues": entries}


def fetch_chains(index_leagues, get):
    """{current_id: [(past_id, past_name)]}, walking previous_league_id."""
    out = {}
    for m in index_leagues.values():
        cur = str(m["id"])
        past, seen = [], {cur}
        lg = get(f"league/{cur}") or {}
        prev = str(lg.get("previous_league_id") or "")
        while prev.isdigit() and prev != "0" and prev not in seen:
            seen.add(prev)
            p = get(f"league/{prev}") or {}
            past.append((prev, (p.get("name") or "").strip()))
            prev = str(p.get("previous_league_id") or "")
        out[cur] = past
    return out


def cmd_leagues(fetch=False):
    p = _release_dir() / "leagues.json"
    chains = None
    if fetch:
        from battle_rhythm.sleeper_client import get
        chains = fetch_chains(paths.leagues(), get)
    new = propose_leagues(paths.leagues(), _truth_league_docs(), chains, _load(p, None))
    _save(p, new)
    for e in new["leagues"]:
        print(f"  {e['key']}  {e.get('format', ''):<26} {len(e['ids'])} season id(s), "
              f"{len(e['replace'])} strings to replace")
    print(f"\n  -> {p}  (review it; it is private and never exported)")
    return 0


# ------------------------------------------------------ surrogate: managers

def propose_managers(users_by_league, existing=None, self_name=None):
    """users_by_league {league_id: [sleeper user objects]} -> merged map.
    One entry per user_id; keys stable; names and team names accumulate."""
    ex = existing or {"managers": []}
    entries = [dict(e, user_ids=list(e.get("user_ids", [])), names=list(e.get("names", [])),
                    teams=list(e.get("teams", []))) for e in ex.get("managers", [])]
    by_uid = {u: e for e in entries for u in e["user_ids"]}
    users = {}
    for lst in users_by_league.values():
        for u in lst or []:
            if u.get("user_id"):
                users.setdefault(str(u["user_id"]), []).append(u)
    for uid in sorted(users, key=int):
        e = by_uid.get(uid)
        if e is None:
            n = max([int(x["key"][3:]) for x in entries] + [0]) + 1
            e = {"key": f"MGR{n:02d}", "user_ids": [uid], "names": [], "teams": [], "self": False}
            entries.append(e)
            by_uid[uid] = e
        for u in users[uid]:
            for nm in (u.get("display_name"), u.get("username")):
                nm = (nm or "").strip()
                if nm and nm not in e["names"]:
                    e["names"].append(nm)
            tn = ((u.get("metadata") or {}).get("team_name") or "").strip()
            if tn and tn not in e["teams"]:
                e["teams"].append(tn)
        if self_name and self_name.lower() in {n.lower() for n in e["names"]}:
            e["self"] = True
    entries.sort(key=lambda e: e["key"])
    return {"_note": "One entry per Sleeper user across every league and past season. names -> "
                     "key, teams -> 'Team <key>'. self:true is John; his names are kept only if "
                     "listed in redact.json 'keep'. Private, never exported.",
            "managers": entries}


def cmd_managers():
    from battle_rhythm.sleeper_client import get
    lg = _load(_release_dir() / "leagues.json", None)
    if not lg:
        raise SystemExit("run `release leagues --fetch` first -- managers are read per league id")
    ids = [i for e in lg["leagues"] for i in e["ids"]]
    users = {i: get(f"league/{i}/users") or [] for i in ids}
    me = (_load(paths.REPO / "config.json", {}) or {}).get("username")
    p = _release_dir() / "managers.json"
    new = propose_managers(users, _load(p, None), self_name=me)
    _save(p, new)
    print(f"  {len(new['managers'])} managers across {len(ids)} league-seasons -> {p}")
    for e in new["managers"]:
        flag = "  (you)" if e.get("self") else ""
        warn = [n for n in e["names"] if n.lower() in COMMON_WORDS or len(n) < 4]
        print(f"  {e['key']}  {len(e['names'])} name(s), {len(e['teams'])} team name(s){flag}"
              + (f"   REVIEW: common-word name(s) {warn}" if warn else ""))
    return 0


# ------------------------------------------------------------ replacement plan

# A private string is a match when it is not glued to a letter or digit on
# either side. Underscores and punctuation are breaks, so `queue_oakwood.json`
# and `OAKWOOD_2026` are caught; "degenerate" does not match "lg03". A
# literal escape (the two characters \\n or \\t) before the string also counts
# as a break: print("\\n\\nOAKWOOD PLAN") leaked through a \\w boundary on 9/26.
_PRE = r"(?:(?<![A-Za-z0-9])|(?<=\\n)|(?<=\\t))"
_POST = r"(?![A-Za-z0-9])"


def _bounded(text, flags=0):
    # any run of whitespace between words matches, so a name that wraps onto
    # the next line of a markdown file is still one name (ROADMAP.md, 9/26)
    body = r"\s+".join(re.escape(w) for w in text.split())
    return re.compile(_PRE + body + _POST, flags)


def load_plan(root=None):
    d = _release_dir(root)
    return (_load(d / "leagues.json", {"leagues": []}),
            _load(d / "managers.json", {"managers": []}),
            _load(d / "redact.json", {"names": [], "rename": {}, "keep": []}))


def build_rules(leagues, managers, redact):
    """[(regex, replacement fn, original)] longest original first."""
    keep = {k.lower() for k in (redact.get("keep") or [])}
    claims = defaultdict(list)
    for e in leagues.get("leagues", []):
        for s in e.get("replace", []):
            if e["key"] not in claims[s.lower()]:
                claims[s.lower()].append(e["key"])
    rules = []
    for low, keys in claims.items():
        # "-" not "/": the lowercase form must equal the key lowercased, or a
        # lookup that normalises names ("lg03-lg05" -> "lg03-lg05") stops
        # matching the league's name ("LG03/LG05") -- the 9/26 export test
        key = "-".join(sorted(keys))
        slug = "-".join(k.lower() for k in sorted(keys))
        rx = _bounded(low, re.IGNORECASE)
        rules.append((rx, (lambda m, k=key, s=slug: s if m.group().islower() else k), low))
    for e in managers.get("managers", []):
        for nm, rep in [(n, e["key"]) for n in e.get("names", [])] + \
                       [(t, f"Team {e['key']}") for t in e.get("teams", [])]:
            if nm.lower() in keep:            # John's handle, if he chose to keep it
                continue
            flags = 0 if (nm.lower() in COMMON_WORDS or len(nm) < 4) else re.IGNORECASE
            rx = _bounded(nm, flags)
            rules.append((rx, (lambda m, r=rep: r), nm))
    n = 0
    for nm in redact.get("names") or []:
        if nm.lower() in keep:
            continue
        n += 1
        rx = _bounded(nm)
        rules.append((rx, (lambda m, r=f"Person {n:02d}": r), nm))
    for old, new in (redact.get("rename") or {}).items():
        rx = _bounded(old)
        rules.append((rx, (lambda m, r=new: r), old))
    rules.sort(key=lambda r: len(r[2]), reverse=True)
    return rules


def scrub_text(text, idmap, rules):
    text = ID_RE.sub(lambda m: idmap.get(m.group(), m.group()), text)
    for rx, fn, _ in rules:
        text = rx.sub(fn, text)
    return text


def id_mapping(ids):
    """Order-preserving real -> fake, all 19 digits."""
    return {real: str(FAKE_BASE + i + 1) for i, real in enumerate(sorted(ids, key=int))}


# ---------------------------------------------------------------- inventory

def _tracked_text_files(root):
    ls = _git(["ls-files", "-z"], root)
    for rel in [p for p in ls.stdout.decode("utf-8", "replace").split("\0") if p]:
        f = pathlib.Path(root) / rel
        if f.is_file() and f.suffix.lower() not in BINARY_EXT:
            try:
                yield rel, f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def _walk_text_files(root):
    root = pathlib.Path(root)
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() not in BINARY_EXT and ".git" not in f.parts:
            try:
                yield f.relative_to(root).as_posix(), f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def _names_from_json(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in NAME_FIELDS and isinstance(v, str) and v.strip():
                found[v.strip()] += 1
            else:
                _names_from_json(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _names_from_json(v, found)


def inventory(files):
    """(ids Counter, {id: files}, JSON name candidates Counter)."""
    ids, where, names = Counter(), defaultdict(set), Counter()
    for rel, text in files:
        for m in ID_RE.finditer(text + " " + rel):
            ids[m.group()] += 1
            where[m.group()].add(rel)
        if rel.endswith((".json", ".jsonl")):
            chunks = text.splitlines() if rel.endswith(".jsonl") else [text]
            for c in chunks:
                try:
                    _names_from_json(json.loads(c), names)
                except ValueError:
                    pass
    return ids, where, names


def cmd_inventory():
    files = [(r, t) for r, t in _tracked_text_files(_repo()) if not r.startswith(PRIVATE_DIR + "/")]
    ids, where, names = inventory(files)
    leagues, managers, redact = load_plan()
    print(f"{len(ids)} distinct Sleeper-length ids in tracked files -- export replaces ALL of them.\n")
    if not leagues["leagues"]:
        print("  NO LEAGUE MAP. Run `release leagues --fetch` on the PC first.\n")
    for e in leagues["leagues"]:
        print(f"  {e['key']}  {e.get('format', '')}: replaces {', '.join(repr(s) for s in e['replace'])}")
    if not managers["managers"]:
        print("\n  NO MANAGER MAP. Run `release managers --fetch` on the PC -- without it, only")
        print("  names typed into redact.json are protected.")
    else:
        mine = [e["key"] for e in managers["managers"] if e.get("self")]
        print(f"\n  {len(managers['managers'])} managers mapped" + (f" (you: {mine[0]})" if mine else ""))
    covered = {n.lower() for e in managers["managers"] for n in e["names"] + e["teams"]} | \
              {n.lower() for n in redact.get("names", []) + redact.get("keep", [])}
    loose = [(n, c) for n, c in names.most_common() if n.lower() not in covered]
    if loose:
        print("\n  JSON names NOT covered by any map (decide each):")
        for n, c in loose[:40]:
            print(f"    {n!r}  x{c}")
    print("\n  Friends' REAL names (first names, nicknames) only in prose are not in any Sleeper")
    print("  field. Add them to data/release/redact.json \"names\" by hand.")
    return 0


# ------------------------------------------------------------------ export

def export(dest, repo=None, plan=None):
    """git archive HEAD -> dest minus data/release/, then scrub every text
    file, filename and folder name. Returns (rewritten, binaries, idmap)."""
    repo = pathlib.Path(repo or _repo())
    dest = pathlib.Path(dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} is not empty -- export into a fresh folder")
    if repo.resolve() in dest.parents or dest == repo.resolve():
        raise SystemExit("export destination must be OUTSIDE the repo")
    leagues, managers, redact = plan if plan is not None else load_plan(repo)
    dest.mkdir(parents=True, exist_ok=True)
    tar = _git(["archive", "--format=tar", "HEAD"], repo)
    if tar.returncode:
        raise SystemExit(tar.stderr.decode())
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
        members = [m for m in t.getmembers()
                   if not (m.name == PRIVATE_DIR or m.name.startswith(PRIVATE_DIR + "/"))]
        safe = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        t.extractall(dest, members=members, **safe)

    ids, _, _ = inventory(_walk_text_files(dest))
    idmap = id_mapping(ids)
    rules = build_rules(leagues, managers, redact)
    rewritten, binaries = 0, []
    for f in [p for p in dest.rglob("*") if p.is_file()]:
        rel = f.relative_to(dest).as_posix()
        if f.suffix.lower() in BINARY_EXT:
            binaries.append(rel)
            continue
        try:
            t0 = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            binaries.append(rel)
            continue
        t1 = scrub_text(t0, idmap, rules)
        if t1 != t0:
            f.write_text(t1, encoding="utf-8", newline="")
            rewritten += 1
    # rename deepest first so a parent rename never strands a child path
    for p in sorted(dest.rglob("*"), key=lambda p: -len(p.parts)):
        new = scrub_text(p.name, idmap, rules)
        if new != p.name:
            p.rename(p.with_name(new))
    rows = ["| Key | Format | Seasons on Sleeper |", "|---|---|---:|"]
    for e in leagues.get("leagues", []):
        rows.append(f"| {e['key']} | {e.get('format') or ''} | {len(e.get('ids') or [])} |")
    (dest / "LEAGUES.md").write_text(
        "# Leagues\n\nEvery league in this repo is referred to by a surrogate key. Names,\n"
        "ids and managers are private; the format is what the engine has to handle.\n\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    (dest / "RELEASE_NOTE.md").write_text(
        "Scrubbed public copy of a private repository. Leagues are LG01..., managers\n"
        "MGR01..., and Sleeper ids are order-preserving placeholders (9000...). Player\n"
        "ids and NFL stats are public data and unchanged.\n", encoding="utf-8")
    return rewritten, sorted(binaries), idmap


def verify(dest, originals, plan):
    """Every surviving private token: [(rel, token)]. Empty = clean."""
    dest = pathlib.Path(dest)
    leagues, managers, redact = plan
    rules = build_rules(leagues, managers, redact)
    orig = set(originals)
    bad = []
    if (dest / PRIVATE_DIR).exists():
        bad.append((PRIVATE_DIR, "private folder exported"))
    paths_all = [p.relative_to(dest).as_posix() for p in dest.rglob("*")]
    texts = dict(_walk_text_files(dest))
    for rel in paths_all:
        body = texts.get(rel, "")
        for m in ID_RE.finditer(body + " " + rel):
            if m.group() in orig:
                bad.append((rel, m.group()))
        for rx, _, name in rules:
            if rx.search(body) or rx.search(rel):
                bad.append((rel, name))
    return bad


def _ids_path(stamp=None):
    return paths.out("release", f"ids_{stamp or 'latest'}.json")


def _save_ids(idmap):
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for p in (_ids_path(stamp), _ids_path()):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sorted(idmap)), encoding="utf-8")


def cmd_export(dest):
    plan = load_plan()
    if not plan[0]["leagues"]:
        raise SystemExit("no league map -- run `release leagues --fetch` first")
    rewritten, binaries, idmap = export(dest, plan=plan)
    _save_ids(idmap)
    print(f"exported HEAD to {pathlib.Path(dest).resolve()} (without {PRIVATE_DIR}/)")
    print(f"  {len(idmap)} ids replaced, {rewritten} text files rewritten, "
          f"{len(plan[0]['leagues'])} leagues and {len(plan[1]['managers'])} managers keyed")
    if binaries:
        print(f"  {len(binaries)} binary files copied UNSCRUBBED (check they hold no ids):")
        for b in binaries[:20]:
            print(f"    {b}")
    bad = verify(dest, idmap.keys(), plan)
    print("  verify: " + ("CLEAN" if not bad else f"{len(bad)} survivors -- run `release verify`"))
    print(f"  real-id list kept in THIS repo at {_ids_path()} (gitignored), not in the export")
    return 1 if bad else 0


def cmd_verify(dest):
    p = _ids_path()
    originals = json.loads(p.read_text(encoding="utf-8")) if p.exists() else \
        list(inventory(_tracked_text_files(_repo()))[0])
    bad = verify(dest, originals, load_plan())
    if not bad:
        print(f"CLEAN: no real id, league name, manager or listed name in {dest}")
        return 0
    print(f"{len(bad)} survivors:")
    for rel, tok in bad[:60]:
        print(f"  {rel}: {tok}")
    return 1


# ------------------------------------------------------------------ update

def update(dest, repo=None, plan=None):
    """Refresh an existing public clone in place, keeping its .git.

    HEAD is exported to a staging folder and verified there first; a copy
    that fails verify never touches the clone. Then the clone's tracked files
    are removed, the staged copy is laid over it, and `git add -A` stages the
    difference. It never commits or pushes: John reads the diff and does both.
    Refuses a clone with uncommitted changes, so nothing done by hand (or a
    previous update not yet committed) is silently overwritten.
    Returns (bad, status_lines, idmap, binaries)."""
    repo = pathlib.Path(repo or _repo()).resolve()
    dest = pathlib.Path(dest).resolve()
    if not (dest / ".git").is_dir():
        raise SystemExit(f"{dest} is not a git clone -- `release export` makes the first copy")
    if repo in dest.parents or dest == repo:
        raise SystemExit("update destination must be OUTSIDE the repo")
    st = _git(["status", "--porcelain"], dest)
    if st.returncode:
        raise SystemExit(st.stderr.decode("utf-8", "replace"))
    if st.stdout.strip():
        raise SystemExit(f"{dest} has uncommitted changes -- commit or discard them first "
                         "(`git status` there shows what)")
    plan = plan if plan is not None else load_plan(repo)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="br-release-"))
    try:
        stage = tmp / "copy"
        _, binaries, idmap = export(stage, repo=repo, plan=plan)
        bad = verify(stage, idmap.keys(), plan)
        if bad:
            return bad, [], idmap, binaries
        tracked = _git(["ls-files", "-z"], dest).stdout.decode("utf-8").split("\0")
        parents = set()
        for rel in filter(None, tracked):
            f = dest / rel
            if f.is_file() or f.is_symlink():
                f.unlink()
                parents.add(f.parent)
        # prune folders the removals emptied, deepest first; ignored files keep theirs alive
        for d in sorted(parents, key=lambda p: -len(p.parts)):
            while d != dest and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        shutil.copytree(stage, dest, dirs_exist_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    add = _git(["add", "-A"], dest)
    if add.returncode:
        raise SystemExit(add.stderr.decode("utf-8", "replace"))
    lines = _git(["status", "--short"], dest).stdout.decode("utf-8", "replace").splitlines()
    return [], lines, idmap, binaries


def cmd_update(dest, run_tests=True):
    plan = load_plan()
    if not plan[0]["leagues"]:
        raise SystemExit("no league map -- run `release leagues --fetch` first")
    dest = pathlib.Path(dest).resolve()
    head = _git(["log", "-1", "--format=%h %s"], _repo()).stdout.decode("utf-8", "replace").strip()
    bad, lines, idmap, binaries = update(dest, plan=plan)
    if bad:
        print(f"verify FAILED on the staged copy -- {dest} was not touched. {len(bad)} survivors:")
        for rel, tok in bad[:60]:
            print(f"  {rel}: {tok}")
        return 1
    _save_ids(idmap)
    print(f"updated {dest} from private HEAD {head}")
    print("  verify: CLEAN (checked on the staged copy before anything was replaced)")
    if not lines:
        print("  nothing changed -- the public copy already matches")
        return 0
    kinds = Counter(l[:2].strip() or "?" for l in lines)
    print("  staged: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
          + "   (A added, M modified, D deleted, R renamed)")
    for l in lines[:40]:
        print(f"    {l}")
    if len(lines) > 40:
        print(f"    ... {len(lines) - 40} more (`git status` in the clone)")
    if binaries:
        print(f"  {len(binaries)} binary files copied unscrubbed, as with export")
    rc = 0
    if run_tests:
        print("  running the offline suite inside the clone ...")
        t = subprocess.run([sys.executable, "br.py", "test"], cwd=str(dest), capture_output=True)
        out = (t.stdout + t.stderr).decode("utf-8", "replace").strip().splitlines()
        print("    " + (out[-1] if out else "(no output)"))
        rc = t.returncode
        if rc:
            print("  suite FAILED in the clone -- fix before committing (`git reset --hard` there undoes the update)")
    print("\nNothing is committed. Review, then in PowerShell:")
    print(f"  cd {dest}")
    print("  git diff --cached --stat")
    print(f'  git commit -m "sync: {head.split(" ", 1)[0]}"')
    print("  git push")
    return rc


# --------------------------------------------------------------- selftest

def selftest():
    import os
    import tempfile
    ok = []

    def ck(name, cond):
        ok.append((name, bool(cond)))
        print(f"  {'ok' if cond else 'XX'}  {name}")

    tmp = pathlib.Path(tempfile.mkdtemp())
    repo = tmp / "repo"
    repo.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def git(*a):
        subprocess.run(["git", *a], cwd=str(repo), env=env, capture_output=True, check=True)

    def w(rel, text):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    git("init", "-q")
    fake_key = "pk_TESTONLY_7f3a9c2e1b"
    w("config.json", json.dumps({"username": "dirtymurdock", "k": fake_key}))
    git("add", "."); git("commit", "-q", "-m", "oops")

    oak, crash, hyb_a, hyb_b = ("9000000000000000017", "9000000000000000012",
                               "9000000000000000016", "9000000000000000019")
    prev_a = "9000000000000000007"
    index = {
        "oakwood": {"id": oak, "name": "The Oakwood Senate", "type": "redraft-keeper",
                    "teams": 12, "aliases": ["oakwood", "senate"]},
        "crash-pals": {"id": crash, "name": "Crash Pals", "type": "redraft", "teams": 14,
                      "aliases": ["crashpals", "crash pals"]},
        "midnight": {"id": hyb_a, "name": "Midnight Talent", "type": "hybrid",
                           "teams": 12, "aliases": ["mido", "hybrid"], "former_names": ["Hybrid 9"]},
        "hybrid9": {"id": hyb_b, "name": "Hybrid 9 🦸", "type": "hybrid", "teams": 12,
                     "aliases": ["hybrid 9", "hero"]},
    }
    w("config.json", json.dumps({"username": "dirtymurdock"}))
    w("leagues/_index.json", json.dumps({"leagues": index}, ensure_ascii=False))
    w("leagues/oakwood/brief.md", "Oakwood draft brief. Zorblax took Cook. Quentin said so.\n")
    w(f"data/truth/2026/wk01/x/league_{oak}.json",
      json.dumps({"league_id": oak, "name": "The Oakwood Senate", "season": "2026"}))
    w("battle_rhythm/code.py", 'SLUG = "oakwood"\nALIAS = "crashpals"\n# we will see; dynasty value\n'
                               'x = paths.id_for("oakwood")\n')
    w("battle_rhythm/ids.py", 'OAKWOOD_2026 = 1\nprint("\\n\\nOAKWOOD PLAN")\n'
                              'open("queue_oakwood.json")\n# the midori tea stays\n')
    w("ROADMAP.md", "Crash Pals (undated), and The Oakwood\nSenate drafts next.\n")
    w("DECISIONS.md", "Crash Pals drafted. The Hybrid 9 room. Will said the dynasty room buys vets.\n"
                      "Will Smith's team Moon Unit. dirtymurdock is me.\n")
    w("data/release/redact.json", json.dumps({"names": ["Quentin"], "keep": ["dirtymurdock"]}))
    (repo / "roster.png").write_bytes(b"\x89PNG....")
    git("add", "."); git("commit", "-q", "-m", "remove key, add data")

    # --- scan-key
    hits = scan_history(fake_key, repo)
    ck("key removed from HEAD is still found in history", any(h[0].startswith("history") for h in hits))
    ck("the hit names the file, never the key", all(fake_key not in str(h) for h in hits)
       and any(h[1] == "config.json" for h in hits))
    ck("a string that is nowhere comes back clean", scan_history("zz_not_present_zz", repo) == [])
    try:
        scan_history("", repo)
        ck("an empty key is refused", False)
    except ValueError:
        ck("an empty key is refused", True)

    # --- surrogate leagues
    api = {f"league/{hyb_a}": {"previous_league_id": prev_a},
           f"league/{prev_a}": {"name": "Hybrid 9", "previous_league_id": None},
           f"league/{oak}": {}, f"league/{crash}": {}, f"league/{hyb_b}": {}}
    chains = fetch_chains(index, lambda q: api.get(q))
    ck("--fetch walks previous_league_id to past seasons", chains[hyb_a] == [(prev_a, "Hybrid 9")])
    lg = propose_leagues(index, _truth_league_docs(repo), chains)
    keys = {e["ids"][0]: e for e in lg["leagues"]}
    ck("keys are numbered by league id", [e["key"] for e in sorted(lg["leagues"],
                                          key=lambda e: int(e["ids"][0]))] == ["LG01", "LG02", "LG03", "LG04"])
    ck("a past season shares its league's key", prev_a in keys[hyb_a]["ids"])
    ck("generic format aliases are not treated as identity",
       "hybrid" not in keys[hyb_a]["replace"] and "hero" not in keys[hyb_b]["replace"])
    again = propose_leagues({**index, "new": {"id": "9000000000000000024", "name": "New League"}},
                            existing=lg)
    ck("re-running keeps every key and appends new leagues",
       {e["ids"][0]: e["key"] for e in again["leagues"]}[oak] == keys[oak]["key"]
       and any(e["key"] == "LG05" for e in again["leagues"]))

    # --- surrogate managers
    users = {oak: [{"user_id": "9000000000000000002", "display_name": "dirtymurdock"},
                   {"user_id": "9000000000000000004", "display_name": "Zorblax",
                    "metadata": {"team_name": "Moon Unit"}},
                   {"user_id": "9000000000000000005", "display_name": "Will"}],
             crash: [{"user_id": "9000000000000000004", "display_name": "zorblax"}]}
    mg = propose_managers(users, self_name="dirtymurdock")
    bam = next(e for e in mg["managers"] if "Zorblax" in e["names"])
    ck("one manager across leagues keeps one key and collects both spellings",
       set(bam["names"]) == {"Zorblax", "zorblax"} and bam["teams"] == ["Moon Unit"])
    ck("John is marked self", any(e.get("self") for e in mg["managers"]))

    # --- export
    redact = {"names": ["Quentin"], "rename": {}, "keep": ["dirtymurdock"]}
    dest = tmp / "public"
    rewritten, binaries, idmap = export(dest, repo=repo, plan=(lg, mg, redact))
    txt = "\n".join(t for _, t in _walk_text_files(dest))
    allpaths = " ".join(p.relative_to(dest).as_posix() for p in dest.rglob("*"))
    k_oak, k_crash = keys[oak]["key"], keys[crash]["key"]
    ck("no real id survives, in content or paths",
       not any(i in txt or i in allpaths for i in idmap))
    ck("league names, slugs and aliases are gone (any case)",
       not re.search(r"oakwood|senate|crash ?-?pals|midnight|mido\b", txt + allpaths, re.I))
    ck("prose gets the key, a lowercase slug gets the lowercase key",
       f"{k_oak} draft brief" in txt and f'SLUG = "{k_oak.lower()}"' in txt)
    ck("the league folder is renamed to its key", (dest / "leagues" / k_oak.lower() / "brief.md").exists())
    ck("a name two leagues shared becomes both keys",
       f"The {'-'.join(sorted([keys[hyb_a]['key'], keys[hyb_b]['key']]))} room" in txt)
    ids_py = (dest / "battle_rhythm" / "ids.py").read_text(encoding="utf-8")
    ck("a name glued to an underscore is still caught", f"{k_oak}_2026" in ids_py
       and f"queue_{k_oak.lower()}.json" in ids_py)
    ck("a name right after a literal \\n escape is still caught", f"\\n\\n{k_oak} PLAN" in ids_py)
    ck("a word that merely contains an alias is left alone", "the midori tea stays" in ids_py)
    rm = (dest / "ROADMAP.md").read_text(encoding="utf-8")
    ck("a league name wrapped across two lines is still one name",
       "Oakwood" not in rm and "Senate" not in rm and f"{k_oak} drafts next" in rm)
    ck("generic format words survive", "dynasty value" in txt and "the dynasty room" in txt)
    ck("managers become MGRnn, their teams Team MGRnn, any case",
       "Zorblax" not in txt and f"Team {bam['key']}" in txt and "Moon Unit" not in txt)
    will = next(e["key"] for e in mg["managers"] if "Will" in e["names"])
    ck("a common-word name is replaced only in its exact form",
       f"{will} said" in txt and "we will see" in txt)
    ck("redact names become Person NN; kept names stay",
       "Quentin" not in txt and "Person 01" in txt and "dirtymurdock is me" in txt)
    ck("data/release/ is never exported", not (dest / "data" / "release").exists())
    ck("binaries are copied and reported", binaries == ["roster.png"])
    legend = (dest / "LEAGUES.md").read_text(encoding="utf-8")
    ck("LEAGUES.md lists every key with its format and no name",
       all(e["key"] in legend for e in lg["leagues"]) and "redraft-keeper, 12 teams" in legend
       and "Oakwood" not in legend)
    ck("the removed key is not in the export", fake_key not in txt)
    ck("verify is clean on the export", verify(dest, idmap.keys(), (lg, mg, redact)) == [])
    (dest / "leak.md").write_text(f"oops {oak} Crash Pals zorblax")
    got = {t for _, t in verify(dest, idmap.keys(), (lg, mg, redact))}
    ck("verify catches a planted id, league name and manager", {oak, "crash pals"} <= got
       and any(t.lower() == "zorblax" for t in got))
    try:
        export(dest, repo=repo, plan=(lg, mg, redact))
        ck("export refuses a non-empty destination", False)
    except SystemExit:
        ck("export refuses a non-empty destination", True)

    # --- update: refresh a public clone in place
    pub = tmp / "pub"
    export(pub, repo=repo, plan=(lg, mg, redact))

    def pgit(*a):
        return subprocess.run(["git", *a], cwd=str(pub), env=env, capture_output=True,
                              check=True).stdout.decode("utf-8", "replace")
    pgit("init", "-q"); pgit("add", "."); pgit("commit", "-q", "-m", "first public copy")
    (pub / ".git" / "info" / "exclude").write_text("__pycache__/\n")
    (pub / "__pycache__").mkdir()
    (pub / "__pycache__" / "junk.pyc").write_bytes(b"x")  # ignored-style leftovers survive
    w("NEW.md", "Crash Pals added a note.\n")
    (repo / "ROADMAP.md").unlink()
    git("add", "-A"); git("commit", "-q", "-m", "more")
    bad, st, _, _ = update(pub, repo=repo, plan=(lg, mg, redact))
    ck("update: verify clean, the new file and the deletion are staged",
       not bad and any(l.endswith("NEW.md") and l.startswith("A") for l in st)
       and any(l.endswith("ROADMAP.md") and l.startswith("D") for l in st))
    ck("update: history kept and nothing committed", pgit("rev-list", "--count", "HEAD").strip() == "1")
    ck("update: the new file is scrubbed", "Crash Pals" not in (pub / "NEW.md").read_text(encoding="utf-8"))
    ck("update: data/release/ still never lands", not (pub / "data" / "release").exists())
    ck("update: ignored leftovers in the clone are left alone", (pub / "__pycache__" / "junk.pyc").exists())
    try:
        update(pub, repo=repo, plan=(lg, mg, redact))
        ck("update refuses a clone with uncommitted changes", False)
    except SystemExit:
        ck("update refuses a clone with uncommitted changes", True)
    pgit("commit", "-q", "-m", "sync")
    bad, st, _, _ = update(pub, repo=repo, plan=(lg, mg, redact))
    ck("update: a second run with no new commits changes nothing", not bad and st == [])
    try:
        update(tmp / "repo" / "leagues", repo=repo, plan=(lg, mg, redact))
        ck("update refuses a folder that is not a clone", False)
    except SystemExit:
        ck("update refuses a folder that is not a clone", True)

    bad = [n for n, c in ok if not c]
    print(f"\n{len(ok) - len(bad)}/{len(ok)} " + ("selftest PASSED" if not bad else "FAILED"))
    return 1 if bad else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    cmd = argv[0] if argv else ""
    if cmd == "scan-key":
        return cmd_scan_key()
    if cmd == "leagues":
        return cmd_leagues(fetch="--fetch" in argv)
    if cmd == "managers" and "--fetch" in argv:
        return cmd_managers()
    if cmd == "inventory":
        return cmd_inventory()
    if cmd == "update" and len(argv) > 1:
        return cmd_update(argv[1], run_tests="--no-test" not in argv)
    if cmd in ("export", "verify") and len(argv) > 1:
        return (cmd_export if cmd == "export" else cmd_verify)(argv[1])
    print(__doc__.split("\n\n")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
