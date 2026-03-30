"""
Document Forgery Detection System - FastAPI Backend
Entry point for the backend service.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from routes.verify import router as verify_router
from routes.revoke import router as revoke_router
from routes.signature_verification import router as signature_verification_router
from routes.combined_detection import router as combined_detection_router

app = FastAPI(
    title="Document Forgery Detection API",
    description="AI-powered document forgery detection.",
    version="1.0.0",
)


def _get_allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:5173", "http://localhost:3000"]

# CORS — allow frontend dev server and production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(verify_router, prefix="/api/v1", tags=["Blockchain"])
app.include_router(revoke_router, prefix="/api/v1", tags=["Blockchain"])
app.include_router(
    signature_verification_router,
    prefix="/api/v1",
    tags=["Signature Verification"],
)
app.include_router(
    combined_detection_router,
    prefix="/api/v1",
    tags=["Combined Detection"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "document-forgery-detection-backend"}


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STATIC_DIST_DIR = _PROJECT_ROOT / "frontend" / "dist"

if _STATIC_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIST_DIR / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_index():
        return FileResponse(str(_STATIC_DIST_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if (
            full_path.startswith("api/")
            or full_path.startswith("health")
            or full_path.startswith("docs")
            or full_path.startswith("redoc")
            or full_path.startswith("openapi.json")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = _STATIC_DIST_DIR / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_STATIC_DIST_DIR / "index.html"))
