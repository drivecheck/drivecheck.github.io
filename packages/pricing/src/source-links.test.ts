import { describe, expect, it } from "vitest";
import { buildSourceSearchLinks } from "./source-links";

describe("buildSourceSearchLinks", () => {
  it("builds tier1 sauto and bazos urls without rare filters", () => {
    const links = buildSourceSearchLinks({
      mode: "quick",
      make: "Škoda",
      model: "Octavia",
      year: 2020,
      mileageKm: 100000,
      featureKeys: ["panorama", "custom-rare-seats"],
    });
    expect(links.sautoUrl).toBe("https://www.sauto.cz/inzerce/osobni/skoda/octavia");
    expect(links.bazosUrl).toBe("https://auto.bazos.cz/skoda/");
    expect(links.sautoUrl).not.toContain("panorama");
  });
});
