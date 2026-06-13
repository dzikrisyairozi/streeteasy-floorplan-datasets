"""Proxy session rotation, sharding logic, and summaries (no network)."""

import random

from streeteasy_floorplans import pipeline
from streeteasy_floorplans.constants import BOROUGHS, bucket_for_beds
from streeteasy_floorplans.models import Bucket, ListingRecord, Shard
from streeteasy_floorplans.proxy import ProxyManager


# --- proxy ------------------------------------------------------------------
def test_proxy_none() -> None:
    pm = ProxyManager(None)
    assert pm.enabled is False
    assert pm.session() is None


def test_proxy_static() -> None:
    pm = ProxyManager("http://u:p@host:7000")
    assert pm.rotating is False
    assert pm.session() == {"http": "http://u:p@host:7000", "https": "http://u:p@host:7000"}


def test_proxy_rotating_substitutes_fresh_session() -> None:
    pm = ProxyManager("http://user-session-{{rand}}:pass@gate:7000", rng=random.Random(1))
    assert pm.rotating is True
    s1 = pm.session()["http"]
    s2 = pm.session()["http"]
    assert "{{rand}}" not in s1 and "{{rand}}" not in s2
    assert s1 != s2  # different exit session each call


# --- buckets ----------------------------------------------------------------
def test_bucket_for_beds() -> None:
    assert bucket_for_beds(0).name == "studio"
    assert bucket_for_beds(1).name == "1br"
    assert bucket_for_beds(4).name == "4plus"
    assert bucket_for_beds(9).name == "4plus"
    assert bucket_for_beds(None) is None


def test_bucket_matches_open_ended() -> None:
    b = Bucket("4plus", "4+", 4, None)
    assert b.matches(4) and b.matches(50)
    assert not b.matches(3)


# --- sharding ---------------------------------------------------------------
def test_subdivide_borough_to_neighborhoods() -> None:
    brooklyn = Shard(area_code=300, area_name="BROOKLYN", bucket="1br")
    subs = pipeline._subdivide(brooklyn, log=lambda *_: None)
    assert subs and len(subs) > 10
    assert all(300 < s.area_code <= 399 for s in subs)
    assert all(s.price_min is None for s in subs)


def test_subdivide_neighborhood_to_price_bands() -> None:
    williamsburg = Shard(area_code=302, area_name="WILLIAMSBURG", bucket="1br")
    subs = pipeline._subdivide(williamsburg, log=lambda *_: None)
    assert subs and len(subs) == len(pipeline.PRICE_BANDS)
    assert any(s.price_max == 2000 for s in subs)


def test_subdivide_priceband_is_terminal() -> None:
    banded = Shard(302, "WILLIAMSBURG", "1br", price_min=2000, price_max=3000)
    assert pipeline._subdivide(banded, log=lambda *_: None) is None


# --- summary ----------------------------------------------------------------
def test_summarize_counts_and_rate() -> None:
    recs = [
        ListingRecord(id="1", bucket="studio", has_floor_plan=True),
        ListingRecord(id="2", bucket="studio", has_floor_plan=False),
        ListingRecord(id="3", bucket="1br", has_floor_plan=True),
    ]
    s = pipeline.summarize(recs)
    assert s["total_listings"] == 3
    assert s["with_floorplan"] == 2
    assert s["floorplan_rate"] == round(2 / 3, 4)
    assert s["per_bucket"]["studio"] == {"total": 2, "with_floorplan": 1}
