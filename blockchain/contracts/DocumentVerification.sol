// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title DocumentVerification
 * @notice Stores tamper-proof document verification records on-chain.
 * @dev Each document is keyed by its SHA-256 hash. Records are immutable once written.
 */
contract DocumentVerification {

    // ── Structs ──────────────────────────────────────────────────────────────

    struct VerificationRecord {
        string  documentHash;   // SHA-256 hex string of the original document
        string  ipfsCid;        // IPFS Content Identifier of the stored document
        string  result;         // "Authentic" | "Suspicious" | "Forged"
        uint256 timestamp;      // Block timestamp of submission
        address submitter;      // Address that submitted the verification
    }

    // ── State ─────────────────────────────────────────────────────────────────

    /// Mapping from document hash → verification record
    mapping(string => VerificationRecord) private records;

    /// Ordered list of submitted document hashes (for enumeration)
    string[] private documentHashes;

    // ── Events ────────────────────────────────────────────────────────────────

    event DocumentVerified(
        string  indexed documentHash,
        string  ipfsCid,
        string  result,
        uint256 timestamp,
        address indexed submitter
    );

    // ── Errors ────────────────────────────────────────────────────────────────

    error AlreadyVerified(string documentHash);
    error InvalidHash();
    error InvalidResult();

    // ── Modifiers ─────────────────────────────────────────────────────────────

    modifier onlyValidResult(string memory result) {
        bytes32 r = keccak256(abi.encodePacked(result));
        require(
            r == keccak256("Authentic") ||
            r == keccak256("Suspicious") ||
            r == keccak256("Forged"),
            "Invalid result value"
        );
        _;
    }

    // ── Write Functions ───────────────────────────────────────────────────────

    /**
     * @notice Store a new verification record for a document.
     * @param documentHash  SHA-256 hash of the document (hex string, 64 chars).
     * @param ipfsCid       IPFS CID where the document is stored.
     * @param result        Classification: "Authentic", "Suspicious", or "Forged".
     */
    function storeVerification(
        string calldata documentHash,
        string calldata ipfsCid,
        string calldata result
    ) external onlyValidResult(result) {
        if (bytes(documentHash).length != 64) revert InvalidHash();
        if (bytes(records[documentHash].documentHash).length != 0) {
            revert AlreadyVerified(documentHash);
        }

        records[documentHash] = VerificationRecord({
            documentHash: documentHash,
            ipfsCid:      ipfsCid,
            result:       result,
            timestamp:    block.timestamp,
            submitter:    msg.sender
        });

        documentHashes.push(documentHash);

        emit DocumentVerified(documentHash, ipfsCid, result, block.timestamp, msg.sender);
    }

    // ── Read Functions ────────────────────────────────────────────────────────

    /**
     * @notice Retrieve the verification record for a given document hash.
     * @param documentHash SHA-256 hash of the document.
     */
    function getVerification(string calldata documentHash)
        external
        view
        returns (VerificationRecord memory)
    {
        return records[documentHash];
    }

    /**
     * @notice Check whether a document has already been verified.
     */
    function isVerified(string calldata documentHash) external view returns (bool) {
        return bytes(records[documentHash].documentHash).length != 0;
    }

    /**
     * @notice Return total number of verified documents.
     */
    function totalVerified() external view returns (uint256) {
        return documentHashes.length;
    }
}
