"""Google's authorization-code login with PKCE and verified OIDC identity."""

import asyncio
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import re
import secrets
import time
from typing import Annotated, Callable
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.models import OAuthAttempt, OAuthIdentity, User
from profligator_api.repository import Repository
from profligator_api.security import (
    ACCESS_COOKIE, REFRESH_COOKIE, decode_access_claims, get_current_user, hash_refresh_token,
)

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
STATE_COOKIE = "profligator_google_state"
STATE_PATH = "/api/v1/auth/google"
email_adapter = TypeAdapter(EmailStr)


class GoogleAuthError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class GoogleOAuthClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self._keys: dict[str, dict] = {}
        self._keys_expire = 0.0
        self._key_lock = asyncio.Lock()

    async def _signing_key(self, kid: str):
        async with self._key_lock:
            if kid not in self._keys or time.monotonic() >= self._keys_expire:
                async with httpx.AsyncClient(transport=self.transport, timeout=15) as client:
                    response = await client.get(GOOGLE_CERTS)
                    response.raise_for_status()
                payload = response.json()
                self._keys = {key["kid"]: key for key in payload["keys"] if key.get("kty") == "RSA" and key.get("kid")}
                max_age = re.search(r"max-age=(\d+)", response.headers.get("cache-control", ""))
                self._keys_expire = time.monotonic() + min(int(max_age[1]) if max_age else 300, 3600)
            if kid not in self._keys:
                raise GoogleAuthError("invalid_identity")
            return jwt.PyJWK.from_dict(self._keys[kid], algorithm="RS256").key

    async def identity(self, code: str, verifier: str, nonce: str) -> dict:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15) as client:
                response = await client.post(GOOGLE_TOKEN, data={
                    "code": code, "code_verifier": verifier,
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret.get_secret_value(),
                    "redirect_uri": self.settings.google_callback_url,
                    "grant_type": "authorization_code",
                })
                if response.status_code >= 500 or response.status_code == 429:
                    raise GoogleAuthError("google_unavailable")
                if not response.is_success:
                    raise GoogleAuthError("google_exchange_failed")
                token = response.json().get("id_token")
            if not isinstance(token, str) or len(token) > 16384:
                raise GoogleAuthError("invalid_identity")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise GoogleAuthError("invalid_identity")
            key = await self._signing_key(header["kid"])
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=self.settings.google_client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
                options={"require": ["iss", "aud", "sub", "exp", "iat", "nonce", "email", "email_verified"]},
                leeway=30,
            )
            if (not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce)
                    or not (claims["email_verified"] is True or claims["email_verified"] == "true")
                    or not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 255
                    or not claims["sub"].isascii()
                    or claims.get("azp", self.settings.google_client_id) != self.settings.google_client_id
                    or (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and not claims.get("azp"))):
                raise GoogleAuthError("invalid_identity")
            claims["email"] = str(email_adapter.validate_python(claims["email"])).lower()
            return claims
        except httpx.HTTPError as exc:
            raise GoogleAuthError("google_unavailable") from exc
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError, ValidationError) as exc:
            raise GoogleAuthError("invalid_identity") from exc


def create_google_router(database: Database, settings: Settings, session_response: Callable, google: GoogleOAuthClient) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    def configured() -> None:
        if not settings.google_enabled:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured yet.")

    def start(response: Response, link_user_id: str | None = None) -> dict:
        configured()
        state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        now = datetime.now(UTC)
        with database.session() as session:
            session.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at <= now))
            session.add(OAuthAttempt(
                state_hash=hash_refresh_token(state), nonce=nonce, code_verifier=verifier,
                link_user_id=link_user_id, expires_at=now + timedelta(minutes=10),
            ))
        response.set_cookie(STATE_COOKIE, state, httponly=True, secure=settings.auth_cookie_secure,
                            samesite="lax", max_age=600, path=STATE_PATH)
        response.headers["Cache-Control"] = "no-store"
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")
        return {"authorization_url": GOOGLE_AUTHORIZE + "?" + urlencode({
            "client_id": settings.google_client_id, "redirect_uri": settings.google_callback_url,
            "response_type": "code", "scope": "openid email profile", "state": state,
            "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
            "prompt": "select_account",
        })}

    @router.post("/google/start")
    async def google_start(response: Response) -> dict:
        return start(response)

    @router.post("/google/link")
    async def google_link(response: Response, user: Annotated[User, Depends(get_current_user)]) -> dict:
        return start(response, user.id)

    @router.get("/providers")
    async def providers(response: Response, user: Annotated[User, Depends(get_current_user)]) -> dict:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            identity = session.scalar(select(OAuthIdentity).where(OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "google"))
            return {"google_configured": settings.google_enabled, "google_connected": identity is not None,
                    "google_email": identity.email if identity else None, "password_enabled": user.password_hash is not None}

    def finish(path: str, error: str | None = None) -> RedirectResponse:
        url = settings.public_web_url.rstrip("/") + path
        if error:
            url += ("&" if "?" in url else "?") + urlencode({"google_error": error})
        response = RedirectResponse(url, status_code=303)
        response.delete_cookie(STATE_COOKIE, path=STATE_PATH, httponly=True,
                               secure=settings.auth_cookie_secure, samesite="lax")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @router.get("/google/callback")
    async def callback(
        request: Request, code: str | None = Query(default=None, max_length=4096),
        state: str | None = Query(default=None, max_length=256),
        error: str | None = Query(default=None, max_length=256),
    ) -> RedirectResponse:
        target = "/login"
        try:
            if not settings.google_enabled:
                raise GoogleAuthError("google_not_configured")
            cookie = request.cookies.get(STATE_COOKIE)
            if not state or not cookie or not secrets.compare_digest(state, cookie):
                raise GoogleAuthError("invalid_state")
            with database.session() as session:
                # Consume once, before exchanging a code. Replays cannot reuse an attempt.
                attempt = session.execute(delete(OAuthAttempt).where(
                    OAuthAttempt.state_hash == hash_refresh_token(state),
                    OAuthAttempt.expires_at > datetime.now(UTC),
                ).returning(OAuthAttempt.nonce, OAuthAttempt.code_verifier, OAuthAttempt.link_user_id)).first()
            if attempt is None:
                raise GoogleAuthError("invalid_state")
            if attempt.link_user_id:
                target = "/settings/account"
            if error:
                raise GoogleAuthError("google_cancelled")
            if not code:
                raise GoogleAuthError("google_exchange_failed")
            claims = await google.identity(code, attempt.code_verifier, attempt.nonce)
            with database.session() as session:
                repository = Repository(session)
                identity = session.scalar(select(OAuthIdentity).where(
                    OAuthIdentity.provider == "google", OAuthIdentity.subject == claims["sub"],
                ))
                if attempt.link_user_id:
                    token = request.cookies.get(ACCESS_COOKIE)
                    try:
                        current_claims = decode_access_claims(token or "", settings)
                        current_id = current_claims["sub"]
                    except HTTPException as exc:
                        raise GoogleAuthError("link_session_expired") from exc
                    if current_id != attempt.link_user_id:
                        raise GoogleAuthError("link_session_expired")
                    user = repository.get_user(current_id)
                    if user is None or user.auth_version != current_claims.get("auth_version", 0):
                        raise GoogleAuthError("link_session_expired")
                    if identity and identity.user_id != user.id:
                        raise GoogleAuthError("google_already_linked")
                    existing = session.scalar(select(OAuthIdentity).where(OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "google"))
                    if existing and existing.subject != claims["sub"]:
                        raise GoogleAuthError("google_already_linked")
                elif identity:
                    user = repository.get_user(identity.user_id)
                else:
                    if repository.get_user_by_email(claims["email"]):
                        raise GoogleAuthError("account_exists")
                    base = re.sub(r"[^A-Za-z0-9_.-]", "_", claims["email"].split("@", 1)[0])[:40]
                    handle = f"{base or 'candidate'}_{secrets.token_hex(5)}"
                    user = repository.create_user(email=claims["email"], handle=handle, password_hash=None)
                if identity is None:
                    identity = OAuthIdentity(user_id=user.id, provider="google", subject=claims["sub"], email=claims["email"])
                    session.add(identity)
                else:
                    identity.email = claims["email"]
                user.auth_provider = "password_google" if user.password_hash else "google"
                session.flush()
                if attempt.link_user_id:
                    target = "/settings/account?google_connected=1"
                elif user.role == "recruiter":
                    target = "/team"
                else:
                    target = "/dashboard" if repository.list_profiles(user.id) else "/onboarding/profiles"
                response = finish(target)
                old_refresh = request.cookies.get(REFRESH_COOKIE)
                if old_refresh:
                    repository.revoke_refresh_session(hash_refresh_token(old_refresh))
                session_response(response, repository, user)
                return response
        except GoogleAuthError as exc:
            return finish(target, exc.code)
        except IntegrityError:
            return finish(target, "account_conflict")

    return router
