# Nick Job Agent

Nick Job Agent is a personal, production-oriented job discovery and fit-intelligence system. Phase 1 discovers roles from supported ATS job boards, normalizes them, applies configurable hard filters, scores fit deterministically, explains the result, deduplicates records, tracks job/application state, and presents the queue in a professional dashboard.

It does **not** fill or submit applications. There is no `APPLY` action in Phase 1.

## Non-negotiable truthfulness boundary

> The system may select, summarize, and rewrite verified candidate information. It must never invent experience, employment, skills, degrees, publications, patents, metrics, job titles, or dates.

Every candidate-profile fact can carry supporting evidence and a verification flag. Future application material generation must retrieve facts from that canonical, evidence-linked profile. The disabled application-agent boundary documents and enforces this constraint; final submission will eventually require explicit human approval.

## Architecture

```text
ATS board (Greenhouse / Lever / Ashby)
  -> connector + normalization
  -> configurable hard filters
  -> structural deduplication
  -> SQLite job + lifecycle tracking
  -> deterministic eight-dimension scorer
  -> typed FastAPI API
  -> Next.js dashboard and job analysis
```

- `backend/app/connectors`: common connector contract, ordinary HTTP/rate-limit handling, and ATS adapters. No CAPTCHA or anti-bot bypass behavior exists.
- `backend/app/models`: typed API/domain schemas for normalized jobs, candidate evidence, preferences, scoring, and applications.
- `backend/app/services`: persistence orchestration, exact/structural deduplication, hard filters, and provider-independent scoring contracts.
- `backend/app/agents`: small orchestration boundaries for discovery and fit. Research and application agents are placeholders and disabled.
- `backend/app/db`: SQLAlchemy models and SQLite session setup.
- `backend/app/api`: job, profile, and application endpoints.
- `frontend`: Next.js App Router dashboard with filtering and job detail views.
- `data`: deliberately unpopulated profile/preferences/answer-bank examples.

## Installation

Requires Python 3.12+ and a current Node.js LTS release.

Backend (PowerShell):

```powershell
cd C:\Projects\nick-job-agent\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```powershell
cd C:\Projects\nick-job-agent\frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. FastAPI documentation is at `http://localhost:8000/docs` and health is at `http://localhost:8000/health`.

## Configuration

Backend environment variables are documented in `backend/.env.example`. The frontend uses `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`. Never commit `.env`, `.env.local`, credentials, access tokens, or private candidate documents.

The canonical project resume is `documents/master_resume.pdf`. `data/profile.example.json` and `data/evidence.json` contain facts reviewed against that file. Every important profile item references stable evidence IDs. Evidence records include category, source location, company/role context, skills, domains, verification, and confidence.

```json
{"id":"WALMART_004","source":"master_resume","source_reference":"Page 1 Walmart bullet 4","verified":true,"confidence":1.0}
```

Phase 2 configuration includes real initial role/domain/location preferences, neutral unknown-data behavior, configurable compensation policy, exact approved H-1B answers, and a typed answer bank. Protect this personal data before any multi-user or public deployment.

### Canonical identity and application field mapping

`data/profile.example.json` is the sole canonical source for identity and contact values. `IdentityService` exposes that object to APIs and future ApplicationAgent/BrowserAgent workflows. Identity answers in `AnswerBankService` are derived from the service at load time rather than duplicated in the answer-bank JSON.

The approved legal given name is `Srinikhil Reddy` and the approved legal family name is `Parvath`; `Reddy` must never be inferred as a middle name. Required separate middle-name fields fail closed for human review, while optional middle-name fields are left blank. The exact resume-supported LinkedIn and portfolio URLs are stored with the canonical identity.

### Optional live-company setup

`data/company_seed.example.json` demonstrates the Company API payload without automatically adding any production records. Replace its placeholder with a company Nick wants to monitor, submit the object to `POST /companies`, then call `POST /companies/{id}/detect`. Review the detected ATS configuration before using `POST /sources/detect-and-create` or creating the recommended source manually. Finally, scan only that source with `POST /sources/{id}/scan`. This keeps live discovery deliberate and prevents an example file from populating the database on startup.

## Database

SQLite is the MVP database. On first backend startup, SQLAlchemy creates:

- `jobs`: normalized postings and canonical deduplication keys
- `job_scores`: versioned, explainable score snapshots
- `applications`: one current lifecycle state per job
- `application_events`: append-only status transition history
- `job_sources`: persistent ATS boards and scan state
- `scan_runs`: multi-source scan metrics and errors
- `job_feedback`: Nick's manual labels and notes
- `agent_runs`: observable deterministic and future agent execution

Application statuses remain backward-compatible and now include `recruiter_screen` and `final_round`. Schema evolution is additive: startup creates new Phase 2 tables without deleting or recreating Phase 1 tables or data.

## API

- `GET /health`
- `GET /jobs` and `GET /jobs/{id}`
- `POST /jobs/scan`
- `POST /jobs/{id}/score`
- `POST /jobs/{id}/shortlist`
- `POST /jobs/{id}/skip`
- `GET /applications`
- `GET /profile`
- `GET /profile/evidence` and `GET /profile/evidence/{id}`
- `GET/POST/PUT/DELETE /sources`
- `PATCH /sources/{id}/enabled`
- `POST /sources/{id}/scan` and `POST /sources/scan-all`
- `GET /scans` and `GET /scans/{id}`
- `POST/GET/PUT /jobs/{id}/feedback`
- `GET /evaluation/ranking`
- `GET /agents` and `GET /agents/runs`

Example ATS scan:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/jobs/scan -ContentType application/json -Body '{"connector":"greenhouse","company":"Example Company","identifier":"company-board-token"}'
```

The identifier is the public job-board slug/token used by the ATS:

- Greenhouse: the board token in `boards.greenhouse.io/{token}`
- Lever: the site name in `jobs.lever.co/{site}`
- Ashby: the organization name in `jobs.ashbyhq.com/{organization}`

Identifiers are supplied per scan and are never hardcoded. Some companies customize or restrict their board; those cases may need a company-specific connector configuration later. Connectors stop cleanly on ordinary HTTP failures and return a clear rate-limit error on HTTP 429.

## Scoring

`ScoringEngine` is a provider-independent interface. The MVP `DeterministicScoringEngine` returns a 0–100 weighted score across title, technical domain, skills, experience, research, seniority, location, and compensation. Each component includes its score, weight, and explanation. Results also include strengths, gaps, matched/missing skills, a reasoning summary, and one of `exceptional`, `strong`, `possible`, `weak`, or `skip`.

Phase 2 weights are role 20%, technical domain 20%, skills 15%, experience 15%, research 15%, seniority 5%, location 5%, and compensation 5%. Thresholds are exceptional >=90, strong >=80, possible >=70, weak >=55, and skip below 55. All weights and thresholds live in backend settings/environment configuration, and weights are validated to total 1.0.

The deterministic scorer treats missing configuration or undisclosed compensation neutrally. It does not infer candidate facts.

## Evidence and truthfulness architecture

Future agents may retrieve, select, combine, summarize, tailor, and rewrite verified facts. They must never invent employment, titles, dates, education, skills, research, publications, patents, metrics, leadership, responsibilities, or outcomes. Every candidate-specific generated claim must cite one or more evidence IDs. Unsupported, partially supported, or ambiguous claims must be revised or blocked; unsupported candidate claims must never be submitted.

`EvidenceService` provides deterministic retrieval by ID, company, domain, skill, category, and text. Its interface permits later embedding search without changing the evidence contract. `ClaimValidator` is intentionally interface-only in Phase 2.

Work authorization uses exact approved question-answer pairs. Materially different legal wording, including unrestricted/permanent authorization or no-immigration-support attestations, fails closed with `requires_human_review=true`.

## Phase 3 semantic intelligence

Phase 3 adds an optional semantic layer without replacing the deterministic pipeline. With `LLM_ENABLED=false`, discovery, filtering, deduplication, family classification, family scoring, tracking, and the dashboard continue to operate normally.

`LLMService` exposes typed structured generation through provider adapters. OpenAI and Anthropic adapters use the configured provider/model and environment API key; the deterministic mock provider supports tests and local demonstrations without paid credentials. Prompt text and identifiers live under `backend/app/prompts`, currently `role_classifier_v1`, `fit_analysis_v1`, `research_agent_v1`, and `evidence_selection_v1`. Invalid structured output receives only the configured conservative retry count and then fails explicitly.

`EmbeddingService` is provider-independent. The default hash embedding provider is deterministic, local, and intended for offline/test readiness; the OpenAI embedding adapter is available when explicitly configured. `SemanticEvidenceIndex` stores vectors and provider/model/version metadata in SQLite and computes cosine similarity in-process. The 38 canonical evidence IDs remain authoritative. `EvidenceService.search_hybrid` combines structured filters, deterministic matching, and semantic similarity, and falls back to deterministic retrieval if embeddings are unavailable.

Semantic role classification is a fallback only. High-confidence deterministic classifications take precedence. For ambiguous jobs, both deterministic and semantic families/confidences are retained along with the final family and resolution method. Semantic fit similarly stores deterministic, semantic, and optionally blended scores separately; the configurable blend is an evaluation candidate, not a replacement baseline.

`FitAgent` can retrieve a job, deterministic score, role family, preferences, feedback, and verified evidence through the explicit tool registry. It produces a typed `SemanticFitReport`. Every positive candidate strength must cite canonical evidence IDs and pass `EvidenceClaimValidator`; unsupported claims are removed from verified strengths, recorded, and surfaced as gaps/review items. Provider or embedding failures retain the deterministic result.

`ResearchAgent` is active only for attributable public context. It can use stored job/company data and explicitly permitted public URLs. Each finding retains URL, title, source type, retrieval time, and excerpt. It cannot log in, use LinkedIn automation, bypass access controls/CAPTCHAs, send messages, or submit forms. Search-engine result scraping is not implemented; `WebSearchProvider` is an interface for a future authorized provider.

Agent execution is bounded by configured steps, retries, token caps, timeouts, page limits, analysis thresholds, per-scan limits, and a daily-budget safeguard. Registered tools declare typed input/output schemas, allowed agents, sensitivity, and approval requirements. Agent runs retain action/tool traces, evidence IDs, sources, provider, model, prompt version, token counts, estimated cost, latency, status, and errors. Traces intentionally expose actions and structured results, never private chain-of-thought.

Semantic analysis and research are fingerprint-cached using job content, evidence-set version, prompt version, and model configuration. A changed evidence set invalidates fit-analysis cache keys. The ranking evaluator reports deterministic, semantic, and blended Precision@5, nDCG@5, ranking agreement, score/label correlation, and a simple calibration bucket only when each score family has enough human labels.

Phase 3 endpoints:

- `POST /jobs/{id}/analyze` and `GET /jobs/{id}/analysis`
- `POST /jobs/{id}/research` and `GET /jobs/{id}/research`
- `GET /jobs/{id}/agent-runs`
- `GET /models/status`
- `POST /evidence/reindex`

The job-detail UI keeps deterministic fit visible beside semantic and blended scores. It shows validated evidence-linked strengths, gaps, attributed research, subtle model metadata, and an optional structured agent trace. `AI ANALYZE` and `RESEARCH ROLE` are explicit actions; normal scans do not automatically spend LLM tokens on every job.

## Source and agent orchestration

Persistent enabled sources flow through connector fetch, normalization, hard filters, structural deduplication, persistence, automatic deterministic scoring, recommendation, and scan-run metrics. A failing source records its error while other sources continue. CAPTCHA, access-control, and unsupported-site conditions are blocking states, never bypass targets.

Every agent declares objective, tools, input/output state, actions, evidence access, failure behavior, and human-review conditions. `ScoutAgent` and `FitAgent` are active deterministic agents. `ResearchAgent`, `ApplicationAgent`, `ReviewerAgent`, and `BrowserAgent` are inactive stubs. `AgentOrchestrator` refuses inactive agents, and agent-run records provide observability.

## Phase 2.5 role-family routing

Search, ranking, and personalization are evidence domains, not mandatory job requirements. Every discovered job is classified before scoring into `RESEARCH_AI`, `DATA_SCIENCE`, `PRODUCT_MANAGEMENT`, or `UNKNOWN` using title plus description, requirements, qualifications, and domain signals. Unknown jobs remain visible but are not prioritized.

Each supported family has a separate deterministic scoring profile. Research/AI emphasizes research, technical and ML depth, experience, skills, and production-research fit. Data Science emphasizes statistical/evaluation work, technical and production experience, experimentation, domain, and skills. Product Management uses only verified transferable evidence in technical strategy, problem framing, cross-functional work, AI/data understanding, execution, communication, and leadership. PM jobs are explicitly marked as career transitions; the system never claims prior Product Manager employment.

## Phase 2.5 discovery support

Truly active scan connectors are Greenhouse, Lever, Ashby, SmartRecruiters, Workday public CXS configurations, and conservative generic company sites with schema.org `JobPosting` JSON-LD. Manual URL and pasted-text ingestion are active outside scheduled scans. LinkedIn is reference-only: a public URL may be parsed if accessible, otherwise the user supplies the description text. No login, Easy Apply, authenticated scraping, clicking, messaging, or access-control bypass exists.

iCIMS, Jobvite, and SuccessFactors have explicit `connector_not_implemented` connectors because their public deployments are not uniform enough to claim generic support. Search discovery and email alerts are interface-only and require authorized providers later. Workday sources use `tenant|site|career_base_url`; unsupported variants fail clearly.

Company registry records own website/careers URLs, type, priority, detected ATS, and multiple source relationships. ATS detection recognizes known public host patterns for Greenhouse, Lever, Ashby, SmartRecruiters, Workday, iCIMS, Jobvite, and SuccessFactors, with conservative generic-site fallback. Cross-source deduplication uses canonical company/title/location, ATS IDs, canonical apply URLs, and description fingerprints while preserving alternate source references.

## Future autonomy and application policy

The eventual authorized flow is `DISCOVER -> FILTER -> SCORE -> RESEARCH -> PLAN -> RETRIEVE EVIDENCE -> GENERATE MATERIALS -> VALIDATE CLAIMS -> FILL APPLICATION -> FINAL VALIDATION -> SUBMIT -> TRACK OUTCOME`.

Future automatic submission is allowed only when thresholds pass, all claims are evidence-backed, every field has a valid answer, no human-review-required item exists, no CAPTCHA/access block exists, and final validation passes. Standing authorization never permits fabrication, guessing ambiguous legal answers, CAPTCHA bypass, access-control bypass, anti-bot circumvention, or deliberate violation of technical restrictions.

Future learning signals include discovery, shortlist, submission, recruiter response/screen, interview, final round, offer, and rejection. Later analysis may study score calibration, conversion by role/company type, resume framing, callback-correlated skills, and interview-predictive fit dimensions. Phase 2 performs no predictive learning.

## Deduplication

The MVP checks source + external ID, canonical apply URL (with common tracking parameters removed), and normalized company/title/location combinations. The service boundary allows a later semantic duplicate detector to be added without changing connectors or persistence.

## Testing

```powershell
cd backend
pytest

cd ..\frontend
npm run lint
npm run build
```

## Roadmap

- **Phase 1 - COMPLETE:** Core deterministic discovery and scoring.
- **Phase 2 - COMPLETE:** Candidate evidence, policies, sources, orchestration, feedback, and agent contracts.
- **Phase 2.5 - COMPLETE:** Multi-source discovery, company registry, ATS detection, expanded connectors, role-family routing, and family-specific scoring.
- **Phase 2.6 - COMPLETE:** Canonical identity hardening, approved application-name mapping, middle-name safeguards, and live-discovery readiness.
- **Phase 3 - CURRENT:** Semantic retrieval, provider-independent LLM infrastructure, semantic FitAgent, attributable ResearchAgent, agent tools, observability, and evaluation.
- **Phase 4:** Evidence-grounded resume tailoring, answer generation, claim validation, and ReviewerAgent.
- **Phase 5:** Playwright BrowserAgent, form understanding, field mapping, resume upload, and application preparation.
- **Phase 6:** Evidence-validated autonomous submission, standing authorization, safe submission, and blocked-question handling.
- **Phase 7:** Outcome learning, ranking calibration, interview-response analysis, and strategy optimization.
- **Phase 8:** Recruiter/team/hiring-manager intelligence and human-approved outreach.
