from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.thumbs.storage import LocalFsThumbStorage, thumb_key
from drivecheck_crawler.thumbs.sync import ensure_listing_thumb


def _dto(image_url: str = "https://cdn.example/a.jpg") -> ListingDTO:
    return ListingDTO(
        source="sauto",
        external_id="42",
        url="https://www.sauto.cz/inzerat/42",
        price_czk=100_000,
        image_url=image_url,
        observed_at=datetime.now(timezone.utc),
    )


def test_skip_when_source_unchanged_and_file_exists(tmp_path) -> None:
    storage = LocalFsThumbStorage(tmp_path)
    dto = _dto()
    key = thumb_key(dto.source, dto.external_id)
    storage.put(key, b"already")

    repo = MagicMock()
    repo.get_thumb_meta.return_value = {
        "image_url": dto.image_url,
        "image_source_url": dto.image_url,
        "image_thumb_key": key,
        "image_thumb_sha256": "abc",
    }
    client = MagicMock()

    result = ensure_listing_thumb(repo, dto, client=client, storage=storage)
    assert result == key
    client.get_bytes.assert_not_called()
    repo.update_thumb_meta.assert_not_called()


def test_redownload_when_source_url_changes(tmp_path) -> None:
    from PIL import Image
    import io

    storage = LocalFsThumbStorage(tmp_path)
    dto = _dto("https://cdn.example/new.jpg")
    key = thumb_key(dto.source, dto.external_id)
    storage.put(key, b"stale")

    img = Image.new("RGB", (100, 80), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    repo = MagicMock()
    repo.get_thumb_meta.return_value = {
        "image_source_url": "https://cdn.example/old.jpg",
        "image_thumb_key": key,
        "image_thumb_sha256": "old",
    }
    client = MagicMock()
    client.get_bytes.return_value = buf.getvalue()

    result = ensure_listing_thumb(repo, dto, client=client, storage=storage)
    assert result == key
    client.get_bytes.assert_called_once()
    assert client.get_bytes.call_args.kwargs.get("referer") == "https://www.sauto.cz/"
    repo.update_thumb_meta.assert_called_once()
    assert storage.open(key)[:4] == b"RIFF"


def test_tipcars_download_uses_tipcars_referer(tmp_path) -> None:
    from PIL import Image
    import io

    storage = LocalFsThumbStorage(tmp_path)
    dto = ListingDTO(
        source="tipcars",
        external_id="12345678",
        url="https://www.tipcars.com/skoda/octavia/x-12345678.html",
        price_czk=389_000,
        image_url="https://g.tipcars.com/cover.jpg",
        observed_at=datetime.now(timezone.utc),
    )
    key = thumb_key(dto.source, dto.external_id)

    img = Image.new("RGB", (100, 80), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    repo = MagicMock()
    repo.get_thumb_meta.return_value = None
    client = MagicMock()
    client.get_bytes.return_value = buf.getvalue()

    result = ensure_listing_thumb(repo, dto, client=client, storage=storage)
    assert result == key
    client.get_bytes.assert_called_once_with(
        "https://g.tipcars.com/cover.jpg",
        referer="https://www.tipcars.com/",
    )


def test_missing_image_url_skips() -> None:
    repo = MagicMock()
    client = MagicMock()
    storage = MagicMock()
    dto = _dto("")
    dto.image_url = None
    assert ensure_listing_thumb(repo, dto, client=client, storage=storage) is None
    client.get_bytes.assert_not_called()
