"""Ethereum wallet generation and account file management."""
from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from eth_account import Account

ACCOUNTS_DIR = Path(__file__).resolve().parent.parent / "accounts"
ACCOUNTS_CSV = ACCOUNTS_DIR / "accounts.csv"

_batch_csv: Path | None = None


def init_batch_csv(name: str = "") -> Path:
    """Create a batch CSV for this run. Uses timestamp if name not given. Returns the path."""
    global _batch_csv
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    if name:
        if not name.endswith(".csv"):
            name += ".csv"
        _batch_csv = ACCOUNTS_DIR / name
    else:
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        _batch_csv = ACCOUNTS_DIR / f"{ts}_accounts.csv"
    return _batch_csv

CSV_FIELDS = [
    "address", "private_key",
    "username", "profile_created", "trading_enabled",
    "api_key", "api_secret", "api_passphrase",
    "proxy_wallet", "deposit_address",
    "terms_accepted", "usdc_approved", "auto_redeem_enabled",
    "referral_code", "http_proxy", "user_agent", "created_at",
]


def generate_wallet() -> tuple[str, str]:
    """Generate a new Ethereum wallet. Returns (address, private_key)."""
    acct = Account.create()
    return acct.address, acct.key.hex()


def save_account(
    address: str,
    private_key: str,
    username: str = "",
    polymarket_session: str = "",
    profile_created: bool = False,
    trading_enabled: bool = False,
    api_key: str = "",
    api_secret: str = "",
    api_passphrase: str = "",
    proxy_wallet: str = "",
    deposit_address: str = "",
    terms_accepted: bool = False,
    usdc_approved: bool = False,
    auto_redeem_enabled: bool = True,
    referral_code: str = "",
    http_proxy: str = "",
    user_agent: str = "",
) -> Path:
    """Save account data to JSON file. Returns the file path."""
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ACCOUNTS_DIR / f"{address}.json"
    data = {
        "address": address,
        "private_key": private_key,
        "username": username,
        "polymarket_session": polymarket_session,
        "profile_created": profile_created,
        "trading_enabled": trading_enabled,
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_passphrase,
        "proxy_wallet": proxy_wallet,
        "deposit_address": deposit_address,
        "created_at": datetime.now(UTC).isoformat(),
        "terms_accepted": terms_accepted,
        "usdc_approved": usdc_approved,
        "auto_redeem_enabled": auto_redeem_enabled,
        "referral_code": referral_code,
        "http_proxy": http_proxy,
        "user_agent": user_agent,
    }
    path.write_text(json.dumps(data, indent=2))
    _append_csv(data)
    return path


def _append_csv(data: dict) -> None:
    """Append account to global CSV and batch CSV (if initialized)."""
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    for csv_path in (ACCOUNTS_CSV, _batch_csv):
        if csv_path is None:
            continue
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({k: data.get(k, "") for k in CSV_FIELDS})


def load_account(path: Path) -> dict:
    """Load account data from JSON file."""
    return json.loads(path.read_text())


def list_accounts() -> list[dict]:
    """Load all accounts from the accounts directory."""
    if not ACCOUNTS_DIR.exists():
        return []
    accounts = []
    for f in sorted(ACCOUNTS_DIR.glob("0x*.json")):
        accounts.append(load_account(f))
    return accounts


def get_account_path(address: str) -> Path:
    """Get the file path for an account by address."""
    return ACCOUNTS_DIR / f"{address}.json"
