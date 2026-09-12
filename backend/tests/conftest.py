import os
from pathlib import Path
import sys
import tempfile

# Never drop a pre-existing database in the developer's working directory.
_test_storage = tempfile.TemporaryDirectory(prefix="rolecall-pytest-")
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(_test_storage.name) / "tests.db").as_posix()
os.environ["LLM_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-semantic-v1"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODEL"] = "hash-embedding-v1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["CANDIDATE_PROFILE_PATH"] = "../data/profile.example.json"
os.environ["CANDIDATE_PREFERENCES_PATH"] = "../data/preferences.example.json"
os.environ["CANDIDATE_EVIDENCE_PATH"] = "../data/evidence.example.json"
os.environ["CANDIDATE_ANSWER_BANK_PATH"] = "../data/answer_bank.example.json"
os.environ["CANDIDATE_APPLICATION_POLICY_PATH"] = "../data/application_policy.example.json"
os.environ["APPLICATION_MODE"] = "manual"
os.environ["AUTO_SUBMIT_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.database import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def close_test_database():
    yield
    from sqlalchemy.orm import close_all_sessions
    close_all_sessions()
    engine.dispose()
    _test_storage.cleanup()


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    import shutil
    from app.core.config import get_settings
    settings = get_settings()
    root = Path(__file__).resolve().parents[2] / "data"
    for field, filename in (("candidate_profile_path", "profile.example.json"), ("candidate_preferences_path", "preferences.example.json"), ("candidate_evidence_path", "evidence.example.json")):
        target = tmp_path / filename
        shutil.copyfile(root / filename, target)
        monkeypatch.setattr(settings, field, str(target))
    monkeypatch.setattr(settings, "candidate_private_storage_path", str(tmp_path / "private"))
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client: yield test_client
