# Blockchain Module

This module contains the Solidity contract and tests for document hash anchoring.

## Contract

- [contracts/DocumentVerification.sol](contracts/DocumentVerification.sol)
  - `issueDocument(bytes32 fileHash, bytes32 textHash)`
  - `verifyDocument(bytes32 fileHash)`
  - `revokeDocument(bytes32 fileHash)`

## Commands

From [blockchain](.):

```bash
npm install
npm run compile
npm test
```

## Ganache App network

Expected defaults:

- RPC URL: `http://127.0.0.1:7545`
- Chain ID: `5777`

Set environment variables in project root `.env`:

- `GANACHE_RPC_URL`
- `WEB3_PROVIDER_URI`
- `CHAIN_ID`
- `CONTRACT_ADDRESS`

## Deployment note

Some Ganache App setups do not expose wallet RPC methods required by Hardhat viem deployment.
If `npm run deploy:ganache` fails with wallet RPC method errors, deploy using:

```bash
python blockchain/scripts/deploy_with_web3.py
```

Then set `CONTRACT_ADDRESS` in root `.env`.
