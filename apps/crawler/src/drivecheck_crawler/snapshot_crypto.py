from __future__ import annotations

import base64
import os
from typing import Any, TypedDict

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ARGON2_TIME_COST = 3
ARGON2_MEMORY_KIB = 32_768
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12
META_VERSION = 1


class SnapshotMeta(TypedDict):
    v: int
    kdf: str
    m: int
    t: int
    p: int
    salt_b64: str
    nonce_b64: str


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def derive_key(password: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_KIB,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )


def encrypt_snapshot(
    plaintext: bytes,
    password: str,
    *,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> tuple[bytes, SnapshotMeta]:
    salt_bytes = salt if salt is not None else os.urandom(SALT_LEN)
    nonce_bytes = nonce if nonce is not None else os.urandom(NONCE_LEN)
    if len(salt_bytes) != SALT_LEN:
        raise ValueError("salt must be 16 bytes")
    if len(nonce_bytes) != NONCE_LEN:
        raise ValueError("nonce must be 12 bytes")
    key = derive_key(password, salt_bytes)
    ciphertext = AESGCM(key).encrypt(nonce_bytes, plaintext, None)
    meta: SnapshotMeta = {
        "v": META_VERSION,
        "kdf": "argon2id",
        "m": ARGON2_MEMORY_KIB,
        "t": ARGON2_TIME_COST,
        "p": ARGON2_PARALLELISM,
        "salt_b64": _b64(salt_bytes),
        "nonce_b64": _b64(nonce_bytes),
    }
    return ciphertext, meta


def decrypt_snapshot(ciphertext: bytes, password: str, meta: SnapshotMeta | dict[str, Any]) -> bytes:
    if int(meta["v"]) != META_VERSION or meta.get("kdf") != "argon2id":
        raise ValueError("unsupported snapshot meta")
    salt = _unb64(str(meta["salt_b64"]))
    nonce = _unb64(str(meta["nonce_b64"]))
    key = derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ciphertext, None)
