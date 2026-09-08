import { describe, expect, it } from "vitest";
import {
  calibrateHaircutPct,
  haircutPctForDaysOnMarket,
  proxyFairValueFromAsk,
} from "./haircuts";

describe("haircutPctForDaysOnMarket", () => {
  it("uses 5/8/12 percent by days on market", () => {
    expect(haircutPctForDaysOnMarket(7)).toBe(0.05);
    expect(haircutPctForDaysOnMarket(30)).toBe(0.08);
    expect(haircutPctForDaysOnMarket(90)).toBe(0.12);
    expect(haircutPctForDaysOnMarket(null)).toBe(0.08);
  });
});

describe("calibrateHaircutPct", () => {
  it("keeps the default table when there are no closed sales", () => {
    expect(
      calibrateHaircutPct({
        defaultPct: 0.08,
        askMedianCzk: 400_000,
        soldMedianCzk: 360_000,
        closedSalesCount: 0,
      }),
    ).toBe(0.08);
  });

  it("uses the empirical ask-to-sold gap once there are five sales", () => {
    expect(
      calibrateHaircutPct({
        defaultPct: 0.08,
        askMedianCzk: 400_000,
        soldMedianCzk: 360_000,
        closedSalesCount: 5,
      }),
    ).toBeCloseTo(0.1);
  });
});

describe("proxyFairValueFromAsk", () => {
  it("applies the default haircut when sales are missing", () => {
    expect(
      proxyFairValueFromAsk({
        askCzk: 400_000,
        medianDaysOnMarket: 10,
        soldMedianCzk: null,
        closedSalesCount: 0,
      }),
    ).toBe(380_000);
  });
});
