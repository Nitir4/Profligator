from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from profligator_api.models import (
    CodingRecord, PlatformProfile, ProfileActivityCalendar, RefreshSession, SyncRun, UniqueCluster, User, VerificationToken,
)
from profligator_api.connectors.base import payload_checksum
from profligator_api.schemas import (
    CanonicalProfile,
    CalendarCollection,
    ConnectorMode,
    ContestResponse,
    DashboardActivityDay,
    DashboardActivitySummary,
    DashboardBreakdownItem,
    DashboardDifficultySummary,
    DashboardPlatformSummary,
    DashboardResponse,
    DashboardTopicSummary,
    NormalizedRecord,
    ProfileSnapshot,
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

    def create_user(
        self, *, email: str, handle: str, password_hash: str | None, role: str = "candidate"
    ) -> User:
        user = User(
            email=email.strip().lower(), handle=handle.strip(),
            password_hash=password_hash, role=role,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.strip().lower()))

    def get_user_by_handle(self, handle: str) -> User | None:
        return self.session.scalar(select(User).where(func.lower(User.handle) == handle.strip().lower()))

    def create_refresh_session(
        self, *, user_id: str, token_hash: str, expires_at: datetime, auth_version: int | None = None
    ) -> RefreshSession:
        refresh_session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            auth_version=auth_version if auth_version is not None else self.get_user(user_id).auth_version,
        )
        self.session.add(refresh_session)
        self.session.flush()
        return refresh_session

    def get_active_refresh_session(self, token_hash: str) -> RefreshSession | None:
        return self.session.scalar(
            select(RefreshSession).join(User, User.id == RefreshSession.user_id).where(
                RefreshSession.token_hash == token_hash,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > datetime.now(UTC),
                RefreshSession.auth_version == User.auth_version,
            )
        )

    def revoke_refresh_session(self, token_hash: str) -> bool:
        # Claim the token with a conditional write, rather than read-then-revoke.
        result = self.session.execute(update(RefreshSession).where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
        return result.rowcount == 1

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
            if saved.disconnected_at is not None or saved.verification_state != "verified":
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
        profile.verification_state = "fixture_only" if profile.connector_mode == "fixture" else "unverified"
        self.session.execute(update(VerificationToken).where(VerificationToken.target == profile.id,
            VerificationToken.purpose == "profile", VerificationToken.used_at.is_(None)).values(used_at=datetime.now(UTC)))
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

    def claim_sync(self, profile_id: str, cooldown_seconds: int, timeout_seconds: int) -> tuple[SyncRun, bool]:
        # Serialize claims on the profile row (also acquires SQLite's write lock).
        # An explicit unchanged value avoids updating the profile's modified time.
        self.session.execute(update(PlatformProfile).where(
            PlatformProfile.id == profile_id,
            PlatformProfile.disconnected_at.is_(None),
        ).values(updated_at=PlatformProfile.updated_at))
        now = datetime.now(UTC)
        runs = list(self.session.scalars(select(SyncRun).where(
            SyncRun.platform_profile_id == profile_id, SyncRun.status.in_(["pending", "running"]),
        ).order_by(SyncRun.created_at.desc(), SyncRun.id.desc())))
        for run in runs:
            created = run.created_at.replace(tzinfo=UTC) if run.created_at.tzinfo is None else run.created_at
            if run.status in {"pending", "running"}:
                if created > now - timedelta(seconds=timeout_seconds * 2):
                    return run, False
                self.fail_sync(run, code="worker_timeout", message="Sync worker did not finish in time")
        latest = self.session.scalar(select(SyncRun).where(
            SyncRun.platform_profile_id == profile_id,
        ).order_by(SyncRun.created_at.desc(), SyncRun.id.desc()).limit(1))
        if latest is not None:
            # An abandoned run may be retried immediately after recovery.
            last_attempt = latest.created_at if latest.error_code == "worker_timeout" else (latest.finished_at or latest.created_at)
            last_attempt = last_attempt.replace(tzinfo=UTC) if last_attempt.tzinfo is None else last_attempt
            if last_attempt > now - timedelta(seconds=cooldown_seconds):
                return latest, False
        return self.start_sync(profile_id), True

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
            # Fetching a public account confirms availability, not ownership.
        self.session.flush()
        return run

    def save_snapshot(self, profile_id: str, snapshot: ProfileSnapshot) -> None:
        profile = self.session.get(PlatformProfile, profile_id)
        if profile is not None:
            profile.source_total_solved = snapshot.source_total_solved
            profile.rating = snapshot.rating
            profile.rank = snapshot.rank
            profile.history_complete = snapshot.history_complete
            profile.source_difficulty_counts = snapshot.source_difficulty_counts
            if (profile.connector_mode == "scraper" and profile.platform in {"leetcode", "geeksforgeeks"}
                    and snapshot.source_total_solved is not None and snapshot.history_complete is not None):
                # Public windows move; coverage includes earlier saved problems.
                # A decreased source count is a mismatch, not a reason to erase history.
                imported = self.session.scalar(select(func.count()).select_from(CodingRecord).where(
                    CodingRecord.platform_profile_id == profile_id,
                    CodingRecord.kind == "problem", CodingRecord.status == "solved",
                ))
                profile.history_complete = imported == snapshot.source_total_solved

    def activity_years(self, profile_id: str) -> dict[int, datetime]:
        return {row.year: row.fetched_at for row in self.session.scalars(
            select(ProfileActivityCalendar).where(ProfileActivityCalendar.platform_profile_id == profile_id)
        )}

    def save_activity(self, profile_id: str, collection: CalendarCollection) -> None:
        profile = self.session.get(PlatformProfile, profile_id)
        if profile is None:
            return
        profile.activity_status = collection.status
        profile.activity_error = collection.error_code
        if collection.calendars:
            profile.activity_available_years = collection.available_years
        for calendar in collection.calendars:
            row = self.session.get(ProfileActivityCalendar, (profile_id, calendar.year))
            if row is None:
                row = ProfileActivityCalendar(platform_profile_id=profile_id, year=calendar.year)
                self.session.add(row)
            else:
                old = row.fetched_at.replace(tzinfo=UTC) if row.fetched_at.tzinfo is None else row.fetched_at
                if old > calendar.fetched_at:
                    continue
            row.days = [day.model_dump(mode="json") for day in calendar.days]
            row.fetched_at = calendar.fetched_at
        self.session.flush()

    def solved_records(self, user_id: str) -> list[CodingRecord]:
        return list(self.session.scalars(
            select(CodingRecord).join(PlatformProfile).where(
                PlatformProfile.user_id == user_id,
                PlatformProfile.disconnected_at.is_(None),
                CodingRecord.kind == "problem",
                CodingRecord.status == "solved",
            ).order_by(
                CodingRecord.occurred_at.is_(None), CodingRecord.occurred_at,
                CodingRecord.created_at, CodingRecord.id,
            )
        ))

    def new_cluster(self, user_id: str, title: str) -> UniqueCluster:
        cluster = UniqueCluster(user_id=user_id, base_problem_title=title)
        self.session.add(cluster)
        self.session.flush()
        return cluster

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
            if saved is not None and record.kind.value == "problem" and record.status.value == "solved":
                # A moving public submission window must not erase an older known
                # acceptance or richer metadata imported in an earlier sync.
                record = record.model_copy(deep=True)
                before = record.model_dump(mode="json", exclude={"source_payload_checksum"})
                old_time = saved.occurred_at
                if old_time is not None:
                    old_time = old_time.replace(tzinfo=UTC) if old_time.tzinfo is None else old_time
                    if record.occurred_at is None or old_time < record.occurred_at:
                        record.occurred_at = old_time
                        record.submission_url = saved.submission_url
                record.statement = record.statement or saved.statement
                record.submission_url = record.submission_url or saved.submission_url
                record.difficulty = record.difficulty or saved.difficulty
                record.topics = record.topics or saved.topics
                if saved.source_solved_at and (record.source_solved_at is None or saved.source_solved_at < record.source_solved_at):
                    record.source_solved_at = saved.source_solved_at
                after = record.model_dump(mode="json", exclude={"source_payload_checksum"})
                if before != after:
                    record.source_payload_checksum = payload_checksum(after)
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
                self.session.flush()
                written += 1
            elif saved.source_payload_checksum != record.source_payload_checksum or (
                saved.statement, saved.submission_url, saved.contest_rating, saved.global_rank
            ) != (record.statement, record.submission_url, record.contest_rating, record.global_rank):
                saved.status = record.status.value
                saved.title = record.title
                saved.canonical_url = record.canonical_url
                saved.difficulty = record.difficulty
                saved.topics = record.topics
                saved.occurred_at = record.occurred_at
                saved.source_payload_checksum = record.source_payload_checksum
                saved.cluster_id = None
                saved.matching_state = "pending"
                saved.similarity_score = None
                written += 1
            saved.statement = record.statement
            saved.source_solved_at = record.source_solved_at
            saved.submission_url = record.submission_url
            saved.contest_rating = record.contest_rating
            saved.global_rank = record.global_rank
            if saved.kind == "problem" and saved.status == "solved" and saved.cluster_id is None:
                profile = self.session.get(PlatformProfile, profile_id)
                if profile is None:
                    raise ValueError("Profile not found")
                saved.cluster_id = self.new_cluster(profile.user_id, saved.title).id
        self.session.flush()
        return written

    def dashboard(self, user_id: str, *, leetcode_collect_contests: bool = False, semantic_matching: bool = False) -> DashboardResponse:
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
        unique = len({record.cluster_id or record.id for record in records})
        records_by_profile: dict[str, list[CodingRecord]] = {}
        for record in records:
            records_by_profile.setdefault(record.platform_profile_id, []).append(record)
        calendars_by_profile: dict[str, list[ProfileActivityCalendar]] = {}
        for calendar in self.session.scalars(select(ProfileActivityCalendar).join(PlatformProfile).where(
            PlatformProfile.user_id == user_id, PlatformProfile.disconnected_at.is_(None),
        )):
            calendars_by_profile.setdefault(calendar.platform_profile_id, []).append(calendar)
        summaries = []
        for profile in profiles:
            profile_records = records_by_profile.get(profile.id, [])
            latest = self.session.scalar(
                select(SyncRun).where(SyncRun.platform_profile_id == profile.id)
                .order_by(SyncRun.created_at.desc()).limit(1)
            )
            summaries.append(
                DashboardPlatformSummary(
                    verification_state=VerificationState(profile.verification_state),
                    platform=Platform(profile.platform),
                    profile_handle=profile.public_handle,
                    solved=len(profile_records),
                    last_successful_sync=profile.last_successful_sync,
                    unique_solved=len({record.cluster_id or record.id for record in profile_records}),
                    source_total_solved=profile.source_total_solved,
                    rating=profile.rating if profile.platform != "leetcode" or leetcode_collect_contests else None,
                    rank=profile.rank if profile.platform != "leetcode" or leetcode_collect_contests else None,
                    contests_enabled=profile.platform == "codeforces" or (profile.platform == "leetcode" and leetcode_collect_contests),
                    history_complete=profile.history_complete,
                    connector_mode=ConnectorMode(profile.connector_mode),
                    latest_sync_status=latest.status if latest else None,
                    sync_error=latest.error_message if latest else None,
                    source_difficulty_counts=profile.source_difficulty_counts,
                    activity_status=profile.activity_status,
                    activity_years=sorted(calendar.year for calendar in calendars_by_profile.get(profile.id, [])),
                    activity_available_years=profile.activity_available_years,
                    activity_error=profile.activity_error,
                    questions_with_statements=sum(bool(row.statement) for row in profile_records),
                    questions_with_utc_dates=sum(row.occurred_at is not None for row in profile_records),
                    questions_with_source_times=sum(row.source_solved_at is not None for row in profile_records),
                )
            )

        record_activity_counts = Counter(
            record.occurred_at.date()
            for record in records
            if record.occurred_at is not None
        )
        activity_counts: Counter[date] = Counter()
        calendar_submissions = 0
        fallback_count = 0
        for profile in profiles:
            calendars = calendars_by_profile.get(profile.id, [])
            covered_years = {calendar.year for calendar in calendars}
            # A calendar replaces this profile's dated records for the same year;
            # adding both would count an acceptance twice.
            for record in records_by_profile.get(profile.id, []):
                if record.occurred_at is not None and record.occurred_at.year not in covered_years:
                    activity_counts[record.occurred_at.date()] += 1
                    fallback_count += 1
            for calendar in calendars:
                for day in calendar.days:
                    activity_counts[date.fromisoformat(day["date"])] += day["count"]
                    calendar_submissions += day["count"]
        current_streak, longest_streak = _streaks(set(activity_counts), datetime.now(UTC).date())
        # Preserve provider-local calendar dates as a separate series. They must
        # never be silently interpreted as UTC or added to UTC submission totals.
        source_calendars = []
        for profile in profiles:
            counts = Counter(
                record.source_solved_at[:10]
                for record in records_by_profile.get(profile.id, [])
                if record.occurred_at is None and record.source_solved_at
            )
            if counts:
                source_calendars.append({
                    "platform": profile.platform, "profile_handle": profile.public_handle,
                    "days": [{"date": day, "count": count} for day, count in sorted(counts.items())],
                })
        activity = DashboardActivitySummary(
            days=[
                DashboardActivityDay(date=active_date, count=count)
                for active_date, count in sorted(activity_counts.items())
            ],
            known_timestamp_records=sum(record_activity_counts.values()),
            unknown_timestamp_records=sum(
                1 for record in records if record.occurred_at is None
            ),
            current_streak=current_streak,
            longest_streak=longest_streak,
            calendar_profiles=len(calendars_by_profile),
            calendar_submissions=calendar_submissions,
            source_calendars=source_calendars,
            count_label=("submissions and dated solved records" if calendars_by_profile and fallback_count
                         else "submissions" if calendars_by_profile else "dated solved records"),
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
            elif difficulty in {"school", "basic"}:
                difficulty_counts["Fundamentals"] += 1
        rated_records = sum(difficulty_counts.values())
        ordered_difficulties = Counter(
            {name: difficulty_counts[name] for name in ("Fundamentals", "Easy", "Medium", "Hard")}
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
        if any(summary.sync_error for summary in summaries):
            partial_reasons.append("One or more profile syncs failed; previously imported data is retained.")
        if any(profile.history_complete is False for profile in profiles):
            partial_reasons.append("One or more providers expose only partial history.")
        if any(profile.activity_status in {"partial", "unavailable"} for profile in profiles):
            partial_reasons.append("Some public activity calendars are incomplete or unavailable; saved activity is retained.")
        data_state = "empty" if total == 0 else "partial" if partial_reasons else "ready"
        successful_syncs = [
            profile.last_successful_sync
            for profile in profiles
            if profile.last_successful_sync is not None
        ]
        contests = list(self.session.scalars(
            select(CodingRecord).join(PlatformProfile).where(
                PlatformProfile.user_id == user_id,
                PlatformProfile.disconnected_at.is_(None),
                CodingRecord.kind == "contest",
            ).order_by(CodingRecord.occurred_at.desc())
        ))
        if not leetcode_collect_contests:
            contests = [record for record in contests if record.platform_profile.platform != "leetcode"]
        return DashboardResponse(
            total_problems_solved=total,
            provisional_unique_problems=unique,
            unique_problems_solved=unique,
            matched_records=sum(record.matching_state in {"exact", "semantic"} for record in records),
            unmatched_records=sum(record.matching_state not in {"exact", "semantic"} for record in records),
            semantic_matching="enabled" if semantic_matching else "disabled",
            records_with_statements=sum(bool(row.statement) for row in records),
            records_without_statements=sum(not row.statement for row in records),
            matching_unavailable_records=sum(row.matching_state == "unavailable" for row in records),
            exact_matched_records=sum(row.matching_state == "exact" for row in records),
            semantic_matched_records=sum(row.matching_state == "semantic" for row in records),
            contests=[
                ContestResponse(
                    platform=Platform(record.platform_profile.platform),
                    source_id=record.source_id, title=record.title,
                    canonical_url=record.canonical_url, occurred_at=record.occurred_at,
                    contest_rating=record.contest_rating, global_rank=record.global_rank,
                ) for record in contests
            ],
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
