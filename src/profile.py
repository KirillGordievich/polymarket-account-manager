"""Create and query Polymarket profiles via the Gamma API."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import requests
from faker import Faker

from src.config import FUN_XYZ_API, FUN_XYZ_KEY, GAMMA_API, POLYMARKET_URL, USDC_E_POLYGON
from src.fingerprint import generate_headers

_EMAIL_NOTIFICATION_PREFS = json.dumps({
    "generalEmail": {"sendEmails": False},
    "marketEmails": {"sendEmails": False},
    "newsletterEmails": {"sendEmails": False},
    "promotionalEmails": {"sendEmails": False},
    "eventEmails": {"sendEmails": False, "tagIds": ["2", "21", "1", "107", "596", "74", "101110"]},
    "orderFillEmails": {"sendEmails": False, "hideSmallFills": True},
    "resolutionEmails": {"sendEmails": False},
})

_APP_NOTIFICATION_PREFS = json.dumps({
    "eventApp": {"sendApp": True, "tagIds": ["2", "21", "1", "107", "596", "74", "101110"]},
    "marketPriceChangeApp": {"sendApp": True},
    "orderFillApp": {"sendApp": True, "hideSmallFills": True},
    "resolutionApp": {"sendApp": True},
})


def check_username_available(username: str, proxy: str = "", headers: dict[str, str] | None = None) -> bool:
    """Check if a username is available on Polymarket."""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.get(
        f"{POLYMARKET_URL}/api/profile/username-available",
        params={"username": username},
        headers=headers or generate_headers(),
        proxies=proxies,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("isAvailable", False)


def get_profile(session: str, proxy: str = "", headers: dict[str, str] | None = None) -> dict:
    """GET /profiles — fetch existing profile. Returns the first profile dict."""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.get(
        f"{GAMMA_API}/profiles",
        headers=headers or generate_headers(),
        cookies={"polymarketsession": session, "polymarketauthtype": "metamask"},
        proxies=proxies,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    # API may return a list of profiles, a single dict, or null
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def create_profile(
    session: str,
    address: str,
    proxy_wallet: str,
    referral: str = "",
    proxy: str = "",
    headers: dict[str, str] | None = None,
) -> dict:
    """POST /profiles — create profile matching browser format.

    Returns the response JSON (includes server-generated pseudonym).
    422 (profile already exists) is treated as success.
    """
    fake = Faker()
    fake_name = fake.user_name()

    payload: dict = {
        "displayUsernamePublic": True,
        "emailOptIn": False,
        "walletActivated": False,
        "name": fake_name,
        "pseudonym": fake_name,
        "proxyWallet": proxy_wallet,
        "users": [
            {
                "address": address,
                "email": "",
                "isExternalAuth": True,
                "proxyWallet": proxy_wallet,
                "username": fake_name,
                "provider": "metamask",
                "preferences": [
                    {
                        "preferencesStatus": "New/Existing - Created Prefs",
                        "subscriptionStatus": False,
                        "emailNotificationPreferences": _EMAIL_NOTIFICATION_PREFS,
                        "appNotificationPreferences": _APP_NOTIFICATION_PREFS,
                        "marketInterests": "[]",
                    }
                ],
                "walletPreferences": [
                    {
                        "advancedMode": False,
                        "customGasPrice": "30",
                        "gasPreference": "fast",
                        "walletPreferencesStatus": "New/Existing - Created Wallet Prefs",
                    }
                ],
            }
        ],
    }
    if referral:
        payload["referral"] = referral

    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.post(
        f"{GAMMA_API}/profiles",
        headers=headers or generate_headers(),
        cookies={"polymarketsession": session, "polymarketauthtype": "metamask"},
        json=payload,
        timeout=15,
        proxies=proxies,
    )
    if resp.status_code == 422:
        return resp.json()
    resp.raise_for_status()
    return resp.json()


def enable_trading(session: str, profile_id: int | str, proxy: str = "", headers: dict[str, str] | None = None) -> dict:
    """PUT /profiles/{id} — enable trading (walletActivated=true).

    Must be called BEFORE accept_terms.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.put(
        f"{GAMMA_API}/profiles/{profile_id}",
        headers=headers or generate_headers(),
        cookies={"polymarketsession": session, "polymarketauthtype": "metamask"},
        json={"walletActivated": True},
        proxies=proxies,
        timeout=10,
    )
    if resp.status_code == 422:
        return resp.json() if resp.text.strip() else {}
    resp.raise_for_status()
    return resp.json() if resp.text.strip() else {}


def accept_terms(session: str, profile_id: int | str, proxy: str = "", headers: dict[str, str] | None = None) -> dict:
    """PUT /profiles/{id} — accept Terms of Service.

    Sets termsAcceptedAt to current UTC time.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.put(
        f"{GAMMA_API}/profiles/{profile_id}",
        headers=headers or generate_headers(),
        cookies={"polymarketsession": session, "polymarketauthtype": "metamask"},
        json={"termsAcceptedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"},
        proxies=proxies,
        timeout=10,
    )
    if resp.status_code == 422:
        return resp.json() if resp.text.strip() else {}
    resp.raise_for_status()
    return resp.json() if resp.text.strip() else {}


def get_deposit_addresses(eoa: str, proxy_wallet: str, proxy: str = "", headers: dict[str, str] | None = None) -> dict:
    """Fetch deposit addresses from fun.xyz (Polymarket's deposit provider).

    Returns dict with keys: depositAddr, solanaAddr, tronAddr, btcAddrSegwit.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.post(
        FUN_XYZ_API,
        headers={**(headers or generate_headers()), "x-api-key": FUN_XYZ_KEY, "sec-fetch-site": "cross-site"},
        json={
            "userId": eoa,
            "recipientAddr": proxy_wallet,
            "toChainId": "137",
            "toTokenAddress": USDC_E_POLYGON.lower(),
            "clientMetadata": {
                "id": "",
                "startTimestampMs": 0,
                "finalDollarValue": 0,
                "latestQuote": None,
                "depositAddress": None,
                "initSettings": {
                    "config": {
                        "targetAsset": "0x", "targetChain": "",
                        "targetAssetTicker": "", "checkoutItemTitle": "",
                    },
                },
                "selectedSourceAssetInfo": {
                    "address": "0x", "symbol": "", "chainId": "", "iconSrc": None,
                },
                "selectedPaymentMethodInfo": {
                    "paymentMethod": "token_transfer",
                    "title": "QR Code Transfer", "description": "",
                },
            },
        },
        proxies=proxies,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
