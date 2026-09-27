# Premiums and discounts the API cannot price

Derived 8/11 from the 447-player dossier pass. Every example is dated —
the categories are durable, the names go stale. Re-derive the names each
week from the refresh; keep the categories.

## Why these exist at all

Sleeper's ADP is one number from one global market. It has no idea what
your league pays, who is on your roster, how severe an injury is, or
what happened yesterday. Six structural blind spots:

1. **One market, every format.** ADP is the average of drafts with wildly
   different scoring. Your Hybrid rules pay 0.5 per TE reception plus
   reception buckets plus first downs; the ADP that prices a tight end
   is mostly built from leagues that pay none of that.
2. **Injury status is a single tag with no severity and no timeline.**
   "Questionable" covers a hamstring that costs one practice and a knee
   that costs a season. There is no field for "torn ACL plus a spring
   cleanup, coach says not a simple knee."
3. **No attribution.** The feed knows a player is hurt. It does not know
   the player *ahead of him* is hurt, which is the more valuable fact.
4. **Transactions reprice slowly.** ADP is an average over a drafting
   window, so a March trade takes weeks of drafts to work through the
   number, and a player nobody drafts never reprices at all.
5. **No roster context.** Two receivers sharing a quarterback are worth
   less to you together than apart. The market cannot see your roster.
6. **No room context.** Your LG01 room buys veterans about ten
   picks before market price. That is a local fact, permanently.

## The attribution trap — read this before automating anything

Scanning the dossiers for injury language and cross-referencing price
produced a list that looked like "expensive players with scary injuries."
It was actually two opposite categories jammed together:

- **Nabers** appears because *he* tore his ACL. That is a premium to avoid.
- **Tyler Warren** appears because *Alec Pierce* had ankle surgery with no
  return timetable, and *Josh Downs* is hurt. That is a discount to buy.
- **Jadarian Price** appears because *Charbonnet* is on PUP. Also a buy.
- **Jake Ferguson** appears because his TE2 competitor tore an ACL. Buy.

Same keywords, inverted meaning, entirely dependent on whose body it is.
Any automated flag that skips attribution will confidently rank the
beneficiaries alongside the casualties. This is the single biggest
gotcha in turning this file into code.

## DISCOUNTS — the market is too low

**D1. Role inheritance not yet priced.** Someone ahead of him left,
got hurt, or was traded, and the ADP predates it. Highest-yield
category in the whole pass.

    Willis QB    adp  93  proj 331   Tua released, signed as starter
    Geno Smith   adp 186  proj 261   traded to NYJ, named Week 1 starter
    Warren TE    adp  39  proj 273   Pittman traded, Pierce + Downs out
    Odunze WR    adp  55  proj 244   DJ Moore traded to BUF
    Brissett QB  adp 159  proj 188   Kyler Murray left ARI
    Price RB     adp  82  proj 218   Charbonnet PUP, Walker to KC
    Goedert TE   adp 160  proj 183   A.J. Brown traded away
    J.Williams   adp  70  proj 252   target competition left

**D2. Superflex QB points-vs-name gap.** In a two-quarterback league
the ADP prices reputation and team quality; you are paid in points.
The current shelf, sorted by price:

    Herbert   adp  24   proj 358
    Lawrence  adp  32   proj 358
    Dak       adp  45   proj 364     <- highest points on the board
    Goff      adp  65   proj 340     <- 41 picks later, 18 fewer points
    Murray    adp  84   proj 320
    Willis    adp  93   proj 331     <- 69 picks after Herbert, -27 pts
    Geno      adp 186   proj 261     <- 162 picks after Herbert, -97 pts

Read the bottom two rows again. That is the structural discount, and it
exists because ADP cannot tell a starting quarterback from a backup any
faster than the transaction wire moves.

**D3. Scoring-format edge.** Your league pays tight ends for volume the
global market does not. Any target-hog TE is underpriced here by
construction, permanently, not as a one-time error. Warren at 39 is the
current instance; the category outlives him.

**D4. Injury-return overshoot.** Cleared, but the price still carries
the discount from when he was not.

    Irving RB    full-go 7/29 after shoulder surgery, still adp 51
    G.Wilson WR  fully cleared, unambiguous WR1
    Brooks RB    cleared by surgeon, "looks like the guy I remember"

## PREMIUMS — the market is too high

**P1. Injury severity flattened to one tag.** The API says
"Questionable." The reporting says otherwise.

    Nabers WR    adp  13   torn ACL + meniscus + spring cleanup;
                           "not a simple knee" (Harbaugh, 7/16)
    Charbonnet   adp 114   Jan 2026 playoff ACL, NO timetable
    Bell WR      adp 135   NFI, "still a long way away," may miss 4+
    Pierce WR    adp  91   PUP, ankle surgery, no timetable
    Sadiq TE     adp  87   hernia setback, out indefinitely
    Kittle TE    adp 113   Achilles, PUP, no Week 1 guarantee

**P2. Role loss not yet priced** — the mirror of D1, and the one most
likely to cost you money because the name is still familiar.

    Waddle WR    adp  80   traded to DEN as WR2 behind Sutton
    B.Thomas WR  adp  63   Hunter healthy, Meyers re-signed 3yr/$60M
    Kamara RB    adp 222   Etienne signed 4yr/$52M, listed ahead of him
    R.White RB   adp 179   lost RB1 job to Croskey-Merritt
    Kmet TE      adp  ~    demoted behind rookie Loveland
    A.Jones RB   adp 191   pay cut 9M -> 5.5M, Mason taking camp lead

**P3. Off-field availability the API has no field for.**

    Rice WR      adp  53   2025 suspension, knee debridement May 2026,
                           probation-violation arrest, contact only 8/4
    Aiyuk WR     adp 156   Reserve-DNR; team says he will not play again

**P4. Contract signals.** A team's money is a forecast.

    Pickens WR   franchise tag, extension deadline passed, "likely his
                 last in Dallas" — fine rental, poor dynasty keeper
    A.Jones RB   $9M -> $5.5M is the Vikings telling you their plan

**P5. Draft capital versus the actual depth chart.** The market prices
the draft slot and the guaranteed money; the depth chart prices reality.

    Love RB      3rd overall, $53M guaranteed, listed RB2 behind
                 Tyler Allgeier on the first preseason chart (8/2)

Cuts both ways — sometimes the chart is stale and the money is right.
Treat a conflict as a reason to look, not a verdict.

**P6. Keeper-league inflation.** Kept players never reach the market,
so every early price in a keeper league runs rich. Already in the
README caveat; it belongs on this list because it is the same class of
error.

**P7. Age cliff shape.** Dynasty ADP prices age as a smooth premium.
Actual decline is not smooth — running backs fall off a cliff around
28, receivers hold to 30, quarterbacks run long. ages.json encodes the
shape; the market averages it away.

## Structural — never priceable by a global number

    S1  your roster context (two receivers, one quarterback)
    S2  your league's scoring
    S3  your league's keeper rules
    S4  your room's behavior (LG01 pays ~10 picks early)

S1 is implemented in roster_adjust and the FIT engine. S2 is implemented
in the scoring dot product. S3 is a displayed caveat. S4 is a rule of
thumb applied by hand.

## What can be automated, and what cannot

Automatable now, from data already held:

- D2, the superflex points-vs-price gap — pure arithmetic on proj vs ADP
  rank, no research needed.
- P7, age cliff — already in the dynasty value model.
- S1-S4 — already implemented or displayed.

Automatable only with attribution:

- D1 and P2 both require knowing *whose* situation changed and in which
  direction. The dossier competition field carries the names; nothing
  currently parses direction. This is the highest-value thing left to
  build, and the attribution trap above is why it must be built
  carefully rather than by keyword.

Not automatable, needs a human read:

- P1 severity, P3 off-field, P4 contract signals. These are judgment
  calls on prose. The research surfaces them; you decide.
