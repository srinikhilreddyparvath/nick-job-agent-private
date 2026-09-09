# Architecture

Career Intelligence Agent separates public source code from private user state.

## Runtime components

- **Next.js frontend:** opportunity dashboard, analysis, pipeline, market views, and experimental application controls.
- **FastAPI API:** discovery, job intelligence, profile/evidence access, applications, operations, and reports.
- **PostgreSQL / SQLite:** production and local-development persistence.
- **Worker:** durable leased queue processing with failure isolation.
- **Scheduler:** discovery cadence, queue wake-ups, and morning reports.
- **Playwright BrowserAgent:** optional ATS inspection/filling/submission behind domain safeguards.

## Intelligence path

Jobs are normalized and deduplicated before role-family classification. Deterministic and optional semantic scores feed `OpportunityScore`. `ConstraintEngine` evaluates known constraints without treating unknowns as failures. Recommendations link match reasons to candidate evidence IDs and type each gap as experience, evidence wording, or unknown.

Career-intelligence runs use the persistent `agent_runs` queue and are processed independently of application automation. Discovery and deterministic scoring cover all enabled-source results. Previously unanalyzed, high-fit jobs are selected first within `LLM_MAX_SEMANTIC_ANALYSES_PER_SCAN`; cached analysis is reused. OpportunityScore blends deterministic and semantic fit at 45/55 when both are available and falls back to deterministic fit when AI is disabled or unavailable. Jobs are globally ranked server-side before offset/limit pagination. Scheduled discovery queues this same intelligence path while the submission worker remains governed separately by manual/auto-submit controls.

## Data boundary

Tracked `*.example.json` files are fictional. Runtime loaders prefer ignored `*.local.json` files configured through environment variables. Candidate facts never belong in prompts, fixtures, or source constants unless loaded through this boundary.

## Application subsystem

Application generation, review, resume rendering, ATS adapters, BrowserAgent, queue leasing, idempotency, receipts, and submission reconciliation remain intact but secondary and experimental. Browser telemetry does not replace the canonical application state machine.

## Contact intelligence

`ContactDiscoveryService` performs an explicit, bounded search of supported public company team, engineering, research, technical-feed, and blog pages, then normalizes, deduplicates, ranks, caches, and persists evidenced contacts. Static HTTP is the default; a Playwright fallback renders at most three likely people-bearing pages only when static parsing yields no candidates. Public GitHub pages may add domain evidence only to identities already established by a company-authored source. `ContactRecord` stores job-specific public evidence, role/team/domain similarity, relationship confidence, and a transparent relevance reason. Deterministic ranking favors same-role and same-team peers, excludes generic executives by default, and ranks recruiting matches below technical peers. Contact records never affect `OpportunityScore`. Outreach previews cite approved candidate evidence and are never sent automatically. Coverage is early and incomplete; authenticated LinkedIn scraping is not permitted.
