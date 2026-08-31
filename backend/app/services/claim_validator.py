from abc import ABC,abstractmethod
from app.models.policy import ClaimValidationRequest,ClaimValidationResult
class ClaimValidator(ABC):
    @abstractmethod
    def validate(self,request:ClaimValidationRequest)->ClaimValidationResult: ...
class FutureClaimValidator(ClaimValidator):
    def validate(self,request:ClaimValidationRequest)->ClaimValidationResult: raise NotImplementedError("Claim validation arrives with evidence-grounded generation; unsupported claims must never be submitted")
