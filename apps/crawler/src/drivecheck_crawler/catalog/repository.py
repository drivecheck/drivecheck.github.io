from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Json


@dataclass(frozen=True)
class VariantRow:
    make: str
    model: str
    category: str
    year: int
    body: str
    fuel: str
    transmission: str
    motorization_label: str
    power_kw: int | None
    displacement_cc: int | None
    engine_code: str | None
    source: str


UPSERT_MAKE = """
INSERT INTO vehicle_makes (name, name_normalized)
VALUES (%(name)s, %(name_normalized)s)
ON CONFLICT (name_normalized) DO UPDATE SET name = EXCLUDED.name
RETURNING id
"""

UPSERT_MODEL = """
INSERT INTO vehicle_models (make_id, name, name_normalized, category)
VALUES (%(make_id)s, %(name)s, %(name_normalized)s, %(category)s)
ON CONFLICT (make_id, name_normalized, category) DO UPDATE SET name = EXCLUDED.name
RETURNING id
"""

UPSERT_VARIANT = """
INSERT INTO vehicle_variants (
  model_id, category, year, body, fuel, transmission, motorization_label,
  power_kw, displacement_cc, engine_code, sources, natural_key, updated_at
) VALUES (
  %(model_id)s, %(category)s, %(year)s, %(body)s, %(fuel)s, %(transmission)s,
  %(motorization_label)s, %(power_kw)s, %(displacement_cc)s, %(engine_code)s,
  ARRAY[%(source)s]::text[], %(natural_key)s, now()
)
ON CONFLICT (natural_key) DO UPDATE SET
  sources = (
    SELECT ARRAY(SELECT DISTINCT unnest(vehicle_variants.sources || EXCLUDED.sources))
  ),
  power_kw = COALESCE(EXCLUDED.power_kw, vehicle_variants.power_kw),
  displacement_cc = COALESCE(EXCLUDED.displacement_cc, vehicle_variants.displacement_cc),
  engine_code = COALESCE(EXCLUDED.engine_code, vehicle_variants.engine_code),
  updated_at = now()
RETURNING id, (xmax = 0) AS inserted
"""


class CatalogRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self._make_cache: dict[str, Any] = {}
        self._model_cache: dict[tuple[str, str, str], Any] = {}

    def upsert_variant(self, row: VariantRow) -> bool:
        from drivecheck_crawler.catalog.normalize import normalize_key

        make_key = normalize_key(row.make)
        if make_key not in self._make_cache:
            with self.conn.cursor() as cur:
                cur.execute(
                    UPSERT_MAKE,
                    {"name": row.make, "name_normalized": make_key},
                )
                self._make_cache[make_key] = cur.fetchone()[0]

        make_id = self._make_cache[make_key]
        model_key = normalize_key(row.model)
        model_cache_key = (str(make_id), model_key, row.category)
        if model_cache_key not in self._model_cache:
            with self.conn.cursor() as cur:
                cur.execute(
                    UPSERT_MODEL,
                    {
                        "make_id": make_id,
                        "name": row.model,
                        "name_normalized": model_key,
                        "category": row.category,
                    },
                )
                self._model_cache[model_cache_key] = cur.fetchone()[0]

        model_id = self._model_cache[model_cache_key]
        natural_key = "|".join(
            [
                str(model_id),
                str(row.year),
                normalize_key(row.body),
                normalize_key(row.fuel),
                normalize_key(row.transmission),
                normalize_key(row.motorization_label),
                str(row.power_kw if row.power_kw is not None else -1),
                str(row.displacement_cc if row.displacement_cc is not None else -1),
            ]
        )
        with self.conn.cursor() as cur:
            cur.execute(
                UPSERT_VARIANT,
                {
                    "model_id": model_id,
                    "category": row.category,
                    "year": row.year,
                    "body": row.body,
                    "fuel": row.fuel,
                    "transmission": row.transmission,
                    "motorization_label": row.motorization_label,
                    "power_kw": row.power_kw,
                    "displacement_cc": row.displacement_cc,
                    "engine_code": row.engine_code,
                    "source": row.source,
                    "natural_key": natural_key,
                },
            )
            result = cur.fetchone()
        return bool(result and result[1])

    def start_sync_run(self) -> Any:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle_catalog_sync_runs (status)
                VALUES ('running')
                RETURNING id
                """
            )
            return cur.fetchone()[0]

    def finish_sync_run(
        self,
        run_id: Any,
        *,
        status: str,
        stats: dict[str, Any],
        error_text: str | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vehicle_catalog_sync_runs
                SET finished_at = now(), status = %s, stats_json = %s, error_text = %s
                WHERE id = %s
                """,
                (status, Json(stats), error_text, run_id),
            )
