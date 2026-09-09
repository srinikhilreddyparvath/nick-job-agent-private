from datetime import datetime,timezone

from app.models.job import Job
from app.models.opportunity import ConstraintAssessment,ConstraintState,EvidenceMatch,GapKind,OpportunityGap,OpportunityRecommendation,OpportunityScore
from app.models.profile import JobPreferences


class ConstraintEngine:
    """Evaluate configured constraints without converting unknowns into failures."""
    def evaluate(self,job:Job,preferences:JobPreferences)->ConstraintAssessment:
        location=ConstraintState.unknown
        arrangement=ConstraintState.unknown
        if job.remote_type.value=="remote":arrangement=ConstraintState.match if preferences.remote_allowed else ConstraintState.mismatch;location=arrangement
        elif job.remote_type.value=="hybrid":arrangement=ConstraintState.match if preferences.hybrid_allowed else ConstraintState.mismatch
        elif job.remote_type.value=="onsite":arrangement=ConstraintState.match if preferences.onsite_allowed else ConstraintState.mismatch
        elif job.location:
            configured=preferences.locations+preferences.commutable_locations
            if configured:location=ConstraintState.match if any(x.lower() in job.location.lower() for x in configured) else ConstraintState.mismatch
        if job.remote_type.value!="remote" and job.location:
            configured=preferences.locations+preferences.commutable_locations
            if configured:location=ConstraintState.match if any(x.lower() in job.location.lower() for x in configured) else ConstraintState.mismatch
        compensation=ConstraintState.unknown
        minimum=preferences.compensation.minimum_base_salary or preferences.minimum_salary
        if minimum is not None and job.salary_max is not None:compensation=ConstraintState.match if job.salary_max>=minimum else ConstraintState.mismatch
        employment=ConstraintState.unknown
        if preferences.employment_types and job.employment_type:employment=ConstraintState.match if any(x.lower() in job.employment_type.lower() for x in preferences.employment_types) else ConstraintState.mismatch
        seniority=ConstraintState.unknown;level=None;title=job.title.lower()
        for token,value in (("principal","principal"),("staff","staff"),("senior","senior"),("lead","lead"),("junior","junior"),("entry","entry")):
            if token in title:level=value;break
        if preferences.seniority and level:seniority=ConstraintState.match if any(level in item.lower() for item in preferences.seniority) else ConstraintState.mismatch
        blockers=[]
        if arrangement==ConstraintState.mismatch:blockers.append(f"{job.remote_type.value.title()} work is excluded by configured preferences")
        if location==ConstraintState.mismatch and preferences.relocation_willing is False:blockers.append("Location is outside configured commutable locations and relocation is disabled")
        if compensation==ConstraintState.mismatch and preferences.compensation.salary_is_hard_filter:blockers.append("Compensation is below a configured hard minimum")
        if employment==ConstraintState.mismatch:blockers.append("Employment type is outside configured preferences")
        return ConstraintAssessment(location=location,work_arrangement=arrangement,compensation=compensation,visa=ConstraintState.unknown,employment_type=employment,seniority=seniority,hard_blockers=blockers)


class OpportunityScoringService:
    def __init__(self):self.constraints=ConstraintEngine()
    @staticmethod
    def _component(job:Job,*keys:str)->float|None:
        for key in keys:
            value=job.family_component_scores.get(key) or job.component_scores.get(key)
            if isinstance(value,dict) and value.get("score") is not None:return float(value["score"])
            if getattr(value,"score",None) is not None:return float(value.score)
        return None
    def score(self,job:Job,preferences:JobPreferences,semantic_report:dict|None=None)->OpportunityScore:
        constraints=self.constraints.evaluate(job,preferences)
        technical=self._component(job,"technical_domain_depth","technical_domain_alignment","skills_alignment")
        career=self._component(job,"role_alignment","strategy_execution","seniority_alignment")
        research=self._component(job,"research_alignment","research_depth")
        skills=self._component(job,"skills_alignment","ai_data_understanding")
        location=self._component(job,"location_alignment","location_compensation")
        compensation=self._component(job,"compensation_alignment")
        discovered=job.discovered_at if job.discovered_at.tzinfo else job.discovered_at.replace(tzinfo=timezone.utc)
        age_days=max(0,(datetime.now(timezone.utc)-discovered).days)
        freshness=max(0.0,100.0-age_days*4)
        deterministic=float(job.fit_score) if job.fit_score is not None else None
        semantic=float(job.semantic_fit_score) if job.semantic_fit_score is not None else None
        if deterministic is not None and semantic is not None:base=deterministic*.45+semantic*.55
        elif deterministic is not None:base=deterministic
        elif semantic is not None:base=semantic
        else:base=0
        known=[x for x in (base,technical,career,research,skills,location,compensation,freshness) if x is not None]
        overall=round(base*.8+freshness*.2,1) if deterministic is not None or semantic is not None else round(sum(known)/len(known),1) if known else 0
        cap = self._component(job, "role_family_gate")
        if cap is not None: overall = min(overall, cap)
        if deterministic is None and semantic is None: overall = 0
        if constraints.hard_blockers:recommendation=OpportunityRecommendation.skip
        elif overall>=82:recommendation=OpportunityRecommendation.apply_now
        elif overall>=65:recommendation=OpportunityRecommendation.apply
        elif overall>=52:recommendation=OpportunityRecommendation.contact_first
        else:recommendation=OpportunityRecommendation.stretch
        semantic_strengths=(semantic_report or {}).get("strengths",[])
        matches=[EvidenceMatch(reason=item.get("statement","") if isinstance(item,dict) else str(item),evidence_ids=item.get("evidence_ids",[]) if isinstance(item,dict) else []) for item in semantic_strengths[:3]] if semantic_strengths else [EvidenceMatch(reason=text,evidence_ids=job.matched_evidence_ids[:3]) for text in job.strengths[:3]]
        gaps=[]
        semantic_gaps=[*(semantic_report or {}).get("gaps",[]),*(semantic_report or {}).get("requirement_gaps",[])]
        for text in (semantic_gaps or job.gaps)[:3]:
            lower=text.lower();kind=GapKind.unknown if any(x in lower for x in ("unknown","unconfirmed","not listed")) else GapKind.evidence if any(x in lower for x in ("evidence","resume","wording")) else GapKind.experience
            gaps.append(OpportunityGap(text=text,kind=kind))
        reason={OpportunityRecommendation.apply_now:"High fit and fresh enough to prioritize now.",OpportunityRecommendation.apply:"Relevant opportunity worth applying to.",OpportunityRecommendation.contact_first:"Promising but context from the team could resolve meaningful gaps.",OpportunityRecommendation.stretch:"A plausible stretch; fit affects priority, not permission.",OpportunityRecommendation.skip:"A configured hard constraint blocks this opportunity."}[recommendation]
        confidence=round((job.semantic_fit_confidence or .7)*.55+.8*.45,2) if semantic is not None and deterministic is not None else job.semantic_fit_confidence or (.8 if deterministic is not None else .35)
        return OpportunityScore(overall_score=overall,deterministic_fit=deterministic,semantic_fit=semantic,technical_fit=technical,career_fit=career,research_fit=research,skills_fit=skills,location_fit=location,compensation_fit=compensation,visa_fit=None,freshness_score=freshness,application_effort_score=None,confidence=confidence,recommendation=recommendation,recommendation_reason=reason,why_you_match=matches,real_gaps=gaps,constraints=constraints)
