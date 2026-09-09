import re

from app.models.job import Job
from app.models.profile import CandidateProfile, JobPreferences
from app.models.role_family import FamilyFitResult, RoleFamily
from app.services.evidence_service import EvidenceService
from app.services.role_family_service import DeterministicRoleFamilyClassifier
from app.services.scoring_service import DeterministicScoringEngine, terms

# Phrases must occur in BOTH the job and approved candidate evidence.
SIGNALS = {
    RoleFamily.research_ai: ["machine learning", "retrieval", "search ranking", "neural", "pytorch", "tensorflow", "nlp", "llm", "reinforcement learning", "computer vision"],
    RoleFamily.data_science: ["data science", "data scientist", "causal inference", "statistical", "a/b", "experimentation", "python", "sql"],
    RoleFamily.product_management: ["product management", "product manager", "roadmap", "product strategy", "product launch", "user research", "product discovery", "prioritization", "go-to-market"],
    RoleFamily.clinical_research: ["clinical research", "clinical trial", "clinical trials", "oncology", "cancer", "protocol", "participant screening", "regulatory documentation", "irb", "gcp", "research operations"],
    RoleFamily.public_health: ["public health", "epidemiology", "population health", "biostatistics", "health outcomes", "surveillance"],
    RoleFamily.healthcare_operations: ["healthcare", "patient care", "clinical operations", "health services", "patient screening"],
    RoleFamily.research: ["laboratory", "protocol", "study design", "research operations", "publication"],
    RoleFamily.software_engineering: ["software engineering", "software development", "python", "typescript", "javascript", "backend", "frontend", "distributed systems"],
    RoleFamily.information_technology: ["system administration", "linux", "networking", "storage", "infrastructure", "database administration"],
}
ADJACENT = [
    {RoleFamily.clinical_research, RoleFamily.public_health, RoleFamily.healthcare_operations, RoleFamily.research},
    {RoleFamily.research_ai, RoleFamily.data_science, RoleFamily.software_engineering},
]


def contains(text, phrase):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text.casefold()))


def families_for_titles(titles):
    classifier = DeterministicRoleFamilyClassifier()
    return {classifier.classify(Job(external_id="target", source="candidate", company="", title=title,
            apply_url="https://example.test/target", source_url="https://example.test/target")).role_family for title in titles} - {RoleFamily.unknown}


class FamilyScoringEngine:
    def __init__(self, evidence: EvidenceService | None = None):
        self.evidence = evidence or EvidenceService()
        self.baseline = DeterministicScoringEngine()

    def score(self, job: Job, profile: CandidateProfile, preferences: JobPreferences) -> FamilyFitResult:
        baseline = self.baseline.score(job, profile, preferences)
        family = DeterministicRoleFamilyClassifier().classify(job).role_family
        job.role_family = family
        targets = families_for_titles(preferences.preferred_titles)
        background = families_for_titles([x.value for x in profile.roles] + [x.details.get("title", x.value) for x in profile.experience])
        items = [x for group in (profile.roles, profile.experience, profile.skills, profile.research, profile.projects,
                 profile.technical_domains, profile.education, profile.publications, profile.leadership) for x in group]
        if profile.professional_summary: items.append(profile.professional_summary)
        allowed = {value for item in items for value in item.evidence_ids}
        evidence = [x for x in self.evidence.all() if x.verified and x.id in allowed
                    and (not profile.candidate_profile_id or (x.candidate_profile_id == profile.candidate_profile_id
                         and x.candidate_profile_version == profile.profile_version))]
        candidate_text = " ".join(x.statement + " " + " ".join(x.skills + x.domains) for x in evidence).casefold()
        for category, signals in SIGNALS.items():
            if sum(contains(candidate_text, signal) for signal in signals) >= 3:
                background.add(category)
        intended = targets or background
        text = " ".join([job.title, job.description, *job.requirements, *job.preferred_qualifications]).casefold()
        signals = SIGNALS.get(family, [])
        hits = [signal for signal in signals if contains(text, signal) and contains(candidate_text, signal)]
        all_job_signals = {signal for values in SIGNALS.values() for signal in values if contains(text, signal)}
        transferable = [signal for signal in all_job_signals if contains(candidate_text, signal)]
        ids = [x.id for x in evidence if any(contains(x.statement + " " + " ".join(x.skills + x.domains), signal) for signal in transferable)]
        aligned = family in intended
        adjacent = any(family in group and bool(intended & group) for group in ADJACENT)
        transition = bool(targets and family in targets and family not in background)
        title_terms = terms([job.title])
        title_alignment = max((len(title_terms & terms([title])) / max(1, len(title_terms | terms([title])))
                               for title in preferences.preferred_titles), default=0)
        if family == RoleFamily.unknown: aligned = title_alignment >= .5
        role_score = 100 if aligned else 65 if adjacent else 35 if family == RoleFamily.unknown else 0
        evidence_score = min(100, len(hits) * 25)
        score = round(role_score * .55 + evidence_score * .35 + baseline.overall_score * .10, 1)
        # This cap survives semantic blending and freshness bonuses downstream.
        cap = 100 if aligned and len(hits) >= 3 else 79 if aligned else 74 if adjacent else 59 if family == RoleFamily.unknown else 35
        if transition and len(hits) < 3: cap = min(cap, 69)
        score = min(score, cap)
        components = {
            "target_role_alignment": {"score": role_score, "weight": .55, "explanation": "Matches reviewed target family" if aligned else "Adjacent career family" if adjacent else "Career family is outside the candidate's targets and demonstrated background"},
            "grounded_domain_evidence": {"score": evidence_score, "weight": .35, "explanation": "Verified candidate evidence matches: " + ", ".join(hits) if hits else "No verified domain-specific evidence match"},
            "candidate_fit": {"score": baseline.overall_score, "weight": .10, "explanation": "Candidate skills and configured constraints"},
            "role_family_gate": {"score": cap, "weight": 1, "explanation": "Maximum opportunity score allowed by career-family and evidence alignment"},
        }
        strengths = [components["grounded_domain_evidence"]["explanation"]] if hits else []
        gaps = []
        if not aligned: gaps.append(components["target_role_alignment"]["explanation"])
        missing = sorted(signal for signal in all_job_signals if signal not in transferable)
        if missing: gaps.append("No verified candidate evidence for: " + ", ".join(missing[:5]))
        if not hits: gaps.append("Domain-specific experience is not established in approved evidence")
        if "phd" in text and not any("phd" in x.value.lower() or "ph.d" in x.value.lower() for x in profile.education):
            gaps.append("Explicit PhD requirement is not supported by canonical education evidence")
        recommendation = "exceptional" if score >= 90 else "strong" if score >= 80 else "possible" if score >= 70 else "weak" if score >= 55 else "skip"
        return FamilyFitResult(role_family=family, family_fit_score=score, family_component_scores=components,
            strengths=strengths, gaps=gaps, matched_evidence_ids=sorted(set(ids)), recommendation=recommendation,
            career_transition_flag=transition, career_transition_notes="Explicitly targeted career transition; review transferable evidence and missing domain experience." if transition else None)
