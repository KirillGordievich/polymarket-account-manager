"""Centralised settings — loaded from environment / .env file."""
from __future__ import annotations

import os

from dotenv import load_dotenv

from web3 import Web3

load_dotenv()

# ─── Network ─────────────────────────────────────────────────────────────────

RPC_URL: str = os.environ.get("RPC_URL", "https://polygon-rpc.com")
CHAIN_ID: int = int(os.environ.get("CHAIN_ID", "137"))

# ─── Polygon contract addresses ───────────────────────────────────────────────

USDC_E_POLYGON = Web3.to_checksum_address(
    os.environ.get("USDC_E_POLYGON", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
)
CTF_EXCHANGE = Web3.to_checksum_address(
    os.environ.get("CTF_EXCHANGE", "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E")
)
NEG_RISK_CTF_EXCHANGE = Web3.to_checksum_address(
    os.environ.get("NEG_RISK_CTF_EXCHANGE", "0xC5d563A36AE78145C45a50134d48A1215220f80a")
)
NEG_RISK_ADAPTER = Web3.to_checksum_address(
    os.environ.get("NEG_RISK_ADAPTER", "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296")
)
COLLATERAL_TOKEN = Web3.to_checksum_address(
    os.environ.get("COLLATERAL_TOKEN", "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB")
)
CTF = Web3.to_checksum_address(
    os.environ.get("CTF", "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")
)
USDC_SPENDER = Web3.to_checksum_address(
    os.environ.get("USDC_SPENDER", "0x93070a847efef7f70739046a929d47a521f5b8ee")
)

# Operators that need ERC-20 approve on collateral + ERC-1155 setApprovalForAll on CTF
CTF_OPERATORS: list[str] = [
    "0xe111180000d2663c0091e4f400237545b87b996b",
    "0xe2222d279d744050d28e00520010520000310f59",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296",
    "0xada100db00ca00073811820692005400218fce1f",
    "0xada2005600dec949baf300f4c6120000bdb6eaab",
]

# ─── API endpoints ────────────────────────────────────────────────────────────

POLYMARKET_URL: str = os.environ.get("POLYMARKET_URL", "https://polymarket.com")
GAMMA_API: str = os.environ.get("GAMMA_API", "https://gamma-api.polymarket.com")
CLOB_HOST: str = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")
RELAYER_URL: str = os.environ.get("RELAYER_URL", "https://relayer-v2.polymarket.com/submit")
FUN_XYZ_API: str = os.environ.get("FUN_XYZ_API", "https://api.fun.xyz/v1/eoa")
FUN_XYZ_KEY: str = os.environ.get("FUN_XYZ_KEY", "Y53dikxXdT4E3afI1l8BMBSWgyhKvf65k6Dut1k6")

# ─── Registration ─────────────────────────────────────────────────────────────

# Default referral code supports the developer. To disable: set REFERRAL= in .env
REFERRAL: str = os.environ.get("REFERRAL", "SupportMeCode")
