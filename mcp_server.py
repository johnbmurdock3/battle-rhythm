"""
mcp_server.py — MCP (Model Context Protocol) server over stdio, stdlib-only.

Exposes the whole Sleeper toolkit as tools Claude can call from chat:
leagues, board, rookies, find, explain, recap, managers, weekly, waivers,
ledger, keeper, scoring_diff.
Every tool runs the SAME verified engine as the CLI — this file is transport,
not logic.

Setup (Claude Desktop, Windows):
  1. Open %APPDATA%\\Claude\\claude_desktop_config.json  (create if missing)
  2. Add:
     {
       "mcpServers": {
         "sleeper": {
           "command": "python",
           "args": ["C:\\\\Users\\\\johnb\\\\workspace\\\\Sleeper\\\\mcp_server.py"]
         }
       }
     }
  3. Restart Claude Desktop. Ask: "which of my teams is weakest at RB?"

Protocol notes: implements the minimal MCP surface a tools-only server needs —
initialize, notifications/initialized, ping, tools/list, tools/call — speaking
JSON-RPC 2.0 over stdio, one message per line. Print-style tools are captured
via stdout redirection and returned as text content.
"""

import contextlib
import io
import json
import sys
import traceback

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__
                else __file__.rsplit("/", 1)[0])

# Derived from leagues/_index.json, which is THE league key. This used
# to be a hand-typed dict and it drifted twice: it carried lg02 when
# keepers.json did not (8/13), and neither it nor the index had ever
# heard of LG07 (found 9/2). paths.selftest compared this dict
# against the index -- two hand-maintained copies, which is not a check.
# There is one copy now.
from battle_rhythm import paths as _paths

import re
import unicodedata


def _norm(s):
    """casefold, strip emoji/punct/extra spaces -> comparable key"""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if c.isalnum() or c.isspace())
    return re.sub(r"\s+", " ", s).strip().casefold()


LEAGUE_IDS = {slug: str(lg["id"]) for slug, lg in _paths.leagues().items()}


def _capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()




# chat nicknames -> unambiguous league ids (both Hybrids normalize to the
# same "lg03-lg05", so nicknames are the only safe shorthand for them)
# Chat nicknames -> unambiguous league ids. Also from the index: both
# Hybrids normalize to the same "lg03-lg05", so a nickname is the only
# safe shorthand for either, and the index is where they are written
# down. A slug is always an alias for itself.
ALIASES = {}
for _slug, _lg in _paths.leagues().items():
    for _a in [_slug, *(_lg.get("aliases") or [])]:
        _k = _norm(_a)
        if _k and _k in ALIASES and ALIASES[_k] != str(_lg["id"]):
            raise ValueError(f"leagues/_index.json: alias {_a!r} points at two "
                             f"leagues ({ALIASES[_k]} and {_lg['id']})")
        ALIASES[_k] = str(_lg["id"])


def _resolve(league):
    """Return a validated league_id or raise ValueError. Never passes
    unvalidated input through to a URL (spaces/emoji used to reach
    http.client and die there)."""
    from battle_rhythm.sleeper_client import load_leagues
    leagues = load_leagues().get("leagues", [])
    q = _norm(league)
    if not q:
        raise ValueError("no league given — name, nickname, or id required")
    if q.isdigit():
        if any(lg["league_id"] == q for lg in leagues):
            return q
        raise ValueError(f"league id {q} is not one of your leagues")
    if q in ALIASES:
        return ALIASES[q]
    hits = [lg for lg in leagues if q in _norm(lg.get("name"))]
    if len(hits) == 1:
        return hits[0]["league_id"]
    if len(hits) > 1:
        opts = ", ".join(f"{lg['name']} (id {lg['league_id']})" for lg in hits)
        raise ValueError(f"'{league}' is ambiguous: {opts} — use the id or a "
                         "nickname (hero / lg05)")
    names = ", ".join(lg.get("name") or "?" for lg in leagues)
    raise ValueError(f"league '{league}' not found. Your leagues: {names}")


# ------------------------------------------------------------------- tools

def t_leagues(args):
    """Every league: status, record, FAAB, roster shape, scoring identity."""
    from battle_rhythm.sleeper_client import report
    return _capture(report)


def t_board(args):
    """Live/pre-draft board for one league: VORP, dynasty ADP, age, injuries,
    turn plan. args: league (name/id), position (optional QB/RB/WR/TE/K/DEF)."""
    from battle_rhythm.draft_helper import board
    return _capture(board, _resolve(args.get("league")),
                    pos_filter=args.get("position"))


def t_rookies(args):
    """Available current-class rookies for a league, incl. taxi lottery
    tickets the projections rate near zero. args: league."""
    from battle_rhythm.draft_helper import rookies
    return _capture(rookies, _resolve(args.get("league")))


def t_find(args):
    """Price players by name under a league's scoring: projection, dynasty
    ADP, age, injury, drafted/available. args: league, names (list or str)."""
    from battle_rhythm.draft_helper import find
    names = args.get("names") or []
    if isinstance(names, str):
        names = [names]
    return _capture(find, _resolve(args.get("league")), names)


def t_explain(args):
    """Decompose one player's season projection stat-by-stat under a league's
    scoring, incl. the availability haircut. args: league, player."""
    from battle_rhythm.draft_helper import explain
    return _capture(explain, _resolve(args.get("league")), args.get("player") or "")


def t_managers(args):
    """Per-manager draft-behavior profiles (age drafted, reach vs dynasty
    price, vet-hungry vs youth-hoarder labels). args: league."""
    from battle_rhythm.draft_helper import recap
    return _capture(recap, _resolve(args.get("league")))


def t_recap(args):
    """Grade MY OWN picks the morning after a draft: where I beat the board
    (selection), where I beat the market (price), the biggest steal, the
    biggest reach, and whether a required slot went undrafted. args: league.

    Renamed 9/2. This name used to serve the per-manager room profile,
    which is now `managers`."""
    from battle_rhythm.recap import run
    return _capture(run, _resolve(args.get("league")))


def t_weekly(args):
    """In-season brief for all leagues (or one): optimal lineup, two-tier
    waivers with drops, trade candidates, situation flags. Pre-draft leagues
    are skipped by design. args: league (optional)."""
    from battle_rhythm import weekly
    lid = _resolve(args["league"]) if args.get("league") else None
    argv = ["weekly.py"] + ([lid] if lid else [])
    old = sys.argv
    try:
        sys.argv = argv
        return _capture(weekly.main)
    finally:
        sys.argv = old


def t_waivers(args):
    """Waiver claims for one league THIS week, priced under its own
    scoring: tier 1 (beats a projected starter, with a sized FAAB bid and
    the logic behind it) and tier 2 (beats your worst ACTIVE bench player,
    churn). Each row carries the Sleeper depth-chart slot, a ROLE? flag
    when the projection prices a job the chart says he lost, handcuff
    ties to your own starters, and the named drop -- never a reserve or
    taxi player. Order-based leagues show your waiver position instead
    of a bid. Recorded to the ledger unless record=false. args: league."""
    from battle_rhythm import weekly, ledger
    lid = _resolve(args.get("league"))
    argv = ["weekly.py", lid, "--waivers"]
    if args.get("record") is False:
        argv.append("--no-record")
    old = sys.argv
    try:
        sys.argv = argv
        return _capture(weekly.main)
    finally:
        sys.argv = old
        ledger.ENABLED[0] = True


def t_ledger(args):
    """The recommendation ledger: every lineup / waiver / trade call the
    toolkit has made this season, how many have been scored against
    actual results, and the win rate by projected-edge bucket beside the
    feed's own calibration prior. score=true first grades every rec whose
    weeks have played (needs network; run on the PC). args: league
    (optional), score (optional bool)."""
    from battle_rhythm import ledger
    argv = []
    if args.get("score"):
        argv.append("score")
    if args.get("league"):
        argv += ["--league", _resolve(args["league"])]
    return _capture(ledger.main, argv)


def t_keeper(args):
    """Keeper recommendations. Hybrids: 3+2 DR slots with QB caps, taxi-aware,
    re-draftability tags and SWAP advisories. args: league (optional; default
    both Hybrids; 'lg04' becomes meaningful from the 2027 offseason)."""
    from battle_rhythm import keeper
    lid = _resolve(args["league"]) if args.get("league") else None
    if lid == LEAGUE_IDS["lg04"]:
        return _capture(keeper.analyze_priced)
    if lid:
        return _capture(keeper.analyze, lid)
    buf = []
    for hyb in keeper.HYBRIDS:
        buf.append(_capture(keeper.analyze, hyb))
    return "\n".join(buf)


def t_scoring_diff(args):
    """Where the leagues disagree on scoring rules — the table that
    explains why the same player is worth different amounts per league."""
    from battle_rhythm.sleeper_client import load_leagues, scoring_diff
    lgs = load_leagues().get("leagues", [])
    rows = scoring_diff(lgs)
    hdr = [(lg.get("name") or "?").strip()[:14] for lg in lgs]
    out = [f"{'rule':<18}" + "".join(f"{h:>16}" for h in hdr)]
    for k, vals in rows.items():
        out.append(f"{k:<18}" + "".join(f"{v:>16g}" for v in vals))
    return "\n".join(out)


TOOLS = {
    "leagues": (t_leagues, {"type": "object", "properties": {}}),
    "board": (t_board, {"type": "object", "properties": {
        "league": {"type": "string", "description": "league name, nickname, or id"},
        "position": {"type": "string", "description": "optional QB/RB/WR/TE/K/DEF"}},
        "required": ["league"]}),
    "rookies": (t_rookies, {"type": "object", "properties": {
        "league": {"type": "string"}}, "required": ["league"]}),
    "find": (t_find, {"type": "object", "properties": {
        "league": {"type": "string"},
        "names": {"type": "array", "items": {"type": "string"},
                  "description": "player-name fragments to price"}},
        "required": ["league", "names"]}),
    "explain": (t_explain, {"type": "object", "properties": {
        "league": {"type": "string"}, "player": {"type": "string"}},
        "required": ["league", "player"]}),
    "recap": (t_recap, {"type": "object", "properties": {
        "league": {"type": "string"}}, "required": ["league"]}),
    "managers": (t_managers, {"type": "object", "properties": {
        "league": {"type": "string"}}, "required": ["league"]}),
    "weekly": (t_weekly, {"type": "object", "properties": {
        "league": {"type": "string", "description": "optional; all leagues if omitted"}}}),
    "waivers": (t_waivers, {"type": "object", "properties": {
        "league": {"type": "string", "description": "league name, nickname, or id"},
        "record": {"type": "boolean", "description": "default true; false skips the ledger"}},
        "required": ["league"]}),
    "ledger": (t_ledger, {"type": "object", "properties": {
        "league": {"type": "string", "description": "optional; all leagues if omitted"},
        "score": {"type": "boolean", "description": "grade played weeks first (network)"}}}),
    "keeper": (t_keeper, {"type": "object", "properties": {
        "league": {"type": "string", "description": "optional; both Hybrids if omitted"}}}),
    "scoring_diff": (t_scoring_diff, {"type": "object", "properties": {}}),
}


# ------------------------------------------------------------ JSON-RPC loop

def _reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid = req.get("method"), req.get("id")
        if method == "initialize":
            _reply(mid, {
                "protocolVersion": (req.get("params") or {}).get(
                    "protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sleeper", "version": "1.0.0"}})
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue  # notifications get no reply
        elif method == "ping":
            _reply(mid, {})
        elif method == "tools/list":
            _reply(mid, {"tools": [
                {"name": name, "description": (fn.__doc__ or "").strip(),
                 "inputSchema": schema}
                for name, (fn, schema) in TOOLS.items()]})
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in TOOLS:
                _reply(mid, error={"code": -32602, "message": f"unknown tool {name}"})
                continue
            try:
                text = TOOLS[name][0](args)
                _reply(mid, {"content": [{"type": "text", "text": text or "(no output)"}],
                             "isError": False})
            except (ValueError, SystemExit) as e:
                _reply(mid, {"content": [{"type": "text", "text": str(e)}],
                             "isError": True})
            except Exception:
                _reply(mid, {"content": [{"type": "text",
                                          "text": traceback.format_exc(limit=3)}],
                             "isError": True})
        elif mid is not None:
            _reply(mid, error={"code": -32601, "message": f"unknown method {method}"})


if __name__ == "__main__":
    main()
