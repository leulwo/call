import pytest
from pipeline.renderer import sanitize_latex
from app.dependencies.auth import _user_from_payload


def test_latex_sanitization_removes_dangerous_macros():
    malicious_latex = r"""
    \documentclass{article}
    \usepackage{minted}
    \usepackage{shellesc}
    \begin{document}
    \write18{whoami > hacked.txt}
    \immediate\write18{cat /etc/passwd}
    \input{../../backend/.env}
    \include{secret}
    \openin1=secret.txt
    \catcode`\&=12
    \csname relax\endcsname
    \includegraphics[width=0.8\textwidth]{../../etc/passwd.png}
    \includegraphics{safe_diagram.png}
    \end{document}
    """
    sanitized = sanitize_latex(malicious_latex)
    assert "\\write18" not in sanitized
    assert "\\immediate" not in sanitized
    assert "\\input{" not in sanitized
    assert "\\include{" not in sanitized
    assert "\\openin" not in sanitized
    assert "\\catcode" not in sanitized
    assert "\\csname" not in sanitized
    assert "minted" not in sanitized
    assert "shellesc" not in sanitized
    assert "../../etc/passwd.png" not in sanitized
    assert "\\includegraphics{safe_diagram.png}" in sanitized


def test_auth_user_role_extraction():
    # Admin via app_metadata
    admin_payload = {
        "sub": "user-123",
        "email": "admin@example.com",
        "app_metadata": {"role": "admin"},
        "user_metadata": {"full_name": "Admin User"},
    }
    user = _user_from_payload(admin_payload)
    assert user.is_admin is True

    # Standard member
    regular_payload = {
        "sub": "user-456",
        "email": "student@example.com",
        "app_metadata": {"role": "authenticated"},
        "user_metadata": {"full_name": "Regular Student"},
    }
    regular_user = _user_from_payload(regular_payload)
    assert regular_user.is_admin is False


def test_safe_redirect_validation():
    # Simulates the frontend next param check
    def is_safe_redirect(url: str) -> bool:
        return url.startswith("/") and not url.startswith("//") and not url.startswith("/\\")

    assert is_safe_redirect("/") is True
    assert is_safe_redirect("/library") is True
    assert is_safe_redirect("/papers/123") is True
    assert is_safe_redirect("//evil.com") is False
    assert is_safe_redirect("/\\evil.com") is False
    assert is_safe_redirect("https://evil.com") is False


@pytest.mark.asyncio
async def test_admin_reports_endpoint_rejects_unauthenticated():
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/reports")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_rejects_spoofed_magic_bytes():
    import io
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.dependencies.auth import get_current_user, AuthUser

    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="00000000-0000-0000-0000-000000000001",
        email="student@example.com",
        name="Test Student",
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # File named .pdf but containing plain text instead of %PDF- header
            fake_pdf = b"Plain text file content trying to spoof pdf"
            files = {"file": ("malicious.pdf", io.BytesIO(fake_pdf), "application/pdf")}
            data = {
                "title": "Malicious Test",
                "description": "Attempting spoofed upload",
            }
            response = await ac.post("/api/upload", files=files, data=data)
            assert response.status_code == 400
            assert "not a valid PDF" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
