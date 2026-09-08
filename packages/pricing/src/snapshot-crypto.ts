export type SnapshotMeta = {
  v: number;
  kdf: string;
  m: number;
  t: number;
  p: number;
  salt_b64: string;
  nonce_b64: string;
};

export const ARGON2_TIME_COST = 3;
export const ARGON2_MEMORY_KIB = 32_768;
export const ARGON2_PARALLELISM = 1;
export const ARGON2_HASH_LEN = 32;
export const META_VERSION = 1;

function bytesFromB64(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

export async function deriveSnapshotKey(
  password: string,
  salt: Uint8Array,
  meta: Pick<SnapshotMeta, "m" | "t" | "p">,
): Promise<Uint8Array> {
  const { argon2id } = await import("hash-wasm");
  return argon2id({
    password,
    salt,
    parallelism: meta.p,
    iterations: meta.t,
    memorySize: meta.m,
    hashLength: ARGON2_HASH_LEN,
    outputType: "binary",
  });
}

export async function decryptSnapshot(
  ciphertext: Uint8Array,
  password: string,
  meta: SnapshotMeta,
): Promise<Uint8Array> {
  if (meta.v !== META_VERSION || meta.kdf !== "argon2id") {
    throw new Error("unsupported snapshot meta");
  }
  const keyBytes = await deriveSnapshotKey(password, bytesFromB64(meta.salt_b64), meta);
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, [
    "decrypt",
  ]);
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: bytesFromB64(meta.nonce_b64) },
    key,
    ciphertext,
  );
  return new Uint8Array(plain);
}

export async function decryptSnapshotToSqlite(
  ciphertext: Uint8Array,
  password: string,
  meta: SnapshotMeta,
): Promise<Uint8Array> {
  const gz = await decryptSnapshot(ciphertext, password, meta);
  if (typeof DecompressionStream === "undefined") {
    throw new Error("gzip is not supported in this browser");
  }
  const stream = new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
