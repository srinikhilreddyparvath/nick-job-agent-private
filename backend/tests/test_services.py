from app.models.job import Job
from app.models.profile import CandidateProfile, JobPreferences, ProfileItem
from app.services.dedupe_service import canonicalize_url, normalize_text
from app.services.scoring_service import DeterministicScoringEngine


def test_url_canonicalization_removes_tracking():
    assert canonicalize_url("HTTPS://Example.com/jobs/1/?utm_source=x&team=ai#top") == "https://example.com/jobs/1?team=ai"


def test_deterministic_score_is_explainable():
    job = Job(external_id="1", source="test", company="Acme", title="Machine Learning Engineer", location="Remote", remote_type="remote", description="Python machine learning research", requirements=["Python"], apply_url="https://example.com/apply", source_url="https://example.com/job")
    profile = CandidateProfile(skills=[ProfileItem(value="Python", evidence=[])], research=[ProfileItem(value="Machine learning research", evidence=[])])
    preferences = JobPreferences(preferred_titles=["Machine Learning Engineer"], preferred_domains=["machine learning"], remote_allowed=True)
    result = DeterministicScoringEngine().score(job, profile, preferences)
    assert result.overall_score >= 70
    assert len(result.component_scores) == 8
    assert result.matched_skills == ["Python"]

