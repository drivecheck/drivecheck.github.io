import { describe, expect, it } from "vitest";
import {
  canonicalizeEquipmentKey,
  equipmentMatchTokens,
  listingHasAllEquipment,
  listingHasEquipment,
  matchingEquipmentItems,
} from "./equipment";

describe("equipment catalog", () => {
  it("maps Czech aliases to canonical keys", () => {
    expect(canonicalizeEquipmentKey("vyhrivana_sedadla")).toBe("heated_seats");
    expect(canonicalizeEquipmentKey("panoramatická střecha")).toBe("panorama");
    expect(canonicalizeEquipmentKey("tempomat")).toBe("cruise_control");
    expect(canonicalizeEquipmentKey("mrtvy_uhel")).toBe("blind_spot");
    expect(canonicalizeEquipmentKey("adaptive_cruise")).toBe("cruise_control");
  });

  it("matches listing keys via aliases", () => {
    expect(listingHasEquipment(["heated_seats", "awd"], "vyhrivana_sedadla")).toBe(true);
    expect(listingHasEquipment(["panorama"], "panoramaticka_strecha")).toBe(true);
    expect(listingHasEquipment(["navigation"], "keyless")).toBe(false);
  });

  it("requires all selected equipment (AND)", () => {
    const keys = ["keyless", "heated_seats", "parking_camera"];
    expect(listingHasAllEquipment(keys, ["keyless", "vyhrivana_sedadla"])).toBe(true);
    expect(listingHasAllEquipment(keys, ["keyless", "blind_spot"])).toBe(false);
    expect(listingHasAllEquipment(keys, [])).toBe(true);
  });

  it("returns catalog items in stable order", () => {
    const items = matchingEquipmentItems(["tempomat", "keyless", "unknown_feature"]);
    expect(items.map((i) => i.key)).toEqual(["keyless", "cruise_control"]);
  });

  it("expands match tokens with aliases for SQL overlap", () => {
    const tokens = equipmentMatchTokens("heated_seats");
    expect(tokens).toContain("heated_seats");
    expect(tokens).toContain("vyhrivana_sedadla");
  });
});
