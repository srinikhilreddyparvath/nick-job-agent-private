from app.db.database import SessionLocal
from app.db.models import ApplicationFormRecord


def test_api_is_open_without_authentication(client):
    assert client.get("/jobs").status_code==200
    assert client.get("/operations/status").status_code==200
    assert client.get("/application-settings").status_code==200
    assert client.get("/application-summary").status_code==200
    assert client.get("/reports/morning/latest").status_code in {200,404}
    assert client.get("/auth/login").status_code==404
    assert client.post("/auth/login",json={"password":"unused"}).status_code==404


def test_mutations_need_no_cookie_authorization_or_csrf(client):
    response=client.post("/operations/pause",json={"value":True})
    assert response.status_code==200
    assert client.post("/operations/pause",json={"value":False}).status_code==200
    preflight=client.options("/jobs/1/inspect-form",headers={"Origin":"http://localhost:3000","Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"content-type"})
    assert preflight.status_code in {200,204}
    assert preflight.headers["access-control-allow-origin"]=="http://localhost:3000"
    assert preflight.headers.get("access-control-allow-credentials") is None
    rejected=client.options("/jobs/1/inspect-form",headers={"Origin":"https://unapproved.invalid","Access-Control-Request-Method":"POST"})
    assert "access-control-allow-origin" not in rejected.headers


def test_job_application_reads_need_no_auth_headers(client):
    created=client.post("/jobs/ingest-text",json={"source_url":"https://fixture.invalid/no-auth","company":"No Auth Fixture","title":"Research Engineer","location":"San Francisco, CA","job_description_text":"Research and evaluate machine learning systems using Python."})
    assert created.status_code==200
    job_id=created.json()["job"]["id"]
    assert client.get(f"/jobs/{job_id}").status_code==200
    assert client.get(f"/jobs/{job_id}/application-eligibility").status_code==200
    assert client.get(f"/jobs/{job_id}/application-package").status_code==404
    with SessionLocal() as db:
        schema={"application_url":"https://fixture.invalid/apply","ats":"generic","company":"No Auth Fixture","job_id":job_id,"fields":[],"required_fields":[],"captcha_detected":False,"authentication_required":False,"status":"INSPECTED"}
        db.add(ApplicationFormRecord(job_id=job_id,application_url=schema["application_url"],ats="generic",schema_json=schema,form_fingerprint="no-auth",status="INSPECTED"));db.commit()
    assert client.get(f"/jobs/{job_id}/application-form").status_code==200
