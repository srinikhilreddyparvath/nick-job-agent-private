from app.models.job import Job
from app.models.profile import CandidateProfile,JobPreferences
from app.models.role_family import FamilyFitResult,RoleFamily
from app.services.evidence_service import EvidenceService
from app.services.scoring_service import DeterministicScoringEngine

PROFILES={
 RoleFamily.research_ai:{"research_alignment":.25,"technical_alignment":.20,"ml_ai_depth":.15,"experience_alignment":.15,"skills_alignment":.10,"production_research_fit":.10,"location_compensation":.05},
 RoleFamily.data_science:{"data_science_alignment":.20,"statistical_eval_fit":.20,"technical_alignment":.15,"production_experience":.15,"experimentation_fit":.10,"domain_alignment":.10,"skills_alignment":.05,"location_compensation":.05},
 RoleFamily.product_management:{"technical_domain_depth":.20,"product_problem_framing":.20,"cross_functional_evidence":.20,"ai_data_understanding":.15,"strategy_execution":.10,"communication_leadership":.10,"location_compensation":.05}}
KEYWORDS={
 RoleFamily.research_ai:{"research_alignment":["research","scientist","paper","evaluation"],"technical_alignment":["machine learning","ai","llm","reinforcement","computer vision","nlp"],"ml_ai_depth":["model","training","pytorch","tensorflow"],"experience_alignment":["production","develop","lead"],"skills_alignment":["python","sql","pytorch"],"production_research_fit":["production","experiment","deploy","scale"]},
 RoleFamily.data_science:{"data_science_alignment":["data scientist","data science","decision scientist"],"statistical_eval_fit":["statistical","evaluation","causal","measurement","precision","recall"],"technical_alignment":["python","sql","machine learning"],"production_experience":["production","pipeline","scale"],"experimentation_fit":["experiment","a/b","hypothesis"],"domain_alignment":["marketplace","growth","product","analytics"],"skills_alignment":["python","sql","pandas","spark"]},
 RoleFamily.product_management:{"technical_domain_depth":["ai","ml","data","platform","search"],"product_problem_framing":["problem","customer","requirements","product"],"cross_functional_evidence":["cross-functional","stakeholder","engineering","design"],"ai_data_understanding":["ai","machine learning","data science","analytics"],"strategy_execution":["strategy","roadmap","launch","execution"],"communication_leadership":["communication","leadership","alignment","partner"]}}

class FamilyScoringEngine:
 def __init__(self,evidence:EvidenceService|None=None): self.evidence=evidence or EvidenceService(); self.baseline=DeterministicScoringEngine()
 def score(self,job:Job,profile:CandidateProfile,preferences:JobPreferences)->FamilyFitResult:
    if job.role_family==RoleFamily.unknown:
      return FamilyFitResult(role_family=job.role_family,family_fit_score=45,family_component_scores={"unknown":{"score":45,"weight":1,"explanation":"Family confidence is insufficient"}},strengths=[],gaps=["Role family is unknown"],matched_evidence_ids=[],recommendation="skip")
    text=" ".join([job.title,job.description,*job.requirements,*job.preferred_qualifications]).lower(); components={}; evidence_ids=[]
    for name,weight in PROFILES[job.role_family].items():
      if name=="location_compensation":
        baseline=self.baseline.score(job,profile,preferences); score=(baseline.component_scores["location_alignment"].score+baseline.component_scores["compensation_alignment"].score)/2; hits=[]
      else:
        hits=[x for x in KEYWORDS[job.role_family][name] if x in text]; score=min(100,50+15*len(hits)) if hits else 50
      components[name]={"score":round(score,1),"weight":weight,"explanation":f"Matched signals: {', '.join(hits)}" if hits else "No explicit signal; scored neutrally"}
    matched_terms={term for values in KEYWORDS[job.role_family].values() for term in values if term in text}
    for record in self.evidence.search():
      evidence_text=" ".join(record.skills+record.domains+ [record.statement]).lower()
      if any(term in evidence_text for term in matched_terms): evidence_ids.append(record.id)
    score=round(sum(v["score"]*v["weight"] for v in components.values()),1); thresholds={"exceptional":90,"strong":80,"possible":70,"weak":55}; recommendation="exceptional" if score>=90 else "strong" if score>=80 else "possible" if score>=70 else "weak" if score>=55 else "skip"
    gaps=["Explicit PhD requirement is not supported by canonical education evidence"] if "phd" in text else []
    transition=job.role_family==RoleFamily.product_management; transition_note="Technically aligned PM transition opportunity; canonical evidence supports transferable strategy, collaboration, launch, and AI/data depth, not prior Product Manager employment." if transition else None
    strengths=[v["explanation"] for v in components.values() if v["score"]>=65][:5]
    return FamilyFitResult(role_family=job.role_family,family_fit_score=score,family_component_scores=components,strengths=strengths,gaps=gaps,matched_evidence_ids=sorted(set(evidence_ids))[:12],recommendation=recommendation,career_transition_flag=transition,career_transition_notes=transition_note)
