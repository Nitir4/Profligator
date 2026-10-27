"""Inbox verification and server-observed proof of coding-profile control."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import logging
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from profligator_api.connectors import ConnectorError, ConnectorRegistry
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.models import PlatformProfile, User, VerificationToken, VerifiedEmail
from profligator_api.password_recovery import allow_request
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, Platform
from profligator_api.security import get_current_user

logger = logging.getLogger(__name__)


class EmailProof(BaseModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{64}$")


class ProfileProof(BaseModel):
    challenge: str = Field(pattern=r"^PG-[a-f0-9]{24}$")


def digest(token):
    return sha256(token.encode()).hexdigest()


def create_verification_router(database, settings, mailer):
    router = APIRouter(prefix="/api/v1", tags=["verification"])
    owner = Annotated[User, Depends(get_current_user)]

    def verified(session, user):
        record = session.get(VerifiedEmail, user.id)
        return record is not None and record.email == user.email

    def throttle(session, user_id, purpose, limit):
        key = digest(f"verification:{user_id}:{purpose}")
        if not allow_request(session, key, limit, datetime.now(UTC)):
            return False
        return True

    def new_token(session, user, target, purpose, token):
        now = datetime.now(UTC)
        session.execute(delete(VerificationToken).where(VerificationToken.expires_at < now - timedelta(days=1)))
        session.execute(update(VerificationToken).where(VerificationToken.user_id == user.id,
            VerificationToken.target == target, VerificationToken.purpose == purpose,
            VerificationToken.used_at.is_(None)).values(used_at=now))
        session.add(VerificationToken(token_hash=digest(token), user_id=user.id, target=target,
            purpose=purpose, auth_version=user.auth_version, expires_at=now + timedelta(minutes=30)))

    def consume(session, user, target, purpose, token):
        now = datetime.now(UTC)
        result = session.execute(update(VerificationToken).where(
            VerificationToken.token_hash == digest(token), VerificationToken.user_id == user.id,
            VerificationToken.target == target, VerificationToken.purpose == purpose,
            VerificationToken.auth_version == user.auth_version,
            VerificationToken.auth_version == select(User.auth_version).where(User.id == user.id).scalar_subquery(),
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > now).values(used_at=now))
        if result.rowcount != 1:
            raise HTTPException(400, "Verification is invalid, expired or already used. Request a new challenge.")

    def deliver(email, token):
        link = settings.public_web_url.rstrip("/") + "/verify-email#token=" + token
        try:
            mailer.send(email, "Verify your Profligator email",
                f"Open this link while signed in to the same Profligator account:\n\n{link}\n\n"
                "This one-use link expires in 30 minutes. If you did not request it, ignore this message.")
        except Exception as error:
            logger.warning("Email verification delivery failed (%s)", type(error).__name__)

    @router.get("/auth/verification")
    async def status(current_user: owner, response: Response):
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            return {"email": current_user.email, "email_verified": verified(session, current_user),
                    "email_delivery_configured": settings.verification_email_backend == "smtp"}

    @router.post("/auth/verification/request", status_code=202)
    async def request(current_user: owner, response: Response, tasks: BackgroundTasks):
        response.headers["Cache-Control"] = "no-store"
        if settings.verification_email_backend != "smtp":
            raise HTTPException(503, "Verification email is not configured.")
        with database.session() as session:
            allowed = throttle(session, current_user.id, "email", 3)
            if allowed:
                token = secrets.token_urlsafe(48)
                new_token(session, current_user, current_user.email, "email", token)
        if not allowed:
            raise HTTPException(429, "Too many verification requests. Try again in an hour.")
        tasks.add_task(deliver, current_user.email, token)
        return {"message": "Verification email requested. Check your inbox and spam folder."}

    @router.post("/auth/verification/confirm")
    async def confirm(payload: EmailProof, current_user: owner, response: Response):
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            # Serialize confirmations for the same user before consuming a token.
            session.execute(update(User).where(User.id == current_user.id).values(updated_at=User.updated_at))
            consume(session, current_user, current_user.email, "email", payload.token)
            session.merge(VerifiedEmail(user_id=current_user.id, email=current_user.email, verified_at=datetime.now(UTC)))
        return {"message": "Your account email is verified."}

    @router.post("/platform-profiles/{profile_id}/ownership/challenge")
    async def challenge(profile_id: str, current_user: owner, response: Response):
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            profile = Repository(session).get_profile(profile_id, current_user.id)
            if profile is None:
                raise HTTPException(404, "Linked profile not found")
            if not verified(session, current_user):
                raise HTTPException(403, "Verify your Profligator email first.")
            if profile.connector_mode not in {"scraper", "official_api"}:
                raise HTTPException(409, "Ownership proof requires a live source connector, not fixture or aggregated data.")
            allowed = throttle(session, current_user.id, "ownership-request", 10)
            if allowed:
                code = "PG-" + secrets.token_hex(12)
                new_token(session, current_user, profile.id, "profile", code)
        if not allowed:
            raise HTTPException(429, "Too many ownership requests. Try again in an hour.")
        return {"challenge": code, "expires_in_minutes": 30,
                "instructions": "Temporarily add this exact code to your coding profile's public name (Codeforces: first name). Save the platform profile, then check ownership here. Restore your name after success."}

    @router.post("/platform-profiles/{profile_id}/ownership/confirm")
    async def prove(profile_id: str, payload: ProfileProof, current_user: owner, response: Response):
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            profile = Repository(session).get_profile(profile_id, current_user.id)
            if profile is None:
                raise HTTPException(404, "Linked profile not found")
            if not verified(session, current_user):
                raise HTTPException(403, "Verify your Profligator email first.")
            allowed = throttle(session, current_user.id, "ownership-check", 20)
            pending = session.get(VerificationToken, digest(payload.challenge))
            now = datetime.now(UTC)
            expires = pending.expires_at.replace(tzinfo=UTC) if pending and pending.expires_at.tzinfo is None else pending.expires_at if pending else now
            if not pending or pending.user_id != current_user.id or pending.target != profile.id or pending.purpose != "profile" or pending.used_at or expires <= now or pending.auth_version != current_user.auth_version:
                raise HTTPException(400, "Verification is invalid, expired or already used. Request a new challenge.")
            canonical = CanonicalProfile(platform=Platform(profile.platform), handle=profile.public_handle, canonical_url=profile.canonical_url)
        if not allowed:
            raise HTTPException(429, "Too many ownership checks. Try again in an hour.")
        connector = ConnectorRegistry(settings, metadata_store=DatabaseMetadataStore(database)).get(canonical.platform)
        if not connector.descriptor.live_data or connector.descriptor.mode.value not in {"scraper", "official_api"}:
            raise HTTPException(409, "Ownership proof requires a live source connector.")
        try:
            snapshot = await connector.fetch_profile(canonical)
        except ConnectorError:
            raise HTTPException(502, "The coding platform could not be checked. No ownership was verified.") from None
        name = snapshot.profile.display_name or ""
        if snapshot.profile.handle.casefold() != canonical.handle.casefold() or not re.search(r"(?<![A-Za-z0-9-])" + re.escape(payload.challenge) + r"(?![A-Za-z0-9-])", name):
            raise HTTPException(409, "Challenge not found in the public profile name. Save it on the coding platform and try again.")
        with database.session() as session:
            session.execute(update(PlatformProfile).where(PlatformProfile.id == profile_id).values(updated_at=PlatformProfile.updated_at))
            profile = Repository(session).get_profile(profile_id, current_user.id)
            if profile is None:
                raise HTTPException(404, "Linked profile was disconnected")
            consume(session, current_user, profile.id, "profile", payload.challenge)
            profile.verification_state = "verified"
        return {"message": "Coding-profile control verified. You can restore your public name.", "verification_state": "verified"}

    return router
