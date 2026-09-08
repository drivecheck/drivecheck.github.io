import { describe, expect, it } from "vitest";
import { snapshotCacheUrl } from "./gate";

describe("snapshotCacheUrl", () => {
  it("uses an https URL so Cache.put accepts the key", () => {
    const url = snapshotCacheUrl("https://example.com/app/", "2026-09-08T11:27:15Z");
    expect(url).toBe("https://example.com/app/snapshot.bin?v=2026-09-08T11%3A27%3A15Z");
    expect(() => new URL(url)).not.toThrow();
    expect(new URL(url).protocol).toMatch(/^https?:$/);
  });
});
