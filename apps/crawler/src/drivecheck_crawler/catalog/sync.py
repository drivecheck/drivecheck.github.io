from __future__ import annotations

import logging
from typing import Any

import httpx
import psycopg

from drivecheck_crawler.catalog.nhtsa import sync_nhtsa_make_models
from drivecheck_crawler.catalog.rdw import iter_rdw_variants
from drivecheck_crawler.catalog.rdw_grouped import iter_rdw_grouped_variants
from drivecheck_crawler.catalog.repository import CatalogRepository
from drivecheck_crawler.catalog.wikidata import sync_wikidata_make_models
from drivecheck_crawler.config import get_config

log = logging.getLogger(__name__)


def run_catalog_sync(
    *,
    sources: list[str] | None = None,
    max_rdw_rows: int = 120_000,
    max_rdw_groups: int = 200_000,
) -> dict[str, Any]:
    cfg = get_config()
    wanted = set(sources or ["rdw", "rdw_grouped", "nhtsa", "wikidata"])
    stats: dict[str, Any] = {
        "inserted": 0,
        "upserted": 0,
        "by_source": {},
        "errors": [],
    }

    with psycopg.connect(cfg.database_url) as conn:
        repo = CatalogRepository(conn)
        run_id = repo.start_sync_run()
        conn.commit()
        try:
            with httpx.Client(
                headers={"User-Agent": cfg.user_agent},
                follow_redirects=True,
            ) as client:
                if "rdw_grouped" in wanted:
                    n = 0
                    for row in iter_rdw_grouped_variants(client, max_groups=max_rdw_groups):
                        inserted = repo.upsert_variant(row)
                        n += 1
                        stats["inserted" if inserted else "upserted"] += 1
                        if n % 1000 == 0:
                            conn.commit()
                    stats["by_source"]["rdw_grouped"] = n
                    conn.commit()
                    log.info("rdw_grouped done n=%s", n)

                if "rdw" in wanted:
                    n = 0
                    for row in iter_rdw_variants(client, max_rows=max_rdw_rows):
                        inserted = repo.upsert_variant(row)
                        n += 1
                        stats["inserted" if inserted else "upserted"] += 1
                        if n % 500 == 0:
                            conn.commit()
                    stats["by_source"]["rdw"] = n
                    conn.commit()
                    log.info("rdw plate-enrichment done n=%s", n)

                if "nhtsa" in wanted:
                    n = sync_nhtsa_make_models(client, conn)
                    stats["by_source"]["nhtsa_models"] = n
                    conn.commit()

                if "wikidata" in wanted:
                    n = sync_wikidata_make_models(client, conn)
                    stats["by_source"]["wikidata_models"] = n
                    conn.commit()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT category, COUNT(*)::int
                    FROM vehicle_variants
                    GROUP BY category
                    ORDER BY category
                    """
                )
                stats["variants_by_category"] = {r[0]: r[1] for r in cur.fetchall()}
                cur.execute("SELECT COUNT(*)::int FROM vehicle_makes")
                stats["makes"] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*)::int FROM vehicle_models")
                stats["models"] = cur.fetchone()[0]

            repo.finish_sync_run(run_id, status="ok", stats=stats)
            conn.commit()
            return stats
        except Exception as exc:
            log.exception("catalog sync failed")
            stats["errors"].append(str(exc))
            repo.finish_sync_run(run_id, status="error", stats=stats, error_text=str(exc))
            conn.commit()
            raise
