import asyncio
import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.dependencies.auth import get_current_user, AuthUser


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="00000000-0000-0000-0000-000000000001",
        email="student@example.com",
        name="Test Student",
        is_admin=True,
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_health_and_root_endpoints():
    """Test health check and root landing endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        root_res = await ac.get("/")
        assert root_res.status_code == 200
        assert root_res.json()["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_nonblocking_upload_and_polling():
    """Test that uploading returns HTTP 202 immediately with polling URL."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        dummy_content = b"%PDF-1.4 test dummy pdf content for unit test"
        files = {"file": ("unit_test_math_exam.pdf", io.BytesIO(dummy_content), "application/pdf")}
        data = {
            "title": "2026 MATH101 Calculus I examination",
            "description": "A unit test document for the async upload and processing flow.",
            "university": "AASTU",
            "course_code": "MATH101",
            "course_name": "Calculus I",
            "year": 2026,
            "email": "student@example.com",
        }

        # 1. Upload returns 202 Accepted
        response = await ac.post("/api/upload", files=files, data=data)
        assert response.status_code in (200, 202)
        body = response.json()
        assert "id" in body
        assert "polling_url" in body

        paper_id = body["id"]

        # 2. Polling returns granular 6-stage progress breakdown
        status_res = await ac.get(f"/api/papers/{paper_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()

        assert status_data["id"] == paper_id
        assert "status" in status_data
        assert "total_stages" in status_data
        assert status_data["total_stages"] == 6
        assert len(status_data["stages"]) == 6
        assert [s["name"] for s in status_data["stages"]] == [
            "preprocess",
            "extract",
            "analyze",
            "rewrite",
            "render",
            "store",
        ]


@pytest.mark.asyncio
async def test_papers_listing_and_filtering():
    """Test papers list endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/papers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
