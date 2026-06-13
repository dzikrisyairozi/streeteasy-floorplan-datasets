"""Orchestration: enumerate -> (optional detail enrich) -> index -> download.

Key problem this solves: StreetEasy caps any single search at ~100 pages, so a
popular bucket (e.g. NYC-wide 1BR) cannot be fully reached from one query. We
shard adaptively — start per borough, and when a shard is still capped, subdivide
it (borough -> neighborhoods -> price bands). Listings are de-duplicated by id
across shards, so overlapping shards are harmless.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from . import constants, images
from .config import Settings
from .constants import AREA_NAMES, BOROUGHS, neighborhoods_for_borough
from .graphql import GraphQLClient
from .models import ListingRecord, Shard

Logger = Callable[[str], None]

# Price bands (USD/month) used when a neighborhood-level shard is still capped.
PRICE_BANDS: list[tuple[Optional[int], Optional[int]]] = [
    (None, 2000), (2000, 3000), (3000, 4000), (4000, 5000),
    (5000, 7000), (7000, 10000), (10000, None),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str:
    return uuid.uuid4().hex


# --- enumeration ------------------------------------------------------------
def _enumerate_shard(
    gclient: GraphQLClient, settings: Settings, shard: Shard, log: Logger, scraped_at: str
) -> tuple[list[ListingRecord], int, bool]:
    """Enumerate one shard. Returns (records, total_count, capped)."""
    token = _token()
    first, total = gclient.search_page(shard, 1, user_search_token=token, scraped_at=scraped_at)
    pages_needed = math.ceil(total / settings.per_page) if total else 1
    capped = pages_needed > settings.page_cap

    if capped:
        log(f"  · {shard.describe()}: {total} listings > cap — subdividing")
        return first, total, True

    records = list(first)
    for page in range(2, pages_needed + 1):
        more, _ = gclient.search_page(shard, page, user_search_token=token, scraped_at=scraped_at)
        if not more:
            break
        records.extend(more)
    log(f"  · {shard.describe()}: {total} listings, {len(records)} collected")
    return records, total, False


def _subdivide(shard: Shard, log: Logger) -> Optional[list[Shard]]:
    has_band = shard.price_min is not None or shard.price_max is not None
    if has_band:
        return None  # already finest grain — accept truncation
    if shard.area_code in BOROUGHS:
        subs = [
            Shard(area_code=code, area_name=AREA_NAMES.get(code, str(code)), bucket=shard.bucket)
            for code in neighborhoods_for_borough(shard.area_code)
        ]
        return subs or None
    # neighborhood, no band yet -> split by price
    return [
        Shard(shard.area_code, shard.area_name, shard.bucket, price_min=lo, price_max=hi)
        for (lo, hi) in PRICE_BANDS
    ]


def enumerate_listings(
    gclient: GraphQLClient,
    settings: Settings,
    *,
    buckets: Iterable[str],
    areas: Optional[list[int]] = None,
    log: Logger = print,
) -> list[ListingRecord]:
    """Enumerate all listings for the given buckets, de-duped by listing id."""
    area_codes = areas if areas is not None else list(BOROUGHS.keys())
    scraped_at = _now()
    by_id: dict[str, ListingRecord] = {}

    for bucket in buckets:
        log(f"[enumerate] bucket={bucket}")
        queue: list[Shard] = [
            Shard(area_code=a, area_name=AREA_NAMES.get(a, str(a)), bucket=bucket) for a in area_codes
        ]
        while queue:
            shard = queue.pop(0)
            recs, _total, capped = _enumerate_shard(gclient, settings, shard, log, scraped_at)
            for r in recs:
                # prefer the record that found a floor plan
                prev = by_id.get(r.id)
                if prev is None or (r.has_floor_plan and not prev.has_floor_plan):
                    by_id[r.id] = r
            if capped:
                subs = _subdivide(shard, log)
                if subs:
                    queue.extend(subs)
                else:
                    log(f"  ! {shard.describe()}: still capped at finest grain — some listings unreached")
    return list(by_id.values())


# --- detail enrichment ------------------------------------------------------
def enrich_with_details(
    gclient: GraphQLClient,
    records: list[ListingRecord],
    *,
    mode: str = "hits",
    log: Logger = print,
) -> None:
    """Fetch ``rentalByListingId`` to get the authoritative ``media.floorPlans[]``.

    mode="hits": only listings already flagged (gets multi-image plans).
    mode="all":  every listing (authoritative presence; catches plans the search
                 ``leadMedia.floorPlan`` missed). Slower — one call per listing.
    """
    targets = records if mode == "all" else [r for r in records if r.has_floor_plan]
    log(f"[details] enriching {len(targets)} listings (mode={mode})")
    for i, r in enumerate(targets, 1):
        try:
            d = gclient.listing_details(r.id)
        except Exception as exc:  # keep going on a single failure
            log(f"  ! details {r.id} failed: {exc}")
            continue
        if d.get("floor_plan_keys"):
            r.floor_plan_keys = d["floor_plan_keys"]
            r.has_floor_plan = True
        elif mode == "all":
            r.has_floor_plan = bool(d.get("has_floor_plan"))
        if d.get("bedroom_count") is not None and r.bedroom_count is None:
            r.bedroom_count = d["bedroom_count"]
        r.source = "graphql-detail"
        if i % 25 == 0:
            log(f"  · {i}/{len(targets)}")


# --- dataset writers --------------------------------------------------------
def write_index(records: list[ListingRecord], out_dir: Path, log: Logger = print) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.jsonl"
    no_fp_path = out_dir / "_no_floorplan.jsonl"

    import json

    with index_path.open("w", encoding="utf-8") as idx, no_fp_path.open("w", encoding="utf-8") as nofp:
        for r in records:
            line = json.dumps(r.to_json(), ensure_ascii=False)
            idx.write(line + "\n")
            if not r.has_floor_plan:
                nofp.write(line + "\n")

    stats = summarize(records)
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    log(f"[index] wrote {len(records)} -> {index_path}")
    return stats


_RECORD_FIELDS = {
    "id", "bucket", "bedroom_count", "area_name", "url", "street", "unit", "price",
    "living_area_size", "building_type", "is_new_development", "has_floor_plan",
    "floor_plan_keys", "photo_keys", "source", "scraped_at",
}


def record_from_dict(d: dict[str, Any]) -> ListingRecord:
    """Build a ListingRecord from a harvest.json / index.jsonl row (tolerant)."""
    return ListingRecord(**{k: v for k, v in d.items() if k in _RECORD_FIELDS and k != "id"}, id=str(d["id"]))


def ingest_harvest(
    path: Path, out_dir: Path, log: Logger = print, *, merge: bool = False
) -> list[ListingRecord]:
    """Load a browser-harvested JSON file into ListingRecords + write the index.

    Accepts either ``{"listings": [...]}`` (the userscript output) or a bare list.
    The harvest comes from your real browser, so no proxy is involved here.

    With ``merge=True``, listings already in ``out_dir/index.jsonl`` are loaded
    first and combined (deduped by id) — so harvesting buckets incrementally adds
    to the dataset instead of replacing it.
    """
    import json

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("listings") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list of listings or {{'listings': [...]}}")

    by_id: dict[str, ListingRecord] = {}
    if merge:
        existing = Path(out_dir) / "index.jsonl"
        if existing.exists():
            for line in existing.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    r = record_from_dict(json.loads(line))
                except (KeyError, TypeError, json.JSONDecodeError):
                    continue
                by_id[r.id] = r
            log(f"[ingest] merging with {len(by_id)} existing records in {existing}")

    for d in rows:
        try:
            r = record_from_dict(d)
        except (KeyError, TypeError) as exc:
            log(f"  ! skipping malformed row: {exc}")
            continue
        prev = by_id.get(r.id)
        if prev is None or (r.has_floor_plan and not prev.has_floor_plan):
            by_id[r.id] = r

    records = list(by_id.values())
    log(f"[ingest] loaded {len(records)} unique listings from {path}")
    write_index(records, out_dir, log=log)
    return records


def summarize(records: list[ListingRecord]) -> dict[str, Any]:
    per_bucket: dict[str, dict[str, int]] = {}
    for r in records:
        b = per_bucket.setdefault(r.bucket, {"total": 0, "with_floorplan": 0})
        b["total"] += 1
        if r.has_floor_plan:
            b["with_floorplan"] += 1
    total = len(records)
    with_fp = sum(1 for r in records if r.has_floor_plan)
    return {
        "total_listings": total,
        "with_floorplan": with_fp,
        "floorplan_rate": round(with_fp / total, 4) if total else 0.0,
        "per_bucket": per_bucket,
    }


# --- image download ---------------------------------------------------------
def download_floorplans(
    client: Any, records: list[ListingRecord], settings: Settings, log: Logger = print
) -> dict[str, Any]:
    import json

    out_dir = settings.out_dir
    seen_hashes: dict[str, str] = {}
    manifest_path = out_dir / "floorplans.jsonl"
    downloaded = dupes = failed = 0

    targets = [r for r in records if r.has_floor_plan and r.floor_plan_keys]
    log(f"[download] {sum(len(r.floor_plan_keys) for r in targets)} floor-plan images from {len(targets)} listings")

    with manifest_path.open("w", encoding="utf-8") as mf:
        for r in targets:
            assets = images.plan_assets(r.id, r.bucket, r.floor_plan_keys, size=settings.image_size, ext=settings.image_ext)
            for i, asset in enumerate(assets):
                try:
                    images.download_asset(
                        asset, lambda u: client.get_bytes(u), out_dir,
                        seen_hashes=seen_hashes, index=i, ext=settings.image_ext,
                    )
                except Exception as exc:
                    failed += 1
                    log(f"  ! {r.id} key={asset.key[:10]}… failed: {exc}")
                    continue
                if asset.duplicate_of:
                    dupes += 1
                else:
                    downloaded += 1
                mf.write(json.dumps(asset.__dict__, ensure_ascii=False) + "\n")

    result = {"downloaded": downloaded, "duplicates": dupes, "failed": failed}
    log(f"[download] done: {result}")
    return result


# --- top-level run ----------------------------------------------------------
def run(
    settings: Settings,
    *,
    buckets: list[str],
    areas: Optional[list[int]] = None,
    detail_mode: str = "none",
    do_download: bool = True,
    log: Logger = print,
) -> dict[str, Any]:
    from .http_client import HttpClient  # lazy: needs curl_cffi

    client = HttpClient(settings)
    gclient = GraphQLClient(client, per_page=settings.per_page)

    records = enumerate_listings(gclient, settings, buckets=buckets, areas=areas, log=log)
    if detail_mode in ("hits", "all"):
        enrich_with_details(gclient, records, mode=detail_mode, log=log)

    stats = write_index(records, settings.out_dir, log=log)
    if do_download:
        stats["download"] = download_floorplans(client, records, settings, log=log)
    return stats
