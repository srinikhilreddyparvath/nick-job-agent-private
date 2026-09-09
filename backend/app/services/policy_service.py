import json,re
from dataclasses import dataclass
from datetime import date,timedelta
from pathlib import Path
from app.models.policy import ApprovedAnswer, WorkAuthorizationAssessment
from app.services.identity_service import IdentityService
from app.services.profile_service import _configured_path,load_application_policy
from app.core.config import get_settings

class AnswerBankService:
    def __init__(self,path:Path|None=None):
        explicit_path = path is not None
        path=path or _configured_path(get_settings().candidate_answer_bank_path,"answer_bank.example.json")
        data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"approved_structured":[],"evidence_generated":[],"human_review_required":[]}
        from app.services.candidate_context_service import read_bundle
        if not explicit_path and read_bundle(): data = {"approved_structured":[],"evidence_generated":[],"human_review_required":[]}
        self.sections={k:[ApprovedAnswer.model_validate(x) for x in v] for k,v in data.items()}
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

class StandingApplicationPolicy:
    DISCOVERY_PREFERENCES=("linkedin","social media","google","search engine","friend","word of mouth","company website","careers website","other")
    DISCOVERY_QUESTIONS=("how did you hear about","how did you hear about this opportunity","how did you learn about this position","where did you find this job","how did you find us")
    REFERRAL_DETAILS=("employee name","recruiter name","referral name","referral id","referral code","event name","conference","university recruiter","agency")

    @staticmethod
    def _normalize(value:str)->str:return " ".join(value.lower().replace("/"," ").replace("-"," ").split())

    def discovery_source(self,question:str,options:list[str])->tuple[str|None,str]:
        normalized=self._normalize(question)
        if any(term in normalized for term in self.REFERRAL_DETAILS):return None,"Specific referral/discovery detail is not approved"
        if not any(term in normalized for term in self.DISCOVERY_QUESTIONS):return None,"Not a generic discovery-source question"
        for preference in self.DISCOVERY_PREFERENCES:
            for option in options:
                candidate=self._normalize(option)
                if "employee referral" in candidate:continue
                if preference in candidate or (preference=="social media" and "social network" in candidate) or (preference in {"google","search engine"} and "web search" in candidate) or (preference in {"friend","word of mouth"} and "friend or colleague" in candidate):
                    return option,"User-approved reusable discovery-source policy"
        return ("LinkedIn","User-approved reusable discovery-source policy") if not options else (None,"No approved generic option available")

    def motivation(self,question:str,character_limit:int|None=None)->tuple[str|None,str]:
        normalized=self._normalize(question)
        if any(term in normalized for term in ("why this company","why this role","why do you want to work","why are you interested","specific company","specific product","specific mission")):return None,"Company/role-specific question"
        if not any(term in normalized for term in ("what motivates you","motivates you professionally","work motivates you","excites you about your work","work excites you","what drives you")):return None,"Not a professional-motivation question"
        approved=next((item for item in AnswerBankService().sections.get("approved_structured",[]) if item.answer_category=="PROFESSIONAL_MOTIVATION" and item.answer),None)
        if not approved:return None,"No approved reusable professional-motivation answer"
        answer=approved.answer
        if character_limit and len(answer)>character_limit:
            short="I am motivated by taking research through experimentation and evaluation into production, where it can create measurable real-world impact."
            if len(short)>character_limit:return None,"Approved deterministic shortening exceeds field limit"
            answer=short
        return answer,"User-approved reusable professional-motivation policy"

class WorkAuthorizationService:
    risky=("unrestricted","permanent authorization","no current or future immigration support","immigration status certification","country-specific","without sponsorship")
    def __init__(self): self.answers=AnswerBankService().sections["approved_structured"];self.policy=load_application_policy().work_authorization
    def assess(self,question:str)->WorkAuthorizationAssessment:
        normalized=" ".join(re.sub(r"[^a-z0-9]+"," ",question.lower()).split())
        if "visa" in normalized and "expir" in normalized and any(x in normalized for x in ("sponsor","status","h 1b","h1b")):
            status=self.policy.get("current_status");expiration=self.policy.get("expiration")
            if status and expiration:return WorkAuthorizationAssessment(matched_answer_id="IMMIGRATION_STATUS_EXPIRATION",answer=f"{status}; expiration {expiration}",requires_human_review=False,reason="Configured work-authorization policy")
        if any(x in normalized for x in self.risky): return WorkAuthorizationAssessment(requires_human_review=True,reason="Materially different legal wording requires human review")
        mappings=(
            (("visa expiration","immigration expiration","h 1b expiration","h1b expiration"),"IMMIGRATION_EXPIRATION",self.policy.get("expiration")),
            (("u s citizen","us citizen","united states citizen"),"US_CITIZEN",self.policy.get("us_citizen")),
            (("permanent resident","green card holder"),"PERMANENT_RESIDENT",self.policy.get("permanent_resident")),
            (("new visa lottery","cap selection","new h 1b lottery","h 1b cap selection","h1b lottery"),"NEW_LOTTERY_REQUIRED",self.policy.get("new_lottery_required")),
            (("visa transfer","change of employer","h 1b transfer"),"TRANSFER_REQUIRED",self.policy.get("transfer_required")),
            (("currently in h 1b status","current h 1b status","current immigration status","current visa","visa status"),"IMMIGRATION_STATUS",self.policy.get("current_status")),
            (("require sponsorship","require employment visa sponsorship","need visa sponsorship","employer immigration support","sponsorship at any point","now or later need","now or in the future require"),"SPONSORSHIP_REQUIRED",self.policy.get("sponsorship_required")),
            (("authorized to work","legally authorized"),"WORK_AUTHORIZED_US",self.policy.get("authorized_us")),
        )
        for phrases,answer_id,answer in mappings:
            if any(phrase in normalized for phrase in phrases):return WorkAuthorizationAssessment(matched_answer_id=answer_id,answer=answer,requires_human_review=answer is None,reason="Configured work-authorization policy" if answer is not None else "Work-authorization value is not configured")
        for item in self.answers:
            item_normalized=" ".join(re.sub(r"[^a-z0-9]+"," ",item.question.lower()).split())
            if item.id.startswith(("WORK_","SPONSORSHIP_","H1B_")) and normalized==item_normalized:
                return WorkAuthorizationAssessment(matched_answer_id=item.id,answer=item.answer,requires_human_review=False,reason="Exact approved standard question")
        return WorkAuthorizationAssessment(requires_human_review=True,reason="No exact approved work-authorization question match")

@dataclass(frozen=True)
class AvailabilityAnswer:
    answer:str;application_reference_date:date;calculated_start_date:date;policy_version:str="availability_v1_plus_14_calendar_days"

class AvailabilityPolicy:
    def answer(self,question:str,reference_date:date|None=None)->AvailabilityAnswer|None:
        reference=reference_date or date.today();start=reference+timedelta(days=14);normalized=" ".join(question.lower().replace("-"," ").split())
        if "notice period" in normalized:return AvailabilityAnswer("2 weeks",reference,start)
        if any(x in normalized for x in ("earliest start month","available month","earliest month")):return AvailabilityAnswer(start.strftime("%B %Y"),reference,start)
        if any(x in normalized for x in ("earliest start date","available start date","when can you start","earliest availability","able to join")):return AvailabilityAnswer(start.isoformat(),reference,start)
        return None

@dataclass(frozen=True)
class StandingPolicyAnswer:
    answer:str|None
    category:str
    requires_human_review:bool=False
    reason:str="User-approved standing policy"

class StandardApplicationPolicy:
    """Deterministic mappings for user-approved routine application facts."""
    def __init__(self):self.answers=load_application_policy().answers
    def value(self,key:str)->str|None:return self.answers.get(key)
    def normalize(self,value:str)->str:return " ".join(re.sub(r"[^a-z0-9]+"," ",value.lower()).split())
    def choose(self,options:list[str],aliases:tuple[str,...],fallback:str)->str:
        for alias in aliases:
            for option in options:
                candidate=self.normalize(option)
                if alias==candidate or re.search(rf"(?:^| ){re.escape(alias)}(?: |$)",candidate):return option
        return fallback
    def resolve(self,question:str,options:list[str]|None=None,field_type:str="text",certification_allowed:bool=False,salary_min:float|None=None,salary_max:float|None=None)->StandingPolicyAnswer|None:
        x=self.normalize(question);options=options or []
        pick=lambda aliases,fallback:self.choose(options,aliases,fallback)
        # Contact and residence facts.
        if any(k in x for k in ("street address","address line 1","home address")):return StandingPolicyAnswer(self.value("street_address"),"address",self.value("street_address") is None)
        if x in {"city","home city","current city"} or "city of residence" in x:return StandingPolicyAnswer(self.value("city"),"address",self.value("city") is None)
        if x in {"state","state province","state of residence"}:return StandingPolicyAnswer(self.value("state_code") or self.value("state"),"address",not bool(self.value("state_code") or self.value("state")))
        if any(k in x for k in ("zip code","postal code","zipcode")):return StandingPolicyAnswer(self.value("postal_code"),"address",self.value("postal_code") is None)
        if x in {"country","country of residence"}:return StandingPolicyAnswer(self.value("country"),"address",self.value("country") is None)
        # DOB is supplied only when explicitly requested; age eligibility does not disclose it.
        if any(k in x for k in ("date of birth","birth date","dob")):
            dob=self.value("date_of_birth")
            if dob and field_type!="date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}",dob):year,month,day=dob.split("-");dob=f"{month}/{day}/{year}"
            return StandingPolicyAnswer(dob,"date_of_birth",dob is None)
        if any(k in x for k in ("over 18","at least 18","legally old enough to work")):return StandingPolicyAnswer(self.value("over_18"),"age_eligibility",self.value("over_18") is None)
        # Location and schedule preferences.
        if any(k in x for k in ("preferred location","preferred work location","work region")):return StandingPolicyAnswer(self.value("preferred_location"),"location",self.value("preferred_location") is None)
        if "relocation assistance" in x:return StandingPolicyAnswer(self.value("relocation_assistance"),"relocation",self.value("relocation_assistance") is None)
        if any(k in x for k in ("willing to relocate","would you relocate","would you move for this job","open to relocation")):return StandingPolicyAnswer(self.value("relocation"),"relocation",self.value("relocation") is None)
        if any(k in x for k in ("work onsite","work on site","onsite work","on site work","commute to","office","hybrid")):
            answer=self.value("hybrid") if "hybrid" in x else self.value("onsite");return StandingPolicyAnswer(answer,"location",answer is None)
        if any(k in x for k in ("remote work","work remotely","remote us")):return StandingPolicyAnswer(self.value("remote"),"location",self.value("remote") is None)
        # User-approved voluntary demographic answers.
        demographic={"gender":"gender","gender identity":"gender","sex":"gender","race":"race","race ethnicity":"race","racial identity":"race"}
        if x in demographic:return StandingPolicyAnswer(self.value(demographic[x]),"demographic",self.value(demographic[x]) is None)
        for phrase,key in (("hispanic","hispanic_latino"),("latino","hispanic_latino"),("pronoun","pronouns"),("sexual orientation","sexual_orientation"),("transgender","transgender"),("veteran","veteran"),("disability","disability")):
            if phrase in x:return StandingPolicyAnswer(self.value(key),"demographic",self.value(key) is None)
        # Compensation: never disclose salary history or invent a numeric range.
        if any(k in x for k in ("current salary","salary history","previous salary")):return StandingPolicyAnswer(pick(("prefer not to answer","decline to answer","decline"),""),"salary",not bool(options and any("decline" in self.normalize(o) or "prefer not" in self.normalize(o) for o in options)),"Salary history is not approved for disclosure")
        if any(k in x for k in ("minimum acceptable salary","minimum salary","minimum base")):return StandingPolicyAnswer(self.value("minimum_salary"),"salary",self.value("minimum_salary") is None)
        if any(k in x for k in ("desired salary","salary expectation","expected salary","compensation expectation")):
            if field_type=="number":
                minimum=int(self.value("minimum_salary") or 0);preferred=int(self.value("preferred_salary") or minimum)
                if salary_max is None or salary_max<minimum:return StandingPolicyAnswer(None,"salary",True,"Numeric desired salary requires a compatible employer-posted range")
                target=max(preferred,int(salary_min or minimum));target=min(target,int(salary_max))
                return StandingPolicyAnswer(str(target),"salary")
            return StandingPolicyAnswer(self.value("salary_free_text"),"salary",self.value("salary_free_text") is None)
        # Travel, schedule, driving, and employer contact.
        if any(k in x for k in ("maximum travel","travel percentage","percent travel","willing to travel")):return StandingPolicyAnswer(self.value("travel"),"travel",self.value("travel") is None)
        if any(k in x for k in ("weekend work","weekend availability","available weekends")):return StandingPolicyAnswer(self.value("weekends"),"schedule",self.value("weekends") is None)
        if any(k in x for k in ("non standard shift","nonstandard shift","night shift","overnight shift")):return StandingPolicyAnswer(self.value("nonstandard_shifts"),"schedule",self.value("nonstandard_shifts") is None)
        if any(k in x for k in ("standard weekday","weekday schedule")):return StandingPolicyAnswer(self.value("standard_weekday"),"schedule",self.value("standard_weekday") is None)
        if any(k in x for k in ("drivers license","driver license","driver s license")):return StandingPolicyAnswer(self.value("drivers_license"),"drivers_license",self.value("drivers_license") is None) if not any(k in x for k in ("number","issuing state","expiration")) else StandingPolicyAnswer(None,"drivers_license",True,"License detail is not configured")
        if any(k in x for k in ("contact your current employer","contact current employer")):return StandingPolicyAnswer(self.value("contact_current_employer"),"employment",self.value("contact_current_employer") is None)
        if x in {"current employer","current company"}:return StandingPolicyAnswer(self.value("current_employer"),"employment",self.value("current_employer") is None)
        # Clearly equivalent factual/compliance questions only.
        factual_no={"relative employed":"relative employed by company","government history":"government employee","non_compete":"subject to a non compete","criminal":"convicted","conflict":"conflict of interest"}
        for category,phrase in factual_no.items():
            if phrase in x:
                key={"relative employed":"relative_employed","government history":"government_history","non_compete":"non_compete","criminal":"criminal_history","conflict":"conflict_of_interest"}[category];return StandingPolicyAnswer(self.value(key),category,self.value(key) is None)
        if "government contractor" in x:return StandingPolicyAnswer(self.value("government_history"),"government history",self.value("government_history") is None)
        if "restrictive covenant" in x:return StandingPolicyAnswer(self.value("non_compete"),"non_compete",self.value("non_compete") is None)
        if any(k in x for k in ("drug test","drug screening","background check")):return StandingPolicyAnswer(self.value("standard_consent"),"consent",self.value("standard_consent") is None)
        # Export control and arbitration distinctions are intentionally narrow.
        if "export control restriction" in x:return StandingPolicyAnswer(self.value("export_control_restriction"),"export_control",self.value("export_control_restriction") is None)
        if any(k in x for k in ("us person under itar","u s person under itar","eligible to access export controlled","export license","citizen national permanent resident")):return StandingPolicyAnswer(None,"export_control",True,"Legally distinct export-control question")
        if any(k in x for k in ("currently subject to a binding arbitration","currently bound by arbitration","bound by an arbitration agreement with another employer")):return StandingPolicyAnswer(self.value("current_arbitration"),"arbitration",self.value("current_arbitration") is None)
        if "agree" in x and "arbitration" in x:return StandingPolicyAnswer(None,"arbitration",True,"New contractual arbitration consent is not approved")
        # Standard application-process terms.
        if any(k in x for k in ("privacy policy","terms of use","electronic communications","process application data")):return StandingPolicyAnswer(pick(("agree","yes","i agree"),"YES"),"standard_terms")
        if any(k in x for k in ("certify that the information","information provided is true","application is complete and truthful","false information may result")):
            return StandingPolicyAnswer(pick(("agree","yes","certify","i agree"),"YES"),"truthfulness_certification",not certification_allowed,"Certification requires a fully validated application")
        if any(k in x for k in ("electronic signature","type your full name","signature full name")):
            return StandingPolicyAnswer(IdentityService().get().legal_name,"electronic_signature",not certification_allowed or not IdentityService().get().legal_name,"Signature requires a fully validated application")
        return None
