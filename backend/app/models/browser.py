from datetime import datetime,timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel,ConfigDict,Field,field_validator

class Eligibility(StrEnum): eligible="ELIGIBLE";eligible_low_confidence="ELIGIBLE_LOW_CONFIDENCE";needs_review="NEEDS_REVIEW";blocked="BLOCKED";skip="SKIP"
class BrowserMode(StrEnum): inspect_only="INSPECT_ONLY";fill_only="FILL_ONLY";user_triggered_submit="USER_TRIGGERED_SUBMIT";auto_submit="AUTO_SUBMIT"
class FieldType(StrEnum): text="text";textarea="textarea";email="email";phone="phone";url="url";select="select";radio="radio";checkbox="checkbox";file="file";date="date";number="number";hidden="hidden";other="other"
class ApplicationFormField(BaseModel):
 field_id:str;label:str;normalized_label:str;field_type:FieldType;required:bool=False;options:list[str]=Field(default_factory=list);character_limit:int|None=None;detected_category:str="other";mapped_answer_source:str|None=None;mapped_answer:str|None=None;mapping_metadata:dict[str,Any]=Field(default_factory=dict);confidence:float=0;sensitivity:str="normal";requires_human_review:bool=False;write_allowed:bool=False
class SubmitControl(BaseModel):
 selector_strategy:str="legacy";locator_value:str|None=None;accessible_name:str="Submit";element_type:str="button";visible:bool=False;enabled:bool=False;actionable:bool=False
class ApplicationFormSchema(BaseModel):
 application_url:str;ats:str;company:str;job_id:int;steps:list[str]=Field(default_factory=list);fields:list[ApplicationFormField]=Field(default_factory=list);required_fields:list[str]=Field(default_factory=list);optional_fields:list[str]=Field(default_factory=list);file_uploads:list[str]=Field(default_factory=list);submit_controls:list[SubmitControl]=Field(default_factory=list);captcha_detected:bool=False;authentication_required:bool=False;form_fingerprint:str="";status:str="NOT_INSPECTED"
 @field_validator("submit_controls",mode="before")
 @classmethod
 def legacy_submit_controls(cls,value):
  return [item if isinstance(item,(dict,SubmitControl)) else {"accessible_name":str(item),"locator_value":str(item)} for item in (value or [])]
class EligibilityDecision(BaseModel):eligibility:Eligibility;priority:float;reasons:list[str]=Field(default_factory=list);hard_blockers:list[str]=Field(default_factory=list);manual_override:bool=False
class BrowserRunRequest(BaseModel):mode:BrowserMode=BrowserMode.inspect_only;dry_run:bool=True;manual_override:bool=False
class BrowserRunResult(BaseModel):status:str;eligibility:EligibilityDecision|None=None;form:ApplicationFormSchema|None=None;fields_resolved:int=0;fields_needing_review:int=0;resume_upload_status:str="NOT_ATTEMPTED";ready_to_submit:bool=False;blockers:list[str]=Field(default_factory=list);events:list[dict[str,Any]]=Field(default_factory=list);submitted:bool=False;confirmation_url:str|None=None;failure_stage:str|None=None;error_code:str|None=None;external_click_occurred:bool=False;confirmation_verified:bool=False;receipt_created:bool=False;retry_allowed:bool=True;diagnostics:dict[str,Any]=Field(default_factory=dict)
class AutoApplyPolicy(BaseModel):
 enabled:bool=False;allowed_role_families:list[str]=Field(default_factory=lambda:["RESEARCH_AI","DATA_SCIENCE","PRODUCT_MANAGEMENT"]);allowed_locations:list[str]=Field(default_factory=list);employment_types:list[str]=Field(default_factory=lambda:["full-time"]);excluded_companies:list[str]=Field(default_factory=list);excluded_keywords:list[str]=Field(default_factory=list);minimum_salary_if_known:int|None=None;allow_unknown_salary:bool=True;apply_to_moderate_fit:bool=True;manual_override_behavior:str="eligibility_only";daily_application_cap:int=25;company_daily_cap:int=3;requires_package_pass:bool=True;requires_all_required_fields_resolved:bool=True;stop_on_unknown_sensitive_field:bool=True
class BrowserSettingsRead(BaseModel):application_mode:str;auto_submit_enabled:bool;policy:AutoApplyPolicy
class QueueItemRead(BaseModel):
 id:int;job_id:int;application_package_id:int;priority:float;eligibility:str;status:str;attempt_count:int;next_attempt_at:datetime|None=None;block_reason:str|None=None;last_error:str|None=None;created_at:datetime;updated_at:datetime;model_config=ConfigDict(from_attributes=True)
class ApplicationReceiptRead(BaseModel):
 id:int;application_id:int|None=None;job_id:int;company:str;role:str;submitted_at:datetime;ats:str;apply_url:str;confirmation_url:str|None=None;external_confirmation_text:str|None=None;external_application_id:str|None=None;resume_artifact_hash:str;application_package_version:str;model_config=ConfigDict(from_attributes=True)
class ApplyOverrideRequest(BaseModel):enabled:bool=True
class AutoApplySettingsUpdate(BaseModel):application_mode:str|None=None;auto_submit_enabled:bool|None=None;auto_apply_paused:bool|None=None;override_receipt_prerequisite:bool=False;policy:AutoApplyPolicy|None=None
class FormResolutionRequest(BaseModel):field_label:str;answer:str;scope:str="JUST_THIS_APPLICATION"
