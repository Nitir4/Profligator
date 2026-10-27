from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class ProblemMetadata(Base):
    __tablename__ = "problem_metadata"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    bio: Mapped[str] = mapped_column(String(280), default="", server_default="", nullable=False)
    avatar_revision: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (Index("uq_users_handle_lower", func.lower(handle), unique=True),)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    auth_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(32), default="password", nullable=False)
    is_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    platform_profiles: Mapped[list["PlatformProfile"]] = relationship(back_populates="user")
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(back_populates="user")

    @property
    def avatar_url(self) -> str | None:
        return f"/api/v1/account/avatar?v={self.avatar_revision}" if self.avatar_revision else None


class UserAvatar(Base):
    __tablename__ = "user_avatars"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(320), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerifiedEmail(Base):
    __tablename__ = "verified_emails"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordResetRateLimit(Base):
    __tablename__ = "password_reset_rate_limits"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    link_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="refresh_sessions")


class ExtensionSession(Base):
    __tablename__ = "extension_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformProfile(Base):
    __tablename__ = "platform_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "public_handle", name="uq_profile_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    public_handle: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(512), nullable=False)
    verification_state: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    source_total_solved: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[str | None] = mapped_column(String(128))
    history_complete: Mapped[bool | None] = mapped_column(Boolean)
    source_difficulty_counts: Mapped[dict | None] = mapped_column(JSON)
    activity_status: Mapped[str] = mapped_column(String(32), default="unsupported", nullable=False)
    activity_available_years: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    activity_error: Mapped[str | None] = mapped_column(String(64))
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="platform_profiles")
    sync_runs: Mapped[list["SyncRun"]] = relationship(back_populates="platform_profile")
    coding_records: Mapped[list["CodingRecord"]] = relationship(back_populates="platform_profile")


class ProfileActivityCalendar(Base):
    __tablename__ = "profile_activity_calendars"

    platform_profile_id: Mapped[str] = mapped_column(ForeignKey("platform_profiles.id"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    days: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform_profile_id: Mapped[str] = mapped_column(
        ForeignKey("platform_profiles.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    matching_status: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    platform_profile: Mapped[PlatformProfile] = relationship(back_populates="sync_runs")


class UniqueCluster(Base):
    __tablename__ = "unique_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    base_problem_title: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CodingRecord(Base):
    __tablename__ = "coding_records"
    __table_args__ = (
        UniqueConstraint(
            "platform_profile_id", "source_id", "kind", name="uq_profile_source_record"
        ),
        Index("ix_coding_records_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    platform_profile_id: Mapped[str] = mapped_column(
        ForeignKey("platform_profiles.id"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    canonical_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(64), index=True)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_solved_at: Mapped[str | None] = mapped_column(String(32))
    source_payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("unique_clusters.id"), index=True)
    statement: Mapped[str | None] = mapped_column(Text)
    submission_url: Mapped[str | None] = mapped_column(String(1024))
    contest_rating: Mapped[int | None] = mapped_column(Integer)
    global_rank: Mapped[int | None] = mapped_column(Integer)
    similarity_score: Mapped[float | None] = mapped_column(Float)
    matching_state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    platform_profile: Mapped[PlatformProfile] = relationship(back_populates="coding_records")


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_id: Mapped[str] = mapped_column(ForeignKey("coding_records.id"), index=True)
    candidate_record_id: Mapped[str] = mapped_column(ForeignKey("coding_records.id"))
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderRequestWindow(Base):
    __tablename__ = "provider_request_windows"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    next_request_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
