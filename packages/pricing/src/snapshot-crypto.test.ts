import { describe, expect, it } from "vitest";
import golden from "./fixtures/snapshot-crypto-golden.json";
import { decryptSnapshot } from "./snapshot-crypto";

function bytesFromB64(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

describe("snapshot crypto", () => {
  it("decrypts the Python golden vector", async () => {
    const ciphertext = bytesFromB64(golden.ciphertext_b64);
    const text = new TextDecoder().decode(ciphertext);
    expect(text.includes("Octavia")).toBe(false);
    const plain = await decryptSnapshot(ciphertext, golden.password, golden.meta);
    expect(new TextDecoder().decode(plain)).toBe(golden.plaintext_utf8);
  });

  it("rejects the wrong password", async () => {
    const ciphertext = bytesFromB64(golden.ciphertext_b64);
    await expect(
      decryptSnapshot(ciphertext, "wrong-password", golden.meta),
    ).rejects.toThrow();
  });
});
