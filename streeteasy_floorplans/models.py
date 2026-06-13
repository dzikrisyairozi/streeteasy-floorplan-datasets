"""Plain dataclasses shared across the pipeline. Pure stdlib, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass(frozen=True)
class Bucket:
    """A bedroom category. ``beds_max=None`` means open-ended (the 4+ bucket)."""

    name: str          # internal key, also the dataset subfolder, e.g. "studio", "1br", "4plus"
    label: str         # human label, e.g. "Studio", "1 Bedroom", "4+ Bedrooms"
    beds_min: int      # 0 for studio
    beds_max: Optional[int]

    def matches(self, beds: Optional[int]) -> bool:
        if beds is None:
            return False
        if beds < self.beds_min:
            return False
        if self.beds_max is not None and beds > self.beds_max:
            return False
        return True


@dataclass
class Shard:
    """One search query unit: an area, a bucket, and an optional price band.

    Sharding by area (and, if still over StreetEasy's ~100-page cap, by price band)
    is how we reach more than ~2,800 listings for a popular bucket. Results are
    de-duplicated by listing id across shards, so overlapping areas are harmless.
    """

    area_code: int
    area_name: str
    bucket: str
    price_min: Optional[int] = None
    price_max: Optional[int] = None

    def describe(self) -> str:
        band = ""
        if self.price_min is not None or self.price_max is not None:
            band = f" ${self.price_min or 0}-{self.price_max or '∞'}"
        return f"{self.area_name}/{self.bucket}{band}"


@dataclass
class ListingRecord:
    """One enumerated rental listing plus its floor-plan verdict."""

    id: str
    bucket: str
    bedroom_count: Optional[int] = None
    area_name: Optional[str] = None
    url: Optional[str] = None
    street: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[int] = None
    living_area_size: Optional[int] = None
    building_type: Optional[str] = None
    is_new_development: Optional[bool] = None
    has_floor_plan: bool = False
    floor_plan_keys: list[str] = field(default_factory=list)
    photo_keys: list[str] = field(default_factory=list)
    source: str = "graphql-search"   # graphql-search | graphql-detail | srp-html
    scraped_at: Optional[str] = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FloorPlanAsset:
    """A downloaded (or planned) floor-plan image."""

    listing_id: str
    bucket: str
    key: str
    url: str
    local_path: Optional[str] = None
    sha256: Optional[str] = None
    bytes: Optional[int] = None
    duplicate_of: Optional[str] = None   # listing_id whose identical image we already saved
