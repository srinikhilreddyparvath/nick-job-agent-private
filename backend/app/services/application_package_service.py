import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings,get_settings
from app.db.models import ApplicationPackageRecord,ApprovedAnswerHistoryRecord,CompanyResearchRecord,SemanticAnalysisRecord
from app.models.application_package import *
from app.models.policy import ClaimValidationRequest
from app.prompts.application_agent_v1 import SYSTEM as APPLICATION_SYSTEM,VERSION as APPLICATION_VERSION
from app.prompts.reviewer_agent_v1 import SYSTEM as REVIEW_SYSTEM,VERSION as REVIEW_VERSION
from app.services.agent_service import AgentRunService
from app.services.claim_validator import EvidenceClaimValidator
from app.services.evidence_service import EvidenceService
from app.services.identity_service import IdentityService
from app.services.job_service import JobService
from app.services.llm_service import LLMError,LLMService
from app.services.policy_service import AnswerBankService,WorkAuthorizationService
from app.services.profile_service import load_profile
from app.services.resume_renderer import ResumeRenderer
from app.services.semantic_evidence_service import SemanticEvidenceIndex


class ApplicationPackageService:
    def __init__(self,llm:LLMService,review_llm:LLMService|None=None,settings:Settings|None=None,renderer:ResumeRenderer|None=None):
        self.llm=llm;self.review_llm=review_llm or llm;self.settings=settings or get_settings();self.renderer=renderer or ResumeRenderer();self.evidence=EvidenceService();self.validator=EvidenceClaimValidator(self.evidence);self.runs=AgentRunService();self.jobs=JobService()
    def _fingerprints(self,job,evidence_version:str,provider:str|None=None,model:str|None=None):
        job_fp=hashlib.sha256(json.dumps({"description":job.description,"requirements":job.requirements,"preferred":job.preferred_qualifications},sort_keys=True).encode()).hexdigest()
        root=Path(__file__).resolve().parents[3]
        configured={
            "profile":Path(self.settings.candidate_profile_path),
            "answer_bank":Path(self.settings.candidate_answer_bank_path),
            "master_resume":root/"documents/master_resume.pdf",
        }
        inputs={}
        for name,path in configured.items():
            resolved=path if path.is_absolute() else (root/"backend"/path).resolve()
            inputs[name]=hashlib.sha256(resolved.read_bytes()).hexdigest() if resolved.exists() else "missing"
        package_fp=hashlib.sha256(json.dumps({"job":job_fp,"evidence":evidence_version,"inputs":inputs,"application_prompt":APPLICATION_VERSION,"review_prompt":REVIEW_VERSION,"provider":provider or self.llm.provider.name,"model":model or self.llm.provider.model},sort_keys=True).encode()).hexdigest();return job_fp,package_fp
    def _requirements(self,job,research)->list[JobRequirement]:
        required=job.requirements or (research.key_requirements if research else [])
        preferred=job.preferred_qualifications or (research.preferred_requirements if research else [])
        def category(text):
            x=text.lower()
            for name,terms in {"education":["degree","phd"],"programming":["python","programming","code"],"ML_AI":["machine learning"," ml ","embedding"],"research":["research"],"technical_skill":["crawler","parser","database","retrieval"],"cross_functional":["customer","cross-functional"],"location":["in person","location"]}.items():
                if any(t in f" {x} " for t in terms):return name
            return "other"
        rows=[]
        for i,(text,kind) in enumerate([(x,"required") for x in required]+[(x,"preferred") for x in preferred],1):rows.append(JobRequirement(requirement_id=f"REQ_{i:03}",category=category(text),text=text,importance=4 if kind=="required" else 2,required_vs_preferred=kind))
        return rows
    def _policy_answer(self,q:ApplicationQuestionInput,index:int)->ApplicationAnswer|None:
        lower=q.question_text.lower();limit=q.character_limit or {"SHORT":300,"MEDIUM":750,"LONG":1500}[q.answer_length.value]
        auth=WorkAuthorizationService().assess(q.question_text)
        if auth.matched_answer_id:return ApplicationAnswer(id=f"ANSWER_{index:03}",question_text=q.question_text,required=q.required,detected_category="work_authorization",answer=auth.answer,original_model_answer=auth.answer,answer_status="APPROVED",answer_type="APPROVED_STRUCTURED",confidence=1,character_limit=limit,requires_human_review=False,reusable=True)
        if any(x in lower for x in ("middle name","years of experience","current salary","salary history","relocat","criminal","non-compete","security clearance","demographic","disability","veteran","conflict of interest")):
            return ApplicationAnswer(id=f"ANSWER_{index:03}",question_text=q.question_text,required=q.required,detected_category="sensitive_or_missing",answer=None,answer_status="HUMAN_REVIEW_REQUIRED",answer_type="HUMAN_REVIEW_REQUIRED",confidence=1,character_limit=limit,requires_human_review=True)
        return None
    def _validate_text(self,text:str,evidence_ids:list[str]):
        return self.validator.validate(ClaimValidationRequest(generated_claim=text,supporting_evidence_ids=evidence_ids))
    def _record_to_schema(self,row:ApplicationPackageRecord)->ApplicationPackageRead:
        return ApplicationPackageRead(id=row.id,job_id=row.job_id,status=row.status,resume_version_id=row.resume_version_id,resume_strategy=row.resume_strategy_json,tailored_resume_path=row.tailored_resume_path,tailored_resume_preview=row.tailored_resume_preview_json,job_requirements=row.job_requirements_json,cover_letter=row.cover_letter,cover_letter_evidence_ids=row.cover_letter_evidence_ids,cover_letter_required=row.cover_letter_required,cover_letter_status=row.cover_letter_status,application_answers=row.application_answers_json,application_summary=row.application_summary_json,fit_analysis_id=row.fit_analysis_id,research_report_id=row.research_report_id,evidence_ids_used=row.evidence_ids_used,unsupported_claims_removed=row.unsupported_claims_removed,review_findings=row.review_findings_json,review_status=row.review_status,requires_human_review=row.requires_human_review,human_review_reasons=row.human_review_reasons,provider=row.provider,model=row.model,prompt_versions=row.prompt_versions,input_tokens=row.input_tokens,output_tokens=row.output_tokens,cached_tokens=row.cached_tokens,estimated_cost=row.estimated_cost,latency_ms=row.latency_ms,evidence_version=row.evidence_version,job_fingerprint=row.job_fingerprint,package_fingerprint=row.package_fingerprint,created_at=row.created_at,updated_at=row.updated_at,approved_at=row.approved_at)
    def get(self,db:Session,job_id:int)->ApplicationPackageRead|None:
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
        if not row:return None
        job_record=self.jobs.get(db,job_id)
        if job_record:
            job=self.jobs.to_schema(job_record);job_fp,package_fp=self._fingerprints(job,SemanticEvidenceIndex(self.evidence).version,row.provider,row.model)
            if row.job_fingerprint!=job_fp or row.package_fingerprint!=package_fp:
                row.status="STALE";row.approved_at=None;row.human_review_reasons=list(dict.fromkeys((row.human_review_reasons or [])+["Relevant job, evidence, policy, resume, prompt, or model inputs changed"]));db.commit();db.refresh(row)
        return self._record_to_schema(row)
    def generate(self,db:Session,job_id:int,request:PackageGenerateRequest)->PackageResponse:
        record=self.jobs.get(db,job_id)
        if not record:return PackageResponse(status="not_found",error="Job not found")
        job=self.jobs.to_schema(record);analysis_row=db.scalar(select(SemanticAnalysisRecord).where(SemanticAnalysisRecord.job_id==job_id).order_by(SemanticAnalysisRecord.created_at.desc()));research_row=db.scalar(select(CompanyResearchRecord).where(CompanyResearchRecord.job_id==job_id).order_by(CompanyResearchRecord.generated_at.desc()))
        if not analysis_row:return PackageResponse(status="REVIEW_REQUIRED",error="Semantic fit analysis is required before application generation")
        analysis=analysis_row.report_json;research=research_row.report_json if research_row else None;index=SemanticEvidenceIndex(self.evidence);version=index.version;job_fp,package_fp=self._fingerprints(job,version)
        cached=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
        if cached and cached.package_fingerprint==package_fp and not request.force:return PackageResponse(status="cached",package=self._record_to_schema(cached))
        run=self.runs.start(db,"application","Create a truthful evidence-grounded draft application package",job_id,{"questions":len(request.questions)},provider=self.llm.provider.name,model=self.llm.provider.model,prompt_version=APPLICATION_VERSION,temperature=0)
        try:
            ids=list(dict.fromkeys(analysis.get("evidence_ids",[])+["SUMMARY_001","SKILLS_004","SKILLS_005","EDUCATION_001","EDUCATION_002"]))
            records=[self.evidence.get_by_id(x) for x in ids];records=[x for x in records if x]
            requirements=self._requirements(job,type("Research",(),research) if research else None)
            compact_evidence=[{"id":x.id,"statement":x.statement,"company":x.company,"role":x.role,"skills":x.skills} for x in records]
            context={"job_id":job_id,"company":job.company,"title":job.title,"role_family":job.role_family,"job_description":job.description,"requirements":[x.model_dump(mode="json") for x in requirements],"fit_analysis":{"strengths":analysis.get("strengths",[]),"gaps":analysis.get("gaps",[]),"requirement_matches":analysis.get("requirement_matches",[])},"research":{"company_summary":research.get("company_summary"),"role_summary":research.get("role_summary"),"key_requirements":research.get("key_requirements",[]),"potential_risks":research.get("potential_risks",[])} if research else None,"evidence":compact_evidence,"identity":IdentityService().get().model_dump(mode="json"),"questions":[x.model_dump(mode="json") for x in request.questions],"approved_answers":{k:[{"id":x.id,"question":x.question,"answer":x.answer} for x in v] for k,v in AnswerBankService().all().items()},"cover_letter_requested":request.cover_letter_requested}
            draft,response=self.llm.generate_structured(APPLICATION_SYSTEM,json.dumps(context,default=str),ApplicationGenerationDraft,max_tokens=self.settings.application_llm_max_tokens)
            removed=[];valid_bullets=[]
            for bullet in draft.resume_bullets:
                bullet.original_model_text=bullet.original_model_text or bullet.generated_text
                result=self._validate_text(bullet.generated_text,bullet.source_evidence_ids);bullet.validation_status=result.support_status;bullet.validation_confidence=result.confidence
                if result.support_status=="unsupported":removed.append(bullet.generated_text)
                else:valid_bullets.append(bullet)
            valid_summary=[]
            for item in draft.summary:
                result=self._validate_text(item.text,item.evidence_ids)
                if result.support_status=="unsupported":removed.append(item.text)
                else:valid_summary.append(item)
            valid_skills=[x for x in draft.skills if x.evidence_ids and all(self.evidence.get_by_id(i) for i in x.evidence_ids)]
            generated_by_question={x.question_text.lower():x for x in draft.application_answers};answers=[]
            for i,q in enumerate(request.questions,1):
                policy=self._policy_answer(q,i)
                if policy:answers.append(policy);continue
                answer=generated_by_question.get(q.question_text.lower())
                if not answer:answers.append(ApplicationAnswer(id=f"ANSWER_{i:03}",question_text=q.question_text,required=q.required,answer_type="HUMAN_REVIEW_REQUIRED",answer_status="INSUFFICIENT_EVIDENCE",character_limit=q.character_limit,requires_human_review=True));continue
                answer.id=f"ANSWER_{i:03}";answer.character_limit=q.character_limit or {"SHORT":300,"MEDIUM":750,"LONG":1500}[q.answer_length.value]
                validation=self._validate_text(answer.answer or "",answer.evidence_ids)
                if validation.support_status=="unsupported":removed.append(answer.answer or "");answer.answer=None;answer.answer_status="INSUFFICIENT_EVIDENCE";answer.requires_human_review=True
                elif answer.answer and len(answer.answer)>answer.character_limit:
                    answer.original_model_answer=answer.answer;answer.answer=None;answer.answer_status="CHARACTER_LIMIT_REVIEW";answer.requires_human_review=True
                answers.append(answer)
            profile=load_profile();identity=profile.identity
            education=[GroundedText(text=f"{x.value} - {x.details.get('institution','')}",evidence_ids=x.evidence_ids) for x in profile.education]
            resume=TailoredResumeData(professional_name=identity.display_name or identity.preferred_professional_name or "Candidate",email=identity.email or "",phone=identity.phone or "",location=identity.location,portfolio_url=str(identity.portfolio_url) if identity.portfolio_url else None,linkedin_url=str(identity.linkedin_url) if identity.linkedin_url else None,target_company=job.company,target_role=job.title,summary=valid_summary,bullets=valid_bullets,skills=valid_skills,education=education,page_length=request.resume_pages)
            if not resume.summary:resume.summary=[GroundedText(text=profile.professional_summary.value,evidence_ids=profile.professional_summary.evidence_ids)]
            if not resume.bullets:
                for n,e in enumerate(records[:8],1):resume.bullets.append(ResumeBullet(id=f"BULLET_{n:03}",section="experience",employer_or_context=f"{e.company or 'Professional Experience'} | {e.role or ''}",generated_text=e.statement,source_evidence_ids=[e.id],source_resume_text=e.statement,transformation_type="UNCHANGED",validation_status="supported",validation_confidence=1))
            path=self.renderer.render(job_id,resume);evidence_ids=sorted({i for b in resume.bullets for i in b.source_evidence_ids}|{i for x in resume.summary+resume.skills for i in x.evidence_ids}|{i for x in answers for i in x.evidence_ids})
            now=datetime.now(timezone.utc);row=cached or ApplicationPackageRecord(job_id=job_id,created_at=now)
            row.status="REVIEW_REQUIRED";row.resume_version_id=f"resume-{job_id}-{now.strftime('%Y%m%d%H%M%S')}";row.resume_strategy_json=draft.strategy.model_dump(mode="json");row.tailored_resume_path=str(path);row.tailored_resume_preview_json=resume.model_dump(mode="json");row.job_requirements_json=[x.model_dump(mode="json") for x in requirements];row.cover_letter=draft.cover_letter if draft.strategy.cover_letter_recommended or request.cover_letter_requested else None;row.original_cover_letter=row.cover_letter;row.cover_letter_evidence_ids=draft.cover_letter_evidence_ids if row.cover_letter else [];row.cover_letter_required=request.cover_letter_requested;row.cover_letter_status="DRAFT" if row.cover_letter else "NOT_RECOMMENDED";row.application_answers_json=[x.model_dump(mode="json") for x in answers];row.application_summary_json=[x.model_dump(mode="json") for x in draft.recruiter_summary];row.fit_analysis_id=analysis_row.id;row.research_report_id=research_row.id if research_row else None;row.evidence_ids_used=evidence_ids;row.unsupported_claims_removed=removed;row.review_findings_json=[];row.review_status=None;row.requires_human_review=True;row.human_review_reasons=["Human approval is required before any future application use"];row.provider=response.provider;row.model=response.model;row.prompt_versions={"application":APPLICATION_VERSION,"review":REVIEW_VERSION};row.input_tokens=response.usage.input_tokens;row.output_tokens=response.usage.output_tokens;row.cached_tokens=response.usage.cached_tokens;row.estimated_cost=response.usage.estimated_cost;row.latency_ms=response.latency_ms;row.evidence_version=version;row.job_fingerprint=job_fp;row.package_fingerprint=package_fp;row.updated_at=now;row.approved_at=None
            db.add(row);db.commit();db.refresh(row);self.runs.complete(db,run,{"package_id":row.id,"status":row.status},[{"step":1,"tool":"get_fit_analysis","status":"completed"},{"step":2,"tool":"search_candidate_evidence","status":"completed","result_count":len(records)},{"step":3,"tool":"create_resume_strategy","status":"completed"},{"step":4,"tool":"create_application_answer_draft","status":"completed"},{"step":5,"tool":"validate_claims","status":"completed","removed":len(removed)}],evidence_ids_used=evidence_ids,input_tokens=response.usage.input_tokens,output_tokens=response.usage.output_tokens,cached_tokens=response.usage.cached_tokens,estimated_cost=response.usage.estimated_cost,latency_ms=response.latency_ms,requires_human_review=True)
            return PackageResponse(status="REVIEW_REQUIRED",package=self._record_to_schema(row),application_agent_run_id=run.id)
        except Exception as exc:
            self.runs.fail(db,run,str(exc));return PackageResponse(status="GENERATION_FAILED",error=str(exc),application_agent_run_id=run.id)
    def review(self,db:Session,job_id:int)->PackageResponse:
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
        if not row:return PackageResponse(status="not_found",error="Application package not found")
        run=self.runs.start(db,"reviewer","Verify application package grounding and safety",job_id,{"package_id":row.id},provider=self.review_llm.provider.name,model=self.review_llm.provider.model,prompt_version=REVIEW_VERSION,temperature=0)
        deterministic=[]
        resume=TailoredResumeData.model_validate(row.tailored_resume_preview_json)
        identity=IdentityService().get()
        for field,actual,expected in (("professional_name",resume.professional_name,identity.display_name),("email",resume.email,identity.email),("phone",resume.phone,identity.phone)):
            if actual!=expected:deterministic.append(ReviewFinding(severity="ERROR",affected_artifact="resume_identity",claim=f"{field} does not match canonical identity",evidence_ids=identity.evidence_ids,recommended_action="Restore canonical identity value"))
        for bullet in resume.bullets:
            result=self._validate_text(bullet.edited_text or bullet.generated_text,bullet.source_evidence_ids)
            if result.support_status=="unsupported":deterministic.append(ReviewFinding(severity="ERROR",affected_artifact="resume",claim=bullet.edited_text or bullet.generated_text,evidence_ids=bullet.source_evidence_ids,recommended_action="Remove or rewrite from evidence"))
        for answer in [ApplicationAnswer.model_validate(x) for x in row.application_answers_json]:
            if answer.detected_category=="work_authorization":
                approved=WorkAuthorizationService().assess(answer.question_text)
                if approved.requires_human_review or answer.answer!=approved.answer:deterministic.append(ReviewFinding(severity="ERROR",affected_artifact="work_authorization",claim=answer.answer or "Missing answer",evidence_ids=[],recommended_action="Use exact approved policy or require human review"))
            if answer.answer_type=="EVIDENCE_GENERATED" and answer.answer:
                result=self._validate_text(answer.edited_answer or answer.answer,answer.evidence_ids)
                if result.support_status=="unsupported":deterministic.append(ReviewFinding(severity="ERROR",affected_artifact="application_answer",claim=answer.edited_answer or answer.answer,evidence_ids=answer.evidence_ids,recommended_action="Remove or rewrite from evidence"))
        if row.cover_letter:
            result=self._validate_text(row.cover_letter,row.cover_letter_evidence_ids)
            if result.support_status=="unsupported":deterministic.append(ReviewFinding(severity="ERROR",affected_artifact="cover_letter",claim=row.cover_letter,evidence_ids=row.cover_letter_evidence_ids,recommended_action="Remove unsupported candidate claims or add verified provenance"))
        context={"package":self._record_to_schema(row).model_dump(mode="json"),"canonical_identity":IdentityService().get().model_dump(mode="json"),"work_authorization":[x.model_dump(mode="json") for x in AnswerBankService().all()["approved_structured"] if x.id.startswith(("WORK_","SPONSORSHIP_","H1B_"))],"evidence":[x.model_dump(mode="json") for x in self.evidence.all()],"deterministic_findings":[x.model_dump(mode="json") for x in deterministic]}
        try:
            review,response=self.review_llm.generate_structured(REVIEW_SYSTEM,json.dumps(context,default=str),ApplicationReview);findings=deterministic+review.findings
            if deterministic:status="REVIEW_REQUIRED"
            elif review.status in {"PASS","PASS_WITH_WARNINGS"}:status="READY_FOR_REVIEW"
            else:status="REVIEW_REQUIRED"
            row.status=status;row.review_status="FAIL" if deterministic else review.status.value;row.review_findings_json=[x.model_dump(mode="json") for x in findings];row.requires_human_review=True;row.human_review_reasons=["Human approval is required"]+(["Reviewer found blocking issues"] if status!="READY_FOR_REVIEW" else []);row.input_tokens+=response.usage.input_tokens;row.output_tokens+=response.usage.output_tokens;row.cached_tokens+=response.usage.cached_tokens;row.estimated_cost=round(row.estimated_cost+response.usage.estimated_cost,8);row.latency_ms+=response.latency_ms;row.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(row);self.runs.complete(db,run,review.model_dump(mode="json"),[{"step":1,"tool":"get_application_package","status":"completed"},{"step":2,"tool":"compare_resume_to_evidence","status":"completed"},{"step":3,"tool":"validate_claim","status":"completed"}],evidence_ids_used=row.evidence_ids_used,input_tokens=response.usage.input_tokens,output_tokens=response.usage.output_tokens,cached_tokens=response.usage.cached_tokens,estimated_cost=response.usage.estimated_cost,latency_ms=response.latency_ms,requires_human_review=status!="READY_FOR_REVIEW");return PackageResponse(status=status,package=self._record_to_schema(row),reviewer_agent_run_id=run.id)
        except Exception as exc:
            row.status="REVIEW_REQUIRED";row.review_status="HUMAN_REVIEW_REQUIRED";row.human_review_reasons=["ReviewerAgent failed; human review required"];db.commit();self.runs.fail(db,run,str(exc));return PackageResponse(status="REVIEW_REQUIRED",package=self._record_to_schema(row),error=str(exc),reviewer_agent_run_id=run.id)
    def edit_answer(self,db:Session,job_id:int,answer_id:str,text:str):
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id));answers=[ApplicationAnswer.model_validate(x) for x in row.application_answers_json];found=False
        for answer in answers:
            if answer.id==answer_id:answer.edited_answer=text;answer.answer=text;answer.answer_status="EDITED_REVALIDATION_REQUIRED";answer.requires_human_review=True;found=True
        if not found:raise KeyError(answer_id)
        row.application_answers_json=[x.model_dump(mode="json") for x in answers];row.status="REVIEW_REQUIRED";row.review_status=None;row.approved_at=None;row.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(row);return self._record_to_schema(row)
    def edit_cover_letter(self,db:Session,job_id:int,text:str):
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id));row.cover_letter=text;row.cover_letter_status="EDITED_REVALIDATION_REQUIRED";row.status="REVIEW_REQUIRED";row.review_status=None;row.approved_at=None;db.commit();db.refresh(row);return self._record_to_schema(row)
    def edit_resume_bullet(self,db:Session,job_id:int,bullet_id:str,text:str):
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id));resume=TailoredResumeData.model_validate(row.tailored_resume_preview_json);found=False
        for bullet in resume.bullets:
            if bullet.id==bullet_id:bullet.edited_text=text;bullet.validation_status="pending_revalidation";found=True
        if not found:raise KeyError(bullet_id)
        row.tailored_resume_preview_json=resume.model_dump(mode="json");row.tailored_resume_path=str(self.renderer.render(job_id,resume));row.status="REVIEW_REQUIRED";row.review_status=None;row.approved_at=None;row.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(row);return self._record_to_schema(row)
    def approve(self,db:Session,job_id:int,save_reusable:bool=False):
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
        if row.status not in {"READY_FOR_REVIEW","APPROVED"}:raise ValueError("Only a reviewer-passed package can be approved")
        row.status="APPROVED";row.approved_at=row.approved_at or datetime.now(timezone.utc);row.requires_human_review=False;row.human_review_reasons=[]
        if save_reusable:
            for answer in [ApplicationAnswer.model_validate(x) for x in row.application_answers_json]:
                if answer.reusable and answer.answer:db.add(ApprovedAnswerHistoryRecord(question_pattern=answer.question_text,approved_answer=answer.answer,category=answer.detected_category,job_id=job_id,evidence_ids=answer.evidence_ids,reusable=True))
        db.commit();db.refresh(row);return self._record_to_schema(row)

    def revalidate_policy_only_change(self,db:Session,job_id:int):
        """Refresh a clean reviewer-passed package after standing-policy changes."""
        row=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
        if not row:raise ValueError("Application package not found")
        if row.review_status!="PASS" or row.review_findings_json or row.unsupported_claims_removed:
            raise ValueError("A clean persisted ReviewerAgent PASS is required")
        identity=IdentityService().get();resume=TailoredResumeData.model_validate(row.tailored_resume_preview_json)
        if (resume.professional_name,resume.email,resume.phone)!=(identity.display_name,identity.email,identity.phone):raise ValueError("Canonical resume identity mismatch")
        for bullet in resume.bullets:
            if self._validate_text(bullet.edited_text or bullet.generated_text,bullet.source_evidence_ids).support_status=="unsupported":raise ValueError(f"Unsupported resume bullet: {bullet.id}")
        for answer in [ApplicationAnswer.model_validate(x) for x in row.application_answers_json]:
            if answer.answer and answer.character_limit and len(answer.answer)>answer.character_limit:raise ValueError(f"Answer exceeds limit: {answer.id}")
            if answer.requires_human_review:raise ValueError(f"Application answer requires review: {answer.id}")
            if answer.detected_category=="work_authorization":
                approved=WorkAuthorizationService().assess(answer.question_text)
                if approved.requires_human_review or answer.answer!=approved.answer:raise ValueError(f"Work authorization mismatch: {answer.id}")
            if answer.answer_type=="EVIDENCE_GENERATED" and answer.answer and self._validate_text(answer.edited_answer or answer.answer,answer.evidence_ids).support_status=="unsupported":raise ValueError(f"Unsupported application answer: {answer.id}")
        job=self.jobs.to_schema(self.jobs.get(db,job_id));job_fp,package_fp=self._fingerprints(job,SemanticEvidenceIndex(self.evidence).version,row.provider,row.model)
        row.job_fingerprint=job_fp;row.package_fingerprint=package_fp;row.status="READY_FOR_REVIEW";row.requires_human_review=True;row.human_review_reasons=["Human approval is required"];row.updated_at=datetime.now(timezone.utc)
        db.commit();db.refresh(row);return self._record_to_schema(row)
