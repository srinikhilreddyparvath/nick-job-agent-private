import json
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models.onboarding import OnboardingApprovalRequest, OnboardingState
from app.services.evidence_service import EvidenceService
from app.services.profile_service import load_preferences, load_profile
from app.services.candidate_context_service import current_context, state_path


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
        context = current_context(self.settings)
        configured = all(configured_output_path(value).exists() for value in (
            self.settings.candidate_profile_path, self.settings.candidate_evidence_path, self.settings.candidate_preferences_path))
        configured = configured or state_path(self.settings).exists()
        if context.pending:
            from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences
            private = configured_output_path(self.settings.candidate_private_storage_path)
            draft_path = private / "onboarding-draft.json"
            draft = json.loads(draft_path.read_text(encoding="utf-8")) if draft_path.exists() else {}
            marker = state_path(self.settings).with_suffix(".pending.json")
            upload_path = private / "resume-upload.json"
            expected = json.loads((marker if marker.exists() else upload_path).read_text(encoding="utf-8")).get("document_id") if marker.exists() or upload_path.exists() else None
            if draft.get("metadata", {}).get("document_id") != expected: draft = {}
            profile = CandidateProfile.model_validate(draft.get("draft", {}).get("profile", {}))
            if expected: profile.source_document_id = expected
            evidence = [EvidenceRecord.model_validate(x) for x in draft.get("draft", {}).get("evidence", [])]
            return OnboardingState(profile=profile, evidence=evidence, preferences=JobPreferences(preferred_titles=[x.value for x in profile.roles]), configured=False, replacement_pending=True)
        return OnboardingState(profile=context.profile, evidence=list(context.evidence), preferences=context.preferences,
                               configured=configured and not context.pending, replacement_pending=context.pending)

    def approve(self, request: OnboardingApprovalRequest) -> OnboardingState:
        if not request.preferences_reviewed:
            raise ValueError("Review target roles and constraints before approving the profile")
        active = current_context(self.settings)
        previous = OnboardingState(profile=active.profile, evidence=list(active.evidence), preferences=active.preferences, configured=not active.pending)
        replacing = request.profile.candidate_profile_id != previous.profile.candidate_profile_id or not request.profile.candidate_profile_id
        has_previous = bool(previous.evidence or previous.profile.approved_at)
        if replacing and has_previous and not request.confirm_replacement:
            raise ValueError("Confirm replacement of the active candidate profile")
        pending_path = state_path(self.settings).with_suffix(".pending.json")
        legacy_upload = configured_output_path(self.settings.candidate_private_storage_path) / "resume-upload.json"
        if active.pending and (pending_path.exists() or legacy_upload.exists()):
            pending = json.loads((pending_path if pending_path.exists() else legacy_upload).read_text(encoding="utf-8"))
            if request.profile.source_document_id != pending["document_id"]:
                raise ValueError("Review the latest uploaded resume before approval")
        now = datetime.now(timezone.utc)
        profile_id = str(uuid4()) if replacing else previous.profile.candidate_profile_id
        version = 1 if replacing else previous.profile.profile_version + 1
        request.profile.candidate_profile_id = profile_id
        request.profile.profile_version = version
        request.profile.approved_at = now
        remap = {}
        for item in request.evidence:
            if item.candidate_profile_id and (replacing or item.candidate_profile_id != profile_id):
                raise ValueError("Cannot merge evidence from a different candidate")
            old_id = item.id
            new_id = f"{profile_id}:{version}:{len(remap)+1}"
            if old_id in remap:
                raise ValueError("Duplicate evidence identifier")
            remap[old_id] = new_id
            item.id = new_id
            item.candidate_profile_id = profile_id
            item.candidate_profile_version = version
            item.verified = True
        collections = [request.profile.roles, request.profile.experience, request.profile.education, request.profile.skills,
                       request.profile.research, request.profile.publications, request.profile.patents, request.profile.projects,
                       request.profile.technical_domains, request.profile.leadership, [request.profile.identity]]
        if request.profile.professional_summary:
            collections.append([request.profile.professional_summary])
        for collection in collections:
            for item in collection:
                if not set(item.evidence_ids).issubset(remap):
                    raise ValueError("Profile contains evidence outside the approved candidate")
                item.evidence_ids = [remap[value] for value in item.evidence_ids]
        request.preferences.version = 1 if replacing else previous.preferences.version + 1
        request.preferences.provenance = "explicit"
        request.preferences.reviewed_at = now
        bundle = {"profile": request.profile.model_dump(mode="json", exclude_computed_fields=True),
                  "evidence": [item.model_dump(mode="json") for item in request.evidence],
                  "preferences": request.preferences.model_dump(mode="json")}
        # The bundle is the only canonical write: readers cannot see a profile
        # from one approval with evidence/preferences from another approval.
        atomic_json(state_path(self.settings), bundle)
        pending_path.unlink(missing_ok=True)
        return self.state()

    def save_preferences(self, preferences):
        from app.services.candidate_context_service import read_bundle
        bundle = read_bundle(self.settings)
        previous = self.state()
        preferences.version = previous.preferences.version + 1
        preferences.provenance = "explicit"
        preferences.reviewed_at = datetime.now(timezone.utc)
        if bundle:
            bundle["preferences"] = preferences.model_dump(mode="json")
            atomic_json(state_path(self.settings), bundle)
        else:
            atomic_json(configured_output_path(self.settings.candidate_preferences_path), preferences.model_dump(mode="json"))
        return preferences
