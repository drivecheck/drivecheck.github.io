from __future__ import annotations

import argparse
import logging
import time

from drivecheck_crawler.pipeline import run_seed
from drivecheck_crawler.sources import (
    cli_source_choices,
    fair_loop_rotation,
    probeable_source_ids,
    resolve_sources,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="drivecheck-crawler")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_choices = cli_source_choices(include_all=True)
    seed = sub.add_parser("seed", help="Run polite seed crawl batches")
    seed.add_argument(
        "--source",
        default="all",
        help=f"all, one id, or comma-separated among: {', '.join(seed_choices)}",
    )
    seed.add_argument("--max-pages", type=int, default=None)
    seed.add_argument(
        "--loop",
        action="store_true",
        help="Keep running batches forever (background seed)",
    )
    seed.add_argument(
        "--sleep-between-batches",
        type=int,
        default=30,
        help="Seconds to sleep between loop batches",
    )

    catalog = sub.add_parser(
        "catalog-sync",
        help="Sync free vehicle catalog (RDW / NHTSA / Wikidata) into Postgres",
    )
    catalog.add_argument(
        "--sources",
        default="rdw_grouped,rdw,nhtsa,wikidata",
        help="Comma-separated: rdw_grouped,rdw,nhtsa,wikidata",
    )
    catalog.add_argument("--max-rdw-rows", type=int, default=120_000)
    catalog.add_argument("--max-rdw-groups", type=int, default=200_000)

    live = sub.add_parser("live-api", help="HTTP API for on-demand live market search")
    live.add_argument("--host", default="0.0.0.0")
    live.add_argument("--port", type=int, default=8090)

    sub.add_parser(
        "market-aggregate",
        help="Recompute today's daily market price aggregates from active listings",
    )

    thumbs = sub.add_parser(
        "thumbs-backfill",
        help="Download missing listing cover WebP thumbnails",
    )
    thumbs.add_argument("--limit", type=int, default=100)
    thumbs.add_argument(
        "--source",
        choices=cli_source_choices(include_all=False),
        default=None,
        help="Only backfill one marketplace",
    )

    purge = sub.add_parser(
        "bazos-purge-parts",
        help="Soft-hide Bazos car-parts listings (status=removed, never DELETE)",
    )
    purge.add_argument(
        "--apply",
        action="store_true",
        help="Set status=removed for matched rows (default is dry-run)",
    )
    purge.add_argument("--limit", type=int, default=50_000)

    ab_fix = sub.add_parser(
        "autobazar-fix-prices",
        help=(
            "Re-fetch Autobazar.eu details for absurd price_czk rows "
            "(FX poison) and UPDATE price/currency — never DELETE"
        ),
    )
    ab_fix.add_argument(
        "--min-price",
        type=int,
        default=300_000,
        help="Only rows with price_czk >= this (default 300000)",
    )
    ab_fix.add_argument("--limit", type=int, default=200)
    ab_fix.add_argument(
        "--apply",
        action="store_true",
        help="Persist UPDATEs (default is dry-run)",
    )

    probe = sub.add_parser(
        "probe-actives",
        help=(
            "Existence-check DB-active listings on the source "
            "(404/410 → status=removed; never treat 429/5xx as gone)"
        ),
    )
    probe.add_argument(
        "--source",
        default="all",
        help=f"all or comma-separated among: {', '.join(probeable_source_ids())}",
    )
    probe.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max actives to probe per source (default: config probe_limit_per_source)",
    )
    probe.add_argument(
        "--apply",
        action="store_true",
        help="Persist removals + touch last_seen for live (default is dry-run)",
    )
    probe.add_argument(
        "--no-touch-live",
        action="store_true",
        help="When applying, do not refresh last_seen for LIVE verdicts",
    )

    fx = sub.add_parser(
        "fx-sync",
        help="Fetch ECB daily rates, store fx_rates, re-quote import price_czk",
    )
    fx.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not hit ECB — load the latest stored snapshot only",
    )
    fx.add_argument(
        "--no-backfill",
        action="store_true",
        help="Skip re-quoting stored import listings",
    )

    snap = sub.add_parser(
        "snapshot-export",
        help="Export listings+price_points to encrypted snapshot.bin for Pages",
    )
    snap.add_argument("--sqlite", default="listings.sqlite")
    snap.add_argument("--cipher", default="snapshot.bin")
    snap.add_argument("--meta", default="snapshot.meta.json")
    snap.add_argument(
        "--password-env",
        default="SNAPSHOT_PASSWORD",
        help="Env var holding the company password (never pass on CLI)",
    )

    restore = sub.add_parser(
        "snapshot-restore",
        help="Decrypt snapshot.bin and upsert into Postgres",
    )
    restore.add_argument("--cipher", default="snapshot.bin")
    restore.add_argument("--meta", default="snapshot.meta.json")
    restore.add_argument("--sqlite", default="listings.sqlite")
    restore.add_argument("--password-env", default="SNAPSHOT_PASSWORD")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "seed":
        source_ids = resolve_sources(args.source)
        # Multi-source --loop: one source per batch (fair rotation). A single
        # run_seed("all") serializes CZ then import and can leave AutoScout24
        # waiting 30+ minutes behind Sauto/Autobazar detail crawls.
        if args.loop and len(source_ids) > 1:
            from drivecheck_crawler.config import get_config
            from drivecheck_crawler.probe import run_probe_actives

            config = get_config()
            rotation = fair_loop_rotation(source_ids)
            # Probe sources we actually crawl; fall back to all probeable.
            crawled = set(source_ids)
            probe_sources = [s for s in probeable_source_ids() if s in crawled] or list(
                probeable_source_ids()
            )
            logging.info("Seed loop rotation (%s sources): %s", len(rotation), rotation)
            if config.probe_in_seed_loop:
                logging.info(
                    "Seed loop will probe after each full rotation "
                    "(limit=%s, sources=%s)",
                    config.probe_loop_limit,
                    probe_sources,
                )
            idx = 0
            probe_idx = 0
            while True:
                sid = rotation[idx % len(rotation)]
                logging.info(
                    "Loop batch source=%s (%s/%s)",
                    sid,
                    (idx % len(rotation)) + 1,
                    len(rotation),
                )
                result = run_seed(sid, max_pages=args.max_pages)
                logging.info("Batch result: %s", result)
                idx += 1
                # After a full discover rotation, certify a batch of actives
                # (soft-deleted Sauto returns HTTP 200 + status=deleted).
                if (
                    config.probe_in_seed_loop
                    and probe_sources
                    and idx % len(rotation) == 0
                ):
                    probe_src = probe_sources[probe_idx % len(probe_sources)]
                    probe_idx += 1
                    logging.info(
                        "Loop probe source=%s limit=%s",
                        probe_src,
                        config.probe_loop_limit,
                    )
                    try:
                        probe_result = run_probe_actives(
                            source=probe_src,
                            limit=config.probe_loop_limit,
                            dry_run=False,
                            touch_live=True,
                            config=config,
                        )
                        logging.info("Loop probe result: %s", probe_result)
                    except Exception:
                        logging.exception(
                            "Loop probe failed source=%s — continuing seed",
                            probe_src,
                        )
                time.sleep(args.sleep_between_batches)
        else:
            while True:
                result = run_seed(args.source, max_pages=args.max_pages)
                logging.info("Batch result: %s", result)
                if not args.loop:
                    break
                time.sleep(args.sleep_between_batches)
    elif args.command == "catalog-sync":
        from drivecheck_crawler.catalog.sync import run_catalog_sync

        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        result = run_catalog_sync(
            sources=sources,
            max_rdw_rows=args.max_rdw_rows,
            max_rdw_groups=args.max_rdw_groups,
        )
        logging.info("Catalog sync result: %s", result)
    elif args.command == "live-api":
        from drivecheck_crawler.live_api import serve

        serve(host=args.host, port=args.port)
    elif args.command == "market-aggregate":
        from datetime import datetime, timezone

        from drivecheck_crawler.config import get_config
        from drivecheck_crawler.market_aggregate import record_daily_market_aggregates
        from drivecheck_crawler.repository import ListingRepository

        config = get_config()
        count = record_daily_market_aggregates(
            ListingRepository(config.database_url),
            datetime.now(timezone.utc),
        )
        logging.info("Daily market aggregates upserted: %s", count)
    elif args.command == "thumbs-backfill":
        from drivecheck_crawler.thumbs.sync import run_thumbs_backfill

        result = run_thumbs_backfill(limit=args.limit, source=args.source)
        logging.info("Thumbs backfill: %s", result)
    elif args.command == "bazos-purge-parts":
        from drivecheck_crawler.bazos_purge_parts import run_bazos_purge_parts

        dry_run = not args.apply
        result = run_bazos_purge_parts(dry_run=dry_run, limit=args.limit)
        logging.info("Bazos purge parts: %s", result)
    elif args.command == "autobazar-fix-prices":
        from drivecheck_crawler.autobazar_fix_prices import run_autobazar_fix_prices

        result = run_autobazar_fix_prices(
            min_price_czk=args.min_price,
            limit=args.limit,
            dry_run=not args.apply,
        )
        logging.info("Autobazar fix prices: %s", result)
    elif args.command == "probe-actives":
        from drivecheck_crawler.config import get_config
        from drivecheck_crawler.probe import run_probe_actives

        config = get_config()
        limit = (
            args.limit
            if args.limit is not None
            else config.probe_limit_per_source
        )
        result = run_probe_actives(
            source=args.source,
            limit=limit,
            dry_run=not args.apply,
            touch_live=not args.no_touch_live,
            config=config,
        )
        logging.info("Probe actives: %s", result)
    elif args.command == "fx-sync":
        from drivecheck_crawler.config import get_config
        from drivecheck_crawler.fx_sync import run_fx_sync
        from drivecheck_crawler.repository import ListingRepository

        config = get_config()
        result = run_fx_sync(
            ListingRepository(config.database_url),
            fetch=not args.no_fetch,
            backfill=not args.no_backfill,
        )
        logging.info("FX sync: %s", result)
    elif args.command == "snapshot-export":
        import os
        from pathlib import Path

        import psycopg
        from psycopg.rows import dict_row

        from drivecheck_crawler.config import get_config
        from drivecheck_crawler.snapshot import (
            export_encrypted_snapshot,
            fetch_postgres_snapshot,
        )

        password = os.environ.get(args.password_env, "").strip()
        if len(password) < 8:
            raise SystemExit(
                f"{args.password_env} must be set to a password of at least 8 characters"
            )
        config = get_config()
        with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
            listings, points = fetch_postgres_snapshot(conn)
        counts = export_encrypted_snapshot(
            listings=listings,
            points=points,
            sqlite_path=Path(args.sqlite),
            cipher_path=Path(args.cipher),
            meta_path=Path(args.meta),
            password=password,
        )
        logging.info("Snapshot export: %s", counts)
    elif args.command == "snapshot-restore":
        import os
        from pathlib import Path

        import psycopg

        from drivecheck_crawler.config import get_config
        from drivecheck_crawler.snapshot import (
            decrypt_cipher_to_sqlite,
            restore_sqlite_to_postgres,
        )

        password = os.environ.get(args.password_env, "").strip()
        if len(password) < 8:
            raise SystemExit(
                f"{args.password_env} must be set to a password of at least 8 characters"
            )
        sqlite_path = Path(args.sqlite)
        decrypt_cipher_to_sqlite(Path(args.cipher), Path(args.meta), password, sqlite_path)
        config = get_config()
        with psycopg.connect(config.database_url) as conn:
            result = restore_sqlite_to_postgres(sqlite_path, conn)
        logging.info("Snapshot restore: %s", result)


if __name__ == "__main__":
    main()
