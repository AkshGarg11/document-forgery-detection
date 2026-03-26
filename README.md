# Document Forgery Detection System

Docker-first setup for document forgery detection with blockchain verification.

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

- Blockchain RPC: `8545` (from `WEB3_PROVIDER_URI`)
- IPFS API: `5001` (from `IPFS_API_URL`)

Important:

- Current `docker-compose.yml` starts backend + frontend only.
- Blockchain and IPFS are referenced endpoints but are not started as compose services in the current setup.
- Backend currently supports mocked blockchain/IPFS flow for local development.

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
