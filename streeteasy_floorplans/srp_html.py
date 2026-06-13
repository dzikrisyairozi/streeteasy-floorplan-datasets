"""Parse StreetEasy's rental search-results-page (SRP) HTML.

This is a *fallback* enumerator. The primary path is the GraphQL API
(:mod:`streeteasy_floorplans.graphql`), which also returns floor-plan presence.
The SRP HTML does NOT contain any floor-plan signal, but it is reachable without
the api-v6 403 wall and is handy for cheaply harvesting listing ids + bedroom
counts (floor plans then come from per-listing detail calls).

The page embeds two usable sources:
* one ``<script type="application/ld+json">`` block with ~14 ``Apartment`` items;
* an inline React Server Components stream (``self.__next_f.push([1, "..."])``)
  whose ``listingData`` carries every listing edge with the numeric listing id.

Pure stdlib. Verified against ``tests/fixtures/srp_beds_le1_page1.html``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .models import ListingRecord

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)', re.S)
_LD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_LISTING_ANCHOR = re.compile(r'\{"id":"\d+","areaName"')


def flight_stream(html: str) -> str:
    """Concatenate and JSON-decode all __next_f chunks into the raw RSC stream."""
    parts = []
    for m in _PUSH_RE.finditer(html):
        try:
            parts.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_balanced(s: str, start: int) -> Optional[str]:
    """Return the JSON object substring beginning at ``s[start] == '{'``."""
    if start >= len(s) or s[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def parse_search_meta(stream: str) -> dict[str, Any]:
    def _int(pat: str) -> Optional[int]:
        m = re.search(pat, stream)
        return int(m.group(1)) if m else None

    crit = re.search(r'"criteria":"([^"]+)"', stream)
    return {
        "criteria": crit.group(1) if crit else None,
        "total_count": _int(r'"totalCount":(\d+)'),
        "total_pages": _int(r'"totalPages":(\d+)'),
        "current_page": _int(r'"currentPage":(\d+)'),
    }


def parse_listings(stream: str, bucket: str, *, scraped_at: Optional[str] = None) -> list[ListingRecord]:
    """Extract listing edges from the RSC stream by id-anchored balanced parsing."""
    out: list[ListingRecord] = []
    seen: set[str] = set()
    for m in _LISTING_ANCHOR.finditer(stream):
        blob = _extract_balanced(stream, m.start())
        if not blob:
            continue
        try:
            node = json.loads(blob)
        except json.JSONDecodeError:
            continue
        lid = node.get("id")
        if lid is None or str(lid) in seen:
            continue
        seen.add(str(lid))
        slug = node.get("slug")
        url = f"https://streeteasy.com/rental/{lid}"
        if isinstance(slug, str) and slug:
            url = f"https://streeteasy.com/building/{slug}" if "/" in slug else url
        out.append(
            ListingRecord(
                id=str(lid),
                bucket=bucket,
                bedroom_count=node.get("bedroomCount"),
                area_name=node.get("areaName"),
                url=url,
                price=node.get("price"),
                living_area_size=node.get("livingAreaSize"),
                building_type=node.get("buildingType"),
                is_new_development=node.get("isNewDevelopment"),
                has_floor_plan=False,   # not knowable from SRP — needs a detail call
                source="srp-html",
                scraped_at=scraped_at,
            )
        )
    return out


def parse_jsonld_apartments(html: str) -> list[dict[str, Any]]:
    """Return the JSON-LD ``Apartment`` objects (secondary, SEO-oriented source)."""
    m = _LD_RE.search(html)
    if not m:
        return []
    try:
        graph = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    items = graph.get("@graph", []) if isinstance(graph, dict) else []
    return [x for x in items if isinstance(x, dict) and x.get("@type") == "Apartment"]


def parse_srp_html(
    html: str, bucket: str, *, scraped_at: Optional[str] = None
) -> tuple[list[ListingRecord], dict[str, Any]]:
    stream = flight_stream(html)
    meta = parse_search_meta(stream)
    records = parse_listings(stream, bucket, scraped_at=scraped_at)
    meta["jsonld_count"] = len(parse_jsonld_apartments(html))
    return records, meta
