# Blockchain Rebuild Workflow and Codebase Guide

## Why this document exists

This guide explains:

- The current workflow in your project (after blockchain removal)
- How blockchain should be added back cleanly from scratch
- Recommended folder and file structure
- The role and importance of each key file
- Security, testing, and rollout steps

This is written to be practical, so you can implement in phases without breaking the app.

## Current project state

Right now your app runs as:

- Frontend uploads a file
- Backend runs AI analysis
- Backend computes SHA-256 file hash
- Backend returns AI result, confidence, module scores, and a mock IPFS CID

There is currently no on-chain write or on-chain verification in runtime code.

## Current high-level architecture

### Frontend

- frontend/src/pages/Home.jsx
  - Upload UI and submit flow
  - Calls frontend service layer
- frontend/src/services/api.js
  - Sends file to backend upload endpoint
- frontend/src/components/ResultCard.jsx
  - Displays analysis result, confidence, module scores, hash, CID

### Backend

- backend/main.py
  - FastAPI app entrypoint and router registration
- backend/routes/upload.py
  - Main API endpoint for upload
  - Orchestrates hashing, AI analysis, and IPFS mock call
- backend/services/ai_service.py
  - AI orchestration and explanation building
- backend/services/ipfs_service.py
  - Mock IPFS uploader (deterministic CID)
- backend/utils/hashing.py
  - SHA hashing helpers

### Shared

- shared/schemas/analysis_schema.py
  - Reusable Pydantic schema models (not tightly wired everywhere yet)

### IPFS helper module

- ipfs/ipfs_client.py
  - Standalone mock IPFS client, useful if separated later into another service

## Target architecture when re-adding blockchain

Add blockchain as a separate concern, not mixed into AI logic.

Design rule:

- AI decides authenticity
- Blockchain anchors integrity evidence
- Verification endpoint checks existence and status

### Target flows

#### 1) Issue or Anchor flow

1. User uploads file
2. Backend computes file hash
3. Backend optionally computes normalized text hash (if you re-enable text-based anchoring)
4. Backend stores file in IPFS (real or mocked)
5. Backend sends transaction to smart contract issue function
6. Backend returns AI output + CID + tx hash + anchor status

#### 2) Verify flow

1. User submits file (or hash)
2. Backend computes hash
3. Backend queries contract verify function
4. Backend returns exists or not, issuer, timestamp, revoked or active
5. If mismatch logic is enabled, return tamper signal and confidence

#### 3) Revoke flow

1. Authorized issuer calls revoke with file hash
2. Contract marks record revoked
3. Verify flow returns revoked status

## Recommended new folder structure

Create a fresh module instead of reusing old deleted code directly.

- blockchain/
  - contracts/
    - DocumentVerification.sol
  - scripts/
    - deploy.js
  - hardhat.config.js
  - package.json
- backend/
  - services/
    - blockchain_service.py
    - document_integrity_service.py
  - routes/
    - verify.py
    - revoke.py
  - schemas/
    - blockchain_schema.py

Keep upload route minimal and delegate all blockchain logic to service files.

## Smart contract design recommendation

Use Solidity 0.8.x with strict role control.

Suggested fields:

- fileHash (bytes32)
- textHash (bytes32, optional compatibility)
- issuer address
- timestamp
- exists
- revoked

Suggested functions:

- issueDocument(bytes32 fileHash, bytes32 textHash)
- verifyDocument(bytes32 fileHash)
- revokeDocument(bytes32 fileHash)
- setIssuer(address issuer, bool isAuthorized)

Security controls:

- only owner can authorize issuers
- only authorized issuer can issue
- only original issuer (or owner, if desired) can revoke
- reject duplicate issue on same hash

## Backend implementation plan

### 1) Add blockchain config

Use backend .env for:

- WEB3_PROVIDER_URI
- CONTRACT_ADDRESS
- CHAIN_ID
- DEPLOYER_PRIVATE_KEY
- CONTRACT_ABI_PATH (optional)

### 2) Add blockchain service

backend/services/blockchain_service.py should expose:

- issue_document(file_hash_hex, text_hash_hex)
- verify_document(file_hash_hex)
- revoke_document(file_hash_hex)

It should only do:

- Web3 connection
- ABI loading
- tx build/sign/send
- read call mapping into simple dict output

### 3) Add dedicated API routes

- backend/routes/verify.py
  - Accept file upload or hash
  - Return verify response from contract
- backend/routes/revoke.py
  - Accept hash
  - Revoke via blockchain service

### 4) Keep upload route focused

- backend/routes/upload.py should:
  - Analyze file
  - Hash file
  - Upload to IPFS
  - Optionally call issue_document if anchor_enabled

This keeps runtime stable if blockchain node is down.

## Frontend integration recommendation

### Add new API methods

frontend/src/services/api.js:

- verifyDocument(file)
- revokeDocument(fileHash)

### Add UI sections

- Verification panel
- Revoke action for admin/issuer mode
- Status badges:
  - Anchored
  - Not Found
  - Revoked

### Display fields

- tx hash
- block timestamp
- issuer address
- on-chain status

## File importance guide

### Most critical backend files

- backend/routes/upload.py
  - Core data path for analysis
- backend/services/ai_service.py
  - AI orchestration and explainability
- backend/services/blockchain_service.py (future)
  - Chain I/O boundary, keep all Web3 complexity here
- backend/utils/hashing.py
  - Integrity source of truth for hashing

### Most critical frontend files

- frontend/src/services/api.js
  - Single source of API contracts for UI
- frontend/src/pages/Home.jsx
  - User workflow and orchestration
- frontend/src/components/ResultCard.jsx
  - User trust and interpretability layer

### Important shared files

- shared/schemas/analysis_schema.py
  - Contract between services and frontend expectations

## Development workflow to reintroduce blockchain safely

### Phase 1

- Recreate blockchain folder
- Compile contract locally
- Deploy to Ganache
- Save contract address and ABI

### Phase 2

- Implement blockchain_service.py
- Add verify route first (read only)
- Confirm read path works

### Phase 3

- Add issue path from upload
- Add feature flag: ENABLE_BLOCKCHAIN_ANCHORING=true or false
- Keep graceful fallback if tx fails

### Phase 4

- Add revoke route and role checks
- Add frontend verify and revoke views

### Phase 5

- Add tests and logging hardening

## Environment strategy

Use two environments:

- Local
  - Ganache
  - unlocked accounts or local private key
- Testnet
  - Sepolia RPC
  - dedicated issuer wallet

Never reuse production keys in local env.

## Security checklist

- Never log private keys
- Validate all hashes are 64-char hex before chain calls
- Add timeout and retries for RPC calls
- Handle revert messages and map to clean API errors
- Rate-limit issue and revoke endpoints
- Add auth for issuer-only APIs

## Testing checklist

### Unit

- Hash normalization and validation
- Blockchain service conversion and error mapping
- Route request and response validation

### Integration

- Issue then verify same hash
- Verify non-existent hash
- Revoke then verify returns revoked
- Upload endpoint with chain on and chain off

### Frontend

- Upload and render success
- Verify status display
- Error display for RPC down

## Suggested first implementation tasks

1. Recreate blockchain module with Hardhat and a minimal contract
2. Add backend blockchain_service.py with issue and verify
3. Add verify endpoint before wiring upload anchoring
4. Add feature flag for safe rollout
5. Update frontend only after API contracts are stable

## Notes for your current codebase

- You already have strong upload and AI orchestration structure.
- Shared schemas exist and can be expanded for verify and revoke responses.
- IPFS is currently mock-based; you can switch to real Pinata or local IPFS after blockchain path is stable.

## Next action you can ask me to do

If you want, I can now generate the fresh blockchain skeleton in code directly (contract, hardhat config, deploy script, backend service stubs, and verify route) in one controlled pass.
