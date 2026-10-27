from datetime import UTC, date, datetime
from enum import StrEnum

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Topic = Annotated[str, Field(max_length=128)]


def stored_utc_time(value: datetime | None) -> datetime | None:
    # SQLite drops timezone metadata from UTC database instants. Unzoned provider
    # clocks are stored separately in source_solved_at and never reach this field.
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class Platform(StrEnum):
    LEETCODE = "leetcode"
    GEEKSFORGEEKS = "geeksforgeeks"
    CODEFORCES = "codeforces"


class ConnectorMode(StrEnum):
    FIXTURE = "fixture"
    OFFICIAL_API = "official_api"
    AGGREGATOR = "aggregator"
    SCRAPER = "scraper"


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


class UserRole(StrEnum):
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"


class AuthRegister(BaseModel):
    email: EmailStr
    handle: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.CANDIDATE


class AuthLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    handle: str
    display_name: str = ""
    bio: str = ""
    avatar_url: str | None = None
    created_at: datetime
    role: UserRole
    auth_provider: str


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
    source_id: str = Field(min_length=1, max_length=160)
    kind: RecordKind
    status: RecordStatus
    title: str = Field(min_length=1, max_length=512)
    canonical_url: str = Field(max_length=1024)
    difficulty: str | None = None
    topics: list[Topic] = Field(default_factory=list, max_length=50)
    occurred_at: datetime | None = None
    source_solved_at: str | None = Field(default=None, max_length=32)
    source_payload_checksum: str = Field(min_length=1, max_length=64)
    statement: str | None = Field(default=None, max_length=50000)
    submission_url: str | None = Field(default=None, max_length=1024)
    contest_rating: int | None = None
    global_rank: int | None = Field(default=None, ge=1)

    @field_validator("canonical_url", "submission_url")
    @classmethod
    def public_url(cls, value: str | None) -> str | None:
        from urllib.parse import urlparse

        if value is not None:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
                raise ValueError("Expected a public HTTPS URL")
        return value


class ProfileSnapshot(BaseModel):
    profile: CanonicalProfile
    fetched_at: datetime
    source_total_solved: int | None = None
    rating: int | None = None
    rank: str | None = None
    history_complete: bool | None = None
    source_difficulty_counts: dict[str, int] | None = None


class ActivityDay(BaseModel):
    date: date
    count: int = Field(ge=0, strict=True)


class ActivityCalendar(BaseModel):
    year: int = Field(ge=2010, le=2100)
    days: list[ActivityDay] = Field(max_length=366)
    fetched_at: datetime

    @model_validator(mode="after")
    def validate_days(self) -> "ActivityCalendar":
        if any(day.date.year != self.year for day in self.days):
            raise ValueError("Calendar dates must belong to the requested year")
        if len({day.date for day in self.days}) != len(self.days):
            raise ValueError("Calendar dates must be unique")
        if self.fetched_at.tzinfo is None:
            raise ValueError("Calendar fetch time must include its time zone")
        return self


class CalendarCollection(BaseModel):
    status: Literal["available", "partial", "unavailable", "unsupported"] = "unsupported"
    calendars: list[ActivityCalendar] = Field(default_factory=list, max_length=10)
    available_years: list[int] = Field(default_factory=list, max_length=100)
    error_code: str | None = None


class ConnectorPage(BaseModel):
    records: list[NormalizedRecord] = Field(max_length=1000)
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
    source_total_solved: int | None = None
    rating: int | None = None
    rank: str | None = None
    history_complete: bool | None = None


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
    matching_status: str | None = None


class DashboardPlatformSummary(BaseModel):
    verification_state: VerificationState = VerificationState.UNVERIFIED
    platform: Platform
    profile_handle: str
    solved: int
    last_successful_sync: datetime | None
    unique_solved: int = 0
    source_total_solved: int | None = None
    rating: int | None = None
    rank: str | None = None
    contests_enabled: bool = True
    history_complete: bool | None = None
    connector_mode: ConnectorMode = ConnectorMode.FIXTURE
    latest_sync_status: SyncStatus | None = None
    sync_error: str | None = None
    source_difficulty_counts: dict[str, int] | None = None
    activity_status: str = "unsupported"
    activity_years: list[int] = Field(default_factory=list)
    activity_available_years: list[int] = Field(default_factory=list)
    activity_error: str | None = None
    questions_with_statements: int = 0
    questions_with_utc_dates: int = 0
    questions_with_source_times: int = 0


class DashboardActivityDay(BaseModel):
    date: date
    count: int


class DashboardSourceCalendar(BaseModel):
    platform: Platform
    profile_handle: str
    days: list[DashboardActivityDay]


class DashboardActivitySummary(BaseModel):
    days: list[DashboardActivityDay]
    known_timestamp_records: int
    unknown_timestamp_records: int
    current_streak: int
    longest_streak: int
    count_label: str = "dated solved records"
    timezone: str = "UTC"
    calendar_submissions: int = 0
    calendar_profiles: int = 0
    source_calendars: list[DashboardSourceCalendar] = Field(default_factory=list)


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
    unique_problems_solved: int = 0
    matched_records: int = 0
    unmatched_records: int = 0
    contests: list["ContestResponse"] = Field(default_factory=list)
    uniqueness_notice: str = "Unique counts group confirmed duplicates; unchecked records count separately."
    semantic_matching: str = "disabled"
    records_with_statements: int = 0
    records_without_statements: int = 0
    matching_unavailable_records: int = 0
    exact_matched_records: int = 0
    semantic_matched_records: int = 0


class ContestResponse(BaseModel):
    platform: Platform
    source_id: str
    title: str
    canonical_url: str
    occurred_at: datetime | None
    contest_rating: int | None
    global_rank: int | None


class SharingUpdate(BaseModel):
    enabled: bool


class SharingResponse(BaseModel):
    enabled: bool
    shareable_link: str | None


class PublicProfileResponse(BaseModel):
    handle: str
    display_name: str = ""
    bio: str = ""
    avatar_url: str | None = None
    dashboard: DashboardResponse


class DuplicateCheckRequest(BaseModel):
    platform: Platform
    source_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=512)
    canonical_url: str = Field(max_length=1024)
    statement: str | None = Field(default=None, min_length=1, max_length=50000)
    topics: list[Topic] = Field(default_factory=list, max_length=50)

    _public_url = field_validator("canonical_url")(NormalizedRecord.public_url.__func__)


class PreviousAttempt(BaseModel):
    record_id: str
    platform: Platform
    source_id: str
    title: str
    problem_url: str
    submission_url: str | None
    solved_at: datetime | None

    _solved_utc = field_validator("solved_at")(stored_utc_time)


class DuplicateCheckResponse(BaseModel):
    duplicate: bool
    status: str
    previous_attempt: PreviousAttempt | None = None


class CodingRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform_profile_id: str
    source_id: str
    kind: RecordKind
    status: RecordStatus
    title: str
    canonical_url: str
    submission_url: str | None
    difficulty: str | None
    topics: list[str]
    occurred_at: datetime | None

    _occurred_utc = field_validator("occurred_at")(stored_utc_time)
    cluster_id: str | None
    matching_state: str


class SolvedProblemResponse(BaseModel):
    id: str
    platform: Platform
    profile_handle: str
    source_id: str
    title: str
    canonical_url: str
    submission_url: str | None
    difficulty: str | None
    topics: list[str]
    solved_at: datetime | None
    source_solved_at: str | None = None
    has_statement: bool = False

    _solved_utc = field_validator("solved_at")(stored_utc_time)


class SolvedProblemPage(BaseModel):
    items: list[SolvedProblemResponse]
    total: int
    offset: int
    limit: int


class ClusterResponse(BaseModel):
    id: str
    base_problem_title: str
    records: list[CodingRecordResponse]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
