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

## Train AI Models (inside Docker)

After containers are up, run training in the backend container:

```bash
docker compose exec backend python -m ai_models.train_all_models --epochs 8 --batch-size 16
```

Dataset folders expected on host:

```text
ai_models/data/
  train/
    authentic/
    forged/
  test/
    authentic/
    forged/
```

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
