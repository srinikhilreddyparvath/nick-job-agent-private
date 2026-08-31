from pathlib import Path

from app.models.profile import CandidateProfile


PROFILE_PATH = Path(__file__).resolve().parents[3] / "data" / "profile.example.json"


def load_profile(path: Path | None = None) -> CandidateProfile:
    source = path or PROFILE_PATH
    return CandidateProfile.model_validate_json(source.read_text(encoding="utf-8")) if source.exists() else CandidateProfile()
