import { describe, expect, it } from "vitest";
import {
  PLACEHOLDER_ICON_IDS,
  placeholderCaption,
  placeholderIconId,
} from "./placeholders";

describe("listing placeholders", () => {
  it("maps hatchback and red to a hatchback icon with red tint", () => {
    const tile = placeholderIconId({
      body: "Hatchback",
      color: "Červená",
      source: "sauto",
      externalId: "1",
    });
    expect(tile.icon).toBe("hatchback");
    expect(tile.tintCss).toBe("#B33A3A");
  });

  it("picks a stable icon when body is missing", () => {
    const a = placeholderIconId({
      body: null,
      color: null,
      source: "bazos",
      externalId: "abc",
    });
    const b = placeholderIconId({
      body: null,
      color: null,
      source: "bazos",
      externalId: "abc",
    });
    expect(a.icon).toBe(b.icon);
    expect(PLACEHOLDER_ICON_IDS).toContain(a.icon);
    expect(a.tintCss).toBe("#2E7D32");
  });

  it("never uses Bez fotografie as a caption", () => {
    expect(placeholderCaption()).toBe("");
    expect(placeholderCaption()).not.toMatch(/bez fotografie/i);
  });
});
