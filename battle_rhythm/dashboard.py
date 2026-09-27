"""
dashboard.py — Battle Rhythm: one self-contained HTML command center.

  python dashboard.py            # writes dashboard.html
  python dashboard.py --open     # ...and opens it
  python dashboard.py --serve    # localhost:8787 with a working refresh button

Design ("Roster Fit" spec, ported): one league at a time via a switcher, tabs
per league — Draft (pre-draft/in-flight only, default when present), Board,
Lineup / Waiver / Trade (in-season), Health. The Board ranks available players
by FIT — the Fitline score: a 0-100 blend of roster need, value over
replacement, market discount, and availability, with live weight sliders
(components are precomputed per row; sliders re-score and re-sort in JS).
Actions deep-link to Sleeper (the API is read-only by design). Archivo +
JetBrains Mono embed from fonts.json when present; system stack otherwise.
Title: "{Username}'s {Phase} Battle Rhythm" — phase follows the most active
league. Dark is canonical (the design); a light scheme derives from the same
tokens.
"""

import html
import json
import pathlib
from battle_rhythm import paths as _paths
import sys
import webbrowser
from datetime import datetime

from battle_rhythm.sleeper_client import players, state, load_leagues
from battle_rhythm.draft_helper import board_data, my_slot, injury_tag

OUT = _paths.out("dashboard.html")
POS_COLORS = {"QB": "#C08CFF", "RB": "#5FE0A8", "WR": "#6FB6FF",
              "TE": "#FFC24D", "K": "#FF9EC4", "DEF": "#8A82A6",
              "LB": "#FF9E6B", "DL": "#E96B8F", "DB": "#6BE0DD"}
LEAGUE_ACCENTS = ["#D6FF3F", "#6FB6FF", "#C08CFF", "#FF9EC4", "#5FE0A8",
                  "#FFC24D", "#E9FF8C", "#ff8a80"]
INJ_AVAIL = {"OUT": .25, "IR": .2, "PUP": .25, "SUS": .3, "D": .5, "Q": .7,
             "NA": .6, "DNR": .2, "COV": .6}


def esc(s):
    return html.escape(str(s))


def fmt_ts(ms):
    if not ms:
        return "not scheduled"
    return datetime.fromtimestamp(ms / 1000).strftime("%a %b %d, %I:%M %p")


_HEADLINES = {}


def load_headlines(force=False):
    """{pid: (headline, tags, stale_days)} from the research store.

    Optional by design: no dossiers/ directory means the dashboard
    renders exactly as it did before. Research is displayed BESIDE the
    numbers, never folded into them — board_data stays one auditable,
    tested computation (DECISIONS.md 8/11)."""
    if _HEADLINES and not force:
        return _HEADLINES
    try:
        from battle_rhythm import dossier
        # 88 chars was sized for a cramped column; the roomy dynasty
        # table can show a real sentence, so cut far less aggressively
        try:
            _HEADLINES.update(dossier.load_all_headlines(maxlen=190))
        except TypeError:
            _HEADLINES.update(dossier.load_all_headlines())
    except Exception as e:
        print(f"  (no research store: {e})")
    return _HEADLINES


def research_cell(pid, width="wide"):
    """(html, plain) for one player's research note. Empty when unknown."""
    h = load_headlines().get(str(pid))
    if not h:
        return "", ""
    head, tags, vd = h
    if not head:
        return "", ""
    cls = ("rblock" if "BLOCKED" in tags else
           "rgain" if "INHERITING" in tags else "rwatch")
    age = f" · {vd}d" if isinstance(vd, int) and vd > 10 else ""
    chip = (f"<span class='rchip {cls}'>"
            f"{'!' if cls == 'rblock' else '+' if cls == 'rgain' else '?'}"
            f"</span>") if tags else ""
    return (f"{chip}<span class='rnote' title='{esc(head)}'>"
            f"{esc(head)}{esc(age)}</span>"), head


def _load_json(name):
    p = _paths.data(name)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------- fit engine

def fit_components(rows, my_pids=None, tbl=None):
    """Precompute normalized FIT components per board row. Embedded as data-*
    attributes so the weight sliders re-score client-side with no server.

    Roster correlation (the Reed/Watson lesson): a WR or TE on the same NFL
    team as one of your pass catchers competes for the same targets, so his
    projection overstates what he adds to YOUR roster — availability takes a
    hit and the WHY says so. The mirror case is good: an RB behind your own
    RB is a handcuff — you would own the whole backfield — so he gets a
    bump and a note."""
    if not rows:
        return {}
    my_pass_teams, my_rb_teams = set(), set()
    for pid in (my_pids or []):
        m = (tbl or {}).get(pid) or {}
        team = m.get("team")
        if not team:
            continue
        if m.get("position") in ("WR", "TE"):
            my_pass_teams.add(team)
        elif m.get("position") == "RB":
            my_rb_teams.add(team)
    vorps = [r["vorp"] for r in rows]
    lo, hi = min(vorps), max(vorps)
    span = (hi - lo) or 1.0
    by_proj = sorted(rows, key=lambda r: -r["pts"])
    proj_rank = {r["pid"]: i + 1 for i, r in enumerate(by_proj)}
    comps = {}
    for r in rows:
        vorp_n = (r["vorp"] - lo) / span
        ratio = (r["need_vorp"] / r["vorp"]) if r["vorp"] else 1.0
        need_n = 1.0 if ratio > 0.75 else (0.45 if ratio > 0.25 else 0.05)
        if r["adp"]:
            disc = (r["adp"] - proj_rank[r["pid"]]) / 60.0
            disc_n = max(0.0, min(1.0, 0.5 + disc))
        else:
            disc_n = 0.5
        tag = (r["inj"].split("-")[0] if r["inj"] else "")
        avail_n = INJ_AVAIL.get(tag, 1.0)
        team = r["meta"].get("team")
        pos = r["meta"].get("position")
        collide = (pos in ("WR", "TE") and team in my_pass_teams)
        handcuff = (pos == "RB" and team in my_rb_teams)
        # handcuff bump only with standalone value (vorp > 0): a pure
        # insurance back doesn't help while your starter is healthy.
        # Same-QB collision applies to ANY team you roster a pass
        # catcher on — the GB rule was one instance, not the rule.
        if collide:
            avail_n = round(avail_n * 0.6, 2)
        elif handcuff and r["vorp"] > 0:
            avail_n = round(min(1.0, avail_n * 1.15), 2)
        why = []
        # research leads the WHY when it flags something: a torn ACL the
        # market has as "Questionable" outranks any derived number
        rhead = load_headlines().get(str(r["pid"]))
        if rhead and rhead[1]:
            why.append(rhead[0])
        if collide:
            why.append(f"shares one QB's throws with your {team} guy")
        elif handcuff and r["vorp"] > 0:
            why.append(f"handcuffs your {team} RB, standalone value too")
        elif handcuff:
            why.append(f"insurance for your {team} RB, little solo value")
        if need_n >= 1.0:
            why.append("fills an open starting slot")
        if r["vorp"] == hi and hi > 0:
            why.append("best value over replacement out there")
        elif vorp_n > 0.7:
            why.append(f"+{r['vorp']:.0f} over replacement")
        if r["adp"] and disc_n > 0.62:
            why.append(f"market prices him {r['adp']:.0f}")
        if r["inj"]:
            why.append(r["inj"])
        comps[r["pid"]] = {"vorp_n": round(vorp_n, 3), "need_n": need_n,
                           "disc_n": round(disc_n, 3), "avail_n": avail_n,
                           "why": " · ".join(why[:2]) or "steady contributor"}
    return comps


# ------------------------------------------------------------- tab renders

_DEPTH_N = {}


def _depth_counts(tbl):
    """(team, depth-chart pos) -> how many players hold an order there."""
    if not _DEPTH_N:
        for m in tbl.values():
            if (isinstance(m, dict) and m.get("depth_chart_order")
                    and m.get("team")):
                k = (m["team"],
                     m.get("depth_chart_position") or m.get("position"))
                _DEPTH_N[k] = _DEPTH_N.get(k, 0) + 1
    return _DEPTH_N


def _ordinal(n):
    if 10 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


# Sleeper's depth-chart position codes, in plain words. WRs are charted
# by alignment, so a team can have a 1st LWR, 1st RWR, and 1st SWR at once.
DEPTH_POS = {
    "QB": "quarterback", "RB": "running back", "FB": "fullback",
    "TE": "tight end", "K": "kicker",
    "LWR": "left (outside) wide receiver",
    "RWR": "right (outside) wide receiver",
    "SWR": "slot wide receiver",
    "WR": "wide receiver",
    "MLB": "middle linebacker", "ILB": "inside linebacker",
    "OLB": "outside linebacker", "LB": "linebacker",
    "LCB": "left cornerback", "RCB": "right cornerback",
    "CB": "cornerback", "NB": "nickel (slot) corner",
    "FS": "free safety", "SS": "strong safety", "S": "safety",
    "DB": "defensive back",
    "LDE": "left defensive end", "RDE": "right defensive end",
    "DE": "defensive end", "DT": "defensive tackle",
    "NT": "nose tackle", "DL": "defensive lineman",
}


def bio_cols(meta, tbl):
    """(team, depth-chart seat, experience, seat tooltip) — e.g.
    ('MIN', '2nd RB of 5', '4 yrs', '2nd running back on the MIN depth
    chart, 5 listed'). Empty strings when the feed has no seat."""
    team = meta.get("team") or "FA"
    seat, tip = "", ""
    order = meta.get("depth_chart_order")
    dpos = meta.get("depth_chart_position") or meta.get("position")
    if order and dpos:
        n = _depth_counts(tbl).get((meta.get("team"), dpos), 0)
        seat = f"{_ordinal(order)} {dpos}"
        if n:
            seat += f" of {n}"
        tip = (f"{_ordinal(order)} {DEPTH_POS.get(dpos, dpos)} on the "
               f"{team} depth chart" + (f", {n} listed" if n else ""))
    yx = meta.get("years_exp")
    if yx == 0:
        exp = "Rookie"
    elif isinstance(yx, int):
        exp = f"{yx} yr{'s' if yx != 1 else ''}"
    else:
        exp = ""
    return team, seat, exp, tip


def bio_line(meta, tbl):
    """'MIN · 2nd RB of 5 · 4 yrs' — prose form for callouts."""
    return " · ".join(b for b in bio_cols(meta, tbl)[:3] if b)


def _pchip(pos):
    pc = POS_COLORS.get(pos, "#8A82A6")
    return (f"<span class='poschip2' style='color:{pc};border-color:{pc}'>"
            f"{esc(pos)}</span>")


def _inj(tag, maxlen=10):
    """Injury chip. Long body parts ('Q-undisclosed') get clipped to a
    readable stub with the full text on hover — an ellipsized 'Q-undis…'
    carries no more information than 'Q' and costs twice the width."""
    if not tag:
        return ""
    short = tag if len(tag) <= maxlen else tag[:maxlen - 1] + "…"
    return (f" <span class='tag inj' title='{esc(tag)}'>"
            f"{esc(short)}</span>")


def player_row(r, c, tbl, dyn=False):
    pos = r["meta"].get("position") or "?"
    adp_s = f"{r['adp']:.0f}" if r["adp"] else "–"
    radp = r.get("radp")
    radp_div = (f"<div class='mono col'>{f'{radp:.0f}' if radp else '–'}</div>"
                if dyn else "")
    team_c, seat_c, exp_c, tip_c = bio_cols(r["meta"], tbl)
    return (
        f"<div class='prow' data-pos='{esc(pos)}' data-vorp='{c['vorp_n']}' "
        f"data-need='{c['need_n']}' data-disc='{c['disc_n']}' data-avail='{c['avail_n']}'>"
        f"<div class='fitcell'><span class='fitnum mono'>–</span>"
        f"<span class='meter'><span class='meterfill'></span></span></div>"
        f"<div class='pname'>{_pchip(pos)}"
        f"<b>{esc((r['meta'].get('full_name') or r['name']).split(' (')[0])}</b>"
        f"<span class='pmeta mono'>age "
        f"{esc(r['meta'].get('age') or '?')}</span>{_inj(r['inj'])}</div>"
        f"<div class='bio mono'>{esc(team_c)}</div>"
        f"<div class='bio' title='{esc(tip_c)}'>{esc(seat_c)}</div>"
        f"<div class='bio'>{esc(exp_c)}</div>"
        f"<div class='mono col'>{r['pts']:.0f}</div>"
        f"<div class='mono col'>{adp_s}</div>"
        f"{radp_div}"
        f"<div class='mono col'>{r['vorp']:+.1f}</div>"
        f"<div class='why'>{esc(c['why'])}</div></div>")


def render_board_tab(d, lg_url):
    # full engine depth (120), not a top-40 slice: a position filter must
    # select from the whole pool, or thin positions show 5 names and lie
    rows = d["rows"]
    comps = fit_components(rows, d.get("my_pids"), d.get("tbl"))
    h = ["<div class='boardgrid'><div class='boardmain'>",
         "<div class='boardhead'><div><b>Ranked by fit to your roster</b>",
         f"<div class='sub2'>Fitline score · {len(rows)} available players "
         "· click a column header to sort</div></div>",
         "<div class='poschips'>"]
    # chips follow the league: IDP slots earn LB/DL/DB chips, a no-K
    # league never shows a K chip. FLEX rides with the offensive skill trio.
    present = {r["meta"].get("position") for r in rows}
    chips = ["ALL"] + [p for p in ("QB", "RB", "WR", "TE", "K", "DEF",
                                   "LB", "DL", "DB") if p in present]
    if {"RB", "WR", "TE"} & present:
        chips.append("FLEX")
    for chip in chips:
        cls = " active" if chip == "ALL" else ""
        h.append(f"<button class='poschip{cls}' data-pos='{chip}'>{chip}</button>")
    h.append("</div></div>")
    h.append("<div class='phead'><div title='0-100 blend of roster need, "
             "value over replacement, market discount, and availability at "
             "your next pick. The sliders on the right change the weights "
             "live'>FIT</div><div>PLAYER</div><div>TEAM</div>"
             f"<div title='{T_DEPTH}'>DEPTH</div>"
             "<div title='NFL seasons played'>EXP</div>"
             f"<div title='{T_PROJ}'>PROJ</div>"
             f"<div title='{adp_tip(d)}'>"
             f"{esc(d['adp_hdr'])}</div>"
             + (f"<div title='{T_RADP}'>rADP</div>" if d["dynasty"] else "")
             + f"<div title='{T_VORP}'>VORP</div>"
             "<div title='The main lever behind the FIT score'>WHY</div>"
             "</div>")
    h.append("<div class='plist'>")
    for r in rows:
        h.append(player_row(r, comps[r["pid"]], d.get("tbl") or {},
                            d["dynasty"]))
    h.append("</div></div>")
    h.append(
        "<aside class='rail'>"
        "<div class='railcard'><div class='railtitle'>FIT SCORE</div>"
        "<div class='railtext'>A 0 to 100 score for how much a player would "
        "help your roster specifically. It blends open-slot need, value over "
        "replacement under this league's scoring, market discount, and "
        "availability.</div></div>"
        "<div class='railcard'><div class='railtitle'>FIT MODEL — weight what "
        "matters</div>")
    for key, label, dflt in (("need", "Roster need", 35),
                             ("vorp", "Value over repl.", 35),
                             ("disc", "Market discount", 20),
                             ("avail", "Availability", 10)):
        h.append(f"<label class='wrow'><span>{label}</span>"
                 f"<input type='range' min='0' max='100' value='{dflt}' "
                 f"class='wslider' data-w='{key}'>"
                 f"<span class='mono wval' data-wval='{key}'>{dflt}</span></label>")
    h.append("<div class='railtext dim'>Sliders re-score and re-rank live.</div>"
             "</div>"
             f"<a class='cta' href='{lg_url}' target='_blank'>Open league in "
             "Sleeper ↗</a></aside></div>")
    return "".join(h)


# Header tooltips shared across tables. Kept plain on purpose: these are
# the one place a friend borrowing the app learns what the numbers mean.
T_PROJ = ("Projected season points in this league&#39;s exact scoring, "
          "trimmed for expected missed games")
T_VORP = ("Points above the best player likely still available at his "
          "position. Negative = bench-level pick, not a bad player")
T_RADP = ("Avg pick in Sleeper redraft drafts — this season only. "
          "Gap vs dADP = the age premium")


def adp_tip(d):
    """League-aware ADP tooltip: dynasty vs redraft market, 2QB market
    for superflex rosters, keeper caveat where kept players skew prices."""
    if d.get("dynasty"):
        tip = ("Avg pick in Sleeper dynasty drafts — prices age and "
               "future value, not just this season")
    else:
        tip = "Avg pick in Sleeper PPR redraft drafts — market price"
    if d.get("superflex"):
        tip += ". 2QB/superflex market: QBs go far earlier than in 1QB"
    if d.get("keeper"):
        tip += ". Kept players never hit this market, so early prices run rich here"
    return tip
T_DEPTH = ("Where he sits on his NFL team&#39;s depth chart right now. "
           "WRs are charted by alignment: LWR/RWR = outside receivers, "
           "SWR = slot. A team runs one of each, so three WRs can all be "
           "listed 1st. Hover any cell for the plain-words version")


def render_draft_tab(d, keepers, lid):
    lg, draft, picks = d["lg"], d["draft"], d["picks"]
    h = []
    if draft:
        h.append(f"<div class='sub2' style='margin-bottom:10px'>draft: "
                 f"{esc(draft.get('status'))} · {fmt_ts(draft.get('start_time'))}"
                 f" · {len(picks)} picks made</div>")
    t = d["turn"]
    status = (draft or {}).get("status")
    if status == "pre_draft":
        teams_n = ((draft.get("settings") or {}).get("teams")
                   or lg.get("total_rosters") or 12)
        slot = my_slot(draft)
        note = ""
        if not slot:
            slot = (teams_n + 1) // 2
            note = " (order not published — middle slot shown)"
        h.append(f"<div class='callout'><b>First-3-pick scenarios — slot "
                 f"{slot}{esc(note)}</b></div>")
        priced = [r for r in d["rows"] if r["adp"]]
        for rnd in (1, 2, 3):
            pos_slot = slot if rnd % 2 == 1 else teams_n - slot + 1
            pick = (rnd - 1) * teams_n + pos_slot
            steal = sorted([r for r in priced if r["adp"] < pick - 12],
                           key=lambda r: r["adp"])[-3:]
            fall = sorted([r for r in priced if pick - 12 <= r["adp"] < pick],
                          key=lambda r: -r["vorp"])[:4]
            expected = sorted([r for r in priced if pick <= r["adp"] <= pick + 14],
                              key=lambda r: -r["vorp"])[:5]
            h.append(f"<div class='scen'><div class='railtitle'>PICK {pick} "
                     f"(ROUND {rnd})</div><table class='mini grid'>"
                     "<colgroup><col style='width:90px'><col>"
                     "<col style='width:48px'><col style='width:96px'>"
                     "<col style='width:58px'>"
                     + "<col style='width:54px'>" * (4 if d["dynasty"] else 3)
                     + "</colgroup>"
                     "<tr><th title='STEAL: usually drafted well before this "
                     "pick, grab him if he is somehow still here. FALL WATCH: "
                     "priced just ahead of you, might slip. EXPECTED: priced "
                     "to be available'>TIER</th><th>PLAYER</th>"
                     f"<th>TEAM</th><th title='{T_DEPTH}'>DEPTH</th>"
                     "<th title='NFL seasons played'>EXP</th>"
                     f"<th class='num' title='{T_PROJ}'>PROJ</th>"
                     f"<th class='num' title='{adp_tip(d)}'>"
                     f"{esc(d['adp_hdr'])}</th>"
                     + (f"<th class='num' title='{T_RADP}'>rADP</th>"
                        if d["dynasty"] else "")
                     + f"<th class='num' title='{T_VORP}'>VORP</th></tr>")
            for label, group in (("STEAL", steal), ("FALL WATCH", fall),
                                 ("EXPECTED", expected)):
                for r in group:
                    pos = r["meta"].get("position") or "?"
                    team, seat, exp, tip = bio_cols(r["meta"], d["tbl"])
                    h.append(f"<tr><td class='dim'>{label}</td>"
                             f"<td>{_pchip(pos)} {esc(r['name'].split(' (')[0])}"
                             f"{_inj(r['inj'])}</td>"
                             f"<td class='bio mono'>{esc(team)}</td>"
                             f"<td class='bio' title='{esc(tip)}'>{esc(seat)}</td>"
                             f"<td class='bio'>{esc(exp)}</td>"
                             f"<td class='num'>{r['pts']:.0f}</td>"
                             f"<td class='num'>{r['adp']:.0f}</td>"
                             + (f"<td class='num'>"
                                f"{f'''{r['radp']:.0f}''' if r.get('radp') else '–'}"
                                f"</td>" if d["dynasty"] else "")
                             + f"<td class='num'>{r['vorp']:+.1f}</td></tr>")
            h.append("</table></div>")
    elif t and t.get("phase") == "depth":
        h.append(f"<div class='callout'><b>Starters filled — depth phase</b> "
                 f"(picks {t['picks'][0]} and {t['picks'][1]}). Every starting "
                 "slot is covered. From here you are drafting bench value "
                 "and players worth stashing.</div>")

        dyn = d["dynasty"]
        ncols = 10 if dyn else 9
        COLS = ("<colgroup><col><col style='width:48px'>"
                "<col style='width:96px'><col style='width:58px'>"
                "<col style='width:44px'>"
                + "<col style='width:54px'>" * (4 if dyn else 3)
                + "<col style='width:210px'></colgroup>")
        radp_th = (f"<th class='num' title='{T_RADP}'>rADP</th>" if dyn else "")
        HDR_ROW = ("<tr><th>PLAYER</th><th>TEAM</th>"
                   f"<th title='{T_DEPTH}'>DEPTH</th>"
                   "<th title='NFL seasons played'>EXP</th>"
                   "<th class='num' title='Age this season. In dynasty, "
                   "younger players hold trade value longer'>AGE</th>"
                   f"<th class='num' title='{T_PROJ}'>PROJ</th>"
                   f"<th class='num' title='{adp_tip(d)}'>"
                     f"{esc(d['adp_hdr'])}</th>"
                   f"{radp_th}"
                   f"<th class='num' title='{T_VORP}'>VORP</th>"
                   "<th class='note'>NOTE</th></tr>")

        def mini_rows(rows_sel, extra=None):
            out = []
            for r in rows_sel:
                pos = r["meta"].get("position") or "?"
                age = r["meta"].get("age") or "?"
                mkt = f"{r['adp']:.0f}" if r["adp"] else "–"
                radp = r.get("radp")
                radp_td = (f"<td class='num'>"
                           f"{f'{radp:.0f}' if radp else '–'}</td>"
                           if dyn else "")
                note = extra(r) if extra else ""
                team, seat, exp, tip = bio_cols(r["meta"], d["tbl"])
                out.append(f"<tr><td>{_pchip(pos)} "
                           f"{esc(r['name'].split(' (')[0])}{_inj(r['inj'])}"
                           f"</td><td class='bio mono'>{esc(team)}</td>"
                           f"<td class='bio' title='{esc(tip)}'>{esc(seat)}</td>"
                           f"<td class='bio'>{esc(exp)}</td>"
                           f"<td class='num'>{esc(age)}</td>"
                           f"<td class='num'>{r['pts']:.0f}</td>"
                           f"<td class='num'>{mkt}</td>"
                           f"{radp_td}"
                           f"<td class='num'>{r['vorp']:+.1f}</td>"
                           f"<td class='note'>{note}</td></tr>")
            return "".join(out)

        pool = d["rows"]
        # the three lists answer different questions — overlap is fine
        best = sorted(pool, key=lambda r: -r["vorp"])[:6]
        young = sorted((r for r in pool
                        if isinstance(r["meta"].get("age"), int)
                        and r["meta"]["age"] <= 24),
                       key=lambda r: -r["pts"])[:6]
        rookies_ = sorted((r for r in pool
                           if r["meta"].get("years_exp") == 0),
                          key=lambda r: -r["pts"])[:4]
        redshirt = [r for r in pool
                    if r["inj"].split("-")[0] in ("OUT", "IR", "PUP")
                    and isinstance(r["meta"].get("age"), int)
                    and r["meta"]["age"] <= 24
                    and r["meta"].get("years_exp") != 0][:2]
        taxi = (rookies_ + redshirt)[:6]

        h.append("<table class='mini grid'>" + COLS + HDR_ROW)
        for title, rows_sel, note_fn in (
                ("BEST VALUE ON THE BOARD", best, None),
                ("YOUNG UPSIDE (24 AND UNDER)", young, None),
                ("TAXI / REDSHIRT STASHES", taxi,
                 lambda r: ("redshirt: the taxi lock costs nothing while he is out"
                            if r["inj"].split("-")[0] in ("OUT", "IR", "PUP")
                            else "rookie, taxi eligible"))):
            if rows_sel:
                h.append(f"<tr class='secrow'><td colspan='{ncols}'>"
                         f"{title}</td></tr>"
                         + mini_rows(rows_sel, note_fn))
        h.append("</table>")
    elif t:
        now = t["now"]
        h.append(f"<div class='callout big'><div class='railtitle'>TURN PLAN "
                 f"— PICKS {t['picks'][0]} AND {t['picks'][1]}</div>"
                 f"<div class='turnnow'>NOW: <b>{esc(now['name'])}</b>"
                 f"{_inj(now['inj'])} <span class='pmeta mono'>"
                 f"{esc(bio_line(now['meta'], d['tbl']))}</span>"
                 f" <span class='mono'>need-adj "
                 f"{now['need_vorp']:.1f} · vorp {now['vorp']:.1f} · proj "
                 f"{now['pts']:.0f}</span></div>")
        if t["next"]:
            h.append(f"<div class='turnnext'>NEXT: {esc(t['next']['name'])} — "
                     f"{esc(d['adp_hdr'])} {t['next']['adp']:.0f} says he waits "
                     f"past pick {t['picks'][1]}</div>")
        if t["waiting"]:
            h.append("<div class='sub2'>also priced to wait: "
                     + ", ".join(f"{esc(c['name'].split(' (')[0])} "
                                 f"({c['adp']:.0f})" for c in t["waiting"])
                     + "</div>")
        h.append("</div>")
        h.append("<div class='railtitle' style='margin-top:16px'>ALTERNATES "
                 "(NEED-ADJUSTED)</div><table class='mini grid'>"
                 "<colgroup><col><col style='width:48px'>"
                 "<col style='width:96px'><col style='width:58px'>"
                 "<col style='width:60px'><col style='width:60px'>"
                 + "<col style='width:60px'>" * (2 if d["dynasty"] else 1)
                 + "</colgroup>"
                 "<tr><th>PLAYER</th><th>TEAM</th>"
                 f"<th title='{T_DEPTH}'>DEPTH</th>"
                 "<th title='NFL seasons played'>EXP</th>"
                 "<th class='num' title='VORP weighted "
                 "by your open roster slots: full credit while you still "
                 "need his position, cut in half once it is filled'>NEED"
                 f"</th><th class='num' title='{T_PROJ}'>PROJ</th>"
                 f"<th class='num' title='{adp_tip(d)}'>"
                     f"{esc(d['adp_hdr'])}</th>"
                 + (f"<th class='num' title='{T_RADP}'>rADP</th>"
                    if d["dynasty"] else "")
                 + "</tr>")
        for r in sorted(d["rows"][:20], key=lambda x: -x["need_vorp"])[1:7]:
            pos = r["meta"].get("position") or "?"
            team, seat, exp, tip = bio_cols(r["meta"], d["tbl"])
            h.append(f"<tr><td>{_pchip(pos)} {esc(r['name'].split(' (')[0])}"
                     f"{_inj(r['inj'])}</td>"
                     f"<td class='bio mono'>{esc(team)}</td>"
                     f"<td class='bio' title='{esc(tip)}'>{esc(seat)}</td>"
                     f"<td class='bio'>{esc(exp)}</td>"
                     f"<td class='num'>{r['need_vorp']:.1f}</td>"
                     f"<td class='num'>{r['pts']:.0f}</td>"
                     f"<td class='num'>{(r['adp'] or 0):.0f}</td>"
                     + (f"<td class='num'>"
                        f"{f'''{r['radp']:.0f}''' if r.get('radp') else '–'}"
                        f"</td>" if d["dynasty"] else "")
                     + "</tr>")
        h.append("</table>")
    k = keepers.get(lid)
    if k and k.get("rules"):
        h.append(f"<div class='railcard' style='margin-top:16px'>"
                 f"<div class='railtitle'>KEEPER RULES</div>"
                 f"<div class='railtext'>{esc(k['rules'])}</div></div>")
    return "".join(h)


def _exp(meta):
    """NFL seasons played, compact. 'R' for rookie so it never reads as
    a zero-value stat."""
    yx = meta.get("years_exp")
    if yx == 0:
        return "R"
    return str(yx) if isinstance(yx, int) else "?"


def _equation_block(P, hz, season=""):
    """The two formulas, written in the table's own column names.

    Every term maps to something on screen except replacement and the
    dADP ladder lookup, and both of those are named rather than hidden
    behind a symbol. A number you cannot reconstruct is a number you
    stop trusting."""
    w = P.get("market_blend", 0.35)
    R = P.get("roster") or {}
    disc = P.get("discount", 0.85)
    same = R.get("collision_mult", 0.6)
    cross = R.get("collision_mult_cross", 0.8)
    cuff = R.get("handcuff_mult", 1.15)
    span = "LEFT" if hz >= 20 else f"min(LEFT, {hz}+1)"
    return (
        "<div class='eqn'>"
        f"<div><span class='eqk'>MODEL</span> = sum over {span} seasons of "
        f"<b>({esc(season)} PTS aged by the curve &minus; replacement)</b>"
        f" &times; {disc}<sup>yr</sup>"
        "<span class='eqn2'>replacement = the Nth best available player at "
        "his position, N = remaining starter demand. Seasons below it "
        "count zero.</span></div>"
        f"<div><span class='eqk'>VALUE</span> = "
        f"<b>{1 - w:.2f} &times; MODEL</b> + <b>{w:.2f} &times; MODEL@dADP</b>"
        f" &nbsp;then&nbsp; &#9888; &times;{same} same-pos / &times;{cross} "
        f"TE-WR &nbsp;&nbsp; &#9873; &times;{cuff}"
        "<span class='eqn2'>MODEL@dADP = the MODEL score of whoever the "
        "market ranks at this player's dADP. No dADP means VALUE = MODEL."
        "</span></div>"
        "</div>")


def _hz_note(hz):
    if hz >= 20:
        return " — full dynasty, his whole remaining career counts"
    return (" — this league keeps a limited roster and churns the rest, "
            "so seasons past that are never yours to own")


def render_dynasty_tab(d):
    """Dynasty value board: multi-year, age-curved, market-blended value
    with tier breaks at value cliffs. Pure view on dynasty_value.py —
    board_data() and the Board tab are untouched; if this import or math
    fails, build() catches it and only this tab degrades."""
    from battle_rhythm.dynasty_value import (load_params, dynasty_value as _dv,
                               years_left, blend_market, tier_breaks,
                               roster_adjust, horizon_for,
                               damped_replacement)
    P = load_params()
    tbl = d["tbl"]
    curves = set(P["curves"])
    repl = d.get("replacement") or {}
    # Damping lives in ages.json and draft_review applied it; this tab did
    # not, so the same player carried two different VALUEs under one name
    # — the exact bug the market-blend fix was supposed to end. Weights are
    # available players per position, matching draft_review.
    _wts = {}
    for _r in d["rows"]:
        _p = (_r.get("meta") or {}).get("position")
        if _p:
            _wts[_p] = _wts.get(_p, 0) + 1
    repl = damped_replacement(repl, P, _wts)
    # A 3-keeper league carries 7 players; the rest churns every year, so
    # a veteran's seasons past the horizon are never yours to own and
    # should not price him down.
    hz = horizon_for(P, dynasty=d.get("dynasty", True),
                     keeper=bool(d.get("keeper")))

    def dv(pos, age, pts, P_, repl_):
        return _dv(pos, age, pts, P_, repl_, horizon=hz)

    # full-pool ladder (available AND gone): dADP is an overall-market
    # rank, so the blend must map onto everyone, or a half-drafted board
    # shifts every market-implied value (display-artifact trap)
    ladder = []
    for pid, pts in d["totals"].items():
        m = tbl.get(pid) or {}
        if m.get("position") in curves and pts > 0:
            ladder.append(dv(m["position"], m.get("age"), pts, P,
                             repl.get(m["position"], 0.0)))
    ladder.sort(reverse=True)

    rows = []
    for r in d["rows"]:
        pos = r["meta"].get("position")
        if pos not in curves:
            continue
        age = r["meta"].get("age")
        rows.append({"r": r, "adp": r["adp"], "meta": r["meta"],
                     "proj": r["pts"],
                     "model_v": dv(pos, age, r["pts"], P,
                                   repl.get(pos, 0.0)),
                     "yrs": years_left(pos, age, P)})
    blend_market(rows, P, ladder)
    roster_adjust(rows, d.get("my_pids"), tbl, P,
                  roster_positions=(d.get("lg") or {}).get(
                      "roster_positions"),
                  repl=repl)
    rows.sort(key=lambda x: -x["value"])
    rows = rows[:60]
    breaks = tier_breaks([x["value"] for x in rows], P)

    h = [f"<div class='callout'><b>Dynasty value — multi-year, "
         f"age-curved, market-blended</b><div class='sub2'>Each remaining "
         f"season contributes his points ABOVE positional replacement, "
         f"aged through his position's curve, discounted "
         f"{P['discount']:.0%}/yr, blended {P['market_blend']:.0%} toward "
         f"the dADP-implied value. Horizon {hz} season"
         f"{'s' if hz != 1 else ''}{_hz_note(hz)}. "
         f"Roster-aware: same-QB pass catchers take a target-collision "
         f"haircut, handcuffs of your RBs get a bump only with standalone "
         f"value. Tier breaks land on value cliffs, not fixed counts. "
         f"Curves, weights and horizons live in ages.json — priors, not "
         f"fitted; tune and refresh.</div>"
         + _equation_block(P, hz, d.get("season") or "") + "</div>",
         "<table class='mini grid roomy'>",
         "<colgroup><col style='width:250px'><col style='width:50px'>",
         "<col style='width:108px'>",
         "<col style='width:44px'><col style='width:44px'>",
         "<col style='width:48px'>",
         "<col style='width:70px'>",
         "<col style='width:62px'>" * 2,
         "<col style='width:58px'><col></colgroup>",
         "<tr><th>PLAYER</th><th>TEAM</th>",
         f"<th title='{T_DEPTH}'>DEPTH</th>",
         "<th class='num' title='Age this season'>AGE</th>",
         "<th class='num' title='NFL seasons already played. R = rookie. "
         "This is experience; the next column is what is LEFT'>EXP</th>",
         "<th class='num' title='Seasons of useful play REMAINING before "
         "his position&#39;s curve hits zero (ages.json end age minus "
         "current age). Not experience — see EXP'>LEFT</th>",
         # derived from the league season so it does not go stale, and
         # named so the contrast with the multi-year columns beside it is
         # obvious: one season of points vs a career valuation
         f"<th class='num' title='{T_PROJ}'>"
         f"{esc(d.get('season') or '')} PTS</th>",
         "<th class='num' title='Multi-year model value: seasons of "
         "points above positional replacement, aged through the curve "
         "and discounted per year. No market input'>MODEL</th>",
         "<th class='num' title='MODEL blended toward the value implied "
         "by his dynasty market price — the market sees role changes and "
         "breakouts the model can&#39;t'>VALUE</th>",
         f"<th class='num' title='{adp_tip(d)}'>{esc(d['adp_hdr'])}</th>",
         "<th class='note' title='From the research store. ! = his own "
         "injury is severe. + = someone ahead of him is hurt or gone. "
         "? = thin or conflicting reporting. Age in days shown when the "
         "note is going stale'>RESEARCH</th>"
         "</tr>"]
    tier = 1
    h.append(f"<tr class='secrow'><td colspan='11'>TIER {tier}</td></tr>")
    for i, x in enumerate(rows):
        r = x["r"]
        pos = r["meta"].get("position") or "?"
        # do NOT name this throwaway _exp — it shadows the _exp() helper
        # used below and fails only at render time
        team, seat, _bio_exp, tip = bio_cols(r["meta"], tbl)
        adp_s = f"{x['adp']:.0f}" if x["adp"] else "–"
        # symbol only — the full sentence lives in the tooltip. The chip
        # is a flag that something applies, not the explanation.
        note = ""
        if x.get("note"):
            collide = "collision" in x["note"]
            note = (f" <span class='rchip {'rwatch' if collide else 'rgain'} "
                    f"sym' title='{esc(x['note'])}'>"
                    f"{'&#9888;' if collide else '&#9873;'}</span>")
        h.append(f"<tr><td>{_pchip(pos)} {esc(r['name'].split(' (')[0])}"
                 f"{_inj(r['inj'])}{note}</td>"
                 f"<td class='bio mono'>{esc(team)}</td>"
                 f"<td class='bio' title='{esc(tip)}'>{esc(seat)}</td>"
                 f"<td class='num'>{esc(r['meta'].get('age') or '?')}</td>"
                 f"<td class='num'>{esc(_exp(r['meta']))}</td>"
                 f"<td class='num'>{esc(x['yrs'] if x['yrs'] is not None else '?')}</td>"
                 f"<td class='num'>{r['pts']:.0f}</td>"
                 f"<td class='num'>{x['model_v']:.0f}</td>"
                 f"<td class='num'><b>{x['value']:.0f}</b></td>"
                 f"<td class='num'>{adp_s}</td>"
                 f"<td class='note'>{research_cell(r['pid'])[0]}</td></tr>")
        if i in breaks and i < len(rows) - 1:
            tier += 1
            h.append(f"<tr class='secrow'><td colspan='11'>TIER {tier}"
                     "</td></tr>")
    h.append("</table>")
    return "".join(h)


def render_season_tabs(lg, season, week, tbl, lg_url):
    """Lineup / Waiver / Trade tab bodies from the weekly engine."""
    from battle_rhythm import weekly as wk
    L = wk.league_brief(lg, season, week, tbl, {"leagues": []})
    lineup = ["<div class='sub2'>Solved on <b>THIS WEEK</b>. A lineup is a "
              "one-week decision; the season column is what waivers and "
              "trades are solved on, and is here for context.</div>",
              "<table class='mini wide'><tr><th>SLOT</th><th>PLAYER</th>"
              "<th title='This week&#39;s projection in this league&#39;s "
              "scoring. Anyone ruled Out is zero.'>WEEK</th>"
              "<th title='Rest-of-season, availability-adjusted. NOT what "
              "the lineup is solved on.'>ROS</th>"
              "<th title='Projected points across weeks 15-17, the fantasy "
              "playoffs'>WK 15-17</th></tr>"]
    for s in L["optimal_starters"]:
        lineup.append(f"<tr><td class='dim'>{esc(s['slot'])}</td>"
                      f"<td>{esc(s['player'])}</td>"
                      f"<td class='mono good'>{s.get('wk', 0.0):.1f}</td>"
                      f"<td class='mono dim'>{s['ros']:.1f}</td>"
                      f"<td class='mono'>{s['playoff_1517']:.1f}</td></tr>")
    lineup.append("</table>")

    waiver = []
    W = L.get("waiver") or {}
    if W.get("faab_left") is not None:
        comps = W.get("comps") or []
        c = (f" · winning bids so far: {len(comps)}, median "
             f"<b class='mono'>{comps[len(comps) // 2]}</b>, max "
             f"<b class='mono'>{comps[-1]}</b>" if comps
             else " · no claim history in this league yet")
        waiver.append(f"<div class='sub2'>FAAB left: <b class='mono'>{W['faab_left']}"
                      f"/{W['faab_budget']}</b>{c}</div>")
    else:
        pos = (f" · you are <b class='mono'>#{W['position']}</b>"
               if W.get("position") else "")
        waiver.append(f"<div class='sub2'>{esc(W.get('mode') or 'waivers')}{pos}"
                      " · no budget to size, one premium claim before you "
                      "drop to the back</div>")
    if L.get("parked"):
        waiver.append(f"<div class='sub2'>{len(L['parked'])} reserve/taxi "
                      "player(s) excluded from every drop</div>")

    def _tags(w):
        t = []
        if w.get("depth"):
            t.append(f"<span class='mono dim'>{esc(w['depth'])}</span>")
        if w.get("stale_role"):
            t.append("<span class='warn' title='Sleeper&#39;s depth chart puts "
                     "him below the role his projection assumes. Read the "
                     "situation before bidding.'>ROLE?</span>")
        if w.get("handcuff_to"):
            t.append(f"<span class='dim'>handcuff to {esc(w['handcuff_to'].split(' (')[0])}</span>")
        if w.get("contested"):
            t.append("<span class='dim' title='top-3 free agent at his position: "
                     "other managers see him too'>contested</span>")
        return " ".join(t)

    any_rows = False
    for title, key in (("TIER 1 — BEATS A STARTER", "waivers_tier1"),
                       ("TIER 2 — BEATS WORST ACTIVE BENCH", "waivers_tier2")):
        if L[key]:
            any_rows = True
            waiver.append(f"<div class='railtitle'>{title}</div>"
                          "<table class='mini wide'><tr><th>ADD</th><th>OVER</th>"
                          "<th>DROP</th><th title='ROS points over the player he "
                          "displaces'>EDGE</th>"
                          "<th title='Sized bid: (budget - hold-back) x this add&#39;s "
                          "share of this week&#39;s tier-1 value. A stated formula, "
                          "recorded so the ledger can correct it.'>BID</th>"
                          "<th></th><th></th></tr>")
            for w in L[key]:
                bid = (f"<b class='mono'>{w['bid']}</b>" if w.get("bid") is not None
                       else "<span class='dim'>—</span>")
                waiver.append(f"<tr><td>{esc(w['add'])}{_inj(w.get('inj'))}</td>"
                              f"<td class='dim'>{esc(w.get('over') or '')}</td>"
                              f"<td>{esc(w.get('drop') or '—')}</td>"
                              f"<td class='mono good'>+{w['gap']:.1f}</td>"
                              f"<td title='{esc(w.get('bid_why') or '')}'>{bid}</td>"
                              f"<td>{_tags(w)}</td>"
                              f"<td><a class='minibtn' href='{lg_url}' "
                              f"target='_blank'>Claim ↗</a></td></tr>")
            waiver.append("</table>")
    if not any_rows:
        waiver.append("<div class='sub2'>no claims clear the bar this week</div>")

    trade = []
    if L["trades"]:
        trade.append("<table class='mini wide'><tr><th>YOU SEND</th>"
                     "<th>YOU GET</th><th>PARTNER</th>"
                     "<th title='Rest-of-season points your lineup gains "
                     "from the swap'>YOU</th>"
                     "<th title='Points their lineup gains. Only trades "
                     "where both sides gain are listed, so the pitch "
                     "writes itself'>THEM</th><th></th></tr>")
        for tr in L["trades"]:
            def side(pfx):
                bits = []
                if tr.get(f"{pfx}_age"):
                    bits.append(f"age {tr[f'{pfx}_age']}")
                if tr.get(f"{pfx}_dadp"):
                    bits.append(f"mkt {tr[f'{pfx}_dadp']:.0f}")
                extra = (f" <span class='dim'>({', '.join(bits)})</span>"
                         if bits else "")
                return f"{esc(tr[pfx])}{extra}"
            trade.append(f"<tr><td>{side('give')}</td><td>{side('get')}</td>"
                         f"<td>{esc(tr['partner'])}</td>"
                         f"<td class='mono good'>+{tr['my_gain']}</td>"
                         f"<td class='mono'>+{tr['their_gain']}</td>"
                         f"<td><a class='minibtn' href='{lg_url}' "
                         f"target='_blank'>Propose ↗</a></td></tr>")
        trade.append("</table><div class='sub2'>proposals where both sides "
                     "gain. Treat them as conversation openers.</div>")
    else:
        trade.append("<div class='sub2'>no both-sides-gain 1-for-1s found</div>")
    for f in L["trade_flags"]:
        trade.append(f"<div class='flag'><b>{esc(f['type'])}</b> — "
                     f"{esc(f['note'])}</div>")
    # L too: the roster pane needs the same brief, and building it twice
    # means two API round trips and two chances to disagree with itself.
    return "".join(lineup), "".join(waiver), "".join(trade), L


def render_roster_tab(L, lg_url):
    """Your roster as it stands, with every upgrade shown beside the player
    it would replace.

    The other in-season tabs each answer half of this. LINEUP prints the
    OPTIMAL nine and says nothing about what you actually have started;
    WAIVER lists adds on their own page, so the starter each one beats is
    a name you have to go and match up by hand. This joins them: one row
    per player you own, and the upgrade sitting next to him.

    Nothing here is new arithmetic. weekly.league_brief already computed
    roster_ranked, the actual-versus-optimal diff, and both waiver tiers;
    the numbers were being discarded at the render.
    """
    h = []

    # ---- the headline: are you leaving points on your own bench --------
    if not L.get("lineup_known"):
        h.append("<div class='sub2'>Sleeper has not published a lineup for "
                 "this league yet, so the rows below compare against the "
                 "OPTIMAL nine rather than what you have started.</div>")
    elif L.get("lineup_diff"):
        h.append(f"<div class='callout'><b>You are leaving "
                 f"{L['lineup_gap']:.1f} points on your bench this week.</b> "
                 f"The swaps below close it — read the ODDS column before "
                 f"acting on a small one.</div>")
        h.append("<table class='mini wide'><tr><th>SIT</th><th>START</th>"
                 "<th title='This week&#39;s points the swap gains'>GAIN</th>"
                 "<th title='How often an edge this size actually wins, "
                 "measured on 2025: 174,776 same-position pairs. A one "
                 "point edge is a coin flip.'>ODDS</th>"
                 "<th></th></tr>")
        for d in L["lineup_diff"]:
            h.append(f"<tr><td class='dim'>{esc(d['out'])} "
                     f"<span class='mono'>{d['out_ros']:.1f}</span></td>"
                     f"<td><b>{esc(d['in'])}</b>{_inj(d.get('in_inj'))} "
                     f"<span class='mono'>{d['in_ros']:.1f}</span></td>"
                     f"<td class='mono good'>+{d['gain']:.1f}</td>"
                     f"<td class='mono'>"
                     + (f"{100*d['conf']:.0f}%" if d.get("conf")
                        else "<span class='dim'>—</span>")
                     + f"</td>"
                     f"<td><a class='minibtn' href='{lg_url}' "
                     f"target='_blank'>Set ↗</a></td></tr>")
        h.append("</table>")
    else:
        h.append("<div class='sub2'>Your lineup matches the optimal one. "
                 "Nothing to move.</div>")

    # ---- upgrades, keyed to the player each one would replace ----------
    # tier 1 beats a projected STARTER and is worth FAAB; tier 2 beats your
    # worst bench body and is churn. His rule, and the reason they are
    # labelled rather than merged into one list.
    up = {}
    for w in L.get("waivers_tier1", []):
        up.setdefault(w["over"], []).append(("1", w))
    for w in L.get("waivers_tier2", []):
        up.setdefault(w["over"], []).append(("2", w))

    h.append("<div class='railtitle'>ROSTER — upgrades shown beside the "
             "player they replace</div>")
    h.append("<table class='mini wide'><tr><th>SLOT</th><th>PLAYER</th>"
             "<th>POS</th>"
             "<th title='This week&#39;s projection. What the lineup is "
             "solved on. Anyone ruled Out is zero.'>WEEK</th>"
             "<th title='Projected rest-of-season points, this league&#39;s "
             "scoring. Waivers and trades are solved on this.'>ROS</th>"
             "<th title='Projected points across weeks 15-17'>WK15-17</th>"
             "<th>STATE</th><th>UPGRADE AVAILABLE</th></tr>")
    for r in L.get("roster_ranked", []):
        known = L.get("lineup_known")
        if not known:
            state = "<span class='dim'>starting</span>" if r["starter"] else "bench"
        elif r["started"] and r["starter"]:
            state = "starting"
        elif r["started"] and not r["starter"]:
            state = "<b class='bad'>SHOULD SIT</b>"
        elif r["starter"] and not r["started"]:
            state = "<b class='good'>SHOULD START</b>"
        else:
            state = "<span class='dim'>bench</span>"
        if r.get("parked"):
            state = "<span class='dim'>reserve/taxi</span>"
        if r.get("depth"):
            state += f" <span class='mono dim'>{esc(r['depth'])}</span>"
        if r.get("stale_role"):
            state += " <span class='warn' title='Depth chart puts him below the role his projection assumes'>ROLE?</span>"

        cell = "<span class='dim'>—</span>"
        rows = up.get(r["player"])
        if rows:
            tier, w = max(rows, key=lambda t: t[1]["gap"])
            cls = "good" if tier == "1" else "dim"
            label = "FAAB" if tier == "1" else "churn"
            cell = (f"<span class='mono {cls}'>+{w['gap']:.1f}</span> "
                    f"{esc(w['add'])}{_inj(w.get('inj'))} "
                    f"<span class='dim'>({label})</span> "
                    f"<a class='minibtn' href='{lg_url}' target='_blank'>"
                    f"Claim ↗</a>")
        # where the week model and the season model disagree, say so — that
        # disagreement is exactly the DJ Moore case and it is information,
        # not an error to hide
        split = ("" if r["starter"] == r.get("ros_starter", r["starter"])
                 else " <span class='dim' title='The season model disagrees "
                      "with the week model about this player'>&#8593;&#8595;"
                      "</span>")
        h.append(f"<tr><td class='dim'>{esc(r.get('slot') or '')}</td>"
                 f"<td>{esc(r['player'])}{_inj(r.get('inj'))}{split}</td>"
                 f"<td class='dim'>{esc(r.get('pos') or '')}</td>"
                 f"<td class='mono good'>{r.get('wk', 0.0):.1f}</td>"
                 f"<td class='mono dim'>{r['ros']:.1f}</td>"
                 f"<td class='mono'>{r.get('playoff', 0.0):.1f}</td>"
                 f"<td>{state}</td><td>{cell}</td></tr>")
    h.append("</table>")
    h.append("<div class='sub2'>SLOT is where this week's optimal lineup "
             "would play him, blank if he is not in it. \u2191\u2193 marks a "
             "player the season model would treat differently. Upgrades are "
             "ranked rest-of-season, because an add is a hold-him-or-not "
             "question, not a start-him-this-Sunday one.</div>")
    return "".join(h)


def render_health_tab(lg, totals, tbl):
    mine = [p for p in (lg.get("my_players") or []) if p]
    # my_players now carries live draft picks merged in by discover(); the
    # rosters endpoint alone stops at the pre-draft roster and left this tab
    # showing keepers only, all draft long (8/17). Keep the two visually
    # distinct so a glance answers "did my pick land" without a reconcile.
    drafted = {str(p) for p in (lg.get("my_drafted") or [])}
    n_d = len(drafted)
    split = (f" · {len(mine) - n_d} kept + {n_d} drafted" if n_d else "")
    h = [f"<div class='railtitle'>POSITION-BY-POSITION{esc(split)}</div>"
         "<div class='healthgrid'>"]
    for pos in ("QB", "RB", "WR", "TE"):
        ps = sorted((p for p in mine
                     if (tbl.get(p) or {}).get("position") == pos),
                    key=lambda p: -totals.get(p, 0))
        pc = POS_COLORS.get(pos, "#8A82A6")
        depth = len(ps)
        best = totals.get(ps[0], 0) if ps else 0
        pips = "".join(f"<span class='pip{' on' if i < min(depth, 5) else ''}'"
                       f" style='--pc:{pc}'></span>" for i in range(5))
        names = []
        for p in ps[:4]:
            m = tbl.get(p) or {}
            mark = ("<span style='color:#b8e02a' title='drafted this year'>"
                    "&#9679;</span> " if str(p) in drafted else "")
            names.append(mark + esc(m.get("full_name") or p)
                         + _inj(injury_tag(m)))
        note = ("no one rostered" if not ps else
                f"best projects {best:.0f} · depth {depth}")
        h.append(f"<div class='hcard'><div class='hpos' style='color:{pc}'>"
                 f"{pos}</div><div class='pips'>{pips}</div>"
                 f"<div class='sub2'>{note}</div>"
                 f"<div class='hnames'>{'<br>'.join(names) or '—'}</div></div>")
    h.append("</div>")
    return "".join(h)


# ------------------------------------------------------------------ build

def build():
    _DEPTH_N.clear()  # recount depth charts on every rebuild
    st = state()
    season, week = st.get("season"), max(st.get("week") or 1, 1)
    data = load_leagues(refresh=True)
    tbl = players()
    keepers = _load_json("keepers.json")
    fonts = _load_json("fonts.json")

    title = "Battle Rhythm"

    switch, panels, live = [], [], []
    from battle_rhythm import paths as _paths
    _ignored = _paths.ignored_ids()
    for i, lg in enumerate(data["leagues"]):
        lid = lg["league_id"]
        if lid in _ignored:
            continue                      # a registered copy, not a room
        accent = LEAGUE_ACCENTS[i % len(LEAGUE_ACCENTS)]
        status = lg.get("status") or "?"
        drafty = status in ("pre_draft", "drafting", "paused")
        lg_url = f"https://sleeper.com/leagues/{lid}"
        dyn_cls = ""
        try:
            d = board_data(lid)
            dyn_cls = " dyn" if d["dynasty"] else ""
            # Sleeper's type flag can't tell a 3-keeper hybrid from full
            # dynasty — keepers.json owns that distinction per league
            d["keeper"] = (d.get("keeper")
                           or bool(keepers.get(lid, {}).get("keeper")))
            tabs = []
            if drafty:
                tabs.append(("draft", "DRAFT", render_draft_tab(d, keepers, lid)))
            tabs.append(("board", "BOARD", render_board_tab(d, lg_url)))
            if d["dynasty"]:
                # additive: a dynasty_value bug degrades this tab only
                try:
                    tabs.append(("dynval", "DYNASTY", render_dynasty_tab(d)))
                except Exception as e:
                    tabs.append(("dynval", "DYNASTY",
                                 f"<div class='sub2'>dynasty value failed: "
                                 f"{esc(e)} — see ages.json / "
                                 "dynasty_value.py</div>"))
            if not drafty:
                lu, wv, tr, L_ = render_season_tabs(lg, season, week, tbl,
                                                    lg_url)
                # The dashboard is where the advice gets READ, so it records
                # too. Dedupe by rec id means a --serve poll every few
                # seconds still writes each rec once, as of its first run.
                try:
                    from battle_rhythm import ledger as _ledger
                    _ledger.record_brief(L_, season, week)
                except Exception as e:
                    print(f"  ledger: not recorded for {lg.get('name')}: {e}")
                # additive, and first among the season tabs: once the season
                # is running "what do I own and what beats it" is the
                # question, not the draft board.
                try:
                    tabs.append(("roster", "ROSTER",
                                 render_roster_tab(L_, lg_url)))
                except Exception as e:
                    tabs.append(("roster", "ROSTER",
                                 f"<div class='sub2'>roster pane failed: "
                                 f"{esc(e)}</div>"))
                tabs += [("lineup", "LINEUP", lu), ("waiver", "WAIVER", wv),
                         ("trade", "TRADE", tr)]
            tabs.append(("health", "HEALTH",
                         render_health_tab(lg, d["totals"], tbl)))
            if status in ("drafting", "paused") and d.get("draft"):
                nxt = d["next_picks"][0][0] if d.get("next_picks") else None
                live.append({"draft_id": d["draft"].get("draft_id"),
                             "picks": len(d["picks"]), "next": nxt,
                             "name": lg["name"]})
        except Exception as e:
            tabs = [("board", "BOARD",
                     f"<div class='sub2'>failed: {esc(e)}</div>")]
        phase_txt = {"pre_draft": "pre-draft", "drafting": "drafting",
                     "paused": "drafting",
                     "in_season": "in season"}.get(status, status)
        switch.append(
            f"<button class='lgbtn' data-lg='lg{i}' style='--ac:{accent}'>"
            f"<span class='lgdot'></span>"
            f"<span class='lgname'>{esc(lg['name'])}</span>"
            f"<span class='lgmeta mono'>{esc(phase_txt)} · "
            f"{esc(lg['total_teams'])}tm</span></button>")
        nav = "".join(f"<button class='tabbtn{' active' if j == 0 else ''}' "
                      f"data-tab='lg{i}-{key}'>{lab}</button>"
                      for j, (key, lab, _) in enumerate(tabs))
        bodies = "".join(f"<div class='tabpane{' active' if j == 0 else ''}' "
                         f"id='lg{i}-{key}'>{body}</div>"
                         for j, (key, _, body) in enumerate(tabs))
        panels.append(f"<div class='lgpanel{dyn_cls}' id='lg{i}' "
                      f"style='--ac:{accent}'>"
                      f"<div class='lghead'><h1>{esc(lg['name'])}</h1>"
                      f"<span class='pill2'>{esc(phase_txt)}</span>"
                      f"<nav class='tabs'>{nav}</nav></div>{bodies}</div>")

    font_css = ""
    if fonts.get("Archivo"):
        font_css += ("@font-face{font-family:'Archivo';font-weight:100 900;"
                     "font-display:swap;src:url(data:font/woff2;base64,"
                     + fonts["Archivo"] + ") format('woff2');}")
    if fonts.get("JetBrains Mono"):
        font_css += ("@font-face{font-family:'JetBrains Mono';"
                     "font-weight:100 800;font-display:swap;"
                     "src:url(data:font/woff2;base64,"
                     + fonts["JetBrains Mono"] + ") format('woff2');}")

    now = datetime.now().strftime("%a %b %d %Y, %I:%M %p")
    doc = ("<!doctype html><html><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{esc(title)}</title><style>{font_css}{CSS}</style></head>"
           "<body><header class='top'>"
           f"<div><div class='apptitle'><span class='mark'></span>"
           f"{esc(title)}</div>"
           f"<div class='sub2'>{len(data['leagues'])} leagues · season "
           f"{esc(season)} wk {week} ({esc(st.get('season_type'))}) · "
           f"generated {now}</div></div>"
           "<div class='topright'>"
           "<span class='livebadge mono' id='livebadge'></span>"
           "<button class='refresh' id='refresh'>&#8635; refresh</button>"
           "</div></header>"
           f"<div class='switch'>{''.join(switch)}</div>"
           f"<main>{''.join(panels)}</main>"
           f"<script>const LIVE={json.dumps(live)};{JS}</script>"
           "</body></html>")
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT} ({len(doc) // 1024} KB)")
    return OUT


CSS = """
:root{color-scheme:dark;
 --bg:#0A0810;--panel:#14101F;--panel2:#1B1533;--edge:#3D3557;--edge2:#4A3F78;
 --ink:#ECE9F5;--ink2:#B4ACCC;--mut:#8A82A6;--dim:#5B5478;
 --lime:#D6FF3F;--amber:#FFC24D;--purple:#C08CFF;--blue:#6FB6FF;
 --green:#5FE0A8;--pink:#FF9EC4;--red:#ff8a80;--limeink:#0A0810;}
@media (prefers-color-scheme: light){:root{color-scheme:light;
 --bg:#F4F2FA;--panel:#FFFFFF;--panel2:#ECE9F5;--edge:#C9C2E0;--edge2:#9A92B8;
 --ink:#14101F;--ink2:#3D3557;--mut:#6E6690;--dim:#8A82A6;
 --lime:#6B8F00;--amber:#B07600;--purple:#7C4DDB;--blue:#2563D6;
 --green:#0E9F6E;--pink:#D0367E;--red:#C93030;--limeink:#FFFFFF;}}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);
 font:14px/1.5 Archivo,system-ui,sans-serif}
.mono{font-family:'JetBrains Mono',Consolas,monospace;font-size:.92em}
.top{display:flex;justify-content:space-between;align-items:center;
 padding:18px 26px 14px}
.apptitle{font:700 19px/1.15 Archivo,sans-serif;letter-spacing:-.01em;
 display:flex;align-items:center;gap:9px}
.mark{width:15px;height:15px;background:var(--lime);border-radius:4px;
 transform:rotate(45deg);flex:none;
 box-shadow:0 0 0 3px color-mix(in srgb, var(--lime) 22%, transparent)}
.sub2{color:var(--mut);font-size:12px}
.topright{display:flex;align-items:center;gap:12px}
.livebadge{font-size:11px;color:var(--dim);letter-spacing:.04em}
.livebadge.hot{color:var(--lime);animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{50%{opacity:.35}}
.refresh{background:transparent;border:1px solid var(--edge2);
 color:var(--ink2);border-radius:8px;padding:8px 15px;
 font:600 12px Archivo,sans-serif;cursor:pointer}
.refresh:hover{border-color:var(--lime);color:var(--lime)}
.refresh[disabled]{opacity:.5;cursor:wait}
.switch{display:flex;gap:8px;padding:6px 26px 16px;flex-wrap:wrap}
.lgbtn{display:flex;align-items:center;gap:8px;background:var(--panel);
 border:1px solid var(--edge);border-radius:10px;padding:9px 14px;
 cursor:pointer;color:var(--ink);font:inherit}
.lgbtn:hover{border-color:var(--ac)}
.lgbtn.active{border-color:var(--ac);background:var(--panel2)}
.lgdot{width:8px;height:8px;border-radius:50%;background:var(--ac);flex:none}
.lgname{font:600 13px Archivo,sans-serif;max-width:170px;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.lgmeta{color:var(--dim);font-size:10.5px}
main{padding:0 26px 44px}
.lgpanel{display:none;background:var(--panel);border:1px solid var(--edge);
 border-radius:14px;overflow:hidden}
.lgpanel.active{display:block}
.lghead{display:flex;align-items:center;gap:12px;padding:16px 22px 0;
 border-bottom:1px solid var(--edge);flex-wrap:wrap}
.lghead h1{font:700 20px/1.1 Archivo,sans-serif;letter-spacing:-.01em;
 padding-bottom:12px}
.pill2{font:600 10.5px Archivo,sans-serif;color:var(--ac);
 border:1px solid var(--ac);border-radius:20px;padding:2px 10px;
 text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.tabs{display:flex;gap:2px;margin-left:auto}
.tabbtn{cursor:pointer;padding:12px 14px;font:600 12px/1 Archivo,sans-serif;
 color:var(--mut);background:none;border:none;
 border-bottom:2px solid transparent}
.tabbtn:hover{color:var(--ink2)}
.tabbtn.active{color:var(--lime);border-bottom-color:var(--lime)}
.tabpane{display:none;padding:18px 22px 26px}
.tabpane.active{display:block}
.boardgrid{display:grid;grid-template-columns:minmax(700px,1fr) 300px;gap:20px}
@media(max-width:980px){.boardgrid{grid-template-columns:1fr}}
.boardhead{display:flex;align-items:flex-start;justify-content:space-between;
 gap:14px;margin-bottom:12px;flex-wrap:wrap}
.poschips{display:flex;gap:5px;flex-wrap:wrap}
.poschip{background:none;border:1px solid var(--edge2);color:var(--mut);
 border-radius:14px;padding:4px 12px;font:600 11px Archivo,sans-serif;
 cursor:pointer}
.poschip.active{background:var(--lime);border-color:var(--lime);
 color:var(--limeink)}
.lgpanel.dyn .phead,.lgpanel.dyn .prow{
 grid-template-columns:104px 1fr 42px 88px 50px 46px 44px 44px 50px 150px}
.phead{display:grid;
 grid-template-columns:104px 1fr 42px 88px 52px 48px 54px 42px 170px;
 gap:10px;padding:5px 8px;font:600 10px Archivo,sans-serif;color:var(--dim);
 letter-spacing:.08em}
.plist{display:flex;flex-direction:column}
.prow{display:grid;
 grid-template-columns:104px 1fr 42px 88px 52px 48px 54px 42px 170px;
 gap:10px;align-items:center;padding:8px;border-top:1px solid var(--edge);
 border-radius:8px}
.prow:hover{background:var(--panel2)}
.prow.hidden{display:none}
.fitcell{display:flex;align-items:center;gap:8px}
.fitnum{font-weight:700;font-size:14px;color:var(--lime);width:30px;
 text-align:right}
.meter{flex:1;height:5px;background:var(--panel2);border-radius:3px;
 overflow:hidden}
.meterfill{display:block;height:100%;background:var(--lime);width:0%}
.pname b{font-weight:600;font-size:13.5px}
.pmeta{color:var(--dim);font-size:11px;margin-left:7px}
.poschip2{font:700 9.5px 'JetBrains Mono',monospace;border:1px solid;
 border-radius:4px;padding:1px 5px;margin-right:7px;vertical-align:1px}
.col{color:var(--ink2);font-size:12.5px;text-align:right}
.why{color:var(--mut);font-size:11.5px;line-height:1.35}
.tag.inj{font:600 9.5px 'JetBrains Mono',monospace;color:var(--amber);
 border:1px solid var(--amber);border-radius:4px;padding:1px 5px;
 margin-left:6px}
.rail{display:flex;flex-direction:column;gap:12px}
.railcard{background:var(--panel2);border:1px solid var(--edge);
 border-radius:12px;padding:14px 16px}
.railtitle{font:700 10.5px Archivo,sans-serif;letter-spacing:.1em;
 color:var(--dim);margin-bottom:8px}
.railtext{font-size:12.5px;color:var(--ink2);line-height:1.5}
.railtext.dim{color:var(--dim);font-size:11.5px;margin-top:8px}
.wrow{display:flex;align-items:center;gap:10px;margin:9px 0;font-size:12px;
 color:var(--ink2)}
.wrow span:first-child{width:104px}
.wslider{flex:1;accent-color:var(--lime)}
.wval{width:26px;text-align:right;color:var(--lime)}
.cta{display:block;text-align:center;background:var(--lime);
 color:var(--limeink);font:700 13px Archivo,sans-serif;border-radius:10px;
 padding:11px;text-decoration:none}
.minibtn{font:600 11px Archivo,sans-serif;color:var(--lime);
 border:1px solid var(--edge2);border-radius:6px;padding:3px 10px;
 text-decoration:none;white-space:nowrap}
.minibtn:hover{border-color:var(--lime)}
.callout{border-left:3px solid var(--lime);background:var(--panel2);
 border-radius:0 10px 10px 0;padding:13px 16px;margin:4px 0 12px}
.callout.big .turnnow{font-size:16px;margin:6px 0 4px}
.turnnow b{color:var(--lime)}
.turnnext{color:var(--ink2);font-size:13px}
.scen{margin:14px 0}
table.mini{border-collapse:collapse;width:auto;min-width:0}
table.mini.grid{table-layout:fixed;width:100%;max-width:860px}
/* the dynasty board carries ten columns including a prose research
   cell; 860px squeezes the field into ellipses */
table.mini.grid.roomy{max-width:1560px}
table.mini.grid.roomy td{padding-right:10px}
table.mini.grid.roomy td.note{white-space:normal;line-height:1.45;
 padding-left:14px}
table.mini.grid.roomy td:first-child{white-space:nowrap;overflow:visible}
table.mini.grid td{overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
table.mini.grid th{overflow:visible;white-space:nowrap}
table.mini.grid td.note{white-space:normal}
table.mini tr.secrow td{font:700 10.5px Archivo,sans-serif;
 letter-spacing:.1em;color:var(--lime);padding:18px 0 6px;
 border-bottom:1px solid var(--edge)}
table.mini tr:first-child+tr.secrow td{padding-top:8px}
table.mini td.num,table.mini th.num{text-align:right;width:64px;
 font-family:'JetBrains Mono',Consolas,monospace;font-size:12.5px}
table.mini td.note,table.mini th.note{color:var(--dim);font-size:11px;
 padding-left:18px}
table.mini.wide{width:100%}
table.mini td,table.mini th{padding:6px 14px 6px 0;
 border-bottom:1px solid var(--edge);font-size:13px;text-align:left}
table.mini th{font:600 10px Archivo,sans-serif;color:var(--dim);
 letter-spacing:.08em}
table.mini th,.phead>div{cursor:pointer;user-select:none}
th.sa::after,div.sa::after{content:' \\25B2';font-size:8px;
 color:var(--lime)}
th.sd::after,div.sd::after{content:' \\25BC';font-size:8px;
 color:var(--lime)}
table.mini th[title],.phead div[title]{cursor:help;
 text-decoration:underline dotted;text-underline-offset:3px;
 text-decoration-color:color-mix(in srgb,var(--dim) 55%,transparent)}
table.mini tr:last-child td{border-bottom:none}
.dim{color:var(--dim);font-size:11px}
.bio{color:var(--ink2);font-size:11px;overflow:hidden;
 text-overflow:ellipsis;white-space:nowrap}
.good{color:var(--green);font-weight:600}
/* SHOULD SIT: a starter the optimum would bench. --red
   already exists in the palette and nothing used it. */
.bad{color:var(--red);font-weight:600}
/* ROLE?: the depth chart disagrees with the projection. Amber, not
   red -- it is a prompt to read the situation, not a verdict. */
.warn{color:var(--amber);font-weight:600;font-size:11px}
.flag{margin:8px 0;padding:9px 13px;border-left:3px solid var(--amber);
 background:var(--panel2);border-radius:0 8px 8px 0;color:var(--ink2);
 font-size:12.5px}
.healthgrid{display:grid;
 grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.hcard{background:var(--panel2);border:1px solid var(--edge);
 border-radius:12px;padding:14px 16px}
.hpos{font:700 13px 'JetBrains Mono',monospace;margin-bottom:8px}
.pips{display:flex;gap:4px;margin-bottom:8px}
.pip{width:16px;height:5px;border-radius:3px;background:var(--edge)}
.pip.on{background:var(--pc)}
.hnames{font-size:12px;color:var(--ink2);line-height:1.7;margin-top:6px}
.rchip{display:inline-block;width:14px;height:14px;line-height:14px;
 text-align:center;border-radius:4px;font:700 10px 'JetBrains Mono',monospace;
 margin-right:6px;vertical-align:1px}
.rchip.rblock{background:var(--red);color:var(--bg)}
.rchip.rgain{background:var(--green);color:var(--bg)}
.rchip.rwatch{background:var(--amber);color:var(--bg)}
.rchip.sym{cursor:help;font-size:11px;margin-left:2px;margin-right:0}
.eqn{margin-top:11px;padding:9px 12px;border-radius:8px;
 background:color-mix(in srgb, var(--bg) 55%, transparent);
 border:1px solid var(--edge)}
.eqn>div{font:12px/1.7 'JetBrains Mono',Consolas,monospace;
 color:var(--ink2)}
.eqn>div+div{margin-top:5px}
.eqn b{color:var(--ink);font-weight:600}
.eqn sup{font-size:9px}
.eqk{display:inline-block;min-width:52px;color:var(--lime);font-weight:700}
.eqn2{display:block;font:11px/1.5 Archivo,sans-serif;color:var(--dim);
 margin:2px 0 0 52px}
.rnote{color:var(--ink2);font-size:11px}
table.mini td.note .rnote{white-space:normal}
"""

JS = """
const $=s=>[...document.querySelectorAll(s)];
const lgbtns=$('.lgbtn'),panels=$('.lgpanel');
function pickLg(b){lgbtns.forEach(x=>x.classList.toggle('active',x===b));
 panels.forEach(p=>p.classList.toggle('active',p.id===b.dataset.lg));}
if(lgbtns.length){
 lgbtns.forEach(b=>b.addEventListener('click',()=>pickLg(b)));
 pickLg(lgbtns.find(b=>{const p=document.getElementById(b.dataset.lg);
  return p&&p.querySelector("[id$='-draft']");})||lgbtns[0]);}
document.addEventListener('click',e=>{
 const tb=e.target.closest('.tabbtn');if(!tb)return;
 const panel=tb.closest('.lgpanel');
 panel.querySelectorAll('.tabbtn').forEach(x=>
  x.classList.toggle('active',x===tb));
 panel.querySelectorAll('.tabpane').forEach(p=>
  p.classList.toggle('active',p.id===tb.dataset.tab));});
document.addEventListener('click',e=>{
 const ch=e.target.closest('.poschip');if(!ch)return;
 const pane=ch.closest('.tabpane');
 pane.querySelectorAll('.poschip').forEach(x=>
  x.classList.toggle('active',x===ch));
 const want=ch.dataset.pos;
 pane.querySelectorAll('.prow').forEach(r=>{
  const p=r.dataset.pos;
  const show=want==='ALL'||p===want||
   (want==='FLEX'&&['RB','WR','TE'].includes(p));
  r.classList.toggle('hidden',!show);});});
function rescore(pane){
 const w={};let sum=0;
 pane.querySelectorAll('.wslider').forEach(s=>{
  w[s.dataset.w]=+s.value;sum+=+s.value;});
 if(sum===0)sum=1;
 const rows=[...pane.querySelectorAll('.prow')];
 rows.forEach(r=>{
  const f=(w.need*r.dataset.need+w.vorp*r.dataset.vorp+
           w.disc*r.dataset.disc+w.avail*r.dataset.avail)/sum;
  r._fit=Math.round(100*f);
  r.querySelector('.fitnum').textContent=r._fit;
  const fill=r.querySelector('.meterfill');
  fill.style.width=r._fit+'%';
  const hue=r._fit>=70?'var(--lime)':r._fit>=45?'var(--amber)':'var(--dim)';
  fill.style.background=hue;
  r.querySelector('.fitnum').style.color=hue;});
 const list=pane.querySelector('.plist');
 rows.sort((a,b)=>b._fit-a._fit).forEach((r,i)=>{
  r.dataset.oi=i;list.appendChild(r);});
 list._oi=1;
 pane.querySelectorAll('.wval').forEach(v=>{
  const s=pane.querySelector(".wslider[data-w='"+v.dataset.wval+"']");
  if(s)v.textContent=s.value;});}
$('.tabpane').forEach(p=>{if(p.querySelector('.plist'))rescore(p);});
document.addEventListener('input',e=>{
 const s=e.target.closest('.wslider');if(!s)return;
 rescore(s.closest('.tabpane'));});
const rb=document.getElementById('refresh');
async function doRefresh(){
 if(location.protocol==='file:')return false;
 if(rb){rb.disabled=true;rb.textContent='refreshing\\u2026';}
 try{const r=await fetch('/refresh',{method:'POST'});
  if(r.ok){location.reload();return true;}
  if(rb){rb.textContent='failed — see terminal';rb.disabled=false;}}
 catch(e){if(rb){rb.textContent='server gone — rerun --serve';
  rb.disabled=false;}}
 return false;}
if(rb){if(location.protocol==='file:'){
 rb.title='refresh needs the local server: python dashboard.py --serve';
 rb.addEventListener('click',()=>alert(rb.title));}
else{rb.addEventListener('click',doRefresh);}}
/* column sorting: click a header to sort ascending, again for descending.
   Depth-phase sections (secrow markers) each sort within themselves. */
function cellVal(el){
 if(!el)return '';
 const t=el.textContent.trim();
 const n=parseFloat(t.replace('+',''));
 return isNaN(n)?t.toLowerCase():n;}
function rowCmp(idx,asc){return (r1,r2)=>{
 const a=cellVal(r1.children[idx]),b=cellVal(r2.children[idx]);
 const an=typeof a==='number',bn=typeof b==='number';
 if(an&&bn)return (asc?1:-1)*(a-b);
 if(an)return -1;if(bn)return 1;      // missing values sink either way
 return (asc?1:-1)*(a<b?-1:a>b?1:0);};}
function oiCmp(asc){return (r1,r2)=>
 (asc?1:-1)*((+r1.dataset.oi)-(+r2.dataset.oi));}
/* three-state cycle: 1st click ascending, 2nd descending, 3rd back to
   the page's default order (rows remember their original index). */
document.addEventListener('click',e=>{
 const th=e.target.closest('table.mini th');if(!th)return;
 const table=th.closest('table');
 const idx=[...th.parentNode.children].indexOf(th);
 if(!table._oi){let i=0;
  table.querySelectorAll('tr').forEach(r=>{
   if(r.querySelector('td')&&!r.classList.contains('secrow'))
    r.dataset.oi=i++;});
  table._oi=1;}
 const state=th.classList.contains('sa')?'sa'
  :th.classList.contains('sd')?'sd':'';
 table.querySelectorAll('th').forEach(x=>x.classList.remove('sa','sd'));
 const cmp=state===''?rowCmp(idx,true)
  :state==='sa'?rowCmp(idx,false):oiCmp(true);
 if(state==='')th.classList.add('sa');
 else if(state==='sa')th.classList.add('sd');
 let seg=[],anchor=th.parentNode;
 const flush=()=>{seg.sort(cmp);
  for(let i=seg.length-1;i>=0;i--)
   anchor.parentNode.insertBefore(seg[i],anchor.nextSibling);
  seg=[];};
 [...table.querySelectorAll('tr')].forEach(r=>{
  if(r===th.parentNode)return;
  if(r.classList.contains('secrow')){flush();anchor=r;}
  else if(r.querySelector('td'))seg.push(r);});
 flush();});
document.addEventListener('click',e=>{
 const hd=e.target.closest('.phead>div');if(!hd)return;
 const phead=hd.parentNode,list=phead.nextElementSibling;
 if(!list||!list.classList.contains('plist'))return;
 const idx=[...phead.children].indexOf(hd);
 if(!list._oi){[...list.querySelectorAll('.prow')].forEach((r,i)=>
  r.dataset.oi=i);list._oi=1;}
 const state=hd.classList.contains('sa')?'sa'
  :hd.classList.contains('sd')?'sd':'';
 [...phead.children].forEach(x=>x.classList.remove('sa','sd'));
 const cmp=state===''?rowCmp(idx,true)
  :state==='sa'?rowCmp(idx,false):oiCmp(true);
 if(state==='')hd.classList.add('sa');
 else if(state==='sa')hd.classList.add('sd');
 [...list.querySelectorAll('.prow')].sort(cmp)
  .forEach(r=>list.appendChild(r));});
/* live draft poll: one public GET per drafting league every 30s; a full
   server-side rebuild happens only when a new pick actually lands */
const badge=document.getElementById('livebadge');
if(typeof LIVE!=='undefined'&&LIVE.length&&badge){
 const baseTitle=document.title;let busy=false;
 async function poll(){
  if(busy)return;busy=true;
  try{
   const parts=[];let hot=false,fresh=false;
   for(const L of LIVE){
    const r=await fetch('https://api.sleeper.app/v1/draft/'
     +L.draft_id+'/picks');
    if(!r.ok)continue;
    const made=(await r.json()).length;
    const until=L.next?L.next-made-1:null;
    let txt=L.name+' LIVE \\u00b7 pick '+(made+1);
    if(until!==null)txt+=until<=0?' \\u2014 YOU ARE UP'
     :' \\u00b7 '+until+' until you';
    parts.push(txt);
    if(until!==null&&until<=3)hot=true;
    if(made>L.picks){L.picks=made;fresh=true;}}
   if(parts.length)badge.textContent=parts.join('   |   ');
   badge.classList.toggle('hot',hot);
   document.title=(hot?'\\uD83D\\uDD14 ':'')+baseTitle;
   if(fresh){await doRefresh();return;}}
  catch(e){badge.textContent='live poll blocked';}
  busy=false;}
 poll();setInterval(poll,30000);}
"""


def serve(port=8787):
    """python dashboard.py --serve — refresh button reruns build() live."""
    import http.server

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body=b"", ctype="text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html", "/dashboard.html"):
                self._send(200, OUT.read_bytes())
            else:
                self._send(404, b"not found")

        def do_POST(self):
            if self.path == "/refresh":
                try:
                    build()
                    self._send(200, b"ok")
                except Exception as e:
                    print(f"refresh failed: {e}")
                    self._send(500, str(e).encode())
            else:
                self._send(404, b"not found")

        def log_message(self, *a):
            pass

    build()
    url = f"http://localhost:{port}/"
    print(f"serving {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        path = build()
        if "--open" in sys.argv:
            webbrowser.open(path.as_uri())
