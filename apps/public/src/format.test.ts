import { describe, expect, it } from "vitest";
import { isStaleListing, STALE_AFTER_DAYS } from "./format";

describe("isStaleListing", () => {
  const now = Date.parse("2026-09-08T12:00:00Z");

  it("treats a listing seen today as live", () => {
    expect(isStaleListing("2026-09-08T08:00:00Z", now)).toBe(false);
  });

  it(`flags listings older than ${STALE_AFTER_DAYS} days`, () => {
    expect(isStaleListing("2026-08-01T08:00:00Z", now)).toBe(true);
  });
});
