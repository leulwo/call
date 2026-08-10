"""ExamPaper Refine - Application configuration."""

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ── Gemini AI ──────────────────────────────────────────────────────────
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key",
    )
    gemini_model: str = Field(
        default="gemini-2.0-flash-lite",
        description="Gemini model for analysis and rewriting",
    )

    # ── Paths ──────────────────────────────────────────────────────────────
    data_dir: str = Field(
        default="../data",
        description="Root directory for runtime data (originals, derivatives, DB)",
    )

    # ── Upload limits ──────────────────────────────────────────────────────
    max_file_size_mb: int = Field(default=50, description="Max upload size in MB")
    max_pages: int = Field(default=200, description="Max pages per document")
    allowed_extensions: set[str] = Field(
        default={".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"},
        description="Allowed file extensions for upload",
    )

    # ── Server ─────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    log_level: str = Field(default="INFO", description="Logging level")

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        description="Database URL. Auto-generated from data_dir if empty.",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def resolved_data_dir(self) -> Path:
        """Resolve data directory to an absolute path."""
        path = Path(self.data_dir)
        if not path.is_absolute():
            # Relative to the backend/ directory
            path = Path(__file__).parent.parent / self.data_dir
        return path.resolve()

    @property
    def originals_dir(self) -> Path:
        return self.resolved_data_dir / "originals"

    @property
    def derivatives_dir(self) -> Path:
        return self.resolved_data_dir / "derivatives"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.resolved_data_dir / "exampaper.db"
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Create required data directories if they don't exist."""
        self.resolved_data_dir.mkdir(parents=True, exist_ok=True)
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.derivatives_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
