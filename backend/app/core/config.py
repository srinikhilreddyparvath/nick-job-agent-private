from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Nick Job Agent"
    database_url: str = "sqlite:///./nick_job_agent.db"
    cors_origins: str = "http://localhost:3000"
    http_timeout_seconds: float = 20.0
    connector_user_agent: str = "NickJobAgent/0.1 (personal job discovery)"
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
    llm_provider: str = ""
    llm_model: str = ""
    review_llm_provider: str = ""
    review_llm_model: str = ""
    embedding_provider: str = "mock"
    embedding_model: str = "hash-embedding-v1"
    llm_max_agent_steps: int = 6
    llm_max_retries: int = 1
    llm_max_tokens: int = 3000
    llm_timeout_seconds: float = 45
    llm_analysis_threshold: float = 60
    llm_role_fallback_threshold: float = 0.72
    llm_max_semantic_analyses_per_scan: int = 10
    llm_max_research_pages_per_job: int = 5
    llm_daily_budget_usd: float = 5
    llm_input_cost_per_million: float = 0
    llm_output_cost_per_million: float = 0
    blend_deterministic_weight: float = 0.45
    blend_semantic_weight: float = 0.55

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
