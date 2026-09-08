-- Constrained vehicle catalog (free multi-source sync → hard UI cascade)

CREATE TABLE IF NOT EXISTS vehicle_makes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name_normalized)
);

CREATE TABLE IF NOT EXISTS vehicle_models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  make_id UUID NOT NULL REFERENCES vehicle_makes(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  category TEXT NOT NULL CHECK (
    category IN ('passenger', 'van', 'caravan', 'motorcycle')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (make_id, name_normalized, category)
);

CREATE TABLE IF NOT EXISTS vehicle_variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id UUID NOT NULL REFERENCES vehicle_models(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (
    category IN ('passenger', 'van', 'caravan', 'motorcycle')
  ),
  year INT NOT NULL CHECK (year >= 1950 AND year <= 2100),
  body TEXT NOT NULL,
  fuel TEXT NOT NULL,
  transmission TEXT NOT NULL,
  motorization_label TEXT NOT NULL,
  power_kw INT,
  displacement_cc INT,
  engine_code TEXT,
  sources TEXT[] NOT NULL DEFAULT '{}',
  natural_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (natural_key)
);

CREATE INDEX IF NOT EXISTS vehicle_models_category_idx ON vehicle_models (category);
CREATE INDEX IF NOT EXISTS vehicle_variants_cascade_idx
  ON vehicle_variants (category, year, body, fuel, transmission);
CREATE INDEX IF NOT EXISTS vehicle_variants_model_year_idx
  ON vehicle_variants (model_id, year);

CREATE TABLE IF NOT EXISTS vehicle_catalog_sync_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('running', 'ok', 'error')),
  stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_text TEXT
);
