import { describe, expect, it } from "vitest";
import { inclVatComparable } from "./vat";

describe("inclVatComparable", () => {
  it("grosses up asks that exclude VAT", () => {
    expect(
      inclVatComparable(100_000, {
        priceIncludesVat: false,
        vatDeductible: true,
      }),
    ).toBe(121_000);
  });

  it("leaves consumer incl-VAT asks unchanged", () => {
    expect(
      inclVatComparable(250_000, {
        priceIncludesVat: true,
        vatDeductible: false,
      }),
    ).toBe(250_000);
  });
});
