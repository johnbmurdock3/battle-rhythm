// Outbound half: post to a Discord incoming webhook. The URL is itself a
// secret (anyone holding it can post), so it is never logged.

export interface SendResult {
  ok: boolean;
  status: number;
  attempts: number;
  error?: string;
}
export type Notifier = (text: string) => Promise<SendResult>;

const MAX_ATTEMPTS = 3;
const MAX_WAIT_MS = 5000; // the worker has limited time after responding; don't sleep past it
const DISCORD_LIMIT = 2000;

export function isDiscordWebhookUrl(url: string): boolean {
  return /^https:\/\/(discord\.com|discordapp\.com)\/api\/webhooks\/\d+\/[\w-]+$/.test(url);
}

export function discordNotifier(
  url: string,
  fetchImpl: typeof fetch = fetch,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Notifier {
  if (!isDiscordWebhookUrl(url)) throw new Error("DISCORD_WEBHOOK_URL is not a Discord webhook URL");
  return async (text) => {
    const body = JSON.stringify({
      content: text.length > DISCORD_LIMIT ? text.slice(0, DISCORD_LIMIT - 1) + "…" : text,
      // Branch names and commit text come from the payload. Without this, a
      // branch called "@everyone" would ping the whole server.
      allowed_mentions: { parse: [] },
    });
    let last: SendResult = { ok: false, status: 0, attempts: 0 };
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      let res: Response;
      try {
        res = await fetchImpl(url, { method: "POST", headers: { "content-type": "application/json" }, body });
      } catch (e) {
        last = { ok: false, status: 0, attempts: attempt, error: `network: ${(e as Error).message}` };
        if (attempt < MAX_ATTEMPTS) await sleep(500 * attempt);
        continue;
      }
      if (res.ok) return { ok: true, status: res.status, attempts: attempt };
      last = { ok: false, status: res.status, attempts: attempt, error: `discord ${res.status}` };
      if (res.status === 429) {
        const wait = await retryAfterMs(res);
        if (wait > MAX_WAIT_MS || attempt === MAX_ATTEMPTS) break;
        await sleep(wait);
      } else if (res.status >= 500) {
        if (attempt < MAX_ATTEMPTS) await sleep(500 * attempt);
      } else {
        break; // 4xx other than 429 won't fix itself: bad URL, deleted webhook, bad body
      }
    }
    return last;
  };
}

async function retryAfterMs(res: Response): Promise<number> {
  try {
    const j = (await res.clone().json()) as { retry_after?: number };
    if (typeof j.retry_after === "number") return Math.ceil(j.retry_after * 1000);
  } catch {
    /* fall through to the header */
  }
  const h = Number(res.headers.get("retry-after"));
  return Number.isFinite(h) && h > 0 ? h * 1000 : 1000;
}
