# br-hooks: the GitHub webhook receiver

The rest of Battle Rhythm pulls. It calls Sleeper on a schedule and compares what comes back. This part runs the other way: GitHub calls it. When CI on battle-rhythm breaks or recovers, or someone force-pushes to main, GitHub posts an event to this receiver. The receiver checks that GitHub really sent it and hasn't already been handled, then posts a short alert to Discord.

It runs as a Cloudflare Worker with a D1 (SQLite) database, in two separate environments. The sandbox listens to a throwaway repo, and production listens to battle-rhythm. Each has its own Worker, database, secret and Discord channel, so nothing is shared between them.

## What happens to a delivery

Each check below maps to a status code, and GitHub shows that code in the repo's delivery log, which makes the log easy to read.

| Check | Fails with |
|---|---|
| path and method (`POST /github`) | 404, 405 |
| content type is `application/json` | 415 |
| body under 2 MB, by header and by actual size | 413 |
| `X-GitHub-Event` and `X-GitHub-Delivery` present | 400 |
| `X-Hub-Signature-256` matches the raw body | 401 |
| body is a JSON object | 400 |
| repository is the one this environment serves | 403 |
| delivery id not already handled | 200 `duplicate`, or 409 if the id comes back with a different body |
| storage works | 500, so GitHub marks it failed and you can redeliver it |

The signature is checked on the exact bytes that arrived, before anything is parsed. Parsing and re-serializing changes the bytes, and then even a genuine signature won't match. The comparison uses `crypto.subtle.verify`, which takes the same time whether the first byte is wrong or the last one is. A request that fails the signature check is logged but never stored. Without that rule, anyone could send junk with a real delivery id and use up that id before GitHub's delivery arrived.

A delivery that passes is claimed in D1 with one `INSERT … ON CONFLICT … RETURNING`. When GitHub or a person sends the same delivery twice, the primary key lets exactly one through. A delivery can be claimed again in two cases: it failed, or it started and never finished within five minutes. That's why the Redeliver button in GitHub works as a retry and not as a way to get double alerts.

The reply goes back as soon as the event is recorded. The Discord post happens after that, through `ctx.waitUntil`, so a slow Discord can't push the reply past GitHub's 10-second timeout.

## Alert rules

`src/events.ts` holds the rules as plain functions: a payload and the previous state go in, and a plan comes out.

- `workflow_run` alerts when a workflow changes state: passing to failing, or failing back to passing. A second failure in a row is recorded without another alert. Cancelled and skipped runs don't count either way. GitHub doesn't guarantee delivery order, so each run is compared with the stored run number and attempt, and an older run that arrives late is ignored. The same check catches one run showing up under two delivery ids, which dedupe by id alone would miss.
- `push`: an ordinary push is recorded without an alert. A force-push to the default branch alerts, and so does a deleted branch.
- `ping` is what GitHub sends when a hook is created. It posts a "connected" message, which is the first sign the setup works.

State only moves once Discord has taken the alert. If Discord is down, the delivery is marked failed and the state stays where it was. A redelivery then works out the same change again and sends the alert that was missed.

Discord posts go out with `allowed_mentions: {parse: []}`. Branch names come from the payload, so a branch named `@everyone` would otherwise ping the whole server. A 429 is retried after the `retry_after` Discord sends, and a 5xx is retried with backoff, three tries in all. Any other 4xx fails at once, since retrying won't fix a deleted webhook.

## Tests

```
npm test          # 38 tests: signatures, gatekeeping, dedupe, alert rules, Discord retries
npm run typecheck
```

The store tests use Node's built-in SQLite and run the same SQL the Worker sends to D1, so a typo in the SQL fails here and not in production. The first signature test uses the example from GitHub's own documentation. I checked the suite by planting ten bugs: accepting any signature, turning dedupe off, dropping the repo check, and seven more. At first two got through (an off-by-one in the stale-run check and a missing Content-Length check). There are tests for both now, and the suite catches all ten.

`scripts/probe.mjs` sends twelve requests to a deployed receiver and checks each response: bad signature, tampered body, wrong content type, wrong repo, a signed delivery, its replay, and a reused id with a different body. Run it after every deploy. Its deliveries are the kind that never alert, so it's safe to run against production.

`scripts/export-fixtures.mjs` pulls the raw deliveries the sandbox stored and writes them to `test/fixtures/recorded/`. `test/recorded.test.ts` replays each one through the handler. If `SANDBOX_WEBHOOK_SECRET` is set, it also checks GitHub's original signature against the stored bytes. That's the check that proves the receiver handles GitHub's real signatures, not only the ones the tests generate.

## Setup (PowerShell 5.1, from `webhooks\`)

One-time:

```
npm install
npx wrangler login
npx wrangler d1 create br-hooks-sandbox
npx wrangler d1 create br-hooks-production
```

Paste each `database_id` into `wrangler.toml`. Then apply the schema:

```
npx wrangler d1 execute br-hooks-sandbox --remote --env sandbox --file schema.sql
npx wrangler d1 execute br-hooks-production --remote --env production --file schema.sql
```

Make one secret per environment. These lines print 32 random bytes as hex. Put the value in your password manager, not in a file:

```
$b = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
-join ($b | ForEach-Object { $_.ToString("x2") })
```

Set it, along with a Discord webhook URL (Channel settings → Integrations → Webhooks). Each command prompts for the value:

```
npx wrangler secret put GITHUB_WEBHOOK_SECRET --env sandbox
npx wrangler secret put DISCORD_WEBHOOK_URL --env sandbox
npm run deploy:sandbox
```

In the sandbox repo, go to Settings → Webhooks → Add webhook. Use `https://br-hooks-sandbox.<you>.workers.dev/github` as the URL, set content type to `application/json`, paste the same secret, and choose "Push" and "Workflow runs". GitHub sends a ping, and the Discord channel should say "Webhook connected".

Production is the same steps with `--env production`, a new secret, its own Discord channel, and the hook added on battle-rhythm.

## Rotating a secret

Set the new secret in the Worker, keeping the old one as `GITHUB_WEBHOOK_SECRET_PREVIOUS`. Then change the secret in GitHub. Once the delivery log shows deliveries going through under the new one, delete the previous secret. The receiver accepts either secret during the switch, so no deliveries get dropped.
