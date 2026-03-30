# Document Forgery Detection System

Docker-first setup for document forgery detection.

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- No local Python or Node installation is required.

## Quick Start

1. Create environment file:

```bash
copy .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

2. Build and start services:

```bash
docker compose up --build
```

3. Open applications:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

## Ports and Services

When you run `docker compose up`, these containers start:

- Frontend container (`forgeguard-frontend`): host `${FRONTEND_PORT}` -> container `80` (default `3000 -> 80`)
- Backend container (`forgeguard-backend`): host `${BACKEND_PORT}` -> container `8000` (default `8000 -> 8000`)

Ports defined in `.env.example` for related infrastructure:

- IPFS API: `5001` (from `IPFS_API_URL`)

Important:

- Current `docker-compose.yml` starts backend + frontend only.
- IPFS is referenced as an endpoint but is not started as a compose service in the current setup.
- Backend currently supports mocked IPFS flow for local development.

## AI Model Training and Evaluation

Use these commands from project root (`d:\document-forgery-detection`).

### Dataset Layout

Primary dataset expected by the pipeline:

```text
ai_models/data_forgery_type/
  train/
    authentic/
    copy_move/
    splicing/
    removal/
    object_insertion/
    ai_generated_text_based/
  test/
    authentic/
    copy_move/
    splicing/
    removal/
    object_insertion/
    ai_generated_text_based/
```

### Train (Docker)

Run forgery-type model training (auto-resume from checkpoint):

```bash
docker compose exec backend python -m ai_models.train_all_models --epochs 12 --batch-size 16
```

Resume from existing checkpoints automatically:

```bash
docker compose exec backend python -m ai_models.train_all_models --epochs 12 --batch-size 16
```

Start fresh by deleting checkpoints first:

```bash
docker compose exec backend sh -c "rm -f ai_models/models/forgery_type_cnn.pt"
docker compose exec backend python -m ai_models.train_all_models --epochs 12 --batch-size 16
```

### Evaluate (Docker)

Evaluate both tasks (binary + forgery type) and write a JSON report:

```bash
docker compose exec backend python -m ai_models.evaluate_models --data-root ai_models/data_forgery_type --out ai_models/models/evaluation_latest.json
```

### Train (Local Python)

If you want to run without Docker:

```bash
python -m ai_models.train_all_models --epochs 12 --batch-size 16
```

### Evaluate (Local Python)

```bash
python -m ai_models.evaluate_models --data-root ai_models/data_forgery_type --out ai_models/models/evaluation_latest.json
```

### Useful Flags

- `--forgery-type-backbone resnet18|efficientnet_b0`: choose CNN backbone.
- `--forgery-type-data-root <path>`: custom subtype dataset location.
- `--num-workers <int>`: DataLoader workers.
- `--lr <float>`: learning rate.

## Stop Services

```bash
docker compose down
```

## Full Cleanup (remove all project docker data)

```bash
docker compose down --rmi all --volumes --remove-orphans
```

This removes containers, images, networks, and volumes created by this project.

## Notes

- Backend image installs both backend and AI dependencies.
- Frontend uses multi-stage Docker build (Node build + Nginx runtime).
- Healthcheck is enabled for backend and frontend depends on backend health.

## Blockchain Workflow (Ganache App + Hardhat + Backend)

This repository now includes a blockchain module in [blockchain](blockchain) and backend integration for:

- Issue (anchor) document hash on-chain during upload
- Verify hash via API
- Revoke hash via API

### 1) Start Ganache App

1. Open Ganache App.
2. Start a local workspace.
3. Ensure RPC URL is available (default is usually `http://127.0.0.1:7545`).
4. Ensure `Chain ID` is `5777` in Ganache settings.

### 2) Compile and test contract

From [blockchain](blockchain):

```bash
npm install
npm test
```

### 3) Deploy contract

Deployment via `hardhat viem` may require wallet methods not exposed by some Ganache App configurations.
Use this reliable Web3 deployment from repo root:

```bash
python blockchain/scripts/deploy_with_web3.py
```

Copy the printed contract address.

### 4) Configure environment

Set these in [.env](.env):

- `BLOCKCHAIN_ENABLED=true`
- `GANACHE_RPC_URL=http://127.0.0.1:7545`
- `WEB3_PROVIDER_URI=http://127.0.0.1:7545`
- `CHAIN_ID=5777`
- `CONTRACT_ADDRESS=<deployed_address>`

`DEPLOYER_PRIVATE_KEY` is optional for Ganache App if unlocked accounts are available.

### 5) Backend API behavior

- Upload endpoint [backend/routes/upload.py](backend/routes/upload.py):
  - computes file hash
  - runs AI pipeline
  - uploads to IPFS mock
  - attempts on-chain issue and returns:
    - `tx_hash`
    - `anchor_status`
    - `anchor_error` (only on failure)

- Verify endpoint [backend/routes/verify.py](backend/routes/verify.py):
  - `POST /api/v1/verify`
  - body: `{ "file_hash": "<64 hex>" }`

- Revoke endpoint [backend/routes/revoke.py](backend/routes/revoke.py):
  - `POST /api/v1/revoke`
  - body: `{ "file_hash": "<64 hex>" }`

### 6) Frontend behavior

[frontend/src/components/ResultCard.jsx](frontend/src/components/ResultCard.jsx) now shows:

- document hash
- IPFS CID
- anchor status
- blockchain transaction hash
- anchor error (if any)
