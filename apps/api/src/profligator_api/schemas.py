from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Platform(StrEnum):
    LEETCODE = "leetcode"
    GEEKSFORGEEKS = "geeksforgeeks"
    CODEFORCES = "codeforces"


class ConnectorMode(StrEnum):
    FIXTURE = "fixture"
    OFFICIAL_API = "official_api"


class RecordKind(StrEnum):
    PROBLEM = "problem"
    CONTEST = "contest"


class RecordStatus(StrEnum):
    SOLVED = "solved"
    ATTEMPTED = "attempted"
    PARTICIPATED = "participated"


class SyncStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VerificationState(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    FIXTURE_ONLY = "fixture_only"


class AuthRegister(BaseModel):
    email: EmailStr
    handle: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)


class AuthLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    handle: str
    created_at: datetime


class AuthSessionResponse(BaseModel):
    user: UserResponse
    access_expires_at: datetime


class CanonicalProfile(BaseModel):
    platform: Platform
    handle: str
    canonical_url: str
    display_name: str | None = None


class NormalizedRecord(BaseModel):
    platform: Platform
    source_id: str
    kind: RecordKind
    status: RecordStatus
    title: str
    canonical_url: str
    difficulty: str | None = None
    topics: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None
    source_payload_checksum: str


class ProfileSnapshot(BaseModel):
    profile: CanonicalProfile
    fetched_at: datetime
    source_total_solved: int | None = None
    rating: int | None = None
    rank: str | None = None


class ConnectorPage(BaseModel):
    records: list[NormalizedRecord]
    next_cursor: str | None = None


class ConnectorDescriptor(BaseModel):
    platform: Platform
    mode: ConnectorMode
    live_data: bool
    notice: str


class ProfileCheckRequest(BaseModel):
    platform: Platform
    handle_or_url: str = Field(min_length=1, max_length=512)


class ProfileCheckResponse(BaseModel):
    profile: CanonicalProfile
    mode: ConnectorMode
    live_data: bool
    notice: str


class PlatformProfileCreate(ProfileCheckRequest):
    pass


class PlatformProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: Platform
    public_handle: str
    canonical_url: str
    verification_state: VerificationState
    connector_mode: ConnectorMode
    last_successful_sync: datetime | None
    created_at: datetime
    updated_at: datetime


class SyncCreate(BaseModel):
    platform_profile_id: str


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform_profile_id: str
    status: SyncStatus
    records_seen: int
    records_written: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DashboardPlatformSummary(BaseModel):
    platform: Platform
    profile_handle: str
    solved: int
    last_successful_sync: datetime | None


class DashboardActivityDay(BaseModel):
    date: date
    count: int


class DashboardActivitySummary(BaseModel):
    days: list[DashboardActivityDay]
    known_timestamp_records: int
    unknown_timestamp_records: int
    current_streak: int
    longest_streak: int


class DashboardBreakdownItem(BaseModel):
    name: str
    count: int
    percent: float


class DashboardTopicSummary(BaseModel):
    items: list[DashboardBreakdownItem]
    total_assignments: int
    records_without_topics: int


class DashboardDifficultySummary(BaseModel):
    items: list[DashboardBreakdownItem]
    rated_records: int
    unrated_records: int


class DashboardResponse(BaseModel):
    total_problems_solved: int
    provisional_unique_problems: int
    connected_profiles: int
    platforms: list[DashboardPlatformSummary]
    activity: DashboardActivitySummary
    topics: DashboardTopicSummary
    difficulties: DashboardDifficultySummary
    data_state: str
    partial_reasons: list[str]
    last_successful_sync: datetime | None
    generated_at: datetime
    uniqueness_notice: str = (
        "Unique counts currently use normalized titles; semantic matching is not implemented yet."
    )


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
