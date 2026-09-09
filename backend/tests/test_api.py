from app.db.database import SessionLocal
from app.models.job import Job
from app.services.job_service import JobService


def make_job():
    return Job(external_id="abc-123", source="test", company="Example Labs", title="Senior ML Engineer", location="Remote", remote_type="remote", description="Build Python machine learning systems", requirements=["Python", "Machine learning"], preferred_qualifications=["Research"], apply_url="https://example.com/jobs/abc-123", source_url="https://example.com/jobs/abc-123")


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_job_lifecycle(client):
    with SessionLocal() as db:
        record = JobService().create(db, make_job()); job_id = record.id
    assert client.get("/jobs").json()["total"] == 1
    scored = client.post(f"/jobs/{job_id}/score")
    assert scored.status_code == 200
    assert 0 <= scored.json()["overall_score"] <= 100
    shortlisted = client.post(f"/jobs/{job_id}/shortlist")
    assert shortlisted.json()["status"] == "shortlisted"
    assert client.get(f"/jobs/{job_id}").json()["application_status"] == "shortlisted"
    applied = client.post(f"/jobs/{job_id}/status/applied")
    assert applied.status_code == 200 and applied.json()["status"] == "applied"
    assert client.get(f"/jobs/{job_id}").json()["application_status"] == "applied"
