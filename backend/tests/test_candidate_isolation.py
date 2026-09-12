"""Cross-profession regressions use one persisted, entirely fictional catalog."""
import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import JobRecord, JobScoreRecord, SemanticAnalysisRecord
from app.models.job import Job
from app.models.onboarding import OnboardingApprovalRequest
from app.services.candidate_context_service import current_context, job_version, state_path
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.career_intelligence_service import CareerIntelligenceService
from app.services.evidence_service import EvidenceService
from app.services.family_scoring_service import FamilyScoringEngine
from app.services.job_service import JobService
from app.services.llm_service import configured_llm_service
from app.services.opportunity_service import OpportunityScoringService
from app.services.scoring_service import terms
from app.services.semantic_analysis_service import SemanticAnalysisService

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/candidate_isolation.json').read_text())


def approve(label):
    return CandidatePersistenceService().approve(OnboardingApprovalRequest.model_validate(copy.deepcopy(FIXTURE['candidates'][label])))


def catalog(db):
    jobs = JobService()
    return [jobs.create(db, Job.model_validate(value)) for value in FIXTURE['jobs']]


def test_same_catalog_three_candidates_and_top_twenty():
    with SessionLocal() as db:
        records = catalog(db)
        ids = {x.id for x in records}
        shared_id = records[-1].id
        snapshots = []
        for label, families in [('AI', {'RESEARCH_AI'}), ('CLINICAL', {'CLINICAL_RESEARCH','PUBLIC_HEALTH'}), ('PRODUCT', {'PRODUCT_MANAGEMENT'})]:
            approve(label)
            db.expire_all()
            jobs = JobService()
            assert all(x.fit_score is None for x in jobs.list(db).items)
            context = current_context()
            run = CareerIntelligenceService().enqueue(db)
            assert run.input_state_json['scan_required'] is False
            finished = CareerIntelligenceService().process_next(db)
            assert finished.status == 'completed', finished.errors_json
            assert finished.output_state_json['unique_jobs'] == 0
            ranked = jobs.list(db, limit=100).items
            assert all(x.role_family in families for x in ranked[:20])
            assert {x.id for x in db.scalars(select(JobRecord))} == ids
            evaluations = db.scalars(select(JobScoreRecord)).all()
            assert len(evaluations) == len(records)
            assert all(x.candidate_context_key == context.key for x in evaluations)
            assert all(set(x.matched_evidence_ids).issubset(context.evidence_ids) for x in evaluations)
            shared = next(x for x in ranked if x.id == shared_id)
            snapshots.append((shared.fit_score, set(shared.matched_evidence_ids), shared.gaps, context.key))
            if label == 'CLINICAL':
                assert not any(x.opportunity_score.overall_score > 90 for x in ranked if x.role_family in {'PRODUCT_MANAGEMENT','RESEARCH_AI','SOFTWARE_ENGINEERING','INFORMATION_TECHNOLOGY'})
        historical = db.scalars(select(JobScoreRecord).where(JobScoreRecord.job_id == shared_id).execution_options(candidate_history_audit=True)).all()
        assert len(historical) == 3
        assert len({x[0] for x in snapshots}) >= 2
        assert all(x[1] for x in snapshots)
        assert all(not snapshots[i][1] & snapshots[j][1] for i in range(3) for j in range(i+1,3))
        assert len({tuple(x[2]) for x in snapshots}) == 3
        assert len({x[3] for x in snapshots}) == 3


def test_profile_version_preferences_and_evidence_edit_invalidate():
    state = approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        first = current_context()
        request = OnboardingApprovalRequest(profile=state.profile, evidence=state.evidence, preferences=state.preferences, preferences_reviewed=True)
        state = CandidatePersistenceService().approve(request)
        second = current_context()
        assert second.profile_id == first.profile_id and second.profile_version == first.profile_version + 1
        assert not second.evidence_ids & first.evidence_ids
        assert JobService().to_schema(record).fit_score is None
        JobService().evaluate_catalog(db)
        CandidatePersistenceService().save_preferences(state.preferences.model_copy(update={'preferred_titles':['Senior Product Manager']}))
        assert current_context().preference_version != second.preference_version
        assert JobService().to_schema(record).fit_score is None


def test_replacement_confirmation_and_review_required():
    approve('AI')
    value = copy.deepcopy(FIXTURE['candidates']['CLINICAL'])
    value['confirm_replacement'] = False
    with pytest.raises(ValueError, match='Confirm replacement'):
        CandidatePersistenceService().approve(OnboardingApprovalRequest.model_validate(value))
    value['confirm_replacement'] = True
    value['preferences_reviewed'] = False
    with pytest.raises(ValueError, match='Review target'):
        CandidatePersistenceService().approve(OnboardingApprovalRequest.model_validate(value))


def test_active_candidate_api_and_history_isolation(client):
    approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        job_id = record.id
        first_context = current_context()
        assert client.post(f'/jobs/{job_id}/shortlist').status_code == 200
        assert client.get(f'/jobs/{job_id}').json()['fit_score'] is not None
    approve('CLINICAL')
    for path in [f'/jobs/{job_id}', '/jobs?view=raw']:
        value = client.get(path).json()
        job = value['items'][0] if 'items' in value else value
        assert job['fit_score'] is None and not job['matched_evidence_ids']
        assert job['application_status'] == 'discovered'
        assert job['semantic_analysis_status'] == 'NOT_ANALYZED'
    assert client.get(f'/jobs/{job_id}/analysis').status_code == 404
    assert client.get(f'/jobs/{job_id}/opportunity').json()['overall_score'] == 0
    assert client.get('/career-intelligence/runs/latest').json() is None
    assert client.get(f'/profile/evidence/{next(iter(first_context.evidence_ids))}').status_code == 404
    assert client.post(f'/jobs/{job_id}/shortlist').status_code == 200


def test_persistence_rejects_foreign_evidence_and_midrun_switch():
    approve('AI')
    old = current_context()
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        row = JobService().evaluation(db, record.id)
        row.matched_evidence_ids = ['OTHER_CANDIDATE_EVIDENCE']
        with pytest.raises(ValueError, match='Evidence does not belong'): db.commit()
        db.rollback()
        approve('CLINICAL')
        with pytest.raises(ValueError, match='Candidate changed'): JobService().evaluate_catalog(db, old)


def test_read_rejects_corrupt_evidence_even_with_matching_owner():
    approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        row = JobService().evaluation(db, record.id)
        # Simulate historical corruption below the ORM persistence boundary.
        db.connection().execute(JobScoreRecord.__table__.update().where(JobScoreRecord.id==row.id).values(matched_evidence_ids=['FOREIGN']))
        db.commit();db.expire_all()
        assert JobService().to_schema(JobService().get(db, record.id)).fit_score is None


def test_semantic_cache_includes_job_candidate_preferences_and_schema(monkeypatch):
    approve('AI')
    service = SemanticAnalysisService(configured_llm_service(use_mock=True))
    job = Job.model_validate(FIXTURE['jobs'][0]);job.id = 1
    first = service.fingerprint(job, 'same-evidence-version')
    changed_job = job.model_copy(update={'id':2})
    assert service.fingerprint(changed_job,'same-evidence-version') != first
    approve('CLINICAL')
    second = service.fingerprint(job,'same-evidence-version')
    assert second != first
    preferences = current_context().preferences.model_copy(update={'remote_allowed':False})
    CandidatePersistenceService().save_preferences(preferences)
    assert service.fingerprint(job,'same-evidence-version') != second
    monkeypatch.setattr('app.services.semantic_analysis_service.VERSION','new-schema')
    assert service.fingerprint(job,'same-evidence-version') != second


def test_semantic_result_recomputed_with_reused_service():
    approve('AI')
    service = SemanticAnalysisService(configured_llm_service(use_mock=True))
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][-1]))
        versions=[]
        for label in ['AI','CLINICAL','PRODUCT']:
            if label != 'AI': approve(label)
            db.expire_all();JobService().evaluate_catalog(db)
            result = service.analyze(db, record.id)
            assert result.report is not None, result.error
            assert not result.report.cache_hit
            versions.append(current_context().key)
            rows = db.scalars(select(SemanticAnalysisRecord)).all()
            assert len(rows)==1 and rows[0].candidate_context_key==versions[-1]
            assert set(result.report.evidence_ids).issubset(current_context().evidence_ids)
            assert service.analyze(db,record.id).report.cache_hit
        rows = db.scalars(select(SemanticAnalysisRecord).execution_options(candidate_history_audit=True)).all()
        assert len(rows)==3 and len({x.fingerprint for x in rows})==3


@pytest.mark.parametrize('title',['Staff Product Manager','Software Engineering Intern','Storage Administrator'])
def test_clinical_role_family_cap_survives_perfect_semantics(title):
    state=approve('CLINICAL')
    job=Job.model_validate({**FIXTURE['jobs'][-1], 'title':title})
    result=FamilyScoringEngine().score(job,state.profile,state.preferences)
    job.fit_score=result.family_fit_score;job.family_component_scores=result.family_component_scores
    job.semantic_fit_score=100;job.semantic_fit_confidence=1
    assert OpportunityScoringService().score(job,state.preferences).overall_score<=35


def test_generic_terms_never_count_as_strong_candidate_evidence():
    assert not terms(['problem requirements customer data platform product research'])
    state=approve('CLINICAL')
    job=Job.model_validate({**FIXTURE['jobs'][-1], 'description':'problem requirements customer data platform product research '*100})
    result=FamilyScoringEngine().score(job,state.profile,state.preferences)
    assert result.family_fit_score<=35 and result.strengths==[] and result.matched_evidence_ids==[]


def test_pending_resume_prevents_old_profile_approval_and_find_jobs(client):
    state=approve('AI')
    state_path().with_suffix('.pending.json').write_text(json.dumps({'document_id':'new-clinical-draft'}))
    assert client.post('/career-intelligence/find-jobs').status_code==409
    value=OnboardingApprovalRequest(profile=state.profile,evidence=state.evidence,preferences=state.preferences,preferences_reviewed=True)
    with pytest.raises(ValueError,match='latest uploaded'): CandidatePersistenceService().approve(value)


def test_global_job_model_contains_no_candidate_fit_columns():
    assert not {'family_fit_score','family_component_scores','family_strengths','family_gaps','matched_evidence_ids','career_transition_flag'} & set(JobRecord.__table__.columns.keys())


def test_ui_filters_are_generated_from_returned_families():
    source=(Path(__file__).resolve().parents[2]/'frontend/components/Dashboard.tsx').read_text()
    assert 'new Set(data.items' in source
    assert 'const families=["ALL","RESEARCH_AI"' not in source
    assert 'freshPreferences(result.draft.profile.roles)' in (Path(__file__).resolve().parents[2]/'frontend/app/onboarding/page.tsx').read_text()


def test_reused_ingestion_service_cannot_relabel_old_candidate_fit():
    from app.models.ingestion import JobTextIngestRequest
    from app.services.ingestion_service import JobIngestionService
    state = approve('AI')
    service = JobIngestionService(state.profile, state.preferences)
    approve('CLINICAL')
    with SessionLocal() as db:
        result = service.ingest_text(db, JobTextIngestRequest(
            title='Machine Learning Engineer', company='Fictional Ingestion Lab',
            source_url='https://example.test/ingestion',
            job_description_text='machine learning retrieval search ranking pytorch tensorflow nlp llm python'))
        assert result.job.fit_score <= 35
        assert not result.job.matched_evidence_ids
        assert not result.job.matched_skills


def test_analyze_before_find_jobs_still_applies_clinical_family_gate(client):
    approve('CLINICAL')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        job_id = record.id
    response = client.post(f'/jobs/{job_id}/analyze', json={'use_mock': True})
    assert response.status_code == 200
    assert response.json()['report'], response.json()
    job = client.get(f'/jobs/{job_id}').json()
    assert job['fit_score'] is not None
    assert job['family_component_scores']['role_family_gate']['score'] <= 35
    assert job['opportunity_score']['overall_score'] <= 35


def test_reused_evidence_index_rejects_foreign_candidate():
    from app.services.semantic_evidence_service import SemanticEvidenceIndex
    approve('AI')
    index = SemanticEvidenceIndex()
    approve('CLINICAL')
    with SessionLocal() as db, pytest.raises(ValueError, match='Evidence does not belong'):
        index.reindex(db)


def test_company_research_cache_allows_same_job_for_distinct_candidates():
    from app.db.models import CompanyResearchRecord
    from app.services.research_service import ResearchService, SuppliedDataResearchProvider
    approve('AI')
    service = ResearchService(configured_llm_service(use_mock=True), SuppliedDataResearchProvider())
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        for label in ['AI', 'CLINICAL', 'PRODUCT']:
            if label != 'AI': approve(label)
            result = service.research(db, record.id)
            assert result.report and not result.report.cache_hit, result.error
            assert service.research(db, record.id).report.cache_hit
        rows = db.scalars(select(CompanyResearchRecord).execution_options(candidate_history_audit=True)).all()
        assert len(rows) == 3 and len({row.fingerprint for row in rows}) == 3


def test_job_edit_invalidates_fit_and_semantics(client):
    approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        result = SemanticAnalysisService(configured_llm_service(use_mock=True)).analyze(db, record.id)
        assert result.report
        record.salary_currency = 'EUR'
        db.commit()
        assert JobService().to_schema(record).fit_score is None
        assert client.get(f'/jobs/{record.id}/analysis').status_code == 404


def test_corrupt_evaluation_is_repaired_by_find_jobs():
    approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        JobService().evaluate_catalog(db)
        row = JobService().evaluation(db, record.id)
        db.connection().execute(JobScoreRecord.__table__.update().where(JobScoreRecord.id == row.id)
                                .values(matched_evidence_ids=['FOREIGN']))
        db.commit(); db.expire_all()
        assert JobService().evaluate_catalog(db) == 1
        assert JobService().to_schema(record).fit_score is not None


@pytest.mark.parametrize(('title', 'description', 'expected'), [
    ('Research Scientist', 'Lead oncology clinical trials with IRB and GCP protocols.', 'CLINICAL_RESEARCH'),
    ('Applied Scientist', 'Study public health and population health outcomes.', 'PUBLIC_HEALTH'),
    ('Research Engineer', 'Develop laboratory instruments and study design.', 'RESEARCH'),
    ('Research Scientist', 'Develop machine learning retrieval and ranking models.', 'RESEARCH_AI'),
])
def test_generic_research_titles_are_profession_neutral(title, description, expected):
    from app.services.role_family_service import DeterministicRoleFamilyClassifier
    job = Job.model_validate({**FIXTURE['jobs'][0], 'title': title, 'description': description,
                             'requirements': [], 'preferred_qualifications': []})
    assert DeterministicRoleFamilyClassifier().classify(job).role_family == expected


def test_evaluator_and_prompt_changes_invalidate_current_results(client, monkeypatch):
    approve('AI')
    with SessionLocal() as db:
        record = JobService().create(db, Job.model_validate(FIXTURE['jobs'][0]))
        result = SemanticAnalysisService(configured_llm_service(use_mock=True)).analyze(db, record.id)
        assert result.report
        monkeypatch.setattr('app.prompts.fit_analysis_v1.VERSION', 'updated-prompt')
        assert JobService().to_schema(record).semantic_analysis_status == 'NOT_ANALYZED'
        assert client.get(f'/jobs/{record.id}/analysis').status_code == 404
        monkeypatch.setattr('app.services.candidate_context_service.EVALUATOR_VERSION', 'updated-evaluator')
        assert JobService().to_schema(record).fit_score is None


def test_explicit_transition_requires_review_and_preserves_evidence_limits():
    state = approve('CLINICAL')
    preferences = state.preferences.model_copy(update={'preferred_titles': ['Product Manager']})
    CandidatePersistenceService().save_preferences(preferences)
    job = Job.model_validate({**FIXTURE['jobs'][0], 'title': 'Product Manager',
                             'description': 'product management roadmap product strategy product discovery',
                             'requirements': [], 'preferred_qualifications': []})
    result = FamilyScoringEngine().score(job, state.profile, current_context().preferences)
    assert result.career_transition_flag
    assert result.family_fit_score <= 69
    assert not result.matched_evidence_ids

