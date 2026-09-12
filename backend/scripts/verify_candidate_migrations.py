"""Verify fresh and populated pre-isolation upgrades on disposable PostgreSQL.

Requires an isolated, trust-authenticated PostgreSQL on loopback port 55439.
Creates uniquely named databases; never connects to a developer database.
The historical ORM schema comes from the checked-in pre-isolation Git commit.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = 'postgresql+psycopg://postgres@127.0.0.1:55439/postgres'


def command(args, env):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def main():
    from sqlalchemy import create_engine, inspect, text
    admin = create_engine(ADMIN_URL, isolation_level='AUTOCOMMIT')
    reports = []
    with tempfile.TemporaryDirectory(prefix='rolecall-migration-') as directory:
        directory = Path(directory)
        for case in ('fresh', 'existing'):
            name = 'rolecall_verify_' + case + '_' + uuid4().hex[:12]
            with admin.connect() as db:
                db.execute(text(f'CREATE DATABASE "{name}"'))
            url = ADMIN_URL.rsplit('/', 1)[0] + '/' + name
            env = {**os.environ, 'DATABASE_URL': url, 'APPLICATION_MODE': 'manual',
                   'AUTO_SUBMIT_ENABLED': 'false', 'LLM_ENABLED': 'false',
                   'CANDIDATE_PROFILE_PATH': str(directory / 'profile.json'),
                   'CANDIDATE_EVIDENCE_PATH': str(directory / 'evidence.json'),
                   'CANDIDATE_PREFERENCES_PATH': str(directory / 'preferences.json'),
                   'CANDIDATE_PRIVATE_STORAGE_PATH': str(directory / 'private'),
                   'PYTHONPATH': str(ROOT)}
            if case == 'existing':
                legacy = subprocess.run(['git', 'show', '4f741bd:backend/app/db/models.py'],
                                        cwd=ROOT, check=True, capture_output=True).stdout
                source = directory / 'legacy_models.py'
                source.write_bytes(legacy)
                seed = directory / 'seed.py'
                seed.write_text('''from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from legacy_models import Base, JobRecord, JobScoreRecord, ApplicationRecord, JobExclusionRecord
from app.core.config import get_settings
engine = create_engine(get_settings().database_url)
Base.metadata.create_all(engine)
with Session(engine) as db:
    job = JobRecord(external_id="fictional-legacy", source="fictional", company="Fictional Migration Lab",
        title="Machine Learning Engineer", normalized_title="machine learning engineer",
        description="Fictional historical posting", apply_url="https://example.test/migration",
        canonical_apply_url="https://example.test/migration", source_url="https://example.test/migration",
        family_fit_score=99, family_strengths=["STALE_FICTIONAL_AI_FIT"], matched_evidence_ids=["OLD_FICTIONAL_EVIDENCE"])
    db.add(job); db.flush()
    db.add(JobScoreRecord(job_id=job.id, overall_score=99, component_scores={}, strengths=["STALE_FICTIONAL_AI_FIT"],
        gaps=[], matched_skills=["ai"], missing_skills=[], reasoning_summary="Fictional legacy history", recommendation="exceptional"))
    db.add(ApplicationRecord(job_id=job.id, status="shortlisted"))
    db.add(JobExclusionRecord(job_id=job.id, reason="Fictional legacy exclusion"))
    db.commit()
engine.dispose()
''', encoding='utf-8')
                command([sys.executable, str(seed)], env)
                # Historical ORM was the pre-isolation schema at 0004. Exercise
                # the real provider-text migration and then candidate isolation.
                command([sys.executable, '-m', 'alembic', 'stamp', '20260907_0004'], env)
                command([sys.executable, '-m', 'alembic', 'upgrade', '20260909_0005'], env)
            command([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env)
            engine = create_engine(url)
            with engine.connect() as db:
                assert db.scalar(text('SELECT version_num FROM alembic_version')) == '20260909_0006'
                columns = {column['name'] for column in inspect(db).get_columns('jobs')}
                assert not {'family_fit_score', 'family_strengths', 'matched_evidence_ids'} & columns
                count = db.scalar(text('SELECT count(*) FROM jobs'))
                assert count == (1 if case == 'existing' else 0)
                if case == 'existing':
                    for table in ('job_scores', 'applications', 'job_exclusions'):
                        assert db.scalar(text(f'SELECT count(*) FROM {table} WHERE candidate_profile_id IS NULL')) == 1
                    assert db.scalar(text('SELECT overall_score FROM job_scores')) == 99
                    assert db.scalar(text('SELECT description FROM jobs')) == 'Fictional historical posting'
                    assert inspect(db).get_pk_constraint('job_exclusions')['constrained_columns'] == ['id']
                constraints = inspect(db).get_unique_constraints('job_scores')
                assert any(set(item['column_names']) == {'candidate_context_key', 'job_id'} for item in constraints)
            # Use the upgraded schema through the actual A/B/C scoring service.
            verify = directory / 'verify.py'
            verify.write_text('''import copy,json
from pathlib import Path
from sqlalchemy import select
from app.db.database import SessionLocal,engine
from app.db.models import JobRecord,JobScoreRecord
from app.models.job import Job
from app.models.onboarding import OnboardingApprovalRequest
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.job_service import JobService
fixture=json.loads(Path("tests/fixtures/candidate_isolation.json").read_text())
with SessionLocal() as db:
    jobs=JobService()
    record=db.scalar(select(JobRecord)) or jobs.create(db,Job.model_validate(fixture['jobs'][0]))
    for label in ['AI','CLINICAL','PRODUCT']:
        CandidatePersistenceService().approve(OnboardingApprovalRequest.model_validate(copy.deepcopy(fixture['candidates'][label])))
        db.expire_all()
        assert jobs.to_schema(jobs.get(db,record.id)).fit_score is None
        assert jobs.evaluate_catalog(db)==1
        assert len(db.scalars(select(JobScoreRecord)).all())==1
    rows=db.scalars(select(JobScoreRecord).execution_options(candidate_history_audit=True)).all()
    assert len({row.candidate_profile_id for row in rows if row.candidate_profile_id})==3
engine.dispose()
''', encoding='utf-8')
            command([sys.executable, str(verify)], env)
            engine.dispose()
            reports.append({'case': case, 'database': name, 'migration': '20260909_0006',
                            'global_rows_preserved': count, 'candidate_owners_verified': 3, 'status': 'PASS'})
            print(json.dumps(reports[-1]), flush=True)
    admin.dispose()
    output = ROOT / 'tmp/candidate-isolation-reproduction/migrations.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reports, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
