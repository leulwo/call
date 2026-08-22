"""ExamPaper Refine - Application configuration."""

import os
from pathlib import Path
from functools import lru_cache
from urllib.parse import quote, urlsplit, urlunsplit

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
        description="Database URL (PostgreSQL asyncpg or SQLite). Auto-generated if empty.",
    )
    supabase_pooler_host: str = Field(
        default="",
        description="Optional Supabase pooler host for environments without direct DB DNS/IPv6.",
    )
    supabase_project_ref: str = Field(
        default="",
        description="Supabase project ref used by the pooled PostgreSQL username.",
    )

    # ── Redis & Celery ─────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis broker URL for Celery task queue",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        description="Redis result backend URL for Celery",
    )
    auto_reprocess_needs_review: bool = Field(
        default=True,
        description="Retry needs-review papers once when a worker starts",
    )

    # ── Rate Limiting (slowapi) ────────────────────────────────────────────
    rate_limit_upload: str = Field(
        default="5/hour",
        description="Upload rate limit per IP",
    )
    rate_limit_general: str = Field(
        default="60/minute",
        description="General API rate limit per IP",
    )
    rate_limit_reprocess: str = Field(
        default="10/hour",
        description="Reprocess rate limit per IP",
    )

    # ── Email Notifications (SMTP) ─────────────────────────────────────────
    smtp_host: str = Field(default="", description="SMTP host server")
    smtp_port: int = Field(default=587, description="SMTP port")
    smtp_user: str = Field(default="", description="SMTP username")
    smtp_pass: str = Field(default="", description="SMTP password")
    smtp_from: str = Field(
        default="noreply@exampaper.org", description="Sender email address"
    )
    smtp_tls: bool = Field(default=True, description="Use TLS/STARTTLS for SMTP")

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
            database_url = self.database_url.strip()
            # Supabase exposes a standard PostgreSQL URI. SQLAlchemy's
            # async engine needs the asyncpg driver explicitly, so accept
            # both forms and normalize them at the application boundary.
            if database_url.startswith("postgres://"):
                database_url = "postgresql+asyncpg://" + database_url[len("postgres://"):]
            elif database_url.startswith("postgresql://"):
                database_url = "postgresql+asyncpg://" + database_url[len("postgresql://"):]

            # Supabase's direct `db.<project>.supabase.co` endpoint may be
            # unavailable on machines without IPv6/direct-DNS access. When a
            # pooler host is configured, transparently use the session pooler
            # while keeping the password from the user's DATABASE_URL.
            if self.supabase_pooler_host:
                parsed = urlsplit(database_url)
                direct_host = parsed.hostname or ""
                project_ref = self.supabase_project_ref or (
                    direct_host.removeprefix("db.").removesuffix(".supabase.co")
                    if direct_host.startswith("db.") and direct_host.endswith(".supabase.co")
                    else ""
                )
                if project_ref and parsed.username and parsed.password:
                    pooler_user = parsed.username
                    if pooler_user == "postgres":
                        pooler_user = f"postgres.{project_ref}"
                    userinfo = f"{quote(pooler_user, safe='')}:{quote(parsed.password, safe='')}"
                    database_url = urlunsplit(
                        (
                            "postgresql+asyncpg",
                            f"{userinfo}@{self.supabase_pooler_host}:5432",
                            parsed.path or "/postgres",
                            parsed.query,
                            parsed.fragment,
                        )
                    )
            return database_url
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
