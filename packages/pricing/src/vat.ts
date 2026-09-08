export const CZ_VAT_RATE = 0.21;

/** Consumer comparable: asking prices including VAT. */
export function inclVatComparable(
  priceCzk: number,
  opts: {
    priceIncludesVat?: boolean | null;
    vatDeductible?: boolean | null;
  },
): number {
  if (!Number.isFinite(priceCzk) || priceCzk <= 0) return priceCzk;
  if (opts.priceIncludesVat === false) {
    return Math.round(priceCzk * (1 + CZ_VAT_RATE));
  }
  return Math.round(priceCzk);
}
