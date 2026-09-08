import { describe, expect, it } from "vitest";
import { computeDealerAdvice } from "./dealer-advice";

describe("computeDealerAdvice", () => {
  it("derives buy-in and list-at from fair value, not from asks", () => {
    const advice = computeDealerAdvice({
      fairValueCzk: 400_000,
      marginPct: 10,
      reworkBufferCzk: 5_000,
    });
    expect(advice.listAtCzk).toBe(400_000);
    expect(advice.buyInCzk).toBe(355_000);
    expect(advice.commissionCzk).toBe(45_000);
  });

  it("returns empty plates when fair value is missing", () => {
    const advice = computeDealerAdvice({ fairValueCzk: null });
    expect(advice.buyInCzk).toBeNull();
    expect(advice.listAtCzk).toBeNull();
    expect(advice.commissionCzk).toBeNull();
  });
});
