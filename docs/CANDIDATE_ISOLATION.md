# Candidate isolation repair

## Pre-migration Job field audit

Relationships are included; application and feedback state are candidate owned. Job role classification describes the job only.

| Field | Classification |
| --- | --- |
| `id` | GLOBAL_JOB_FACT |
| `external_id` | GLOBAL_JOB_FACT |
| `source` | GLOBAL_JOB_FACT |
| `company` | GLOBAL_JOB_FACT |
| `title` | GLOBAL_JOB_FACT |
| `normalized_title` | GLOBAL_JOB_FACT |
| `location` | GLOBAL_JOB_FACT |
| `remote_type` | GLOBAL_JOB_FACT |
| `employment_type` | GLOBAL_JOB_FACT |
| `salary_min` | GLOBAL_JOB_FACT |
| `salary_max` | GLOBAL_JOB_FACT |
| `salary_currency` | GLOBAL_JOB_FACT |
| `description` | GLOBAL_JOB_FACT |
| `requirements` | GLOBAL_JOB_FACT |
| `preferred_qualifications` | GLOBAL_JOB_FACT |
| `apply_url` | GLOBAL_JOB_FACT |
| `canonical_apply_url` | GLOBAL_JOB_FACT |
| `source_url` | GLOBAL_JOB_FACT |
| `posted_at` | GLOBAL_JOB_FACT |
| `discovered_at` | GLOBAL_JOB_FACT |
| `created_at` | GLOBAL_JOB_FACT |
| `updated_at` | GLOBAL_JOB_FACT |
| `role_family` | GLOBAL_JOB_FACT |
| `role_family_confidence` | GLOBAL_JOB_FACT |
| `role_family_reasons` | GLOBAL_JOB_FACT |
| `classification_method` | GLOBAL_JOB_FACT |
| `deterministic_family` | GLOBAL_JOB_FACT |
| `deterministic_confidence` | GLOBAL_JOB_FACT |
| `semantic_family` | GLOBAL_JOB_FACT |
| `semantic_confidence` | GLOBAL_JOB_FACT |
| `final_family` | GLOBAL_JOB_FACT |
| `classification_resolution_method` | GLOBAL_JOB_FACT |
| `family_fit_score` | CANDIDATE_SPECIFIC_EVALUATION |
| `family_component_scores` | CANDIDATE_SPECIFIC_EVALUATION |
| `family_recommendation` | CANDIDATE_SPECIFIC_EVALUATION |
| `family_strengths` | CANDIDATE_SPECIFIC_EVALUATION |
| `family_gaps` | CANDIDATE_SPECIFIC_EVALUATION |
| `matched_evidence_ids` | CANDIDATE_SPECIFIC_EVALUATION |
| `career_transition_flag` | CANDIDATE_SPECIFIC_EVALUATION |
| `career_transition_notes` | CANDIDATE_SPECIFIC_EVALUATION |
| `raw_company` | GLOBAL_JOB_FACT |
| `canonical_company` | GLOBAL_JOB_FACT |
| `normalized_location` | GLOBAL_JOB_FACT |
| `description_fingerprint` | GLOBAL_JOB_FACT |
| `alternate_sources` | GLOBAL_JOB_FACT |
| `first_seen_at` | GLOBAL_JOB_FACT |
| `last_seen_at` | GLOBAL_JOB_FACT |
| `last_verified_at` | GLOBAL_JOB_FACT |
| `posting_status` | GLOBAL_JOB_FACT |
| `scores` | CANDIDATE_SPECIFIC_EVALUATION |
| `application` | CANDIDATE_SPECIFIC_EVALUATION |
| `feedback` | CANDIDATE_SPECIFIC_EVALUATION |
| `semantic_analyses` | CANDIDATE_SPECIFIC_EVALUATION |


## Preserved failure-state observations (IDs, counts, versions and types only)

- Profile ID, profile version, approval timestamp, preference ID/version: absent in the previous schema/files.
- Latest uploaded/extracted document ID: `f2a6223b29224bb5`; did not match the active approved evidence document.
- Approved profile file modification timestamp: `2026-09-09T16:27:32.623676+00:00` (not an approval audit timestamp).
- Active evidence: 23 items (experience 5, skills 13, education 2, projects 2, research 1).
- Active target-role count: 0. Profession-specific preference leakage exists in the replacement UI, but was not established in this snapshot's empty target roles.
- Global jobs: 4,109; global fit results: 4,109; global fit scores above 90: 62.
- Global role types: UNKNOWN 3,861; PRODUCT_MANAGEMENT 154; RESEARCH_AI 58; DATA_SCIENCE 36.
- Latest scan ID 6: 20 sources; 4,527 fetched; 0 added; 4,527 duplicates; 0 rescored.
- Job evidence references: 2,672; references outside the still-active approved evidence: 0.
- Semantic rows: 40; evidence versions: 1. Candidate/profile/preference owner columns: 0.
- Database snapshot retained in the original PostgreSQL container at `/tmp/rolecall-pre-isolation.dump`; it is private runtime data and must never be synchronized or committed.

The new upload had produced a draft while Find Jobs continued using the previous approved candidate. Independently, duplicate jobs bypassed rescoring, Job fit fields were ownerless, semantic reads chose the latest job-only row, and family scores rewarded job vocabulary without candidate evidence.

## Ownership and migration

`CandidateJobEvaluationRecord` is the existing `JobScoreRecord` / `job_scores` abstraction extended with candidate profile ID, profile version, preference fingerprint, complete candidate/evidence context fingerprint, job-content version, family evaluation, OpportunityScore and constraints. Uniqueness is `(candidate_context_key, job_id)`. The context includes profile ID/version, profile content, evidence content and ownership, preference content/version, and evaluation schema version. Semantic analyses use the same ownership and additionally key job identity/content, evidence version, prompt version, provider and model.

Application history and associated artifacts are scoped by candidate identity; evaluation artifacts are scoped by the full versioned context. Anonymous legacy owners remain NULL and hidden. The migration never guesses ownership and does not delete global job facts. Global job fit columns are removed. Profile/evidence/preferences are published as a single atomic canonical bundle. Replacement creates a new identity; subsequent approvals advance its version. New uploads suspend Find Jobs until the current draft and preferences are approved.

No providers were added. Taxonomy changes classify existing jobs across professions. Scoring requires discriminative signals in both the job and profile-owned verified evidence. Unrelated career families are capped at 35 after semantic blending and freshness. Adjacent roles and explicitly targeted transitions retain bounded consideration.

## Follow-up audit and hardening (2026-09-12)

The audit resumed from `de42891`. The checkpoint's 15 isolation tests passed, but six additional regressions failed before the following repairs:

| Boundary | Remaining failure | Repair |
| --- | --- | --- |
| Manual ingestion | A reused service retained the previous profile and could commit its baseline score under the new owner before evidence validation rejected family fit | Capture current profile, preferences and evidence together at ingestion; use that context for every score write |
| Direct semantic analysis | Analyze could run before Find Jobs and bypass the deterministic career-family gate | Evaluate that job for the current candidate before semantic analysis; rankings require a valid deterministic evaluation before exposing semantic fit |
| Evidence embeddings | A reused index could assign old evidence vectors to the current context | Validate evidence ownership before embedding and bind writes to the captured context |
| Company/role research cache | Candidate-scoped reads missed another candidate's row, but the globally unique fingerprint collided on insertion | Include job identity/content and candidate context in the research fingerprint; validate context before persistence |
| Job edits | Company and salary currency changes did not invalidate fit | Include both fields and normalize enum values in the job-content fingerprint; clear old family fit when job content changes |
| Corrupt evaluation history | Reads hid foreign evidence, but Find Jobs considered the row complete and never repaired it | Recompute evaluations whose evidence ownership is invalid |

Generic Research Scientist, Research Engineer and Applied Scientist titles now require AI-specific job evidence before being classified as AI. Clinical and public-health research responsibilities establish their corresponding family; other research remains generic. Explicitly targeted career transitions are still supported and limited when domain evidence is missing.

The candidate context uses `candidate-fit-v3` and includes scoring weights and recommendation thresholds as well as profile identity/version, full profile/evidence content and preference content/version. This invalidates prior evaluations without assigning them a new owner or deleting history. Semantic generation fingerprints also include prompt version, provider, model and evidence version. Ranking/detail reads reject obsolete fit prompt versions. Existing tests that supplied an obsolete prompt identifier were updated to use the current version; the classifier-version assertion was corrected to match the checkpoint's existing `role-classifier-v2` prompt.

No migration was changed or added. Migration `20260909_0006` remains required. Application history remains scoped by candidate identity; evaluation history remains scoped by the complete candidate context. New uploads reset inferred preferences and suspend evaluation until review; approval writes an atomic profile/evidence/preferences bundle. The UI builds its filter buttons from returned role families. The replacement explanation also had a literal `r?sum?` corrected to `résumé`.

## Reproduction evidence

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe scripts/candidate_isolation_reproduction.py
```

The script now creates its own temporary SQLite database and candidate store instead of replacing a candidate on a live development server. It uses only fictional fixtures and mock semantic generation, rejects external HTTP, uploads each fictional TXT document, checks the pending-review boundary, approves the candidate, and processes the real Find Jobs queue. It seeds a poisoned ownerless 99-point AI evaluation and verifies that it stays hidden. It checks every catalog item for deduplication after each switch, validates evidence ownership, compares shared-job scores and gaps, and verifies separate semantic cache misses followed by same-candidate hits. Only a sanitized report is saved under ignored `backend/tmp/`.

Observed results on the same 64 global jobs:

| Fictional candidate | Top 20 families | Representative roles | Shared product-role fit / opportunity |
| --- | --- | --- | --- |
| AI/search/ML | 20 Research/AI | Machine Learning Engineer, Search Ranking Scientist, Research Engineer | 6.6 / 25.3 |
| Clinical/cancer trials/public health | 16 Clinical Research, 4 Public Health | Clinical Research Coordinator, Clinical Research Associate, Public Health Analyst | 6.6 / 25.3 |
| Product management | 20 Product Management | Senior Product Manager, Staff Product Manager, Group Product Manager | 97.6 / 98.1 |

Each candidate had 64 separately owned evaluations, 64 catalog dedupe matches, zero new jobs and zero source refetches. The shared job retained three distinct evaluation owners and three distinct semantic fingerprints; matched evidence sets were disjoint and gaps differed across all three candidates. The highest unrelated clinical-candidate opportunity score was 25.3. Equal low A/B scores on the shared product role are independent evaluations, not reuse; their evidence and gaps differ.

A separate automated browser run exercised the existing upload/review/approval UI against a fresh PostgreSQL Compose stack containing the same fictional catalog. All three candidates had 20/20 appropriate top results, zero new jobs, distinct profile/evidence ownership, and a semantic cache miss for the shared job. Clinical filter buttons were All, Clinical research and Public health. Desktop and 390-pixel mobile checks passed with zero browser errors. No application or outreach was sent. These browser checks used mock extraction and semantic generation.

## Migration and regression verification

`scripts/verify_candidate_migrations.py` requires an isolated, trust-authenticated PostgreSQL instance at `127.0.0.1:55439`. It creates uniquely named test databases and never opens or deletes a development database. For example, start a dedicated instance with:

```powershell
docker run -d --name rolecall-migration-check -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55439:5432 postgres:16-alpine
.\.venv\Scripts\python.exe scripts/verify_candidate_migrations.py
```

Both migration paths passed:

- Empty database to `20260909_0006`, followed by independent A/B/C evaluations.
- The actual pre-isolation ORM schema from Git commit `4f741bd`, seeded with fictional job, score, application and exclusion history, upgraded through `0005` to `0006`. Global facts and all four historical rows survived; candidate owners remained NULL; global fit columns were removed; the exclusion primary-key conversion and candidate/job uniqueness worked. A/B/C evaluations remained distinct on the upgraded job.

Pytest now uses a fresh temporary database per invocation and closes its sessions before cleanup, so it cannot drop a pre-existing `test_nick_job_agent.db` in the working directory.

Verification commands include the 27 candidate-isolation cases, the complete backend pytest suite, `scripts/eval.py`, Python compilation, `npm run lint`, `npm run build`, `docker compose ps`, and `scripts/doctor.ps1`. The final full backend run passed 306 tests; its four opt-in browser tests were run separately with `RUN_FRONTEND_E2E=1` and all passed. Golden evaluations passed all 107 cases. Frontend lint/build, compile checks, both migration paths and Doctor passed. Doctor was run against the isolated verification stack; the user's existing databases and Docker volumes were preserved. Only dependency deprecation warnings remained.

**Release remains blocked until a human successfully performs the manual cross-profession test.** Automated fixture and browser results do not establish production ranking quality or satisfy that human launch gate.
