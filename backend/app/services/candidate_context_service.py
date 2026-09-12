"""One immutable candidate snapshot per evaluation; never identify an owner by job."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences

EVALUATOR_VERSION = "candidate-fit-v3"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def state_path(settings=None) -> Path:
    settings = settings or get_settings()
    path = Path(settings.candidate_profile_path)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    return path.with_suffix(".state.json")


def read_bundle(settings=None):
    path = state_path(settings)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@dataclass(frozen=True)
class CandidateContext:
    profile: CandidateProfile
    preferences: JobPreferences
    evidence: tuple[EvidenceRecord, ...]
    profile_id: str
    profile_version: int
    preference_version: str
    key: str
    pending: bool = False

    @property
    def evidence_ids(self):
        return {item.id for item in self.evidence if item.verified and
                (not self.profile.candidate_profile_id or (item.candidate_profile_id == self.profile_id
                 and item.candidate_profile_version == self.profile_version))}

    def validate_evidence(self, ids):
        if not set(ids or []).issubset(self.evidence_ids):
            raise ValueError("Evidence does not belong to the evaluated candidate version")

    def ownership(self):
        return dict(candidate_profile_id=self.profile_id, candidate_profile_version=self.profile_version,
                    preference_version=self.preference_version, candidate_context_key=self.key)


def current_context(settings=None) -> CandidateContext:
    from app.services.profile_service import load_profile, load_preferences
    from app.services.evidence_service import EvidenceService
    settings = settings or get_settings()
    bundle = read_bundle(settings)
    if bundle:
        profile = CandidateProfile.model_validate(bundle["profile"])
        preferences = JobPreferences.model_validate(bundle["preferences"])
        evidence = tuple(EvidenceRecord.model_validate(x) for x in bundle["evidence"])
    else:
        def resolve(value):
            path = Path(value)
            return path if path.is_absolute() else (Path(__file__).resolve().parents[2] / path).resolve()
        profile = load_profile(resolve(settings.candidate_profile_path))
        preferences = load_preferences(resolve(settings.candidate_preferences_path))
        evidence = tuple(EvidenceService(resolve(settings.candidate_evidence_path)).all())
    payload = profile.model_dump(mode="json", exclude_computed_fields=True)
    # Legacy files have no reliable historical ownership. This identity scopes
    # NEW evaluations only; no old database values are backfilled with it.
    profile_id = profile.candidate_profile_id or "legacy-" + digest(payload)[:32]
    version = profile.profile_version or 1
    preference_version = digest(preferences.model_dump(mode="json"))
    pending = state_path(settings).with_suffix(".pending.json").exists()
    if not bundle:
        private = Path(settings.candidate_private_storage_path)
        if not private.is_absolute(): private = (Path(__file__).resolve().parents[2] / private).resolve()
        upload_path = private / "resume-upload.json"
        if upload_path.exists() and evidence:
            uploaded = json.loads(upload_path.read_text(encoding="utf-8")).get("document_id")
            documents = {x.source_document for x in evidence if x.source_document}
            if uploaded and documents and not any(uploaded in name for name in documents): pending = True
    key = digest({"profile_id": profile_id, "version": version, "profile": payload,
                  "preferences": preference_version, "evidence": [x.model_dump(mode="json", exclude={"created_at", "updated_at"}) for x in evidence],
                  "evaluation_schema": EVALUATOR_VERSION,
                  "scoring_weights": settings.scoring_weights,
                  "thresholds": settings.recommendation_thresholds,
                  "pending": pending})
    return CandidateContext(profile, preferences, evidence, profile_id, version, preference_version, key, pending)


def assert_current(context):
    if context.key != current_context().key:
        raise ValueError("Candidate changed during evaluation; rerun Find Jobs")


def job_version(job):
    def value(name):
        item = getattr(job, name, None)
        return getattr(item, "value", item)
    return digest({name: value(name) for name in (
        "id", "source", "external_id", "company", "title", "description", "requirements", "preferred_qualifications",
        "location", "remote_type", "employment_type", "salary_min", "salary_max", "salary_currency")})
