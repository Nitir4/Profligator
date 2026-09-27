# Profligator

Profligator is a web platform that combines a candidate's public coding activity from multiple competitive-programming and interview-preparation sites into one profile. It helps candidates understand their actual breadth of practice and gives recruiters a consent-gated, read-only view of that work.

The distinguishing feature is cross-platform duplicate detection. Profligator compares problem statements and metadata, groups identical or substantially similar problems, and reports both:

- **Total problems solved** — every solved platform problem.
- **Unique problems solved** — deduplicated problem clusters that better represent breadth.

When a candidate opens a problem that resembles one already solved elsewhere, a browser extension can notify them and link to the earlier attempt.

This repository implements the product specified in the class [project report](../Group%20-%205%20.pdf). The report initially calls the concept **CodeFusion**, but the approved design, logo, GitHub repository, and later design section use **Profligator**; this implementation consistently uses Profligator.

## First-release scope

The MVP will provide:

1. Candidate registration and sign-in.
2. Public profile linking and verification.
3. LeetCode and GeeksforGeeks aggregation through reviewed, pinned, self-hosted open-source services and replaceable backend adapters, subject to validated capabilities and recorded access conditions; sanitized fixtures remain the current implementation.
4. Codeforces aggregation through its documented public API as the first live connector.
5. Periodic synchronization of solved problems, difficulty, topics, activity, and contest data when the source exposes it publicly.
6. A candidate dashboard showing, in priority order:
   - total and unique problems solved;
   - topic/skill breakdown;
   - progress over time;
   - difficulty breakdown;
   - contest performance and ratings.
7. LLM-assisted cross-platform duplicate detection with a traceable link to every original problem or submission.
8. A candidate-controlled, shareable, read-only recruiter profile.
9. A browser extension that checks the currently open problem and displays a duplicate notification with a link to the previous attempt.
10. Clear partial-failure states when an external platform is unavailable or changes its public interface.

Not planned for the first release: CodeChef and HackerRank connectors, similarity scores in the user interface, automatic topic tagging, skill-gap analysis, personalized recommendations, recruiter comparison, progress prediction, and placement-platform integrations. AtCoder, Kaggle, and GitHub appear as visual suggestions in the profile-setup mock-up but are not committed MVP connectors in the SRS.

## Product rules

- Only publicly available platform data will be collected; platform passwords or private data will never be requested.
- Each connector must comply with the source platform's terms, public API policy, and rate limits.
- A recruiter can access a candidate profile only through a currently enabled candidate-approved share link.
- Duplicate matches must retain their source platform, source problem ID/URL, and earlier-attempt URL.
- A false positive is more damaging than a missed suggestion, so uncertain matches remain ungrouped or enter review rather than being presented as facts.
- The dashboard must remain useful when one connector temporarily fails; it should show data freshness and the affected connector's error state.

## User interfaces

The visual source of truth is the [Figma design](https://www.figma.com/design/eJnpqtoALXCdAu7EHcGrq1/Figma-basics?node-id=2603-1161&t=LDsIwhAnAFkB0fnI-1), supplemented by Figures 11.5–11.10 of the project report. The frontend should reproduce the designs without adding unapproved features.

Planned screens:

- Login
- Profile setup / connected accounts
- Candidate dashboard
- Profile sharing controls
- Public recruiter profile
- Browser-extension duplicate notification

## Proposed tech stack

| Area | Technology | Purpose |
| --- | --- | --- |
| Web frontend | React, TypeScript, Vite | Component-based implementation of the Figma screens with fast local builds |
| Styling | CSS custom properties and component-scoped class naming | Precise, reusable colors, spacing, type, borders, and responsive behavior without a runtime styling dependency |
| Routing and data | React Router, TanStack Query | Page routing, API caching, loading/error states, and refresh behavior |
| Charts | Recharts plus a small custom contribution-grid component | Dashboard activity and distribution visualizations |
| Forms and validation | React Hook Form, Zod | Typed validation for authentication, profile URLs, and sharing controls |
| Backend API | Python, FastAPI, Pydantic | Typed REST API and orchestration of connectors and matching |
| Data access | SQLAlchemy, Alembic | Relational models, queries, and versioned migrations |
| Database | PostgreSQL with `pgvector` | Users, profiles, records, clusters, sync history, and vector-assisted candidate matching |
| Collection | `httpx`, Beautiful Soup, and Playwright only where necessary | API/page retrieval, parsing, and browser rendering for permitted public data |
| Upstream aggregation (planned) | Reviewed, pinned, self-hosted open-source service(s) | Reuse maintained collectors behind backend adapters; candidates are not selected or audited yet |
| Background work | Redis and RQ | Scheduled profile synchronization and matching outside web requests |
| Similarity layer | Provider-neutral LLM adapter plus embeddings | Shortlist likely matches, then evaluate supported LLM providers for accuracy, cost, and latency |
| Authentication | Short-lived JWT access tokens, rotating refresh tokens, and Argon2 password hashes | Candidate sessions and protected API access |
| Browser extension | Manifest V3, TypeScript, React | Cross-browser-oriented content script and notification UI |
| Testing | Pytest, Vitest, React Testing Library, Playwright | Unit, integration, contract, UI, and end-to-end coverage |
| Local environment | Docker Compose | Reproducible API, worker, PostgreSQL, and Redis services |
| CI | GitHub Actions | Lint, type-check, test, and build verification on real commits and pull requests |

The LLM provider is intentionally not fixed at the start. The SRS requires comparing candidate models on an agreed validation set before selecting one. Provider-specific code will sit behind a common adapter.

## Architecture

```mermaid
flowchart LR
    W[React web app] -->|HTTPS / REST| API[FastAPI API]
    X[Browser extension] -->|HTTPS / REST| API
    API --> DB[(PostgreSQL + pgvector)]
    API --> Q[(Redis queue)]
    Q --> WK[Sync and matching worker]
    WK --> LC[LeetCode connector]
    WK --> GFG[GeeksforGeeks connector]
    WK --> CF[Codeforces connector]
    WK --> LLM[Provider-neutral LLM adapter]
    LC --> AGG[Self-hosted aggregator — planned]
    GFG --> AGG
    LC --> DB
    GFG --> DB
    CF --> DB
    LLM --> DB
```

Connectors normalize source-specific records into one internal format. Raw platform records remain traceable, while the matcher groups records into unique-problem clusters. Both web views and the extension consume the same API and matching results.

## Upstream aggregator strategy

On 27 September 2026, the user approved reusing reviewed open-source collectors rather than writing every platform scraper ourselves. The planned service will run internally at an exact reviewed version; FastAPI adapters will normalize its responses through the existing background-sync pipeline. The browser will continue to use only Profligator's API. We will adopt tested upstream fixes, preserve rollback, and keep adapters replaceable if maintenance stops.

Initial candidates are [alfa-leetcode-api](https://github.com/alfaarghya/alfa-leetcode-api) for LeetCode and [coding-profile-service-v2.0](https://github.com/mearjuntripathi/coding-profile-service-v2.0) for multi-platform stats, including GFG. Recent commits were checked, but neither project has been security-audited, capability-tested, selected, or integrated. Source/dependency review and license verification precede installation and pinning.

Summary counts alone do not support duplicate detection. Establish whether a service provides individual solved IDs/URLs, usable metadata, pagination, and full or partial history. Recent submissions must not be represented as a complete solved list. Source totals, ingested records, and deduplicated coverage must stay distinguishable; missing fields remain unavailable rather than invented.

Software reuse and provider access rules are separate questions. The earlier LeetCode/GFG terms findings remain recorded; an open-source wrapper does not establish provider permission. See [provider feasibility](../provider_feasibility.md) for candidate evidence, runtime status, and evaluation gates.

## Planned repository structure

```text
Profligator/
├── apps/
│   ├── web/                 # React candidate and recruiter interfaces
│   ├── api/                 # FastAPI application and worker
│   └── extension/           # Manifest V3 browser extension
├── packages/
│   ├── ui/                  # Shared visual components and design tokens
│   └── contracts/           # Shared API schemas/types generated from OpenAPI
├── infra/
│   └── compose.yaml         # Local PostgreSQL and Redis services
├── tests/
│   ├── fixtures/            # Sanitized connector and matcher fixtures
│   └── validation/          # Labeled duplicate-detection dataset
└── .github/workflows/       # CI checks
```

This is the intended layout. `apps/web`, `apps/api`, and `infra` exist; the extension workspace, shared packages, top-level validation suite, and CI configuration remain planned. Planning, feasibility, progress, and agent handover documents live one directory above this Git repository; the project README stays in the repository.

## Delivery order

Development follows three one-week increments:

- **Week 1 — foundation and exact frontend:** scaffold the monorepo, encode the Figma design tokens, implement the documented screens with fixture data, define the schema/API contracts, and establish tests and CI.
- **Week 2 — real aggregation:** review upstream collectors, self-host pinned versions, implement LeetCode/GFG adapters for validated capabilities, preserve explicit fixture mode during evaluation, and continue the official Codeforces connector, persisted records, background syncs, and API-backed dashboard.
- **Week 3 — deduplication and sharing:** evaluate matching models, build unique clusters and notifications, enforce consent-based sharing, integrate the browser extension, harden error states, and complete end-to-end acceptance tests.

The detailed technical plan and live checklist are maintained in [`../implementation.md`](../implementation.md) and [`../progress.md`](../progress.md). The next agent should begin with [`../project_handover.md`](../project_handover.md).

## Status

All supplied Figma screens are implemented and were previously visually verified. The backend includes FastAPI/OpenAPI, SQLAlchemy models and migrations, candidate authentication, fixture-backed LeetCode and GeeksforGeeks adapters, a live Codeforces adapter, Redis/RQ profile-sync jobs, and persisted dashboard analytics. Login, profile setup, totals, activity, topics, difficulty, freshness, and partial-data notices use the API. Unique counts are provisional title-based counts; semantic matching, secure backend sharing, periodic scheduling, and the actual extension workspace remain unfinished. The upstream strategy is approved but not implemented. See the [progress tracker](../progress.md) for historical verification evidence and next tasks.
