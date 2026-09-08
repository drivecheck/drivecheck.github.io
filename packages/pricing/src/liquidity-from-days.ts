import type { LiquidityStats } from "@drivecheck/shared";
import { median } from "./stats";

export function liquidityFromDomDays(
  days: number[],
  usedPublishedOnly: boolean,
): LiquidityStats {
  const finite = days.filter((d) => Number.isFinite(d) && d >= 0);
  const med = median(finite.map((d) => Math.round(d)));
  if (finite.length < 3 || med == null) {
    return {
      sampleSize: finite.length,
      medianDaysOnMarket: med,
      noteCs: "Zatím málo dat o době v nabídce.",
    };
  }
  if (!usedPublishedOnly && med < 1) {
    return {
      sampleSize: finite.length,
      medianDaysOnMarket: null,
      noteCs:
        "Inzeráty jsou v databázi velmi čerstvé — doba v nabídce se zpřesní, až bude datum zveřejnění.",
    };
  }
  let noteCs = usedPublishedOnly
    ? `Typická doba v nabídce cca ${med} dní (podle data zveřejnění).`
    : `Typická doba v nabídce cca ${med} dní (aktivní inzeráty).`;
  if (med <= 14) {
    noteCs = `Segment se točí rychle — typicky ~${med} dní v nabídce.`;
  } else if (med >= 60) {
    noteCs = `Segment se točí pomaleji — typicky ~${med} dní v nabídce.`;
  }
  return {
    sampleSize: finite.length,
    medianDaysOnMarket: med,
    noteCs,
  };
}
