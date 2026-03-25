"""
utils/hashing.py
Cryptographic utilities for generating document fingerprints.
"""

import hashlib


def compute_hash(content: bytes, algorithm: str = "sha256") -> str:
    """
    Compute a hex digest of the given bytes using the specified algorithm.

    Args:
        content:   Raw file bytes.
        algorithm: Hash algorithm name (default: sha256).

    Returns:
        Lowercase hex string of the digest.

    Raises:
        ValueError: If the algorithm is not supported.
    """
    try:
        h = hashlib.new(algorithm)
    except ValueError as exc:
        raise ValueError(f"Unsupported hash algorithm: '{algorithm}'") from exc

    h.update(content)
    return h.hexdigest()
