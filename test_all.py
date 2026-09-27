"""
Offline regression suite — no network. Run before trusting any change:

  python test_all.py

Covers: the verified scoring engine (ground truth captured live from Sleeper),
projection normalization, availability-ratio math, ADP fallback chain, snake
draft math, injury tags, keeper constraint logic, weekly lineup/waiver/trade
logic, and a board_data smoke test with the turn plan. All network functions
are stubbed; ground-truth fixtures live in fixtures/.
"""

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
# The modules moved into battle_rhythm/ on 9/2; fixtures did not.
PKG = HERE / "battle_rhythm"
sys.path.insert(0, str(HERE))

PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"  FAIL  {name}: {e}")


# ---------------------------------------------------------------- scoring

def t_scoring_ground_truth():
    from battle_rhythm.sleeper_client import score
    data = json.loads((HERE / "fixtures" / "verify_cases.json").read_text(encoding="utf-8"))
    for case in data["cases"]:
        got = score(case["stats"], data[case["scoring"]])
        assert abs(got - case["expected"]) < 0.005, (case["label"], got)


def t_scoring_diff():
    from battle_rhythm.sleeper_client import scoring_diff
    lg = json.loads((HERE / "fixtures" / "leagues_2026_scoring.json").read_text(encoding="utf-8"))["leagues"]
    d = scoring_diff(lg)
    assert d["rec"] == [0.0, 0.5, 0.0, 0.5, 1.0]
    assert "pass_yd" not in d  # identical everywhere -> excluded


# ------------------------------------------------------------- projections

def _fresh_dh():
    import importlib
    from battle_rhythm import draft_helper as dh
    importlib.reload(dh)
    dh.CACHE = pathlib.Path(tempfile.mkdtemp())
    return dh


def t_normalize_shapes():
    dh = _fresh_dh()
    assert dh._normalize({"1": {"a": 1}, "2": {"stats": {"b": 2}}}) == \
        {"1": {"a": 1}, "2": {"b": 2}}
    assert dh._normalize([{"player_id": "3", "stats": {"c": 3}}]) == {"3": {"c": 3}}


def t_availability_ratio():
    """Per WEEK, not per total — the bye is not availability.

    This test used to assert 130/170, dividing a full-season aggregate by
    a seventeen-week sum, which is the bug it was supposed to guard. Week
    11 is A's bye and the old arithmetic charged him for it.
    """
    dh = _fresh_dh()
    wk = {"A": {"x": 10, "pts_ppr": 10.0}, "B": {"x": 10, "pts_ppr": 10.0}}
    dh.weekly_projections = lambda s, w: wk if w != 11 else {}
    dh._get = lambda url, retries=3: ([{"player_id": "A", "stats": {"pts_ppr": 130.0}}]
                                      if "position[]=QB" in url else [])
    r = dh.availability_ratios("2026")
    # 17 weeks at 10 = 170. Per week: (130/18) / (170/17) = 0.7222.
    assert abs(r["A"] - (130 / 18) / (170 / 17)) < 1e-9, r["A"]
    assert "B" not in r                      # no aggregate -> no ratio
    t = dh.season_projection_totals("2026", {"x": 1})
    assert abs(t["A"] - round(170 * r["A"], 1)) < 0.05
    assert t["B"] == 170.0                   # no aggregate -> no haircut


def t_a_full_season_is_not_a_bonus():
    """The live case, 9/3: Brian Thomas at 1.062, clamped to 1.05.

    A receiver missing exactly one week — his bye — whose aggregate is a
    full-season number will divide out to 18/17 = 1.059 under the old
    formula. He is not 6% MORE available than available. He is 1.0, and a
    field whose entire job is taking points away must never add them.
    """
    dh = _fresh_dh()
    wk = {"BTJ": {"pts_ppr": 10.0}}
    dh.weekly_projections = lambda s, w: wk if w != 7 else {}   # bye week 7
    # aggregate = 18 weeks' worth: a player the feed expects to be fine
    dh._get = lambda url, retries=3: ([{"player_id": "BTJ",
                                        "stats": {"pts_ppr": 180.0}}]
                                      if "position[]=QB" in url else [])
    r = dh.availability_ratios("2026")
    assert r["BTJ"] == 1.0, f"a bye became a bonus again: {r['BTJ']}"

    # ---- and a genuinely hurt player still takes his haircut
    dh2 = _fresh_dh()
    dh2.weekly_projections = lambda s, w: {"HURT": {"pts_ppr": 10.0}} if w != 7 else {}
    dh2._get = lambda url, retries=3: ([{"player_id": "HURT",
                                         "stats": {"pts_ppr": 144.0}}]
                                       if "position[]=QB" in url else [])
    # (144/18) / (170/17) = 0.8 — a real 20% discount, not masked by the bye
    assert abs(dh2.availability_ratios("2026")["HURT"] - 0.8) < 1e-9

    # ---- one week of data is not a measurement, it is broken input
    dh3 = _fresh_dh()
    dh3.weekly_projections = lambda s, w: {"THIN": {"pts_ppr": 10.0}} if w == 1 else {}
    dh3._get = lambda url, retries=3: ([{"player_id": "THIN",
                                         "stats": {"pts_ppr": 180.0}}]
                                       if "position[]=QB" in url else [])
    diag = {}
    r3 = dh3.availability_ratios("2026", _diag=diag)
    assert "THIN" not in r3, "a ratio of 18.06 must not be clamped into 1.05"
    assert diag["thin"] == ["THIN"], "and it must be reportable, not silent"


def t_availability_clamp():
    dh = _fresh_dh()
    dh.weekly_projections = lambda s, w: {"A": {"pts_ppr": 10.0}}
    dh._get = lambda url, retries=3: ([{"player_id": "A", "stats": {"pts_ppr": 20.0}}]
                                      if "position[]=QB" in url else [])
    assert dh.availability_ratios("2026")["A"] == 0.5  # floor clamp


def t_adp_fallback_chain():
    dh = _fresh_dh()
    dh.weekly_projections = lambda s, w: {"r1": {"adp_dd_ppr": 31.0}}
    dh._get = lambda url, retries=3: ({"stats": {"adp_dynasty_ppr": 12.5}}
                                      if "/player/r1?" in url
                                      else (_ for _ in ()).throw(Exception("403")))
    val, exact = dh._adp("r1", "2026", dh.DYNASTY_ADP_KEYS, dh.REDRAFT_ADP_KEYS)
    assert (val, exact) == (12.5, True)          # exact dynasty via per-player
    val, exact = dh._adp("r2", "2026", dh.DYNASTY_ADP_KEYS, dh.REDRAFT_ADP_KEYS)
    assert val is None                            # no bulk, per-player 403 -> None


def t_stale_adp_cache_migrates():
    dh = _fresh_dh()
    (dh.CACHE / "adp_2026_adp_dynasty_ppr.json").write_text(json.dumps({"r1": 31.0}))
    dh.weekly_projections = lambda s, w: {}
    dh._get = lambda url, retries=3: {"stats": {"adp_dynasty_ppr": 12.5}}
    assert dh._adp("r1", "2026", dh.DYNASTY_ADP_KEYS)[0] == 12.5


# ------------------------------------------------------------------ draft

def t_snake_math():
    dh = _fresh_dh()
    dh.my_slot = lambda d: 9
    draft = {"settings": {"rounds": 22, "teams": 12}, "draft_order": {"u": 9}}
    assert dh.my_next_pick(draft, 42) == (57, 5)
    assert dh.my_next_pick(draft, 57) == (64, 6)
    assert dh.my_next_picks(draft, 63, 3) == [(64, 6), (81, 7), (88, 8)]
    # a plain snake must be unchanged by the reversal work
    assert dh.my_next_pick({**draft, "settings": {**draft["settings"],
                                                  "reversal_round": 0}}, 42) == (57, 5)


def t_snake_math_reversal():
    """my_next_pick walks a live board forward, so it has to know the
    format too. Under a 3-reversal from slot 9 the round-5 pick moves."""
    dh = _fresh_dh()
    dh.my_slot = lambda d: 9
    plain = {"settings": {"rounds": 22, "teams": 12}, "draft_order": {"u": 9}}
    rev = {"settings": {"rounds": 22, "teams": 12, "reversal_round": 3},
           "draft_order": {"u": 9}}
    from battle_rhythm.sleeper_client import slot_picks
    p_plain = slot_picks(9, 22, 12, 0)
    p_rev = slot_picks(9, 22, 12, 3)
    assert p_plain[:2] == p_rev[:2] and p_plain[2:] != p_rev[2:]
    # walking from 0 must reproduce the same list the closed form gives
    walked, n = [], 0
    while True:
        nxt = dh.my_next_pick(rev, n)
        if not nxt:
            break
        walked.append(nxt[0]); n = nxt[0]
    assert walked == p_rev, (walked[:6], p_rev[:6])
    walked2, n = [], 0
    while True:
        nxt = dh.my_next_pick(plain, n)
        if not nxt:
            break
        walked2.append(nxt[0]); n = nxt[0]
    assert walked2 == p_plain


def t_injury_tags():
    dh = _fresh_dh()
    assert dh.injury_tag({"injury_status": "Questionable",
                          "injury_body_part": "Groin"}) == "Q-groin"
    assert dh.injury_tag({"injury_status": "IR", "injury_body_part": "Knee"}) == "IR-knee"
    assert dh.injury_tag({"injury_status": "Out"}) == "OUT"
    assert dh.injury_tag({}) == ""


def t_board_data_turn_plan():
    dh = _fresh_dh()
    tbl = {"et": {"position": "RB", "age": 27, "full_name": "Urgent RB"},
           "sw": {"position": "RB", "age": 27, "full_name": "Waiting RB"},
           "bu": {"position": "WR", "age": 22, "full_name": "Cheap WR",
                  "injury_status": "Questionable", "injury_body_part": "Groin"},
           "z1": {"position": "RB", "age": 25, "full_name": "Depth RB"},
           "z2": {"position": "WR", "age": 25, "full_name": "Depth WR"}}
    for v in tbl.values():
        v.update(team="X")
    lg = {"name": "T", "league_id": "L", "season": "2026",
          "scoring_settings": {"x": 1}, "total_rosters": 12, "draft_id": "d",
          "roster_positions": ["QB", "RB", "RB", "WR", "BN"], "settings": {"type": 2}}
    draft = {"settings": {"rounds": 22, "teams": 12}, "draft_order": {"me": 9},
             "status": "drafting"}
    picks = [{"player_id": f"g{i}", "picked_by": "x"} for i in range(63)]
    dh.league_draft = lambda lid: (lg, draft, picks)
    dh.state = lambda: {"season": "2026"}
    dh.players = lambda force=False: tbl
    dh.season_projection_totals = lambda s, sc: {"et": 205, "sw": 205.4, "bu": 218,
                                                 "z1": 50, "z2": 50}
    dh.get = lambda path: [] if "rosters" in path else {"user_id": "me"}
    dh._uid_cache[0] = "me"
    dh._adp = lambda pid, s, k, f=(): {"et": (67.4, True), "sw": (85.7, True),
                                       "bu": (46.6, True), "z1": (150.0, True),
                                       "z2": (150.0, True)}[pid]
    dh.weekly_projections = lambda s, w: {}
    dh.my_slot = lambda d: 9
    d = dh.board_data("L")
    assert d["turn"]["picks"] == (64, 81)
    # sw (adp 85.7) survives to 81; urgent picks now, survivor banked for next
    assert d["turn"]["next"]["pid"] == "sw"
    assert d["turn"]["now"]["pid"] in ("et", "bu")
    by_pid = {r["pid"]: r for r in d["rows"]}
    assert by_pid["bu"]["inj"] == "Q-groin"



def t_turn_plan_pre_draft_skips_the_unreachable():
    """Pre-draft, "now:" named a player the market takes before your pick.

    Real output, LG04, 9/2: slot 10, zero picks made, banner read
    "now: Jahmyr Gibbs" -- ADP 1.0, nine picks ahead of the user's first.
    The board underneath was correct. Only the sentence was wrong, which
    is this repo's most expensive defect class and the one tests keep
    missing because the arithmetic is fine.

    The rule is not "adp below your pick." Mid-draft a still-available
    player priced well above your pick has been passed over and IS the
    value; the second half of this test pins that down so the fix cannot
    be simplified into a bug.
    """
    dh = _fresh_dh()
    tbl = {"elite": {"position": "RB", "age": 24, "full_name": "Elite RB"},
           "reach": {"position": "RB", "age": 26, "full_name": "Reachable RB"},
           "late":  {"position": "WR", "age": 25, "full_name": "Late WR"}}
    for v in tbl.values():
        v.update(team="X")
    lg = {"name": "T", "league_id": "L", "season": "2026",
          "scoring_settings": {"x": 1}, "total_rosters": 12, "draft_id": "d",
          "roster_positions": ["QB", "RB", "RB", "WR", "BN"], "settings": {"type": 0}}
    draft = {"settings": {"rounds": 15, "teams": 12}, "draft_order": {"me": 10},
             "status": "pre_draft"}
    dh.state = lambda: {"season": "2026"}
    dh.players = lambda force=False: tbl
    dh.get = lambda path: [] if "rosters" in path else {"user_id": "me"}
    dh._uid_cache[0] = "me"
    dh.weekly_projections = lambda s, w: {}
    dh.my_slot = lambda d: 10
    # elite is the best player and is gone by pick 10; reach is takeable.
    dh.season_projection_totals = lambda s, sc: {"elite": 300, "reach": 240,
                                                 "late": 200}
    dh._adp = lambda pid, s, k, f=(): {"elite": (1.0, True), "reach": (11.0, True),
                                       "late": (70.0, True)}[pid]

    dh.league_draft = lambda lid: (lg, draft, [])
    d = dh.board_data("L")
    t = d["turn"]
    assert t["picks"][0] == 10, t["picks"]
    assert t["now"]["pid"] != "elite", "named a player the market takes at 1.0"
    assert t["now"]["pid"] == "reach"
    assert "elite" in [c["pid"] for c in t["falling"]], "and lost him entirely"

    # late is priced at 70 so a survivor exists for the "next" slot; with
    # none, board_data declines to build a turn plan at all.
    # ---- mid-draft: the same ADP, but he has already been passed over.
    # 40 picks are in and elite is still on the board. He is not a wish
    # now, he is the steal, and he must come back into the plan.
    picks40 = [{"player_id": f"g{i}", "picked_by": "x"} for i in range(40)]
    dh.league_draft = lambda lid: (lg, draft | {"status": "drafting"}, picks40)
    d2 = dh.board_data("L")
    assert d2["turn"]["now"]["pid"] == "elite", "a faller is the value, not a wish"



def t_an_edge_rusher_reaches_the_idp_board():
    """Sleeper says DE, the league says DL, and 503 defenders vanished.

    Real, 9/7, two days before the IDP draft. `board lg06 --pos DL` ran 11
    deep and `find` answered "no player matching" for Myles Garrett, Nick
    Bosa, Maxx Crosby, Danielle Hunter, Brian Burns and Jeffery Simmons.
    None of them was mispriced. None of them was in the pool.

    The pool filter compared Sleeper's `position` -- the real NFL position,
    DE -- against the league's roster slots after those slots had been run
    through SLOT_ALIAS. The map existed and was correct, and was applied to
    one side of the comparison. `fantasy_positions` carried ['DL'] the whole
    time. Measured on the live table: 314 of 458 linemen dropped, and a
    draft card built on "ten linemen above replacement for ten teams".

    Two halves, because the fix has to widen the IDP pool WITHOUT touching
    leagues that have already drafted. The second half is not decoration: a
    first version admitted fullbacks to RB and moved a settled league's pool
    from 125 to 129.
    """
    dh = _fresh_dh()
    tbl = {
        "edge": {"position": "DE", "fantasy_positions": ["DL"], "age": 27,
                 "full_name": "Edge Rusher"},
        "lineman": {"position": "DL", "fantasy_positions": ["DL"], "age": 26,
                    "full_name": "Plain Lineman"},
        "corner": {"position": "CB", "fantasy_positions": ["DB"], "age": 25,
                   "full_name": "Some Corner"},
        "fullback": {"position": "FB", "fantasy_positions": ["RB"], "age": 28,
                     "full_name": "A Fullback"},
        "back": {"position": "RB", "fantasy_positions": ["RB"], "age": 24,
                 "full_name": "Plain Back"},
    }
    for v in tbl.values():
        v.update(team="X")
    dh.state = lambda: {"season": "2026"}
    dh.players = lambda force=False: tbl
    dh.get = lambda path: [] if "rosters" in path else {"user_id": "me"}
    dh._uid_cache[0] = "me"
    dh.weekly_projections = lambda s, w: {}
    dh._adp = lambda pid, s, k, f=(): (None, True)
    dh.season_projection_totals = lambda s, sc: {
        "edge": 200.0, "lineman": 180.0, "corner": 170.0,
        "fullback": 90.0, "back": 220.0}

    idp = {"name": "IDP", "league_id": "L", "season": "2026",
           "scoring_settings": {"x": 1}, "total_rosters": 10, "draft_id": "d",
           "roster_positions": ["RB", "DL", "DB", "BN"], "settings": {"type": 0}}
    draft = {"settings": {"rounds": 16, "teams": 10}, "draft_order": {},
             "status": "pre_draft"}
    dh.league_draft = lambda lid: (idp, draft, [])
    pool = {r["pid"]: r["meta"]["position"] for r in dh.board_data("L")["rows"]}
    assert "edge" in pool, "a DE eligible at DL never reached the DL board"
    assert pool["edge"] == "DL", f"bucketed as {pool.get('edge')}, not DL"
    assert pool.get("corner") == "DB", "a CB eligible at DB never reached DB"
    assert pool.get("lineman") == "DL", "and the players who already worked broke"

    # the same man must not be counted twice -- one player, one bucket
    assert len([1 for r in dh.board_data("L")["rows"] if r["pid"] == "edge"]) == 1

    # ---- and a league with no IDP slot is untouched, fullback included.
    off = dict(idp, roster_positions=["QB", "RB", "RB", "WR", "BN"])
    dh.league_draft = lambda lid: (off, draft, [])
    pool2 = {r["pid"] for r in dh.board_data("L")["rows"]}
    assert "back" in pool2
    assert "fullback" not in pool2, \
        "widened a settled league's RB pool; the IDP fix must not reach offence"
    assert "edge" not in pool2 and "corner" not in pool2


def t_turn_plan_never_names_one_man_in_both_lists():
    """"now: Derrick Henry" and "also priced to wait: Derrick Henry", 3 lines apart.

    Real output, LG02, 9/4, the day before the draft. The PICK was
    right -- Henry at 13 plus Barkley at 16 beats every other pairing on
    need-vorp. Only the page was wrong: `waiting` was survivors minus the
    partner, and never minus `best`, so the man you were told to take now
    also appeared under the heading that means "he will still be there,
    do not spend this pick on him."

    True number, false label -- the same class as the Gibbs banner and the
    "starters filled" banner, and the third time it has shipped. A draft
    clock is not when to work out which of two contradicting lines to
    believe.
    """
    dh = _fresh_dh()
    tbl = {"now": {"position": "RB", "age": 30, "full_name": "Take Now RB"},
           "part": {"position": "RB", "age": 29, "full_name": "Partner RB"},
           "also": {"position": "RB", "age": 25, "full_name": "Also Waits RB"}}
    for v in tbl.values():
        v.update(team="X")
    lg = {"name": "T", "league_id": "L", "season": "2026",
          "scoring_settings": {"x": 1}, "total_rosters": 14, "draft_id": "d",
          "roster_positions": ["QB", "RB", "RB", "WR", "BN"], "settings": {"type": 0}}
    draft = {"settings": {"rounds": 13, "teams": 14}, "draft_order": {"me": 13},
             "status": "pre_draft"}
    dh.state = lambda: {"season": "2026"}
    dh.players = lambda force=False: tbl
    dh.get = lambda path: [] if "rosters" in path else {"user_id": "me"}
    dh._uid_cache[0] = "me"
    dh.weekly_projections = lambda s, w: {}
    dh.my_slot = lambda d: 13
    # All three survive to the second pick (ADP >= next_p + 3), which is
    # exactly the condition that put the recommended man into `waiting`.
    dh.season_projection_totals = lambda s, sc: {"now": 300, "part": 280,
                                                 "also": 260}
    dh._adp = lambda pid, s, k, f=(): {"now": (23.0, True), "part": (36.0, True),
                                       "also": (24.0, True)}[pid]
    dh.league_draft = lambda lid: (lg, draft, [])

    t = dh.board_data("L")["turn"]
    named = {t["now"]["pid"], t["next"]["pid"] if t["next"] else None}
    waiting = [c["pid"] for c in t["waiting"]]
    assert t["now"]["pid"] not in waiting, \
        f"recommended {t['now']['pid']} and also listed him as priced to wait"
    assert not (named & set(waiting)), f"named twice: {named & set(waiting)}"
    # and the list still does its job -- the third man is genuinely waiting
    assert "also" in waiting, "excluded too much; waiting must keep the rest"


def t_depth_banner_names_an_empty_required_slot():
    """"starters filled" printed while a required slot sat empty.

    needs_open drops K and DEF so the need model does not chase a defense
    in round 4, which is right. It also gated the depth-phase banner,
    which is not: the banner claimed the roster was done through two live
    LG01 picks with DEF unfilled. Harmless in the Hybrids, which
    roster neither. LG02 rosters both, and drafts next.
    """
    dh = _fresh_dh()
    tbl = {"a": {"position": "RB", "age": 25, "full_name": "A Back"},
           "b": {"position": "WR", "age": 25, "full_name": "B Wideout"}}
    for v in tbl.values():
        v.update(team="X")
    lg = {"name": "T", "league_id": "L", "season": "2026",
          "scoring_settings": {"x": 1}, "total_rosters": 12, "draft_id": "d",
          "roster_positions": ["RB", "WR", "DEF", "BN"], "settings": {"type": 0}}
    draft = {"settings": {"rounds": 15, "teams": 12}, "draft_order": {"me": 3},
             "status": "drafting"}
    picks = [{"player_id": f"g{i}", "picked_by": "x"} for i in range(30)]
    dh.league_draft = lambda lid: (lg, draft, picks)
    dh.state = lambda: {"season": "2026"}
    dh.players = lambda force=False: tbl
    dh.season_projection_totals = lambda s, sc: {"a": 200, "b": 190}
    # my roster already covers RB and WR; DEF is the empty required slot
    dh.get = lambda path: ([{"roster_id": 1, "owner_id": "me",
                             "players": ["a", "b"]}] if "rosters" in path
                           else {"user_id": "me"})
    dh._uid_cache[0] = "me"
    dh._adp = lambda pid, s, k, f=(): {"a": (99.0, True), "b": (99.0, True)}[pid]
    dh.weekly_projections = lambda s, w: {}
    dh.my_slot = lambda d: 3

    t = dh.board_data("L")["turn"]
    assert t and t.get("phase") == "depth", t
    assert "DEF" in (t.get("required_open") or []), \
        "banner would say 'starters filled' with the DEF slot empty"



def t_new_season_tools_selftest_clean():
    """recap and rhythm run their own suites inside the one gate.

    Both are new on 9/2 and both would otherwise sit outside `br.py test`,
    which is the command every doc tells the next session to trust. A
    module whose tests only run when someone remembers to run them is a
    module with no tests by Friday.
    """
    import io
    import contextlib
    for mod in ("recap", "rhythm"):
        m = __import__(f"battle_rhythm.{mod}", fromlist=[mod])
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                m.selftest()
        except SystemExit as e:
            assert not e.code, f"{mod} selftest exited {e.code}"
        out = buf.getvalue()
        assert "selftest PASSED" in out, f"{mod}: {out[-400:]}"
        assert " XX " not in out, f"{mod} had a failing check:\n{out}"



def t_resolve_draft_finds_the_draft_that_actually_ran():
    """league.draft_id named a COMPLETE draft with zero picks.

    Real, 9/2: LG03 had 265 players rostered from its
    8/18 draft, and board answered "your slot: 8, next pick overall 8,
    7 picks away". keeper said "10 picks left" the same morning. The
    lesson was already written down in keeper.py -- a league season can
    hold several drafts -- and had never reached league_draft().
    """
    from battle_rhythm.draft_helper import resolve_draft

    real = [{"player_id": f"p{i}", "pick_no": i + 1} for i in range(264)]
    stub = {"draft_id": "empty", "status": "complete"}
    full = {"draft_id": "real", "status": "complete", "season": "2026"}

    def fetch(path):
        return {
            "draft/empty": stub,
            "draft/empty/picks": [],
            "draft/real": full,
            "draft/real/picks": real,
            "league/L/drafts": [stub, full],
        }.get(path, [])

    lg = {"league_id": "L", "season": "2026", "draft_id": "empty"}
    d, picks = resolve_draft(lg, fetch=fetch)
    assert d["draft_id"] == "real", d
    assert len(picks) == 264

    # ---- a LIVE draft always wins, even against a fatter finished one.
    # Mid-draft the in-progress draft holds nine picks and last year's
    # holds 264; taking the fatter one breaks the board on the clock.
    live = {"draft_id": "live", "status": "drafting", "season": "2026"}
    nine = [{"player_id": f"q{i}", "pick_no": i + 1} for i in range(9)]

    def fetch_live(path):
        return {
            "draft/live": live,
            "draft/live/picks": nine,
            "draft/real": full,
            "draft/real/picks": real,
            "league/L/drafts": [live, full],
        }.get(path, [])

    d2, p2 = resolve_draft({"league_id": "L", "season": "2026",
                            "draft_id": "live"}, fetch=fetch_live)
    assert d2["draft_id"] == "live", "a live draft must never lose to a fat one"
    assert len(p2) == 9

    # ---- an empty PRE-draft is a legitimate state, not a lookup failure.
    pre = {"draft_id": "pre", "status": "pre_draft", "season": "2026"}
    calls = []

    def fetch_pre(path):
        calls.append(path)
        return {"draft/pre": pre, "draft/pre/picks": []}.get(path, [])

    d3, p3 = resolve_draft({"league_id": "L", "season": "2026",
                            "draft_id": "pre"}, fetch=fetch_pre)
    assert d3["draft_id"] == "pre" and p3 == []
    assert not any("drafts" in c for c in calls), \
        "went hunting for a draft that has simply not happened yet"

    # ---- the named draft having picks is left alone (LG01).
    ok = {"draft_id": "ok", "status": "complete", "season": "2026"}

    def fetch_ok(path):
        return {"draft/ok": ok, "draft/ok/picks": real}.get(path, [])

    d4, p4 = resolve_draft({"league_id": "L", "season": "2026",
                            "draft_id": "ok"}, fetch=fetch_ok)
    assert d4["draft_id"] == "ok" and len(p4) == 264



def t_season_drafts_sees_both_stages_of_a_two_stage_draft():
    """Both Hybrids run TWO drafts a season and every tool graded one.

    keepers.json has said so since August: "TWO-STAGE DRAFT: managers keep
    different numbers of players, so the commissioner runs a 10-round
    draft first and a second draft afterwards to fill rosters out."
    resolve_draft picks the fullest single draft, which between two real
    drafts is a guess -- the 9/2 recap graded 120 picks and stage two was
    never in it.
    """
    from battle_rhythm.draft_helper import season_drafts, season_picks

    one = {"draft_id": "s1", "status": "complete", "season": "2026",
           "start_time": 1000}
    two = {"draft_id": "s2", "status": "complete", "season": "2026",
           "start_time": 2000}
    old = {"draft_id": "s0", "status": "complete", "season": "2025",
           "start_time": 1}
    p1 = [{"player_id": f"a{i}", "pick_no": i + 1} for i in range(120)]
    p2 = [{"player_id": f"b{i}", "pick_no": i + 1} for i in range(36)]
    p0 = [{"player_id": "ancient", "pick_no": 1}]

    def fetch(path):
        return {"league/L/drafts": [two, one, old],   # deliberately unordered
                "draft/s1/picks": p1,
                "draft/s2/picks": p2,
                "draft/s0/picks": p0}.get(path, [])

    lg = {"league_id": "L", "season": "2026", "draft_id": "s1"}
    got = season_drafts(lg, fetch=fetch)
    assert [d["draft_id"] for d, _ in got] == ["s1", "s2"], got
    assert [len(pk) for _, pk in got] == [120, 36]
    assert all(pk["_draft_id"] == "s1" for pk in got[0][1]), \
        "a pick must say which draft it came from; pick_no 1 means two things"

    flat = season_picks(lg, fetch=fetch)
    assert len(flat) == 156, len(flat)
    assert not any(pk["player_id"] == "ancient" for pk in flat), \
        "last season's draft is not this season's board"

    # ---- a player in both drafts is counted once, earliest wins.
    dupe = [{"player_id": "a0", "pick_no": 1}]

    def fetch_dupe(path):
        return {"league/L/drafts": [one, two],
                "draft/s1/picks": p1,
                "draft/s2/picks": dupe}.get(path, [])

    flat2 = season_picks(lg, fetch=fetch_dupe)
    assert len(flat2) == 120
    assert [pk for pk in flat2 if pk["player_id"] == "a0"][0]["_draft_id"] == "s1"

    # ---- a single-draft league is unchanged.
    def fetch_solo(path):
        return {"league/L/drafts": [one], "draft/s1/picks": p1}.get(path, [])

    solo = season_drafts(lg, fetch=fetch_solo)
    assert len(solo) == 1 and len(solo[0][1]) == 120



def t_both_boards_price_survival_off_the_same_market():
    """`br.py board lg04` called Saquon Barkley "priced to wait" at ADP 36
    on the morning `br.py live` had him at 0% -- consensus rank 13, and he
    went 8th in the LG02 room. draft_helper priced survival off ADP
    while draft_live priced it off consensus rank. Two tools, one question,
    opposite answers, on a 60-second clock.

    They now share ext_tiers.market_pos. The default differs on purpose:
    draft_live wants 999 for an unknown (never survives), draft_helper wants
    None (falsy, same idea in its own predicates).
    """
    from battle_rhythm.ext_tiers import market_pos
    from battle_rhythm.draft_live import mkt

    saquon = {"pos": "RB", "bc_rank": 13, "adp": 36}
    assert market_pos(saquon) == 13 and mkt(saquon) == 13

    # draft_helper rows carry position under meta, not pos
    assert market_pos({"meta": {"position": "RB"}, "bc_rank": 13, "adp": 36}) == 13

    # defenses keep ADP in BOTH callers, from the same fit
    dst = {"pos": "DEF", "bc_rank": 178, "adp": 105}
    assert market_pos(dst) == 105 and mkt(dst) == 105

    # no consensus entry falls back to ADP, not to the default
    assert market_pos({"pos": "WR", "adp": 44}) == 44 and mkt({"pos": "WR", "adp": 44}) == 44

    # unknown resolves per caller convention
    assert market_pos({"pos": "WR"}) is None
    assert mkt({"pos": "WR"}) == 999.0

    # THE JOIN MUST SURVIVE A DECORATED NAME. draft_helper rows carry
    # name_of() output -- "Saquon Barkley (RB, PHI)" -- and the first attempt
    # at this keyed the whole string, matched zero rows, reported nothing,
    # and left the board printing ADP while claiming to be aligned.
    from battle_rhythm.ext_tiers import annotate, _key
    rows = [{"name": "Saquon Barkley (RB, PHI)", "pos": "RB", "adp": 36.0},
            {"name": "Derrick Henry (RB, BAL)", "pos": "RB", "adp": 23.0},
            {"name": "HOU (DEF, HOU)", "pos": "DEF", "adp": 105.0}]
    # FIXTURE, not whatever TSV happens to be on disk. This asserted against
    # a live load() until 9/7, when retiring the half-PPR board for the IDP
    # league emptied data/tiers/ and the check failed 0/3 -- reporting a
    # broken name join when the join was fine and the directory was simply
    # empty. Which board a league should read is a per-league question and a
    # legitimately empty directory is not a defect; whether a decorated name
    # matches a plain one is mechanics, and mechanics is what this test is
    # for. annotate() already takes an injected table.
    fixture = {_key("Saquon Barkley", "RB"): {"tier": 2, "rank": 13, "sd": 4.1,
                                              "pos": "RB", "src": "fixture"},
               _key("Derrick Henry", "RB"): {"tier": 4, "rank": 30, "sd": 6.0,
                                             "pos": "RB", "src": "fixture"},
               _key("HOU", "DEF"): {"tier": 19, "rank": 178, "sd": 6.0,
                                    "pos": "DEF", "src": "fixture"}}
    hit, tot = annotate(rows, table=fixture)
    assert hit == tot == 3, f"decorated names must join: {hit}/{tot}"
    assert market_pos(rows[0]) == 13, "Saquon must price off consensus, not ADP 36"
    assert market_pos(rows[2]) == 105, "a defense must keep ADP"

    # and the survivors filter must now drop him: at picks 10/15 the test is
    # mkt >= next_pick + 3, so 13 >= 18 is False where ADP 36 was True
    assert not (market_pos(rows[0]) >= 15 + 3)
    assert market_pos(rows[1]) >= 15 + 3, "Henry at 21 genuinely does wait"


def t_board_command_accepts_a_slug_not_only_an_id():
    """`br.py board lg04` exited "league lg04 not found" on draft
    morning while `br.py live --league lg04` resolved the same word.
    draft_helper's entry point took a raw id and nothing else.

    That is the split leagues/_index.json exists to close, and it survived
    because an id is what gets typed while testing and a slug is what gets
    typed on the day. CLAUDE.md tells you to run `board <league>` before a
    draft, so this path is load-bearing exactly when nobody is checking it.
    """
    from battle_rhythm.draft_helper import cli_league
    from battle_rhythm import paths

    for slug, meta in paths.leagues().items():
        want = str(meta["id"])
        assert str(cli_league(slug)) == want, slug
        for alias in (meta.get("aliases") or []):
            assert str(cli_league(alias)) == want, alias

    # a raw id must pass through: id_for knows slugs, not 19-digit numbers
    any_id = str(next(iter(paths.leagues().values()))["id"])
    assert cli_league(any_id) == any_id

    try:
        cli_league("definitely-not-a-league")
    except SystemExit as e:
        assert "no league matching" in str(e)
    else:
        raise AssertionError("an unknown league must fail loudly, not silently")


def t_roster_panel_shows_every_seat_and_agrees_with_lineup_vorp():
    """The panel showed one chip per REQUIRED position, so a league starting
    RB2 + FLEX2 drew four chips for six seats a back can fill, and the bench
    was invisible. Late in a draft "how many picks do I still owe" is the
    only question it exists to answer.

    lineup_slots and lineup_vorp must assign identically. If they drift, the
    panel names one starter while the projection scores another and neither
    is wrong on its own -- the exact shape of defect this repo keeps finding.
    """
    from battle_rhythm.draft_live import lineup_slots, lineup_vorp
    req = ["QB", "RB", "RB", "WR", "WR", "TE", "DEF"]
    flex = [["RB", "WR", "TE"], ["RB", "WR", "TE"]]
    # pids matter: lineup_vorp tracks used players by p["pid"], lineup_slots
    # by id(). Both are fine alone; the fixture carries pids so the two can
    # be compared at all, which is the point of this test.
    team = [{"pid": "1", "name": "Cook", "pos": "RB", "vorp": 100.0},
            {"pid": "2", "name": "Henry", "pos": "RB", "vorp": 96.0},
            {"pid": "3", "name": "Bowers", "pos": "TE", "vorp": 82.0},
            {"pid": "4", "name": "Lamar", "pos": "QB", "vorp": 43.0},
            {"pid": "5", "name": "Evans", "pos": "WR", "vorp": 31.0},
            {"pid": "6", "name": "Watson", "pos": "WR", "vorp": 22.0},
            {"pid": "7", "name": "Tracy", "pos": "RB", "vorp": 5.0}]
    slots = lineup_slots(team, req, flex, bench=6)
    labels = [s for s, _ in slots]
    assert labels[:9] == ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "DEF",
                          "FLEX1", "FLEX2"], labels
    assert len(slots) == 15, "9 starters + 6 bench = one seat per round"
    assert dict(slots)["DEF"] is None and dict(slots)["FLEX2"] is None
    assert dict(slots)["FLEX1"]["name"] == "Tracy"

    # the two assignments must score the same starters
    started = sum(p["vorp"] for lab, p in slots
                  if p and not lab.startswith(("BN", "OVER")))
    assert abs(started - lineup_vorp(team, req, flex)) < 1e-6

    # an empty roster is every seat open, not an empty panel
    empty = lineup_slots([], req, flex, bench=6)
    assert len(empty) == 15 and all(p is None for _, p in empty)

    # single-slot positions are not numbered
    solo = lineup_slots([], ["QB", "RB", "TE"], [["RB", "WR"]], bench=1)
    assert [s for s, _ in solo] == ["QB", "RB", "TE", "FLEX", "BN1"]

    # More players than seats is a real state and must still be shown. Note
    # DEF stays open no matter how many backs are added -- only a defense
    # fills it -- so nine slots absorb eight of these players, not nine.
    extra = [{"pid": "8", "name": "X", "pos": "RB", "vorp": 4.0},
             {"pid": "9", "name": "Y", "pos": "RB", "vorp": 3.0},
             {"pid": "10", "name": "Z", "pos": "RB", "vorp": 2.0}]
    over = lineup_slots(team + extra, req, flex, bench=0)
    assert sum(1 for lab, _ in over if lab == "OVER") == 2, \
        [lab for lab, _ in over]
    assert all(p is not None for lab, p in over if lab == "OVER")


def t_market_position_prefers_consensus_except_defense():
    """survives() asks where the room will actually take a player, and the
    ADP feed answers it badly. Measured on the completed LG02 draft,
    101 players ranked by both sources: residual sd of log(actual/estimate)
    was 0.431 against ADP and 0.284 against consensus rank. SIGMA_POS
    assumes 0.18-0.27, so against ADP every survival number was computed
    with half the real spread -- a 59% back was gone 35 picks early.

    Defenses are the exception and go the other way: sd 0.063 against ADP,
    0.157 with a -0.324 shift against consensus, because a skill-heavy
    board ranks them far later than rooms take them. Houston was ADP 105,
    consensus 178, drafted 127.
    """
    from battle_rhythm.draft_live import mkt
    assert mkt({"pos": "RB", "bc_rank": 61, "adp": 131}) == 61
    assert mkt({"pos": "WR", "bc_rank": None, "adp": 140}) == 140
    assert mkt({"pos": "DEF", "bc_rank": 178, "adp": 105}) == 105
    assert mkt({"pos": "K", "bc_rank": 196, "adp": 125}) == 125
    assert mkt({}) == 999.0


def t_external_tier_join_survives_suffixes_and_defenses():
    """Both join failures are silent: a suffix mismatch drops one player,
    a defense-key case mismatch drops all of them. The defense case
    shipped broken once already."""
    from battle_rhythm.ext_tiers import norm, _key
    assert norm("James Cook III") == norm("James Cook") == "james cook"
    assert norm("Patrick Mahomes II") == "patrick mahomes"
    assert norm("D.K. Metcalf") == "dk metcalf"
    assert norm("Ja'Marr Chase") == "jamarr chase"
    assert _key("HOU", "DEF") == _key("Houston Texans", "DEF") == "HOU"


def t_one_league_identity_for_both_resolvers():
    """`recap lg05` worked in chat and failed on the command line.

    mcp_server resolves through leagues/_index.json; dynasty_value's
    resolve_league matched league NAMES only. Same question, two
    resolvers, different answers -- which is the split _index.json was
    created to close.
    """
    import battle_rhythm.dynasty_value as dv
    import battle_rhythm.sleeper_client as sc
    from battle_rhythm import paths

    lgs = [{"league_id": str(m["id"]), "name": m["name"]}
           for m in paths.leagues().values()]
    saved = sc.load_leagues
    try:
        sc.load_leagues = lambda *a, **k: {"leagues": lgs}
        for slug, m in paths.leagues().items():
            for alias in [slug, *(m.get("aliases") or [])]:
                got = dv.resolve_league(alias)
                assert str(got) == str(m["id"]), \
                    f"{alias!r} -> {got}, expected {m['id']}"
            assert str(dv.resolve_league(str(m["id"]))) == str(m["id"])
    finally:
        sc.load_leagues = saved



def t_weekly_reads_the_lineup_you_actually_set():
    """Every in-season view computed the OPTIMAL lineup and stopped.

    That quietly assumes you set it, so the one thing a Thursday brief
    exists to catch -- a bench player out-projecting a starter you left
    in -- was invisible. Sleeper carries the answer in the roster's
    `starters` array and nothing read it.
    """
    from battle_rhythm import weekly as wk

    tbl = {"a": {"position": "RB", "full_name": "Good Back", "team": "X"},
           "b": {"position": "RB", "full_name": "Bad Back", "team": "X"},
           "c": {"position": "QB", "full_name": "A QB", "team": "X"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2,
          "roster_positions": ["QB", "RB", "BN"], "scoring_settings": {"x": 1},
          "my_players": ["a", "b", "c"], "status": "in_season"}
    ros = {"a": 200.0, "b": 50.0, "c": 300.0}

    saved = (wk.get, wk.ros_totals, wk.weekly_projections,
             wk._adp, wk.adp_of, wk.availability_ratios)
    try:
        # the value-gap section prices players; without these it reaches the
        # network and the test fails on egress rather than on the model
        wk._adp = lambda *a, **k: (None, False)
        wk.adp_of = lambda *a, **k: None
        wk.availability_ratios = lambda *a, **k: {}
        # started the WRONG back: b (50) is in, a (200) is on the bench
        wk.get = lambda path: ([{"roster_id": 1, "owner_id": "me",
                                 "players": ["a", "b", "c"],
                                 "starters": ["c", "b"]}]
                               if "rosters" in path else [])
        wk.ros_totals = lambda season, scoring, wk_: (ros, {k: 0.0 for k in ros})
        # the lineup is solved on THIS WEEK now, so the week feed has to
        # carry the players; scoring is {"x": 1} so the stat is the score
        wk.weekly_projections = lambda s, w: (
            {"a": {"x": 200.0}, "b": {"x": 50.0}, "c": {"x": 300.0}}
            if w == 1 else {})
        import battle_rhythm.draft_helper as dh
        saved_uid = dh.uid
        dh.uid = lambda: "me"
        try:
            L = wk.league_brief(lg, "2026", 1, tbl, {"leagues": []})
        finally:
            dh.uid = saved_uid
    finally:
        (wk.get, wk.ros_totals, wk.weekly_projections,
         wk._adp, wk.adp_of, wk.availability_ratios) = saved

    assert L["lineup_known"] is True
    assert [s_["slot"] for s_ in L["actual_starters"]] == ["QB", "RB"]
    # the RB you started is not the one the optimum picks
    bad = next(s_ for s_ in L["actual_starters"] if s_["slot"] == "RB")
    assert bad["player"].startswith("Bad Back") and bad["optimal"] is False

    assert len(L["lineup_diff"]) == 1, L["lineup_diff"]
    d = L["lineup_diff"][0]
    assert d["out"].startswith("Bad Back") and d["in"].startswith("Good Back")
    assert d["gain"] == 150.0
    assert L["lineup_gap"] == 150.0, "the total is the honest number"

    # roster_ranked must carry the join keys the roster pane needs
    by = {r["player"].split(" (")[0]: r for r in L["roster_ranked"]}
    assert by["Good Back"]["starter"] is True and by["Good Back"]["started"] is False
    assert by["Bad Back"]["starter"] is False and by["Bad Back"]["started"] is True

    # ---- a league that returns no starters array must say so, not lie
    saved2 = (wk.get, wk._adp, wk.adp_of, wk.availability_ratios)
    try:
        wk._adp = lambda *a, **k: (None, False)
        wk.adp_of = lambda *a, **k: None
        wk.availability_ratios = lambda *a, **k: {}
        wk.get = lambda path: ([{"roster_id": 1, "owner_id": "me",
                                 "players": ["a", "b", "c"]}]
                               if "rosters" in path else [])
        wk.ros_totals = lambda season, scoring, wk_: (ros, {k: 0.0 for k in ros})
        wk.weekly_projections = lambda s, w: (
            {"a": {"x": 200.0}, "b": {"x": 50.0}, "c": {"x": 300.0}}
            if w == 1 else {})
        import battle_rhythm.draft_helper as dh
        sv = dh.uid
        dh.uid = lambda: "me"
        try:
            L2 = wk.league_brief(lg, "2026", 1, tbl, {"leagues": []})
        finally:
            dh.uid = sv
    finally:
        (wk.get, wk._adp, wk.adp_of, wk.availability_ratios) = saved2
    assert L2["lineup_known"] is False and L2["lineup_diff"] == []



def t_roster_tab_joins_upgrades_to_the_player_they_replace():
    """The numbers existed; the render threw them away.

    LINEUP printed the optimal nine and said nothing about what was
    actually started. WAIVER listed adds on a separate page, so the
    starter each one beats was a name to match up by hand. This pane is
    the join, and it must not invent anything: every value comes from
    weekly.league_brief.
    """
    from battle_rhythm import dashboard as db

    L = {"lineup_known": True, "lineup_gap": 40.0,
         "lineup_diff": [{"out": "Bench Guy (RB, X)", "in": "Better Guy (RB, X)",
                          "out_ros": 10.0, "in_ros": 50.0, "gain": 40.0,
                          "in_inj": ""}],
         "waivers_tier1": [{"add": "Wire Star (WR, X)", "over": "Weak Starter (WR, X)",
                            "drop": "Bench Guy (RB, X)", "gap": 22.5, "inj": ""}],
         "waivers_tier2": [{"add": "Churn Body (RB, X)", "over": "Bench Guy (RB, X)",
                            "drop": "Bench Guy (RB, X)", "gap": 3.0, "inj": ""}],
         "roster_ranked": [
             {"player": "Weak Starter (WR, X)", "pid": "w", "pos": "WR",
              "ros": 60.0, "playoff": 9.0, "inj": "", "starter": True,
              "slot": "WR", "started": True},
             {"player": "Better Guy (RB, X)", "pid": "g", "pos": "RB",
              "ros": 50.0, "playoff": 8.0, "inj": "", "starter": True,
              "slot": "RB", "started": False},
             {"player": "Bench Guy (RB, X)", "pid": "b", "pos": "RB",
              "ros": 10.0, "playoff": 1.0, "inj": "", "starter": False,
              "slot": "", "started": True}]}

    html = db.render_roster_tab(L, "https://sleeper.com/leagues/L")

    assert "leaving 40.0" in html, "the total gap is the headline"
    assert "SHOULD START" in html and "SHOULD SIT" in html, \
        "a benched optimal starter and a started non-optimal one must be named"
    # the tier-1 upgrade sits on the row of the starter it beats, not on a
    # separate page
    wk_row = [r for r in html.split("<tr>") if "Weak Starter" in r][0]
    assert "Wire Star" in wk_row and "22.5" in wk_row and "FAAB" in wk_row
    # tier 2 is present but labelled as churn, not as a lineup change
    bench_row = [r for r in html.split("<tr>") if "Bench Guy" in r
                 and "Churn Body" in r][0]
    assert "churn" in bench_row

    # ---- no published lineup: say so rather than claim the roster is right
    L2 = dict(L, lineup_known=False, lineup_diff=[], lineup_gap=0.0)
    h2 = db.render_roster_tab(L2, "u")
    assert "has not published a lineup" in h2
    assert "SHOULD SIT" not in h2, \
        "cannot accuse a lineup of being wrong when it was never read"

    # ---- an optimal lineup says nothing rather than inventing a swap
    L3 = dict(L, lineup_diff=[], lineup_gap=0.0)
    h3 = db.render_roster_tab(L3, "u")
    assert "matches the optimal" in h3 and "leaving" not in h3



def t_lineup_is_a_one_week_decision():
    """The DJ Moore case, pinned.

    optimal_starters ran on rest-of-season totals, which carry the
    availability haircut -- a probability spread over eighteen weeks --
    and used it to answer who to start on Sunday. Moore out-projected
    Brian Thomas EVERY week and lost only to a season-long durability
    discount. Three of four in-season leagues had a start/sit flip on it
    in week 1 alone.

    Season stays the objective for waivers and trades. Not for lineups.
    """
    from battle_rhythm import weekly as wk

    tbl = {"moore": {"position": "WR", "full_name": "Moore", "team": "X"},
           "btj": {"position": "WR", "full_name": "BTJ", "team": "X"},
           "hurt": {"position": "WR", "full_name": "Hurt Guy", "team": "X",
                    "injury_status": "Out"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2,
          "roster_positions": ["WR", "BN", "BN"], "scoring_settings": {"x": 1},
          "my_players": ["moore", "btj", "hurt"], "status": "in_season"}

    # this week Moore is better; across the season the haircut flips it
    wkp = {"moore": {"x": 14.5}, "btj": {"x": 12.8}, "hurt": {"x": 30.0}}
    # hurt carries a big WEEK number so the Out-zeroing is what excludes
    # him, and a small season one so he does not win the ROS comparison
    # for an unrelated reason and hide what this test is checking
    ros = {"moore": 202.9, "btj": 224.1, "hurt": 10.0}

    saved = (wk.get, wk.ros_totals, wk.weekly_projections,
             wk._adp, wk.adp_of, wk.availability_ratios)
    try:
        wk.get = lambda path: ([{"roster_id": 1, "owner_id": "me",
                                 "players": list(tbl), "starters": ["btj"]}]
                               if "rosters" in path else [])
        wk.ros_totals = lambda s_, sc_, w_: (ros, {k: 0.0 for k in ros})
        wk.weekly_projections = lambda s_, w_: wkp if w_ == 1 else {}
        wk._adp = lambda *a, **k: (None, False)
        wk.adp_of = lambda *a, **k: None
        wk.availability_ratios = lambda *a, **k: {}
        import battle_rhythm.draft_helper as dh
        sv = dh.uid
        dh.uid = lambda: "me"
        try:
            L = wk.league_brief(lg, "2026", 1, tbl, {"leagues": []})
        finally:
            dh.uid = sv
    finally:
        (wk.get, wk.ros_totals, wk.weekly_projections,
         wk._adp, wk.adp_of, wk.availability_ratios) = saved

    started = [o["player"] for o in L["optimal_starters"]]
    assert any("Moore" in x for x in started), \
        f"benched the better week-1 player on a season durability bet: {started}"
    assert not any("Hurt Guy" in x for x in started), \
        "a player ruled Out cannot be the optimal start at any projection"

    # both numbers must be on the row -- the season view is still the
    # objective for waivers, and where they disagree is information
    row = L["optimal_starters"][0]
    assert "wk" in row and "ros" in row and row["wk"] == 14.5

    # and the roster rows say which model each player belongs to
    by = {r["player"].split(" (")[0]: r for r in L["roster_ranked"]}
    assert by["Moore"]["starter"] is True, "week model starts Moore"
    assert by["BTJ"]["ros_starter"] is True, "season model still prefers BTJ"

    # the gap you are closing is THIS WEEK's points, not the season's
    assert L["lineup_diff"] and L["lineup_diff"][0]["gain"] == 1.7, L["lineup_diff"]



def t_calibration_travels_with_the_recommendation():
    """A gap without its odds invites you to believe the gap.

    Measured on 2025, a 1.7 point edge wins 53% of the time. The tool
    said "+1.7" and I relayed it as though 1.7 were the thing he wins.
    He wins it 53% of the time and loses something 47% of the time.
    """
    from battle_rhythm import backtest as bt
    from battle_rhythm import weekly as wk

    table = {"0-1": {"n": 21361, "rate": 0.501},
             "1-2": {"n": 20351, "rate": 0.534},
             "5-8": {"n": 37436, "rate": 0.708},
             "12-999": {"n": 40, "rate": 0.95}}
    assert bt.confidence(0.4, table) == 0.501
    assert bt.confidence(1.7, table) == 0.534, "the DJ Moore edge"
    assert bt.confidence(6.0, table) == 0.708
    assert bt.confidence(50, table) is None, "40 pairs is not a measurement"
    assert bt.confidence(3.5, table) is None, "unmeasured bucket must decline"

    # the module ships without a calibration file on a fresh clone; that
    # must degrade to silence, not to a crash or an invented number
    saved = wk._CALIB[0]
    try:
        wk._CALIB[0] = {}
        assert wk.edge_confidence(1.7) is None
    finally:
        wk._CALIB[0] = saved


def t_backtest_selftest_clean():
    """backtest runs its own suite inside the one gate."""
    import io
    import contextlib
    from battle_rhythm import backtest as bt
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            bt.selftest()
    except SystemExit as e:
        assert not e.code
    out = buf.getvalue()
    assert "selftest PASSED" in out and " XX " not in out, out


# ---------------------------------------------------------- dynasty value

def t_dynasty_curves():
    from battle_rhythm.dynasty_value import curve, dynasty_value, load_params, years_left
    P = load_params()
    assert curve("RB", 24, P) == 1.0            # peak plateau
    assert 0 < curve("RB", 21, P) < 1.0         # riser below peak
    assert curve("RB", 29, P) < curve("RB", 27, P)
    assert curve("RB", P["curves"]["RB"]["end"], P) == 0.0
    assert curve("QB", 30, P) > curve("RB", 30, P)
    # the rookie fix: equal projections, youth must win
    assert dynasty_value("RB", 22, 150.0, P) > dynasty_value("RB", 27, 150.0, P)
    assert dynasty_value("WR", 26, 150.0, P) > dynasty_value("RB", 26, 150.0, P)
    assert years_left("RB", 27, P) == P["curves"]["RB"]["end"] - 27
    # the QB-wall fix: surplus over replacement beats raw points —
    # a 20-surplus QB must lose to a 50-surplus RB in a 1QB league
    assert (dynasty_value("QB", 26, 250.0, P, 230.0)
            < dynasty_value("RB", 24, 150.0, P, 100.0))
    assert dynasty_value("RB", 29, 90.0, P, 100.0) == 0.0
    # a young riser below the line today can climb above it later
    assert dynasty_value("RB", 21, 95.0, P, 100.0) > 0.0


def t_dynasty_blend_and_tiers():
    from battle_rhythm.dynasty_value import blend_market, tier_breaks, load_params
    P = load_params()
    # zero-model rookie priced at dADP 5 blends up off the floor
    rows = [{"model_v": 0.0, "adp": 5.0}]
    ladder = [float(v) for v in range(300, 0, -10)]
    blend_market(rows, P, ladder)
    assert rows[0]["value"] > 0
    # no adp -> pure model, untouched by the blend
    rows2 = [{"model_v": 100.0, "adp": None}]
    blend_market(rows2, P, ladder)
    assert rows2[0]["value"] == 100.0
    # one obvious cliff -> exactly one break at it
    assert tier_breaks([300.0, 295.0, 290.0, 180.0, 176.0, 173.0], P) == {2}


def t_research_queue_ranks_stars_first():
    """v1 of research_score ranked a buried, unpriced, injured rookie TE
    #1 out of 447 — maximum uncertainty, zero stakes. Guard the fix."""
    from battle_rhythm import research_queue as rq
    P = {"curves": {"RB": {"peak": [23, 26], "rise": .92, "decline": .87,
                           "cliff": [28, .70], "end": 32}}}

    def dv(pos, age, proj, P, repl=0.0):
        return max(0.0, proj - repl)

    def row(pid, pos, age, pts, adp, **meta):
        m = {"position": pos, "age": age, "team": "X"}
        m.update(meta)
        return {"pid": pid, "name": f"{pid} ({pos}, X)", "meta": m,
                "pts": pts, "adp": adp, "inj": ""}

    rows = [row("star", "RB", 24, 300, 8.0),
            row("scrub", "WR", 25, 6, None, depth_chart_order=6,
                years_exp=0, injury_status="IR")]
    rows += [row(f"f{i}", "RB", 26, 120 - i, 100.0 + i) for i in range(40)]
    q = rq.build(rows, [], P, {"RB": 50.0}, dv)
    by = {e["player_id"]: e for e in q}
    assert by["scrub"]["rank"] > by["star"]["rank"]
    assert by["scrub"]["rank"] > len(rows) * 0.75, "scrub not near the bottom"
    assert by["scrub"]["stakes"] < 0.1, "unpriced scrub given real stakes"


def t_keeper_depletion_shifts_redraftability():
    """Global ADP assumes nobody is kept. In a 12-team league retaining 5
    each, ~60 players never reach the board and everyone behind them
    slides earlier. Comparing raw ADP to a pick number told John that
    Derrick Henry (adp 74) was reclaimable at pick 65 with ~30 kept
    players ahead of him — a keeper he'd have released and lost."""
    from battle_rhythm import keeper
    tbl = {f"p{i}": {"position": "RB"} for i in range(40)}
    tbl["q"] = {"position": "QB"}
    # two rosters, 5 players each, all keepable
    rosters = [{"roster_id": 1, "players": [f"p{i}" for i in range(5)]},
               {"roster_id": 2, "players": [f"p{i}" for i in range(5, 10)]}]
    totals = {f"p{i}": 300 - i for i in range(40)}
    kept = keeper.estimate_kept(rosters, tbl, totals)
    assert len(kept) == 10, f"expected both rosters fully kept, got {len(kept)}"

    # with 30 keepers ahead of him, an adp-74 player goes ~44, not 74
    kept_adps = list(range(1, 31))

    def effective(adp):
        return max(1, adp - sum(1 for a in kept_adps if a < adp))

    assert effective(74) == 44, effective(74)
    # and the reclaim test must now fail at pick 65
    assert not (effective(74) >= 65 + 3), "still claims reclaimable at 65"
    # a genuinely late player is still reclaimable
    assert effective(200) >= 65 + 3


def t_dossier_attribution():
    """Same injury keywords mean opposite things depending on whose body
    it is. Nabers shows 'torn ACL' because he tore his; Tyler Warren shows
    it because Alec Pierce did. A flag that collapses those is worse than
    no flag. See MISPRICING.md, 'the attribution trap'."""
    from battle_rhythm import dossier

    def sourced(pid, name):
        # blank() is confidence "low" and correctly earns its own WATCH
        d = dossier.blank(pid, name)
        d["confidence"] = "high"
        d["sources"] = [{"url": "https://x"}]
        return d

    hurt = sourced("1", "Casualty")
    hurt["volatile"]["injury"] = {"status": "Torn ACL, out for the season"}
    gains = sourced("2", "Beneficiary")
    gains["stable"]["competition"] = [
        {"name": "Guy Ahead", "age": 27, "status": "PUP, no timetable"}]
    a = [t for t, _ in dossier.opportunity_flags(hurt)]
    b = [t for t, _ in dossier.opportunity_flags(gains)]
    assert a == ["BLOCKED"], a
    assert b == ["INHERITING"], b
    # a resolved injury must not keep flagging
    ok = sourced("3", "Cleared")
    ok["volatile"]["injury"] = {"status": "Torn ACL 2025, fully cleared"}
    assert "BLOCKED" not in [t for t, _ in dossier.opportunity_flags(ok)]


def t_dashboard_research_is_display_only():
    """Research shows BESIDE the numbers, never inside them: board_data
    must stay one auditable, tested computation."""
    from battle_rhythm import dashboard as db
    import inspect
    src = inspect.getsource(db.render_dynasty_tab)
    assert "research_cell" in src, "research not surfaced on the dynasty tab"
    # the dashboard must render fine with no research store at all
    db._HEADLINES.clear()
    db._HEADLINES.update({})
    assert db.research_cell("does-not-exist") == ("", "")


def t_league_resolver_exact_wins():
    """Invented names on purpose: this tests the resolver, not the real
    leagues, and a public copy renames every real league (release.py).
    Two leagues named 'Hybrid 9' and 'Hybrid 9 <emoji>': the short
    name is a substring of the long one, so substring matching alone can
    never select it. Exact match must win, and ambiguity must print ids."""
    from battle_rhythm import dynasty_value as dv
    from battle_rhythm import sleeper_client
    LGS = {"leagues": [
        {"league_id": "111", "name": "Hybrid 9 \U0001F9B8\U0001F4AA"},
        {"league_id": "222", "name": "Hybrid 9"},
        {"league_id": "333", "name": "Dynasty Crew"}]}
    orig = sleeper_client.load_leagues
    sleeper_client.load_leagues = lambda refresh=False: LGS
    try:
        assert dv.resolve_league("Hybrid 9") == "222"      # exact wins
        assert dv.resolve_league("hybrid 9") == "222"      # case-insensitive
        assert dv.resolve_league("111") == "111"            # id wins
        assert dv.resolve_league("dynasty") == "333"        # substring ok
        try:
            dv.resolve_league("hybrid")
            raise AssertionError("expected ambiguity")
        except SystemExit as e:
            assert "111" in str(e) and "222" in str(e), "ids not shown"
    finally:
        sleeper_client.load_leagues = orig


def t_dynasty_roster_context():
    """Target collision is about the shared QB, not Green Bay; handcuff
    bump requires standalone value."""
    from battle_rhythm.dynasty_value import roster_adjust, load_params
    P = load_params()
    tbl = {"my_wr": {"position": "WR", "team": "GB"},
           "my_te": {"position": "TE", "team": "KC"},
           "my_rb": {"position": "RB", "team": "TB"}}
    rows = [{"meta": {"position": "TE", "team": "GB"},   # collides w/ my_wr
             "model_v": 40.0, "value": 100.0},
            {"meta": {"position": "WR", "team": "KC"},   # collides w/ my_te
             "model_v": 40.0, "value": 100.0},
            {"meta": {"position": "RB", "team": "GB"},   # RB never collides
             "model_v": 40.0, "value": 100.0},
            {"meta": {"position": "RB", "team": "TB"},   # real handcuff
             "model_v": 25.0, "value": 100.0},
            {"meta": {"position": "RB", "team": "TB"},   # insurance only
             "model_v": 0.0, "value": 30.0}]
    roster_adjust(rows, ["my_wr", "my_te", "my_rb"], tbl, P)
    assert rows[0]["value"] < 100.0 and "collision" in rows[0]["note"]
    assert rows[1]["value"] < 100.0          # TE-vs-WR collides both ways
    assert rows[2]["value"] == 100.0         # RBs don't share targets
    assert rows[3]["value"] > 100.0          # standalone handcuff bumped
    assert rows[4]["value"] == 30.0          # insurance back: no bump
    assert "no standalone" in rows[4]["note"]


def t_dynasty_tab_renders():
    """Dashboard DYNASTY tab renders from a fake board_data dict, offline,
    with tier rows present and the gone-players ladder wired in."""
    from battle_rhythm import dashboard as db
    db._DEPTH_N.clear()
    tbl = {"y": {"position": "RB", "age": 22, "full_name": "Young RB",
                 "team": "A"},
           "o": {"position": "RB", "age": 29, "full_name": "Old RB",
                 "team": "B"},
           "g": {"position": "WR", "age": 25, "full_name": "Gone WR",
                 "team": "C"}}
    d = {"tbl": tbl, "dynasty": True, "superflex": False, "keeper": False,
         "adp_hdr": "dADP",
         "replacement": {"RB": 100.0, "WR": 120.0},
         "totals": {"y": 150.0, "o": 150.0, "g": 200.0},
         "rows": [{"pid": p, "meta": tbl[p], "pts": 150.0, "adp": 60.0,
                   "inj": "", "name": f"{tbl[p]['full_name']} (RB, X)",
                   "vorp": 10.0, "need_vorp": 10.0, "exact": True,
                   "radp": None}
                  for p in ("y", "o")]}
    out = db.render_dynasty_tab(d)
    assert "TIER 1" in out and "Young RB" in out and "Old RB" in out
    assert out.index("Young RB") < out.index("Old RB")  # age curve ranks him


# ----------------------------------------------------------------- keeper

def t_keeper_qb_cap():
    from battle_rhythm import keeper
    tbl = {"q1": {"position": "QB"}, "q2": {"position": "QB"},
           "w1": {"position": "WR"}, "r1": {"position": "RB"}}
    cands = [(320, "q1"), (310, "q2"), (250, "w1"), (200, "r1")]
    picked = keeper.pick_constrained(cands, 3, 1, tbl)
    assert [p for _, p in picked] == ["q1", "w1", "r1"]  # q2 blocked by cap


# ----------------------------------------------------------------- weekly

def t_weekly_core():
    import importlib
    from battle_rhythm import weekly
    importlib.reload(weekly)
    tbl = {"q1": {"position": "QB"}, "r1": {"position": "RB"}, "r2": {"position": "RB"},
           "r3": {"position": "RB"}, "w1": {"position": "WR"}, "w2": {"position": "WR"},
           "t1": {"position": "TE"}, "fa": {"position": "RB"}}
    for k, v in tbl.items():
        v.update(full_name=k, team="X", age=25)
    demand = weekly.starter_demand(["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN"], 10)
    assert demand == {"QB": 10, "RB": 24, "WR": 24, "TE": 12}
    ros = {"q1": 300, "r1": 200, "r2": 150, "r3": 90, "w1": 220, "w2": 140,
           "t1": 120, "fa": 160}
    starters = weekly.optimal_starters(list(ros), ["QB", "RB", "RB", "WR", "WR", "TE",
                                                   "FLEX", "BN"], ros, tbl)
    # fa (160) beats r2 (150) for the second RB slot; r2 lands in flex
    assert [p for _, p in starters] == ["q1", "r1", "fa", "w1", "w2", "t1", "r2"]


def t_weekly_trades_both_sides():
    import importlib
    from battle_rhythm import weekly
    importlib.reload(weekly)
    tbl = {"q1": {"position": "QB", "age": 24}, "q2": {"position": "QB", "age": 25},
           "w1": {"position": "WR", "age": 27}, "w2": {"position": "WR", "age": 25},
           "r1": {"position": "RB", "age": 22}, "tq": {"position": "QB", "age": 30},
           "tr": {"position": "RB", "age": 24}, "tw": {"position": "WR", "age": 24},
           "tw2": {"position": "WR", "age": 22}, "tw3": {"position": "WR", "age": 24}}
    for k, v in tbl.items():
        v.update(full_name=k, team="X")
    proj = {"q1": 300, "q2": 280, "w1": 250, "w2": 100, "r1": 200,
            "tq": 120, "tr": 240, "tw": 260, "tw2": 180, "tw3": 170}
    weekly.ros_totals = lambda s, sc, st: (proj, {p: v * .2 for p, v in proj.items()})
    weekly.weekly_projections = lambda s, w: {p: {"x": 1} for p in tbl}
    weekly.get = lambda path: ([{"owner_id": "me", "roster_id": 1,
                                 "players": ["q1", "q2", "w1", "w2", "r1"]},
                                {"owner_id": "them", "roster_id": 2,
                                 "players": ["tq", "tr", "tw", "tw2", "tw3"]}]
                               if "rosters" in path else
                               ([{"user_id": "them", "display_name": "Rival"}]
                                if "users" in path else None))
    weekly.adp_of = lambda p, s: None
    weekly._adp = lambda pid, s, k, f=(): (None, True)
    weekly.players = lambda force=False: tbl
    lg = {"league_id": "L", "name": "T", "status": "in_season", "total_teams": 2,
          "roster_positions": ["QB", "RB", "WR", "WR", "BN"],
          "scoring_settings": {"x": 1}, "settings": {"type": 2}, "my_faab_used": 0,
          "my_roster_id": 1, "my_players": ["q1", "q2", "w1", "w2", "r1"],
          "my_starters": []}
    L = weekly.league_brief(lg, "2026", 1, tbl, {"leagues": []})
    assert L["trades"], "no trades found"
    t0 = L["trades"][0]
    assert t0["my_gain"] > 5 and t0["their_gain"] > 5
    # pids used to be popped once the age/market tags were attached. Since
    # 9/11 they stay: the ledger keys every trade rec on give_pid/get_pid.
    assert "give_age" in t0 and t0["give_pid"] in tbl and t0["get_pid"] in tbl
    assert L["roster_ranked"][0]["player"].startswith("q1")


def _brief_with(tbl, lg, ros, roster_rows, week=1, wkfeed=None, txs=None, locked=()):
    """Run weekly.league_brief offline with every network edge stubbed.
    Shared by the 9/11 waiver tests so each one states only its own
    fixture and its own assertion."""
    from battle_rhythm import weekly as wk
    import battle_rhythm.draft_helper as dh
    saved = (wk.get, wk.ros_totals, wk.weekly_projections,
             wk._adp, wk.adp_of, wk.availability_ratios, dh.uid)
    try:
        wk._adp = lambda *a, **k: (None, False)
        wk.adp_of = lambda *a, **k: None
        wk.availability_ratios = lambda *a, **k: {}

        def _get(path):
            if "rosters" in path:
                return roster_rows
            if "transactions" in path:
                return txs or []
            return []
        wk.get = _get
        wk.ros_totals = lambda season, scoring, wk_: (ros, {k: 0.0 for k in ros})
        wk.weekly_projections = lambda s, w: (
            (wkfeed or {p: {"x": v} for p, v in ros.items()}) if w == week else {})
        dh.uid = lambda: "me"
        # teams whose game has started; seeded so no test touches the network
        wk._LOCKED[("2026", week)] = set(locked)
        return wk.league_brief(lg, "2026", week, tbl, {"leagues": []})
    finally:
        wk._LOCKED.clear()
        (wk.get, wk.ros_totals, wk.weekly_projections,
         wk._adp, wk.adp_of, wk.availability_ratios, dh.uid) = saved


def t_reserve_is_never_the_drop():
    """James Conner, in LG04's reserve slot and costing no active
    roster space, was the named drop in every claim (9/7). bench was
    `mine - starters`, and Sleeper's `reserve` list is inside `players`.
    The lowest-projected ACTIVE bench player is the drop; the reserve
    player is neither a drop nor a bench bar for tier 2, nor a starter.
    """
    tbl = {"s": {"position": "RB", "full_name": "Starter", "team": "A"},
           "b": {"position": "RB", "full_name": "Bench Back", "team": "B"},
           "ir": {"position": "RB", "full_name": "Hurt Back", "team": "C",
                  "injury_status": "IR"},
           "fa": {"position": "RB", "full_name": "Free Back", "team": "D"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2, "status": "in_season",
          "roster_positions": ["RB", "BN", "BN", "IR"], "scoring_settings": {"x": 1},
          "settings": {"waiver_type": 2, "waiver_budget": 100},
          "my_players": ["s", "b", "ir"], "my_roster_id": 1}
    ros = {"s": 200.0, "b": 60.0, "ir": 5.0, "fa": 80.0}
    rows = [{"roster_id": 1, "owner_id": "me", "players": ["s", "b", "ir"],
             "starters": ["s"], "reserve": ["ir"],
             "settings": {"waiver_budget_used": 40}}]
    L = _brief_with(tbl, lg, ros, rows)
    assert L["parked"] == ["ir"]
    t2 = L["waivers_tier2"]
    assert t2 and t2[0]["add"].startswith("Free Back"), t2
    # the bar is the ACTIVE bench (b, 60), not the reserve player (ir, 5)
    assert t2[0]["over"].startswith("Bench Back"), t2[0]
    assert t2[0]["gap"] == 20.0
    # and the drop is the active bench man, never the reserve one
    assert t2[0]["drop"].startswith("Bench Back"), t2[0]["drop"]
    by = {r["pid"]: r for r in L["roster_ranked"]}
    assert by["ir"]["parked"] is True and by["ir"]["slot"] == "IR"
    assert by["ir"]["starter"] is False
    # FAAB read off the roster row's own counter, not the stale league copy
    assert L["waiver"]["faab_left"] == 60 and L["waiver"]["mode"] == "FAAB"
    print("  reserve is parked: never a drop, never a bar, never a starter")


def t_depth_chart_flags_a_stale_role_and_names_the_handcuff():
    """Tracy at +78.9 over Saylors (9/7): the feed priced a job he no
    longer held, and Sleeper's own chart said so. The table carries
    depth_chart_position/order; the brief now prints them and flags
    order >= 3 backs. A backup whose starter is on MY roster is named as
    his handcuff -- the feature specified weeks ago and never built.
    """
    from battle_rhythm import weekly as wk
    tbl = {"my1": {"position": "RB", "full_name": "My Star", "team": "DET",
                   "depth_chart_position": "RB", "depth_chart_order": 1},
           "w": {"position": "WR", "full_name": "Wide", "team": "DET",
                 "depth_chart_position": "LWR", "depth_chart_order": 1},
           "cuff": {"position": "RB", "full_name": "Direct Backup", "team": "DET",
                    "depth_chart_position": "RB", "depth_chart_order": 2},
           "third": {"position": "RB", "full_name": "Third String", "team": "NYG",
                     "depth_chart_position": "RB", "depth_chart_order": 3},
           "q2": {"position": "QB", "full_name": "Backup QB", "team": "X",
                  "depth_chart_position": "QB", "depth_chart_order": 2},
           "bn": {"position": "RB", "full_name": "Bench Body", "team": "Y"}}
    assert wk.depth_of(tbl["cuff"]) == "RB2" and wk.depth_of({}) == ""
    assert wk.role_is_stale(tbl["third"]) and wk.role_is_stale(tbl["q2"])
    assert not wk.role_is_stale(tbl["cuff"]) and not wk.role_is_stale(tbl["w"])
    # receivers are never flagged: Sleeper stacks men under LWR/RWR/SWR,
    # and the flag fired on 6 of 8 LG04 rows the first time it ran live
    assert not wk.role_is_stale({"position": "WR", "depth_chart_position": "RWR",
                                 "depth_chart_order": 3})
    lg = {"name": "T", "league_id": "L", "total_teams": 2, "status": "in_season",
          "roster_positions": ["RB", "WR", "BN"], "scoring_settings": {"x": 1},
          "settings": {"waiver_type": 0}, "my_players": ["my1", "w", "bn"],
          "my_roster_id": 1}
    ros = {"my1": 250.0, "w": 150.0, "cuff": 90.0, "third": 120.0, "q2": 40.0,
           "bn": 50.0}
    rows = [{"roster_id": 1, "owner_id": "me", "players": ["my1", "w", "bn"],
             "starters": ["my1", "w"], "settings": {"waiver_position": 9}}]
    L = _brief_with(tbl, lg, ros, rows)
    # both backs beat the bench body, so both are tier 2 -- the wording is the point
    adds = {r["add"].split(" (")[0]: r for r in L["waivers_tier1"] + L["waivers_tier2"]}
    assert "Third String" in adds and adds["Third String"]["stale_role"] is True
    assert adds["Third String"]["depth"] == "RB3"
    assert adds["Direct Backup"]["handcuff_to"].startswith("My Star")
    assert adds["Direct Backup"]["stale_role"] is False
    # order-based league: no bid, but the position is shown
    assert adds["Third String"]["bid"] is None
    assert L["waiver"]["position"] == 9 and L["waiver"]["faab_left"] is None
    line = wk._waiver_line(adds["Third String"])
    assert "ROLE?" in line and "RB3" in line, line
    print("  depth chart read: RB3 flagged, handcuff named, order league positioned")


def t_faab_bid_is_a_share_of_the_spendable_slice():
    """The bid is stated arithmetic, recorded so the ledger can refute it.
    One tier-1 add in week 17 gets the whole budget; four adds in week 1
    split roughly half of it; nothing ever exceeds what is left."""
    from battle_rhythm import weekly as wk
    bid, why = wk.faab_bid(30.0, [30.0], 100, 17)
    assert bid == 97, (bid, why)                     # 1 week left: ~3 held back
    bid1, _ = wk.faab_bid(10.0, [10.0, 10.0, 10.0, 10.0], 100, 1)
    assert bid1 == 12, bid1                          # half held back, quarter share
    assert wk.faab_bid(50.0, [50.0], 3, 1)[0] <= 3
    assert wk.faab_bid(5.0, [5.0], 0, 1) == (0, "no budget")
    assert wk.faab_bid(0.0, [0.0], 100, 1)[0] == 0
    # comps come from completed waiver transactions only, prior weeks only
    calls = []

    def g(path):
        calls.append(path)
        return [{"type": "waiver", "status": "complete", "settings": {"waiver_bid": 23}},
                {"type": "waiver", "status": "failed", "settings": {"waiver_bid": 99}},
                {"type": "free_agent", "status": "complete", "settings": {}}]
    assert wk.faab_comps("L", 3, get_fn=g) == [23, 23]
    assert len(calls) == 2 and calls[-1].endswith("/2"), calls
    print("  FAAB bid: stated formula, bounded by budget, comps from real claims")


def t_weekly_records_to_the_ledger_and_the_ledger_scores():
    """The 9/11 contract: a brief's recommendations land in the ledger
    once, keyed on pids, and score against actuals under the league's
    own rules. ledger.selftest covers the arithmetic; this pins the JOIN
    from weekly's output shape -- the pids weekly must carry."""
    from battle_rhythm import ledger
    tbl = {"s": {"position": "RB", "full_name": "Starter", "team": "A"},
           "b": {"position": "RB", "full_name": "Bench Back", "team": "B"},
           "fa": {"position": "RB", "full_name": "Free Back", "team": "D"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2, "status": "in_season",
          "roster_positions": ["RB", "BN"], "scoring_settings": {"x": 1},
          "settings": {"waiver_type": 2, "waiver_budget": 100},
          "my_players": ["s", "b"], "my_roster_id": 1}
    ros = {"s": 200.0, "b": 60.0, "fa": 250.0}
    rows = [{"roster_id": 1, "owner_id": "me", "players": ["s", "b"],
             "starters": ["b"], "settings": {"waiver_budget_used": 0}}]
    L = _brief_with(tbl, lg, ros, rows, week=2)
    recs = ledger.recs_from_brief(L, "2026", 2)
    kinds = sorted(r["kind"] for r in recs)
    assert kinds == ["lineup", "waiver"], kinds
    w = next(r for r in recs if r["kind"] == "waiver")
    assert w["subject"] == ["fa"] and w["over"] == ["s"], w
    assert w["proj"]["bid"] and w["proj"]["tier"] == 1
    l = next(r for r in recs if r["kind"] == "lineup")
    assert l["subject"] == ["s"] and l["over"] == ["b"], l
    feed = {2: {"fa": {"x": 20}, "s": {"x": 10}, "b": {"x": 30}},
            3: {"fa": {"x": 25}, "s": {"x": 10}, "b": {"x": 30}}}
    got = ledger.score(3, {"L": {"x": 1.0}}, fetch=lambda s, wk_: feed.get(wk_, {}),
                       recs=recs)
    by = {o["kind"]: o for o in got}
    # the waiver was made in week 2, so it counts from week 3: 25 - 10
    assert by["waiver"]["won"] is True and by["waiver"]["delta"] == 15.0
    assert by["waiver"]["weeks"] == [3]
    assert by["lineup"]["won"] is False and by["lineup"]["delta"] == -20.0
    print("  weekly -> ledger -> outcome: the pids survive the whole chain")


def t_lineup_swaps_pair_by_position_not_rank():
    """LG03, 9/12: Brown (WR) ruled out and started, Daniels at
    SUPER_FLEX, optimum wants Reed at WR and Geno at SF. Rank-zipping
    printed 'start Reed over Daniels +-7.2 (75%)'. Pairs must be WR for
    WR and QB for QB, odds only where the printed gain is positive."""
    tbl = {"dan": {"position": "QB", "full_name": "Daniels", "team": "W"},
           "geno": {"position": "QB", "full_name": "Geno", "team": "N"},
           "law": {"position": "QB", "full_name": "Lawrence", "team": "J"},
           "ajb": {"position": "WR", "full_name": "Brown", "team": "N",
                   "injury_status": "Out"},
           "reed": {"position": "WR", "full_name": "Reed", "team": "G"},
           "w2": {"position": "WR", "full_name": "Other WR", "team": "X"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2, "status": "in_season",
          "roster_positions": ["QB", "WR", "WR", "SUPER_FLEX", "BN", "BN"],
          "scoring_settings": {"x": 1}, "settings": {"waiver_type": 2, "waiver_budget": 10},
          "my_players": list(tbl), "my_roster_id": 1}
    ros = {"dan": 300.0, "geno": 280.0, "law": 320.0, "ajb": 250.0, "reed": 220.0, "w2": 200.0}
    wk = {"dan": {"x": 21.6}, "geno": {"x": 22.5}, "law": {"x": 25.0},
          "ajb": {"x": 30.0}, "reed": {"x": 14.4}, "w2": {"x": 13.0}}
    rows = [{"roster_id": 1, "owner_id": "me", "players": list(tbl),
             "starters": ["dan", "ajb", "w2", "law"], "settings": {"waiver_budget_used": 0}}]
    L = _brief_with(tbl, lg, ros, rows, wkfeed=wk)
    d = {(x["in"].split(" (")[0], x["out"].split(" (")[0]): x for x in L["lineup_diff"]}
    assert ("Reed", "Brown") in d, L["lineup_diff"]
    assert ("Geno", "Daniels") in d, L["lineup_diff"]
    assert d[("Reed", "Brown")]["gain"] == 14.4          # Brown is Out -> 0.0
    assert abs(d[("Geno", "Daniels")]["gain"] - 0.9) < 1e-9
    assert L["lineup_gap"] == 15.3
    # no cross-position pair, no odds on a negative gain
    assert all(x["gain"] > 0 or x["conf"] is None for x in L["lineup_diff"])
    print("  lineup swaps pair QB with QB and WR with WR")


def t_locked_players_are_not_lineup_advice():
    """A.J. Brown, 9/12: hurt Thursday night, locked in the lineup, and
    the brief said bench him for Reed. A player whose game has started
    can be neither sat nor started. He is on neither list, the gap only
    counts moves you can still make, and the ledger gets no rec for him.
    The lock comes from the week's stats feed: any team with a stat line
    has kicked off."""
    from battle_rhythm import weekly as wk, ledger
    tbl = {"dan": {"position": "QB", "full_name": "Daniels", "team": "WAS"},
           "geno": {"position": "QB", "full_name": "Geno", "team": "NYJ"},
           "law": {"position": "QB", "full_name": "Lawrence", "team": "JAX"},
           "ajb": {"position": "WR", "full_name": "Brown", "team": "NE",
                   "injury_status": "Out"},
           "reed": {"position": "WR", "full_name": "Reed", "team": "GB"},
           "w2": {"position": "WR", "full_name": "Other WR", "team": "X"}}
    lg = {"name": "T", "league_id": "L", "total_teams": 2, "status": "in_season",
          "roster_positions": ["QB", "WR", "WR", "SUPER_FLEX", "BN", "BN"],
          "scoring_settings": {"x": 1}, "settings": {"waiver_type": 2, "waiver_budget": 10},
          "my_players": list(tbl), "my_roster_id": 1}
    ros = {"dan": 300.0, "geno": 280.0, "law": 320.0, "ajb": 250.0, "reed": 220.0, "w2": 200.0}
    wkf = {"dan": {"x": 21.6}, "geno": {"x": 22.5}, "law": {"x": 25.0},
           "ajb": {"x": 30.0}, "reed": {"x": 14.4}, "w2": {"x": 13.0}}
    rows = [{"roster_id": 1, "owner_id": "me", "players": list(tbl),
             "starters": ["dan", "ajb", "w2", "law"], "settings": {"waiver_budget_used": 0}}]
    # the feed says New England has a stat line this week -> NE is locked
    stats = {"ajb": {"rec": 1, "rec_yd": 4}, "somebody": {"pass_yd": 200}}
    got = wk.locked_teams("2026", 1, {**tbl, "somebody": {"team": "NE"}},
                          fetch=lambda s, w: stats)
    assert got == {"NE"}, got
    wk._LOCKED.clear()
    L = _brief_with(tbl, lg, ros, rows, wkfeed=wkf, locked={"NE"})
    names = [(x["in"].split(" (")[0], x["out"].split(" (")[0]) for x in L["lineup_diff"]]
    assert ("Reed", "Brown") not in names, names
    assert ("Geno", "Daniels") in names, names
    assert L["locked"] == ["ajb"]
    assert abs(L["lineup_gap"] - 0.9) < 1e-9, L["lineup_gap"]   # only the movable swap
    recs = ledger.recs_from_brief(L, "2026", 1)
    assert not any("ajb" in r["subject"] + r["over"] for r in recs)
    # a feed miss locks nothing, rather than crashing the brief
    wk._LOCKED.clear()
    assert wk.locked_teams("2026", 1, tbl, fetch=lambda s, w: (_ for _ in ()).throw(OSError())) == set()
    wk._LOCKED.clear()
    print("  locked players: on neither list, out of the gap, out of the ledger")


def t_ledger_selftest_clean():
    from battle_rhythm import ledger
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert ledger.selftest() == 0
    assert "18 checks passed" in buf.getvalue(), buf.getvalue()


def t_truth_selftest_clean():
    """The engine check against Sleeper's own players_points. Pins the two
    hand-verified LG03-LG05 wk2 lines (36.8, 16.8) and the row logic:
    exact / rounding / miss, the missing-key hint, TEAM_ totals kept out."""
    from battle_rhythm import truth
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert truth.selftest() == 0, buf.getvalue()
    assert "22/22 selftest PASSED" in buf.getvalue(), buf.getvalue()


def t_release_selftest_clean():
    """The public-repo gate: history scan finds a key removed from HEAD;
    leagues become LGnn and managers MGRnn (stable keys, any case, folders
    renamed); data/release/ never leaves; verify catches a planted leak.
    Builds its own throwaway git repo."""
    from battle_rhythm import release
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert release.selftest() == 0, buf.getvalue()
    assert "39/39 selftest PASSED" in buf.getvalue(), buf.getvalue()


def t_idp_vocabulary():
    """IDP slots map to feed positions; the alias table covers the fine-
    grained slot names (CB, S, DE...) Sleeper leagues can use."""
    from battle_rhythm import draft_helper as dh
    assert dh.IDP_POS == ("DL", "LB", "DB")
    for slot, canon in (("CB", "DB"), ("S", "DB"), ("FS", "DB"),
                        ("DE", "DL"), ("NT", "DL"), ("MLB", "LB")):
        assert dh.SLOT_ALIAS[slot] == canon, slot
    for p in dh.IDP_POS:
        assert p in dh.SEAT_POS
    # dashboard renders the codes and colors for every canonical position
    from battle_rhythm import dashboard as db
    for p in dh.IDP_POS:
        assert p in db.POS_COLORS, p
        assert p in db.DEPTH_POS, p
    assert "CB" in db.DEPTH_POS and "SS" in db.DEPTH_POS



def t_draft_shape():
    """Pick geometry: reversals and traded picks. Both were silently
    wrong across three files until 8/13 (see DECISIONS)."""
    from battle_rhythm.sleeper_client import (round_is_forward, slot_picks, overall_of,
                                traded_deltas, my_draft_picks)

    # HIS REAL CARD, verbatim: 1.8 2.5 3.5 4.8 5.5 6.8 7.5 8.8 9.5 10.8
    assert slot_picks(8, 10, 12, 3) == [8, 17, 29, 44, 53, 68, 77, 92, 101, 116]
    # ...and the emoji league, a plain snake at slot 6
    assert slot_picks(6, 10, 12, 0) == [6, 19, 30, 43, 54, 67, 78, 91, 102, 115]
    assert slot_picks(6, 10, 12) == slot_picks(6, 10, 12, 0)

    # a reversal repeats round R-1's direction at R, then alternates
    assert round_is_forward(1, 3) and not round_is_forward(2, 3)
    assert not round_is_forward(3, 3)          # repeats round 2
    assert round_is_forward(4, 3)
    # it pays the late slot and charges the early one
    assert slot_picks(8, 3, 12, 3)[2] < slot_picks(8, 3, 12)[2]
    assert slot_picks(2, 3, 12, 3)[2] > slot_picks(2, 3, 12)[2]

    # round 8 under a 3-reversal runs FORWARD, which is why his traded
    # pick is 8.11 = 95 and not the 86 a reverse round would give
    assert overall_of(8, 11, 12, 3) == 95
    assert overall_of(8, 11, 12, 0) == 86

    s2r = {"7": 1, "6": 11}                     # slot -> roster
    fake = [{"round": 8, "roster_id": 1, "owner_id": 11},
            {"round": 9, "roster_id": 11, "owner_id": 4}]
    gained, lost = traded_deltas("d", 11, 12, 0, s2r, get_fn=lambda _u: fake)
    assert gained == {overall_of(8, 7, 12, 0)}, gained     # roster 1 sits at slot 7
    assert lost == {overall_of(9, 6, 12, 0)}, lost         # his own round 9, sold
    # a trade between two rivals moves nothing
    g2, l2 = traded_deltas("d", 5, 12, 0, s2r,
                           get_fn=lambda _u: [{"round": 8, "roster_id": 1,
                                               "owner_id": 11}])
    assert not g2 and not l2

    draft = {"draft_id": "d", "draft_order": {"u": 8},
             "slot_to_roster_id": {str(i): i for i in range(1, 13)},
             "settings": {"teams": 12, "rounds": 10, "reversal_round": 3}}
    picks, meta = my_draft_picks(draft, 8, get_fn=lambda _u: [
        {"round": 8, "roster_id": 11, "owner_id": 8}])
    assert meta["reversal_round"] == 3 and meta["slot"] == 8
    assert meta["gained"] == [overall_of(8, 11, 12, 3)] == [95]
    assert picks == sorted(slot_picks(8, 10, 12, 3) + [95])
    assert len(picks) == 11
    print("  draft shape: reversal + traded picks OK")



def t_owned_picks_beat_arithmetic():
    """The turn plan must use the OWNED pick list, not snake arithmetic.

    Both Hybrids: eleven picks, not ten. One league runs a third-round
    reversal and the other does not. Real payloads, both verified against
    cards he read off Sleeper himself (DECISIONS 8/13).
    """
    from battle_rhythm.sleeper_client import my_draft_picks, slot_picks

    NO_EMOJI = {"draft_id": "9000000000000000015",
        "draft_order": {"9000000000000000003": 8},   # published; the gate needs it
        "settings": {"teams": 12, "rounds": 10, "reversal_round": 3},
        "slot_to_roster_id": {"1":4,"2":3,"3":11,"4":8,"5":9,"6":12,
                              "7":7,"8":6,"9":5,"10":2,"11":1,"12":10}}
    NO_TRADES = [{"round": 8, "roster_id": 1, "owner_id": 6},
                 {"round": 9, "roster_id": 1, "owner_id": 2},
                 {"round": 9, "roster_id": 3, "owner_id": 1}]
    picks, meta = my_draft_picks(NO_EMOJI, 6, get_fn=lambda _u: NO_TRADES)
    assert meta["slot"] == 8 and meta["reversal_round"] == 3
    assert picks == [8, 17, 29, 44, 53, 68, 77, 92, 95, 101, 116], picks
    assert len(picks) == 11
    assert meta["gained"] == [95] and meta["lost"] == []
    # the arithmetic-only answer is a DIFFERENT, shorter list
    assert slot_picks(8, 10, 12, 3) != picks and len(slot_picks(8, 10, 12, 3)) == 10
    # and a plain snake would have been wrong from round 3 down
    assert slot_picks(8, 10, 12)[2] == 32 and picks[2] == 29

    EMOJI = {"draft_id": "9000000000000000021",
        "draft_order": {"9000000000000000003": 6},   # published
        "settings": {"teams": 12, "rounds": 10, "reversal_round": 0},
        "slot_to_roster_id": {"1":7,"2":10,"3":5,"4":12,"5":4,"6":11,
                              "7":1,"8":9,"9":6,"10":3,"11":8,"12":2}}
    EM_TRADES = [{"round": 8, "roster_id": 1, "owner_id": 11}]
    picks2, meta2 = my_draft_picks(EMOJI, 11, get_fn=lambda _u: EM_TRADES)
    assert meta2["slot"] == 6 and meta2["reversal_round"] == 0
    assert picks2 == [6, 19, 30, 43, 54, 67, 78, 90, 91, 102, 115], picks2
    assert meta2["gained"] == [90]
    # 90 and 91 are consecutive — the thing worth telling him about
    assert any(b - a == 1 for a, b in zip(picks2, picks2[1:]))

    # a pick traded AWAY leaves the list
    away = [{"round": 4, "roster_id": 11, "owner_id": 3}]
    picks3, meta3 = my_draft_picks(EMOJI, 11, get_fn=lambda _u: away)
    assert meta3["lost"] == [43] and 43 not in picks3
    assert len(picks3) == 9
    print("  owned picks: reversal + trades, both leagues")



def t_league_shape_drives_positions():
    """`live` positions come from roster_positions, never a hardcode.

    lineup_value pinned {"QB","RB","WR","TE"}, which silently deleted
    every kicker and defender from the roster AND the candidate pool. In
    the IDP league that produced a board with no DL/LB/DB on it and a
    16-round plan holding six quarterbacks for a one-QB league, three
    starting slots left empty (8/13).
    """
    from battle_rhythm.lineup_value import lineup_shape

    def live_of(rp):
        ded, flex = lineup_shape(rp)
        out = set(ded)
        for _s, elig in flex:
            out |= set(elig)
        return out - {"BN", "IR", "TAXI"}

    idp = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DL", "LB",
           "DB"] + ["BN"] * 5
    assert live_of(idp) == {"QB", "RB", "WR", "TE", "K", "DL", "LB", "DB"}
    # the Hybrids must be untouched by the change
    hyb = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX",
           "SUPER_FLEX"] + ["BN"] * 9
    assert live_of(hyb) == {"QB", "RB", "WR", "TE"}
    # and a K/DEF league picks both up
    lg02 = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 4
    assert {"K", "DEF"} <= live_of(lg02)
    print("  live positions follow each league's own slots")


def t_unpublished_draft_order_yields_no_slot():
    """An identity slot_to_roster_id is a placeholder, not an order.

    Sleeper ships slot N -> roster N with draft_order null until the
    commissioner randomises. Reading a slot off that gave the IDP league
    a confident "slot 4 of 10" and a full pick list for a draft whose
    order does not exist (8/13).
    """
    from battle_rhythm.sleeper_client import my_draft_picks
    base = {"draft_id": "d",
            "settings": {"teams": 10, "rounds": 16, "reversal_round": 0},
            "slot_to_roster_id": {str(i): i for i in range(1, 11)}}
    picks, meta = my_draft_picks({**base, "draft_order": None}, 4,
                                 get_fn=lambda _u: [])
    assert picks == [] and meta["slot"] is None and meta["published"] is False
    picks2, meta2 = my_draft_picks({**base, "draft_order": {"u": 4}}, 4,
                                   get_fn=lambda _u: [])
    assert meta2["published"] is True and meta2["slot"] == 4
    assert len(picks2) == 16
    # the Hybrids publish, so they keep working
    hyb = {"draft_id": "h",
           "settings": {"teams": 12, "rounds": 10, "reversal_round": 3},
           "draft_order": {"u": 8},
           "slot_to_roster_id": {"1":4,"2":3,"3":11,"4":8,"5":9,"6":12,
                                 "7":7,"8":6,"9":5,"10":2,"11":1,"12":10}}
    p3, m3 = my_draft_picks(hyb, 6, get_fn=lambda _u: [])
    assert m3["slot"] == 8 and p3[:3] == [8, 17, 29]
    print("  unpublished order -> no slot, no invented picks")



def t_turn_plan_uses_owned_picks():
    """The LIVE board must count traded picks, not just my seat.

    He holds eleven picks in each Hybrid and ten seats. The turn plan
    called my_next_picks, which walks the seat and is blind to trades, so
    the board he rereads every pick would have told him ten — on 8/18,
    across two simultaneous drafts (8/13).
    """
    dh = _fresh_dh()
    # emoji Hybrid: slot 6, plain snake, roster 1's round 8 traded to him
    draft = {"draft_id": "9000000000000000021",
             "draft_order": {"u": 6},
             "settings": {"teams": 12, "rounds": 10, "reversal_round": 0},
             "slot_to_roster_id": {"1":7,"2":10,"3":5,"4":12,"5":4,"6":11,
                                   "7":1,"8":9,"9":6,"10":3,"11":8,"12":2}}
    from battle_rhythm import sleeper_client as sc
    real_get, real_uid = sc.get, dh.uid
    # uid() would hit the network to resolve the username; the seat walk
    # needs it, so stub both and keep this test offline.
    sc.get = lambda path: ([{"round": 8, "roster_id": 1, "owner_id": 11}]
                           if "traded_picks" in path else None)
    dh.uid = lambda: "u"
    try:
        owned = dh.my_owned_next_picks(draft, 85, 11, count=3)
        seat = dh.my_next_picks(draft, 85, count=3)
        # EVERY call that walks the seat belongs inside this block. This
        # one sat below the finally and went to the network for the very
        # username the stub existed to supply (8/13).
        fallback = dh.my_owned_next_picks(draft, 85, None, count=1)
    finally:
        sc.get, dh.uid = real_get, real_uid
    # 90 is the traded pick, 91 his own; the seat walk sees only 91
    assert [p for p, _ in owned][:2] == [90, 91], owned
    assert [p for p, _ in seat][:1] == [91], seat
    assert owned != seat
    # rounds still resolve
    assert owned[0][1] == 8 and owned[1][1] == 8
    # unknown roster falls back to the seat rather than returning nothing
    assert fallback == seat[:1], (fallback, seat[:1])
    print("  turn plan counts traded picks, falls back to seat when it cannot")


def t_watch_alarm_uses_owned_picks():
    """The on-the-clock bell must ring for a pick traded TO him.

    `watch` polls in a loop and cannot be called offline, so this reads
    the source instead. He owns 8.11 in the no-emoji Hybrid, three picks
    behind his own 8.8; a seat-walking alarm goes silent for it while he
    is running the second Hybrid in another window (8/13).
    """
    import ast
    import pathlib
    src = PKG.joinpath("draft_helper.py").read_text(
        encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "watch")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "my_owned_next_picks" in called, called
    assert "my_next_picks" not in called, (
        "watch is back on the seat walk and will not ring for traded picks")
    assert "my_roster_id" in called, (
        "ownership is recorded against a roster; without it the owned "
        "lookup silently falls back to the seat")
    print("  live alarm resolves ownership, not just my seat")



def t_authored_data_is_read_from_data_dir_as_utf8():
    """Two silent failures, one root cause: reading authored JSON wrong.

    1. ENCODING. A bare read with no encoding uses the LOCALE codepage,
       which is cp1252 on his Windows box. Every em dash in keepers.json
       came back as mojibake in roster.md the moment that file was
       written as UTF-8 (8/13).
    2. LOCATION. paths.data() prefers data/ and falls back to the repo
       root. lineup_value built its own path from the module directory,
       so when the dead root copy was deleted its `keeper` flag silently
       went False for both Hybrids — which switches the ADP market from
       redraft to dynasty and moves every survival flag on the card.

    Both reads sit inside bare excepts, so neither failure raised
    anything. This walks the AST rather than grepping: the first version
    matched its own docstring and failed against itself.
    """
    import ast
    import pathlib as _pl
    # Was this file's own directory, which after the package move holds
    # three entry points. A lint that walks almost nothing passes for the
    # wrong reason, so the file count is asserted below.
    files = sorted(PKG.glob("*.py"))
    assert len(files) >= 20, f"lint went vacuous: {len(files)} files"
    bare, direct = [], []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_text"
                    and not node.args and not node.keywords):
                bare.append(f"{f.name}:{node.lineno}")
            # authored data must resolve through paths.data(), never a
            # path assembled from the module's own directory
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                    and isinstance(node.right, ast.Constant)
                    and isinstance(node.right.value, str)
                    and node.right.value in ("keepers.json", "ages.json",
                                             "byes.json", "fonts.json")):
                direct.append(f"{f.name}:{node.lineno}")
    assert not bare, f"read with no encoding: {bare}"
    assert not direct, f"authored data read outside paths.data(): {direct}"
    print("  authored JSON: utf-8 everywhere, data/ everywhere")


def t_replacement_subtracts_kept_demand():
    """Remaining demand, not total — the bug that survived one fix.

    `cands` in a keeper league is ALREADY the post-keeper pool. Scoring
    total league demand against it counts the kept players twice and
    walks the index off the end of a shallow position, where it lands on
    the worst player in the league. That put QB replacement at about one
    point in the no-emoji Hybrid, so Jalen Milroe (1 projected point)
    was NOT below replacement, was not floored, and Dak Prescott came
    back at +359 for the second time in an hour.

    It went unnoticed because the emoji Hybrid — same code, same day —
    has two real quarterbacks and behaved correctly.
    """
    from battle_rhythm.draft_helper import replacement_levels
    # 22 QB of league-wide demand (superflex), a pool of only 16 left
    # because the rest are kept, and 14 of that demand already met.
    pool = {"QB": [400 - i * 20 for i in range(16)]}       # 400 down to 100
    demand = {"QB": 22 / 12}                               # per team
    naive = replacement_levels(pool, demand, 12, gone_by_pos={})
    real = replacement_levels(pool, demand, 12, gone_by_pos={"QB": 14})
    assert naive["QB"] == 100, naive          # falls off the end, worst QB
    assert real["QB"] > naive["QB"], (real, naive)
    # 22 - 14 = 8 remaining, but the teams//2 = 6 floor does not bind
    assert real["QB"] == pool["QB"][7], real
    # and the floor DOES bind when nearly all demand is met
    allgone = replacement_levels(pool, demand, 12, gone_by_pos={"QB": 21})
    assert allgone["QB"] == pool["QB"][5], allgone
    print("  replacement uses REMAINING demand, and the floor still binds")


def t_both_engines_share_one_replacement():
    """The board and lineup_value must not drift.

    Two copies of the pick geometry is how all three ended up wrong in
    August. lineup_value grew a second copy of the replacement formula
    on 8/13 and it was wrong within the hour. There is one function now;
    this asserts lineup_value still calls it rather than its own.
    """
    import ast
    import pathlib as _pl
    src = PKG.joinpath("lineup_value.py").read_text(
        encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "replacement_level")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "replacement_levels" in called, (
        "lineup_value.replacement_level has stopped delegating to "
        "draft_helper.replacement_levels and is computing its own again")
    print("  one replacement formula, both engines")


if __name__ == "__main__":
    print("offline regression suite\n")
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("t_")}.items()):
        check(name, fn)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
