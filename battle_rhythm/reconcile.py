"""
reconcile.py — cross-check dossier competition entries against the
Sleeper player table, and patch what the research left unconfirmed.

Research agents write competition lists from prose. Prose goes out of
date and prose hedges: the Bucky Irving dossier honestly recorded
Rachaad White as "2026 free agent focus / uncertain roster status ...
exact 2026 roster status not confirmed." The player table knows the
answer (WAS). This reconciles the two so the store improves permanently
instead of being corrected at render time on every read.

    python reconcile.py                 # report only, changes nothing
    python reconcile.py --apply         # write the resolved fields back
    python reconcile.py --selftest      # offline

For each competition entry it resolves the name against the player
table and records:
    resolved_id, resolved_team, resolved_pos, same_team (bool)
Nothing is deleted. A competitor who has left keeps his entry with
same_team false, because "he used to be the handcuff and now isn't" is
information, not noise.

Trust order: the player table wins on CURRENT TEAM, always. It is a
structured field refreshed daily; the note is one researcher's reading
of an article. The note wins on everything the table has no opinion
about (role, contract, why it matters).
"""

import json
import sys


UNSURE = ("not confirmed", "uncertain", "unclear", "unverified",
          "could not verify", "no confirmed", "implying", "needs verification")


def reconcile_doc(doc, tbl, resolve):
    """Returns (changes, entries). Pure — does not write."""
    changes = []
    subject_team = None
    for t in sorted((doc.get("stable") or {}).get("team_history") or [],
                    key=lambda x: -(x.get("season") or 0)):
        if t.get("team"):
            subject_team = t["team"]
            break
    subject_team = subject_team or (doc.get("team") or None)

    entries = (doc.get("stable") or {}).get("competition") or []
    for c in entries:
        name = c.get("name")
        if not name:
            continue
        pid, meta, status = resolve(name, subject_team, None)
        before = (c.get("resolved_team"), c.get("same_team"))
        if status == "unknown":
            c["resolved_id"] = None
            c["resolved_team"] = None
            c["same_team"] = None
            note = "unresolved"
        else:
            c["resolved_id"] = pid
            c["resolved_team"] = meta.get("team")
            c["resolved_pos"] = meta.get("position")
            c["same_team"] = bool(subject_team
                                  and meta.get("team") == subject_team)
            if c.get("age") in (None, "") and meta.get("age"):
                c["age"] = meta.get("age")
            note = ("same team" if c["same_team"]
                    else f"now {meta.get('team') or 'FA'}")
        hedged = any(k in str(c.get("status", "") + " "
                              + str(c.get("note", ""))).lower()
                     for k in UNSURE)
        if before != (c.get("resolved_team"), c.get("same_team")):
            changes.append({"player": doc.get("name"),
                            "subject_team": subject_team,
                            "competitor": name, "outcome": note,
                            "was_hedged": hedged})
    return changes, entries


def run(apply=False):
    from battle_rhythm import dossier
    from battle_rhythm.sleeper_client import players
    from battle_rhythm.roster_map import resolve_name
    tbl = players()

    def resolve(name, team, pos):
        return resolve_name(tbl, name, team, pos)

    docs = dossier.all_docs()
    all_changes, touched = [], 0
    for d in docs:
        ch, _e = reconcile_doc(d, tbl, resolve)
        if ch:
            all_changes.extend(ch)
            touched += 1
            if apply:
                dossier.save(d)

    moved = [c for c in all_changes if c["outcome"].startswith("now")]
    unres = [c for c in all_changes if c["outcome"] == "unresolved"]
    hedged_moved = [c for c in moved if c["was_hedged"]]
    print(f"{len(docs)} dossiers · {touched} with competition entries "
          f"· {len(all_changes)} entries resolved")
    print(f"  same team (real handcuff/competitor): "
          f"{len(all_changes) - len(moved) - len(unres)}")
    print(f"  NO LONGER teammates: {len(moved)}"
          f"   (of which the research had hedged: {len(hedged_moved)})")
    print(f"  unresolvable names: {len(unres)}")

    print("\nNO LONGER TEAMMATES — these are not handcuffs or target "
          "competitors any more:")
    seen = set()
    for c in sorted(moved, key=lambda x: x["player"] or ""):
        k = (c["player"], c["competitor"])
        if k in seen:
            continue
        seen.add(k)
        flag = "  (research had flagged this as unconfirmed)" \
            if c["was_hedged"] else ""
        print(f"  {str(c['player'])[:22]:<24}{c['competitor'][:22]:<24}"
              f"{str(c['subject_team'] or '?'):<4}-> {c['outcome']}{flag}")

    if unres:
        print(f"\nUNRESOLVED NAMES ({len(unres)}) — not in the player "
              "table under any spelling:")
        for c in unres[:20]:
            print(f"  {str(c['player'])[:22]:<24}{c['competitor'][:30]}")

    print("\n" + ("APPLIED — dossiers rewritten with resolved fields"
                  if apply else
                  "REPORT ONLY — rerun with --apply to write these back"))
    return all_changes


def selftest():
    ok = True

    def check(n, c):
        nonlocal ok
        print(f"  {'ok' if c else 'XX'}  {n}")
        ok = ok and c

    tbl = {"w": {"full_name": "Rachaad White", "team": "WAS",
                 "position": "RB", "age": 27},
           "g": {"full_name": "Kenny Gainwell", "team": "TB",
                 "position": "RB", "age": 27}}

    def resolve(name, team, pos):
        for pid, m in tbl.items():
            if name.split()[-1].lower() in m["full_name"].lower():
                return pid, m, ("same-team" if m["team"] == team else "moved")
        return None, None, "unknown"

    doc = {"name": "Bucky Irving",
           "stable": {"team_history": [{"season": 2025, "team": "TB"},
                                       {"season": 2024, "team": "TB"}],
                      "competition": [
                          {"name": "Kenneth Gainwell",
                           "status": "signed by TB in free agency"},
                          {"name": "Rachaad White",
                           "status": "uncertain roster status",
                           "note": "exact 2026 roster status not confirmed"},
                          {"name": "Ghost Player", "status": "?"}]}}
    ch, entries = reconcile_doc(doc, tbl, resolve)
    by = {e["name"]: e for e in entries}
    check("subject team read from newest season",
          ch[0]["subject_team"] == "TB")
    check("Kenneth -> Kenny resolves and stays a teammate",
          by["Kenneth Gainwell"]["same_team"] is True)
    check("White resolves to WAS and is NOT a teammate",
          by["Rachaad White"]["same_team"] is False
          and by["Rachaad White"]["resolved_team"] == "WAS")
    check("the hedged entry is reported as hedged",
          any(c["was_hedged"] and c["competitor"] == "Rachaad White"
              for c in ch))
    check("departed competitor is KEPT, not deleted",
          "Rachaad White" in by)
    check("unknown name marked unresolved",
          by["Ghost Player"]["same_team"] is None)
    check("missing age backfilled from the table",
          by["Kenny Gainwell" if "Kenny Gainwell" in by
             else "Kenneth Gainwell"]["age"] == 27)
    # rerun must be idempotent
    ch2, _ = reconcile_doc(doc, tbl, resolve)
    check("second run reports no further changes", ch2 == [])
    print("\nselftest", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        selftest()
    run(apply="--apply" in a)
