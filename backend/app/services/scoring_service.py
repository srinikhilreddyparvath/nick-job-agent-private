from abc import ABC, abstractmethod
import re

from app.core.config import get_settings
from app.models.job import ComponentScore, Job, Recommendation, ScoreResult
from app.models.profile import CandidateProfile, JobPreferences


GENERIC_TERMS = {"the", "and", "for", "with", "from", "that", "this", "our", "you", "your", "will", "have", "has", "are", "was", "were", "into", "across", "using", "work", "working", "experience", "team", "teams", "role", "skills", "ability", "strong", "excellent", "including", "problem", "problems", "requirements", "customer", "customers", "data", "research", "platform", "product", "manager", "senior", "staff", "lead", "support", "develop", "development", "management"}


def terms(values:list[str])->set[str]:
    return {word for value in values for word in re.findall(r"[a-z0-9+#.]+",value.lower()) if len(word)>2 and word not in GENERIC_TERMS}


class ScoringEngine(ABC):
    @abstractmethod
    def score(self,job:Job,profile:CandidateProfile,preferences:JobPreferences)->ScoreResult: ...


class DeterministicScoringEngine(ScoringEngine):
    def __init__(self,weights:dict[str,float]|None=None,thresholds:dict[str,float]|None=None):
        settings=get_settings(); self.weights=weights or settings.scoring_weights; self.thresholds=thresholds or settings.recommendation_thresholds
        if abs(sum(self.weights.values())-1)>1e-9: raise ValueError("Scoring weights must total 1.0")

    def score(self,job:Job,profile:CandidateProfile,preferences:JobPreferences)->ScoreResult:
        haystack=" ".join([job.title,job.description,*job.requirements,*job.preferred_qualifications]).lower()
        title_matches=[x for x in preferences.preferred_titles if x.lower() in job.title.lower()]
        domain_matches=[x for x in preferences.preferred_domains if x.lower() in haystack]
        profile_skills=[x.value for x in profile.skills]; matched_skills=[x for x in profile_skills if x.lower() in haystack]
        missing_skills=sorted({req for req in job.requirements if terms([req]) and not terms([req])&terms(profile_skills)})[:8]
        experience_terms=terms([x.value for x in profile.roles]+[x.value for x in profile.experience]+[x.value for x in profile.technical_domains]); experience_overlap=experience_terms&terms([haystack])
        research_terms=terms([x.value for x in profile.research]+[x.value for x in profile.publications]); research_overlap=research_terms&terms([haystack])
        seniority_markers=[x for x in preferences.seniority if x.lower() in job.title.lower()]

        if not job.location and job.remote_type.value=="unspecified": location_score,location_reason=50,"Location and remote status are unknown; scored neutrally"
        elif job.remote_type.value=="remote": location_score,location_reason=(100,"Remote role is allowed") if preferences.remote_allowed else (0,"Remote roles are disabled")
        elif job.remote_type.value=="hybrid": location_score,location_reason=(100,"Hybrid role is allowed") if preferences.hybrid_allowed else (0,"Hybrid roles are disabled")
        else:
            local=not preferences.locations or any(x.lower() in (job.location or "").lower() for x in preferences.locations)
            location_score,location_reason=(100,"Location is in a preferred area") if local else (35,"Onsite location is outside preferred areas")

        minimum=preferences.compensation.minimum_base_salary or preferences.minimum_salary
        if job.salary_max is None: compensation_score,compensation_reason=50,"Compensation is undisclosed; scored neutrally"
        elif minimum is None: compensation_score,compensation_reason=75,"Compensation is disclosed; no minimum is configured"
        elif job.salary_max>=minimum: compensation_score,compensation_reason=100,"Compensation meets the configured minimum"
        else: compensation_score,compensation_reason=max(0,75-preferences.compensation.below_minimum_penalty),"Compensation is explicitly below the configured minimum"

        values={
          "role_alignment":(100 if title_matches else 45,"Matches a preferred role" if title_matches else "No exact preferred-role phrase; partial credit retained"),
          "technical_domain_alignment":(min(100,50+50*len(domain_matches)/max(1,min(3,len(preferences.preferred_domains)))) if domain_matches else 50,f"{len(domain_matches)} preferred technical domain(s) matched" if domain_matches else "Technical emphasis is unclear; scored neutrally"),
          "skills_alignment":(min(100,50+50*len(matched_skills)/max(1,len(profile_skills))) if matched_skills else 50,f"{len(matched_skills)} verified profile skill(s) matched" if matched_skills else "No explicit verified skill match; scored neutrally"),
          "experience_alignment":(min(100,40+4*len(experience_overlap)),f"{len(experience_overlap)} verified experience/domain term(s) overlap"),
          "research_alignment":(min(100,50+8*len(research_overlap)) if research_overlap else 50,"Research emphasis is unclear; scored neutrally" if not research_overlap else f"{len(research_overlap)} research term(s) overlap"),
          "seniority_alignment":(85 if seniority_markers else 50,"Seniority is ambiguous; scored neutrally" if not seniority_markers else "Seniority marker aligns"),
          "location_alignment":(location_score,location_reason),"compensation_alignment":(compensation_score,compensation_reason)}
        components={name:ComponentScore(score=score,weight=self.weights[name],explanation=reason) for name,(score,reason) in values.items()}
        overall=round(sum(x.score*x.weight for x in components.values()),1)
        recommendation=Recommendation.exceptional if overall>=self.thresholds["exceptional"] else Recommendation.strong if overall>=self.thresholds["strong"] else Recommendation.possible if overall>=self.thresholds["possible"] else Recommendation.weak if overall>=self.thresholds["weak"] else Recommendation.skip
        strengths=[x.explanation for x in components.values() if x.score>=75][:5]; gaps=[x.explanation for x in components.values() if x.score<50][:5]
        unknowns=[x.explanation for x in components.values() if "unknown" in x.explanation.lower() or "unclear" in x.explanation.lower() or "ambiguous" in x.explanation.lower() or "undisclosed" in x.explanation.lower()]
        summary=f"Deterministic score {overall}/100 using configured Phase 2 weights and verified candidate memory. Unknown data is neutral. Missing-data notes: {'; '.join(unknowns) if unknowns else 'none'}."
        return ScoreResult(overall_score=overall,component_scores=components,strengths=strengths,gaps=gaps,matched_skills=matched_skills,missing_skills=missing_skills,reasoning_summary=summary,recommendation=recommendation)
