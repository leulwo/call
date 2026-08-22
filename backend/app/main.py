"""ExamPaper Refine - FastAPI Application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import metadata, papers, process, upload
from slowapi.errors import RateLimitExceeded

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the FastAPI application."""
    settings = get_settings()
    logger.info("Initializing ExamPaper Refine...")

    # Ensure directories exist
    settings.ensure_directories()

    # Initialize database tables
    await init_db()

    logger.info("Startup complete.")
    yield
    logger.info("Shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title="ExamPaper Refine API",
    description="API for uploading and refining exam papers.",
    version="0.1.0",
    lifespan=lifespan,
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(metadata.router, prefix="/api", tags=["Metadata"])
app.include_router(papers.router, prefix="/api", tags=["Papers"])
app.include_router(process.router, prefix="/api", tags=["Process"])


@app.get("/")
async def root():
    """Root entry point with documentation links."""
    return {
        "name": "ExamPaper Refine API",
        "version": app.version,
        "docs_url": "/docs",
        "health_url": "/health",
        "status": "online",
    }


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "version": app.version}
