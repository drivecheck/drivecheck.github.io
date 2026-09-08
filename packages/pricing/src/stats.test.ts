import { describe, expect, it } from "vitest";
import {
  assumedMileageKm,
  confidenceFromSample,
  dampenFeatureDeltas,
  effectiveSubjectMileageKm,
  median,
  mileageYearAdjustmentCzk,
  percentile,
  removeIqrOutliers,
  roundToThousand,
} from "./stats";

describe("pricing stats", () => {
  it("computes percentiles", () => {
    const values = [100, 200, 300, 400, 500];
    expect(percentile(values, 0.5)).toBe(300);
    expect(percentile(values, 0.25)).toBe(200);
    expect(median(values)).toBe(300);
  });

  it("removes iqr outliers", () => {
    const values = [200_000, 210_000, 220_000, 230_000, 1_000_000];
    const cleaned = removeIqrOutliers(values);
    expect(cleaned).not.toContain(1_000_000);
    expect(cleaned.length).toBe(4);
  });

  it("maps confidence bands", () => {
    expect(confidenceFromSample(3, 2).level).toBe("low");
    expect(confidenceFromSample(10, 2).level).toBe("medium");
    expect(confidenceFromSample(20, 2).level).toBe("high");
  });

  it("dampens stacked feature deltas", () => {
    expect(dampenFeatureDeltas([80_000, 80_000], 120_000)).toBe(120_000);
    expect(dampenFeatureDeltas([10_000, -5_000], 120_000)).toBe(5_000);
    // Engine clamps observational negatives to 0 before dampen; dampen itself
    // still sums whatever it is given (legacy unit behaviour).
    expect(dampenFeatureDeltas([0, 0], 120_000)).toBe(0);
  });

  it("rounds to thousands", () => {
    expect(roundToThousand(253_400)).toBe(253_000);
  });

  it("assumes ~15k km/year when mileage is missing", () => {
    expect(assumedMileageKm(2023, 2026)).toBe(60_000);
    expect(effectiveSubjectMileageKm(0, 2023, 2026)).toEqual({
      mileageKm: 60_000,
      assumed: true,
    });
    expect(effectiveSubjectMileageKm(80_000, 2023, 2026)).toEqual({
      mileageKm: 80_000,
      assumed: false,
    });
  });

  it("raises ask when subject has fewer km than the comp", () => {
    const adj = mileageYearAdjustmentCzk({
      subjectYear: 2023,
      subjectMileageKm: 50_000,
      compYear: 2023,
      compMileageKm: 150_000,
      basePriceCzk: 600_000,
    });
    expect(adj).toBeGreaterThan(0);
  });

  it("lowers ask when subject has more km than the comp", () => {
    const adj = mileageYearAdjustmentCzk({
      subjectYear: 2023,
      subjectMileageKm: 150_000,
      compYear: 2023,
      compMileageKm: 50_000,
      basePriceCzk: 600_000,
    });
    expect(adj).toBeLessThan(0);
  });
});
