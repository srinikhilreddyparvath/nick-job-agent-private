"""Offline A/B/C reproduction: new temporary DB, fictional candidates, no live server.

Exercises upload/approval APIs, queued Find Jobs, catalog dedupe and mock semantic
caching. The human manual browser launch gate remains separate.
"""
import copy
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/candidate_isolation.json').read_text(encoding='utf-8'))


def configure(directory):
    os.environ.update(DATABASE_URL='sqlite:///' + (directory / 'catalog.db').as_posix(),
                      ENVIRONMENT='development', LLM_ENABLED='false', LLM_PROVIDER='mock',
                      LLM_MODEL='mock-semantic-v1', EMBEDDING_PROVIDER='mock',
                      APPLICATION_MODE='manual', AUTO_SUBMIT_ENABLED='false', DEMO_MODE='false')
    for key, filename in [('PROFILE', 'profile.json'), ('PREFERENCES', 'preferences.json'),
                          ('EVIDENCE', 'evidence.json'), ('ANSWER_BANK', 'answers.json'),
                          ('APPLICATION_POLICY', 'policy.json'), ('PRIVATE_STORAGE', 'private')]:
        os.environ[f'CANDIDATE_{key}_PATH'] = str(directory / filename)
    os.environ['OPENAI_API_KEY'] = ''
    os.environ['ANTHROPIC_API_KEY'] = ''
    sys.path.insert(0, str(ROOT))


def run():
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from app.main import app
    from app.db.database import SessionLocal
    from app.db.models import JobRecord, JobScoreRecord, SemanticAnalysisRecord
    from app.models.job import Job
    from app.services.candidate_context_service import current_context
    from app.services.career_intelligence_service import CareerIntelligenceService
    from app.services.dedupe_service import DedupeService
    from app.services.job_service import JobService

    def get(response):
        assert response.is_success, f'Unexpected HTTP {response.status_code}'
        return response.json()

    results, snapshots, seen_evidence = [], [], set()
    expected = [('AI', {'RESEARCH_AI'}), ('CLINICAL', {'CLINICAL_RESEARCH', 'PUBLIC_HEALTH'}),
                ('PRODUCT', {'PRODUCT_MANAGEMENT'})]
    with TestClient(app) as client, SessionLocal() as db:
        jobs = JobService()
        records = [jobs.create(db, Job.model_validate(value)) for value in FIXTURE['jobs']]
        ids, shared_id = {row.id for row in records}, records[-1].id
        # Unsafe legacy history must remain hidden, never adopted by a new candidate.
        db.connection().execute(JobScoreRecord.__table__.insert().values(
            job_id=shared_id, overall_score=99, component_scores={}, strengths=['STALE_AI_EXPLANATION'],
            gaps=[], matched_skills=['ai', 'ml', 'data', 'platform', 'search', 'product'], missing_skills=[],
            reasoning_summary='STALE_AI_EXPLANATION', recommendation='exceptional'))
        db.commit()
        for label, families in expected:
            request = copy.deepcopy(FIXTURE['candidates'][label])
            resume = '\n'.join([f'Fictional {label} Candidate', request['profile']['roles'][0]['value'],
                                *[item['statement'] for item in request['evidence']]])
            uploaded = get(client.post('/onboarding/resume', files={'file': ('fictional.txt', resume, 'text/plain')},
                                       data={'use_mock': 'true'}))
            assert client.post('/career-intelligence/find-jobs').status_code == 409
            assert get(client.get(f'/jobs/{shared_id}'))['fit_score'] is None
            pending = get(client.get('/onboarding'))
            assert pending['replacement_pending'] and not pending['configured']
            assert pending['preferences']['preferred_domains'] == []
            request['profile']['source_document_id'] = uploaded['metadata']['document_id']
            get(client.put('/onboarding/approve', json=request))
            context = current_context()
            assert context.evidence_ids and not context.evidence_ids & seen_evidence
            seen_evidence |= context.evidence_ids
            assert get(client.get(f'/jobs/{shared_id}'))['fit_score'] is None
            assert client.get(f'/jobs/{shared_id}/analysis').status_code == 404
            assert get(client.get('/career-intelligence/runs/latest')) is None
            queued = get(client.post('/career-intelligence/find-jobs'))
            finished = CareerIntelligenceService().process_next(db)
            assert finished.id == queued['id'] and finished.status == 'completed'
            run_state = get(client.get(f"/career-intelligence/runs/{queued['id']}"))
            assert run_state['unique_jobs'] == 0 and run_state['sources_scanned'] == 0
            ranked = get(client.get('/jobs?view=raw&limit=500'))
            assert ranked['total'] == len(ids)
            assert all(item['role_family'] in families for item in ranked['items'][:20])
            assert all('STALE_AI_EXPLANATION' not in json.dumps(item) for item in ranked['items'])
            for item in ranked['items']:
                assert set(item['matched_evidence_ids']).issubset(context.evidence_ids)
                for match in item['opportunity_score']['why_you_match']:
                    assert set(match['evidence_ids']).issubset(context.evidence_ids)
            unrelated = [item for item in ranked['items'] if item['role_family'] in
                         {'PRODUCT_MANAGEMENT', 'RESEARCH_AI', 'SOFTWARE_ENGINEERING', 'INFORMATION_TECHNOLOGY'}]
            if label == 'CLINICAL':
                assert max(item['opportunity_score']['overall_score'] for item in unrelated) <= 35
            for value in FIXTURE['jobs']:
                assert DedupeService().find_duplicate(db, Job.model_validate(value)).id in ids
            assert db.scalar(select(func.count()).select_from(JobRecord)) == len(ids)
            shared = get(client.get(f'/jobs/{shared_id}'))
            snapshots.append((shared['fit_score'], set(shared['matched_evidence_ids']), shared['gaps']))
            analyzed = get(client.post(f'/jobs/{shared_id}/analyze', json={'use_mock': True}))
            assert analyzed['report'] and not analyzed['report']['cache_hit']
            assert set(analyzed['report']['evidence_ids']).issubset(context.evidence_ids)
            cached = get(client.post(f'/jobs/{shared_id}/analyze', json={'use_mock': True}))
            assert cached['report']['cache_hit']
            db.expire_all()
            evaluations = db.scalars(select(JobScoreRecord)).all()
            assert len(evaluations) == len(ids)
            assert all(row.candidate_context_key == context.key for row in evaluations)
            result = dict(candidate=label, profile_id=context.profile_id, profile_version=context.profile_version,
                          context_key=context.key, global_jobs=len(ids), new_unique_jobs=0, sources_refetched=0,
                          dedupe_hits=len(ids), evaluations=len(evaluations),
                          top20_families=dict(Counter(item['role_family'] for item in ranked['items'][:20])),
                          top_roles=[{'title': item['title'], 'score': item['opportunity_score']['overall_score']}
                                     for item in ranked['items'][:3]],
                          shared_job_id=shared_id, shared_fit_score=shared['fit_score'],
                          shared_opportunity_score=shared['opportunity_score']['overall_score'],
                          shared_evidence_count=len(shared['matched_evidence_ids']), shared_gaps=shared['gaps'],
                          semantic_first_hit=False, semantic_repeat_hit=True)
            if label == 'CLINICAL':
                result['max_unrelated_opportunity_score'] = max(item['opportunity_score']['overall_score'] for item in unrelated)
            results.append(result)
            print(json.dumps(result), flush=True)
        rows = db.scalars(select(JobScoreRecord).where(JobScoreRecord.job_id == shared_id)
                          .execution_options(candidate_history_audit=True)).all()
        owned = [row for row in rows if row.candidate_profile_id]
        assert len(owned) == 3 and len({row.candidate_context_key for row in owned}) == 3
        assert len(rows) == 4  # ownerless legacy history is preserved
        assert len({snapshot[0] for snapshot in snapshots}) >= 2
        assert len({tuple(snapshot[2]) for snapshot in snapshots}) == 3
        assert all(snapshots[i][1] and not snapshots[i][1] & snapshots[j][1]
                   for i in range(3) for j in range(i + 1, 3))
        semantics = db.scalars(select(SemanticAnalysisRecord).where(SemanticAnalysisRecord.job_id == shared_id)
                               .execution_options(candidate_history_audit=True)).all()
        assert len(semantics) == 3 and len({row.fingerprint for row in semantics}) == 3
    return {'status': 'PASS', 'candidates': results, 'shared_evaluation_owners': 3,
            'shared_semantic_owners': 3, 'ownerless_history_hidden': True,
            'external_requests': 0, 'human_manual_cross_profession_test': 'STILL REQUIRED'}


def main():
    with tempfile.TemporaryDirectory(prefix='rolecall-reproduction-') as directory:
        configure(Path(directory))
        # TestClient uses its own transport. Any external HTTP attempt fails.
        with patch('httpx.HTTPTransport.handle_request', side_effect=AssertionError('External HTTP prohibited')):
            try:
                report = run()
            finally:
                from app.db.database import engine
                engine.dispose()
    output = ROOT / 'tmp/candidate-isolation-reproduction/report.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(output),
                      'human_manual_cross_profession_test': 'STILL REQUIRED'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
