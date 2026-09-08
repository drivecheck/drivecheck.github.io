CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE feature_tags (
  key TEXT PRIMARY KEY,
  label_cs TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE listings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL CHECK (
    source IN (
      'sauto',
      'bazos',
      'tipcars',
      'autobazar_eu',
      'mobile_de',
      'autoscout24',
      'olx_pl'
    )
  ),
  external_id TEXT NOT NULL,
  url TEXT NOT NULL,
  make TEXT,
  model TEXT,
  generation TEXT,
  trim TEXT,
  year INT,
  mileage_km INT,
  fuel TEXT,
  transmission TEXT,
  drive TEXT,
  power_kw INT,
  displacement_cc INT,
  body TEXT,
  seller_type TEXT CHECK (seller_type IS NULL OR seller_type IN ('private', 'dealer', 'unknown')),
  region TEXT,
  price_czk INT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CZK',
  feature_keys TEXT[] NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
  first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, external_id)
);

CREATE TABLE price_points (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  price_czk INT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX price_points_listing_observed_idx ON price_points (listing_id, observed_at);

CREATE TABLE appraisals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mode TEXT NOT NULL CHECK (mode IN ('quick', 'detailed')),
  input_json JSONB NOT NULL,
  result_json JSONB,
  override_price_czk INT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Explicitly NO columns for seller name, phone, email, or profile URLs.
