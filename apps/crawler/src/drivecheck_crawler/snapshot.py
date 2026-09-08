from __future__ import annotations

import gzip
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from drivecheck_crawler.snapshot_crypto import SnapshotMeta, encrypt_snapshot

LOGGER = logging.getLogger(__name__)

LISTING_COLUMNS = [
    "id",
    "source",
    "external_id",
    "url",
    "make",
    "model",
    "generation",
    "trim",
    "year",
    "mileage_km",
    "fuel",
    "transmission",
    "drive",
    "power_kw",
    "displacement_cc",
    "body",
    "color",
    "seller_type",
    "region",
    "price_czk",
    "currency",
    "price_foreign",
    "fx_rate_date",
    "feature_keys",
    "title",
    "published_at",
    "first_seen",
    "last_seen",
    "status",
    "vat_deductible",
    "price_includes_vat",
]


def fold_token(value: str | None) -> str:
    if not value:
        return ""
    import unicodedata

    nfkd = unicodedata.normalize("NFD", value)
    stripped = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    return stripped.lower().strip()


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    text = str(value)
    return text if text else None


def _sql_num(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    return value


def _feature_json(value: Any) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value
    return json.dumps(list(value), ensure_ascii=False)


def write_sqlite(listings: Iterable[dict[str, Any]], points: Iterable[dict[str, Any]], path: Path) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE listings (
              id TEXT PRIMARY KEY,
              source TEXT NOT NULL,
              external_id TEXT NOT NULL,
              url TEXT NOT NULL,
              make TEXT,
              model TEXT,
              generation TEXT,
              trim TEXT,
              year INTEGER,
              mileage_km INTEGER,
              fuel TEXT,
              transmission TEXT,
              drive TEXT,
              power_kw INTEGER,
              displacement_cc INTEGER,
              body TEXT,
              color TEXT,
              seller_type TEXT,
              region TEXT,
              price_czk INTEGER NOT NULL,
              currency TEXT,
              price_foreign REAL,
              fx_rate_date TEXT,
              feature_keys TEXT,
              title TEXT,
              published_at TEXT,
              first_seen TEXT,
              last_seen TEXT,
              status TEXT NOT NULL,
              vat_deductible INTEGER,
              price_includes_vat INTEGER,
              make_norm TEXT NOT NULL,
              model_norm TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE price_points (
              listing_id TEXT NOT NULL,
              price_czk INTEGER NOT NULL,
              observed_at TEXT
            )
            """
        )
        listing_rows = []
        active = 0
        removed = 0
        for row in listings:
            status = row.get("status") or "active"
            if status == "removed":
                removed += 1
            else:
                active += 1
            listing_rows.append(
                (
                    str(row["id"]),
                    row["source"],
                    row["external_id"],
                    row["url"],
                    row.get("make"),
                    row.get("model"),
                    row.get("generation"),
                    row.get("trim"),
                    row.get("year"),
                    row.get("mileage_km"),
                    row.get("fuel"),
                    row.get("transmission"),
                    row.get("drive"),
                    row.get("power_kw"),
                    row.get("displacement_cc"),
                    row.get("body"),
                    row.get("color"),
                    row.get("seller_type"),
                    row.get("region"),
                    int(row["price_czk"]),
                    row.get("currency") or "CZK",
                    _sql_num(row.get("price_foreign")),
                    _as_iso(row.get("fx_rate_date")),
                    _feature_json(row.get("feature_keys")),
                    row.get("title"),
                    _as_iso(row.get("published_at")),
                    _as_iso(row.get("first_seen")),
                    _as_iso(row.get("last_seen")),
                    status,
                    None if row.get("vat_deductible") is None else int(bool(row["vat_deductible"])),
                    None
                    if row.get("price_includes_vat") is None
                    else int(bool(row["price_includes_vat"])),
                    fold_token(row.get("make")),
                    fold_token(row.get("model")),
                )
            )
        conn.executemany(
            f"""
            INSERT INTO listings VALUES ({",".join("?" for _ in range(33))})
            """,
            listing_rows,
        )
        point_rows = [
            (str(p["listing_id"]), int(p["price_czk"]), _as_iso(p.get("observed_at")))
            for p in points
        ]
        conn.executemany(
            "INSERT INTO price_points (listing_id, price_czk, observed_at) VALUES (?, ?, ?)",
            point_rows,
        )
        conn.execute(
            "CREATE INDEX listings_match_idx ON listings (status, make_norm, model_norm, year)"
        )
        conn.execute("CREATE INDEX price_points_listing_idx ON price_points (listing_id)")
        conn.commit()
        return {
            "listings_active": active,
            "listings_removed": removed,
            "price_points": len(point_rows),
        }
    finally:
        conn.close()


def fetch_postgres_snapshot(conn: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cols = ", ".join(LISTING_COLUMNS)
    listings = conn.execute(
        f"SELECT {cols} FROM listings WHERE price_czk IS NOT NULL"
    ).fetchall()
    points = conn.execute(
        "SELECT listing_id, price_czk, observed_at FROM price_points ORDER BY observed_at ASC"
    ).fetchall()
    listing_dicts = []
    for row in listings:
        if hasattr(row, "keys"):
            listing_dicts.append(dict(row))
        else:
            listing_dicts.append(dict(zip(LISTING_COLUMNS, row, strict=True)))
    point_dicts = []
    for row in points:
        if hasattr(row, "keys"):
            point_dicts.append(dict(row))
        else:
            point_dicts.append(
                {"listing_id": row[0], "price_czk": row[1], "observed_at": row[2]}
            )
    return listing_dicts, point_dicts


def encrypt_sqlite_file(
    sqlite_path: Path,
    password: str,
    *,
    cipher_path: Path,
    meta_path: Path,
    counts: dict[str, int],
) -> SnapshotMeta:
    raw = sqlite_path.read_bytes()
    gz = gzip.compress(raw, compresslevel=6)
    ciphertext, meta = encrypt_snapshot(gz, password)
    extra = {
        **meta,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "encoding": "gzip+sqlite",
        **counts,
    }
    cipher_path.write_bytes(ciphertext)
    meta_path.write_text(json.dumps(extra, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %s (%s bytes) and %s", cipher_path, len(ciphertext), meta_path)
    return extra  # type: ignore[return-value]


def export_encrypted_snapshot(
    *,
    listings: Iterable[dict[str, Any]],
    points: Iterable[dict[str, Any]],
    sqlite_path: Path,
    cipher_path: Path,
    meta_path: Path,
    password: str,
) -> dict[str, int]:
    counts = write_sqlite(listings, points, sqlite_path)
    encrypt_sqlite_file(
        sqlite_path,
        password,
        cipher_path=cipher_path,
        meta_path=meta_path,
        counts=counts,
    )
    return counts


def decrypt_cipher_to_sqlite(cipher_path: Path, meta_path: Path, password: str, sqlite_path: Path) -> None:
    from drivecheck_crawler.snapshot_crypto import decrypt_snapshot

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    gz = decrypt_snapshot(cipher_path.read_bytes(), password, meta)
    sqlite_path.write_bytes(gzip.decompress(gz))


def restore_sqlite_to_postgres(sqlite_path: Path, pg_conn: Any) -> dict[str, int]:
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    listings = source.execute("SELECT * FROM listings").fetchall()
    points = source.execute("SELECT listing_id, price_czk, observed_at FROM price_points").fetchall()
    upsert = """
      INSERT INTO listings (
        id, source, external_id, url, make, model, generation, trim, year, mileage_km,
        fuel, transmission, drive, power_kw, displacement_cc, body, color, seller_type,
        region, price_czk, currency, price_foreign, fx_rate_date, feature_keys, title,
        published_at, first_seen, last_seen, status, vat_deductible, price_includes_vat
      ) VALUES (
        %(id)s, %(source)s, %(external_id)s, %(url)s, %(make)s, %(model)s, %(generation)s,
        %(trim)s, %(year)s, %(mileage_km)s, %(fuel)s, %(transmission)s, %(drive)s,
        %(power_kw)s, %(displacement_cc)s, %(body)s, %(color)s, %(seller_type)s, %(region)s,
        %(price_czk)s, %(currency)s, %(price_foreign)s, %(fx_rate_date)s, %(feature_keys)s,
        %(title)s, %(published_at)s, %(first_seen)s, %(last_seen)s, %(status)s,
        %(vat_deductible)s, %(price_includes_vat)s
      )
      ON CONFLICT (source, external_id) DO UPDATE SET
        url = EXCLUDED.url,
        make = COALESCE(EXCLUDED.make, listings.make),
        model = COALESCE(EXCLUDED.model, listings.model),
        year = COALESCE(EXCLUDED.year, listings.year),
        mileage_km = COALESCE(EXCLUDED.mileage_km, listings.mileage_km),
        price_czk = EXCLUDED.price_czk,
        status = EXCLUDED.status,
        last_seen = COALESCE(EXCLUDED.last_seen, listings.last_seen),
        feature_keys = EXCLUDED.feature_keys
    """
    inserted = 0
    with pg_conn.cursor() as cur:
        for row in listings:
            payload = dict(row)
            payload.pop("make_norm", None)
            payload.pop("model_norm", None)
            raw_keys = payload.get("feature_keys")
            if isinstance(raw_keys, str):
                try:
                    payload["feature_keys"] = json.loads(raw_keys)
                except json.JSONDecodeError:
                    payload["feature_keys"] = []
            payload["vat_deductible"] = (
                None if payload.get("vat_deductible") is None else bool(payload["vat_deductible"])
            )
            payload["price_includes_vat"] = (
                None
                if payload.get("price_includes_vat") is None
                else bool(payload["price_includes_vat"])
            )
            cur.execute(upsert, payload)
            inserted += 1
        for row in points:
            cur.execute(
                """
                INSERT INTO price_points (listing_id, price_czk, observed_at)
                VALUES (%s, %s, %s)
                """,
                (row["listing_id"], row["price_czk"], row["observed_at"]),
            )
    pg_conn.commit()
    source.close()
    return {"listings": inserted, "price_points": len(points)}

