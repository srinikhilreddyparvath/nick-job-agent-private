import json
from pathlib import Path
from app.models.policy import ApprovedAnswer, WorkAuthorizationAssessment
from app.services.identity_service import IdentityService

class AnswerBankService:
    def __init__(self,path:Path|None=None):
        path=path or Path(__file__).resolve().parents[3]/"data"/"answer_bank.example.json"; data=json.loads(path.read_text(encoding="utf-8")); self.sections={k:[ApprovedAnswer.model_validate(x) for x in v] for k,v in data.items()}
        identity = IdentityService()
        identity_answers = []
        for answer_id, question, label, evidence_ids in (
            ("IDENTITY_LEGAL_FIRST_NAME", "What is your legal first or given name?", "Legal First Name", ["IDENTITY_002"]),
            ("IDENTITY_LEGAL_LAST_NAME", "What is your legal last or family name?", "Legal Last Name", ["IDENTITY_002"]),
            ("IDENTITY_LEGAL_NAME", "What is your full legal name?", "Full Legal Name", ["IDENTITY_002"]),
            ("IDENTITY_PREFERRED_NAME", "What is your preferred name?", "Preferred Name", ["IDENTITY_001"]),
            ("IDENTITY_PROFESSIONAL_NAME", "What is your professional name?", "Professional Name", ["IDENTITY_001"]),
            ("IDENTITY_EMAIL", "What is your email address?", "Email", ["IDENTITY_003"]),
            ("IDENTITY_PHONE", "What is your phone number?", "Phone", ["IDENTITY_003"]),
            ("IDENTITY_PORTFOLIO", "What is your portfolio URL?", "Portfolio URL", ["IDENTITY_004"]),
            ("IDENTITY_LINKEDIN", "What is your LinkedIn URL?", "LinkedIn URL", ["IDENTITY_004"]),
        ):
            mapping = identity.map_form_field(label)
            identity_answers.append(ApprovedAnswer(id=answer_id, question=question, answer=mapping.value, answer_type="APPROVED_STRUCTURED", evidence_ids=evidence_ids, verified=not mapping.requires_human_review, requires_review=mapping.requires_human_review))
        self.sections["approved_structured"] = identity_answers + self.sections["approved_structured"]
    def all(self)->dict[str,list[ApprovedAnswer]]: return self.sections

class WorkAuthorizationService:
    risky=("unrestricted","permanent authorization","no current or future immigration support","immigration status certification","country-specific","without sponsorship")
    def __init__(self): self.answers=AnswerBankService().sections["approved_structured"]
    def assess(self,question:str)->WorkAuthorizationAssessment:
        normalized=" ".join(question.lower().split())
        if any(x in normalized for x in self.risky): return WorkAuthorizationAssessment(requires_human_review=True,reason="Materially different legal wording requires human review")
        for item in self.answers:
            if item.id.startswith(("WORK_","SPONSORSHIP_","H1B_")) and normalized.rstrip("?")==item.question.lower().rstrip("?"):
                return WorkAuthorizationAssessment(matched_answer_id=item.id,answer=item.answer,requires_human_review=False,reason="Exact approved standard question")
        return WorkAuthorizationAssessment(requires_human_review=True,reason="No exact approved work-authorization question match")
