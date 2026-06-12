"""Floor-plan image URLs and downloading.

A StreetEasy media ``key`` (32-hex hash) renders on Zillow's CDN as
``https://photos.zillowstatic.com/fp/{key}-{size}.{ext}``. The same hash serves
every size; only the tail changes. The CDN is NOT behind PerimeterX, so images
download with a plain HTTP client and need no proxy.

URL building is pure/stdlib; downloading takes a ``fetch(url) -> bytes`` callable
so it can be driven by the curl_cffi client (or anything else) and unit-tested.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Callable, Optional

from . import constants
from .models import FloorPlanAsset

_KEY_RE = re.compile(r"/fp/([a-f0-9]{16,})", re.I)


def cdn_url(key: str, *, size: Optional[str] = None, ext: Optional[str] = None) -> str:
    return constants.PHOTO_CDN_TEMPLATE.format(
        key=key,
        size=size or constants.DEFAULT_IMAGE_SIZE,
        ext=ext or constants.DEFAULT_IMAGE_EXT,
    )


def key_from_url(url: str) -> Optional[str]:
    """Recover the bare media key from any zillowstatic /fp/ URL (size-agnostic)."""
    m = _KEY_RE.search(url or "")
    return m.group(1) if m else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_assets(
    listing_id: str, bucket: str, keys: list[str], *, size: Optional[str] = None, ext: Optional[str] = None
) -> list[FloorPlanAsset]:
    """Build (un-downloaded) FloorPlanAsset rows for a listing's floor-plan keys."""
    assets = []
    for key in keys:
        assets.append(
            FloorPlanAsset(listing_id=listing_id, bucket=bucket, key=key, url=cdn_url(key, size=size, ext=ext))
        )
    return assets


def download_asset(
    asset: FloorPlanAsset,
    fetch: Callable[[str], bytes],
    out_dir: Path,
    *,
    seen_hashes: Optional[dict[str, str]] = None,
    index: int = 0,
    ext: Optional[str] = None,
) -> FloorPlanAsset:
    """Download one floor-plan image into ``out_dir/<bucket>/`` and dedupe by content.

    ``seen_hashes`` maps sha256 -> first listing_id that produced it; identical
    images (the same plan reused across units in a building) are recorded as
    duplicates and not written twice.
    """
    data = fetch(asset.url)
    digest = sha256_bytes(data)
    asset.sha256 = digest
    asset.bytes = len(data)

    if seen_hashes is not None and digest in seen_hashes:
        asset.duplicate_of = seen_hashes[digest]
        return asset

    bucket_dir = out_dir / asset.bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)
    suffix = ext or constants.DEFAULT_IMAGE_EXT
    name = f"{asset.listing_id}__{index}.{suffix}" if index else f"{asset.listing_id}.{suffix}"
    path = bucket_dir / name
    path.write_bytes(data)
    asset.local_path = str(path)
    if seen_hashes is not None:
        seen_hashes[digest] = asset.listing_id
    return asset
