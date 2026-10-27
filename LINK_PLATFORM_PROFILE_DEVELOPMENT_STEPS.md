# Development Steps: Link Platform Profile

## Selected module and scope

This assignment uses **Link Platform Profile**, an existing Profligator backend feature. A signed-in candidate can connect a LeetCode, GeeksforGeeks, or Codeforces profile. The relevant implementation is in the API schema, route, repository, and database model.

The sections below follow **requirements → design → code → test**. Every Python code block labeled *Verbatim source* is copied exactly from the linked repository file. The five unit-test cases are specifications for tests to write; the quoted tests at the end are existing API integration tests.

## 1. Requirements: inputs and validation

| Input | Source | Validation |
| --- | --- | --- |
| `platform` | JSON request body | Must be one of `leetcode`, `geeksforgeeks`, or `codeforces`. |
| `handle_or_url` | JSON request body | Must be 1–512 characters; the selected connector validates the handle or URL and returns its canonical form. |
| Candidate ID | Authenticated session | Supplied by the server's authentication dependency, not trusted from the request body. |

The connector can reject a URL for the wrong host. A syntactically valid request does not by itself prove that a public profile belongs to the candidate.

**Verbatim source:** [`apps/api/src/profligator_api/schemas.py`, lines 7–10](apps/api/src/profligator_api/schemas.py#L7-L10)

```python
class Platform(StrEnum):
    LEETCODE = "leetcode"
    GEEKSFORGEEKS = "geeksforgeeks"
    CODEFORCES = "codeforces"
```

**Verbatim source:** [`apps/api/src/profligator_api/schemas.py`, lines 107–109](apps/api/src/profligator_api/schemas.py#L107-L109)

```python
class ProfileCheckRequest(BaseModel):
    platform: Platform
    handle_or_url: str = Field(min_length=1, max_length=512)
```

**Verbatim source:** [`apps/api/src/profligator_api/schemas.py`, lines 119–120](apps/api/src/profligator_api/schemas.py#L119-L120)

```python
class PlatformProfileCreate(ProfileCheckRequest):
    pass
```

## 2. Design: function and API

**API:** `POST /api/v1/platform-profiles` with a `PlatformProfileCreate` JSON body. The route authenticates the candidate, chooses the connector, validates and canonicalizes the handle or URL, calls `Repository.save_profile`, and returns `PlatformProfileResponse` with HTTP `201 Created`.

**Verbatim source:** [`apps/api/src/profligator_api/main.py`, lines 239–258](apps/api/src/profligator_api/main.py#L239-L258)

```python
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
```

## 3. Code: database updates

The `platform_profiles` table stores the candidate ID, platform, public handle, canonical URL, verification state, connector mode, and timestamps. Its unique constraint prevents two rows with the same candidate, platform, and handle. `disconnected_at` supports soft disconnection.

**Verbatim source:** [`apps/api/src/profligator_api/models.py`, lines 49–67](apps/api/src/profligator_api/models.py#L49-L67)

```python
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
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
```

`save_profile` looks up the candidate's existing profile. It inserts a new row or updates the existing one, including clearing `disconnected_at` on relink. It sets verification to `unverified` for live connectors and `fixture_only` for fixture connectors.

**Verbatim source:** [`apps/api/src/profligator_api/repository.py`, lines 106–139](apps/api/src/profligator_api/repository.py#L106-L139)

```python
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
```

## 4. Test: five unit-test cases to write

These cases target the schema, connector validation, and `Repository.save_profile` separately. A repository test can use an isolated in-memory database; it does not need to call the HTTP API.

| Case | Arrange and act | Assert |
| --- | --- | --- |
| Valid new link | Validate `leetcode` and a valid handle, then save it for a candidate. | One `PlatformProfile` exists with the candidate ID, canonical URL, and `fixture_only` state for a fixture connector. |
| Unsupported platform | Construct `PlatformProfileCreate` with `platform="unknown"`. | Pydantic rejects the input before any save. |
| Wrong website URL | Pass a LeetCode connector a URL on `example.com`. | Connector reports `invalid_profile_url`; no profile is saved. |
| Duplicate link | Call `save_profile` twice for the same candidate, platform, and handle. | The second call returns the same profile ID; there is still one row. |
| Relink after disconnect | Save a profile, set `disconnected_at`, and save it again. | The same row is reused and `disconnected_at` becomes `None`. |

The repository already includes API integration coverage. The following is an existing wrong-host test, quoted to show the current observable behavior.

**Verbatim source:** [`apps/api/tests/test_api.py`, lines 149–155](apps/api/tests/test_api.py#L149-L155)

```python
async def test_profile_validation_rejects_wrong_host(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/platform-profiles/check",
        json={"platform": "leetcode", "handle_or_url": "https://example.com/u/alex"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_profile_url"
```

## 5. Possible integration issue

LeetCode and GeeksforGeeks currently use fixture connectors. Linking one of those profiles can therefore save a row marked `fixture_only` without verifying live activity. The frontend and any downstream sync or dashboard view must present that status accurately so fixture data is not mistaken for a verified account.

## Verification

The existing API test file was run with `apps/api/.venv/bin/pytest -q apps/api/tests/test_api.py`: **8 passed**. The five unit-test cases above are assignment specifications; they have not been added as executable tests.
