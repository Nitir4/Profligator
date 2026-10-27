from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
from pydantic import SecretStr
import pytest
from sqlalchemy import func, select

from profligator_api.google_auth import GOOGLE_CERTS, GOOGLE_TOKEN, STATE_COOKIE
from profligator_api.models import OAuthAttempt, OAuthIdentity, User
from profligator_api.security import hash_refresh_token


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def provider(client, signing_key):
    settings = client._transport.app.state.settings
    settings.google_client_id = "test-client.apps.googleusercontent.com"
    settings.google_client_secret = SecretStr("test-client-secret")
    tokens = {}
    calls = []
    key = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    key.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    def transport(request):
        calls.append(request)
        if str(request.url) == GOOGLE_CERTS:
            return httpx.Response(200, json={"keys": [key]}, headers={"cache-control": "public,max-age=3600"})
        assert str(request.url) == GOOGLE_TOKEN
        form = parse_qs(request.content.decode())
        if form["code"][0] == "unavailable":
            return httpx.Response(503)
        if form["code"][0] not in tokens:
            return httpx.Response(400, json={"error": "invalid_grant"})
        assert form["client_secret"] == ["test-client-secret"]
        return httpx.Response(200, json={"id_token": tokens[form["code"][0]], "access_token": "not-persisted"})
    client._transport.app.state.google_oauth.transport = httpx.MockTransport(transport)
    return tokens, calls


async def begin(client, signing_key, tokens, *, email="google-user@example.com", subject="google-subject", link=False, overrides=None):
    response = await client.post("/api/v1/auth/google/link" if link else "/api/v1/auth/google/start")
    assert response.status_code == 200
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    claims = {"iss": "https://accounts.google.com", "aud": "test-client.apps.googleusercontent.com",
              "sub": subject, "email": email, "email_verified": True,
              "nonce": query["nonce"][0], "iat": int(datetime.now(UTC).timestamp()),
              "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())}
    claims.update(overrides or {})
    tokens["test-code"] = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    return response, query


async def complete(client, query, code="test-code"):
    return await client.get("/api/v1/auth/google/callback", params={"state": query["state"][0], "code": code})


async def test_google_requires_configuration(client):
    assert (await client.post("/api/v1/auth/google/start")).status_code == 503
    providers = (await client.get("/api/v1/auth/providers")).json()
    assert providers == {"google_configured": False, "google_connected": False, "google_email": None, "password_enabled": True}
    assert (await client.get("/api/v1/auth/google/callback")).headers["location"].endswith("google_error=google_not_configured")


async def test_google_registration_pkce_cookies_and_stable_subject(client, signing_key):
    tokens, calls = provider(client, signing_key)
    await client.post("/api/v1/auth/logout")
    response, query = await begin(client, signing_key, tokens)
    assert query["scope"] == ["openid email profile"] and query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://localhost:5173/api/v1/auth/google/callback"]
    assert "client_secret" not in response.text
    cookies = response.headers.get("set-cookie").lower()
    assert "httponly" in cookies and "samesite=lax" in cookies and "max-age=600" in cookies
    with client._transport.app.state.database.session() as session:
        attempt = session.get(OAuthAttempt, hash_refresh_token(query["state"][0]))
        challenge = urlsafe_b64encode(sha256(attempt.code_verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == query["code_challenge"][0]
    callback = await complete(client, query)
    assert callback.status_code == 303 and callback.headers["location"].endswith("/onboarding/profiles")
    assert callback.headers["cache-control"] == "no-store" and callback.headers["referrer-policy"] == "no-referrer"
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["auth_provider"] == "google" and me["role"] == "candidate"
    user_id = me["id"]
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    assert (await client.get("/api/v1/auth/providers")).json()["password_enabled"] is False
    with client._transport.app.state.database.session() as session:
        assert session.get(User, user_id).password_hash is None
        assert session.scalar(select(func.count(OAuthAttempt.state_hash))) == 0
    assert STATE_COOKIE not in client.cookies
    await client.post("/api/v1/auth/logout")
    _, query = await begin(client, signing_key, tokens, email="changed-google-email@example.com")
    assert (await complete(client, query)).status_code == 303
    assert (await client.get("/api/v1/auth/me")).json()["id"] == user_id
    # Identity is keyed by Google's stable subject, not by its current email.
    assert (await client.get("/api/v1/auth/providers")).json()["google_email"] == "changed-google-email@example.com"
    assert sum(str(request.url) == GOOGLE_CERTS for request in calls) == 1
    assert (await client.post("/api/v1/auth/login", json={"email": "google-user@example.com", "password": "arbitrary-password"})).status_code == 401


async def test_existing_password_account_requires_explicit_link_and_preserves_identity(client, signing_key):
    tokens, _ = provider(client, signing_key)
    original = (await client.get("/api/v1/auth/me")).json()
    _, query = await begin(client, signing_key, tokens, email="alex@example.com")
    response = await complete(client, query)
    assert response.headers["location"].endswith("google_error=account_exists")
    assert (await client.get("/api/v1/auth/me")).json()["id"] == original["id"]
    _, query = await begin(client, signing_key, tokens, email="alex@example.com", link=True)
    response = await complete(client, query)
    assert response.headers["location"].endswith("/settings/account?google_connected=1")
    linked = (await client.get("/api/v1/auth/me")).json()
    assert linked["id"] == original["id"] and linked["handle"] == original["handle"]
    assert linked["auth_provider"] == "password_google"
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "correct-horse-battery-staple"})).status_code == 200
    await client.post("/api/v1/auth/logout")
    _, query = await begin(client, signing_key, tokens, email="alex@example.com")
    await complete(client, query)
    assert (await client.get("/api/v1/auth/me")).json()["id"] == original["id"]


@pytest.mark.parametrize("overrides", [
    {"aud": "another-client"}, {"iss": "https://attacker.example"}, {"nonce": "wrong-nonce"},
    {"email_verified": False}, {"email_verified": 1}, {"sub": ""}, {"email": "invalid"},
    {"exp": 1}, {"azp": "another-client"}, {"iat": 9999999999},
])
async def test_invalid_google_claims_cannot_create_accounts(client, signing_key, overrides):
    tokens, _ = provider(client, signing_key)
    await client.post("/api/v1/auth/logout")
    _, query = await begin(client, signing_key, tokens, overrides=overrides)
    response = await complete(client, query)
    assert response.headers["location"].endswith("google_error=invalid_identity")
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    with client._transport.app.state.database.session() as session:
        assert session.scalar(select(func.count(OAuthIdentity.id))) == 0


async def test_forged_signature_and_algorithm_confusion_are_rejected(client, signing_key):
    tokens, _ = provider(client, signing_key)
    _, query = await begin(client, signing_key, tokens)
    claims = jwt.decode(tokens["test-code"], options={"verify_signature": False})
    tokens["test-code"] = jwt.encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256", headers={"kid": "test-key"})
    assert (await complete(client, query)).headers["location"].endswith("google_error=invalid_identity")
    _, query = await begin(client, signing_key, tokens)
    claims = jwt.decode(tokens["test-code"], options={"verify_signature": False})
    tokens["test-code"] = jwt.encode(claims, "attacker-secret-long-enough-for-hs256", algorithm="HS256", headers={"kid": "test-key"})
    assert (await complete(client, query)).headers["location"].endswith("google_error=invalid_identity")


async def test_state_cookie_expiry_cancel_and_replay_are_checked_before_google(client, signing_key):
    tokens, calls = provider(client, signing_key)
    _, query = await begin(client, signing_key, tokens)
    response = await client.get("/api/v1/auth/google/callback", params={"state": "wrong", "code": "test-code"})
    assert response.headers["location"].endswith("google_error=invalid_state") and not calls
    _, query = await begin(client, signing_key, tokens)
    with client._transport.app.state.database.session() as session:
        session.get(OAuthAttempt, hash_refresh_token(query["state"][0])).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await complete(client, query)).headers["location"].endswith("google_error=invalid_state") and not calls
    _, query = await begin(client, signing_key, tokens)
    response = await client.get("/api/v1/auth/google/callback", params={"state": query["state"][0], "error": "access_denied"})
    assert response.headers["location"].endswith("google_error=google_cancelled") and not calls
    _, query = await begin(client, signing_key, tokens)
    cookie = client.cookies.get(STATE_COOKIE)
    assert (await complete(client, query)).status_code == 303
    count = len(calls)
    response = await client.get("/api/v1/auth/google/callback", params={"state": query["state"][0], "code": "test-code"}, headers={"cookie": f"{STATE_COOKIE}={cookie}"})
    assert response.headers["location"].endswith("google_error=invalid_state") and len(calls) == count


async def test_link_requires_same_current_user_and_cannot_steal_google_identity(client, signing_key):
    tokens, _ = provider(client, signing_key)
    _, query = await begin(client, signing_key, tokens, email="alex@example.com", link=True)
    await client.post("/api/v1/auth/logout")
    assert (await complete(client, query)).headers["location"].endswith("google_error=link_session_expired")
    assert (await client.post("/api/v1/auth/google/link")).status_code == 401
    await client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "correct-horse-battery-staple"})
    _, query = await begin(client, signing_key, tokens, email="alex@example.com", link=True)
    await complete(client, query)
    await client.post("/api/v1/auth/logout")
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "handle": "other", "password": "test-password-123"})
    _, query = await begin(client, signing_key, tokens, email="alex@example.com", link=True)
    assert (await complete(client, query)).headers["location"].endswith("google_error=google_already_linked")


async def test_google_failure_does_not_erase_existing_session(client, signing_key):
    tokens, _ = provider(client, signing_key)
    original = (await client.get("/api/v1/auth/me")).json()
    _, query = await begin(client, signing_key, tokens)
    assert (await complete(client, query, "unavailable")).headers["location"].endswith("google_error=google_unavailable")
    assert (await client.get("/api/v1/auth/me")).json()["id"] == original["id"]
    _, query = await begin(client, signing_key, tokens)
    assert (await complete(client, query, "bad-code")).headers["location"].endswith("google_error=google_exchange_failed")


def test_google_redirect_configuration_rejects_unsafe_urls():
    from profligator_api.config import Settings
    for uri in ("http://external.example/callback", "https://user:secret@example.com/callback", "https://example.com/callback#fragment"):
        with pytest.raises(ValueError):
            Settings(google_client_id="test-client", google_client_secret="test-secret", google_redirect_uri=uri)
