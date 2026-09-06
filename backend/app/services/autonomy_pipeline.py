from sqlalchemy import select
from app.core.config import get_settings
from app.db.models import ApplicationPackageRecord,JobRecord
from app.models.application_package import PackageGenerateRequest
from app.services.application_package_service import ApplicationPackageService
from app.services.application_queue_service import ApplicationQueueService
from app.services.llm_service import configured_llm_service
from app.services.research_service import ResearchService
from app.services.runtime_service import RuntimeControlService
from app.services.semantic_analysis_service import SemanticAnalysisService
class AutonomyPipelineService:
 """Bounded post-discovery preparation. It is inert unless LLM and auto-submit are explicitly enabled."""
 def run(self,db,limit=5):
  settings=get_settings();allowed,reason=RuntimeControlService().auto_submit_allowed(db)
  if not settings.llm_enabled or not allowed:return {"status":"disabled","reason":reason or "LLM_DISABLED","prepared":0}
  jobs=db.scalars(select(JobRecord).where(JobRecord.role_family.in_(["RESEARCH_AI","DATA_SCIENCE","PRODUCT_MANAGEMENT"]),JobRecord.posting_status!="CLOSED").order_by(JobRecord.discovered_at.desc()).limit(limit)).all();prepared=0;errors=[]
  llm=configured_llm_service(settings=settings)
  for job in jobs:
   try:
    SemanticAnalysisService(llm,settings=settings).analyze(db,job.id)
    ResearchService(llm,settings=settings).research(db,job.id)
    package=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job.id))
    service=ApplicationPackageService(llm,settings=settings)
    if not package:service.generate(db,job.id,PackageGenerateRequest())
    reviewed=service.review(db,job.id)
    if reviewed.package and reviewed.package.review_status=="PASS" and not reviewed.package.review_findings and not any(answer.requires_human_review for answer in reviewed.package.application_answers):
     service.approve(db,job.id,False);ApplicationQueueService().enqueue(db,job.id);prepared+=1
   except Exception as exc:errors.append({"job_id":job.id,"error":type(exc).__name__})
  return {"status":"completed_with_errors" if errors else "completed","prepared":prepared,"errors":errors}
