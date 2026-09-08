from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageOps


def image_to_webp_thumb(
    raw: bytes,
    *,
    max_width: int = 480,
    quality: int = 80,
) -> tuple[bytes, str]:
    """Resize cover to max_width and encode WebP. Returns (bytes, sha256 hex)."""
    with Image.open(io.BytesIO(raw)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background

        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_size = (max_width, max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="WEBP", quality=quality, method=4)
        data = out.getvalue()

    digest = hashlib.sha256(data).hexdigest()
    return data, digest
