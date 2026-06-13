"""Command-line interface.

Commands:
  run         full pipeline: enumerate -> (details) -> index -> download images
  enumerate   enumerate listings + write index (no image download)
  download    download floor-plan images from an existing index.jsonl
  details     fetch + print one listing's floor-plan info (debug)
  parse-srp   offline: parse a saved SRP HTML file (no network)
  areas       list borough / neighborhood area codes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import constants
from .config import Settings
from .constants import AREAS, BOROUGHS, BUCKETS, BUCKETS_BY_NAME


def _parse_buckets(raw: Optional[str]) -> list[str]:
    if not raw:
        return [b.name for b in BUCKETS]
    names = [x.strip() for x in raw.split(",") if x.strip()]
    bad = [n for n in names if n not in BUCKETS_BY_NAME]
    if bad:
        raise SystemExit(f"unknown bucket(s): {bad}. valid: {list(BUCKETS_BY_NAME)}")
    return names


def _parse_areas(raw: Optional[str]) -> Optional[list[int]]:
    if not raw:
        return None
    out: list[int] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit():
            out.append(int(tok))
        else:
            key = tok.upper().replace("-", "_")
            if key not in AREAS:
                raise SystemExit(f"unknown area: {tok}. try `streeteasy-floorplans areas`.")
            out.append(AREAS[key])
    return out or None


def _settings_from_args(args: argparse.Namespace) -> Settings:
    s = Settings()
    if getattr(args, "out", None):
        s.out_dir = Path(args.out)
    if getattr(args, "no_proxy", False):
        s.proxy_enabled = False
    if getattr(args, "proxy_url", None):
        s.proxy_url = args.proxy_url
        s.proxy_enabled = True
    if getattr(args, "impersonate", None):
        s.impersonate = args.impersonate
    if getattr(args, "per_page", None):
        s.per_page = args.per_page
    if getattr(args, "image_size", None):
        s.image_size = args.image_size
    return s


# --- commands ---------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    from . import pipeline

    s = _settings_from_args(args)
    if not s.proxy_enabled and not args.allow_no_proxy:
        s.require_proxy()
    stats = pipeline.run(
        s,
        buckets=_parse_buckets(args.buckets),
        areas=_parse_areas(args.areas),
        detail_mode=args.details,
        do_download=not args.no_download,
    )
    print(json.dumps(stats, indent=2))
    return 0


def cmd_enumerate(args: argparse.Namespace) -> int:
    from . import pipeline
    from .graphql import GraphQLClient
    from .http_client import HttpClient

    s = _settings_from_args(args)
    if not s.proxy_enabled and not args.allow_no_proxy:
        s.require_proxy()
    client = HttpClient(s)
    gclient = GraphQLClient(client, per_page=s.per_page)
    records = pipeline.enumerate_listings(
        gclient, s, buckets=_parse_buckets(args.buckets), areas=_parse_areas(args.areas)
    )
    if args.details in ("hits", "all"):
        pipeline.enrich_with_details(gclient, records, mode=args.details)
    stats = pipeline.write_index(records, s.out_dir)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    from . import pipeline
    from .http_client import HttpClient

    s = _settings_from_args(args)
    index_path = s.out_dir / "index.jsonl"
    if not index_path.exists():
        raise SystemExit(f"no index at {index_path}. run `enumerate` or `ingest` first.")
    records = [
        pipeline.record_from_dict(json.loads(line))
        for line in index_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # The image CDN isn't bot-walled, so downloading needs no proxy.
    client = HttpClient(s)
    result = pipeline.download_floorplans(client, records, s)
    print(json.dumps(result, indent=2))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from . import pipeline

    s = _settings_from_args(args)
    records = pipeline.ingest_harvest(Path(args.file), s.out_dir, merge=args.merge)
    stats = pipeline.summarize(records)
    if args.download:
        from .http_client import HttpClient  # CDN download — no proxy needed
        stats["download"] = pipeline.download_floorplans(HttpClient(s), records, s)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_details(args: argparse.Namespace) -> int:
    from . import images
    from .graphql import GraphQLClient
    from .http_client import HttpClient

    s = _settings_from_args(args)
    if not s.proxy_enabled and not args.allow_no_proxy:
        s.require_proxy()
    gclient = GraphQLClient(HttpClient(s), per_page=s.per_page)
    info = gclient.listing_details(args.listing_id)
    if info.get("floor_plan_keys"):
        info["floor_plan_urls"] = [images.cdn_url(k, size=s.image_size) for k in info["floor_plan_keys"]]
    print(json.dumps(info, indent=2))
    return 0


def cmd_parse_srp(args: argparse.Namespace) -> int:
    from . import srp_html

    html = Path(args.file).read_text(encoding="utf-8", errors="replace")
    records, meta = srp_html.parse_srp_html(html, args.bucket)
    print(json.dumps({
        "meta": meta,
        "listing_count": len(records),
        "sample": [r.to_json() for r in records[:5]],
    }, indent=2))
    return 0


def cmd_areas(args: argparse.Namespace) -> int:
    if args.borough:
        from .constants import neighborhoods_for_borough, AREA_NAMES
        code = _parse_areas(args.borough)[0]
        for c in neighborhoods_for_borough(code):
            print(f"{c}\t{AREA_NAMES.get(c)}")
        return 0
    for code, slug in BOROUGHS.items():
        print(f"{code}\t{slug}")
    print("1\tALL_NYC_AND_NJ")
    return 0


# --- arg parsing ------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="streeteasy-floorplans", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser, *, proxy: bool = True) -> None:
        sp.add_argument("--out", help="output dataset dir (default: ./dataset or $SE_OUT_DIR)")
        if proxy:
            sp.add_argument("--proxy-url", help="US residential proxy URL; may contain {{rand}} for per-request session rotation")
            sp.add_argument("--no-proxy", action="store_true", help="disable proxy")
            sp.add_argument("--allow-no-proxy", action="store_true", help="proceed without a proxy (expect 403s)")
            sp.add_argument("--impersonate", help="curl_cffi target (default chrome131)")
            sp.add_argument("--per-page", type=int, help="results per search page")
            sp.add_argument("--image-size", help=f"CDN size tail (default {constants.DEFAULT_IMAGE_SIZE})")

    sp = sub.add_parser("run", help="full pipeline")
    add_common(sp)
    sp.add_argument("--buckets", help="comma list: studio,1br,2br,3br,4plus (default all)")
    sp.add_argument("--areas", help="comma list of area names/codes (default: 5 boroughs)")
    sp.add_argument("--details", choices=["none", "hits", "all"], default="none",
                    help="detail enrichment: none | hits (all plan images for flagged) | all (authoritative)")
    sp.add_argument("--no-download", action="store_true", help="skip image download")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("enumerate", help="enumerate + write index, no download")
    add_common(sp)
    sp.add_argument("--buckets")
    sp.add_argument("--areas")
    sp.add_argument("--details", choices=["none", "hits", "all"], default="none")
    sp.set_defaults(func=cmd_enumerate)

    sp = sub.add_parser("download", help="download floor-plan images from index.jsonl")
    add_common(sp)
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("ingest", help="ingest a browser-harvested harvest.json into the dataset index")
    add_common(sp)
    sp.add_argument("file", help="harvest.json produced by tools/harvest.user.js")
    sp.add_argument("--download", action="store_true", help="also download floor-plan images now (no proxy needed)")
    sp.add_argument("--merge", action="store_true", help="merge into an existing index.jsonl instead of replacing it")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("details", help="fetch one listing's floor-plan info")
    add_common(sp)
    sp.add_argument("listing_id")
    sp.set_defaults(func=cmd_details)

    sp = sub.add_parser("parse-srp", help="offline: parse a saved SRP HTML file")
    sp.add_argument("file")
    sp.add_argument("--bucket", default="unknown")
    sp.set_defaults(func=cmd_parse_srp)

    sp = sub.add_parser("areas", help="list area codes")
    sp.add_argument("--borough", help="show neighborhoods for a borough (name/code)")
    sp.set_defaults(func=cmd_areas)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except RuntimeError as exc:  # covers require_proxy / BlockedError / GraphQLError
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
