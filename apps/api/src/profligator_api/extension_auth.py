"""Revocable browser sessions scoped to checks and owner history imports."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.models import ExtensionSession, User
from profligator_api.security import ACCESS_COOKIE, get_candidate_user, get_current_user, optional_bearer


class SessionCreate(BaseModel):
    label: str = Field(default="Browser extension", min_length=1, max_length=80)


class SessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class SessionGrant(BaseModel):
    token: str
    session: SessionInfo
    handle: str


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def read_extension_session(request: Request, bearer: HTTPAuthorizationCredentials | None) -> tuple[User, ExtensionSession]:
    if bearer is None or not bearer.credentials.startswith("pfext_"):
        raise HTTPException(status_code=401, detail="Connect the Profligator extension")
    with request.app.state.database.session() as session:
        device = session.scalar(select(ExtensionSession).where(
            ExtensionSession.token_hash == token_hash(bearer.credentials),
            ExtensionSession.revoked_at.is_(None),
            ExtensionSession.expires_at > datetime.now(UTC),
        ))
        user = session.get(User, device.user_id) if device else None
        if user is None:
            raise HTTPException(status_code=401, detail="Extension connection expired or was revoked")
        if user.role != "candidate":
            raise HTTPException(status_code=403, detail="Candidate account required")
        return user, device


async def get_check_candidate(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)],
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    if bearer is not None and bearer.credentials.startswith("pfext_"):
        return read_extension_session(request, bearer)[0]
    user = await get_current_user(request, bearer, cookie_token)
    if user.role != "candidate":
        raise HTTPException(status_code=403, detail="Candidate account required")
    return user


def create_extension_router(database: Database, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/extension", tags=["extension"])
    candidate = Annotated[User, Depends(get_candidate_user)]

    @router.post("/sessions", response_model=SessionGrant, status_code=201)
    async def connect(payload: SessionCreate, request: Request, response: Response, current_user: candidate) -> SessionGrant:
        # Only an explicit request from the signed-in application may issue a device grant.
        allowed = {settings.public_web_url.rstrip("/"), *settings.cors_origins}
        if request.headers.get("origin") not in allowed:
            raise HTTPException(status_code=403, detail="Connect from the Profligator application")
        response.headers["Cache-Control"] = "no-store"
        token = f"pfext_{secrets.token_urlsafe(48)}"
        with database.session() as session:
            device = ExtensionSession(user_id=current_user.id, token_hash=token_hash(token),
                                      label=payload.label.strip() or "Browser extension",
                                      expires_at=datetime.now(UTC) + timedelta(days=settings.extension_session_days))
            session.add(device)
            session.flush()
            return SessionGrant(token=token, session=SessionInfo.model_validate(device), handle=current_user.handle)

    @router.get("/sessions", response_model=list[SessionInfo])
    async def devices(current_user: candidate, response: Response) -> list[SessionInfo]:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            rows = session.scalars(select(ExtensionSession).where(
                ExtensionSession.user_id == current_user.id, ExtensionSession.revoked_at.is_(None),
                ExtensionSession.expires_at > datetime.now(UTC),
            ).order_by(ExtensionSession.created_at.desc()))
            return [SessionInfo.model_validate(row) for row in rows]

    @router.delete("/sessions/{session_id}", status_code=204)
    async def revoke(session_id: str, current_user: candidate) -> Response:
        with database.session() as session:
            device = session.get(ExtensionSession, session_id)
            if device is None or device.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="Extension connection not found")
            device.revoked_at = datetime.now(UTC)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.get("/session")
    async def identity(request: Request, response: Response,
                       bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)]) -> dict:
        user, device = read_extension_session(request, bearer)
        response.headers["Cache-Control"] = "no-store"
        expires_at = device.expires_at if device.expires_at.tzinfo else device.expires_at.replace(tzinfo=UTC)
        return {"handle": user.handle, "session_id": device.id, "expires_at": expires_at}

    @router.delete("/session", status_code=204)
    async def disconnect(request: Request,
                         bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)]) -> Response:
        _, device = read_extension_session(request, bearer)
        with database.session() as session:
            session.get(ExtensionSession, device.id).revoked_at = datetime.now(UTC)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return router
