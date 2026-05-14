"""Deposit wallet creation and approval via Polymarket relayer (WALLET type)."""
from __future__ import annotations

import time

import httpx
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak as eth_keccak
from eth_utils import to_bytes, to_checksum_address

from src.config import (
    CHAIN_ID,
    COLLATERAL_TOKEN,
    CTF,
    CTF_OPERATORS,
    USDC_E_POLYGON,
    USDC_SPENDER,
)
from src.fingerprint import generate_headers
from web3 import Web3

# ─── Relayer ──────────────────────────────────────────────────────────────────

RELAYER_BASE = "https://relayer-v2.polymarket.com"
DEPOSIT_WALLET_FACTORY = "0x00000000000Fb5C9ADea0298D729A0CB3823Cc07"

# ─── Deposit wallet derivation (Solady ERC-1967 CREATE2) ─────────────────────

DEPOSIT_WALLET_IMPL = "0x58CA52ebe0DadfdF531Cde7062e76746de4Db1eB"

_ERC1967_PREFIX = 0x61003D3D8160233D3973
_ERC1967_CONST2 = bytes.fromhex("5155f3363d3d373d3d363d7f360894a13ba1a3210667c828492db98dca3e2076")
_ERC1967_CONST1 = bytes.fromhex("cc3735a920a3ca505d382bbc545af43d6000803e6038573d6000fd5b3d6000f3")


def _init_code_hash_erc1967(implementation: str, args: bytes) -> bytes:
    """Compute Solady LibClone.initCodeHashERC1967(implementation, args)."""
    n = len(args)
    combined = (_ERC1967_PREFIX + (n << 56)).to_bytes(10, "big")
    init_code = (
        combined
        + to_bytes(hexstr=implementation[2:])
        + bytes.fromhex("6009")
        + _ERC1967_CONST2
        + _ERC1967_CONST1
        + args
    )
    return eth_keccak(init_code)


def derive_deposit_wallet(owner: str) -> str:
    """Derive the deposit wallet address from an EOA via CREATE2 (Solady ERC-1967)."""
    owner = to_checksum_address(owner)
    factory = to_checksum_address(DEPOSIT_WALLET_FACTORY)
    impl = to_checksum_address(DEPOSIT_WALLET_IMPL)

    wallet_id = bytes(12) + to_bytes(hexstr=owner[2:])  # left-pad to 32 bytes
    args = encode(["address", "bytes32"], [factory, wallet_id])
    salt = eth_keccak(args)
    bytecode_hash = _init_code_hash_erc1967(impl, args)

    factory_bytes = to_bytes(hexstr=factory[2:])
    address_hash = eth_keccak(b"\xff" + factory_bytes + salt + bytecode_hash)
    return to_checksum_address(address_hash[-20:].hex())

# ─── EIP-712 types for Batch signing ──────────────────────────────────────────

BATCH_TYPES = {
    "Call": [
        {"name": "target", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
    ],
    "Batch": [
        {"name": "wallet", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "calls", "type": "Call[]"},
    ],
}

# ─── Call builders ────────────────────────────────────────────────────────────

APPROVE_SELECTOR = "095ea7b3"
SET_APPROVAL_FOR_ALL_SELECTOR = "a22cb465"
MAX_UINT256_HEX = "f" * 64


def _approve_data(spender: str) -> str:
    """Build ERC-20 approve(spender, MAX_UINT256) calldata."""
    padded = spender.lower().replace("0x", "").zfill(64)
    return "0x" + APPROVE_SELECTOR + padded + MAX_UINT256_HEX


def _set_approval_for_all_data(operator: str) -> str:
    """Build ERC-1155 setApprovalForAll(operator, true) calldata."""
    padded = operator.lower().replace("0x", "").zfill(64)
    return "0x" + SET_APPROVAL_FOR_ALL_SELECTOR + padded + "0" * 63 + "1"


def build_approval_calls() -> list[dict]:
    """Build the standard set of Polymarket approval calls."""
    calls = []

    # Approve CTF exchange on collateral token
    calls.append({"target": Web3.to_checksum_address(COLLATERAL_TOKEN), "value": "0", "data": _approve_data(CTF)})

    # Each operator: collateral approve + CTF setApprovalForAll
    for op in CTF_OPERATORS:
        calls.append({"target": Web3.to_checksum_address(COLLATERAL_TOKEN), "value": "0", "data": _approve_data(op)})
        calls.append({"target": Web3.to_checksum_address(CTF), "value": "0", "data": _set_approval_for_all_data(op)})

    # Approve USDC spender on USDC
    usdc_target = Web3.to_checksum_address(USDC_E_POLYGON)
    calls.append({"target": usdc_target, "value": "0", "data": _approve_data(USDC_SPENDER)})

    return calls


# ─── Relayer API ──────────────────────────────────────────────────────────────


def _http_client(proxy: str = "", session: str = "", headers: dict[str, str] | None = None) -> httpx.Client:
    cookies = {}
    if session:
        cookies["polymarketsession"] = session
        cookies["polymarketauthtype"] = "metamask"
    kwargs: dict = {"timeout": 30, "cookies": cookies or None, "headers": headers or generate_headers()}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def create_deposit_wallet(
    owner: str, proxy: str = "", session: str = "", headers: dict[str, str] | None = None,
) -> dict:
    """Deploy the deposit wallet via relayer (no signature needed)."""
    payload = {
        "type": "WALLET-CREATE",
        "from": Web3.to_checksum_address(owner),
        "to": DEPOSIT_WALLET_FACTORY,
    }
    with _http_client(proxy, session, headers) as client:
        resp = client.post(f"{RELAYER_BASE}/submit", json=payload)
        resp.raise_for_status()
        return resp.json()


def get_relayer_nonce(address: str, proxy: str = "", session: str = "", headers: dict[str, str] | None = None) -> int:
    """Get wallet nonce from relayer API."""
    with _http_client(proxy, session, headers) as client:
        resp = client.get(
            f"{RELAYER_BASE}/nonce",
            params={"address": Web3.to_checksum_address(address), "type": "WALLET"},
        )
        resp.raise_for_status()
        return int(resp.json()["nonce"])


def _sign_batch(
    private_key: str,
    deposit_wallet: str,
    nonce: int,
    deadline: int,
    calls: list[dict],
) -> str:
    """Sign a batch of calls using EIP-712 (DepositWallet.Batch)."""
    acct = Account.from_key(private_key)
    wallet_addr = Web3.to_checksum_address(deposit_wallet)

    domain = {
        "name": "DepositWallet",
        "version": "1",
        "chainId": CHAIN_ID,
        "verifyingContract": wallet_addr,
    }

    message = {
        "wallet": wallet_addr,
        "nonce": nonce,
        "deadline": deadline,
        "calls": [
            {
                "target": Web3.to_checksum_address(c["target"]),
                "value": int(c["value"]),
                "data": bytes.fromhex(c["data"].replace("0x", "")),
            }
            for c in calls
        ],
    }

    signed = acct.sign_typed_data(
        domain_data=domain,
        message_types=BATCH_TYPES,
        message_data=message,
    )
    return "0x" + signed.signature.hex()


def _poll_transaction(
    tx_id: str, proxy: str = "", session: str = "",
    max_polls: int = 20, headers: dict[str, str] | None = None,
) -> str:
    """Poll relayer until transaction reaches STATE_CONFIRMED or STATE_FAILED."""
    for _ in range(max_polls):
        time.sleep(3)
        with _http_client(proxy, session, headers) as client:
            resp = client.get(f"{RELAYER_BASE}/transaction", params={"id": tx_id})
            txns = resp.json()
            if txns:
                state = txns[0].get("state", "")
                if state in ("STATE_CONFIRMED", "STATE_FAILED"):
                    return state
    return "TIMEOUT"


def relay_wallet_approve(
    private_key: str,
    deposit_wallet: str,
    proxy: str = "",
    session: str = "",
    headers: dict[str, str] | None = None,
) -> dict:
    """Full wallet approve flow: create wallet → wait confirm → get nonce → sign batch → submit.

    Returns the relayer response with transactionID and transactionHash.
    """
    acct = Account.from_key(private_key)
    owner = acct.address

    # Step 1: Deploy deposit wallet and wait for confirmation
    try:
        create_resp = create_deposit_wallet(owner, proxy, session, headers)
        tx_id = create_resp.get("transactionID", "")
        if tx_id and create_resp.get("state") != "STATE_FAILED":
            _poll_transaction(tx_id, proxy, session, headers=headers)
    except Exception:
        pass  # "wallet already deployed" is expected for existing accounts

    # Step 2: Get nonce from relayer
    nonce = get_relayer_nonce(owner, proxy, session, headers)

    # Step 3: Build and sign approval batch
    calls = build_approval_calls()
    deadline = int(time.time()) + 3600
    signature = _sign_batch(private_key, deposit_wallet, nonce, deadline, calls)

    # Step 4: Submit to relayer
    payload = {
        "type": "WALLET",
        "from": owner,
        "to": DEPOSIT_WALLET_FACTORY,
        "nonce": str(nonce),
        "signature": signature,
        "depositWalletParams": {
            "depositWallet": Web3.to_checksum_address(deposit_wallet),
            "deadline": str(deadline),
            "calls": calls,
        },
    }

    with _http_client(proxy, session, headers) as client:
        resp = client.post(f"{RELAYER_BASE}/submit", json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"relayer {resp.status_code}: {resp.text}")
        return resp.json()
