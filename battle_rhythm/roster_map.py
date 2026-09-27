"""
roster_map.py — who owns whom, league-wide.

The toolkit knew YOUR roster and each manager's draft *behavior*, but
never who owned which player. That gap turned "did vdoan take Gainwell
to block me" into speculation when it should have been a lookup.

    python roster_map.py dynasty                 # every manager's roster
    python roster_map.py dynasty --who gainwell  # who owns him
    python roster_map.py dynasty --links         # THE useful one
    python roster_map.py --selftest              # offline

--links is the reason this exists. For every player you roster it walks
his dossier's competition list, resolves those names to player_ids, and
reports who owns them. That surfaces, in one table:

  - your handcuffs someone else owns (the Gainwell case)
  - your handcuffs still free (claimable insurance)
  - target collisions you have created on your own roster
  - which manager is accumulating leverage against your backfield

Read-only. Ownership during a live draft = rostered players plus picks
already made, the same union board_data uses to decide availability.
"""

import json
import sys
from collections import defaultdict


def ownership(league_id):
    """{player_id: (owner_id, display_name)} — rosters + picks so far."""
    from battle_rhythm.sleeper_client import get
    users = {u.get("user_id"): (u.get("display_name") or "?")
             for u in (get(f"league/{league_id}/users") or [])}
    owner_of_roster = {}
    own = {}
    for r in get(f"league/{league_id}/rosters") or []:
        oid = r.get("owner_id")
        owner_of_roster[r.get("roster_id")] = oid
        for p in (r.get("players") or []):
            own[str(p)] = (oid, users.get(oid, str(oid)[:8]))
    lg = get(f"league/{league_id}") or {}
    from battle_rhythm.draft_helper import season_picks
    _picks = season_picks(lg) if lg else []
    if _picks:
        for pk in _picks:
            pid = pk.get("player_id")
            if not pid:
                continue
            oid = pk.get("picked_by") or owner_of_roster.get(pk.get("roster_id"))
            # a live pick beats a stale roster snapshot
            own[str(pid)] = (oid, users.get(oid, str(oid)[:8]))
    return own, users


def by_manager(own, tbl):
    out = defaultdict(list)
    for pid, (oid, name) in own.items():
        m = tbl.get(pid) or {}
        out[name].append((m.get("position") or "?",
                          m.get("full_name") or pid,
                          m.get("team") or "FA",
                          m.get("age")))
    for k in out:
        out[k].sort(key=lambda x: (["QB", "RB", "WR", "TE", "K", "DEF"].index(x[0])
                                   if x[0] in ("QB", "RB", "WR", "TE", "K", "DEF")
                                   else 9, x[1]))
    return out


def resolve_name(tbl, name, want_team=None, want_pos=None):
    """(pid, meta, status) or (None, None, 'unknown').

    status is 'same-team' | 'moved' — and that distinction is the whole
    point. Rachaad White really is in the player table and really was
    Bucky Irving's backfield mate, but he plays for Washington now, so
    reporting MGR38 as holding your Irving handcuff is false. A
    related player on a DIFFERENT NFL team is not a handcuff or a target
    competitor; he is a former one.

    Falls back to surname + position because dossier prose and Sleeper
    disagree on given names: the research says "Kenneth Gainwell", the
    player table says "Kenny Gainwell", and full-name matching misses.
    """
    from battle_rhythm.draft_helper import player_hits, _norm_name
    hits, _h = player_hits(tbl, name)
    if not hits:
        surname = (str(name).split() or [""])[-1]
        key = _norm_name(surname)
        if len(key) >= 4:
            hits = [(p, m) for p, m in tbl.items()
                    if isinstance(m, dict)
                    and _norm_name((m.get("last_name") or "")) == key
                    and (not want_pos or m.get("position") == want_pos)]
    if not hits:
        return None, None, "unknown"
    same = [(p, m) for p, m in hits
            if want_team and m.get("team") == want_team]
    if same:
        return same[0][0], same[0][1], "same-team"
    return hits[0][0], hits[0][1], "moved"


def links(league_id, own, tbl, my_pids):
    """For each player I roster, who owns the players around him.

    Competition names come from the dossier store, which is where the
    'who is ahead of / behind him' knowledge already lives. No dossier
    for a player just means no links for him — not an error."""
    try:
        from battle_rhythm import dossier
    except Exception:
        return []
    rows = []
    for pid in my_pids:
        d = dossier.load(pid)
        if not d:
            continue
        me = tbl.get(pid) or {}
        for c in (d.get("stable") or {}).get("competition") or []:
            name = c.get("name")
            if not name:
                continue
            cp, cm, status = resolve_name(tbl, name, me.get("team"),
                                          me.get("position"))
            if status == "unknown":
                rows.append((me.get("full_name") or pid, me.get("position"),
                             name, None, "—", "not in player table"))
                continue
            owner = own.get(str(cp), (None, None))[1] or "FREE AGENT"
            if status == "moved":
                rows.append((me.get("full_name") or pid, me.get("position"),
                             cm.get("full_name") or name, cm.get("position"),
                             owner,
                             f"left {me.get('team')} (now {cm.get('team') or 'FA'})"))
                continue
            rel = ("handcuff" if cm.get("position") == me.get("position") == "RB"
                   else "target competitor"
                   if cm.get("position") in ("WR", "TE")
                   and me.get("position") in ("WR", "TE")
                   else "same team")
            rows.append((me.get("full_name") or pid, me.get("position"),
                         cm.get("full_name") or name, cm.get("position"),
                         owner, rel))
    return rows


def run(fragment, mode="rosters", query=None):
    from battle_rhythm.sleeper_client import players, load_leagues
    from battle_rhythm.draft_helper import player_hits
    from battle_rhythm.dynasty_value import resolve_league
    lid = resolve_league(fragment)
    tbl = players()
    own, _users = ownership(lid)
    me = next((l for l in load_leagues()["leagues"]
               if l["league_id"] == lid), {})
    my_uid = None
    from battle_rhythm.draft_helper import uid
    my_uid = uid()
    mine = [p for p, (oid, _n) in own.items() if str(oid) == str(my_uid)]

    if mode == "who":
        hits, _h = player_hits(tbl, query)
        if not hits:
            print(f"no player matching '{query}'")
            return
        for pid, m in hits[:6]:
            o = own.get(str(pid))
            tag = f"owned by {o[1]}" if o else "AVAILABLE"
            star = "  <- you" if o and str(o[0]) == str(my_uid) else ""
            print(f"  {m.get('full_name')} ({m.get('position')}, "
                  f"{m.get('team') or 'FA'}, age {m.get('age')})  {tag}{star}")
        return

    if mode == "links":
        rows = links(lid, own, tbl, mine)
        if not rows:
            print("no dossiers for your roster yet — run "
                  "'python dossier.py import <bundle>' first")
            return
        my_name = "dirtymurdock"
        for _p, (oid, nm) in own.items():
            if str(oid) == str(my_uid):
                my_name = nm
                break
        print(f"{me.get('name')} — roster links "
              f"({len(mine)} players you own)\n")
        print(f"{'your player':<22}{'':<3}{'related':<24}{'rel':<26}owner")
        live = [r for r in rows if r[5] in ("handcuff", "target competitor")]
        stale = [r for r in rows if r not in live]
        for a, apos, bname, bpos, owner, rel in live + stale:
            if rel not in ("handcuff", "target competitor"):
                flag = "  "          # not a live relationship, never flag it
            elif owner == "FREE AGENT":
                flag = "++"
            elif owner == my_name:
                flag = "=="          # you own both sides
            else:
                flag = "!!"
            print(f"{a[:21]:<22}{(apos or '?'):<3}{bname[:23]:<24}"
                  f"{rel[:25]:<26}{owner} {flag}")
        print(f"\n!! = a rival owns it   ++ = still free   "
              f"== = you own both sides")
        if stale:
            print("rows with 'left <team>' are former teammates — the "
                  "dossier competition list predates the move, and they "
                  "are NOT handcuffs or competitors any more")
        return

    bm = by_manager(own, tbl)
    print(f"{me.get('name')} — {len(own)} players owned across "
          f"{len(bm)} managers\n")
    for name in sorted(bm, key=lambda n: (n != "dirtymurdock", n)):
        star = "  (you)" if name == "dirtymurdock" else ""
        print(f"── {name}{star}  ({len(bm[name])})")
        for pos, full, team, age in bm[name]:
            print(f"     {pos:<4}{full:<26}{team:<4}{age or '?'}")
        print()


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    tbl = {"1": {"position": "RB", "full_name": "My Back", "last_name": "Back",
                 "team": "TB", "age": 23},
           "2": {"position": "RB", "full_name": "His Backup",
                 "last_name": "Backup", "team": "TB", "age": 27},
           "3": {"position": "WR", "full_name": "Free Guy",
                 "last_name": "Guy", "team": "GB", "age": 25},
           "4": {"position": "RB", "full_name": "Departed Mate",
                 "last_name": "Mate", "team": "WAS", "age": 27},
           "5": {"position": "RB", "full_name": "Kenny Gainwell",
                 "last_name": "Gainwell", "team": "TB", "age": 27}}
    own = {"1": ("me", "dirtymurdock"), "2": ("v", "MGR60"),
           "4": ("r", "MGR38"), "5": ("v", "MGR60")}
    bm = by_manager(own, tbl)
    check("groups by manager",
          set(bm) == {"dirtymurdock", "MGR60", "MGR38"})
    check("unowned player absent", all("Free Guy" not in [x[1] for x in v]
                                       for v in bm.values()))

    import types
    fake_doss = types.SimpleNamespace(
        load=lambda pid: ({"stable": {"competition": [
            {"name": "His Backup"},          # real, same team
            {"name": "Departed Mate"},       # in the table but MOVED
            {"name": "Kenneth Gainwell"},    # name mismatch vs "Kenny"
            {"name": "Nobody At All"}]}}     # genuinely unknown
            if pid == "1" else None))
    sys.modules["dossier"] = fake_doss

    def fake_hits(t, qq):
        return ([(p, m) for p, m in t.items()
                 if qq.lower() in (m.get("full_name") or "").lower()], "")

    fake_dh = types.SimpleNamespace(
        player_hits=fake_hits,
        _norm_name=lambda s: "".join(ch for ch in str(s or "").lower()
                                     if ch.isalnum()))
    real_dh = sys.modules.get("draft_helper")
    sys.modules["draft_helper"] = fake_dh
    try:
        rows = links("L", own, tbl, ["1"])
        by = {r[2]: r for r in rows}
        check("links found the same-team handcuff",
              by["His Backup"][5] == "handcuff")
        check("...and attributed the owner", by["His Backup"][4] == "MGR60")

        # THE FALSE RELATIONSHIP: Rachaad White is in the table and really
        # was Irving's backfield mate, but he plays for Washington now.
        # Reporting his owner as holding your handcuff is simply false.
        check("a competitor who CHANGED TEAMS is not a handcuff",
              by["Departed Mate"][5].startswith("left "))
        check("...and carries no rival flag",
              by["Departed Mate"][5] not in ("handcuff", "target competitor"))

        # NAME MISMATCH: dossier says "Kenneth", Sleeper says "Kenny"
        check("surname fallback bridges Kenneth -> Kenny Gainwell",
              "Kenny Gainwell" in by and by["Kenny Gainwell"][4] == "MGR60")

        check("a truly unknown name is reported, not invented",
              by["Nobody At All"][5] == "not in player table")
    finally:
        del sys.modules["dossier"]
        if real_dh is not None:
            sys.modules["draft_helper"] = real_dh
        else:
            del sys.modules["draft_helper"]
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        selftest() if a else sys.exit(__doc__)
    if "--who" in a:
        i = a.index("--who")
        run(a[0], "who", " ".join(a[i + 1:]))
    elif "--links" in a:
        run(a[0], "links")
    else:
        run(a[0], "rosters")
