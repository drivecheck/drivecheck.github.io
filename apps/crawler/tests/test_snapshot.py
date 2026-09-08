from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

from drivecheck_crawler.snapshot import export_encrypted_snapshot, fold_token, write_sqlite
from drivecheck_crawler.snapshot_crypto import decrypt_snapshot


def test_fold_token_strips_czech_marks() -> None:
    assert fold_token("Škoda") == "skoda"


def test_write_sqlite_and_encrypt_hides_make(tmp_path: Path) -> None:
    listings = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "source": "sauto",
            "external_id": "1",
            "url": "https://www.sauto.cz/1",
            "make": "Škoda",
            "model": "Octavia",
            "year": 2019,
            "mileage_km": 120000,
            "price_czk": 300000,
            "status": "active",
            "feature_keys": ["keyless"],
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source": "bazos",
            "external_id": "2",
            "url": "https://auto.bazos.cz/2",
            "make": "Škoda",
            "model": "Octavia",
            "year": 2018,
            "mileage_km": 140000,
            "price_czk": 280000,
            "status": "removed",
            "feature_keys": [],
        },
    ]
    points = [
        {"listing_id": listings[0]["id"], "price_czk": 310000, "observed_at": None},
        {"listing_id": listings[0]["id"], "price_czk": 300000, "observed_at": None},
    ]
    sqlite_path = tmp_path / "listings.sqlite"
    counts = write_sqlite(listings, points, sqlite_path)
    assert counts == {"listings_active": 1, "listings_removed": 1, "price_points": 2}
    db = sqlite3.connect(sqlite_path)
    make_norm = db.execute("SELECT make_norm FROM listings LIMIT 1").fetchone()[0]
    assert make_norm == "skoda"
    n = db.execute("SELECT count(*) FROM listings").fetchone()[0]
    assert n == 2
    db.close()

    cipher = tmp_path / "snapshot.bin"
    meta_path = tmp_path / "snapshot.meta.json"
    export_encrypted_snapshot(
        listings=listings,
        points=points,
        sqlite_path=sqlite_path,
        cipher_path=cipher,
        meta_path=meta_path,
        password="test-pass-12",
    )
    raw = cipher.read_bytes()
    assert b"Octavia" not in raw
    assert b"Skoda" not in raw
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    plain = decrypt_snapshot(raw, "test-pass-12", meta)
    sqlite_bytes = gzip.decompress(plain)
    assert b"Octavia" in sqlite_bytes


def test_decrypt_cipher_to_sqlite_round_trip(tmp_path: Path) -> None:
    listings = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "source": "sauto",
            "external_id": "1",
            "url": "https://www.sauto.cz/1",
            "make": "Škoda",
            "model": "Octavia",
            "year": 2019,
            "mileage_km": 1,
            "price_czk": 1,
            "status": "active",
            "feature_keys": [],
        }
    ]
    sqlite_path = tmp_path / "a.sqlite"
    cipher = tmp_path / "snapshot.bin"
    meta_path = tmp_path / "snapshot.meta.json"
    export_encrypted_snapshot(
        listings=listings,
        points=[],
        sqlite_path=sqlite_path,
        cipher_path=cipher,
        meta_path=meta_path,
        password="test-pass-12",
    )
    out = tmp_path / "b.sqlite"
    from drivecheck_crawler.snapshot import decrypt_cipher_to_sqlite

    decrypt_cipher_to_sqlite(cipher, meta_path, "test-pass-12", out)
    db = sqlite3.connect(out)
    assert db.execute("SELECT count(*) FROM listings").fetchone()[0] == 1
    db.close()
