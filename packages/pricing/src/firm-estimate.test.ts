import { describe, expect, it } from "vitest";
import type { CompListing } from "@drivecheck/shared";
import { computeFirmEstimate, confidenceFromAppraisal } from "./firm-estimate";

function comp(partial: Partial<CompListing> & { priceCzk: number }): CompListing {
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
  };
}

/** Synthetic Superb 2023-like comps (~35–90k km). */
function superb2023Comps(): CompListing[] {
  return [
    comp({ priceCzk: 620_000, mileageKm: 45_000, year: 2023 }),
    comp({ priceCzk: 580_000, mileageKm: 70_000, year: 2023 }),
    comp({ priceCzk: 650_000, mileageKm: 35_000, year: 2023 }),
    comp({ priceCzk: 540_000, mileageKm: 90_000, year: 2023 }),
    comp({ priceCzk: 600_000, mileageKm: 55_000, year: 2023 }),
    comp({ priceCzk: 570_000, mileageKm: 80_000, year: 2023 }),
    comp({ priceCzk: 630_000, mileageKm: 40_000, year: 2023 }),
    comp({ priceCzk: 560_000, mileageKm: 85_000, year: 2023 }),
    comp({
      priceCzk: 610_000,
      mileageKm: 50_000,
      year: 2023,
      sellerType: "private",
    }),
    comp({ priceCzk: 590_000, mileageKm: 65_000, year: 2023 }),
  ];
}

describe("computeFirmEstimate", () => {
  it("returns a firm ask inside the market band with feature premium", () => {
    const comps = [
      comp({ priceCzk: 280_000, mileageKm: 140_000, year: 2018 }),
      comp({ priceCzk: 300_000, mileageKm: 120_000, year: 2019 }),
      comp({ priceCzk: 310_000, mileageKm: 110_000, year: 2019 }),
      comp({ priceCzk: 320_000, mileageKm: 100_000, year: 2020 }),
      comp({ priceCzk: 330_000, mileageKm: 95_000, year: 2020 }),
      comp({ priceCzk: 340_000, mileageKm: 90_000, year: 2020, sellerType: "private" }),
      comp({ priceCzk: 290_000, mileageKm: 130_000, year: 2018 }),
      comp({ priceCzk: 315_000, mileageKm: 115_000, year: 2019 }),
    ];

    const out = computeFirmEstimate({
      comps,
      subjectYear: 2019,
      subjectMileageKm: 110_000,
      featureAdjCzk: 20_000,
    });

    expect(out.suggestedPriceCzk).not.toBeNull();
    expect(out.marketP25Czk).not.toBeNull();
    expect(out.marketP75Czk).not.toBeNull();
    expect(out.suggestedPriceCzk!).toBeGreaterThanOrEqual(out.marketP25Czk! * 0.96);
    expect(out.suggestedPriceCzk!).toBeLessThanOrEqual(out.marketP75Czk! * 1.04);
    expect(out.suggestedPriceCzk! % 1000).toBe(0);
  });

  it("keeps firm estimate non-increasing as mileage rises (Superb 2023)", () => {
    const comps = superb2023Comps();
    const missing = computeFirmEstimate({
      comps,
      subjectYear: 2023,
      subjectMileageKm: 0,
      featureAdjCzk: 0,
    });
    const mid = computeFirmEstimate({
      comps,
      subjectYear: 2023,
      subjectMileageKm: 80_000,
      featureAdjCzk: 0,
    });
    const extreme = computeFirmEstimate({
      comps,
      subjectYear: 2023,
      subjectMileageKm: 456_000,
      featureAdjCzk: 0,
    });

    expect(missing.suggestedPriceCzk).not.toBeNull();
    expect(mid.suggestedPriceCzk).not.toBeNull();
    expect(extreme.suggestedPriceCzk).not.toBeNull();
    expect(missing.mileageAssumed).toBe(true);
    expect(extreme.mileageAssumed).toBe(false);
    // Missing uses ~15k km/year assumption — must not beat a typical mid km ask
    // in a way that inverts vs absurd mileage.
    expect(extreme.suggestedPriceCzk!).toBeLessThan(missing.suggestedPriceCzk!);
    expect(extreme.suggestedPriceCzk!).toBeLessThan(mid.suggestedPriceCzk!);
    expect(mid.suggestedPriceCzk!).toBeLessThanOrEqual(missing.suggestedPriceCzk! * 1.02);
  });
});

describe("confidenceFromAppraisal", () => {
  it("rates dense tight samples high", () => {
    expect(
      confidenceFromAppraisal({
        sampleSize: 30,
        yearWindow: 2,
        priceLowCzk: 300_000,
        priceHighCzk: 340_000,
        priceTypicalCzk: 320_000,
        featureCount: 3,
        featureLowConfidenceCount: 0,
      }).level,
    ).toBe("high");
  });

  it("rates tiny wide samples low", () => {
    expect(
      confidenceFromAppraisal({
        sampleSize: 3,
        yearWindow: 6,
        priceLowCzk: 200_000,
        priceHighCzk: 450_000,
        priceTypicalCzk: 300_000,
        featureCount: 4,
        featureLowConfidenceCount: 4,
      }).level,
    ).toBe("low");
  });

  it("lowers confidence when mileage is assumed or extreme", () => {
    const base = {
      sampleSize: 30,
      yearWindow: 2 as const,
      priceLowCzk: 300_000,
      priceHighCzk: 340_000,
      priceTypicalCzk: 320_000,
      featureCount: 3,
      featureLowConfidenceCount: 0,
    };
    expect(confidenceFromAppraisal(base).level).toBe("high");
    expect(confidenceFromAppraisal({ ...base, mileageAssumed: true }).level).toBe(
      "medium",
    );
    expect(confidenceFromAppraisal({ ...base, extremeMileage: true }).level).toBe(
      "medium",
    );
    expect(
      confidenceFromAppraisal({
        ...base,
        mileageAssumed: true,
        extremeMileage: true,
      }).level,
    ).not.toBe("high");
  });

  it("cannot be high with fewer than 3 sold-proxies", () => {
    const dense = {
      sampleSize: 30,
      yearWindow: 2,
      priceLowCzk: 300_000,
      priceHighCzk: 340_000,
      priceTypicalCzk: 320_000,
      featureCount: 3,
      featureLowConfidenceCount: 0,
    };
    expect(confidenceFromAppraisal({ ...dense, soldProxyCount: 8 }).level).toBe(
      "high",
    );
    expect(confidenceFromAppraisal({ ...dense, soldProxyCount: 2 }).level).toBe(
      "medium",
    );
    expect(confidenceFromAppraisal({ ...dense, soldProxyCount: 0 }).level).toBe(
      "medium",
    );
  });
});
