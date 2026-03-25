"""
services/blockchain_service.py
Handles interaction with the DocumentVerification smart contract.
Replace mock logic with real Web3 calls once a node is available.
"""

import os
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

# --- Configuration (loaded from environment) ---
WEB3_PROVIDER_URI = os.getenv("WEB3_PROVIDER_URI", "http://localhost:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY", "")


def store_on_blockchain(doc_hash: str, cid: str, result: str) -> str | None:
    """
    Store document verification data on the blockchain.

    Args:
        doc_hash: SHA-256 hash of the document.
        cid:      IPFS Content Identifier.
        result:   Forgery classification label.

    Returns:
        Transaction hash string, or None if blockchain is unavailable.

    ---
    MOCK IMPLEMENTATION:
    Replace the body below with real Web3.py logic:

        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        tx = contract.functions.storeVerification(doc_hash, cid, result).build_transaction({...})
        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        receipt = w3.eth.send_raw_transaction(signed.rawTransaction)
        return receipt.transactionHash.hex()
    """
    logger.info(
        "[BLOCKCHAIN MOCK] Storing doc_hash=%s, cid=%s, result=%s",
        doc_hash, cid, result,
    )

    # Simulate a fake transaction hash deterministically
    payload = f"{doc_hash}:{cid}:{result}:{int(time.time())}"
    fake_tx = "0x" + hashlib.sha256(payload.encode()).hexdigest()

    logger.info("[BLOCKCHAIN MOCK] Fake tx_hash=%s", fake_tx)
    return fake_tx
