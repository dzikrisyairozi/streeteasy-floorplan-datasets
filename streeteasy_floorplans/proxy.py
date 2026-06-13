"""Proxy URL templating with per-request session rotation.

A rotating residential gateway is configured as a single URL containing the
literal token ``{{rand}}`` somewhere in the userinfo, e.g.::

    http://user-session-{{rand}}:pass@gate.decodo.com:7000

Each call to :meth:`ProxyManager.session` substitutes a fresh random session id,
so every request exits a different US residential IP. If the URL contains no
``{{rand}}`` token it is used as-is (a static proxy).

Pure stdlib — no network, fully unit-testable.
"""

from __future__ import annotations

import random
import string
from typing import Optional

_RAND_TOKEN = "{{rand}}"
_ALPHABET = string.ascii_letters + string.digits


def _rand_session(n: int = 16, rng: Optional[random.Random] = None) -> str:
    r = rng or random
    return "".join(r.choice(_ALPHABET) for _ in range(n))


class ProxyManager:
    def __init__(self, proxy_url: Optional[str], *, rng: Optional[random.Random] = None) -> None:
        self.proxy_url = proxy_url or None
        self._rng = rng

    @property
    def enabled(self) -> bool:
        return bool(self.proxy_url)

    @property
    def rotating(self) -> bool:
        return bool(self.proxy_url) and _RAND_TOKEN in self.proxy_url

    def session(self) -> Optional[dict[str, str]]:
        """Return a ``{"http": url, "https": url}`` mapping for curl_cffi, or None.

        Substitutes a fresh session id into a ``{{rand}}`` template each call.
        """
        if not self.proxy_url:
            return None
        url = self.proxy_url
        if _RAND_TOKEN in url:
            url = url.replace(_RAND_TOKEN, _rand_session(rng=self._rng))
        return {"http": url, "https": url}
