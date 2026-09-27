// GitHub signs every delivery with HMAC-SHA256 over the raw request body and
// sends it as `X-Hub-Signature-256: sha256=<hex>`. Verification has to run on
// the exact bytes received, before any JSON parsing, and the comparison has to
// be constant-time. crypto.subtle.verify does both: it recomputes the MAC and
// compares without an early exit.

const enc = new TextEncoder();

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function bytesToHex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacKey(secret: string, usage: "sign" | "verify"): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [usage]);
}

/**
 * True when `header` is a valid signature of `body` under any of `secrets`.
 * More than one secret is how rotation works: set the new secret in GitHub,
 * keep the old one here as the previous secret until deliveries stop using it.
 */
export async function verifySignature(
  secrets: string[],
  body: Uint8Array,
  header: string | null,
): Promise<boolean> {
  const live = secrets.filter((s) => s.length > 0);
  if (live.length === 0) throw new Error("no webhook secret configured");
  if (!header) return false;
  const m = /^sha256=([0-9a-fA-F]{64})$/.exec(header.trim());
  if (!m) return false;
  const sig = hexToBytes(m[1].toLowerCase());
  for (const secret of live) {
    if (await crypto.subtle.verify("HMAC", await hmacKey(secret, "verify"), sig, body)) return true;
  }
  return false;
}

/** The header value GitHub would send for this body. Used by tests and the probe. */
export async function sign(secret: string, body: Uint8Array | string): Promise<string> {
  const bytes = typeof body === "string" ? enc.encode(body) : body;
  const mac = await crypto.subtle.sign("HMAC", await hmacKey(secret, "sign"), bytes);
  return "sha256=" + bytesToHex(mac);
}

export async function sha256Hex(body: Uint8Array): Promise<string> {
  return bytesToHex(await crypto.subtle.digest("SHA-256", body));
}
