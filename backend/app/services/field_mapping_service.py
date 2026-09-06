import re
from datetime import date
from app.models.application_package import ApplicationAnswer,ApplicationPackageRead
from app.models.browser import ApplicationFormField
from app.services.identity_service import IdentityService
from app.services.policy_service import AvailabilityPolicy,StandardApplicationPolicy,StandingApplicationPolicy,WorkAuthorizationService

SENSITIVE=("criminal","conflict","non-compete","restrictive covenant","export control","security clearance","disability","veteran","race","ethnicity","gender","sexual orientation","salary history","current salary","start date","relocat","address","street","attest","certify")
DEMOGRAPHIC=("disability","veteran","race","ethnicity","gender","sexual orientation")
class FieldMappingService:
 def __init__(self,application_reference_date:date|None=None):self.application_reference_date=application_reference_date or date.today()
 def normalize(self,label):return " ".join(re.sub(r"[^a-z0-9]+"," ",label.lower()).split())
 def category(self,label,field_type):
  x=self.normalize(label)
  if field_type=="file" or "resume" in x:return "resume"
  if any(k in x for k in ("sponsor","h 1b","authorized to work")):return "work_authorization"
  if any(k in x for k in ("email","phone")):return "contact"
  if any(k in x for k in ("name","linkedin","portfolio")):return "identity"
  if any(k in x for k in DEMOGRAPHIC):return "demographic_optional"
  if any(k in x for k in ("salary","compensation")):return "salary"
  if any(k in x for k in ("attest","certify","criminal","conflict","non compete","security clearance","export")):return "legal"
  return "other"
 def map(self,field:ApplicationFormField,package:ApplicationPackageRead|None=None,certification_allowed:bool=False,salary_min:float|None=None,salary_max:float|None=None):
  x=self.normalize(field.label);field.normalized_label=x;field.detected_category=self.category(field.label,field.field_type.value)
  if field.detected_category=="resume":
   if package and package.status=="APPROVED" and package.tailored_resume_path:
    field.mapped_answer=package.tailored_resume_path;field.mapped_answer_source="Approved ApplicationPackage artifact";field.confidence=1;field.write_allowed=True
   elif field.required:field.requires_human_review=True
   return field
  identity=IdentityService().map_form_field(field.label,field.required)
  if not identity.requires_human_review and identity.value is not None:field.mapped_answer=identity.value;field.mapped_answer_source="IdentityService";field.confidence=1;field.write_allowed=True;return field
  auth=WorkAuthorizationService().assess(field.label)
  if auth.matched_answer_id:field.mapped_answer=auth.answer;field.mapped_answer_source="WorkAuthorizationPolicy";field.confidence=1;field.write_allowed=True;return field
  availability=AvailabilityPolicy().answer(field.label,self.application_reference_date)
  if availability:
   field.mapped_answer=availability.answer;field.mapped_answer_source="AvailabilityPolicy";field.mapping_metadata={"application_reference_date":availability.application_reference_date.isoformat(),"calculated_start_date":availability.calculated_start_date.isoformat(),"policy_version":availability.policy_version};field.confidence=1;field.write_allowed=True;return field
  # Ashby can present this as one optional radio group. Neither option is an
  # exact statement of the approved policy (Bay Area based, commutable to SF,
  # not open to relocation), so leaving it blank is the only truthful mapping.
  if field.field_type.value=="radio" and "san francisco" in x and "relocat" in x and any("san francisco based" in o.lower() for o in field.options) and any("relocat" in o.lower() for o in field.options):
   field.detected_category="location";field.mapping_metadata={"policy":"BAY_AREA_COMMUTABLE_NOT_SF_CITY_NO_RELOCATION"};return field
  approved=StandardApplicationPolicy().resolve(field.label,field.options,field.field_type.value,certification_allowed,salary_min,salary_max)
  if approved:
   answer=approved.answer
   if answer is not None and field.options:
    normalized_answer=self.normalize(answer)
    equivalent={"male":("male","man"),"heterosexual":("heterosexual","straight"),"no":("no","not transgender"),"yes":("yes","agree","i agree")}
    aliases=equivalent.get(normalized_answer,(normalized_answer,))
    answer=next((option for alias in aliases for option in field.options if self.normalize(option)==alias),answer)
   field.detected_category=approved.category;field.mapped_answer=answer;field.mapped_answer_source="User-approved standing policy";field.confidence=1;field.requires_human_review=approved.requires_human_review;field.write_allowed=answer is not None and not approved.requires_human_review;return field
  standing=StandingApplicationPolicy()
  discovery,reason=standing.discovery_source(field.label,field.options)
  if discovery is not None:
   field.mapped_answer=discovery;field.mapped_answer_source="User-approved DISCOVERY_SOURCE policy";field.mapping_metadata={"answer_category":"DISCOVERY_SOURCE","scope":"REUSABLE","approval_source":"USER_APPROVED_POLICY"};field.confidence=1;field.write_allowed=True;return field
  motivation,reason=standing.motivation(field.label,field.character_limit)
  if motivation is not None:
   field.mapped_answer=motivation;field.mapped_answer_source="User-approved PROFESSIONAL_MOTIVATION policy";field.mapping_metadata={"answer_category":"PROFESSIONAL_MOTIVATION","scope":"REUSABLE","approval_source":"USER_APPROVED_POLICY"};field.confidence=1;field.write_allowed=True;return field
  if any(k in x for k in DEMOGRAPHIC):
   decline=next((o for o in field.options if "decline" in o.lower() or "prefer not" in o.lower()),None)
   if decline:field.mapped_answer=decline;field.mapped_answer_source="DECLINE_TO_ANSWER policy";field.confidence=1;field.write_allowed=True
   elif field.required:field.requires_human_review=True;field.sensitivity="sensitive"
   return field
  if any(k in x for k in SENSITIVE) or ("middle name" in x and field.required):field.requires_human_review=field.required;field.sensitivity="sensitive";return field
  if package:
   answer=next((ApplicationAnswer.model_validate(a) for a in package.application_answers if self.normalize(a.question_text)==x),None)
   if not answer and "why" in x:answer=next((ApplicationAnswer.model_validate(a) for a in package.application_answers if "why are you interested" in self.normalize(a.question_text)),None)
   if not answer and "proud" in x:answer=next((ApplicationAnswer.model_validate(a) for a in package.application_answers if "technically difficult" in self.normalize(a.question_text)),None)
   if answer and answer.answer and not answer.requires_human_review:field.mapped_answer=answer.answer;field.mapped_answer_source="ApplicationPackage";field.confidence=answer.confidence;field.write_allowed=True
  if field.required and not field.write_allowed:field.requires_human_review=True
  return field
 def validate_write(self,field):
  return bool(field.write_allowed and not field.requires_human_review and field.mapped_answer is not None and (not field.character_limit or len(field.mapped_answer)<=field.character_limit))
