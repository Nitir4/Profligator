from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profligator_api.models import CodingRecord, PlatformProfile, RefreshSession, SyncRun, User
from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorMode,
    DashboardActivityDay,
    DashboardActivitySummary,
    DashboardBreakdownItem,
    DashboardDifficultySummary,
    DashboardPlatformSummary,
    DashboardResponse,
    DashboardTopicSummary,
    NormalizedRecord,
    Platform,
    SyncStatus,
    VerificationState,
)


def _streaks(active_dates: set[date], today: date) -> tuple[int, int]:
    longest = 0
    run = 0
    previous: date | None = None
    for active_date in sorted(active_dates):
        if previous is not None and active_date == previous + timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        previous = active_date

    end = today if today in active_dates else today - timedelta(days=1)
    current = 0
    while end in active_dates:
        current += 1
        end -= timedelta(days=1)
    return current, longest


def _breakdown_items(counter: Counter[str], total: int) -> list[DashboardBreakdownItem]:
    return [
        DashboardBreakdownItem(
            name=name,
            count=count,
            percent=round((count / total) * 100, 1) if total else 0,
        )
        for name, count in counter.most_common(6)
    ]


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_user(self, *, email: str, handle: str, password_hash: str) -> User:
        user = User(email=email.strip().lower(), handle=handle.strip(), password_hash=password_hash)
        self.session.add(user)
        self.session.flush()
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.strip().lower()))

    def get_user_by_handle(self, handle: str) -> User | None:
        return self.session.scalar(select(User).where(User.handle == handle.strip()))

    def create_refresh_session(
        self, *, user_id: str, token_hash: str, expires_at: datetime
    ) -> RefreshSession:
        refresh_session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(refresh_session)
        self.session.flush()
        return refresh_session

    def get_active_refresh_session(self, token_hash: str) -> RefreshSession | None:
        return self.session.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == token_hash,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > datetime.now(UTC),
            )
        )

    def revoke_refresh_session(self, token_hash: str) -> bool:
        refresh_session = self.session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        if refresh_session is None or refresh_session.revoked_at is not None:
            return False
        refresh_session.revoked_at = datetime.now(UTC)
        self.session.flush()
        return True

    def save_profile(
        self,
        user_id: str,
        profile: CanonicalProfile,
        mode: ConnectorMode,
        *,
        live_data: bool,
    ) -> PlatformProfile:
        statement = select(PlatformProfile).where(
            PlatformProfile.user_id == user_id,
            PlatformProfile.platform == profile.platform.value,
            PlatformProfile.public_handle == profile.handle,
        )
        saved = self.session.scalar(statement)
        verification = (
            VerificationState.UNVERIFIED if live_data else VerificationState.FIXTURE_ONLY
        )
        if saved is None:
            saved = PlatformProfile(
                user_id=user_id,
                platform=profile.platform.value,
                public_handle=profile.handle,
                canonical_url=profile.canonical_url,
                verification_state=verification.value,
                connector_mode=mode.value,
            )
            self.session.add(saved)
        else:
            saved.canonical_url = profile.canonical_url
            saved.verification_state = verification.value
            saved.connector_mode = mode.value
            saved.disconnected_at = None
        self.session.flush()
        return saved

    def list_profiles(self, user_id: str) -> list[PlatformProfile]:
        statement = (
            select(PlatformProfile)
            .where(
                PlatformProfile.user_id == user_id,
                PlatformProfile.disconnected_at.is_(None),
            )
            .order_by(PlatformProfile.created_at)
        )
        return list(self.session.scalars(statement))

    def get_profile(self, profile_id: str, user_id: str | None = None) -> PlatformProfile | None:
        profile = self.session.get(PlatformProfile, profile_id)
        if profile is not None and (
            (user_id is not None and profile.user_id != user_id)
            or profile.disconnected_at is not None
        ):
            return None
        return profile

    def disconnect_profile(self, profile_id: str, user_id: str) -> bool:
        profile = self.get_profile(profile_id, user_id)
        if profile is None:
            return False
        profile.disconnected_at = datetime.now(UTC)
        self.session.flush()
        return True

    def start_sync(self, profile_id: str) -> SyncRun:
        run = SyncRun(
            platform_profile_id=profile_id,
            status=SyncStatus.PENDING.value,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def mark_sync_running(self, run: SyncRun) -> SyncRun:
        run.status = SyncStatus.RUNNING.value
        run.started_at = run.started_at or datetime.now(UTC)
        run.finished_at = None
        run.error_code = None
        run.error_message = None
        self.session.flush()
        return run

    def finish_sync(self, run: SyncRun, *, seen: int, written: int) -> SyncRun:
        now = datetime.now(UTC)
        run.status = SyncStatus.SUCCEEDED.value
        run.records_seen = seen
        run.records_written = written
        run.finished_at = now
        profile = self.session.get(PlatformProfile, run.platform_profile_id)
        if profile is not None:
            profile.last_successful_sync = now
            if profile.connector_mode == ConnectorMode.OFFICIAL_API.value:
                profile.verification_state = VerificationState.VERIFIED.value
        self.session.flush()
        return run

    def fail_sync(self, run: SyncRun, *, code: str, message: str) -> SyncRun:
        run.status = SyncStatus.FAILED.value
        run.error_code = code
        run.error_message = message
        run.finished_at = datetime.now(UTC)
        self.session.flush()
        return run

    def get_sync(self, sync_id: str) -> SyncRun | None:
        return self.session.get(SyncRun, sync_id)

    def get_sync_for_user(self, sync_id: str, user_id: str) -> SyncRun | None:
        return self.session.scalar(
            select(SyncRun)
            .join(PlatformProfile)
            .where(
                SyncRun.id == sync_id,
                PlatformProfile.user_id == user_id,
            )
        )

    def upsert_records(self, profile_id: str, records: list[NormalizedRecord]) -> int:
        written = 0
        for record in records:
            statement = select(CodingRecord).where(
                CodingRecord.platform_profile_id == profile_id,
                CodingRecord.source_id == record.source_id,
                CodingRecord.kind == record.kind.value,
            )
            saved = self.session.scalar(statement)
            if saved is None:
                saved = CodingRecord(
                    platform_profile_id=profile_id,
                    source_id=record.source_id,
                    kind=record.kind.value,
                    status=record.status.value,
                    title=record.title,
                    canonical_url=record.canonical_url,
                    difficulty=record.difficulty,
                    topics=record.topics,
                    occurred_at=record.occurred_at,
                    source_payload_checksum=record.source_payload_checksum,
                )
                self.session.add(saved)
                written += 1
            elif saved.source_payload_checksum != record.source_payload_checksum:
                saved.status = record.status.value
                saved.title = record.title
                saved.canonical_url = record.canonical_url
                saved.difficulty = record.difficulty
                saved.topics = record.topics
                saved.occurred_at = record.occurred_at
                saved.source_payload_checksum = record.source_payload_checksum
                written += 1
        self.session.flush()
        return written

    def dashboard(self, user_id: str) -> DashboardResponse:
        profiles = self.list_profiles(user_id)
        records = list(
            self.session.scalars(
                select(CodingRecord)
                .join(PlatformProfile)
                .where(
                    PlatformProfile.user_id == user_id,
                    PlatformProfile.disconnected_at.is_(None),
                    CodingRecord.kind == "problem",
                    CodingRecord.status == "solved",
                )
                .order_by(CodingRecord.occurred_at)
            )
        )
        total = len(records)
        normalized_title = func.lower(func.trim(CodingRecord.title))
        unique = self.session.scalar(
            select(func.count(func.distinct(normalized_title)))
            .join(PlatformProfile)
            .where(
                PlatformProfile.user_id == user_id,
                PlatformProfile.disconnected_at.is_(None),
                CodingRecord.kind == "problem",
                CodingRecord.status == "solved",
            )
        ) or 0
        summaries = []
        for profile in profiles:
            solved = self.session.scalar(
                select(func.count(CodingRecord.id)).where(
                    CodingRecord.platform_profile_id == profile.id,
                    CodingRecord.kind == "problem",
                    CodingRecord.status == "solved",
                )
            ) or 0
            summaries.append(
                DashboardPlatformSummary(
                    platform=Platform(profile.platform),
                    profile_handle=profile.public_handle,
                    solved=solved,
                    last_successful_sync=profile.last_successful_sync,
                )
            )

        activity_counts = Counter(
            record.occurred_at.date()
            for record in records
            if record.occurred_at is not None
        )
        current_streak, longest_streak = _streaks(set(activity_counts), datetime.now(UTC).date())
        activity = DashboardActivitySummary(
            days=[
                DashboardActivityDay(date=active_date, count=count)
                for active_date, count in sorted(activity_counts.items())
            ],
            known_timestamp_records=sum(activity_counts.values()),
            unknown_timestamp_records=sum(
                1 for record in records if record.occurred_at is None
            ),
            current_streak=current_streak,
            longest_streak=longest_streak,
        )

        topic_counts: Counter[str] = Counter()
        records_without_topics = 0
        for record in records:
            normalized_topics = {
                str(topic).strip() for topic in (record.topics or []) if str(topic).strip()
            }
            if not normalized_topics:
                records_without_topics += 1
            topic_counts.update(sorted(normalized_topics))
        topic_total = sum(topic_counts.values())
        topics = DashboardTopicSummary(
            items=_breakdown_items(topic_counts, topic_total),
            total_assignments=topic_total,
            records_without_topics=records_without_topics,
        )

        difficulty_counts: Counter[str] = Counter()
        for record in records:
            difficulty = (record.difficulty or "").strip().lower()
            if difficulty in {"easy", "medium", "hard"}:
                difficulty_counts[difficulty.title()] += 1
        rated_records = sum(difficulty_counts.values())
        ordered_difficulties = Counter(
            {name: difficulty_counts[name] for name in ("Easy", "Medium", "Hard")}
        )
        difficulties = DashboardDifficultySummary(
            items=[
                DashboardBreakdownItem(
                    name=name,
                    count=count,
                    percent=round((count / rated_records) * 100, 1) if rated_records else 0,
                )
                for name, count in ordered_difficulties.items()
            ],
            rated_records=rated_records,
            unrated_records=total - rated_records,
        )

        partial_reasons = []
        if any(profile.last_successful_sync is None for profile in profiles):
            partial_reasons.append("One or more connected profiles have not synced successfully.")
        if activity.unknown_timestamp_records:
            partial_reasons.append("Some records do not include activity timestamps.")
        if topics.records_without_topics:
            partial_reasons.append("Some records do not include topic metadata.")
        if difficulties.unrated_records:
            partial_reasons.append("Some records do not include a normalized difficulty.")
        data_state = "empty" if total == 0 else "partial" if partial_reasons else "ready"
        successful_syncs = [
            profile.last_successful_sync
            for profile in profiles
            if profile.last_successful_sync is not None
        ]
        return DashboardResponse(
            total_problems_solved=total,
            provisional_unique_problems=unique,
            connected_profiles=len(profiles),
            platforms=summaries,
            activity=activity,
            topics=topics,
            difficulties=difficulties,
            data_state=data_state,
            partial_reasons=partial_reasons,
            last_successful_sync=max(successful_syncs) if successful_syncs else None,
            generated_at=datetime.now(UTC),
        )
