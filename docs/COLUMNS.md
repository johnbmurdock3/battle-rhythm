# Dynasty tab — what each column actually computes

Written 8/11 by reading the code, not from memory. If a number looks
wrong, this is the file that tells you which knob moved it.

Column order:

    PLAYER  TEAM  DEPTH  AGE  EXP  LEFT  <season> PTS  MODEL  VALUE
    dADP  RESEARCH

---

## PLAYER

Name from Sleeper's player table, with up to three chips:

- position chip, colour-coded
- injury chip from `injury_tag()` — Sleeper's `injury_status` plus
  `injury_body_part`, e.g. `Q-ankle`. Clipped at 10 characters, full
  text on hover.
- a roster-context flag, symbol only, sentence on hover:
  **⚠** target collision, **⚑** handcuff

## TEAM / DEPTH

`team` straight from the player table. DEPTH is
`depth_chart_order` and `depth_chart_position` rendered as
"2nd RB of 5", where the 5 is how many players on that team hold an
order at that depth slot. Receivers are charted by alignment (LWR,
RWR, SWR), so three receivers can each be listed 1st.

## AGE / EXP / LEFT

    AGE   player table `age`
    EXP   player table `years_exp`; "R" when 0
    LEFT  ages.json curves[pos].end  −  age, floored at 0

LEFT is **seasons of useful play remaining**, not experience. For a WR
with `end: 34`, a 26-year-old shows 8.

## \<season\> PTS

This season's projection under **your league's exact scoring**:

    for each week 1..18:
        points += dot(weekly projected stat line, league scoring_settings)
    points *= availability_ratio

`availability_ratio` = the season aggregate's generic points divided by
the summed weekly generic points, clamped to [0.5, 1.05]. The weekly
feed projects each game as if the player plays it; the season aggregate
carries the injury haircut. The ratio is how a hurt star projects lower
here than raw weekly numbers suggest — and why it matches the app.

Players outside a position's top ~100 get no ratio and default to 1.0.

## MODEL

Discounted multi-year **surplus over positional replacement**. No market
input at all.

    base = curve(pos, age)
    for t = 0 .. horizon:
        m       = curve(pos, age + t)
        surplus = proj * (m / base) − replacement[pos]
        if surplus > 0:
            MODEL += surplus * discount^t

Pieces:

- **curve()** — 1.0 across the position's peak plateau; `rise^(peak_start
  − age)` below it; above it, the running product of `decline` per year
  until `cliff_age`, then `cliff_rate` per year; 0 at `end`.
- **replacement[pos]** — the Nth best *available* player at that
  position, where N is remaining starter demand: league positional
  demand × teams, minus players already gone, floored at `teams // 2`.
  That floor exists because in keeper leagues kept starters eat nearly
  all nominal demand and replacement would otherwise collapse onto the
  single best player, flattening everything.
- **discount** — 0.85/yr (ages.json).
- **horizon** — 20 seasons for full dynasty, 2 for a limited-keeper
  league, 1 for redraft (ages.json `horizons`).

Dividing by `curve(age)` makes this season's projection the anchor: a
21-year-old's future seasons scale *up* toward his peak, a 30-year-old
back's scale down fast. Seasons below replacement contribute zero but do
not end the loop, so a young riser currently under the line still
accrues value later.

**MODEL of 0** means every season inside the horizon projects at or
below replacement. It is not missing data.

## VALUE

MODEL, blended toward the market, then adjusted for your roster.

Step 1, market blend:

    ladder       = every player's MODEL, sorted descending (FULL pool,
                   including drafted players)
    market_v     = ladder[round(dADP) − 1]
    VALUE        = (1 − w) * MODEL  +  w * market_v         w = 0.35

The market-implied value is "what the MODEL says a player ranked where
the market prices him is worth." A player with no dADP gets pure MODEL.
The ladder spans the full pool on purpose — building it from only the
available players would shift every number as the draft burns picks.

Step 2, roster context (`ages.json` → `roster`):

    same-position target collision   × 0.60
    cross-position (TE vs WR)        × 0.80
    handcuff to one of your RBs      × 1.15, and only if MODEL > 0

Collision fires when a WR/TE shares an NFL team — therefore a
quarterback — with a pass catcher you already roster. The handcuff bump
requires standalone value: a pure insurance back gets a note and no
bump, because owning the whole backfield is worth nothing while your
starter is healthy.

## dADP

Sleeper's dynasty market average draft position, taken from the
per-player season endpoint. Superflex leagues use the 2QB dynasty key
first, because quarterbacks price completely differently there. If only
a redraft number exists it is used and marked with a trailing `r`.

This is the one column with no model in it. It is what the market
thinks.

## RESEARCH

From the dossier store, not computed. Shows the opportunity flags if the
player has any, otherwise his freshest note, with an age in days once it
starts going stale.

    BLOCKED     his own injury is severe
    INHERITING  someone ahead of him is hurt or gone
    WATCH       thin or conflicting reporting

Attribution is structural: `volatile.injury` is his own body,
`stable.competition[].status` is everyone else's. Same keywords mean
opposite things depending on whose injury it is.

## TIER rows

Breaks are computed on VALUE, and the threshold is scale-free:

    cut = max( gap_factor × median gap,
               min_gap_pct × (highest VALUE − lowest VALUE),
               min_gap_abs )

Defaults 2.5, 0.06, 1.0. A tier ends where the drop to the next player
exceeds `cut`. The percentage floor is what keeps this working after a
change to the units of VALUE — an absolute floor once exceeded the whole
board and put all 60 players in Tier 1.

---

## What is measured vs what is assumed

**Measured:** projections, scoring, ADP, ages, depth charts, injury
status, everything in the dossiers.

**Assumed, and yours to tune in ages.json:** every aging curve, the
0.85 discount, the 0.35 market blend, the collision and handcuff
multipliers, the tier thresholds, the horizons. None of these are
fitted to data. The WR cliff (0.78/yr past 30) is the one I would
change first — it is steep enough to override a 20-point projection
edge in a single season.
