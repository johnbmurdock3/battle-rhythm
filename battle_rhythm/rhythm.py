"""
The battle rhythm itself — what to run today, and what is coming.

  python br.py rhythm                # today, this week, and every open draft
  python br.py rhythm --week         # the whole week, no "today" section
  python br.py rhythm --selftest     # offline, no network

The toolkit had eighteen commands and no answer to "what should I be doing
right now." Everything else here is a tool; this is the schedule that says
which tool and when, so the season runs on a cadence instead of on
remembering.

Offline by design. It reads leagues/_index.json and the calendar, never the
API, so it works before coffee and on a plane. Anything it tells you to run
is what talks to Sleeper.

THE CADENCE, as it actually is:

  Tuesday    waivers. Claims process Wednesday morning, so Tuesday night is
             the last look with the full week of injury news in it.
  Thursday   lineups. Before the Thursday night kickoff locks anyone.
  Sunday     last look, ~90 minutes before the early games.
  Draft day  the card, then the board, live.
  The day
  after a
  draft      recap once, and room_bias once. Both are one-shot and both are
             forgotten if they are not on a list.
"""

import datetime
import sys

WAIVERS, LINEUPS, LASTLOOK = "waivers", "lineups", "last look"

# weekday() -> (label, command, why)
WEEKLY = {
    1: (WAIVERS, "br.py weekly",
        "claims process Wednesday morning; this is the last look with the "
        "full week of injury news in it"),
    3: (LINEUPS, "br.py weekly",
        "before Thursday night kickoff locks anyone"),
    6: (LASTLOOK, "br.py weekly",
        "inactives land ~90 minutes before the early games"),
}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday"]


def parse_draft_date(v):
    """'2026-09-06' -> date. 'done', 'live', null and free text -> None."""
    if not isinstance(v, str):
        return None
    head = v.strip()[:10]
    try:
        return datetime.date.fromisoformat(head)
    except ValueError:
        return None


def upcoming_drafts(leagues, today):
    """[(slug, meta, date_or_None)] for leagues that have not drafted,
    dated ones first in date order, undated after."""
    out = []
    for slug, m in leagues.items():
        if (m.get("status") or "") != "pre_draft":
            continue
        d = parse_draft_date(m.get("drafts"))
        if d and d < today:
            d = None          # a date that has passed tells you nothing
        out.append((slug, m, d))
    out.sort(key=lambda r: (r[2] is None, r[2] or today))
    return out


def week_plan(today, drafts):
    """[(date, label, command, why)] for the next seven days, in order."""
    rows = []
    by_day = {}
    for slug, m, d in drafts:
        if d and 0 <= (d - today).days < 7:
            by_day.setdefault(d, []).append((slug, m))
    for i in range(7):
        day = today + datetime.timedelta(days=i)
        for slug, m in by_day.get(day, []):
            rows.append((day, "DRAFT", f"br.py board {slug}",
                         f"{m.get('name')} — read leagues/{slug}/brief.md first"))
        job = WEEKLY.get(day.weekday())
        if job:
            rows.append((day, job[0], job[1], job[2]))
    return rows


def render(today, leagues, show_today=True):
    lines = []
    drafts = upcoming_drafts(leagues, today)
    lines.append(f"── {DAYS[today.weekday()]}, "
                 f"{today.strftime('%B %-d' if sys.platform != 'win32' else '%B %#d')}")

    plan = week_plan(today, drafts)
    if show_today:
        mine = [r for r in plan if r[0] == today]
        lines.append("")
        lines.append("  TODAY")
        if mine:
            for _, label, cmd, why in mine:
                lines.append(f"    {label:<9} python {cmd}")
                lines.append(f"    {'':<9} {why}")
        else:
            nxt = next((r for r in plan if r[0] > today), None)
            if nxt:
                lines.append(f"    nothing scheduled. Next: {DAYS[nxt[0].weekday()]}"
                             f" — {nxt[1]}.")
            else:
                lines.append("    nothing scheduled.")

    ahead = [r for r in plan if r[0] > today]
    if ahead:
        lines.append("")
        lines.append("  THIS WEEK")
        for day, label, cmd, _ in ahead:
            lines.append(f"    {DAYS[day.weekday()][:3]}  {label:<9} python {cmd}")

    if drafts:
        lines.append("")
        lines.append("  DRAFTS NOT YET RUN")
        for slug, m, d in drafts:
            when = d.isoformat() if d else "no date set"
            slot = m.get("slot")
            note = f"slot {slot}" if slot else "SLOT NOT PUBLISHED — check before you plan picks"
            lines.append(f"    {slug:<14} {when:<12} {note}")
        lines.append("")
        lines.append("    the morning after each one, once:")
        lines.append("      python br.py recap <league>    where you beat the board, where you reached")
        lines.append("      python br.py rooms <league>    replaces the room_shave prior with a measurement")

    excluded = [s for s, m in leagues.items() if m.get("type") == "best-ball"]
    if excluded:
        lines.append("")
        lines.append(f"  not in the cadence: {', '.join(excluded)} "
                     "(best ball — no lineup, no waivers, no trades)")
    return "\n".join(lines)


def run(argv):
    from battle_rhythm import paths
    today = datetime.date.today()
    for a in argv:
        d = parse_draft_date(a)
        if d:
            today = d              # --date 2026-09-06, for checking a plan
    print(render(today, paths.leagues(), show_today="--week" not in argv))


def selftest():
    n = 0

    def check(label, cond):
        nonlocal n
        print(f"  {'ok ' if cond else 'XX '} {label}")
        assert cond, label
        n += 1

    L = {
        "lg04": {"name": "LG04", "status": "pre_draft",
                    "drafts": "2026-09-06", "slot": 10},
        "lg06": {"name": "LG06", "status": "pre_draft",
                         "drafts": None},
        "lg02": {"name": "LG02", "status": "pre_draft", "drafts": None},
        "lg03": {"name": "LG03", "status": "in_season",
                           "drafts": "2026-08-18 (done)"},
        "best-ball": {"name": "BB", "status": "in_season", "type": "best-ball",
                      "drafts": "done"},
    }
    wed = datetime.date(2026, 9, 2)

    check("a date with trailing prose still parses",
          parse_draft_date("2026-08-18 (done)") == datetime.date(2026, 8, 18))
    check("'live' and null are not dates",
          parse_draft_date("live") is None and parse_draft_date(None) is None)

    d = upcoming_drafts(L, wed)
    check("only pre-draft leagues are listed", len(d) == 3)
    check("dated drafts sort ahead of undated", d[0][0] == "lg04"
          and d[0][2] == datetime.date(2026, 9, 6))
    check("in-season leagues are not waiting to draft",
          "lg03" not in [s for s, _, _ in d])

    plan = week_plan(wed, d)
    labels = [(r[0].weekday(), r[1]) for r in plan]
    check("Thursday is lineups", (3, LINEUPS) in labels)
    check("Sunday carries the draft AND the last look",
          (6, "DRAFT") in labels and (6, LASTLOOK) in labels)
    check("the draft comes before the lineup job on the same day",
          labels.index((6, "DRAFT")) < labels.index((6, LASTLOOK)))
    check("next Tuesday is inside the seven-day window",
          (1, WAIVERS) in labels)

    out = render(wed, L)
    check("today has nothing and says what is next",
          "nothing scheduled" in out and "Thursday" in out)
    check("an unpublished slot is called out rather than left blank",
          "SLOT NOT PUBLISHED" in out)
    check("the known slot is shown", "slot 10" in out)
    check("best ball is named as excluded, not silently dropped",
          "best-ball" in out and "no lineup" in out)
    check("the one-shot post-draft jobs are on the list",
          "br.py recap" in out and "br.py rooms" in out)

    # A date that has already passed is not a plan.
    stale = {"x": {"name": "X", "status": "pre_draft", "drafts": "2026-01-01"}}
    check("a draft date in the past is dropped, not counted down to",
          upcoming_drafts(stale, wed)[0][2] is None)

    print(f"\nselftest PASSED  ({n})")
    raise SystemExit(0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()
    run(a)
