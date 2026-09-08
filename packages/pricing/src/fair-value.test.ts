import { describe, expect, it } from "vitest";
import {
  computeFairValueFromComps,
  rarePositiveFeatureAdj,
  type FairValueComp,
} from "./fair-value";

function comp(
  partial: Partial<FairValueComp> & { priceCzk: number },
): FairValueComp {
  return {
    source: "sauto",
    externalId: partial.externalId ?? String(partial.priceCzk),
    url: "https://example.com",
    make: "Škoda",
    model: "Octavia",
    year: partial.year ?? 2019,
    mileageKm: partial.mileageKm ?? 120_000,
    priceCzk: partial.priceCzk,
    sellerType: partial.sellerType ?? "dealer",
    region: null,
    listingStatus: partial.listingStatus ?? "active",
    firstSeenAt: partial.firstSeenAt ?? "2026-06-01T00:00:00Z",
    lastSeenAt: partial.lastSeenAt ?? "2026-08-01T00:00:00Z",
    publishedAt: partial.publishedAt,
    priceIncludesVat: partial.priceIncludesVat ?? true,
    vatDeductible: partial.vatDeductible ?? false,
    priceHistory: partial.priceHistory,
  };
}

describe("rarePositiveFeatureAdj", () => {
  it("only counts rare positive residuals", () => {
    expect(
      rarePositiveFeatureAdj([
        {
          key: "towbar",
          labelCs: "Tažné",
          rarity: "rare",
          deltaCzkLow: 8_000,
          deltaCzkHigh: 12_000,
          sampleSize: 6,
          lowConfidence: false,
        },
        {
          key: "ac",
          labelCs: "Klima",
          rarity: "common",
          deltaCzkLow: 20_000,
          deltaCzkHigh: 30_000,
          sampleSize: 40,
          lowConfidence: false,
        },
      ]),
    ).toBe(10_000);
  });
});

describe("computeFairValueFromComps", () => {
  it("builds an Octavia-like fair value below typical ask", () => {
    const active = [
      420_000, 430_000, 440_000, 450_000, 460_000, 470_000, 480_000, 490_000,
      500_000, 455_000,
    ].map((priceCzk, i) =>
      comp({
        priceCzk,
        externalId: `a${i}`,
        firstSeenAt: "2026-07-01T00:00:00Z",
        lastSeenAt: "2026-08-10T00:00:00Z",
      }),
    );
    const removed = Array.from({ length: 8 }, (_, i) =>
      comp({
        priceCzk: 380_000 + i * 2_000,
        externalId: `r${i}`,
        listingStatus: "removed",
        firstSeenAt: "2026-05-01T00:00:00Z",
        lastSeenAt: "2026-07-20T00:00:00Z",
        priceHistory: [{ priceCzk: 420_000 }, { priceCzk: 380_000 + i * 2_000 }],
      }),
    );

    const out = computeFairValueFromComps({
      active,
      removed,
      subjectYear: 2019,
      subjectMileageKm: 120_000,
      now: Date.parse("2026-08-17T00:00:00Z"),
    });

    expect(out.liveAskCount).toBeGreaterThanOrEqual(8);
    expect(out.soldProxyCount).toBe(8);
    expect(out.fairValueCzk).not.toBeNull();
    expect(out.priceTypicalCzk).not.toBeNull();
    expect(out.fairValueCzk as number).toBeLessThan(out.priceTypicalCzk as number);
  });
});
