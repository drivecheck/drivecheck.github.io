from __future__ import annotations

import json
from pathlib import Path

from drivecheck_crawler.snapshot_crypto import decrypt_snapshot, encrypt_snapshot

PASSWORD = "test-pass-12"
PLAINTEXT = b'{"make":"Octavia"}'
GOLDEN = Path(__file__).resolve().parents[3] / "packages/pricing/src/fixtures/snapshot-crypto-golden.json"


def test_ciphertext_hides_plaintext_and_round_trips() -> None:
    ciphertext, meta = encrypt_snapshot(PLAINTEXT, PASSWORD)
    assert b"Octavia" not in ciphertext
    assert decrypt_snapshot(ciphertext, PASSWORD, meta) == PLAINTEXT


def test_wrong_password_fails() -> None:
    ciphertext, meta = encrypt_snapshot(PLAINTEXT, PASSWORD)
    try:
        decrypt_snapshot(ciphertext, "wrong-password", meta)
    except Exception:
        return
    raise AssertionError("decrypt should fail for the wrong password")


def test_golden_vector_round_trip() -> None:
    salt = bytes(range(16))
    nonce = bytes(range(12))
    ciphertext, meta = encrypt_snapshot(PLAINTEXT, PASSWORD, salt=salt, nonce=nonce)
    payload = {
        "password": PASSWORD,
        "plaintext_utf8": PLAINTEXT.decode("utf-8"),
        "ciphertext_b64": __import__("base64").b64encode(ciphertext).decode("ascii"),
        "meta": meta,
    }
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    raw = __import__("base64").b64decode(loaded["ciphertext_b64"])
    assert b"Octavia" not in raw
    assert decrypt_snapshot(raw, loaded["password"], loaded["meta"]) == PLAINTEXT
