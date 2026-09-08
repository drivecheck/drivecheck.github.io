from __future__ import annotations

import logging

import httpx
import psycopg

from drivecheck_crawler.catalog.normalize import display_make, normalize_key

log = logging.getLogger(__name__)

SPARQL = "https://query.wikidata.org/sparql"

QUERIES = {
    "passenger": """
    SELECT DISTINCT ?makeLabel ?modelLabel WHERE {
      ?model wdt:P31/wdt:P279* wd:Q3231690 .
      ?model wdt:P176 ?make .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,cs,de". }
    }
    LIMIT 5000
    """,
    "motorcycle": """
    SELECT DISTINCT ?makeLabel ?modelLabel WHERE {
      ?model wdt:P31/wdt:P279* wd:Q23925344 .
      ?model wdt:P176 ?make .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,cs,de". }
    }
    LIMIT 3000
    """,
}


def sync_wikidata_make_models(client: httpx.Client, conn: psycopg.Connection) -> int:
    """Upsert make/model rows from Wikidata (no invented variants)."""
    count = 0
    with conn.cursor() as cur:
        for category, query in QUERIES.items():
            try:
                resp = client.get(
                    SPARQL,
                    params={"query": query, "format": "json"},
                    headers={
                        "Accept": "application/sparql-results+json",
                        "User-Agent": "DrivecheckCatalog/0.1 (internal)",
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                bindings = resp.json()["results"]["bindings"]
            except Exception:
                log.exception("Wikidata query failed category=%s", category)
                continue

            for row in bindings:
                make_raw = row.get("makeLabel", {}).get("value", "").strip()
                model_raw = row.get("modelLabel", {}).get("value", "").strip()
                if not make_raw or not model_raw:
                    continue
                if make_raw.startswith("Q") or model_raw.startswith("Q"):
                    continue
                make = display_make(make_raw)
                if not make:
                    continue
                cur.execute(
                    """
                    INSERT INTO vehicle_makes (name, name_normalized)
                    VALUES (%s, %s)
                    ON CONFLICT (name_normalized) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (make, normalize_key(make)),
                )
                make_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO vehicle_models (make_id, name, name_normalized, category)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (make_id, name_normalized, category) DO UPDATE SET name = EXCLUDED.name
                    """,
                    (make_id, model_raw, normalize_key(model_raw), category),
                )
                count += 1
            log.info("Wikidata category=%s rows=%s", category, count)
    return count
