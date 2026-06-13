"""Runtime configuration. Reads environment variables with sane defaults.

Proxy settings matter most: StreetEasy's GraphQL API (api-v6) returns HTTP 403
from datacenter IPs, so a US residential proxy is effectively required for the
search/detail calls. The image CDN (zillowstatic) is not protected and needs no
proxy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import constants


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    # Output
    out_dir: Path = field(default_factory=lambda: Path(os.environ.get("SE_OUT_DIR", "dataset")))

    # Proxy. SE_PROXY_URL may contain the literal token "{{rand}}" which is
    # replaced with a fresh session id per request (rotating residential gateway).
    proxy_url: Optional[str] = field(default_factory=lambda: os.environ.get("SE_PROXY_URL") or None)
    proxy_enabled: bool = field(
        default_factory=lambda: (os.environ.get("SE_PROXY_URL") or "").strip() != ""
    )

    # HTTP / anti-bot
    impersonate: str = field(default_factory=lambda: os.environ.get("SE_IMPERSONATE", "chrome131"))
    request_timeout: int = field(default_factory=lambda: _env_int("SE_TIMEOUT", 30))
    max_retries: int = field(default_factory=lambda: _env_int("SE_MAX_RETRIES", 4))
    backoff_base: float = field(default_factory=lambda: _env_float("SE_BACKOFF_BASE", 8.0))

    # Politeness — keep concurrency low and add jitter so we don't trip
    # PerimeterX's behavioral/velocity scoring even with a good fingerprint.
    min_delay: float = field(default_factory=lambda: _env_float("SE_MIN_DELAY", 1.0))
    max_delay: float = field(default_factory=lambda: _env_float("SE_MAX_DELAY", 3.0))

    # Pagination / sharding
    per_page: int = field(default_factory=lambda: _env_int("SE_PER_PAGE", 50))
    page_cap: int = field(default_factory=lambda: _env_int("SE_PAGE_CAP", 100))  # StreetEasy caps here

    # Image download
    image_size: str = field(default_factory=lambda: os.environ.get("SE_IMAGE_SIZE", constants.DEFAULT_IMAGE_SIZE))
    image_ext: str = field(default_factory=lambda: os.environ.get("SE_IMAGE_EXT", constants.DEFAULT_IMAGE_EXT))

    def require_proxy(self) -> None:
        if not self.proxy_enabled or not self.proxy_url:
            raise RuntimeError(
                "A US residential proxy is required for StreetEasy GraphQL calls "
                "(api-v6 returns 403 from datacenter IPs). Set SE_PROXY_URL, e.g.\n"
                "  export SE_PROXY_URL='http://USER-session-{{rand}}:PASS@gate.example.com:7000'\n"
                "or pass --proxy-url. To attempt without a proxy anyway, use --no-proxy "
                "(expect 403s)."
            )
