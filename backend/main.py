"""
Document Forgery Detection System - FastAPI Backend
Entry point for the backend service.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.upload import router as upload_router
from routes.verify import router as verify_router
from routes.revoke import router as revoke_router

app = FastAPI(
    title="Document Forgery Detection API",
    description="AI-powered document forgery detection.",
    version="1.0.0",
)

# CORS — allow frontend dev server and production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(upload_router, prefix="/api/v1", tags=["Upload"])
app.include_router(verify_router, prefix="/api/v1", tags=["Blockchain"])
app.include_router(revoke_router, prefix="/api/v1", tags=["Blockchain"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "document-forgery-detection-backend"}
