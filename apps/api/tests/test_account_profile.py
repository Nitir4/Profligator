from io import BytesIO

import httpx
import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy.exc import IntegrityError

from profligator_api.account_profile import MAX_UPLOAD_BYTES
from profligator_api.models import User, UserAvatar
from profligator_api.repository import Repository
from test_extension_auth import grant
from test_report_backend import seed


def photo(fmt="PNG", **options):
    output = BytesIO()
    Image.new("RGB", (120, 80), "teal").save(output, fmt, **options)
    return output.getvalue()


async def test_profile_edit_preserves_identity_history_sessions_and_share_link(client: httpx.AsyncClient):
    database = client._transport.app.state.database
    user_id, profiles = seed(database)
    issued = await grant(client)
    link = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"]
    token = link.rsplit("/", 1)[1]
    old = (await client.get("/api/v1/auth/me")).json()
    assert old["display_name"] == old["bio"] == "" and old["avatar_url"] is None
    updated = await client.put("/api/v1/account/profile", json={
        "handle": "  Alex.New-Name  ", "display_name": "  Alex Developer  ", "bio": "  Building useful tools.  "})
    assert updated.status_code == 200, updated.text
    user = updated.json()
    assert user["id"] == user_id == old["id"]
    assert user["email"] == old["email"] and user["role"] == old["role"]
    assert (user["handle"], user["display_name"], user["bio"]) == ("Alex.New-Name", "Alex Developer", "Building useful tools.")
    assert (await client.get("/api/v1/auth/me")).json() == user
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    assert (await client.get("/api/v1/auth/me")).json() == user
    extension = await client.get("/api/v1/extension/session", headers={"Authorization": f"Bearer {issued['token']}"})
    assert extension.status_code == 200 and extension.json()["handle"] == user["handle"]
    assert (await client.get("/api/v1/dashboard")).json()["total_problems_solved"] == 2
    assert {p["id"] for p in (await client.get("/api/v1/platform-profiles")).json()} == set(profiles)
    assert (await client.get("/api/v1/sharing")).json()["shareable_link"] == link
    public = (await client.get(f"/api/v1/public-profiles/{token}")).json()
    assert public["display_name"] == user["display_name"] and public["bio"] == user["bio"]
    assert "email" not in public
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/login", json={"email": old["email"], "password": "correct-horse-battery-staple"})).status_code == 200
    assert (await client.get("/api/v1/auth/me")).json()["handle"] == "Alex.New-Name"


async def test_case_insensitive_username_conflicts_are_enforced_in_api_and_database(client: httpx.AsyncClient):
    database = client._transport.app.state.database
    with database.session() as session:
        Repository(session).create_user(email="taken@example.com", handle="AlreadyTaken", password_hash="test-only")
    response = await client.put("/api/v1/account/profile", json={"handle": "alreadytaken"})
    assert response.status_code == 409
    assert (await client.get("/api/v1/auth/me")).json()["handle"] == "alex_dev96"
    assert (await client.put("/api/v1/account/profile", json={"handle": "ALEX_DEV96"})).status_code == 200
    with pytest.raises(IntegrityError):
        with database.session() as session:
            Repository(session).create_user(email="race@example.com", handle="alreadyTAKEN", password_hash="test-only")
    assert (await client.post("/api/v1/auth/register", json={"email": "register@example.com", "handle": "ALREADYTAKEN", "password": "a-long-enough-password"})).status_code == 409


@pytest.mark.parametrize("payload", [
    {"handle": "ab"}, {"handle": "bad name"}, {"handle": "name/route"},
    {"handle": "valid", "display_name": "A" * 81}, {"handle": "valid", "display_name": "First\nLast"},
    {"handle": "valid", "bio": "b" * 281}, {"handle": "valid", "role": "recruiter"},
    {"handle": "valid", "email": "not-yours@example.com"}, {"handle": "valid", "id": "another-user"},
])
async def test_profile_validation_and_field_allowlist(client: httpx.AsyncClient, payload):
    assert (await client.put("/api/v1/account/profile", json=payload)).status_code == 422
    assert (await client.get("/api/v1/auth/me")).json()["handle"] == "alex_dev96"


async def test_profile_mutations_require_owner_session_and_trusted_origin(client: httpx.AsyncClient):
    bad = {"Origin": "https://other.test"}
    assert (await client.put("/api/v1/account/profile", json={"handle": "new_name"}, headers=bad)).status_code == 403
    assert (await client.put("/api/v1/account/avatar", content=photo(), headers={**bad, "Content-Type": "image/png"})).status_code == 403
    assert (await client.delete("/api/v1/account/avatar", headers=bad)).status_code == 403
    issued = await grant(client)
    assert (await client.put("/api/v1/account/profile", json={"handle": "new_name"}, headers={"Authorization": f"Bearer {issued['token']}"})).status_code == 401
    await client.post("/api/v1/auth/logout")
    for method, path, kwargs in [("put", "/profile", {"json": {"handle": "new_name"}}), ("put", "/avatar", {"content": photo()}), ("delete", "/avatar", {}), ("get", "/avatar", {})]:
        assert (await getattr(client, method)("/api/v1/account" + path, **kwargs)).status_code == 401


@pytest.mark.parametrize("fmt,content_type", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
async def test_photos_are_normalized_and_metadata_removed(client: httpx.AsyncClient, fmt, content_type):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "SECRET METADATA")
    uploaded = await client.put("/api/v1/account/avatar", content=photo(fmt, pnginfo=metadata), headers={"Content-Type": content_type})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["avatar_url"].startswith("/api/v1/account/avatar?v=")
    fetched = await client.get(uploaded.json()["avatar_url"])
    assert fetched.status_code == 200 and fetched.headers["content-type"] == "image/jpeg"
    assert fetched.headers["cache-control"] == "private, no-store"
    assert fetched.headers["x-content-type-options"] == "nosniff"
    with Image.open(BytesIO(fetched.content)) as image:
        assert image.size == (384, 384) and image.mode == "RGB"
        assert not image.getexif() and "private" not in image.info
    assert b"SECRET METADATA" not in fetched.content
    user_id = uploaded.json()["id"]
    with client._transport.app.state.database.session() as session:
        assert session.get(UserAvatar, user_id).data == fetched.content


async def test_photo_is_private_except_through_active_share_and_removal_revokes_access(client: httpx.AsyncClient):
    assert (await client.get("/api/v1/account/avatar")).status_code == 404
    user = (await client.put("/api/v1/account/avatar", content=photo(), headers={"Content-Type": "image/png"})).json()
    first = (await client.get(user["avatar_url"])).content
    token = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"].rsplit("/", 1)[1]
    public_url = (await client.get(f"/api/v1/public-profiles/{token}")).json()["avatar_url"]
    assert public_url and token in public_url
    await client.post("/api/v1/auth/logout")
    assert (await client.get(user["avatar_url"])).status_code == 401
    assert (await client.get(public_url)).content == first
    await client.post("/api/v1/auth/register", json={"email": "other@example.com", "handle": "other_account", "password": "a-long-enough-password"})
    assert (await client.get("/api/v1/account/avatar")).status_code == 404
    assert (await client.delete("/api/v1/account/avatar")).status_code == 200
    assert (await client.get(public_url)).status_code == 200  # another owner cannot remove it
    await client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "correct-horse-battery-staple"})
    assert (await client.put("/api/v1/sharing", json={"enabled": False})).status_code == 200
    assert (await client.get(public_url)).status_code == 404
    new_token = (await client.put("/api/v1/sharing", json={"enabled": True})).json()["shareable_link"].rsplit("/", 1)[1]
    new_url = (await client.get(f"/api/v1/public-profiles/{new_token}")).json()["avatar_url"]
    assert (await client.delete("/api/v1/account/avatar")).json()["avatar_url"] is None
    assert (await client.get(new_url)).status_code == 404
    with client._transport.app.state.database.session() as session:
        assert session.get(UserAvatar, user["id"]) is None
        assert session.get(User, user["id"]).avatar_revision is None


async def test_invalid_large_and_animated_uploads_preserve_existing_photo(client: httpx.AsyncClient):
    await client.put("/api/v1/account/avatar", content=photo(), headers={"Content-Type": "image/png"})
    original = (await client.get("/api/v1/account/avatar")).content
    animated = BytesIO()
    Image.new("RGB", (10, 10), "red").save(animated, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")], duration=100)
    big = BytesIO()
    Image.new("L", (4001, 4000)).save(big, "PNG")
    for data, content_type, status in [(b"<svg/>", "image/svg+xml", 415), (b"not an image", "image/png", 415),
            (b"x" * (MAX_UPLOAD_BYTES + 1), "image/png", 413), (animated.getvalue(), "image/png", 415),
            (big.getvalue(), "image/png", 413), (b"", "image/png", 415)]:
        response = await client.put("/api/v1/account/avatar", content=data, headers={"Content-Type": content_type})
        assert response.status_code == status, response.text
        assert (await client.get("/api/v1/account/avatar")).content == original
