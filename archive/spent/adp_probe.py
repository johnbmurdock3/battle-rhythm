"""
adp_probe.py — which market is each tool pricing this league off?

    python adp_probe.py                    # all five leagues, the summary
    python adp_probe.py lg05           # one league, with players
    python adp_probe.py lg05 "josh allen" "trevor lawrence"

WHY THIS EXISTS (8/13). The superflex/dynasty/keeper ADP-key branch is
written seven times across the toolkit, in two variants that disagree:

    variant A  gates on `dynasty` alone
               draft_helper:401, room_bias:117, keeper.py:198,
               dynasty_value:532
    variant B  gates on `dynasty and not keeper`, and falls back to the
               dynasty chain instead of nothing
               keeper.py:271, draft_review:152, lineup_value:248

draft_helper.board_data is variant A. It is the brain — the dashboard,
the board and the turn plan banner all read it. lineup_value is variant
B. Both Hybrids are dynasty-TYPED (settings.type == 2) and carry
"keeper": true in keepers.json, so the two land on different sides and
price the same league off different markets.

There is a second wrinkle underneath. draft_helper:396 computes

    keeper = settings.get("type") == 1

which is Sleeper's own keeper-league type, NOT the keepers.json flag.
Both Hybrids are type 2, so that variable is False there regardless, and
it is never used in the ADP decision anyway. dashboard.py:925 OR's the
keepers.json flag back in to correct it — but only after board_data has
already chosen the keys. The display was patched; the pricing was not.

This script does not fix anything. It prints what each variant chooses
and what that does to real ADPs, so the call can be made on numbers.

Needs the network on first run (it fills the ADP cache).
"""

import sys

import paths
from draft_helper import (DYNASTY_ADP_KEYS, REDRAFT_ADP_KEYS, _adp,
                          player_hits)
from league_rules import is_keeper_league
from sleeper_client import load_leagues, players, state

# The three quarterbacks HANDOFF's "QB at pick 8" case turns on, plus two
# skill players as a control. Survival at a pick is estimated from ADP, so
# if the board and the turn plan disagree about the market they disagree
# about who is still there at 8.
DEFAULT_PLAYERS = ["josh allen", "justin herbert", "dak prescott",
                   "trevor lawrence", "ashton jeanty", "amon-ra st brown"]


def variant_a(rp, dynasty):
    """draft_helper.board_data, room_bias, keeper.show_keepers, dynasty_value."""
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    if dynasty:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if sflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
        fb = ()
    return keys, fb


def variant_b(rp, dynasty, keeper):
    """lineup_value, draft_review, keeper.adjusted_board."""
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    if dynasty and not keeper:
        keys = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
                if sflex else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
    else:
        keys = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
        fb = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS)
              if sflex else DYNASTY_ADP_KEYS) if dynasty else ()
    return keys, fb


def unified_summary(leagues):
    """One key per league, from the function every path now calls.

    The A/B comparison below is kept for the pre-fix case only. Leaving it
    as the headline after wire_all.py ran would print "*** NO ***" for two
    leagues that agree — a true number under a false label, which is the
    failure ROADMAP names at the bottom and the one this whole thread kept
    tripping over.
    """
    from draft_helper import adp_keys_for
    print(f"\n{'league':22s} {'type':9s} {'keeper':7s} {'sflex':6s} "
          f"{'market this room drafts in':28s} {'fallback'}")
    print("-" * 100)
    for lg in leagues:
        rp = lg.get("roster_positions") or []
        dyn = (lg.get("settings") or {}).get("type") == 2
        kp = is_keeper_league(lg["league_id"])
        sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
        k, fb = adp_keys_for(rp, dyn, kp)
        print(f"{(lg.get('name') or '?')[:21]:22s} "
              f"{'dynasty' if dyn else 'redraft':9s} "
              f"{str(kp):7s} {str(sflex):6s} {k[0]:28s} "
              f"{(fb[0] if fb else '—')}")
    print("\nOne definition (draft_helper.adp_keys_for), so there is nothing "
          "to disagree.")


def summary(leagues):
    print(f"\n{'league':22s} {'type':9s} {'keeper':7s} {'sflex':6s} "
          f"{'board (A)':22s} {'turn plan (B)':22s}  agree?")
    print("-" * 100)
    split = []
    for lg in leagues:
        lid = lg["league_id"]
        rp = lg.get("roster_positions") or []
        dyn = (lg.get("settings") or {}).get("type") == 2
        kp = is_keeper_league(lid)
        sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
        a, _ = variant_a(rp, dyn)
        b, _ = variant_b(rp, dyn, kp)
        same = a == b
        if not same:
            split.append(lg)
        print(f"{(lg.get('name') or '?')[:21]:22s} "
              f"{'dynasty' if dyn else 'redraft':9s} "
              f"{str(kp):7s} {str(sflex):6s} "
              f"{a[0]:22s} {b[0]:22s}  "
              f"{'yes' if same else '*** NO ***'}")
    return split


def compare_players(lg, queries, tbl, season):
    lid = lg["league_id"]
    rp = lg.get("roster_positions") or []
    dyn = (lg.get("settings") or {}).get("type") == 2
    kp = is_keeper_league(lid)
    ka, fa = variant_a(rp, dyn)
    kb, fb = variant_b(rp, dyn, kp)

    print(f"\n── {lg.get('name')}   dynasty={dyn}  keeper={kp}")
    print(f"   board / dashboard / turn-plan banner reads : {ka[0]}")
    print(f"   lineup_value / draft_review reads          : {kb[0]}")
    if ka == kb:
        print("   these agree — nothing to see in this league")
        return
    print(f"\n   {'player':28s} {'board (A)':>11s} {'turn plan (B)':>14s} "
          f"{'delta':>8s}")
    print("   " + "-" * 65)
    for q in queries:
        hits, _hint = player_hits(tbl, q)
        if not hits:
            print(f"   {q[:27]:28s} {'not found':>11s}")
            continue
        pid, m = hits[0]
        nm = (m.get("full_name")
              or f"{m.get('first_name','')} {m.get('last_name','')}".strip()
              or str(pid))
        if m.get("position"):
            nm = f"{nm} ({m['position']})"
        va, xa = _adp(pid, season, ka, fa)
        vb, xb = _adp(pid, season, kb, fb)
        d = ("" if va is None or vb is None else f"{vb - va:+.1f}")
        sa = ("—" if va is None else f"{va:.1f}" + ("" if xa else "~"))
        sb = ("—" if vb is None else f"{vb:.1f}" + ("" if xb else "~"))
        print(f"   {nm[:27]:28s} {sa:>11s} {sb:>14s} {d:>8s}")
    print("\n   ~ = not an exact quote from that market. _adp fell through to "
          "the fallback\n     chain, or superflex_adp interpolated it. A "
          "column of round integers is\n     what interpolation looks like.")
    print("\n   A positive delta means the turn plan thinks he goes LATER "
          "than the board does,\n   so the board is more pessimistic about "
          "him surviving to your pick.")
    coverage(season, ka, kb)


def coverage(season, ka, kb):
    """How dense is each market actually?

    The whole question is which market to trust. A market that is mostly
    interpolated is not a better answer just because it is the more
    appropriate one in principle. superflex_adp.py exists precisely
    because the weekly feed carries no adp_2qb at all — it fetches the
    per-player endpoint and INTERPOLATES THE GAPS.

    Caveat on the numbers below: _adp fills these books lazily, so a book
    reflects what has been asked for, not what the market covers. Read
    the exact-rate, not the row count.
    """
    import json as _json
    from draft_helper import CACHE
    print(f"\n   market coverage (cached books, {season}):")
    print(f"   {'chain':24s} {'rows':>7s} {'exact':>7s} {'exact %':>9s}")
    print("   " + "-" * 50)
    for label, keys in (("board (A)", ka), ("turn plan (B)", kb)):
        p = CACHE / f"adp_{season}_{keys[0]}.json"
        if not p.exists():
            print(f"   {keys[0]:24s} {'(no cache yet)':>25s}")
            continue
        book = _json.loads(p.read_text(encoding="utf-8"))
        rows = [v for v in book.values() if isinstance(v, list)]
        n = len(rows)
        ex = sum(1 for v in rows if len(v) > 1 and v[1])
        pct = f"{100.0 * ex / n:.0f}%" if n else "—"
        print(f"   {keys[0]:24s} {n:7d} {ex:7d} {pct:>9s}   <- {label}")


def code_paths(rp, dynasty, keeper):
    """The ADP chain each code path actually uses, as of 8/13 evening.

    board_data got the keeper fix (draft_helper:489, `if dynasty and
    keeper: dynasty = False`). find / rookies / recap did not — they each
    carry their own one-line branch that knows about neither the keeper
    flag NOR superflex, so they never prepend the 2QB key at all.
    """
    sflex = "SUPER_FLEX" in rp or rp.count("QB") >= 2
    out = []

    # After wire_all.py all four draft_helper sites plus the other modules
    # call one function. If it is present, that IS the answer and the rows
    # below are history.
    try:
        from draft_helper import adp_keys_for
        k, fb = adp_keys_for(rp, dynasty, keeper)
        out.append(("ALL PATHS (adp_keys_for)", "draft_helper", k, fb))
        return out
    except ImportError:
        pass

    # 1. board_data — keeper-aware, superflex-aware
    d = dynasty and not keeper
    if d:
        k = ((("adp_dynasty_2qb",) + DYNASTY_ADP_KEYS) if sflex
             else DYNASTY_ADP_KEYS)
        fb = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
    else:
        k = (("adp_2qb",) + REDRAFT_ADP_KEYS) if sflex else REDRAFT_ADP_KEYS
        fb = ()
    out.append(("board / dashboard / turn banner", "board_data:505", k, fb))

    # 2. find / rookies / recap — neither
    k2 = DYNASTY_ADP_KEYS if dynasty else REDRAFT_ADP_KEYS
    fb2 = REDRAFT_ADP_KEYS if dynasty else ()
    out.append(("find / rookies / recap", "draft_helper:783,865,922", k2, fb2))

    # 3. lineup_value / draft_review / keeper --board
    k3, fb3 = variant_b(rp, dynasty, keeper)
    out.append(("lineup_value / draft_review", "lineup_value:248", k3, fb3))
    return out


def by_code_path(lg, queries, tbl, season):
    rp = lg.get("roster_positions") or []
    dyn = (lg.get("settings") or {}).get("type") == 2
    kp = is_keeper_league(lg["league_id"])
    rows = code_paths(rp, dyn, kp)

    print(f"\n{'=' * 78}")
    print(f"ONE PLAYER, EVERY CODE PATH — {lg.get('name')}")
    print(f"{'=' * 78}")
    for label, where, k, _fb in rows:
        print(f"  {label:32s} {where:26s} {k[0]}")

    # the real superflex market, if superflex_adp has built its cache
    real = {}
    try:
        import json as _json
        from superflex_adp import cache_path
        cp = cache_path(season)
        if cp.exists():
            real = _json.loads(cp.read_text(encoding="utf-8") or "{}")
    except Exception:
        pass
    print(f"\n  superflex_adp cache: "
          + (f"{len(real)} real adp_2qb prices" if real
             else "EMPTY — run superflex_adp.py"))

    hdr = f"\n   {'player':26s}" + "".join(f"{r[0].split(' /')[0]:>16s}"
                                           for r in rows)
    print(hdr + f"{'real 2QB':>12s}")
    print("   " + "-" * (26 + 16 * len(rows) + 12))
    for q in queries:
        hits, _ = player_hits(tbl, q)
        if not hits:
            print(f"   {q[:25]:26s} {'not found':>16s}")
            continue
        pid, m = hits[0]
        nm = (m.get("full_name") or str(pid))
        if m.get("position"):
            nm = f"{nm} ({m['position']})"
        cells = ""
        for _label, _w, k, fb in rows:
            v, ex = _adp(pid, season, k, fb)
            cells += f"{('—' if v is None else f'{v:.1f}' + ('' if ex else '~')):>16s}"
        rv = real.get(str(pid))
        cells += f"{('—' if rv is None else f'{float(rv):.1f}'):>12s}"
        print(f"   {nm[:25]:26s}{cells}")
    print("\n   Every column is the SAME player in the SAME league. Where they "
          "disagree,\n   a tool is pricing survival off a market this room "
          "does not draft in.")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    leagues = load_leagues().get("leagues", [])
    if not leagues:
        sys.exit("no leagues cached — run: python sleeper_client.py discover")

    known = {str(m.get("id")) for m in paths.leagues().values()}
    live = {str(l["league_id"]) for l in leagues}
    if live - known:
        print("\n*** leagues/_index.json does not know about these ***")
        for l in leagues:
            if str(l["league_id"]) not in known:
                rp = l.get("roster_positions") or []
                idp = sorted({s for s in rp if s in ("DL", "LB", "DB",
                                                     "IDP_FLEX")})
                # total_teams, not total_rosters: sleeper_client:159
                # renames it when it caches the league.
                print(f"    {l['league_id']}  {l.get('name')!r}  "
                      f"{l.get('total_teams')} teams  {l.get('status')}"
                      + (f"  IDP slots: {', '.join(idp)}" if idp else ""))
        print("    paths.py --selftest compares _index.json against "
              "mcp_server.LEAGUE_IDS.\n    Neither is the API. That is how "
              "this went unnoticed.")
    if known - live:
        print("\n*** _index.json has ids that are not in your league list: "
              f"{', '.join(sorted(known - live))} ***")

    try:
        from draft_helper import adp_keys_for  # noqa: F401
        unified = True
    except ImportError:
        unified = False

    if unified:
        unified_summary(leagues)
        split = []
    else:
        split = summary(leagues)
    if not split and not unified:
        print("\nEvery league lands on the same keys under the two variants "
              "-- but that\n is not the whole story since 8/13: the keeper fix "
              "landed in board_data\n only, and find / rookies / recap carry "
              "their own branch. Pass a league\n to see every code path side "
              "by side.")

    if split:
        print(f"\n{len(split)} league(s) where the two tools disagree.")

    if not args:
        # split is empty on the unified path, so do not index it — name a
        # league from the index instead.
        example = (paths.slug_for(split[0]["league_id"]) if split
                   else next(iter(paths.leagues()), "lg05"))
        print("\nRun with a league to see the per-player numbers, e.g.")
        print(f"    python adp_probe.py {example}")
        return 0

    lid = paths.id_for(args[0]) or args[0]
    lg = next((x for x in leagues if x["league_id"] == str(lid)), None)
    if lg is None:
        sys.exit(f"unknown league '{args[0]}'. Known: "
                 f"{', '.join(paths.leagues())}")
    season = lg.get("season") or state().get("season")
    tbl = players()
    by_code_path(lg, args[1:] or DEFAULT_PLAYERS, tbl, season)
    if not unified:
        compare_players(lg, args[1:] or DEFAULT_PLAYERS, tbl, season)
    return 0


if __name__ == "__main__":
    sys.exit(main())
