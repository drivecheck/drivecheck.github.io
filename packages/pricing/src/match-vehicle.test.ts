import { describe, expect, it } from "vitest";
import {
  MATCH_THRESHOLDS,
  filterAndRankOffersByVehicle,
  hardMatchVehicle,
  matchVehicle,
  offerMatchesVehicle,
  softScoreVehicle,
} from "./match-vehicle";

const octavia2019DieselDsg = {
  make: "Škoda",
  model: "Octavia",
  year: 2019,
  mileageKm: 120_000,
  fuel: "Nafta",
  transmission: "DSG / dvojspojka",
  body: "Kombi",
  drive: "Přední",
  powerKw: 110,
  featureKeys: ["heated_seats", "keyless"],
};

describe("offerMatchesVehicle (identity)", () => {
  const subject = { make: "Škoda", model: "Octavia" };

  it("accepts matching structured fields", () => {
    expect(
      offerMatchesVehicle(
        { make: "Skoda", model: "Octavia", title: "Škoda Octavia 2.0 TDI" },
        subject,
      ),
    ).toBe(true);
  });

  it("rejects brand-only listings even if model field is stamped", () => {
    expect(
      offerMatchesVehicle(
        { make: "Škoda", model: "Octavia", title: "Škoda Fabia 1.0 TSI" },
        subject,
      ),
    ).toBe(false);
  });

  it("accepts title-only matches when structured model is missing", () => {
    expect(
      offerMatchesVehicle(
        { make: "Škoda", model: null, title: "Prodám Octavia Combi" },
        subject,
      ),
    ).toBe(true);
  });

  it("accepts structured model when title is absent", () => {
    expect(
      offerMatchesVehicle({ make: "Škoda", model: "Octavia", title: null }, subject),
    ).toBe(true);
  });

  it("rejects unrelated makes", () => {
    expect(
      offerMatchesVehicle(
        { make: "VW", model: "Golf", title: "Volkswagen Golf 7" },
        subject,
      ),
    ).toBe(false);
  });

  it("handles multi-word models via title", () => {
    expect(
      offerMatchesVehicle(
        {
          make: "Jeep",
          model: "Grand Cherokee",
          title: "Jeep Grand Cherokee Limited",
        },
        { make: "Jeep", model: "Grand Cherokee" },
      ),
    ).toBe(true);
  });
});

describe("hardMatchVehicle precision", () => {
  it("rejects wrong model even with stamped fields", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Fabia 1.0 TSI",
        fuel: "Nafta",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(false);
    if (!hard.ok) expect(hard.reason).toBe("model_title");
  });

  it("rejects wrong fuel (benzin vs nafta)", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia 1.5 TSI",
        fuel: "Benzín",
        transmission: "DSG",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(false);
    if (!hard.ok) expect(hard.reason).toBe("fuel");
  });

  it("allows unknown fuel when other hard dims match", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia Combi 2.0 TDI DSG",
        fuel: null,
        transmission: "Automatická",
        body: "Kombi",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(true);
  });

  it("rejects manual when subject wants DSG", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia 2.0 TDI",
        fuel: "Diesel",
        transmission: "Manuální",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(false);
    if (!hard.ok) expect(hard.reason).toBe("transmission");
  });

  it("accepts diesel synonym + automatic when subject is DSG", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia Combi 2.0 TDI",
        fuel: "Diesel",
        transmission: "Automatická",
        body: "Combi",
        drive: "FWD",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(true);
  });

  it("rejects contradictory body (sedan vs kombi)", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia sedan",
        fuel: "Nafta",
        transmission: "DSG",
        body: "Sedan",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(false);
    if (!hard.ok) expect(hard.reason).toBe("body");
  });

  it("rejects year beyond hard max delta", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia Combi 2.0 TDI",
        fuel: "Nafta",
        transmission: "DSG",
        body: "Kombi",
        year: 2008,
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(false);
    if (!hard.ok) expect(hard.reason).toBe("year_hard");
  });

  it("does not treat 'Octavia' as MPV via substring 'van'", () => {
    const hard = hardMatchVehicle(
      {
        make: "Škoda",
        model: "Octavia",
        title: "Škoda Octavia 2.0 TDI",
        fuel: "Nafta",
        transmission: "DSG",
      },
      octavia2019DieselDsg,
    );
    expect(hard.ok).toBe(true);
  });
});

describe("softScoreVehicle + matchVehicle", () => {
  const near = {
    make: "Škoda",
    model: "Octavia",
    title: "Škoda Octavia Combi 2.0 TDI DSG",
    year: 2019,
    mileageKm: 115_000,
    fuel: "Nafta",
    transmission: "DSG / dvojspojka",
    body: "Kombi",
    drive: "Přední",
    powerKw: 110,
    featureKeys: ["heated_seats", "keyless", "parking_camera"],
  };

  const farYear = {
    ...near,
    year: 2014,
    mileageKm: 240_000,
    powerKw: 85,
    featureKeys: [] as string[],
  };

  it("ranks near-match above far year/km", () => {
    const nearScore = softScoreVehicle(near, octavia2019DieselDsg);
    const farScore = softScoreVehicle(farYear, octavia2019DieselDsg);
    expect(nearScore).toBeGreaterThan(farScore);
    expect(nearScore).toBeGreaterThanOrEqual(MATCH_THRESHOLDS.minScore);
  });

  it("boosts equipment overlap", () => {
    const withEq = softScoreVehicle(near, octavia2019DieselDsg);
    const withoutEq = softScoreVehicle(
      { ...near, featureKeys: [] },
      octavia2019DieselDsg,
    );
    expect(withEq).toBeGreaterThan(withoutEq);
  });

  it("hides offers below soft threshold", () => {
    // Hard-ok but intentionally terrible soft fit.
    const weak = {
      make: "Škoda",
      model: "Octavia",
      title: "Škoda Octavia",
      year: 2012,
      mileageKm: 380_000,
      fuel: null,
      transmission: null,
      body: null,
      drive: null,
      powerKw: null,
      featureKeys: [] as string[],
    };
    const m = matchVehicle(weak, octavia2019DieselDsg);
    // Year 2012 vs 2019 is within hard max (8) but soft score should sink.
    expect(m.ok).toBe(false);
    expect(m.score).toBeLessThan(MATCH_THRESHOLDS.minScore);
    expect(m.hardRejectReason).toBe("soft_threshold");
  });

  it("filterAndRankOffersByVehicle drops wrong cars and sorts best first", () => {
    const ranked = filterAndRankOffersByVehicle(
      [
        {
          ...near,
          priceCzk: 420_000,
          externalId: "near",
        },
        {
          make: "Škoda",
          model: "Fabia",
          title: "Škoda Fabia 1.0",
          fuel: "Nafta",
          transmission: "DSG",
          year: 2019,
          priceCzk: 200_000,
          externalId: "wrong-model",
        },
        {
          make: "Škoda",
          model: "Octavia",
          title: "Škoda Octavia 1.5 TSI",
          fuel: "Benzín",
          transmission: "DSG",
          year: 2019,
          priceCzk: 390_000,
          externalId: "wrong-fuel",
        },
        {
          ...near,
          year: 2018,
          mileageKm: 140_000,
          featureKeys: ["heated_seats"],
          priceCzk: 400_000,
          externalId: "ok-2nd",
        },
      ] as Array<typeof near & { priceCzk: number; externalId: string }>,
      octavia2019DieselDsg,
    );

    expect(ranked.map((o) => o.externalId)).toEqual(["near", "ok-2nd"]);
    expect(ranked[0]!.matchScore).toBeGreaterThanOrEqual(ranked[1]!.matchScore);
  });
});
