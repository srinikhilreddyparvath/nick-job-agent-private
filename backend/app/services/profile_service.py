from pathlib import Path

from app.core.config import get_settings
from app.models.profile import CandidateApplicationPolicy, CandidateProfile, JobPreferences


DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _configured_path(value: str, fallback: str | None = None) -> Path:
    configured = Path(value)
    if not configured.is_absolute():
        configured = (Path(__file__).resolve().parents[2] / configured).resolve()
    if configured.exists():return configured
    if fallback and get_settings().demo_mode:return DATA_DIR / fallback
    return configured


def load_profile(path: Path | None = None) -> CandidateProfile:
    if path is None:
        from app.services.candidate_context_service import read_bundle
        bundle = read_bundle()
        if bundle: return CandidateProfile.model_validate(bundle["profile"])
    source = path or _configured_path(get_settings().candidate_profile_path, "profile.example.json")
    return CandidateProfile.model_validate_json(source.read_text(encoding="utf-8")) if source.exists() else CandidateProfile()


def load_preferences(path: Path | None = None) -> JobPreferences:
    if path is None:
        from app.services.candidate_context_service import read_bundle
        bundle = read_bundle()
        if bundle: return JobPreferences.model_validate(bundle["preferences"])
    source = path or _configured_path(get_settings().candidate_preferences_path, "preferences.example.json")
    return JobPreferences.model_validate_json(source.read_text(encoding="utf-8")) if source.exists() else JobPreferences()


def load_application_policy(path: Path | None = None) -> CandidateApplicationPolicy:
    from app.services.candidate_context_service import read_bundle
    if path is None and read_bundle(): return CandidateApplicationPolicy()
    source = path or _configured_path(get_settings().candidate_application_policy_path, "application_policy.example.json")
    return CandidateApplicationPolicy.model_validate_json(source.read_text(encoding="utf-8")) if source.exists() else CandidateApplicationPolicy()
