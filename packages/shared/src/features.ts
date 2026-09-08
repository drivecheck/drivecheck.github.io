export type FeatureRarity = "common" | "uncommon" | "rare";

export type FeatureValueEstimate = {
  key: string;
  labelCs: string;
  rarity: FeatureRarity;
  deltaCzkLow: number | null;
  deltaCzkHigh: number | null;
  sampleSize: number;
  lowConfidence: boolean;
};
