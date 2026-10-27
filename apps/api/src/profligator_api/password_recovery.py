"""One-use email recovery with hashed tokens and database-backed throttling."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256
import hmac
import logging
import secrets
import smtplib
import ssl

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from profligator_api.models import (
    ExtensionSession, OAuthAttempt, PasswordResetRateLimit, PasswordResetToken, RefreshSession, User,
)
from profligator_api.security import clear_auth_cookies, hash_password

logger = logging.getLogger(__name__)
GENERIC_MESSAGE = "If an account exists for this email, a password reset link has been requested. Check your inbox."


class RecoveryRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{64}$")
    password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)

    @model_validator(mode="after")
    def confirm(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class RecoveryMailer:
    def __init__(self, settings):
        self.settings = settings

    def send(self, recipient, subject, body):
        settings = self.settings
        message = EmailMessage()
        message["From"] = f"Profligator <{settings.smtp_from_email}>"
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            transport = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                        timeout=settings.smtp_timeout_seconds, context=context)
        else:
            transport = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
        with transport as smtp:
            smtp.ehlo()
            if settings.smtp_security == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    def send_reset(self, recipient, link):
        self.send(recipient, "Reset your Profligator password",
                  f"Use this link to set a new Profligator password:\n\n{link}\n\n"
                  f"It expires in {self.settings.password_reset_minutes} minutes and can be used once.\n"
                  "If you did not request this, you can ignore this message. Your password has not changed.")

    def send_confirmation(self, recipient):
        self.send(recipient, "Your Profligator password was changed",
                  "Your Profligator password has been changed. Existing app and extension sessions were signed out.\n\n"
                  "If you did not make this change, use Forgot password to recover your account.")


def allow_request(session, key, limit, now):
    """Atomic fixed-window counter shared by API processes on SQLite/PostgreSQL."""
    model = PasswordResetRateLimit
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else postgres_insert
    expired = model.window_started_at <= now - timedelta(hours=1)
    statement = insert(model).values(key_hash=key, window_started_at=now, requests=1)
    statement = statement.on_conflict_do_update(index_elements=[model.key_hash], set_={
        "window_started_at": case((expired, now), else_=model.window_started_at),
        "requests": case((expired, 1), else_=model.requests + 1),
    }).returning(model.requests)
    return session.scalar(statement) <= limit


def create_recovery_router(database, settings, mailer):
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    def key(value):
        return hmac.new(settings.auth_secret_key.encode(), value.encode(), sha256).hexdigest()

    def issue_and_deliver(email):
        token = secrets.token_urlsafe(48)
        with database.session() as session:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                return
            session.add(PasswordResetToken(token_hash=sha256(token.encode()).hexdigest(), user_id=user.id,
                auth_version=user.auth_version, expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_minutes)))
        link = settings.public_web_url.rstrip("/") + "/reset-password#token=" + token
        try:
            mailer.send_reset(email, link)
        except Exception as error:
            # SMTP exceptions can contain recipient addresses or credentials.
            logger.warning("Password recovery delivery failed (%s)", type(error).__name__)

    def notify_change(email):
        try:
            mailer.send_confirmation(email)
        except Exception as error:
            logger.warning("Password change notification failed (%s)", type(error).__name__)

    @router.post("/forgot-password", status_code=202)
    async def forgot(payload: RecoveryRequest, request: Request, response: Response, tasks: BackgroundTasks):
        response.headers["Cache-Control"] = "no-store"
        if settings.password_reset_email_backend != "smtp":
            raise HTTPException(status_code=503, detail="Password recovery email is not configured. You can use Google sign-in if connected.")
        now = datetime.now(UTC)
        email = str(payload.email).strip().lower()
        with database.session() as session:
            session.execute(delete(PasswordResetRateLimit).where(PasswordResetRateLimit.window_started_at < now - timedelta(days=2)))
            session.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < now - timedelta(days=1)))
            ip_allowed = allow_request(session, key("ip:" + (request.client.host if request.client else "unknown")), 30, now)
            email_allowed = allow_request(session, key("email:" + email), 3, now) if ip_allowed else False
        # Identical response for missing accounts, throttled addresses and owners.
        # Account lookup and SMTP run after the response, preventing SMTP timing
        # from disclosing whether an email address is registered.
        if ip_allowed and email_allowed:
            tasks.add_task(issue_and_deliver, email)
        return {"message": GENERIC_MESSAGE}

    @router.post("/reset-password")
    async def reset(payload: PasswordReset, response: Response, tasks: BackgroundTasks):
        now = datetime.now(UTC)
        token_hash = sha256(payload.token.encode()).hexdigest()
        invalid = HTTPException(status_code=400, detail="This reset link is invalid or expired. Request a new link.")
        with database.session() as session:
            token = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now))
            if token is None:
                raise invalid
            password = hash_password(payload.password)
            claimed = session.execute(update(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now).values(used_at=now)
                .execution_options(synchronize_session=False))
            if claimed.rowcount != 1:
                raise invalid
            changed = session.execute(update(User).where(User.id == token.user_id, User.auth_version == token.auth_version)
                .values(password_hash=password, auth_version=User.auth_version + 1, updated_at=now))
            if changed.rowcount != 1:
                raise invalid
            email = session.get(User, token.user_id).email
            session.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == token.user_id,
                PasswordResetToken.used_at.is_(None)).values(used_at=now))
            session.execute(update(RefreshSession).where(RefreshSession.user_id == token.user_id,
                RefreshSession.revoked_at.is_(None)).values(revoked_at=now))
            session.execute(update(ExtensionSession).where(ExtensionSession.user_id == token.user_id,
                ExtensionSession.revoked_at.is_(None)).values(revoked_at=now))
            session.execute(delete(OAuthAttempt).where(OAuthAttempt.link_user_id == token.user_id))
        clear_auth_cookies(response, settings)
        response.headers["Cache-Control"] = "no-store"
        tasks.add_task(notify_change, email)
        return {"message": "Password updated. Sign in with your new password."}

    return router
