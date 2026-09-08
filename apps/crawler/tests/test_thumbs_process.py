from __future__ import annotations

import io

from PIL import Image

from drivecheck_crawler.thumbs.process import image_to_webp_thumb
from drivecheck_crawler.thumbs.storage import LocalFsThumbStorage, thumb_key


def _png_bytes(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(40, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_to_webp_thumb_resizes_and_hashes() -> None:
    data, digest = image_to_webp_thumb(_png_bytes(900, 500), max_width=480, quality=80)
    assert data[:4] == b"RIFF"
    assert digest
    assert len(digest) == 64
    with Image.open(io.BytesIO(data)) as out:
        assert out.format == "WEBP"
        assert out.width == 480
        assert out.height == 266


def test_local_fs_storage_roundtrip(tmp_path) -> None:
    storage = LocalFsThumbStorage(tmp_path)
    key = thumb_key("sauto", "abc/123")
    assert key == "sauto/abc_123.webp"
    payload = b"webp-bytes"
    storage.put(key, payload)
    assert storage.exists(key)
    assert storage.open(key) == payload


def test_thumb_key_rejects_traversal(tmp_path) -> None:
    storage = LocalFsThumbStorage(tmp_path)
    try:
        storage.path_for("../evil.webp")
        assert False, "expected ValueError"
    except ValueError:
        pass
