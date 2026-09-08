-- Allow TipCars / Autobazar.eu (+ reserved Phase B/C ids) on listings.source.
-- Fresh installs get the same set via 001_schema.sql.

ALTER TABLE listings DROP CONSTRAINT IF EXISTS listings_source_check;

ALTER TABLE listings ADD CONSTRAINT listings_source_check
  CHECK (
    source = ANY (
      ARRAY[
        'sauto'::text,
        'bazos'::text,
        'tipcars'::text,
        'autobazar_eu'::text,
        'mobile_de'::text,
        'autoscout24'::text,
        'olx_pl'::text
      ]
    )
  );
