"""Polymarket sign-in via direct SIWE (EIP-4361) — no browser needed."""
from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

from src.config import GAMMA_API, POLYMARKET_URL
from src.fingerprint import generate_headers

SESSION_COOKIE = "polymarketsession"
_GAMMA = GAMMA_API  # https://gamma-api.polymarket.com


def get_polymarket_session(
    private_key: str,
    log: Callable = lambda _: None,
    proxy: str = "",
    headers: dict[str, str] | None = None,
) -> str:
    """Sign in to Polymarket and return the polymarketsession cookie value.

    Uses direct SIWE auth with gamma-api:
      1. GET /nonce  → nonce + polymarketnonce cookie (CSRF session)
      2. Build SIWE EIP-4361 message text (Polymarket's exact statement + expiry)
      3. Sign with personal_sign (EIP-191)
      4. Build Bearer JWT: base64(JSON_fields:::0xsignature)
      5. GET /login with Bearer + polymarketnonce cookie → polymarketsession cookie
    """
    acct = Account.from_key(private_key)
    address = acct.address

    # Step 1: get nonce — gamma sets polymarketnonce cookie (CSRF session)
    log("  [dim]→ getting nonce...[/dim]")
    http = requests.Session()
    http.headers.update(headers or generate_headers())
    if proxy:
        http.proxies = {"http": proxy, "https": proxy}
    nonce_resp = http.get(f"{_GAMMA}/nonce")
    nonce_resp.raise_for_status()
    nonce = nonce_resp.json()["nonce"]

    # Step 2: build SIWE message (Polymarket's exact format)
    now = datetime.now(UTC)
    expiry = now + timedelta(days=7)
    issued_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    expiration_time = expiry.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    statement = "Welcome to Polymarket! Sign to connect."

    siwe_text = (
        f"polymarket.com wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"{statement}\n\n"
        f"URI: {POLYMARKET_URL}\n"
        f"Version: 1\n"
        f"Chain ID: 137\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        f"Expiration Time: {expiration_time}"
    )

    # Step 3: sign (EIP-191 personal_sign of the SIWE text)
    log("  [dim]→ signing SIWE message...[/dim]")
    msg = encode_defunct(text=siwe_text)
    signature = "0x" + acct.sign_message(msg).signature.hex()

    # Step 4: build Bearer JWT — format is base64(JSON:::signature)
    siwe_fields = json.dumps(
        {
            "domain": "polymarket.com",
            "address": address,
            "statement": statement,
            "uri": POLYMARKET_URL,
            "version": "1",
            "chainId": 137,
            "nonce": nonce,
            "issuedAt": issued_at,
            "expirationTime": expiration_time,
        },
        separators=(",", ":"),
    )
    jwt_payload = f"{siwe_fields}:::{signature}"
    # Polymarket uses standard base64 (btoa in JS), NOT urlsafe-stripped
    jwt = base64.b64encode(jwt_payload.encode()).decode()

    # Step 5: GET /login — requests.Session sends polymarketnonce cookie automatically
    log("  [dim]→ logging in...[/dim]")
    login_resp = http.get(
        f"{_GAMMA}/login",
        headers={"Authorization": f"Bearer {jwt}"},
    )

    poly_session = login_resp.cookies.get(SESSION_COOKIE)
    if not poly_session:
        raise RuntimeError(
            f"gamma /login {login_resp.status_code}: {login_resp.text[:300]}"
        )
    return poly_session
