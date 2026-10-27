from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from profligator_api.config import Settings
from profligator_api.models import User
from profligator_api.repository import Repository


ACCESS_COOKIE = "profligator_access"
REFRESH_COOKIE = "profligator_refresh"
password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("profligator-dummy-password")
optional_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    if encoded is None:
        password_hash.verify(password, dummy_password_hash)
        return False
    return password_hash.verify(password, encoded)


def create_access_token(user_id: str, settings: Settings, auth_version: int = 0) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {
            "sub": user_id,
            "iss": settings.auth_issuer,
            "aud": settings.auth_audience,
            "type": "access",
            "jti": str(uuid4()),
            "auth_version": auth_version,
            "iat": now,
            "exp": expires_at,
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )
    return token, expires_at


def decode_access_claims(token: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=["HS256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["sub", "iss", "aud", "type", "iat", "exp", "jti"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    version = payload.get("auth_version", 0)
    if (payload.get("type") != "access" or not isinstance(payload.get("sub"), str)
            or type(version) is not int or version < 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def decode_access_token(token: str, settings: Settings) -> str:
    return decode_access_claims(token, settings)["sub"]


def new_refresh_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        ACCESS_COOKIE,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


async def get_current_user(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)],
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    token = bearer.credentials if bearer is not None else cookie_token
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_claims(token, request.app.state.settings)
    with request.app.state.database.session() as session:
        user = Repository(session).get_user(claims["sub"])
        if user is None or user.auth_version != claims.get("auth_version", 0):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


async def get_candidate_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "candidate":
        raise HTTPException(status_code=403, detail="Candidate account required")
    return user
