import type { SnapshotMeta } from "@drivecheck/pricing";
import { decryptSnapshotToSqlite } from "@drivecheck/pricing";

const CACHE_NAME = "drivecheck-snapshot-v1";
const SESSION_PW = "drivecheck.snapshot.password";

/** Cache Storage only accepts http(s) request URLs — not ad-hoc schemes. */
export function snapshotCacheUrl(baseHref: string, generatedAt: string): string {
  const base = baseHref.endsWith("/") ? baseHref : `${baseHref}/`;
  const url = new URL("snapshot.bin", base);
  url.searchParams.set("v", generatedAt);
  return url.toString();
}

export function readSessionPassword(): string | null {
  try {
    return sessionStorage.getItem(SESSION_PW);
  } catch {
    return null;
  }
}

export function writeSessionPassword(password: string): void {
  sessionStorage.setItem(SESSION_PW, password);
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_PW);
}

export async function loadSnapshotMeta(): Promise<SnapshotMeta & { generated_at?: string }> {
  const res = await fetch("./snapshot.meta.json", { cache: "no-cache" });
  if (!res.ok) throw new Error("snapshot meta missing");
  return (await res.json()) as SnapshotMeta & { generated_at?: string };
}

export async function loadCiphertext(generatedAt: string | undefined): Promise<Uint8Array> {
  const cacheKey =
    generatedAt && typeof location !== "undefined"
      ? snapshotCacheUrl(location.href, generatedAt)
      : null;
  if ("caches" in globalThis && cacheKey) {
    try {
      const cache = await caches.open(CACHE_NAME);
      const hit = await cache.match(cacheKey);
      if (hit) return new Uint8Array(await hit.arrayBuffer());
    } catch {
      // Private mode / quota — fall through to network.
    }
  }
  const res = await fetch("./snapshot.bin");
  if (!res.ok) throw new Error("snapshot download failed");
  const buf = new Uint8Array(await res.arrayBuffer());
  if ("caches" in globalThis && cacheKey) {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(
        cacheKey,
        new Response(buf, { headers: { "Content-Type": "application/octet-stream" } }),
      );
    } catch {
      // Cache is optional; login must still succeed.
    }
  }
  return buf;
}

export async function unlockSnapshot(password: string): Promise<{
  sqliteBytes: Uint8Array;
  meta: SnapshotMeta & { generated_at?: string };
}> {
  const meta = await loadSnapshotMeta();
  const cipher = await loadCiphertext(meta.generated_at);
  try {
    const sqliteBytes = await decryptSnapshotToSqlite(cipher, password, meta);
    writeSessionPassword(password);
    return { sqliteBytes, meta };
  } catch {
    throw new Error("Neplatné heslo.");
  }
}
