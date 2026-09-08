import { describe, expect, it } from "vitest";
import {
  blendFairValue,
  classifySoldProxy,
  listingDaysOnMarket,
  selectSoldProxyHistoryCandidates,
} from "./sold-proxy";

describe("listingDaysOnMarket", () => {
  it("uses published or first seen through last seen", () => {
    const now = Date.parse("2026-08-17T00:00:00Z");
    expect(
      listingDaysOnMarket({
        firstSeenAt: "2026-08-01T00:00:00Z",
        lastSeenAt: "2026-08-15T00:00:00Z",
        now,
      }),
    ).toBe(14);
  });
});

describe("classifySoldProxy", () => {
  const now = Date.parse("2026-08-17T00:00:00Z");

  it("treats a quick disappearance with no drop as withdrawn", () => {
    const result = classifySoldProxy(
      {
        priceCzk: 300_000,
        firstSeenAt: "2026-08-16T00:00:00Z",
        lastSeenAt: "2026-08-17T00:00:00Z",
        priceHistory: [{ priceCzk: 300_000 }],
      },
      30,
      now,
    );
    expect(result.kind).toBe("withdrawn");
    expect(result.proxyCzk).toBeNull();
  });

  it("treats a downward price move as a likely sale", () => {
    const result = classifySoldProxy(
      {
        priceCzk: 280_000,
        firstSeenAt: "2026-08-01T00:00:00Z",
        lastSeenAt: "2026-08-10T00:00:00Z",
        priceHistory: [{ priceCzk: 310_000 }, { priceCzk: 280_000 }],
      },
      40,
      now,
    );
    expect(result.kind).toBe("likely_sold");
    expect(result.dropped).toBe(true);
    expect(result.proxyCzk).toBe(280_000);
  });

  it("applies a 5 percent haircut when it sat long without a drop", () => {
    const result = classifySoldProxy(
      {
        priceCzk: 400_000,
        firstSeenAt: "2026-07-01T00:00:00Z",
        lastSeenAt: "2026-08-15T00:00:00Z",
        priceHistory: [{ priceCzk: 400_000 }],
      },
      20,
      now,
    );
    expect(result.kind).toBe("likely_sold");
    expect(result.dropped).toBe(false);
    expect(result.proxyCzk).toBe(380_000);
  });
});

describe("selectSoldProxyHistoryCandidates", () => {
  it("skips withdrawn-age listings and caps the set", () => {
    const now = Date.parse("2026-08-17T00:00:00Z");
    const longStay = {
      listingId: "a",
      priceCzk: 200_000,
      firstSeenAt: "2026-07-01T00:00:00Z",
      lastSeenAt: "2026-08-15T00:00:00Z",
      priceHistory: [] as { priceCzk: number }[],
    };
    const withdrawn = {
      listingId: "b",
      priceCzk: 200_000,
      firstSeenAt: "2026-08-16T00:00:00Z",
      lastSeenAt: "2026-08-17T00:00:00Z",
      priceHistory: [],
    };
    const noId = {
      listingId: null,
      priceCzk: 200_000,
      firstSeenAt: "2026-07-01T00:00:00Z",
      lastSeenAt: "2026-08-15T00:00:00Z",
      priceHistory: [],
    };
    const picked = selectSoldProxyHistoryCandidates(
      [withdrawn, noId, longStay, { ...longStay, listingId: "c" }],
      1,
    );
    expect(picked.map((c) => c.listingId)).toEqual(["a"]);
    expect(
      listingDaysOnMarket({
        firstSeenAt: withdrawn.firstSeenAt,
        lastSeenAt: withdrawn.lastSeenAt,
        now,
      }),
    ).toBeLessThan(3);
  });
});

describe("blendFairValue", () => {
  it("uses only haircut live asks when proxies are scarce", () => {
    const blended = blendFairValue({
      haircutLiveMedianCzk: 300_000,
      soldProxyMedianCzk: 250_000,
      soldProxyCount: 1,
      rawAskMedianCzk: 320_000,
      rawAskP25Czk: 280_000,
    });
    expect(blended.fairValueCzk).toBe(300_000);
    expect(blended.soldWeight).toBe(0);
  });

  it("blends 70/30 once there are eight proxies and skips the ask floor", () => {
    const blended = blendFairValue({
      haircutLiveMedianCzk: 400_000,
      soldProxyMedianCzk: 200_000,
      soldProxyCount: 8,
      rawAskMedianCzk: 410_000,
      rawAskP25Czk: 390_000,
    });
    expect(blended.fairValueCzk).toBe(260_000);
    expect(blended.soldWeight).toBe(0.7);
  });

  it("caps fair value at the raw ask median", () => {
    const blended = blendFairValue({
      haircutLiveMedianCzk: 500_000,
      soldProxyMedianCzk: 480_000,
      soldProxyCount: 4,
      rawAskMedianCzk: 450_000,
      rawAskP25Czk: 400_000,
    });
    expect(blended.fairValueCzk).toBe(450_000);
  });
});
