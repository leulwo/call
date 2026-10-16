import pytest
import pytest_asyncio
from app.database import init_db


@pytest_asyncio.fixture(autouse=True, scope="function")
async def setup_test_db():
    """Ensure database schema is initialized before running tests."""
    await init_db()
