from collections import defaultdict
import asyncio
import secrets
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.matching import MatchingService
from profligator_api.models import CodingRecord, PlatformProfile, UniqueCluster, User, UserAvatar
from profligator_api.account_profile import photo_response
from profligator_api.repository import Repository
from profligator_api.schemas import (
    ClusterResponse, CodingRecordResponse, DuplicateCheckRequest, DuplicateCheckResponse,
    Platform, PublicProfileResponse, SharingResponse, SharingUpdate,
    SolvedProblemPage, SolvedProblemResponse,
)
from profligator_api.security import get_candidate_user
from profligator_api.extension_auth import get_check_candidate

Candidate = Annotated[User, Depends(get_candidate_user)]


def create_report_router(database: Database, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def sharing_response(user: User) -> SharingResponse:
        return SharingResponse(enabled=user.is_sharing_enabled, shareable_link=(
            f"{settings.public_web_url.rstrip('/')}/p/{user.share_token}"
            if user.is_sharing_enabled and user.share_token else None
        ))

    def shared_user(session, share_token: str) -> User:
        user = session.scalar(select(User).where(User.share_token == share_token, User.is_sharing_enabled.is_(True)))
        if user is None:
            raise HTTPException(status_code=404, detail="Shared profile not found", headers={"Cache-Control": "no-store"})
        return user

    def problem_page(session, user_id: str, offset: int, limit: int, platform: Platform | None, difficulty: str | None, search: str | None) -> SolvedProblemPage:
        conditions = [
            PlatformProfile.user_id == user_id, PlatformProfile.disconnected_at.is_(None),
            CodingRecord.kind == "problem", CodingRecord.status == "solved",
        ]
        if platform is not None:
            conditions.append(PlatformProfile.platform == platform.value)
        if difficulty:
            conditions.append(func.lower(CodingRecord.difficulty) == difficulty.casefold())
        if search and search.strip():
            conditions.append(CodingRecord.title.icontains(search.strip(), autoescape=True))
        total = session.scalar(select(func.count(CodingRecord.id)).join(PlatformProfile).where(*conditions))
        rows = session.execute(select(CodingRecord, PlatformProfile).join(PlatformProfile).where(*conditions).order_by(
            CodingRecord.occurred_at.desc().nulls_last(), CodingRecord.title, CodingRecord.id,
        ).offset(offset).limit(limit))
        items = [SolvedProblemResponse(
            id=record.id, platform=profile.platform, profile_handle=profile.public_handle,
            source_id=record.source_id, title=record.title, canonical_url=record.canonical_url,
            submission_url=record.submission_url, difficulty=record.difficulty, topics=record.topics,
            solved_at=record.occurred_at,
            source_solved_at=record.source_solved_at,
            has_statement=bool(record.statement),
        ) for record, profile in rows]
        return SolvedProblemPage(items=items, total=total or 0, offset=offset, limit=limit)

    @router.get("/solved-problems", response_model=SolvedProblemPage, tags=["records"])
    async def solved_problems(
        current_user: Candidate, response: Response,
        offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
        platform: Platform | None = None, difficulty: str | None = Query(default=None, max_length=32),
        search: str | None = Query(default=None, max_length=200),
    ) -> SolvedProblemPage:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            return problem_page(session, current_user.id, offset, limit, platform, difficulty, search)

    @router.get("/public-profiles/{share_token}/solved-problems", response_model=SolvedProblemPage, tags=["sharing"])
    async def shared_solved_problems(
        share_token: str, response: Response,
        offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
        platform: Platform | None = None, difficulty: str | None = Query(default=None, max_length=32),
        search: str | None = Query(default=None, max_length=200),
    ) -> SolvedProblemPage:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            user = shared_user(session, share_token)
            return problem_page(session, user.id, offset, limit, platform, difficulty, search)

    @router.get("/sharing", response_model=SharingResponse, tags=["sharing"])
    async def get_sharing(current_user: Candidate, response: Response) -> SharingResponse:
        response.headers["Cache-Control"] = "no-store"
        return sharing_response(current_user)

    @router.put("/sharing", response_model=SharingResponse, tags=["sharing"])
    async def update_sharing(payload: SharingUpdate, current_user: Candidate, response: Response) -> SharingResponse:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            user = session.get(User, current_user.id)
            user.is_sharing_enabled = payload.enabled
            if payload.enabled:
                user.share_token = user.share_token or secrets.token_urlsafe(32)
            else:
                # Disabling sharing invalidates every previously issued link.
                user.share_token = None
            session.flush()
            return sharing_response(user)

    @router.get("/public-profiles/{share_token}", response_model=PublicProfileResponse, tags=["sharing"])
    async def public_profile(share_token: str, response: Response) -> PublicProfileResponse:
        response.headers["Cache-Control"] = "no-store"
        with database.session() as session:
            user = shared_user(session, share_token)
            return PublicProfileResponse(handle=user.handle, display_name=user.display_name, bio=user.bio,
                avatar_url=f"/api/v1/public-profiles/{share_token}/avatar?v={user.avatar_revision}" if user.avatar_revision else None,
                dashboard=Repository(session).dashboard(user.id,
                leetcode_collect_contests=settings.leetcode_collect_contests, semantic_matching=settings.matching_backend != "disabled"))

    @router.get("/public-profiles/{share_token}/avatar", tags=["sharing"])
    async def public_avatar(share_token: str):
        with database.session() as session:
            user = shared_user(session, share_token)
            avatar = session.get(UserAvatar, user.id)
            if avatar is None:
                raise HTTPException(status_code=404, detail="No shared profile photo is available.")
            return photo_response(avatar.data)

    @router.get("/coding-records", response_model=list[CodingRecordResponse], tags=["records"])
    async def coding_records(current_user: Candidate, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)) -> list[CodingRecordResponse]:
        with database.session() as session:
            records = session.scalars(select(CodingRecord).join(PlatformProfile).where(
                PlatformProfile.user_id == current_user.id, PlatformProfile.disconnected_at.is_(None),
            ).order_by(CodingRecord.created_at, CodingRecord.id).offset(offset).limit(limit))
            return [CodingRecordResponse.model_validate(record) for record in records]

    @router.get("/unique-clusters", response_model=list[ClusterResponse], tags=["matching"])
    async def clusters(current_user: Candidate, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)) -> list[ClusterResponse]:
        with database.session() as session:
            active_clusters = select(CodingRecord.cluster_id).join(PlatformProfile).where(
                PlatformProfile.user_id == current_user.id, PlatformProfile.disconnected_at.is_(None),
                CodingRecord.kind == "problem", CodingRecord.status == "solved",
            )
            selected = list(session.scalars(select(UniqueCluster).where(
                UniqueCluster.user_id == current_user.id, UniqueCluster.id.in_(active_clusters),
            ).order_by(UniqueCluster.created_at, UniqueCluster.id).offset(offset).limit(limit)))
            records = session.scalars(select(CodingRecord).join(PlatformProfile).where(
                PlatformProfile.user_id == current_user.id, PlatformProfile.disconnected_at.is_(None),
                CodingRecord.cluster_id.in_([cluster.id for cluster in selected]),
                CodingRecord.kind == "problem", CodingRecord.status == "solved",
            ).order_by(CodingRecord.occurred_at, CodingRecord.id))
            grouped = defaultdict(list)
            for record in records:
                grouped[record.cluster_id].append(CodingRecordResponse.model_validate(record))
            return [ClusterResponse(id=cluster.id, base_problem_title=cluster.base_problem_title, records=grouped[cluster.id]) for cluster in selected]

    @router.post("/extension/check", response_model=DuplicateCheckResponse, tags=["extension"])
    async def check_duplicate(payload: DuplicateCheckRequest, current_user: Annotated[User, Depends(get_check_candidate)]) -> DuplicateCheckResponse:
        hosts = {"leetcode": {"leetcode.com"}, "geeksforgeeks": {"geeksforgeeks.org", "practice.geeksforgeeks.org"}, "codeforces": {"codeforces.com", "mirror.codeforces.com"}}
        host = (urlparse(payload.canonical_url).hostname or "").lower().removeprefix("www.")
        if host not in hosts[payload.platform.value]:
            raise HTTPException(status_code=422, detail="Problem URL does not match the selected platform")
        try:
            return await asyncio.wait_for(
                MatchingService(database, settings).check(current_user.id, payload),
                timeout=settings.matching_check_timeout_seconds,
            )
        except TimeoutError:
            return DuplicateCheckResponse(duplicate=False, status="matching_unavailable")

    return router
