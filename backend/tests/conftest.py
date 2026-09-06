import os
from pathlib import Path
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_nick_job_agent.db"
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client: yield test_client
