from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ThumbStorage(Protocol):
    def exists(self, key: str) -> bool: ...

    def put(self, key: str, data: bytes) -> None: ...

    def open(self, key: str) -> bytes: ...

    def path_for(self, key: str) -> Path: ...


class LocalFsThumbStorage:
    """Local filesystem backend; swap for S3 later using the same keys."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        # Prevent path traversal; keys are always "source/id.webp".
        clean = key.replace("\\", "/").lstrip("/")
        parts = clean.split("/")
        if ".." in parts or len(parts) != 2:
            raise ValueError(f"invalid thumb key: {key}")
        return self.root.joinpath(*parts)

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def put(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def open(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()


def thumb_key(source: str, external_id: str) -> str:
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in external_id)
    return f"{source}/{safe_id}.webp"
