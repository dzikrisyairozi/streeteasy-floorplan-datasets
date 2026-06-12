"""StreetEasy GraphQL queries, request builders, and response parsers.

Pure module: builds query strings and parses already-fetched JSON. The live
transport (curl_cffi) lives in :mod:`streeteasy_floorplans.http_client`; this
module only needs an object exposing ``graphql(query, variables) -> data``.

Query text and field paths are transcribed from the MIT reference clients
(evandcoleman/streeteasy-api, eneakllomollari/streeteasy-cli). Two gotchas baked
in here:

* ``searchRentals`` rejects enum values passed as JSON-string variables
  (``VALIDATION_INVALID_TYPE_VARIABLE``) — so the search input is INLINED into
  the query text with enums as bare tokens and NO GraphQL variables.
* The single-listing query uses a normal ``$listingID: ID!`` variable.

Floor-plan field paths:
* search  -> ``searchRentals.edges[].node.leadMedia.floorPlan.key`` (nullable)
* detail  -> ``rentalByListingId.media.floorPlans[].key`` (full list)
"""

from __future__ import annotations

from typing import Any, Optional

from .constants import BUCKETS_BY_NAME
from .models import ListingRecord, Shard

# Edge types we keep. Sponsored edges are paid placements that may fall outside
# the search filters, so they are excluded to keep buckets/areas clean.
_KEEP_EDGE_TYPES = {"OrganicRentalEdge", "FeaturedRentalEdge"}

# --- Search query (input inlined, no variables) -----------------------------
_SEARCH_FRAGMENTS = """
fragment LeadMediaForSRP on LeadMedia {
  __typename
  photo { __typename key }
  floorPlan { __typename key }
}
fragment RentalListingDigestForSearchResults on SearchRentalListing {
  __typename id areaName availableAt bedroomCount buildingType fullBathroomCount furnished
  halfBathroomCount hasTour3d hasVideos isNewDevelopment
  leadMedia { __typename ...LeadMediaForSRP }
  leaseTermMonths livingAreaSize mediaAssetCount monthsFree noFee netEffectivePrice offMarketAt
  photos { __typename key }
  price priceChangedAt priceDelta slug sourceGroupLabel sourceType status street unit urlPath
}
"""


def _range_literal(name: str, lo: Optional[int], hi: Optional[int]) -> Optional[str]:
    if lo is None and hi is None:
        return None
    parts = []
    if lo is not None:
        parts.append(f"lowerBound: {int(lo)}")
    if hi is not None:
        parts.append(f"upperBound: {int(hi)}")
    return f"{name}: {{ {', '.join(parts)} }}"


def build_search_query(
    *,
    area_codes: list[int],
    bucket: str,
    page: int,
    per_page: int,
    user_search_token: str,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
) -> str:
    """Render a complete ``SearchRentalsFederated`` query with the input inlined."""
    b = BUCKETS_BY_NAME[bucket]
    areas = ", ".join(str(int(c)) for c in area_codes)

    filters = [
        f"areas: [{areas}]",
        "rentalStatus: ACTIVE",
        _range_literal("bedrooms", b.beds_min, b.beds_max),
        _range_literal("price", price_min, price_max),
    ]
    filters_str = ", ".join(f for f in filters if f)

    token = user_search_token.replace('"', "")
    input_literal = (
        "{ "
        "sorting: { attribute: RECOMMENDED, direction: DESCENDING }, "
        f"filters: {{ {filters_str} }}, "
        "adStrategy: NONE, "
        f'userSearchToken: "{token}", '
        f"perPage: {int(per_page)}, page: {int(page)} "
        "}"
    )

    return (
        "query SearchRentalsFederated {\n"
        f"  searchRentals(input: {input_literal}) {{\n"
        "    __typename\n"
        "    edges {\n"
        "      __typename\n"
        "      ... on OrganicRentalEdge { node { __typename ...RentalListingDigestForSearchResults } }\n"
        "      ... on FeaturedRentalEdge { node { __typename ...RentalListingDigestForSearchResults } }\n"
        "      ... on SponsoredRentalEdge { node { __typename ...RentalListingDigestForSearchResults } }\n"
        "    }\n"
        "    totalCount\n"
        "  }\n"
        "}\n"
        + _SEARCH_FRAGMENTS
    )


# --- Single-listing detail query (uses $listingID variable) -----------------
DETAIL_QUERY = """
query RentalListingDetailsFederated($listingID: ID!) {
  rentalByListingId(id: $listingID) {
    __typename
    id
    status
    availableAt
    offMarketAt
    buildingId
    description
    media { __typename ...MediaInfo }
    propertyDetails { __typename ...PropertyInfo }
    pricing { __typename price noFee leaseTermMonths }
  }
}
fragment MediaInfo on Media {
  __typename
  photos { __typename key }
  floorPlans { __typename key }
  videos { __typename imageUrl id provider }
  tour3dUrl
  assetCount
}
fragment PropertyInfo on PropertyDetails {
  __typename
  address { __typename street houseNumber streetName city state zipCode unit }
  roomCount bedroomCount fullBathroomCount halfBathroomCount livingAreaSize
}
"""


def build_detail_request(listing_id: str | int) -> tuple[str, dict[str, Any]]:
    return DETAIL_QUERY, {"listingID": str(listing_id)}


# --- Response parsers -------------------------------------------------------
def _key_of(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        k = obj.get("key")
        if isinstance(k, str) and k:
            return k
    return None


def _listing_url(node: dict[str, Any]) -> str:
    path = node.get("urlPath")
    if isinstance(path, str) and path:
        if path.startswith("http"):
            return path
        return "https://streeteasy.com" + (path if path.startswith("/") else "/" + path)
    return f"https://streeteasy.com/rental/{node.get('id')}"


def parse_search_response(
    data: dict[str, Any], bucket: str, *, scraped_at: Optional[str] = None
) -> tuple[list[ListingRecord], int]:
    """Return (records, total_count) from a ``searchRentals`` response.

    Floor-plan presence comes straight from ``node.leadMedia.floorPlan.key``.
    """
    sr = (data or {}).get("searchRentals") or {}
    total = int(sr.get("totalCount") or 0)
    records: list[ListingRecord] = []

    for edge in sr.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if edge.get("__typename") not in _KEEP_EDGE_TYPES:
            continue
        node = edge.get("node") or {}
        lid = node.get("id")
        if lid is None:
            continue

        lead = node.get("leadMedia") or {}
        fp_key = _key_of(lead.get("floorPlan")) if isinstance(lead, dict) else None
        photo_keys = [k for k in (_key_of(p) for p in (node.get("photos") or [])) if k]

        records.append(
            ListingRecord(
                id=str(lid),
                bucket=bucket,
                bedroom_count=node.get("bedroomCount"),
                area_name=node.get("areaName"),
                url=_listing_url(node),
                street=node.get("street"),
                unit=node.get("unit"),
                price=node.get("price"),
                living_area_size=node.get("livingAreaSize"),
                building_type=node.get("buildingType"),
                is_new_development=node.get("isNewDevelopment"),
                has_floor_plan=bool(fp_key),
                floor_plan_keys=[fp_key] if fp_key else [],
                photo_keys=photo_keys,
                source="graphql-search",
                scraped_at=scraped_at,
            )
        )
    return records, total


def parse_detail_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract floor-plan + media info from a ``rentalByListingId`` response."""
    rental = (data or {}).get("rentalByListingId") or {}
    media = rental.get("media") or {}
    fp_keys = [k for k in (_key_of(f) for f in (media.get("floorPlans") or [])) if k]
    photo_keys = [k for k in (_key_of(p) for p in (media.get("photos") or [])) if k]
    pd = rental.get("propertyDetails") or {}
    return {
        "id": str(rental.get("id")) if rental.get("id") is not None else None,
        "status": rental.get("status"),
        "has_floor_plan": bool(fp_keys),
        "floor_plan_keys": fp_keys,
        "photo_keys": photo_keys,
        "asset_count": media.get("assetCount"),
        "bedroom_count": pd.get("bedroomCount"),
        "living_area_size": pd.get("livingAreaSize"),
    }


class GraphQLClient:
    """Thin orchestration over a transport with ``graphql(query, variables)``."""

    def __init__(self, transport: Any, *, per_page: int = 50) -> None:
        self.transport = transport
        self.per_page = per_page

    def search_page(
        self, shard: Shard, page: int, *, user_search_token: str, scraped_at: Optional[str] = None
    ) -> tuple[list[ListingRecord], int]:
        query = build_search_query(
            area_codes=[shard.area_code],
            bucket=shard.bucket,
            page=page,
            per_page=self.per_page,
            user_search_token=user_search_token,
            price_min=shard.price_min,
            price_max=shard.price_max,
        )
        data = self.transport.graphql(query, None)
        return parse_search_response(data, shard.bucket, scraped_at=scraped_at)

    def listing_details(self, listing_id: str | int) -> dict[str, Any]:
        query, variables = build_detail_request(listing_id)
        data = self.transport.graphql(query, variables)
        return parse_detail_response(data)
