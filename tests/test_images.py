"""Image URL building + download/dedupe (no network — fetch is faked)."""

from pathlib import Path

from streeteasy_floorplans import images
from streeteasy_floorplans.models import FloorPlanAsset


def test_cdn_url_default_and_override() -> None:
    key = "a96ed3b771b74beee0c8395e175d4866"
    assert images.cdn_url(key) == f"https://photos.zillowstatic.com/fp/{key}-cc_ft_1536.webp"
    assert images.cdn_url(key, size="p_e", ext="jpg") == f"https://photos.zillowstatic.com/fp/{key}-p_e.jpg"


def test_key_from_url_is_size_agnostic() -> None:
    key = "a96ed3b771b74beee0c8395e175d4866"
    assert images.key_from_url(f"https://photos.zillowstatic.com/fp/{key}-p_e.webp") == key
    assert images.key_from_url(f"https://photos.zillowstatic.com/fp/{key}-cc_ft_1536.jpg") == key
    assert images.key_from_url("https://example.com/nope.png") is None


def test_download_and_dedupe(tmp_path: Path) -> None:
    calls = {}

    def fake_fetch(url: str) -> bytes:
        calls[url] = calls.get(url, 0) + 1
        # same bytes for both keys -> should dedupe
        return b"PLANIMAGE"

    seen: dict[str, str] = {}
    a1 = FloorPlanAsset("111", "studio", "k1", images.cdn_url("k1"))
    a2 = FloorPlanAsset("222", "studio", "k2", images.cdn_url("k2"))

    images.download_asset(a1, fake_fetch, tmp_path, seen_hashes=seen)
    images.download_asset(a2, fake_fetch, tmp_path, seen_hashes=seen)

    # first written, second recognized as duplicate
    assert a1.local_path is not None
    assert Path(a1.local_path).exists()
    assert a1.sha256 == a2.sha256
    assert a2.duplicate_of == "111"
    assert a2.local_path is None
    # only one file on disk
    files = list((tmp_path / "studio").glob("*"))
    assert len(files) == 1


def test_download_skips_existing(tmp_path: Path) -> None:
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b"NEW"

    (tmp_path / "studio").mkdir()
    (tmp_path / "studio" / "111.webp").write_bytes(b"already-here")
    a = FloorPlanAsset("111", "studio", "k1", images.cdn_url("k1"))

    images.download_asset(a, fetch, tmp_path)  # skip_existing defaults True

    assert calls == []                          # never fetched
    assert a.local_path.endswith("111.webp")
    assert a.bytes == len(b"already-here")
