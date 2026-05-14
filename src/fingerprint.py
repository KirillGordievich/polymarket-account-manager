"""Dynamic browser fingerprint generation per account."""
from __future__ import annotations

from browserforge.headers import HeaderGenerator

from src.config import POLYMARKET_URL

_generator = HeaderGenerator(browser="chrome", os=("windows", "macos", "linux"), device="desktop")

# Fields that must stay constant for Polymarket API compatibility.
# All keys lowercase — we normalise browserforge output to lowercase too.
_POLYMARKET_OVERRIDES_LOWER: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": POLYMARKET_URL,
    "referer": f"{POLYMARKET_URL}/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


def generate_headers() -> dict[str, str]:
    """Generate a unique set of browser headers for one account.

    Uses browserforge to randomise User-Agent, sec-ch-ua, platform, and
    Accept-Language while keeping Polymarket-specific fields constant.
    """
    raw = _generator.generate()

    # Normalise to lowercase keys so overrides replace browserforge values.
    headers: dict[str, str] = {k.lower(): v for k, v in raw.items()}

    # Remove navigation-specific keys that don't belong in API requests.
    for drop in ("upgrade-insecure-requests", "sec-fetch-user", "accept-encoding"):
        headers.pop(drop, None)

    headers.update(_POLYMARKET_OVERRIDES_LOWER)
    return headers
