"""ExamPaper Refine - Database setup."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


def _create_engine():
    """Create the async SQLAlchemy engine."""
    settings = get_settings()
    db_url = settings.resolved_database_url
    kwargs = {
        "echo": settings.log_level == "DEBUG",
        "future": True,
    }
    # Apply connection pooling for PostgreSQL
    if "postgresql" in db_url:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True

    return create_async_engine(db_url, **kwargs)



engine = _create_engine()

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Keep the local SQLite database compatible with the evolving metadata
        # model without requiring a manual migration for the development app.
        if conn.dialect.name == "sqlite":
            columns = await conn.execute(text("PRAGMA table_info(exam_papers)"))
            existing_columns = {row[1] for row in columns.fetchall()}
            if "study_year" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN study_year VARCHAR(50)"))
            if "description" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN description TEXT"))
            if "university_type" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN university_type VARCHAR(50)"))
            if "metadata_json" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN metadata_json TEXT"))
            if "extracted_text" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN extracted_text TEXT"))
            if "save_count" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN save_count INTEGER NOT NULL DEFAULT 0"))
            if "like_count" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0"))
            if "uploader_id" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN uploader_id VARCHAR(36)"))
            if "uploader_name" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN uploader_name VARCHAR(120)"))
            if "email" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN email VARCHAR(255)"))
            if "failed_stage" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN failed_stage VARCHAR(50)"))
            if "pipeline_version" not in existing_columns:
                await conn.execute(text("ALTER TABLE exam_papers ADD COLUMN pipeline_version VARCHAR(50) DEFAULT '0.1.0'"))

            # Normalize any legacy uppercase enum values in development database
            await conn.execute(text("UPDATE exam_papers SET document_type = lower(document_type) WHERE document_type IS NOT NULL"))
            await conn.execute(text("UPDATE exam_papers SET status = lower(status) WHERE status IS NOT NULL"))
            await conn.execute(text("UPDATE processing_logs SET stage = lower(stage) WHERE stage IS NOT NULL"))
            await conn.execute(text("UPDATE processing_logs SET status = lower(status) WHERE status IS NOT NULL"))


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
