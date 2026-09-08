import { describe, expect, it } from "vitest";
import {
  ACCIDENT_FEATURE_KEY,
  isAccidentOrDamagedListing,
  textSuggestsAccidentOrDamage,
} from "./accident";

describe("accident listing detection", () => {
  it("flags CZ / DE crash wording", () => {
    expect(textSuggestsAccidentOrDamage("Škoda Octavia havarovaná")).toBe(true);
    expect(textSuggestsAccidentOrDamage("Po nehodě pojízdná")).toBe(true);
    expect(textSuggestsAccidentOrDamage("VW Golf Unfallwagen")).toBe(true);
    expect(textSuggestsAccidentOrDamage("Bastlerfahrzeug")).toBe(true);
  });

  it("flags feature key", () => {
    expect(
      isAccidentOrDamagedListing({
        featureKeys: [ACCIDENT_FEATURE_KEY],
        title: "Octavia",
      }),
    ).toBe(true);
  });

  it("does not over-filter ordinary service language", () => {
    expect(
      textSuggestsAccidentOrDamage("Serviska, nové brzdy, pneu 2024"),
    ).toBe(false);
    expect(
      isAccidentOrDamagedListing({
        title: "Octavia RS servisní knížka",
        featureKeys: ["heated_seats"],
      }),
    ).toBe(false);
  });
});
