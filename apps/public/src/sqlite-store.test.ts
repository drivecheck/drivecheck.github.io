import { describe, expect, it } from "vitest";
import { priceVehicle } from "@drivecheck/pricing";
import initSqlJs from "sql.js";
import { catalogMakes, catalogModels, sqliteListingStore } from "./sqlite-store";

describe("sqliteListingStore", () => {
  it("prices an Octavia from a tiny sqlite db", async () => {
    const SQL = await initSqlJs();
    const db = new SQL.Database();
    db.run(`
      CREATE TABLE listings (
        id TEXT, source TEXT, external_id TEXT, url TEXT, make TEXT, model TEXT,
        year INTEGER, mileage_km INTEGER, price_czk INTEGER, seller_type TEXT,
        region TEXT, fuel TEXT, transmission TEXT, body TEXT, drive TEXT, power_kw INTEGER,
        feature_keys TEXT, title TEXT, published_at TEXT, first_seen TEXT, last_seen TEXT,
        status TEXT, vat_deductible INTEGER, price_includes_vat INTEGER, currency TEXT,
        price_foreign REAL, fx_rate_date TEXT, color TEXT, make_norm TEXT, model_norm TEXT
      );
      CREATE TABLE price_points (listing_id TEXT, price_czk INTEGER, observed_at TEXT);
    `);
    for (let i = 0; i < 12; i += 1) {
      db.run(
        `INSERT INTO listings (
          id, source, external_id, url, make, model, year, mileage_km, price_czk,
          seller_type, fuel, transmission, body, status, make_norm, model_norm,
          published_at, first_seen, last_seen, feature_keys
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
        [
          `id-${i}`,
          "sauto",
          `x${i}`,
          `https://www.sauto.cz/${i}`,
          "Škoda",
          "Octavia",
          2018 + (i % 3),
          100000 + i * 2000,
          290000 + i * 4000,
          "dealer",
          "Nafta",
          "Manuální",
          "Kombi",
          "active",
          "skoda",
          "octavia",
          "2026-01-01",
          "2026-01-01",
          "2026-08-01",
          "[]",
        ],
      );
    }
    const result = await priceVehicle(
      {
        mode: "quick",
        make: "Škoda",
        model: "Octavia",
        year: 2019,
        mileageKm: 120000,
        fuel: "Nafta",
      },
      sqliteListingStore(db),
    );
    expect(result.fairValueCzk).toBeGreaterThan(200000);
    expect(catalogMakes(db)).toContain("Škoda");
    expect(catalogModels(db, "Škoda")).toContain("Octavia");
    db.close();
  });
});
