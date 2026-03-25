"""
services/ipfs_service.py
Handles file uploads to IPFS.
Replace mock logic with a real IPFS client (e.g., ipfshttpclient or Pinata API).
"""

import os
import logging
import hashlib

logger = logging.getLogger(__name__)

IPFS_API_URL = os.getenv("IPFS_API_URL", "http://localhost:5001")
PINATA_API_KEY = os.getenv("PINATA_API_KEY", "")
PINATA_SECRET = os.getenv("PINATA_SECRET", "")


def upload_to_ipfs(content: bytes) -> str:
    """
    Upload raw file bytes to IPFS and return the Content Identifier (CID).

    Args:
        content: Raw file bytes.

    Returns:
        IPFS CID string.

    ---
    MOCK IMPLEMENTATION:
    For real IPFS, replace with:

        import ipfshttpclient
        client = ipfshttpclient.connect(IPFS_API_URL)
        res = client.add_bytes(content)
        return res  # Returns the CID

    Or using Pinata:
        import requests
        headers = {"pinata_api_key": PINATA_API_KEY, "pinata_secret_api_key": PINATA_SECRET}
        files = {"file": content}
        res = requests.post("https://api.pinata.cloud/pinning/pinFileToIPFS", files=files, headers=headers)
        return res.json()["IpfsHash"]
    """
    logger.info("[IPFS MOCK] Uploading %d bytes to IPFS", len(content))

    # Derive a deterministic fake CID from content hash (mimics IPFS behaviour)
    sha256 = hashlib.sha256(content).hexdigest()
    fake_cid = "Qm" + sha256[:44]  # IPFS CIDv0 starts with "Qm" and is 46 chars

    logger.info("[IPFS MOCK] Generated CID: %s", fake_cid)
    return fake_cid
