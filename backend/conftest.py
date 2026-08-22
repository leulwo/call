import sys
import os

# Add backend directory to python path for pytest
sys.path.insert(0, os.path.dirname(__file__))

# Tests must never connect to a developer's cloud database or enqueue real
# worker jobs. The application falls back to the local SQLite test database.
os.environ["DATABASE_URL"] = ""
os.environ["AUTO_REPROCESS_NEEDS_REVIEW"] = "false"
