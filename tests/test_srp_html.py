"""Validate the SRP HTML parser against a real saved StreetEasy page."""

from pathlib import Path

import pytest

from streeteasy_floorplans import srp_html

FIXTURE = Path(__file__).parent / "fixtures" / "srp_beds_le1_page1.html"


@pytest.fixture(scope="module")
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_search_meta(html: str) -> None:
    records, meta = srp_html.parse_srp_html(html, "studio")
    # captured live: beds<=1, NYC-wide
    assert meta["total_count"] == 9227
    assert meta["total_pages"] == 100          # the page cap we shard around
    assert meta["criteria"] == "area:1|beds:0-1|status:open"
    assert meta["jsonld_count"] == 14


def test_listings_extracted(html: str) -> None:
    records, _ = srp_html.parse_srp_html(html, "studio")
    # 14 unique organic listings on the page (each appears twice in the RSC
    # stream; the parser de-dupes by id — matches the 14 JSON-LD apartments).
    assert len(records) == 14
    ids = {r.id for r in records}
    assert all(i.isdigit() for i in ids)
    assert "5063351" in ids                    # a known id from the capture

    by_id = {r.id: r for r in records}
    sample = by_id["5063351"]
    assert sample.bedroom_count == 1
    assert sample.area_name == "South Harlem"
    assert sample.price == 3222
    assert sample.source == "srp-html"
    # SRP cannot reveal floor plans
    assert sample.has_floor_plan is False


def test_flight_stream_decodes(html: str) -> None:
    stream = srp_html.flight_stream(html)
    assert '"totalCount":9227' in stream
    assert '"bedroomCount":' in stream
