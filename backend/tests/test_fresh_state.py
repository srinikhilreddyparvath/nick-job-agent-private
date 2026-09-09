from pathlib import Path

from app.core.config import Settings
from app.db.database import SessionLocal
from app.db.models import JobSourceRecord
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.local_state_service import LocalStateService
from app.services.profile_service import load_profile


def configured(tmp_path):
    return Settings(candidate_profile_path=str(tmp_path/"profile.local.json"),candidate_evidence_path=str(tmp_path/"evidence.local.json"),candidate_preferences_path=str(tmp_path/"preferences.local.json"),candidate_answer_bank_path=str(tmp_path/"answer.local.json"),candidate_application_policy_path=str(tmp_path/"policy.local.json"),candidate_private_storage_path=str(tmp_path/"private"),artifact_storage_path=str(tmp_path/"artifacts"),demo_mode=False)


def test_missing_local_profile_does_not_fall_back_to_example(tmp_path):
    settings=configured(tmp_path)
    assert CandidatePersistenceService(settings).state().configured is False
    assert load_profile(Path(settings.candidate_profile_path)).identity.display_name is None


def test_reset_clears_generated_state_but_preserves_environment_and_examples(tmp_path):
    settings=configured(tmp_path);db=SessionLocal()
    for filename in (settings.candidate_profile_path,settings.candidate_evidence_path,settings.candidate_preferences_path):Path(filename).write_text("{}" if "evidence" not in filename else "[]",encoding="utf-8")
    private=Path(settings.candidate_private_storage_path);private.mkdir();(private/"resume.txt").write_text("fictional",encoding="utf-8")
    env=tmp_path/".env";example=tmp_path/"profile.example.json";env.write_text("SECRET=preserved",encoding="utf-8");example.write_text("{}",encoding="utf-8")
    db.add(JobSourceRecord(company="Old Source",ats_type="greenhouse",board_identifier="old"));db.commit()
    LocalStateService(settings).reset(db,"RESET ROLECALL")
    assert not Path(settings.candidate_profile_path).exists() and not (private/"resume.txt").exists()
    assert db.query(JobSourceRecord).count()==0 and env.exists() and example.exists()
    assert CandidatePersistenceService(settings).state().configured is False
    db.close()
