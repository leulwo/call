"""ExamPaper Refine - FastAPI Application."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import admin, library, metadata, papers, process, upload
from services.cleanup_service import stale_process_cleanup_loop
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

    # Initialize database tables — retry on transient pooler failures instead
    # of crash-looping the whole API (Supabase pooler connects can take 10s+).
    for attempt in range(4):
        try:
            await init_db()
            break
        except Exception as exc:
            logger.warning(f"init_db attempt {attempt + 1}/4 failed: {exc}")
            if attempt == 3:
                logger.error("Database unreachable at startup; continuing without init_db (tables already exist).")
                break
            await asyncio.sleep(5)

    # Start the stale-process sweep (fails processes stuck longer than
    # stale_process_days; archive data is never deleted)
    cleanup_task = asyncio.create_task(stale_process_cleanup_loop())

    logger.info("Startup complete.")
    yield
    logger.info("Shutting down...")
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task


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

# Configure CORS with explicit allowed origins
origins = [
    origin.strip()
    for origin in get_settings().cors_origins.split(",")
    if origin.strip()
] or ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(metadata.router, prefix="/api", tags=["Metadata"])
app.include_router(papers.router, prefix="/api", tags=["Papers"])
app.include_router(process.router, prefix="/api", tags=["Process"])
app.include_router(library.router, prefix="/api", tags=["Library"])
app.include_router(admin.router, prefix="/api", tags=["Admin"])


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
