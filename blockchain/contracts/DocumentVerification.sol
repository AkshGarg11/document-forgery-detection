// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract DocumentVerification {
    struct DocumentRecord {
        address issuer;
        uint256 timestamp;
        bytes32 textHash;
        bytes32 previousHash;  // Chain of custody: link to prior version
        string version;        // Version identifier (e.g., "1.0", "2.0")
        string perceptualHash; // Perceptual (pHash) for visual similarity matching (64 hex chars)
        bool exists;
        bool revoked;
    }

    mapping(bytes32 => DocumentRecord) private documents;
    mapping(address => bool) public authorizedIssuers;
    address public owner;

    event IssuerUpdated(address indexed issuer, bool authorized);
    event DocumentIssued(bytes32 indexed fileHash, bytes32 indexed textHash, address indexed issuer, uint256 timestamp);
    event DocumentRevoked(bytes32 indexed fileHash, address indexed issuer, uint256 timestamp);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAuthorizedIssuer() {
        require(authorizedIssuers[msg.sender], "Not an authorized issuer");
        _;
    }

    constructor() {
        owner = msg.sender;
        authorizedIssuers[msg.sender] = true;
        emit IssuerUpdated(msg.sender, true);
    }

    function setIssuer(address issuer, bool isAuthorized) external onlyOwner {
        require(issuer != address(0), "Invalid issuer");
        authorizedIssuers[issuer] = isAuthorized;
        emit IssuerUpdated(issuer, isAuthorized);
    }

    function issueDocument(
        bytes32 fileHash,
        bytes32 textHash
    ) external onlyAuthorizedIssuer {
        _issueDocumentWithVersion(fileHash, textHash, bytes32(0), "", "");
    }

    function issueDocumentWithVersion(
        bytes32 fileHash,
        bytes32 textHash,
        bytes32 previousHash,
        string calldata version,
        string calldata perceptualHash
    ) external onlyAuthorizedIssuer {
        _issueDocumentWithVersion(fileHash, textHash, previousHash, version, perceptualHash);
    }

    function _issueDocumentWithVersion(
        bytes32 fileHash,
        bytes32 textHash,
        bytes32 previousHash,
        string memory version,
        string memory perceptualHash
    ) internal {
        require(fileHash != bytes32(0), "Invalid file hash");
        require(textHash != bytes32(0), "Invalid text hash");
        require(!documents[fileHash].exists, "Document already issued");

        documents[fileHash] = DocumentRecord({
            issuer: msg.sender,
            timestamp: block.timestamp,
            textHash: textHash,
            previousHash: previousHash,
            version: version,
            perceptualHash: perceptualHash,
            exists: true,
            revoked: false
        });

        emit DocumentIssued(fileHash, textHash, msg.sender, block.timestamp);
    }

    function verifyDocument(bytes32 fileHash)
        external
        view
        returns (bool isValid, uint256 timestamp, address issuer, bool revoked)
    {
        DocumentRecord memory record = documents[fileHash];
        if (!record.exists) {
            return (false, 0, address(0), false);
        }
        if (record.revoked) {
            return (false, record.timestamp, record.issuer, true);
        }
        return (true, record.timestamp, record.issuer, false);
    }

    function revokeDocument(bytes32 fileHash) external onlyAuthorizedIssuer {
        DocumentRecord storage record = documents[fileHash];
        require(record.exists, "Document does not exist");
        require(record.issuer == msg.sender, "Only original issuer can revoke");
        require(!record.revoked, "Document already revoked");

        record.revoked = true;
        emit DocumentRevoked(fileHash, msg.sender, block.timestamp);
    }

    function getDocument(bytes32 fileHash)
        external
        view
        returns (address issuer, uint256 timestamp, bytes32 textHash, bool exists, bool revoked)
    {
        DocumentRecord memory record = documents[fileHash];
        return (record.issuer, record.timestamp, record.textHash, record.exists, record.revoked);
    }

    function getDocumentFull(bytes32 fileHash)
        external
        view
        returns (
            address issuer,
            uint256 timestamp,
            bytes32 textHash,
            bytes32 previousHash,
            string memory version,
            string memory perceptualHash,
            bool exists,
            bool revoked
        )
    {
        DocumentRecord memory record = documents[fileHash];
        return (
            record.issuer,
            record.timestamp,
            record.textHash,
            record.previousHash,
            record.version,
            record.perceptualHash,
            record.exists,
            record.revoked
        );
    }
}
