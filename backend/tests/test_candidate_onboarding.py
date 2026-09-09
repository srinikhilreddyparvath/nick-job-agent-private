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
from app.services.llm_service import LLMService, MockLLMProvider, OutputTruncatedError, ProviderTimeoutError, StructuredOutputError
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
    extracted=ResumeTextExtractor().extract(stream.getvalue(),"docx")
    assert "Northstar Labs" in extracted.text and extracted.page_count is None


def test_pdf_parser_textless_is_rejected(tmp_path):
    writer=PdfWriter();writer.add_blank_page(width=100,height=100);stream=io.BytesIO();writer.write(stream)
    with pytest.raises(ResumeExtractionError,match="selectable text"):service(tmp_path).ingest(upload("resume.pdf",stream.getvalue(),"application/pdf"))
    assert list((tmp_path/"private"/"resumes").glob("*.pdf"))


def test_pdf_parser_extracts_text():
    stream=io.BytesIO();pdf=canvas.Canvas(stream);pdf.drawString(72,720,TEXT);pdf.save()
    extracted=ResumeTextExtractor().extract(stream.getvalue(),"pdf")
    assert "Northstar Labs" in extracted.text and extracted.page_count==1


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
    state=persistence.approve(OnboardingApprovalRequest(preferences_reviewed=True,confirm_replacement=True,profile=profile,evidence=[evidence],preferences=preferences))
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


@pytest.mark.parametrize(("error","category"),[(ProviderTimeoutError("timeout"),"AI_REQUEST_TIMED_OUT"),(OutputTruncatedError("truncated"),"AI_RESPONSE_INCOMPLETE"),(StructuredOutputError("invalid"),"RESUME_STRUCTURE_INVALID")])
def test_resume_failure_is_safe_and_stored_file_survives(tmp_path,error,category):
    class FailingProvider(MockLLMProvider):
        def generate(self,*args,**kwargs):raise error
    configured=settings(tmp_path);configured.llm_max_retries=0
    extraction=CandidateExtractionService(LLMService(FailingProvider(),configured),configured)
    with pytest.raises(type(error)) as caught:extraction.ingest(upload("resume.txt",TEXT.encode(),"text/plain"))
    assert caught.value.safe_category==category
    assert len(list((tmp_path/"private"/"resumes").glob("*.txt")))==1
    status=(tmp_path/"private"/"resume-extraction-status.json").read_text()
    assert category in status and TEXT not in status


def test_retry_uses_stored_resume_without_duplicate_upload(tmp_path):
    configured=settings(tmp_path);configured.llm_max_retries=0
    class OnceProvider(MockLLMProvider):
        def __init__(self):super().__init__(responses={"ResumeExtractionPayload":draft_payload()});self.failed=False
        def generate(self,*args,**kwargs):
            if not self.failed:self.failed=True;raise ProviderTimeoutError("timeout")
            return super().generate(*args,**kwargs)
    extraction=CandidateExtractionService(LLMService(OnceProvider(),configured),configured)
    with pytest.raises(ProviderTimeoutError):extraction.ingest(upload("resume.txt",TEXT.encode(),"text/plain"))
    before=list((tmp_path/"private"/"resumes").iterdir());result=extraction.retry_latest();after=list((tmp_path/"private"/"resumes").iterdir())
    assert result.draft.profile.identity.display_name=="Alex Morgan" and before==after

def test_granular_grounding_keeps_role_and_drops_only_hallucinated_bullet(tmp_path):
    text="Alex Morgan\nEXPERIENCE\nNorthstar Labs\nMachine Learning Engineer\nAugust 2025 - Present\nBuilt retrieval evaluation workflows using Python."
    payload=draft_payload();payload["professional_summary"]=None;payload["employment"]=[{"employer":"Northstar Labs","title":"Machine Learning Engineer","start_date":"August 2025","end_date":"Present","location":None,"responsibilities":["Built retrieval evaluation workflows using Python.","Managed a $5 million program"],"accomplishments":[],"source_section":"Experience","supporting_text":"Northstar Labs Machine Learning Engineer","confidence":.92}]
    result=service(tmp_path,payload).ingest(upload("resume.txt",text.encode(),"text/plain"))
    values=[x.value for x in result.draft.profile.experience]
    assert "Machine Learning Engineer at Northstar Labs" in values
    assert "Built retrieval evaluation workflows using Python." in values
    assert "Managed a $5 million program" not in values
    assert len(result.draft.warnings)<=5

@pytest.mark.parametrize(("source","normalized"),[("August 2025 – Present","August 2025 - Present"),("Built reliable\nretrieval systems","Built reliable retrieval systems"),("• Python","Python")])
def test_grounding_tolerates_layout_and_unicode_variation(source,normalized):
    from app.services.candidate_extraction_service import grounding_match
    assert grounding_match(normalized,source)[0] in {"VERIFIED_FROM_RESUME","LIKELY_FROM_RESUME"}
