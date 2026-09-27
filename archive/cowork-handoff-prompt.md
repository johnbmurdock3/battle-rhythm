# Cowork kickoff — personal Sleeper fantasy football client

Paste everything below into a fresh cowork session, with `sleeper_client.py` attached.

---

I'm building a personal tool to manage my five Sleeper fantasy football leagues. I have a data engineering background, so don't simplify explanations. Argue with me when I'm wrong.

## What I'm building and why

Sleeper's app shows me one league at a time. I want one place that reads all five, applies each league's own scoring rules, and lets me ask questions across them — which of my five teams is weakest at RB, is a player worth more in the dynasty league or the keeper league, where should my waiver budget go this week.

Attached is `sleeper_client.py`, a first iteration written in a planning chat but never executed. It has not touched the live API. Treat it as a hypothesis, not working code.

## What's confirmed about the Sleeper API

- Base is `https://api.sleeper.app/v1`. Free, read-only, no API key, no OAuth. Nothing I do can write to my account — no lineup changes, no waiver claims. I'll execute in the app.
- Rate limit is 1000 calls per minute. Go over it and the IP gets blocked. The script self-throttles to roughly 750/min.
- `/user/{username}` gives a user_id. `/user/{user_id}/leagues/nfl/{season}` returns every league. That one call is the whole reason I'm not using a third-party server.
- `/players/nfl` is the name and position lookup. Several megabytes, meant to be cached once daily. Every other endpoint returns bare Sleeper player IDs, so nothing is readable without it.
- `/state/nfl` gives the current season and week.
- Per league: `/league/{id}/rosters`, `/league/{id}/users`, `/league/{id}/matchups/{week}`, `/league/{id}/transactions/{round}`.
- Sleeper player IDs match no other system. Pulling in outside stats later means building a crosswalk.

My username is `dirtymurdock`. There's also a push key in my account — do not use it, do not ask me for it, and don't put it anywhere in the code. It's a secret and it's irrelevant to the read-only API.

## The assumption to test first

`score()` in the attached file computes fantasy points as a dot product: multiply each stat by that league's multiplier for the same key, sum the result. This works only if Sleeper's stat keys and its `scoring_settings` keys use the same vocabulary — `rec`, `pass_yd`, `pass_td`, `fum_lost`, and so on.

I believe they do but nobody has checked. Verify it before anything else. Take one finished week, one player, score him with my code, compare to what the Sleeper app shows. If the numbers match, everything downstream is sound. If they don't, we need a key crosswalk and that's the real work of this session.

Never hardcode scoring rules. Read them from each league object every time. My five leagues disagree on PPR and on passing touchdown values, and getting this wrong produces start/sit advice that's confidently wrong in a way I won't catch.

## Known problems in the attached code

- Team defenses come back as team abbreviations, not numeric IDs, so they miss the player table. There's a crude guard in `name_of()` that will need replacing once we see the real shape. Multiple leagues score defense.
- The FAAB calculation assumes `waiver_budget` and `waiver_budget_used` exist in the settings. Unverified.
- Nothing handles leagues that use a different season format or that haven't started yet.

## Order of work

1. Run it. Fix whatever breaks.
2. Verify the scoring dot product against the app.
3. Fix defenses.
4. Confirm the scoring-difference table across my five leagues looks right. That table is the first thing this gives me that Sleeper can't.

Only after all four:

5. Matchups and transactions.
6. A single function that briefs me on all five leagues at once.
7. Wrap in MCP so I can query it from chat.

## Not now

Projections. They're a licensed third-party feed Sleeper doesn't control and has said it isn't investing in exposing. The endpoint exists at `/v1/projections/nfl/{season_type}/{season}/{week}` but I'm treating it as unstable. When we do get to it, note that the feed is raw stat lines, not fantasy points — so it runs through the same per-league scoring engine as everything else.

## How to work with me

Run the code before telling me it works. If an endpoint returns something different from what I described above, say so — I assembled this from documentation and community projects, not from hitting the API. Show me actual output, not descriptions of output.
