from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from profligator_api.config import Settings
from profligator_api.main import create_app
from profligator_api.models import PasswordResetToken, RefreshSession, User
from profligator_api.password_recovery import RecoveryMailer
from profligator_api.repository import Repository


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'recovery.db'}",
        password_reset_email_backend="smtp", smtp_host="localhost", smtp_from_email="sender@example.com",
        leetcode_connector="fixture", geeksforgeeks_connector="fixture")
    app = create_app(settings)
    deliveries = []
    monkeypatch.setattr(app.state.recovery_mailer, "send", lambda email, subject, body: deliveries.append((email, subject, body)))
    app.state.database.initialize()
    return app, deliveries


async def register(client, email="owner@example.com", handle="owner"):
    response = await client.post("/api/v1/auth/register", json={"email": email, "handle": handle, "password": "original-password"})
    assert response.status_code == 201
    return response.json()["user"]["id"]


async def request_token(client, deliveries, email="owner@example.com"):
    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    link = next(line for line in deliveries[-1][2].splitlines() if "/reset-password#token=" in line)
    return parse_qs(urlsplit(link).fragment)["token"][0]


def reset_payload(token, password="replacement-password"):
    return {"token": token, "password": password, "confirm_password": password}


async def test_reset_is_one_use_and_revokes_all_credentials(recovery):
    app, deliveries = recovery
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        user_id = await register(client)
        old_access = client.cookies.get("profligator_access")
        old_refresh = client.cookies.get("profligator_refresh")
        grant = await client.post("/api/v1/extension/sessions", json={}, headers={"Origin":"http://localhost:5173"})
        device = grant.json()["token"]
        token = await request_token(client, deliveries)
        with app.state.database.session() as session:
            stored = session.scalar(select(PasswordResetToken))
            assert stored.token_hash == sha256(token.encode()).hexdigest() and stored.token_hash != token
        response = await client.post("/api/v1/auth/reset-password", json=reset_payload(token))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert len(deliveries) == 2 and "changed" in deliveries[-1][1]
        assert "replacement-password" not in deliveries[-1][2]
        assert (await client.get("/api/v1/auth/me", headers={"Authorization":f"Bearer {old_access}"})).status_code == 401
        client.cookies.set("profligator_refresh", old_refresh, path="/api/v1/auth")
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401
        assert (await client.get("/api/v1/extension/session", headers={"Authorization":f"Bearer {device}"})).status_code == 401
        assert (await client.post("/api/v1/auth/reset-password", json=reset_payload(token))).status_code == 400
        assert (await client.post("/api/v1/auth/login", json={"email":"owner@example.com","password":"original-password"})).status_code == 401
        assert (await client.post("/api/v1/auth/login", json={"email":"owner@example.com","password":"replacement-password"})).status_code == 200
        with app.state.database.session() as session:
            assert session.get(User, user_id).auth_version == 1


async def test_generic_missing_account_and_email_throttle(recovery):
    app, deliveries = recovery
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        unknown = await client.post("/api/v1/auth/forgot-password", json={"email":"absent@example.com"})
        assert not deliveries
        for _ in range(5):
            known = await client.post("/api/v1/auth/forgot-password", json={"email":"OWNER@example.com"})
            assert known.status_code == unknown.status_code and known.json() == unknown.json()
            assert "token" not in known.text
        assert len(deliveries) == 3


async def test_expired_invalid_and_mismatched_passwords_do_not_change_account(recovery):
    app, deliveries = recovery
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        token = await request_token(client, deliveries)
        mismatched = {**reset_payload(token),"confirm_password":"different-password"}
        response = await client.post("/api/v1/auth/reset-password", json=mismatched)
        assert response.status_code == 422
        assert token not in response.text and "replacement-password" not in response.text
        response = await client.post("/api/v1/auth/reset-password", json=reset_payload(token,"short"))
        assert response.status_code == 422 and '"input"' not in response.text
        with app.state.database.session() as session:
            session.get(PasswordResetToken,sha256(token.encode()).hexdigest()).expires_at = datetime.now(UTC)-timedelta(seconds=1)
        for invalid in (token,"x"*64):
            assert (await client.post("/api/v1/auth/reset-password",json=reset_payload(invalid))).status_code == 400
        assert (await client.post("/api/v1/auth/login",json={"email":"owner@example.com","password":"original-password"})).status_code == 200


async def test_reset_invalidates_other_tokens_but_not_other_users(recovery):
    app, deliveries = recovery
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        first = await request_token(client, deliveries)
        second = await request_token(client, deliveries)
        await register(client,"other@example.com","other")
        other = await request_token(client, deliveries,"other@example.com")
        assert (await client.post("/api/v1/auth/reset-password",json=reset_payload(first))).status_code == 200
        assert (await client.post("/api/v1/auth/reset-password",json=reset_payload(second))).status_code == 400
        assert (await client.post("/api/v1/auth/reset-password",json=reset_payload(other))).status_code == 200


async def test_version_rejects_stale_refresh_created_after_reset(recovery):
    app, deliveries = recovery
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        user_id = await register(client)
        token = await request_token(client, deliveries)
        await client.post("/api/v1/auth/reset-password",json=reset_payload(token))
        with app.state.database.session() as session:
            Repository(session).create_refresh_session(user_id=user_id,token_hash="stale-hash",auth_version=0,
                expires_at=datetime.now(UTC)+timedelta(days=1))
            assert Repository(session).get_active_refresh_session("stale-hash") is None


async def test_google_only_account_can_set_password_through_email_proof(recovery):
    app, deliveries = recovery
    with app.state.database.session() as session:
        Repository(session).create_user(email="owner@example.com",handle="owner",password_hash=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        token = await request_token(client, deliveries)
        assert (await client.post("/api/v1/auth/reset-password",json=reset_payload(token))).status_code == 200
        assert (await client.post("/api/v1/auth/login",json={"email":"owner@example.com","password":"replacement-password"})).status_code == 200


async def test_delivery_failure_is_generic_and_logs_no_secrets(recovery, monkeypatch, caplog):
    app, deliveries = recovery
    def fail(*args): raise RuntimeError("private-password owner@example.com token=private")
    monkeypatch.setattr(app.state.recovery_mailer,"send",fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        response = await client.post("/api/v1/auth/forgot-password",json={"email":"owner@example.com"})
        assert response.status_code == 202
        assert "RuntimeError" in caplog.text and "private" not in caplog.text and "owner@example.com" not in caplog.text


def test_smtp_uses_starttls_and_configured_sender(monkeypatch):
    calls=[]
    class SMTP:
        def __init__(self,*args,**kwargs): calls.append(("connect",args))
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def ehlo(self): calls.append(("ehlo",))
        def starttls(self,context): calls.append(("tls",context.check_hostname))
        def login(self,user,password): calls.append(("login",user,password))
        def send_message(self,message): calls.append(("message",message))
    monkeypatch.setattr("profligator_api.password_recovery.smtplib.SMTP",SMTP)
    settings=Settings(_env_file=None,password_reset_email_backend="smtp",smtp_host="smtp.gmail.com",
        smtp_username="sender@example.com",smtp_password="app-password",smtp_from_email="sender@example.com")
    RecoveryMailer(settings).send_reset("owner@example.com","http://localhost:5173/reset-password#token=test")
    assert [call[0] for call in calls]==["connect","ehlo","tls","ehlo","login","message"]
    assert calls[2][1] is True
    assert calls[-1][1]["To"]=="owner@example.com" and "sender@example.com" in calls[-1][1]["From"]


def test_plain_smtp_is_rejected_for_production_or_remote_hosts():
    for host in ("smtp.gmail.com","example.com"):
        with pytest.raises(ValueError,match="Plain SMTP"):
            Settings(_env_file=None,password_reset_email_backend="smtp",smtp_host=host,
                smtp_from_email="sender@example.com",smtp_security="plain")


def test_disabled_smtp_accepts_empty_compose_sender():
    settings = Settings(_env_file=None, password_reset_email_backend="disabled", smtp_from_email="")
    assert settings.smtp_from_email is None
