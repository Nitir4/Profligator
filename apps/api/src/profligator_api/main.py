from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from profligator_api import __version__
from profligator_api.config import Settings, get_settings
from profligator_api.connectors import ConnectorError, ConnectorRegistry
from profligator_api.database import Database
from profligator_api.jobs import SyncDispatchError, SyncDispatcher
from profligator_api.models import User
from profligator_api.repository import Repository
from profligator_api.schemas import (
    AuthLogin,
    AuthRegister,
    AuthSessionResponse,
    ConnectorDescriptor,
    DashboardResponse,
    HealthResponse,
    PlatformProfileCreate,
    PlatformProfileResponse,
    ProfileCheckRequest,
    ProfileCheckResponse,
    SyncCreate,
    SyncRunResponse,
    UserResponse,
)
from profligator_api.security import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    create_access_token,
    get_current_user,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    set_auth_cookies,
    verify_password,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    database = Database(app_settings.database_url)
    registry = ConnectorRegistry(app_settings)
    sync_dispatcher = SyncDispatcher(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if app_settings.auto_create_schema:
            database.initialize()
        yield
        database.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description=(
            "Profile aggregation API. LeetCode and GeeksforGeeks operate from sanitized "
            "fixtures until an approved provider integration is available."
        ),
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.database = database
    app.state.connectors = registry
    app.state.sync_dispatcher = sync_dispatcher
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(ConnectorError)
    async def connector_error_handler(_: Request, exc: ConnectorError) -> JSONResponse:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.retryable
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return JSONResponse(
            status_code=code,
            content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}},
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        try:
            database.ping()
            database_status = "ok"
        except Exception:
            database_status = "unavailable"
        return HealthResponse(
            status="ok" if database_status == "ok" else "degraded",
            service=app_settings.app_name,
            version=__version__,
            database=database_status,
        )

    def create_session_response(
        response: Response, repository: Repository, user: User
    ) -> AuthSessionResponse:
        access_token, access_expires_at = create_access_token(user.id, app_settings)
        refresh_token, refresh_hash = new_refresh_token()
        repository.create_refresh_session(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC) + timedelta(days=app_settings.refresh_token_days),
        )
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            settings=app_settings,
        )
        return AuthSessionResponse(
            user=UserResponse.model_validate(user),
            access_expires_at=access_expires_at,
        )

    @app.post(
        "/api/v1/auth/register",
        response_model=AuthSessionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["auth"],
    )
    async def register(payload: AuthRegister, response: Response) -> AuthSessionResponse:
        try:
            with database.session() as session:
                repository = Repository(session)
                if repository.get_user_by_email(str(payload.email)) is not None:
                    raise HTTPException(
                        status_code=409, detail="An account with this email exists"
                    )
                if repository.get_user_by_handle(payload.handle) is not None:
                    raise HTTPException(status_code=409, detail="This handle is already taken")
                user = repository.create_user(
                    email=str(payload.email),
                    handle=payload.handle,
                    password_hash=hash_password(payload.password),
                )
                return create_session_response(response, repository, user)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Email or handle already exists") from exc

    @app.post(
        "/api/v1/auth/login",
        response_model=AuthSessionResponse,
        tags=["auth"],
    )
    async def login(payload: AuthLogin, response: Response) -> AuthSessionResponse:
        with database.session() as session:
            repository = Repository(session)
            user = repository.get_user_by_email(str(payload.email))
            password_valid = verify_password(
                payload.password, user.password_hash if user is not None else None
            )
            if user is None or not password_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password",
                )
            return create_session_response(response, repository, user)

    @app.post(
        "/api/v1/auth/refresh",
        response_model=AuthSessionResponse,
        tags=["auth"],
    )
    async def refresh(request: Request, response: Response) -> AuthSessionResponse:
        refresh_token = request.cookies.get(REFRESH_COOKIE)
        if refresh_token is None:
            raise HTTPException(status_code=401, detail="Refresh session required")
        refresh_hash = hash_refresh_token(refresh_token)
        with database.session() as session:
            repository = Repository(session)
            refresh_session = repository.get_active_refresh_session(refresh_hash)
            if refresh_session is None:
                clear_auth_cookies(response, app_settings)
                raise HTTPException(status_code=401, detail="Refresh session is invalid")
            user = repository.get_user(refresh_session.user_id)
            if user is None:
                clear_auth_cookies(response, app_settings)
                raise HTTPException(status_code=401, detail="Refresh session is invalid")
            repository.revoke_refresh_session(refresh_hash)
            return create_session_response(response, repository, user)

    @app.post(
        "/api/v1/auth/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["auth"],
    )
    async def logout(request: Request, response: Response) -> Response:
        refresh_token = request.cookies.get(REFRESH_COOKIE)
        if refresh_token is not None:
            with database.session() as session:
                Repository(session).revoke_refresh_session(hash_refresh_token(refresh_token))
        clear_auth_cookies(response, app_settings)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"])
    async def me(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> UserResponse:
        return UserResponse.model_validate(current_user)

    @app.get(
        "/api/v1/connectors",
        response_model=list[ConnectorDescriptor],
        tags=["connectors"],
    )
    async def connectors() -> list[ConnectorDescriptor]:
        return registry.descriptors()

    @app.post(
        "/api/v1/platform-profiles/check",
        response_model=ProfileCheckResponse,
        tags=["profiles"],
    )
    async def check_profile(
        payload: ProfileCheckRequest,
        _: Annotated[User, Depends(get_current_user)],
    ) -> ProfileCheckResponse:
        connector = registry.get(payload.platform)
        profile = await connector.validate_handle(payload.handle_or_url)
        return ProfileCheckResponse(
            profile=profile,
            mode=connector.descriptor.mode,
            live_data=connector.descriptor.live_data,
            notice=connector.descriptor.notice,
        )

    @app.post(
        "/api/v1/platform-profiles",
        response_model=PlatformProfileResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["profiles"],
    )
    async def link_profile(
        payload: PlatformProfileCreate,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> PlatformProfileResponse:
        connector = registry.get(payload.platform)
        canonical = await connector.validate_handle(payload.handle_or_url)
        with database.session() as session:
            profile = Repository(session).save_profile(
                current_user.id,
                canonical,
                connector.descriptor.mode,
                live_data=connector.descriptor.live_data,
            )
            return PlatformProfileResponse.model_validate(profile)

    @app.get(
        "/api/v1/platform-profiles",
        response_model=list[PlatformProfileResponse],
        tags=["profiles"],
    )
    async def list_profiles(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> list[PlatformProfileResponse]:
        with database.session() as session:
            profiles = Repository(session).list_profiles(current_user.id)
            return [PlatformProfileResponse.model_validate(profile) for profile in profiles]

    @app.delete(
        "/api/v1/platform-profiles/{profile_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["profiles"],
    )
    async def disconnect_profile(
        profile_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> Response:
        with database.session() as session:
            disconnected = Repository(session).disconnect_profile(profile_id, current_user.id)
            if not disconnected:
                raise HTTPException(status_code=404, detail="Platform profile not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/syncs",
        response_model=SyncRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["syncs"],
    )
    async def create_sync(
        payload: SyncCreate,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> SyncRunResponse:
        with database.session() as session:
            repository = Repository(session)
            saved_profile = repository.get_profile(payload.platform_profile_id, current_user.id)
            if saved_profile is None:
                raise HTTPException(status_code=404, detail="Platform profile not found")
            run = repository.start_sync(saved_profile.id)
            run_id = run.id
        try:
            completed = await sync_dispatcher.dispatch(run_id)
        except SyncDispatchError as exc:
            with database.session() as session:
                repository = Repository(session)
                run = repository.get_sync(run_id)
                if run is None:
                    raise RuntimeError("Sync run disappeared during queue dispatch") from exc
                repository.fail_sync(
                    run,
                    code="queue_unavailable",
                    message="The profile sync queue is unavailable",
                )
            raise HTTPException(status_code=503, detail="Profile sync queue unavailable") from exc

        if completed is not None:
            return completed
        with database.session() as session:
            queued = Repository(session).get_sync(run_id)
            if queued is None:
                raise RuntimeError("Sync run disappeared after queue dispatch")
            return SyncRunResponse.model_validate(queued)

    @app.get(
        "/api/v1/syncs/{sync_id}",
        response_model=SyncRunResponse,
        tags=["syncs"],
    )
    async def get_sync(
        sync_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> SyncRunResponse:
        with database.session() as session:
            run = Repository(session).get_sync_for_user(sync_id, current_user.id)
            if run is None:
                raise HTTPException(status_code=404, detail="Sync run not found")
            return SyncRunResponse.model_validate(run)

    @app.get("/api/v1/dashboard", response_model=DashboardResponse, tags=["dashboard"])
    async def dashboard(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> DashboardResponse:
        with database.session() as session:
            return Repository(session).dashboard(current_user.id)

    return app


app = create_app()
