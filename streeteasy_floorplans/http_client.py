"""Live HTTP transport built on curl_cffi (browser TLS/JA3 impersonation).

This is the only module that needs ``curl_cffi`` installed. It implements the
StreetEasy-specific anti-bot handling:

* Chrome impersonation (matches TLS/JA3/HTTP2 to a real browser);
* US residential proxy with a fresh session per request (rotates exit IP);
* retry with exponential backoff + jitter, rotating the proxy session on every
  attempt;
* treats HTTP 403/429/5xx and any 200 body containing a PerimeterX block marker
  as retryable.

GraphQL (api-v6) needs the proxy. The image CDN (zillowstatic) does not, so
:meth:`get_bytes` defaults to a direct connection.
"""

from __future__ import annotations

import random
import time
from typing import Any, Optional

from . import constants
from .config import Settings
from .proxy import ProxyManager


class BlockedError(RuntimeError):
    """Raised when a request keeps hitting the PerimeterX wall after retries."""


class GraphQLError(RuntimeError):
    pass


def _looks_blocked(status: int, text: str) -> bool:
    if status in (403, 429):
        return True
    if status >= 500:
        return True
    head = text[:4000] if text else ""
    return any(marker in head for marker in constants.BLOCK_MARKERS)


class HttpClient:
    def __init__(self, settings: Settings, *, rng: Optional[random.Random] = None) -> None:
        try:
            from curl_cffi import requests as cffi_requests  # noqa: WPS433 (lazy import)
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "curl_cffi is required for live requests. Install with:\n"
                "  pip install curl_cffi\n"
                f"(import error: {exc})"
            ) from exc
        self._requests = cffi_requests
        self.settings = settings
        self.proxies = ProxyManager(settings.proxy_url if settings.proxy_enabled else None, rng=rng)
        self._rng = rng or random

    # --- politeness ---------------------------------------------------------
    def _sleep_jitter(self) -> None:
        lo, hi = self.settings.min_delay, self.settings.max_delay
        if hi > 0:
            time.sleep(self._rng.uniform(lo, max(lo, hi)))

    def _backoff(self, attempt: int) -> None:
        delay = self.settings.backoff_base * attempt + self._rng.uniform(0, 3)
        time.sleep(delay)

    # --- GraphQL ------------------------------------------------------------
    def graphql(self, query: str, variables: Optional[dict[str, Any]]) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables is not None:
            body["variables"] = variables

        last_err: Optional[str] = None
        for attempt in range(1, self.settings.max_retries + 1):
            proxies = self.proxies.session()
            try:
                resp = self._requests.post(
                    constants.GRAPHQL_ENDPOINT,
                    json=body,
                    headers=constants.GRAPHQL_HEADERS,
                    impersonate=self.settings.impersonate,
                    proxies=proxies,
                    timeout=self.settings.request_timeout,
                )
            except Exception as exc:  # network/proxy error -> retry
                last_err = f"transport error: {exc}"
                self._backoff(attempt)
                continue

            text = resp.text or ""
            if _looks_blocked(resp.status_code, text):
                last_err = f"blocked/HTTP {resp.status_code}"
                self._backoff(attempt)
                continue

            try:
                payload = resp.json()
            except Exception as exc:
                last_err = f"non-JSON response (HTTP {resp.status_code}): {exc}"
                self._backoff(attempt)
                continue

            if payload.get("errors"):
                msg = "; ".join(str(e.get("message", e)) for e in payload["errors"])
                raise GraphQLError(f"StreetEasy GraphQL error: {msg}")
            return payload.get("data") or {}

        raise BlockedError(f"GraphQL request failed after {self.settings.max_retries} attempts: {last_err}")

    # --- raw fetches --------------------------------------------------------
    def get_text(self, url: str, *, use_proxy: bool = True) -> str:
        headers = {
            "User-Agent": constants.GRAPHQL_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        last_err: Optional[str] = None
        for attempt in range(1, self.settings.max_retries + 1):
            proxies = self.proxies.session() if use_proxy else None
            try:
                resp = self._requests.get(
                    url,
                    headers=headers,
                    impersonate=self.settings.impersonate,
                    proxies=proxies,
                    timeout=self.settings.request_timeout,
                )
            except Exception as exc:
                last_err = f"transport error: {exc}"
                self._backoff(attempt)
                continue
            text = resp.text or ""
            if _looks_blocked(resp.status_code, text):
                last_err = f"blocked/HTTP {resp.status_code}"
                self._backoff(attempt)
                continue
            return text
        raise BlockedError(f"GET {url} failed after {self.settings.max_retries} attempts: {last_err}")

    def get_bytes(self, url: str, *, use_proxy: bool = False) -> bytes:
        """Download bytes (images). The CDN isn't bot-walled, so no proxy by default."""
        last_err: Optional[str] = None
        for attempt in range(1, self.settings.max_retries + 1):
            proxies = self.proxies.session() if use_proxy else None
            try:
                resp = self._requests.get(
                    url,
                    impersonate=self.settings.impersonate,
                    proxies=proxies,
                    timeout=self.settings.request_timeout,
                )
            except Exception as exc:
                last_err = f"transport error: {exc}"
                self._backoff(attempt)
                continue
            if resp.status_code == 200 and resp.content:
                return resp.content
            last_err = f"HTTP {resp.status_code}"
            self._backoff(attempt)
        raise RuntimeError(f"GET(bytes) {url} failed after {self.settings.max_retries} attempts: {last_err}")
