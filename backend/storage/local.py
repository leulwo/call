"""ExamPaper Refine - Local storage adapter.

Provides a simple S3-like interface for local filesystem storage.
This makes it easy to migrate to actual MinIO/S3 later.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Basic filename sanitization."""
    keep = (" ", ".", "_", "-")
    return "".join(c for c in name if c.isalnum() or c in keep).strip()


class LocalStorage:
    """Local filesystem storage adapter."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.settings.ensure_directories()

    def store_original(self, file_obj: BinaryIO, filename: str, sha256: str) -> str:
        """Store an uploaded original file.

        Args:
            file_obj: The uploaded file stream
            filename: Original filename
            sha256: Pre-computed SHA-256 of the file

        Returns:
            Relative path/key of the stored file
        """
        ext = Path(filename).suffix.lower()
        safe_name = f"{sha256[:12]}{ext}"
        
        # We store originals partitioned by first 2 chars of hash
        partition_dir = self.settings.originals_dir / sha256[:2]
        partition_dir.mkdir(exist_ok=True)
        
        target_path = partition_dir / safe_name
        
        if not target_path.exists():
            with open(target_path, "wb") as f:
                shutil.copyfileobj(file_obj, f)
            logger.info(f"Stored original: {target_path}")
        else:
            logger.info(f"Original already exists: {target_path}")

        # Return a relative 'key' for database storage
        return f"{sha256[:2]}/{safe_name}"

    def store_derivative(
        self,
        source_path: Path | str,
        paper_id: str,
        version: int,
        derivative_type: str,
        extension: str,
    ) -> str:
        """Store a derived file (rewritten PDF, source code, etc)."""
        partition_dir = self.settings.derivatives_dir / paper_id[:2]
        partition_dir.mkdir(exist_ok=True)
        
        safe_type = _sanitize_filename(derivative_type)
        target_name = f"{paper_id}_v{version}_{safe_type}{extension}"
        target_path = partition_dir / target_name
        
        if isinstance(source_path, str):
            source_path = Path(source_path)
            
        shutil.copy2(str(source_path), str(target_path))
        logger.info(f"Stored derivative: {target_path}")
        
        return f"{paper_id[:2]}/{target_name}"

    def get_original_path(self, key: str) -> Path:
        """Get the absolute filesystem path for an original file key."""
        return self.settings.originals_dir / key

    def get_derivative_path(self, key: str) -> Path:
        """Get the absolute filesystem path for a derivative file key."""
        return self.settings.derivatives_dir / key


# Global instance
storage = LocalStorage()
