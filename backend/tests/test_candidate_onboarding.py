import io
from pathlib import Path

import pytest
from docx import Document
from fastapi import UploadFile
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from app.core.config import Settings
from app.models.onboarding import CandidateExtractionDraft, OnboardingApprovalRequest, ResumeExtractionPayload
from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences, ProfileItem
from app.services.candidate_extraction_service import CandidateExtractionService, ResumeExtractionError, ResumeTextExtractor
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.llm_service import LLMService, MockLLMProvider
from app.services.llm_service import _strict_json_schema
from app.services.opportunity_service import ConstraintEngine
from app.models.job import Job


TEXT = "Alex Morgan\nMachine Learning Engineer at Northstar Labs\nBuilt retrieval evaluation workflows using Python."


def settings(tmp_path: Path) -> Settings:
    return Settings(candidate_profile_path=str(tmp_path/"profile.local.json"),candidate_evidence_path=str(tmp_path/"evidence.local.json"),candidate_preferences_path=str(tmp_path/"preferences.local.json"),candidate_private_storage_path=str(tmp_path/"private"),llm_enabled=False)


def upload(name: str, data: bytes, content_type: str) -> UploadFile:
    return UploadFile(filename=name,file=io.BytesIO(data),headers={"content-type":content_type})


def draft_payload(span=TEXT.splitlines()[-1]):
    return {"professional_name":"Alex Morgan","professional_summary":{"value":span,"source_section":"Experience","supporting_text":span,"confidence":.9},"employment":[],"skills":[],"education":[],"projects":[],"certifications":[],"domains":[],"technologies":[],"warnings":[]}


def service(tmp_path: Path, payload=None):
    configured=settings(tmp_path);llm=LLMService(MockLLMProvider(responses={"ResumeExtractionPayload":payload or draft_payload()}),configured)
    return CandidateExtractionService(llm,configured)


def test_txt_upload_extracts_and_stores_private_draft(tmp_path):
    result=service(tmp_path).ingest(upload("resume.txt",TEXT.encode(),"text/plain"))
    assert result.metadata.file_type=="txt" and result.metadata.text_length>20
    assert len(result.draft.evidence)==1 and not result.draft.evidence[0].verified
    assert list((tmp_path/"private"/"resumes").glob("*.txt"))


def test_docx_parser(tmp_path):
    document=Document();document.add_paragraph(TEXT);stream=io.BytesIO();document.save(stream)
    text,pages,_=ResumeTextExtractor().extract(stream.getvalue(),"docx")
    assert "Northstar Labs" in text and pages is None


def test_pdf_parser_textless_is_rejected(tmp_path):
    writer=PdfWriter();writer.add_blank_page(width=100,height=100);stream=io.BytesIO();writer.write(stream)
    with pytest.raises(ResumeExtractionError,match="no usable text"):service(tmp_path).ingest(upload("resume.pdf",stream.getvalue(),"application/pdf"))


def test_pdf_parser_extracts_text():
    stream=io.BytesIO();pdf=canvas.Canvas(stream);pdf.drawString(72,720,TEXT);pdf.save()
    text,pages,_=ResumeTextExtractor().extract(stream.getvalue(),"pdf")
    assert "Northstar Labs" in text and pages==1


def test_upload_validation_and_empty_files(tmp_path):
    with pytest.raises(ResumeExtractionError,match="Unsupported"):service(tmp_path).ingest(upload("resume.exe",b"abc","application/octet-stream"))
    with pytest.raises(ResumeExtractionError,match="empty"):service(tmp_path).ingest(upload("resume.txt",b"","text/plain"))
    with pytest.raises(ResumeExtractionError,match="do not match"):service(tmp_path).ingest(upload("resume.txt",TEXT.encode(),"application/pdf"))


def test_ungrounded_evidence_is_removed(tmp_path):
    result=service(tmp_path,draft_payload("Claim not present in source")).ingest(upload("resume.txt",TEXT.encode(),"text/plain"))
    assert result.draft.evidence==[] and result.draft.warnings


def test_employment_claims_are_separate_reviewable_grounded_items(tmp_path):
    payload=draft_payload();payload["professional_summary"]=None;payload["employment"]=[{"employer":"Northstar Labs","title":"Machine Learning Engineer","start_date":None,"end_date":None,"responsibilities":["Built retrieval evaluation workflows using Python."],"accomplishments":[],"source_section":"Experience","supporting_text":"Machine Learning Engineer at Northstar Labs","confidence":.9}]
    result=service(tmp_path,payload).ingest(upload("resume.txt",TEXT.encode(),"text/plain"))
    assert [item.value for item in result.draft.profile.experience]==["Machine Learning Engineer at Northstar Labs","Built retrieval evaluation workflows using Python."]
    assert {item.sub_category for item in result.draft.evidence}=={"employment","responsibility"}


def test_approval_persists_profile_evidence_preferences_and_constraints(tmp_path):
    configured=settings(tmp_path);persistence=CandidatePersistenceService(configured)
    evidence=EvidenceRecord(id="E1",category="skills",sub_category="programming",statement="Python",source="resume",source_reference="Skills",verified=False,confidence=.9,supporting_text="Python")
    profile=CandidateProfile(skills=[ProfileItem(value="Python",evidence_ids=["E1"])]);preferences=JobPreferences(locations=["Metro City"],employment_types=["full-time"],remote_allowed=True)
    state=persistence.approve(OnboardingApprovalRequest(profile=profile,evidence=[evidence],preferences=preferences))
    assert state.configured and state.evidence[0].verified
    assert CandidatePersistenceService(configured).state().preferences.locations==["Metro City"]
    job=Job(external_id="1",source="test",company="Example",title="Engineer",location="Metro City",employment_type=None,description="Python",apply_url="https://example.com/apply",source_url="https://example.com/job")
    assert ConstraintEngine().evaluate(job,CandidatePersistenceService(configured).state().preferences).location=="MATCH"


def test_onboarding_api_uses_mock_extraction(client):
    response=client.post("/onboarding/resume",files={"file":("resume.txt",TEXT,"text/plain")},data={"use_mock":"true"})
    assert response.status_code==200 and response.json()["metadata"]["file_type"]=="txt"
    assert client.get("/onboarding/preferences").status_code==200


def test_candidate_extraction_schema_uses_provider_supported_subset():
    schema = _strict_json_schema(ResumeExtractionPayload)

    def walk(value):
        if isinstance(value, dict):
            assert value.get("format") != "uri"
            assert "default" not in value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)
