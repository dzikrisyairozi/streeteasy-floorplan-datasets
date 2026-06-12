"""Ingest a browser-harvested harvest.json into the dataset index (no network)."""

import json
from pathlib import Path

from streeteasy_floorplans import pipeline


def _harvest(tmp_path: Path) -> Path:
    payload = {
        "generated_at": "2026-06-13T00:00:00Z",
        "buckets": ["studio", "1br"],
        "listings": [
            {"id": "111", "bucket": "studio", "bedroom_count": 0, "has_floor_plan": True,
             "floor_plan_keys": ["fpA"], "area_name": "Chelsea", "source": "harvest-graphql"},
            {"id": "222", "bucket": "1br", "bedroom_count": 1, "has_floor_plan": False,
             "floor_plan_keys": []},
            # duplicate id: floor-plan-bearing copy should win
            {"id": "222", "bucket": "1br", "bedroom_count": 1, "has_floor_plan": True,
             "floor_plan_keys": ["fpB"]},
        ],
    }
    p = tmp_path / "harvest.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_ingest_writes_index_and_dedupes(tmp_path: Path) -> None:
    out = tmp_path / "dataset"
    records = pipeline.ingest_harvest(_harvest(tmp_path), out, log=lambda *_: None)

    assert len(records) == 2  # 111 + de-duped 222
    by_id = {r.id: r for r in records}
    assert by_id["222"].has_floor_plan is True      # floor-plan copy won
    assert by_id["222"].floor_plan_keys == ["fpB"]

    # index + no-floorplan + stats written
    index_lines = (out / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(index_lines) == 2
    assert (out / "_no_floorplan.jsonl").exists()
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["total_listings"] == 2
    assert stats["with_floorplan"] == 2


def test_ingest_accepts_bare_list(tmp_path: Path) -> None:
    p = tmp_path / "bare.json"
    p.write_text(json.dumps([{"id": "9", "bucket": "studio", "has_floor_plan": False}]), encoding="utf-8")
    records = pipeline.ingest_harvest(p, tmp_path / "ds", log=lambda *_: None)
    assert [r.id for r in records] == ["9"]
