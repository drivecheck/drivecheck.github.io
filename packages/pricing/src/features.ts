import type { FeatureRarity, FeatureValueEstimate } from "@drivecheck/shared";
import { equipmentLabelCs, listingHasEquipment } from "./equipment";
import type { ListingRow } from "./store";
import { median } from "./stats";

function rarityFromPrevalence(p: number): FeatureRarity {
  if (p < 0.08) return "rare";
  if (p < 0.25) return "uncommon";
  return "common";
}

export function estimateFeatureValues(
  rows: ListingRow[],
  featureKeys: string[],
  subjectYear: number,
  subjectMileageKm: number,
): FeatureValueEstimate[] {
  if (featureKeys.length === 0 || rows.length < 6) return [];

  const band = rows.filter((r) => {
    if (r.year != null && Math.abs(r.year - subjectYear) > 3) return false;
    if (
      r.mileage_km != null &&
      subjectMileageKm > 0 &&
      Math.abs(r.mileage_km - subjectMileageKm) > 80_000
    ) {
      return false;
    }
    return true;
  });
  const pool = band.length >= 8 ? band : rows;

  return featureKeys.map((key) => {
    const withTag = pool.filter((r) => listingHasEquipment(r.feature_keys, key));
    const withoutTag = pool.filter((r) => !listingHasEquipment(r.feature_keys, key));
    const prevalence = pool.length ? withTag.length / pool.length : 0;
    const medWith = median(withTag.map((r) => r.price_czk));
    const medWithout = median(withoutTag.map((r) => r.price_czk));

    let delta: number | null = null;
    if (medWith != null && medWithout != null && withTag.length >= 3 && withoutTag.length >= 3) {
      delta = medWith - medWithout;
    }

    const lowConfidence = withTag.length < 5 || withoutTag.length < 5 || delta == null;
    const spread = delta != null ? Math.max(5_000, Math.round(Math.abs(delta) * 0.35)) : null;

    return {
      key,
      labelCs: equipmentLabelCs(key),
      rarity: rarityFromPrevalence(prevalence),
      deltaCzkLow: delta != null && spread != null ? delta - spread : null,
      deltaCzkHigh: delta != null && spread != null ? delta + spread : null,
      sampleSize: withTag.length,
      lowConfidence,
    };
  });
}
