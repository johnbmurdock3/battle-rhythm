# Battle Rhythm

A personal command center for Sleeper fantasy football. One Python toolkit
that reads your leagues, scores every player with each league's exact
scoring settings, and turns that into draft boards, live pick advice, weekly
lineup/waiver/trade briefs, keeper math, and a single-file HTML dashboard.

Everything is **read-only**. The tools never touch your lineup, never make
waiver claims, never draft for you. Action buttons deep-link to sleeper.com
where you make the actual moves. You will never be asked for a password or
API key — Sleeper's read API is public. If you have a Sleeper "push key",
it does not belong anywhere in this project. Don't paste it into config
files, don't paste it into a chat.

## Setup

You need Python 3.10+ and nothing else — no packages to install, the whole
toolkit is standard library.

1. Put these files in a folder.
2. Create `config.json` with your Sleeper username:

       { "username": "yourname" }

   (Or set the `SLEEPER_USERNAME` environment variable.)
3. Run `python br.py discover` once. It finds your leagues for
   the current season and caches them.
4. Run `python br.py dash --serve`. Your browser opens the dashboard.

First run is slow (it downloads the ~5MB player table and projections);
after that everything works from cache and refreshes are quick.

## The dashboard

`python br.py dash --serve` runs a tiny local server with a working
refresh button and, during a live draft, a poller that watches the pick
feed, rebuilds when picks land, and flashes when you're within three picks
of the clock. One league at a time via the switcher; tabs follow each
league's phase:

- **Draft** (before and during drafts) — pre-draft: first-3-pick scenarios
  from your draft slot. In-flight: a turn plan naming the pick to make now
  and the one that waits, or depth-phase shortlists once your starters are
  filled.
- **Board** — every available player ranked by FIT, a 0–100 blend of your
  roster need, value over replacement, market discount, and availability.
  The weight sliders re-score live. Click any column header to sort
  (third click restores default order). Hover any header for what the
  number means.
- **Lineup / Waiver / Trade** (in season) — optimal starters, two tiers of
  waiver claims with the drop named, and 1-for-1 trades where both sides
  gain (so the pitch writes itself).
- **Health** — injury pips across your roster.

The generated `out/dashboard.html` is self-contained. You can open it without
the server; you just lose the refresh button and live polling.

## The command line

Same engine, terminal output:

    python br.py board <league>        # draft board with VORP + ADP
    python br.py board <league> --pos RB
    python br.py watch <league>        # poll a live draft, bell on your turn
    python br.py find <name>           # is he available, what's he worth
    python br.py explain <league> <name>   # stat-by-stat score breakdown
    python br.py rookies <league>      # rookie class + taxi lottery tickets
    python br.py sheet <league>        # printable cheat sheet
    python br.py rhythm                             # what to run today
    python br.py weekly                             # lineup/waiver/trade brief, all leagues
    python br.py recap <league>                     # grade your own picks, the morning after
    python br.py managers <league>                  # who in the room reaches for vets
    python br.py keeper <league>                    # keeper recommendation
    python br.py test                           # offline test suite, no network
    python br.py                                # every command, grouped

`<league>` takes a name fragment, so `board hybrid` works.

## How the numbers are made

- **Scoring** is a dot product of Sleeper's projected stat line against your
  league's scoring settings — verified exact against the app, including
  bucket stats (rec_0_4 and friends), first downs, and DEF points-allowed
  brackets. IDP leagues work the same way: idp_tkl, idp_sack and the rest
  score like any other stat.
- **Availability**: weekly projections assume a player plays; season
  aggregates carry the injury haircut. The ratio between them discounts
  every projection, which is why a hurt star projects lower here than raw
  weekly numbers suggest — and matches what the Sleeper app shows.
- **VORP** measures points above the best player likely still available at
  the position, with remaining demand recomputed as the draft burns picks.
- **ADP** is Sleeper's real market. Dynasty-typed leagues price with dynasty
  ADP and show redraft ADP beside it (the gap is the age premium). Superflex
  leagues price with the 2QB market. Keeper leagues get a caveat: kept
  players never reach the market, so early prices run rich.

## League rules as data

`data/keepers.json` holds per-league rules: a prose description shown on the
Draft tab and a `"keeper": true` flag that turns on the keeper price
caveat. Edit it to match your leagues; the engine reads Sleeper's own
settings for everything else (scoring, rosters, superflex, dynasty type).

IDP leagues need no configuration: if your league rosters LB/CB/DL slots
(any of the usual spellings — CB and S count as DB, DE and DT as DL), the
board, projections, position chips, and depth charts pick them up.

## Claude Desktop (optional)

`mcp_server.py` exposes the toolkit to Claude Desktop so you can ask
questions in plain English mid-draft. Merge the `mcpServers` entry from
`claude_desktop_config.json` into your own Claude config (found under
Settings → Developer), adjusting the path. Quit Claude fully (system tray,
not just the window) and reopen. After any code change, the same full
restart applies — the server keeps old code in memory otherwise.

## Files

Sorted by how hard each thing is to get back, not by topic.

    br.py               the one command. `python br.py` lists the rest.
    mcp_server.py       Claude Desktop bridge — stays at the root because
                        Claude's own config file holds its absolute path
    test_all.py         offline regression tests

    battle_rhythm/      the toolkit
      sleeper_client.py   API client, scoring engine, league discovery
      draft_helper.py     boards, VORP, ADP, turn plan, watch, explain
      lineup_value.py     what a player adds to YOUR lineup, by simulation
      dynasty_value.py    age curves, multi-season value
      keeper.py           keeper optimizer (rules vary per league)
      weekly.py           lineup / waiver / trade engine
      dashboard.py        the HTML dashboard + local server
      roster_snapshot.py  writes roster.md
      paths.py            where everything lives — the only path authority
      ...                 `python br.py` names the rest

    config.json         your Sleeper username
    roster.md           current roster state (regenerated, but kept at
                        the root on purpose — see CLAUDE.md)

    data/               authored truth, edited by hand
      keepers.json        your league rules, as data
      ages.json           aging curves and dynasty parameters
      byes.json           bye weeks — season data, replace every year
      fonts.json          embedded fonts for the dashboard (optional)
      measured/           measured off real drafts (room_bias.json)

    leagues/            per-league material
      _index.json         slug -> league id -> folder. The league key.
      <slug>/brief.md     that league's draft plan

    dossiers/           accumulated player research
    fixtures/           captured ground truth for the scoring tests
    docs/               reference: columns, design brief, research plan
    archive/            spent scratch, kept but not read

    out/                everything the tools generate. Disposable and
                        gitignored — delete it any time, it rebuilds.

Caches live in `~/.sleeper_cache/` — safe to delete any time; the next run
rebuilds them.

Nothing writes outside `out/` except `roster.md`. A generated file
anywhere else is a bug in the writer, not a filing mistake.

## Does the engine score what Sleeper scores?

Yes, checked every week against Sleeper's own points. See [docs/ENGINE_CHECK.md](docs/ENGINE_CHECK.md).
