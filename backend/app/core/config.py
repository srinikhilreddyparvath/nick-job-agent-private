from functools import lru_cache

from pydantic import SecretStr,model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Career Intelligence Agent"
    database_url: str = "sqlite:///./nick_job_agent.db"
    cors_origins: str = "http://localhost:3000"
    http_timeout_seconds: float = 20.0
    connector_user_agent: str = "CareerIntelligenceAgent/0.1 (personal job discovery)"
    source_scan_frequency_default: str = "manual"
    scoring_role_weight: float = 0.20
    scoring_domain_weight: float = 0.20
    scoring_skills_weight: float = 0.15
    scoring_experience_weight: float = 0.15
    scoring_research_weight: float = 0.15
    scoring_seniority_weight: float = 0.05
    scoring_location_weight: float = 0.05
    scoring_compensation_weight: float = 0.05
    recommendation_exceptional_min: float = 90
    recommendation_strong_min: float = 80
    recommendation_possible_min: float = 70
    recommendation_weak_min: float = 55
    llm_enabled: bool = False
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    llm_provider: str = ""
    llm_model: str = ""
    review_llm_provider: str = ""
    review_llm_model: str = ""
    embedding_provider: str = "mock"
    embedding_model: str = "hash-embedding-v1"
    llm_max_agent_steps: int = 6
    llm_max_retries: int = 1
    llm_max_tokens: int = 3000
    application_llm_max_tokens: int = 6000
    resume_extraction_max_tokens: int = 6000
    resume_extraction_timeout_seconds: float = 90
    llm_timeout_seconds: float = 45
    llm_analysis_threshold: float = 60
    llm_role_fallback_threshold: float = 0.72
    llm_max_semantic_analyses_per_scan: int = 10
    llm_max_research_pages_per_job: int = 5
    llm_daily_budget_usd: float = 5
    llm_input_cost_per_million: float = 4.00
    llm_output_cost_per_million: float = 20.00
    embedding_cost_per_million: float = 0.13
    blend_deterministic_weight: float = 0.45
    blend_semantic_weight: float = 0.55
    application_generation_threshold: float = 70
    application_resume_pages: int = 2
    application_mode: str = "manual"
    auto_submit_enabled: bool = False
    auto_apply_daily_cap: int = 25
    auto_apply_company_daily_cap: int = 3
    browser_headless: bool = True
    browser_timeout_seconds: float = 30
    browser_max_retries: int = 2
    browser_upload_in_dry_run: bool = False
    environment: str = "development"
    encryption_key: SecretStr | None = None
    auto_apply_paused: bool = False
    auto_submit_allow_without_receipt: bool = False
    auto_apply_min_interval_seconds: int = 120
    discovery_interval_minutes: int = 240
    queue_interval_minutes: int = 5
    morning_report_hour_local: int = 8
    timezone: str = "America/Los_Angeles"
    worker_lease_seconds: int = 300
    worker_poll_seconds: int = 30
    daily_ai_budget: float = 5.0
    web_discovery_enabled: bool = False
    web_discovery_queries_per_run: int = 3
    web_discovery_max_urls_per_run: int = 20
    web_discovery_daily_budget: float = 1.0
    artifact_storage_backend: str = "local"
    artifact_storage_path: str = "../generated"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    public_base_url: str = ""
    candidate_profile_path: str = "../data/profile.local.json"
    candidate_preferences_path: str = "../data/preferences.local.json"
    candidate_evidence_path: str = "../data/evidence.local.json"
    candidate_answer_bank_path: str = "../data/answer_bank.local.json"
    candidate_application_policy_path: str = "../data/application_policy.local.json"
    candidate_private_storage_path: str = "../data/private"
    resume_max_upload_bytes: int = 10 * 1024 * 1024
    demo_mode: bool = False
    discovery_max_sources_per_run: int = 20
    dashboard_max_jobs_per_company: int = 3
    starter_discovery_catalog_path: str = "../data/discovery_sources.example.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_configuration(self):
        if self.llm_enabled:
            if not self.llm_provider or not self.llm_model:raise ValueError("LLM_ENABLED=true requires LLM_PROVIDER and LLM_MODEL")
            if self.llm_provider=="openai" and not self.openai_api_key:raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
            if self.llm_provider=="anthropic" and not self.anthropic_api_key:raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        if self.application_mode not in {"manual","fill_only","auto_submit"}:raise ValueError("APPLICATION_MODE must be manual, fill_only, or auto_submit")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def scoring_weights(self) -> dict[str, float]:
        weights={"role_alignment":self.scoring_role_weight,"technical_domain_alignment":self.scoring_domain_weight,"skills_alignment":self.scoring_skills_weight,"experience_alignment":self.scoring_experience_weight,"research_alignment":self.scoring_research_weight,"seniority_alignment":self.scoring_seniority_weight,"location_alignment":self.scoring_location_weight,"compensation_alignment":self.scoring_compensation_weight}
        if abs(sum(weights.values())-1.0)>1e-9: raise ValueError("Scoring weights must total 1.0")
        return weights

    @property
    def recommendation_thresholds(self) -> dict[str,float]:
        return {"exceptional":self.recommendation_exceptional_min,"strong":self.recommendation_strong_min,"possible":self.recommendation_possible_min,"weak":self.recommendation_weak_min}

    @property
    def blend_weights(self)->dict[str,float]:
        total=self.blend_deterministic_weight+self.blend_semantic_weight
        if abs(total-1.0)>1e-9: raise ValueError("Blend weights must total 1.0")
        return {"deterministic":self.blend_deterministic_weight,"semantic":self.blend_semantic_weight}


@lru_cache
def get_settings() -> Settings:
    return Settings()
