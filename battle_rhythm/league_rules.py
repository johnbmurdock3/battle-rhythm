"""
league_rules.py — the one reader for data/keepers.json.

Before 8/13 five modules opened, parsed and interpreted that file
independently across seven sites: keeper.py, lineup_value.py (three
times), roster_snapshot.py, draft_review.py and dashboard.py. It holds
the league rules that are NOT in the Sleeper API — the thing CLAUDE.md
names as a repeat failure source, and the thing three consecutive wrong
answers about the taxi squad came from not reading.

Seven independent readers is how two of them end up disagreeing about
what a league is. Same reasoning as snake_picks delegating to
sleeper_client: "Three copies is how all three ended up wrong."

The functions here were not written for this file. `room_shave` and
`keeper_rules` already existed in lineup_value, with six selftest checks
covering the override, the missing-league case and the unreadable-path
case. They moved verbatim; lineup_value re-exports them so its own
tests and callers are unchanged.

Imports paths and stdlib only, so anything can import it.

    python league_rules.py --selftest
"""

import json

from battle_rhythm import paths


def all_rules(path=None):
    """The whole keepers.json, or {} if it cannot be read. Keys are the
    19-digit league ids as strings, plus '_'-prefixed notes."""
    try:
        return json.loads((path or paths.data("keepers.json"))
                          .read_text(encoding="utf-8"))
    except Exception:
        return {}


def keeper_rules(league_id, path=None):
    """This league's entry in keepers.json, or {} if it has none."""
    return (all_rules(path).get(str(league_id))) or {}


def room_shave(league_id, override=None, path=None):
    """Picks to subtract from ADP when asking "will he last to my turn."

    This is a property of the ROOM, not of the market, so it is per-league
    data in keepers.json and never a global default. I shipped it as a
    hardcoded 10 for every league on 8/11 by generalising a LG01
    observation — that room buys veterans about ten picks early
    (CLAUDE.md lesson 6). His correction: the Hybrid rooms draft close to
    market, "these guys know what they're doing, for the most part."

    Once a draft has picks on the board room_bias.py MEASURES this; the
    stored number is only the pre-draft prior. An explicit --shave wins
    over both.
    """
    if override is not None:
        return int(override)
    v = keeper_rules(league_id, path).get("room_shave")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def is_keeper_league(league_id, path=None):
    """The "keeper": true flag.

    Sleeper's settings.type == 2 means dynasty-TYPED, which covers both
    3-keeper Hybrids as well as full dynasty. The type field cannot tell
    them apart; this flag is why the file exists (CLAUDE.md lesson 5).
    """
    return bool(keeper_rules(league_id, path).get("keeper"))


def selftest():
    import json as _json
    import os
    import pathlib
    import tempfile

    checks = []

    def ck(n, c):
        checks.append((n, bool(c)))

    fd, tmp = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(_json.dumps({"DB": {"room_shave": 10, "keeper": False},
                             "HY": {"room_shave": 0, "keeper": True},
                             "_note": "not a league"}))
    tp = pathlib.Path(tmp)
    try:
        ck("room_shave reads the stored per-league number",
           room_shave("DB", path=tp) == 10)
        ck("a stored zero is a real zero, not a missing value",
           room_shave("HY", path=tp) == 0)
        ck("an unknown league shaves nothing",
           room_shave("NO", path=tp) == 0 and room_shave("???", path=tp) == 0)
        ck("an explicit override beats the file",
           room_shave("DB", override=3, path=tp) == 3)
        ck("an unreadable path shaves nothing rather than raising",
           room_shave("DB", path=pathlib.Path("/nope/nope.json")) == 0)
        ck("keeper_rules returns the entry",
           keeper_rules("HY", path=tp).get("room_shave") == 0)
        ck("keeper_rules on an unknown league is an empty dict, not None",
           keeper_rules("nope", path=tp) == {})
        ck("is_keeper_league reads the flag",
           is_keeper_league("HY", path=tp) and not is_keeper_league("DB",
                                                                    path=tp))
        ck("all_rules keeps the '_' notes it was given",
           "_note" in all_rules(path=tp))
        ck("all_rules on a bad path is {} rather than a raise",
           all_rules(path=pathlib.Path("/nope/nope.json")) == {})
        # the real file, if it is there
        real = all_rules()
        ck("the live keepers.json parses and is keyed by league id",
           bool(real) and any(k.isdigit() for k in real))
    finally:
        try:
            tp.unlink()
        except OSError:
            pass

    for n, c in checks:
        print(f"  {'ok' if c else 'XX'}  {n}")
    ok = all(c for _, c in checks)
    print(f"\nselftest {'PASSED' if ok else 'FAILED'}  "
          f"({sum(1 for _, c in checks if c)}/{len(checks)})")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
