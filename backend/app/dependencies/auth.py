"""Supabase Auth dependency for FastAPI.

Verifies Supabase Auth access tokens (JWT, HS256, signed with the project's
JWT secret) and exposes the signed-in user to route handlers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AuthUser:
    """The identity extracted from a Supabase access token."""

    id: str
    email: Optional[str]
    name: Optional[str]
    is_admin: bool = False

    @property
    def display_name(self) -> str:
        return self.name or (self.email.split("@")[0] if self.email else "PaperFlow member")


def _extract_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


_jwk_client: Optional["jwt.PyJWKClient"] = None


def _jwk_client_for(settings) -> "jwt.PyJWKClient":
    """JWKS client for the project's asymmetric signing keys (cached 1h)."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwk_client


def _decode_token(token: str) -> dict:
    """Verify a Supabase access token.

    Supabase projects use asymmetric signing keys (ES256/RS256) published at
    ``/auth/v1/.well-known/jwks.json``; legacy projects used HS256 with the
    JWT secret. We support both, keyed off the token's ``alg`` header.
    """
    settings = get_settings()
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server",
        )
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg", "HS256")
        if algorithm == "HS256":
            signing_material = settings.supabase_jwt_secret
            if not signing_material:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication is not configured on the server",
                )
            payload = jwt.decode(
                token,
                signing_material,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        else:
            signing_key = _jwk_client_for(settings).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
    except jwt.ExpiredSignatureError:
        logger.warning("Auth reject: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        )
    except jwt.InvalidSignatureError:
        logger.warning(
            "Auth reject: BAD SIGNATURE — token does not match any project signing key"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    except jwt.InvalidAudienceError:
        logger.warning("Auth reject: unexpected audience claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    except jwt.PyJWKClientError as exc:
        logger.warning(f"Auth reject: JWKS lookup failed ({exc})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        ) from exc
    except jwt.InvalidTokenError as exc:
        logger.warning(f"Auth reject: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        ) from exc
    return payload


def _user_from_payload(payload: dict) -> AuthUser:
    settings = get_settings()
    user_metadata = payload.get("user_metadata") or {}
    app_metadata = payload.get("app_metadata") or {}
    user_email = (payload.get("email") or "").strip().lower()

    admin_emails_set = {
        email.strip().lower()
        for email in settings.admin_emails.split(",")
        if email.strip()
    }

    is_admin = (
        app_metadata.get("role") in ("admin", "service_role")
        or app_metadata.get("claims_admin") is True
        or (bool(user_email) and user_email in admin_emails_set)
    )

    return AuthUser(
        id=payload["sub"],
        email=payload.get("email"),
        name=user_metadata.get("full_name") or user_metadata.get("name"),
        is_admin=is_admin,
    )


def get_current_user(request: Request) -> AuthUser:
    """Require a valid Supabase session; 401 otherwise."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
        )
    payload = _decode_token(token)
    return _user_from_payload(payload)


def get_optional_user(request: Request) -> Optional[AuthUser]:
    """Like get_current_user but returns None instead of 401 when signed out."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = _decode_token(token)
    except HTTPException:
        return None
    return _user_from_payload(payload)


def get_admin_user(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Require an authenticated user with administrative privileges; 403 otherwise."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required.",
        )
    return user
