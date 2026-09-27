# Starter prompt — LG05

Paste this into a fresh conversation.

---

I'm dirtymurdock. Working in `C:\Users\johnb\workspace\Sleeper`.

Read in this order before doing anything: **CLAUDE.md** (rules and
hard-won lessons), **HANDOFF.md** (current state), **roster.md**, and
**lg05_brief.md** — that last one is the finished draft card for my
other Hybrid and is the template for what I want here.

**Task: build the same plan for LG05**, league id
`9000000000000000019`. Nothing exists for it yet — the 447-player
research queue and the brief were both built for the *other* Hybrid.

Start by running these and reading the output, not by asking me what
they'll say:

    python roster_snapshot.py
    python superflex_adp.py "LG03-LG05 🦸"
    python lineup_value.py "LG03-LG05 🦸" --slot <my slot>

What's different about this league versus the one we just finished:

- **My QB room is genuinely set** — Lamar Jackson and Jayden Daniels
  hold QB and SUPER_FLEX. In the other Hybrid the superflex was a
  15-point body, which is why that plan opened with a quarterback. Don't
  copy that conclusion here.
- **I need RB2 and a FLEX.** One running back rostered (Kenneth Walker).
- **Oronde Gadsden and Kyle Williams come off expired redshirts** onto
  the active roster. Gadsden is my only tight end.
- Two taxi seats open, superflex, 3 keepers + 2 drafted rookies, and the
  commissioner runs a 10-round draft then a second one to fill out.

Two things I haven't told you: the **draft date and my slot**. Ask me.

Before you recommend a pick, check the depth chart for every player I
already roster — that caught Milroe as Seattle's QB3 last session, after
the projections had been telling us for hours and nobody looked.

Standards: advisor, not assistant. Lead with the useful thing, disagree
with structure, name what would flip your answer. Verify with tools
rather than memory — a check that hasn't fired on a known-bad case isn't
evidence. League rules that aren't in the API live in `keepers.json`;
read them before reasoning about roster mechanics.
