"""
ipfs/ipfs_client.py
Standalone IPFS client module (importable independently of the backend).
"""

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

IPFS_API_URL = os.getenv("IPFS_API_URL", "http://localhost:5001")


def upload_file(file_bytes: bytes, filename: str = "document") -> str:
    """
    Upload a file to IPFS and return its Content Identifier (CID).

    Args:
        file_bytes: Raw bytes of the file to upload.
        filename:   Optional original filename (used in metadata).

    Returns:
        IPFS CID string.

    ---
    REAL IMPLEMENTATION with ipfshttpclient:

        import ipfshttpclient
        client = ipfshttpclient.connect(IPFS_API_URL)
        result = client.add_bytes(file_bytes)
        client.close()
        return result

    REAL IMPLEMENTATION with requests (Pinata):

        import requests
        url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
        headers = {
            "pinata_api_key": os.getenv("PINATA_API_KEY"),
            "pinata_secret_api_key": os.getenv("PINATA_SECRET"),
        }
        files = {"file": (filename, file_bytes)}
        response = requests.post(url, files=files, headers=headers)
        response.raise_for_status()
        return response.json()["IpfsHash"]
    """
    logger.info("[IPFS CLIENT MOCK] Uploading '%s' (%d bytes)", filename, len(file_bytes))

    # Deterministic mock CID
    digest = hashlib.sha256(file_bytes).hexdigest()
    cid = "Qm" + digest[:44]

    logger.info("[IPFS CLIENT MOCK] CID: %s", cid)
    return cid
