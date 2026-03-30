"""
services/blockchain_service.py
Web3 integration for document hash anchoring and verification.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

BLOCKCHAIN_ENABLED = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() == "true"
WEB3_PROVIDER_URI = os.getenv("WEB3_PROVIDER_URI", os.getenv("GANACHE_RPC_URL", "http://127.0.0.1:7545"))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY", os.getenv("GANACHE_PRIVATE_KEY", ""))
CHAIN_ID = int(os.getenv("CHAIN_ID", "1337"))
CONTRACT_ABI_PATH = os.getenv("CONTRACT_ABI_PATH", "")

_MINIMAL_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "fileHash", "type": "bytes32"},
            {"internalType": "bytes32", "name": "textHash", "type": "bytes32"},
        ],
        "name": "issueDocument",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "verifyDocument",
        "outputs": [
            {"internalType": "bool", "name": "isValid", "type": "bool"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "address", "name": "issuer", "type": "address"},
            {"internalType": "bool", "name": "revoked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "revokeDocument",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "fileHash", "type": "bytes32"}],
        "name": "getDocument",
        "outputs": [
            {"internalType": "address", "name": "issuer", "type": "address"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes32", "name": "textHash", "type": "bytes32"},
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "bool", "name": "revoked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def _normalize_hash(hash_hex: str) -> str:
    value = hash_hex.strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    if len(value) != 64:
        raise ValueError("Hash must be 64 hex characters")
    int(value, 16)
    return value


def _to_bytes32(hash_hex: str) -> bytes:
    return bytes.fromhex(_normalize_hash(hash_hex))


def _bytes_to_hex(value: bytes) -> str:
    return value.hex()


def _load_contract_abi() -> list[dict[str, Any]]:
    if CONTRACT_ABI_PATH:
        candidate = Path(CONTRACT_ABI_PATH)
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))

    artifact = _REPO_ROOT / "blockchain" / "artifacts" / "contracts" / "DocumentVerification.sol" / "DocumentVerification.json"
    if artifact.exists():
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        abi = payload.get("abi")
        if isinstance(abi, list):
            return abi

    return _MINIMAL_ABI


def _get_web3_and_contract() -> tuple[Any, Any]:
    if not BLOCKCHAIN_ENABLED:
        raise RuntimeError("Blockchain integration is disabled")

    if not CONTRACT_ADDRESS:
        raise RuntimeError("CONTRACT_ADDRESS is not configured")

    web3_module = importlib.import_module("web3")
    Web3 = web3_module.Web3

    w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
    if not w3.is_connected():
        raise RuntimeError(f"Unable to connect to RPC node: {WEB3_PROVIDER_URI}")

    contract = w3.eth.contract(address=w3.to_checksum_address(CONTRACT_ADDRESS), abi=_load_contract_abi())
    return w3, contract


def _send_transaction(w3: Any, tx: dict[str, Any]) -> str:
    if PRIVATE_KEY:
        account = w3.eth.account.from_key(PRIVATE_KEY)
        tx.setdefault("from", account.address)
        tx.setdefault("nonce", w3.eth.get_transaction_count(account.address))
        tx.setdefault("chainId", CHAIN_ID)
        tx.setdefault("gas", 300000)
        if "maxFeePerGas" not in tx and "maxPriorityFeePerGas" not in tx and "gasPrice" not in tx:
            tx["gasPrice"] = w3.eth.gas_price

        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt.transactionHash.hex()

    accounts = w3.eth.accounts
    if not accounts:
        raise RuntimeError("No unlocked accounts available; set DEPLOYER_PRIVATE_KEY")

    tx.setdefault("from", accounts[0])
    tx.setdefault("chainId", CHAIN_ID)
    tx.setdefault("gas", 300000)
    if "maxFeePerGas" not in tx and "maxPriorityFeePerGas" not in tx and "gasPrice" not in tx:
        tx["gasPrice"] = w3.eth.gas_price
    tx_hash = w3.eth.send_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.transactionHash.hex()


def _resolve_sender_address(w3: Any) -> str:
    if PRIVATE_KEY:
        return w3.eth.account.from_key(PRIVATE_KEY).address

    accounts = w3.eth.accounts
    if not accounts:
        raise RuntimeError("No unlocked accounts available; set DEPLOYER_PRIVATE_KEY")
    return accounts[0]


def issue_document(file_hash_hex: str, text_hash_hex: str | None = None) -> str:
    """Issue an on-chain document record."""
    w3, contract = _get_web3_and_contract()
    file_hash = _to_bytes32(file_hash_hex)
    text_hash = _to_bytes32(text_hash_hex or file_hash_hex)
    sender = _resolve_sender_address(w3)

    tx = contract.functions.issueDocument(file_hash, text_hash).build_transaction(
        {"from": sender, "gas": 300000, "chainId": CHAIN_ID}
    )
    tx_hash = _send_transaction(w3, tx)
    logger.info("Document issued. file_hash=%s tx=%s", file_hash_hex, tx_hash)
    return tx_hash


def verify_document(file_hash_hex: str) -> dict[str, Any]:
    """Verify a file hash against on-chain record."""
    _, contract = _get_web3_and_contract()
    file_hash = _to_bytes32(file_hash_hex)

    is_valid, timestamp, issuer, revoked = contract.functions.verifyDocument(file_hash).call()
    record_issuer, record_ts, text_hash, exists, record_revoked = contract.functions.getDocument(file_hash).call()

    return {
        "exists": bool(exists),
        "is_valid": bool(is_valid),
        "revoked": bool(revoked or record_revoked),
        "timestamp": int(timestamp if timestamp else record_ts),
        "issuer": issuer if issuer != "0x0000000000000000000000000000000000000000" else record_issuer,
        "text_hash": _bytes_to_hex(text_hash),
    }


def revoke_document(file_hash_hex: str) -> str:
    """Revoke a previously issued file hash."""
    w3, contract = _get_web3_and_contract()
    file_hash = _to_bytes32(file_hash_hex)
    sender = _resolve_sender_address(w3)

    tx = contract.functions.revokeDocument(file_hash).build_transaction(
        {"from": sender, "gas": 300000, "chainId": CHAIN_ID}
    )
    tx_hash = _send_transaction(w3, tx)
    logger.info("Document revoked. file_hash=%s tx=%s", file_hash_hex, tx_hash)
    return tx_hash
