import { describe, expect, it } from "vitest";
import { priceVehicle } from "./engine";
import { memoryListingStore, sampleOctaviaRow } from "./memory-store";

describe("priceVehicle with memory store", () => {
  it("returns a fair value for a dense Octavia sample", async () => {
    const rows = Array.from({ length: 16 }, (_, i) => sampleOctaviaRow(i));
    const result = await priceVehicle(
      {
        mode: "quick",
        make: "Škoda",
        model: "Octavia",
        year: 2019,
        mileageKm: 120_000,
        fuel: "Nafta",
      },
      memoryListingStore(rows),
    );
    expect(result.liveAskCount).toBeGreaterThanOrEqual(8);
    expect(result.fairValueCzk).toBeGreaterThan(200_000);
    expect(result.priceTypicalCzk).toBeGreaterThan(200_000);
    expect(result.confidence).not.toBe("");
  });
});
