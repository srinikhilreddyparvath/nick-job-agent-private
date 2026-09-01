from abc import ABC,abstractmethod
import re
from app.models.policy import ClaimValidationRequest,ClaimValidationResult
from app.services.evidence_service import EvidenceService
class ClaimValidator(ABC):
    @abstractmethod
    def validate(self,request:ClaimValidationRequest)->ClaimValidationResult: ...
class EvidenceClaimValidator(ClaimValidator):
    def __init__(self,evidence:EvidenceService|None=None):self.evidence=evidence or EvidenceService()
    def validate(self,request:ClaimValidationRequest)->ClaimValidationResult:
        records=[self.evidence.get_by_id(x) for x in request.supporting_evidence_ids];records=[x for x in records if x and x.verified]
        if not records:return ClaimValidationResult(generated_claim=request.generated_claim,supporting_evidence_ids=request.supporting_evidence_ids,support_status="unsupported",confidence=1,reason="No valid verified evidence IDs were supplied",action="remove_or_rephrase_as_gap")
        stop={"nick","has","with","and","the","for","from","experience","strong","extensive","work"};claim={x for x in re.findall(r"[a-z0-9]+",request.generated_claim.lower()) if len(x)>2 and x not in stop};source={x for record in records for x in re.findall(r"[a-z0-9]+",(" ".join([record.statement,*record.skills,*record.domains])).lower()) if len(x)>2 and x not in stop};overlap=len(claim&source)/max(1,len(claim))
        status="supported" if overlap>=.55 else "partially_supported" if overlap>=.25 else "ambiguous" if overlap>=.1 else "unsupported";action="allow" if status=="supported" else "qualify" if status=="partially_supported" else "review" if status=="ambiguous" else "remove_or_rephrase_as_gap"
        return ClaimValidationResult(generated_claim=request.generated_claim,supporting_evidence_ids=request.supporting_evidence_ids,support_status=status,confidence=round(max(overlap,1-overlap) if status in {"supported","unsupported"} else .6,2),reason=f"Verified evidence term coverage: {overlap:.0%}",action=action)
FutureClaimValidator=EvidenceClaimValidator
