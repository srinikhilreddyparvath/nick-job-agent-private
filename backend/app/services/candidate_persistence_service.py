import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.onboarding import OnboardingApprovalRequest, OnboardingState
from app.services.evidence_service import EvidenceService
from app.services.profile_service import load_preferences, load_profile


def configured_output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute(): path = (Path(__file__).resolve().parents[2] / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def atomic_json(path: Path, payload) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


class CandidatePersistenceService:
    def __init__(self, settings: Settings | None = None): self.settings = settings or get_settings()
    def state(self) -> OnboardingState:
        profile_path=configured_output_path(self.settings.candidate_profile_path);evidence_path=configured_output_path(self.settings.candidate_evidence_path);preferences_path=configured_output_path(self.settings.candidate_preferences_path)
        configured = all(path.exists() for path in (profile_path,evidence_path,preferences_path))
        profile=load_profile(profile_path)
        evidence=EvidenceService(evidence_path).all()
        preferences=load_preferences(preferences_path)
        return OnboardingState(profile=profile,evidence=evidence,preferences=preferences,configured=configured)
    def approve(self, request: OnboardingApprovalRequest) -> OnboardingState:
        evidence_ids = {item.id for item in request.evidence}
        for item in request.evidence:
            item.verified = True
        for collection in (request.profile.roles, request.profile.experience, request.profile.education, request.profile.skills, request.profile.research, request.profile.publications, request.profile.patents, request.profile.projects, request.profile.technical_domains, request.profile.leadership):
            for item in collection: item.evidence_ids = [value for value in item.evidence_ids if value in evidence_ids]
        atomic_json(configured_output_path(self.settings.candidate_profile_path), request.profile.model_dump(mode="json", exclude_computed_fields=True))
        atomic_json(configured_output_path(self.settings.candidate_evidence_path), [item.model_dump(mode="json") for item in request.evidence])
        atomic_json(configured_output_path(self.settings.candidate_preferences_path), request.preferences.model_dump(mode="json"))
        return OnboardingState(profile=request.profile, evidence=request.evidence, preferences=request.preferences, configured=True)
    def save_preferences(self, preferences):
        atomic_json(configured_output_path(self.settings.candidate_preferences_path), preferences.model_dump(mode="json"));return preferences
