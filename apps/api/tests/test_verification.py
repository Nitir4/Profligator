from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from profligator_api.config import Settings
from profligator_api.main import create_app
from profligator_api.models import VerificationToken, VerifiedEmail
from profligator_api.repository import Repository
from profligator_api.schemas import ConnectorMode, CanonicalProfile, ProfileSnapshot


@pytest.fixture
def verification(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'verification.db'}",
        verification_email_backend="smtp", verification_smtp_host="localhost",
        verification_smtp_from_email="verify@example.com", password_reset_email_backend="smtp",
        smtp_host="localhost", smtp_from_email="reset@example.com", leetcode_connector="fixture",
        geeksforgeeks_connector="fixture")
    app = create_app(settings)
    app.state.database.initialize()
    verification_mail, reset_mail = [], []
    monkeypatch.setattr(app.state.verification_mailer, "send", lambda *message: verification_mail.append(message))
    monkeypatch.setattr(app.state.recovery_mailer, "send", lambda *message: reset_mail.append(message))
    return app, verification_mail, reset_mail


async def register(client, email="owner@example.com", handle="owner"):
    result = await client.post('/api/v1/auth/register', json={"email":email,"handle":handle,"password":"original-password"})
    assert result.status_code == 201
    return result.json()['user']['id']


async def verify_email(client, deliveries):
    assert (await client.post('/api/v1/auth/verification/request')).status_code == 202
    link = next(line for line in deliveries[-1][2].splitlines() if '/verify-email#token=' in line)
    token = parse_qs(urlsplit(link).fragment)['token'][0]
    result = await client.post('/api/v1/auth/verification/confirm', json={"token":token})
    assert result.status_code == 200
    return token


async def test_separate_senders_and_one_use_bound_email_proof(verification):
    app, verification_mail, reset_mail = verification
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        token = await verify_email(client, verification_mail)
        assert (await client.get('/api/v1/auth/verification')).json()['email_verified'] is True
        assert not reset_mail
        assert app.state.verification_mailer.settings.smtp_from_email == "verify@example.com"
        assert app.state.recovery_mailer.settings.smtp_from_email == "reset@example.com"
        assert (await client.post('/api/v1/auth/verification/confirm', json={"token":token})).status_code == 400
        await client.post('/api/v1/auth/forgot-password', json={"email":"owner@example.com"})
        assert len(reset_mail) == 1 and len(verification_mail) == 1
        await client.post('/api/v1/auth/logout')
        await register(client, 'other@example.com', 'other')
        assert (await client.post('/api/v1/auth/verification/confirm', json={"token":token})).status_code == 400
        assert (await client.get('/api/v1/auth/verification')).json()['email_verified'] is False


async def test_email_expiry_throttle_and_auth_version(verification):
    app, deliveries, _ = verification
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        await register(client)
        await client.post('/api/v1/auth/verification/request')
        with app.state.database.session() as session:
            token = session.scalar(select(VerificationToken))
            token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        value = parse_qs(urlsplit(next(line for line in deliveries[-1][2].splitlines() if '/verify-email#token=' in line)).fragment)['token'][0]
        assert (await client.post('/api/v1/auth/verification/confirm',json={"token":value})).status_code == 400
        for _ in range(2):
            assert (await client.post('/api/v1/auth/verification/request')).status_code == 202
        assert (await client.post('/api/v1/auth/verification/request')).status_code == 429
        assert len(deliveries) == 3


async def test_profile_proof_requires_email_live_data_and_source_challenge(verification, monkeypatch):
    app, deliveries, _ = verification
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        uid = await register(client)
        canonical = CanonicalProfile(platform='leetcode',handle='source-owner',canonical_url='https://leetcode.com/u/source-owner/')
        with app.state.database.session() as session:
            profile = Repository(session).save_profile(uid, canonical, ConnectorMode.SCRAPER, live_data=True)
            pid = profile.id
        base=f'/api/v1/platform-profiles/{pid}/ownership'
        assert (await client.post(base+'/challenge')).status_code == 403
        await verify_email(client, deliveries)
        result = await client.post(base+'/challenge')
        assert result.status_code == 200
        code = result.json()['challenge']
        with app.state.database.session() as session:
            assert session.get(VerificationToken,sha256(code.encode()).hexdigest()).target == pid
        from profligator_api.connectors.leetcode import LeetCodeConnector
        name = 'Wrong name'
        async def fetch(self, profile):
            return ProfileSnapshot(profile=profile.model_copy(update={'display_name':name}),fetched_at=datetime.now(UTC))
        monkeypatch.setattr(LeetCodeConnector,'fetch_profile',fetch)
        # Fixture runtime configuration must not prove live ownership.
        assert (await client.post(base+'/confirm', json={'challenge':code})).status_code == 409
        app.state.settings.leetcode_connector = 'scraper'
        assert (await client.post(base+'/confirm', json={'challenge':code})).status_code == 409
        name = 'Owner '+code
        assert (await client.post(base+'/confirm', json={'challenge':code})).status_code == 200
        assert (await client.post(base+'/confirm', json={'challenge':code})).status_code == 400
        with app.state.database.session() as session:
            assert Repository(session).get_profile(pid,uid).verification_state == 'verified'
            Repository(session).save_profile(uid,canonical,ConnectorMode.SCRAPER,live_data=True)
            assert Repository(session).get_profile(pid,uid).verification_state == 'verified'
        await client.post('/api/v1/auth/logout')
        await register(client,'other@example.com','other')
        assert (await client.post(base+'/challenge')).status_code == 404


async def test_email_proof_invalidated_by_password_reset(verification):
    app, deliveries, resets = verification
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
        await register(client)
        await client.post('/api/v1/auth/verification/request')
        token = parse_qs(urlsplit(next(line for line in deliveries[-1][2].splitlines() if '/verify-email#token=' in line)).fragment)['token'][0]
        await client.post('/api/v1/auth/forgot-password',json={'email':'owner@example.com'})
        reset = parse_qs(urlsplit(next(line for line in resets[-1][2].splitlines() if '/reset-password#token=' in line)).fragment)['token'][0]
        assert (await client.post('/api/v1/auth/reset-password',json={'token':reset,'password':'replacement-password','confirm_password':'replacement-password'})).status_code == 200
        await client.post('/api/v1/auth/login',json={'email':'owner@example.com','password':'replacement-password'})
        assert (await client.post('/api/v1/auth/verification/confirm',json={'token':token})).status_code == 400
