import hashlib
import io
import json
import re
import logging
from pathlib import Path

from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader

from app.core.config import Settings, get_settings
from app.models.onboarding import CandidateExtractionDraft, ResumeExtractionPayload, ResumeIngestionResult, ResumeMetadata
from app.models.profile import CandidateProfile, EvidenceRecord, Identity, ProfileItem
from app.services.llm_service import LLMError, LLMService, OutputTruncatedError, ProviderTimeoutError, StructuredOutputError, configured_llm_service


ALLOWED_TYPES = {
    "pdf": {"application/pdf", "application/octet-stream"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"},
    "txt": {"text/plain", "application/octet-stream"},
}

SYSTEM_PROMPT = """Extract a conservative candidate-profile draft and grounded evidence from the supplied resume text.
Use only facts explicitly present. Do not infer legal identity, contact details, protected traits, immigration,
citizenship, salary, sponsorship, or relocation. A professional/display name may be extracted when present.
Every evidence record must be unverified, use source_type RESUME, and include a verbatim supporting_text span
from the resume. Do not strengthen responsibilities into outcomes and preserve uncertainty in warnings."""
logger=logging.getLogger(__name__)


def private_storage_path(settings: Settings) -> Path:
    path = Path(settings.candidate_private_storage_path)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


class ResumeExtractionError(ValueError):
    pass


class ResumeTextExtractor:
    def extract(self, data: bytes, file_type: str) -> tuple[str, int | None, bool]:
        try:
            if file_type == "pdf":
                reader = PdfReader(io.BytesIO(data))
                if reader.is_encrypted:
                    try: reader.decrypt("")
                    except Exception as exc: raise ResumeExtractionError("Encrypted PDF cannot be read") from exc
                parts = [(page.extract_text() or "").strip() for page in reader.pages]
                text = "\n".join(part for part in parts if part)
                return text, len(reader.pages), any(not part for part in parts)
            if file_type == "docx":
                document = Document(io.BytesIO(data))
                parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
                for table in document.tables:
                    parts.extend(" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows)
                return "\n".join(parts), None, False
            for encoding in ("utf-8-sig", "utf-8", "cp1252"):
                try: return data.decode(encoding), None, encoding == "cp1252"
                except UnicodeDecodeError: continue
        except ResumeExtractionError:
            raise
        except Exception as exc:
            raise ResumeExtractionError(f"Unable to extract {file_type.upper()} resume text") from exc
        raise ResumeExtractionError("Unable to decode text resume")


class CandidateExtractionService:
    def __init__(self, llm: LLMService | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.llm = llm
        self.extractor = ResumeTextExtractor()

    @staticmethod
    def _type(upload: UploadFile) -> str:
        suffix = Path(upload.filename or "").suffix.lower().lstrip(".")
        if suffix not in ALLOWED_TYPES: raise ResumeExtractionError("Unsupported resume type. Upload PDF, DOCX, or TXT")
        content_type = (upload.content_type or "application/octet-stream").lower()
        if content_type not in ALLOWED_TYPES[suffix]: raise ResumeExtractionError("File extension and content type do not match")
        return suffix

    def ingest(self, upload: UploadFile, *, use_mock: bool = False) -> ResumeIngestionResult:
        file_type = self._type(upload)
        data = upload.file.read(self.settings.resume_max_upload_bytes + 1)
        return self._ingest_data(data,file_type,Path(upload.filename or f"resume.{file_type}").name,use_mock=use_mock)

    def retry_latest(self, *, use_mock: bool = False) -> ResumeIngestionResult:
        state_path=private_storage_path(self.settings)/"resume-upload.json"
        if not state_path.exists():raise ResumeExtractionError("No stored resume is available to retry")
        state=json.loads(state_path.read_text(encoding="utf-8"));document_id=state.get("document_id","");file_type=state.get("file_type","")
        if not re.fullmatch(r"[a-f0-9]{16}",document_id) or file_type not in ALLOWED_TYPES:raise ResumeExtractionError("Stored resume metadata is invalid")
        stored=private_storage_path(self.settings)/"resumes"/f"{document_id}.{file_type}"
        if not stored.exists():raise ResumeExtractionError("Stored resume is no longer available")
        return self._ingest_data(stored.read_bytes(),file_type,state.get("filename") or stored.name,use_mock=use_mock)

    def _ingest_data(self,data:bytes,file_type:str,original_filename:str,*,use_mock:bool=False)->ResumeIngestionResult:
        if len(data) > self.settings.resume_max_upload_bytes: raise ResumeExtractionError("Resume exceeds the configured upload limit")
        if not data: raise ResumeExtractionError("Resume file is empty")
        text, pages, partial = self.extractor.extract(data, file_type)
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        if len(text) < 20: raise ResumeExtractionError("Resume contains no usable text; OCR is not supported")
        digest = hashlib.sha256(data).hexdigest()
        document_id = digest[:16]
        storage = private_storage_path(self.settings) / "resumes"
        storage.mkdir(parents=True, exist_ok=True)
        stored = storage / f"{document_id}.{file_type}"
        if not stored.exists():stored.write_bytes(data)
        upload_state={"document_id":document_id,"filename":Path(original_filename).name,"file_type":file_type,"byte_size":len(data),"text_length":len(text),"page_count":pages}
        (private_storage_path(self.settings)/"resume-upload.json").write_text(json.dumps(upload_state,indent=2),encoding="utf-8")
        llm = self.llm or configured_llm_service(use_mock=use_mock, settings=self.settings,timeout=self.settings.resume_extraction_timeout_seconds)
        context = json.dumps({"source_document": stored.name, "resume_text": text}, ensure_ascii=False)
        try: extracted, response = llm.generate_structured(SYSTEM_PROMPT, context, ResumeExtractionPayload, max_tokens=self.settings.resume_extraction_max_tokens)
        except LLMError as exc:
            category="AI_REQUEST_TIMED_OUT" if isinstance(exc,ProviderTimeoutError) else "AI_RESPONSE_INCOMPLETE" if isinstance(exc,OutputTruncatedError) else "RESUME_STRUCTURE_INVALID" if isinstance(exc,StructuredOutputError) else "AI_PROVIDER_UNAVAILABLE"
            logger.warning("candidate_extraction_failed stage=structured_extraction category=%s exception=%s provider=%s model=%s text_length=%s",category,type(exc).__name__,getattr(llm.provider,"name","unknown"),getattr(llm.provider,"model","unknown"),len(text))
            failure={**upload_state,"status":"FAILED","category":category,"exception_class":type(exc).__name__,"provider":getattr(llm.provider,"name",None),"model":getattr(llm.provider,"model",None)}
            (private_storage_path(self.settings)/"resume-extraction-status.json").write_text(json.dumps(failure,indent=2),encoding="utf-8")
            exc.safe_category=category
            raise
        normalized_text = re.sub(r"\s+", " ", text).strip().casefold()
        retained: list[EvidenceRecord] = []
        warnings = list(extracted.warnings)
        profile = CandidateProfile(identity=Identity(preferred_professional_name=extracted.professional_name, display_name=extracted.professional_name))

        def retain(value: str, category: str, sub_category: str, section: str, supporting_text: str, confidence: float, *, details: dict | None = None) -> ProfileItem | None:
            span = re.sub(r"\s+", " ", supporting_text).strip()
            if not span or span.casefold() not in normalized_text:
                warnings.append(f"A {category} item was removed because its supporting span was not found verbatim")
                return None
            evidence_id = f"RESUME_{document_id}_{len(retained)+1:03d}"
            retained.append(EvidenceRecord(id=evidence_id,category=category,sub_category=sub_category,statement=value,source="resume",source_reference=f"{stored.name}: {section or 'unspecified section'}",verified=False,confidence=confidence,source_type="RESUME",source_document=stored.name,source_section=section,supporting_text=supporting_text))
            return ProfileItem(value=value, details=details or {}, evidence_ids=[evidence_id])

        if extracted.professional_summary:
            item=extracted.professional_summary;profile.professional_summary=retain(item.value,"summary","professional_summary",item.source_section,item.supporting_text,item.confidence)
        for employment in extracted.employment:
            value=f"{employment.title} at {employment.employer}";details={"employer":employment.employer,"title":employment.title,"start_date":employment.start_date,"end_date":employment.end_date}
            item=retain(value,"experience","employment",employment.source_section,employment.supporting_text,employment.confidence,details=details)
            if item: profile.experience.append(item);profile.roles.append(ProfileItem(value=employment.title,details={"company":employment.employer},evidence_ids=item.evidence_ids))
            for statement in employment.responsibilities:
                item=retain(statement,"experience","responsibility",employment.source_section,statement,employment.confidence,details={"employer":employment.employer,"title":employment.title})
                if item: profile.experience.append(item)
            for statement in employment.accomplishments:
                item=retain(statement,"experience","accomplishment",employment.source_section,statement,employment.confidence,details={"employer":employment.employer,"title":employment.title})
                if item: profile.experience.append(item)
        for collection,category,sub_category,target in ((extracted.skills,"skills","skill",profile.skills),(extracted.education,"education","education",profile.education),(extracted.projects,"projects","project",profile.projects),(extracted.certifications,"certifications","certification",profile.projects),(extracted.domains,"skills","domain",profile.technical_domains),(extracted.technologies,"skills","technology",profile.skills)):
            for value in collection:
                item=retain(value.value,category,sub_category,value.source_section,value.supporting_text,value.confidence)
                if item: target.append(item)
        draft=CandidateExtractionDraft(profile=profile,evidence=retained,warnings=warnings)
        metadata = ResumeMetadata(document_id=document_id, filename=Path(original_filename).name, file_type=file_type, text_length=len(text), page_count=pages, extraction_status="PARTIAL" if partial or warnings else "EXTRACTED")
        result = ResumeIngestionResult(metadata=metadata, draft=draft, provider=response.provider, model=response.model, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens, estimated_cost=response.usage.estimated_cost)
        (private_storage_path(self.settings) / "onboarding-draft.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        (private_storage_path(self.settings)/"resume-extraction-status.json").write_text(json.dumps({**upload_state,"status":"COMPLETED","provider":response.provider,"model":response.model,"input_tokens":response.usage.input_tokens,"output_tokens":response.usage.output_tokens,"estimated_cost":response.usage.estimated_cost},indent=2),encoding="utf-8")
        return result
