import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import AgentRunRecord, EvidenceEmbeddingRecord, JobFeedbackRecord, JobScoreRecord, SemanticAnalysisRecord
from app.models.job import Job
from app.models.policy import ClaimValidationRequest
from app.models.semantic import ResearchSource, SemanticFitReport, SemanticRoleClassification
from app.services.agent_executor import AgentStepLimitError, BoundedAgentExecutor,BoundedLLMToolExecutor
from app.services.claim_validator import EvidenceClaimValidator
from app.services.embedding_service import EmbeddingError, EmbeddingProvider, EmbeddingService, HashEmbeddingProvider
from app.services.evaluation_service import RankingEvaluationService
from app.services.evidence_service import EvidenceService
from app.services.llm_service import LLMError, LLMProvider, LLMService, MockLLMProvider
from app.services.research_service import ResearchService, SuppliedDataResearchProvider
from app.services.semantic_analysis_service import SemanticAnalysisService
from app.services.semantic_classifier import RoleClassificationPolicy, SemanticRoleFamilyClassifier
from app.services.semantic_evidence_service import SemanticEvidenceIndex
from app.services.tool_registry import AgentTool, ToolRegistry


def saved_job(client,title="Applied Scientist, AI Evaluation"):
    response=client.post("/jobs/ingest-text",json={"source_url":"https://public.example/jobs/phase3","company":"Example AI","title":title,"location":"San Francisco, CA","job_description_text":"Applied machine learning research, model evaluation, ranking experiments, Python, and production ML systems."})
    assert response.status_code==200
    return response.json()["job"]


def test_provider_abstraction_mock_and_structured_validation():
    service=LLMService(MockLLMProvider())
    result,response=service.generate_structured("system",json.dumps({"title":"Unusual role"}),SemanticRoleClassification)
    assert result.role_family=="UNKNOWN" and response.provider=="mock"
    broken=LLMService(MockLLMProvider(responses={"SemanticRoleClassification":{"role_family":"INVALID"}}))
    with pytest.raises(LLMError):broken.generate_structured("system","{}",SemanticRoleClassification)


def test_structured_output_drops_empty_only_for_defaulted_metadata():
    valid={"job_id":1,"role_family":"RESEARCH_AI","semantic_fit_score":80,"confidence":.8,"recommended_action":"review","reasoning_summary":"Grounded summary","created_at":""}
    report,_=LLMService(MockLLMProvider(responses={"SemanticFitReport":valid})).generate_structured("system","{}",SemanticFitReport)
    assert report.created_at is not None
    invalid={**valid,"reasoning_summary":""};invalid.pop("created_at")
    report,_=LLMService(MockLLMProvider(responses={"SemanticFitReport":invalid})).generate_structured("system","{}",SemanticFitReport)
    assert report.reasoning_summary==""


def test_prompt_versions_are_explicit():
    from app.prompts.fit_analysis_v1 import VERSION as fit
    from app.prompts.research_agent_v1 import VERSION as research
    from app.prompts.role_classifier_v1 import VERSION as classifier
    assert (fit,research,classifier)==("fit_analysis_v1","research_agent_v1","role-classifier-v2")


def test_embedding_service_persistence_semantic_and_hybrid_retrieval():
    service=EmbeddingService(HashEmbeddingProvider());vector=service.embed_text("ranking evaluation")
    assert len(vector.vector)==128 and vector.provider=="mock"
    with SessionLocal() as db:
        index=SemanticEvidenceIndex(embeddings=service);status=index.reindex(db)
        expected=len(EvidenceService().all());assert status["indexed"]==expected and db.query(EvidenceEmbeddingRecord).count()==expected
        semantic=index.search(db,"production ranking evaluation",limit=5)
        hybrid=EvidenceService().search_hybrid(db,"cold start ranking",limit=5,embedding_service=service)
        assert semantic and hybrid and all(x.evidence_id for x in hybrid)


def test_embedding_failure_falls_back_to_deterministic():
    class Broken(EmbeddingProvider):
        name="broken";model="broken"
        def embed_batch(self,texts):raise EmbeddingError("offline")
    with SessionLocal() as db:
        evidence=EvidenceService();assert evidence.search_semantic(db,"ranking",embedding_service=EmbeddingService(Broken()))==[]
        assert evidence.search_hybrid(db,"ranking evaluation",embedding_service=EmbeddingService(Broken()))


def test_semantic_classifier_fallback_and_deterministic_precedence():
    ambiguous=Job(external_id="1",source="test",company="X",title="AI Strategy Lead",description="Cross-functional AI research and product experimentation",apply_url="https://x.test/1",source_url="https://x.test/1")
    semantic=SemanticRoleFamilyClassifier(LLMService(MockLLMProvider(responses={"SemanticRoleClassification":{"role_family":"PRODUCT_MANAGEMENT","confidence":.9,"reasoning":"Product strategy signals","signals":["strategy"]}})))
    resolved=RoleClassificationPolicy(semantic).classify(ambiguous);assert resolved.semantic_family=="PRODUCT_MANAGEMENT" and resolved.classification_resolution_method=="semantic_fallback"
    obvious=Job(external_id="2",source="test",company="X",title="Senior Data Scientist, Experimentation",description="Statistical data science experimentation and causal measurement",apply_url="https://x.test/2",source_url="https://x.test/2")
    resolved=RoleClassificationPolicy(semantic).classify(obvious);assert resolved.classification_resolution_method=="deterministic_precedence" and resolved.semantic_family is None


def test_claim_validator_supported_and_unsupported():
    validator=EvidenceClaimValidator();record=EvidenceService().get_by_id("EXPERIENCE_001");supported=validator.validate(ClaimValidationRequest(generated_claim=record.statement,supporting_evidence_ids=[record.id]));unsupported=validator.validate(ClaimValidationRequest(generated_claim="Led quantum computing research",supporting_evidence_ids=[]))
    assert supported.support_status in {"supported","partially_supported"};assert unsupported.support_status=="unsupported" and unsupported.action=="remove_or_rephrase_as_gap"


def test_gap_validator_removes_claims_contradicted_by_canonical_evidence():
    kept,removed=EvidenceClaimValidator().filter_contradicted_gaps(["No verified Python evidence.","No verified publication record."])
    assert removed==["No verified Python evidence."] and kept==["No verified publication record."]


def test_semantic_fit_grounding_persistence_cache_and_agent_trace(client):
    job=saved_job(client);first=client.post(f"/jobs/{job['id']}/analyze",json={"use_mock":True});assert first.status_code==200
    body=first.json();assert body["status"]=="completed" and body["report"]["deterministic_score"] is not None
    assert all(item["evidence_ids"] for item in body["report"]["strengths"])
    second=client.post(f"/jobs/{job['id']}/analyze",json={"use_mock":True}).json();assert second["report"]["cache_hit"] is True
    runs=client.get(f"/jobs/{job['id']}/agent-runs").json();assert runs[0]["provider"]=="mock" and runs[0]["prompt_version"]=="fit_analysis_v1" and runs[0]["actions_json"]
    with SessionLocal() as db:assert db.query(SemanticAnalysisRecord).count()==1


def test_evidence_version_changes_analysis_fingerprint(client):
    job=saved_job(client);service=SemanticAnalysisService(LLMService(MockLLMProvider()))
    record=__import__("app.services.job_service",fromlist=["JobService"]).JobService().get(SessionLocal(),job["id"])
    schema=__import__("app.services.job_service",fromlist=["JobService"]).JobService().to_schema(record)
    assert service.fingerprint(schema,"evidence-a")!=service.fingerprint(schema,"evidence-b")


def test_research_agent_attribution_and_permissions(client):
    job=saved_job(client,"Research Engineer, Agents");source=ResearchSource(url=job["source_url"],title="Public job posting",source_type="job_posting",excerpt="Public role details")
    with SessionLocal() as db:
        result=ResearchService(LLMService(MockLLMProvider()),SuppliedDataResearchProvider([source])).research(db,job["id"])
        assert result.status=="completed" and result.report.source_citations[0].url==job["source_url"]
        run=db.get(AgentRunRecord,result.agent_run_id);assert run.sources_used==[job["source_url"]] and run.prompt_version=="research_agent_v1"


def test_tool_permissions_and_max_step_enforcement():
    class Input(BaseModel):value:int
    registry=ToolRegistry();registry.register(AgentTool("fit_only","test",Input,None,{"fit"},lambda value:{"value":value}))
    assert registry.invoke("fit","fit_only",{"value":2})=={"value":2}
    with pytest.raises(PermissionError):registry.invoke("research","fit_only",{"value":2})
    settings=get_settings().model_copy(update={"llm_max_agent_steps":2});executor=BoundedAgentExecutor(registry,settings)
    with pytest.raises(AgentStepLimitError):executor.execute("fit",lambda state,step:{"tool_call":{"name":"fit_only","arguments":{"value":step}}},{})


def test_mock_model_selects_only_registered_tool_in_bounded_loop():
    class Input(BaseModel):value:int
    registry=ToolRegistry();registry.register(AgentTool("fit_only","test",Input,None,{"fit"},lambda value:{"value":value}))
    _,actions,state,usage,_=BoundedLLMToolExecutor(registry,LLMService(MockLLMProvider())).execute("fit","Use the permitted test tool",{},["fit_only"],{"fit_only":{"value":7}})
    assert actions[0]["tool"]=="fit_only" and state["tool_outputs"][0]["output"]=={"value":7} and usage.input_tokens>0


def test_model_selected_single_tool_can_terminate_for_fixed_agent_stage():
    class Input(BaseModel):value:int
    registry=ToolRegistry();registry.register(AgentTool("fit_only","test",Input,None,{"fit"},lambda value:{"value":value}))
    final,actions,state,_,_=BoundedLLMToolExecutor(registry,LLMService(MockLLMProvider())).execute("fit","Retrieve once",{},["fit_only"],{"fit_only":{"value":3}},stop_after_tool=True)
    assert final=={"tool_completed":"fit_only"} and len(actions)==1 and state["tool_outputs"][0]["output"]=={"value":3}


def test_model_cannot_override_application_validated_tool_arguments():
    class Input(BaseModel):value:int
    provider=MockLLMProvider(responses={"AgentToolDecision":{"action":"tool","tool_name":"fit_only","arguments":{"value":999}}});registry=ToolRegistry();registry.register(AgentTool("fit_only","test",Input,None,{"fit"},lambda value:{"value":value}))
    _,actions,state,_,_=BoundedLLMToolExecutor(registry,LLMService(provider)).execute("fit","Retrieve once",{},["fit_only"],{"fit_only":{"value":4}},stop_after_tool=True)
    assert actions[0]["arguments"]=={"value":4} and state["tool_outputs"][0]["output"]=={"value":4}


def test_provider_failure_and_cost_limit_return_deterministic_fallback(client):
    job=saved_job(client)
    class BrokenProvider(LLMProvider):
        name="broken";model="broken"
        def generate(self,*args,**kwargs):raise LLMError("provider unavailable")
    with SessionLocal() as db:
        failed=SemanticAnalysisService(LLMService(BrokenProvider())).analyze(db,job["id"]);assert failed.status=="fallback_deterministic" and failed.deterministic_score is not None
        settings=get_settings().model_copy(update={"llm_daily_budget_usd":0});limited=SemanticAnalysisService(LLMService(MockLLMProvider(),settings),settings).analyze(db,job["id"],True);assert limited.status=="fallback_deterministic" and "budget" in limited.error.lower()


def test_models_status_reindex_and_mock_research_endpoints(client):
    job=saved_job(client);status=client.get("/models/status");assert status.status_code==200 and status.json()["llm_enabled"] is False
    assert client.post("/evidence/reindex").status_code==200
    research=client.post(f"/jobs/{job['id']}/research",json={"use_mock":True});assert research.status_code==200 and research.json()["report"]["source_citations"]


def test_ranking_evaluation_compares_all_score_families():
    with SessionLocal() as db:
        for index,label in enumerate(["excellent","good","maybe","poor","good"],1):
            job=__import__("app.db.models",fromlist=["JobRecord"]).JobRecord(external_id=str(index),source="eval",company="X",title=f"Role {index}",normalized_title=f"role {index}",location="Remote",remote_type="remote",description="data science",requirements=[],preferred_qualifications=[],apply_url=f"https://x/{index}",canonical_apply_url=f"https://x/{index}",source_url=f"https://x/{index}");db.add(job);db.flush();db.add(JobScoreRecord(job_id=job.id,overall_score=100-index*10,component_scores={},strengths=[],gaps=[],matched_skills=[],missing_skills=[],reasoning_summary="",recommendation="possible"));db.add(SemanticAnalysisRecord(job_id=job.id,fingerprint=f"f{index}",deterministic_score=100-index*10,semantic_score=98-index*9,blended_score=99-index*9.5,report_json={},provider="mock",model="mock",prompt_version="v1",evidence_version="e1"));db.add(JobFeedbackRecord(job_id=job.id,human_label=label))
        db.commit();result=RankingEvaluationService().evaluate(db);assert result.state=="ready" and set(result.metrics)=={"deterministic","semantic","blended"} and "ndcg_at_5" in result.metrics["semantic"]
