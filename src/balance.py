"""On-chain balance queries for Polygon."""
from __future__ import annotations

from src.config import RPC_URL, USDC_E_POLYGON
from src.web3.abi import ERC20_ABI
from web3 import Web3


def get_usdc_balance(address: str, rpc_url: str = RPC_URL) -> float:
    """Get USDC balance for an address. Returns amount in USDC."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    usdc = w3.eth.contract(address=USDC_E_POLYGON, abi=ERC20_ABI)
    raw = usdc.functions.balanceOf(Web3.to_checksum_address(address)).call()
    return raw / 1_000_000


def get_matic_balance(address: str, rpc_url: str = RPC_URL) -> float:
    """Get native MATIC balance for an address."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    raw = w3.eth.get_balance(Web3.to_checksum_address(address))
    return float(w3.from_wei(raw, "ether"))
