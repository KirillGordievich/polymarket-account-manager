"""Proxy loading, rotation, and CLOB client patching."""
from __future__ import annotations

import re
from contextlib import contextmanager
from itertools import cycle
from urllib.parse import urlparse

_PROXY_RE = re.compile(
    r"^(https?|socks5)://(?:[^:]+:[^@]+@)?[^:]+:\d+$",
)


def parse_proxy(line: str) -> str:
    """Validate and normalize a proxy URL. Returns empty string for blanks/comments."""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    if not _PROXY_RE.match(line):
        raise ValueError(f"Invalid proxy format: {line!r}")
    return line


def load_proxies(path: str) -> list[str]:
    """Load proxy list from file, one per line. Skips blanks and #comments."""
    proxies = []
    with open(path) as f:
        for raw in f:
            url = parse_proxy(raw)
            if url:
                proxies.append(url)
    if not proxies:
        raise ValueError(f"No valid proxies found in {path}")
    return proxies


def proxy_display(proxy: str) -> str:
    """Return proxy host:port for display (strip credentials)."""
    p = urlparse(proxy)
    return f"{p.scheme}://{p.hostname}:{p.port}"


class ProxyRotator:
    """Yields proxies round-robin."""

    def __init__(self, proxies: list[str]) -> None:
        self._proxies = proxies
        self._cycle = cycle(proxies)

    def next(self) -> str:
        return next(self._cycle)

    def __len__(self) -> int:
        return len(self._proxies)


@contextmanager
def patched_clob_http(proxy_url: str, headers: dict[str, str] | None = None):
    """Temporarily replace py_clob_client_v2's global httpx.Client with a proxied one."""
    import httpx
    from py_clob_client_v2.http_helpers import helpers

    original = helpers._http_client
    kwargs: dict = {"http2": True}
    if proxy_url:
        kwargs["proxy"] = proxy_url
    if headers:
        kwargs["headers"] = headers
    helpers._http_client = httpx.Client(**kwargs)
    try:
        yield
    finally:
        helpers._http_client.close()
        helpers._http_client = original
