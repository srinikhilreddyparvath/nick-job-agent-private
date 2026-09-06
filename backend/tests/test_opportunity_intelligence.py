from datetime import datetime, timezone

from app.models.job import Job, RemoteType
from app.models.opportunity import ConstraintState, GapKind, OpportunityRecommendation, PublicContact
from app.models.profile import JobPreferences
from app.services.opportunity_service import ConstraintEngine, OpportunityScoringService


def opportunity_job(**overrides):
    values = {
        "external_id": "opportunity-1",
        "source": "fixture",
        "company": "Example AI",
        "title": "Machine Learning Engineer",
        "location": "Metro City",
        "remote_type": RemoteType.hybrid,
        "employment_type": "full-time",
        "description": "Search evaluation and ranking systems",
        "apply_url": "https://example.com/jobs/1",
        "source_url": "https://example.com/jobs/1",
        "discovered_at": datetime.now(timezone.utc),
        "fit_score": 68,
        "strengths": ["Ranking evaluation aligns with verified experience."],
        "gaps": ["Deployment scope is unknown."],
        "matched_evidence_ids": ["EXPERIENCE_002"],
    }
    values.update(overrides)
    return Job(**values)


def test_unknown_constraints_are_neutral_not_failures():
    result = ConstraintEngine().evaluate(opportunity_job(salary_max=None), JobPreferences())
    assert result.compensation == ConstraintState.unknown
    assert result.visa == ConstraintState.unknown
    assert result.hard_blockers == []


def test_fit_prioritizes_without_becoming_permission_gate():
    score = OpportunityScoringService().score(opportunity_job(fit_score=58), JobPreferences())
    assert score.recommendation in {OpportunityRecommendation.contact_first, OpportunityRecommendation.apply}
    assert score.recommendation != OpportunityRecommendation.skip


def test_match_reasons_have_evidence_and_gaps_are_typed():
    score = OpportunityScoringService().score(opportunity_job(), JobPreferences())
    assert score.why_you_match[0].evidence_ids == ["EXPERIENCE_002"]
    assert score.real_gaps[0].kind == GapKind.unknown


def test_only_configured_hard_constraint_causes_skip():
    preferences = JobPreferences.model_validate({
        "compensation": {"minimum_base_salary": 200000, "salary_is_hard_filter": True}
    })
    score = OpportunityScoringService().score(opportunity_job(salary_max=150000), preferences)
    assert score.recommendation == OpportunityRecommendation.skip
    assert score.constraints.hard_blockers


def test_public_contact_model_does_not_imply_hiring_manager_verification():
    contact = PublicContact(
        person_name="Jordan Example",
        title="Engineering Leader",
        company="Example AI",
        public_profile_url="https://example.com/team/jordan",
        source_url="https://example.com/team",
        contact_type="LIKELY_TEAM_LEADER",
        relevance_score=75,
        relevance_reason="Public team page lists a related function.",
        confidence=0.7,
    )
    assert contact.verified_hiring_manager is False
