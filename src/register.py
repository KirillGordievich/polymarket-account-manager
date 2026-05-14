"""Register account on Polymarket CLOB API."""
from __future__ import annotations

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import ApiCreds, AssetType, BalanceAllowanceParams

from src.config import CHAIN_ID, CLOB_HOST


def _make_client(private_key: str, creds: ApiCreds | None = None) -> ClobClient:
    """Create a ClobClient with optional L2 auth (API credentials)."""
    return ClobClient(
        host=CLOB_HOST,
        chain_id=CHAIN_ID,
        key=private_key,
        creds=creds,
        signature_type=2,
    )


def register_api_key(private_key: str, proxy: str = "", headers: dict[str, str] | None = None) -> ApiCreds:
    """Create or derive API credentials for the given private key.

    Uses L1 auth (private key signature) to register on the CLOB API.
    Idempotent — safe to call multiple times.
    """
    client = _make_client(private_key)
    if proxy or headers:
        from src.proxy import patched_clob_http

        with patched_clob_http(proxy, headers):
            return client.create_or_derive_api_key()
    return client.create_or_derive_api_key()


def verify_account(private_key: str, creds: ApiCreds) -> dict:
    """Check account status and USDC balance on Polymarket."""
    client = _make_client(private_key, creds)
    balance = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL),
    )
    return {"balance": balance}


def get_notifications(private_key: str, creds: ApiCreds) -> list:
    """Get auto-redeem notification subscriptions."""
    return _make_client(private_key, creds).get_notifications()


def drop_notifications(private_key: str, creds: ApiCreds) -> dict:
    """Disable auto-redeem (drop all notification subscriptions)."""
    return _make_client(private_key, creds).drop_notifications()
