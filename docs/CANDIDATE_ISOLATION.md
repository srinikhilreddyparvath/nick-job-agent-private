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
