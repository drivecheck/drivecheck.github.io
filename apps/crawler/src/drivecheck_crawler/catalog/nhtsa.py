from __future__ import annotations

import logging

import httpx
import psycopg

from drivecheck_crawler.catalog.normalize import display_make, normalize_key

log = logging.getLogger(__name__)

VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles"

FOCUS_MAKES = [
    "VOLKSWAGEN",
    "SKODA",
    "AUDI",
    "BMW",
    "MERCEDES-BENZ",
    "FORD",
    "OPEL",
    "RENAULT",
    "PEUGEOT",
    "CITROEN",
    "TOYOTA",
    "HYUNDAI",
    "KIA",
    "SEAT",
    "CUPRA",
    "VOLVO",
    "MAZDA",
    "HONDA",
    "NISSAN",
    "FIAT",
    "DACIA",
    "SUZUKI",
    "MITSUBISHI",
    "PORSCHE",
    "MINI",
    "TESLA",
    "LAND ROVER",
    "JAGUAR",
    "ALFA ROMEO",
    "SUBARU",
    "IVECO",
    "HARLEY-DAVIDSON",
    "YAMAHA",
    "KAWASAKI",
    "DUCATI",
    "TRIUMPH",
    "KTM",
    "PIAGGIO",
]


def _category_for_make(make: str) -> str:
    key = normalize_key(make)
    if key in {
        "harley-davidson",
        "yamaha",
        "kawasaki",
        "ducati",
        "triumph",
        "ktm",
        "piaggio",
    }:
        return "motorcycle"
    if key in {"iveco"}:
        return "van"
    return "passenger"


def sync_nhtsa_make_models(client: httpx.Client, conn: psycopg.Connection) -> int:
    """Upsert make/model rows only (no invented year/motorization variants)."""
    count = 0
    with conn.cursor() as cur:
        for make_raw in FOCUS_MAKES:
            url = f"{VPIC}/GetModelsForMake/{make_raw}?format=json"
            try:
                resp = client.get(url, timeout=60.0)
                resp.raise_for_status()
                results = resp.json().get("Results") or []
            except Exception:
                log.exception("NHTSA models failed for %s", make_raw)
                continue
            make = display_make(make_raw)
            if not make:
                continue
            make_key = normalize_key(make)
            category = _category_for_make(make_raw)
            cur.execute(
                """
                INSERT INTO vehicle_makes (name, name_normalized)
                VALUES (%s, %s)
                ON CONFLICT (name_normalized) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (make, make_key),
            )
            make_id = cur.fetchone()[0]
            for item in results:
                model = (item.get("Model_Name") or "").strip()
                if not model:
                    continue
                model_name = model.title() if model.isupper() else model
                cur.execute(
                    """
                    INSERT INTO vehicle_models (make_id, name, name_normalized, category)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (make_id, name_normalized, category) DO UPDATE SET name = EXCLUDED.name
                    """,
                    (make_id, model_name, normalize_key(model_name), category),
                )
                count += 1
            log.info("NHTSA make=%s models=%s", make_raw, len(results))
    return count
