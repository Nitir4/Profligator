"""Owner-edited account details and small, persistent profile photographs."""
from hashlib import sha256
from io import BytesIO
from typing import Annotated
import warnings

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.models import User, UserAvatar
from profligator_api.repository import Repository
from profligator_api.schemas import UserResponse
from profligator_api.security import get_current_user

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=280)

    @field_validator("handle", "display_name", "bio", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("display_name")
    @classmethod
    def single_line_name(cls, value):
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Use a single line for your display name")
        return value


def photo_response(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="profile-photo.jpg"',
    })


def normalize_photo(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="Choose an image with at most 16 megapixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(status_code=415, detail="Choose a still photo, not an animated image.")
                image.verify()
            with Image.open(BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGBA")
                square = ImageOps.fit(oriented, (384, 384), method=Image.Resampling.LANCZOS)
                # A fresh RGB canvas discards source EXIF/ICC/text metadata.
                clean = Image.new("RGB", square.size, "white")
                clean.paste(square, mask=square.getchannel("A"))
                output = BytesIO()
                clean.save(output, "JPEG", quality=85, optimize=True)
                return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=415, detail="Upload a valid JPEG, PNG or WebP photo.") from exc


def create_account_profile_router(database: Database, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/account", tags=["account profile"])
    owner = Annotated[User, Depends(get_current_user)]

    def trusted_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is not None and origin not in {settings.public_web_url.rstrip("/"), *settings.cors_origins}:
            raise HTTPException(status_code=403, detail="Edit your profile from the Profligator application.")

    @router.put("/profile", response_model=UserResponse)
    async def update_profile(payload: ProfileUpdate, request: Request, response: Response, current: owner):
        trusted_origin(request)
        response.headers["Cache-Control"] = "no-store"
        try:
            with database.session() as session:
                repo = Repository(session)
                other = repo.get_user_by_handle(payload.handle)
                if other is not None and other.id != current.id:
                    raise HTTPException(status_code=409, detail="That username is already taken. Choose another one.")
                user = repo.get_user(current.id)
                user.handle, user.display_name, user.bio = payload.handle, payload.display_name, payload.bio
                session.flush()
                return UserResponse.model_validate(user)
        except IntegrityError as exc:
            # The unique index also covers concurrent attempts for the same name.
            raise HTTPException(status_code=409, detail="That username is already taken. Choose another one.") from exc

    @router.put("/avatar", response_model=UserResponse)
    async def upload_avatar(request: Request, response: Response, current: owner):
        trusted_origin(request)
        if request.headers.get("content-type", "").split(";")[0] not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=415, detail="Choose a JPEG, PNG or WebP photo.")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Choose a photo smaller than 4 MB.")
            data.extend(chunk)
        processed = await run_in_threadpool(normalize_photo, bytes(data))
        with database.session() as session:
            user = session.get(User, current.id)
            avatar = session.get(UserAvatar, current.id)
            if avatar is None:
                session.add(UserAvatar(user_id=current.id, data=processed))
            else:
                avatar.data = processed
            user.avatar_revision = sha256(processed).hexdigest()
            session.flush()
            response.headers["Cache-Control"] = "no-store"
            return UserResponse.model_validate(user)

    @router.get("/avatar")
    async def get_avatar(current: owner):
        with database.session() as session:
            avatar = session.get(UserAvatar, current.id)
            if avatar is None:
                raise HTTPException(status_code=404, detail="No profile photo is set.")
            return photo_response(avatar.data)

    @router.delete("/avatar", response_model=UserResponse)
    async def remove_avatar(request: Request, response: Response, current: owner):
        trusted_origin(request)
        with database.session() as session:
            user = session.get(User, current.id)
            avatar = session.get(UserAvatar, current.id)
            if avatar is not None:
                session.delete(avatar)
            user.avatar_revision = None
            session.flush()
            response.headers["Cache-Control"] = "no-store"
            return UserResponse.model_validate(user)

    return router
