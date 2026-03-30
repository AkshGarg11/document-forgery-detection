"""
Deploy DocumentVerification using Web3.py against Ganache App.

Usage:
  python blockchain/scripts/deploy_with_web3.py
"""

from __future__ import annotations

import json
from pathlib import Path

from web3 import Web3

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "blockchain" / "artifacts" / "contracts" / "DocumentVerification.sol" / "DocumentVerification.json"
RPC_URL = "http://127.0.0.1:7545"


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to RPC node: {RPC_URL}")

    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])

    deployer = w3.eth.accounts[0]
    tx_hash = contract.constructor().transact({"from": deployer, "gas": 4_000_000})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print("DocumentVerification deployed at:", receipt.contractAddress)


if __name__ == "__main__":
    main()
