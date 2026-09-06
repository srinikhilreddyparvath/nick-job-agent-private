import json
from pathlib import Path
from time import perf_counter
from datetime import datetime,timezone
from sqlalchemy.orm import Session

from app.agents.fit import FitAgent
from app.connectors import CONNECTORS
from app.db.models import JobSourceRecord,ScanRunRecord
from app.models.profile import CandidateProfile,JobPreferences
from app.services.profile_service import load_profile,load_preferences
from app.services.dedupe_service import DedupeService
from app.services.filter_service import JobFilterService
from app.services.job_service import JobService
from app.services.scoring_service import DeterministicScoringEngine
from app.services.role_family_service import DeterministicRoleFamilyClassifier
from app.services.family_scoring_service import FamilyScoringEngine

class ScanOrchestrator:
    def __init__(self,connectors:dict|None=None):
        self.connectors=connectors or CONNECTORS; self.jobs=JobService(); self.dedupe=DedupeService(); self.filters=JobFilterService(); self.scorer=FitAgent(DeterministicScoringEngine())
        self.profile=load_profile();self.preferences=load_preferences();self.classifier=DeterministicRoleFamilyClassifier();self.family_scorer=FamilyScoringEngine()
    def scan(self,db:Session,sources:list[JobSourceRecord])->ScanRunRecord:
        started=perf_counter(); run=ScanRunRecord(status="running",source_count=len(sources)); db.add(run); db.commit(); db.refresh(run)
        bands={"exceptional":0,"strong":0,"possible":0,"weak":0,"skip":0}; errors=[];by_source={};by_family={"RESEARCH_AI":0,"DATA_SCIENCE":0,"PRODUCT_MANAGEMENT":0,"UNKNOWN":0}
        for source in sources:
            source.last_scanned_at=datetime.now(timezone.utc)
            try:
                connector_type=self.connectors.get(source.ats_type)
                if connector_type is None: raise ValueError(f"Connector {source.ats_type} is not active")
                fetched=connector_type().fetch_jobs(source.board_identifier,source.company); run.jobs_fetched+=len(fetched);by_source[source.ats_type]=by_source.get(source.ats_type,0)+len(fetched)
                for job in fetched:
                    classification=self.classifier.classify(job);job.role_family=classification.role_family;job.role_family_confidence=classification.confidence;job.role_family_reasons=classification.reasons;by_family[classification.role_family.value]+=1
                    if not self.filters.evaluate(job,self.preferences).passes: run.jobs_filtered+=1; continue
                    duplicate=self.dedupe.find_duplicate(db,job)
                    if duplicate:self.dedupe.record_alternate(db,duplicate,job);run.jobs_deduplicated+=1;run.duplicates_across_sources+=int(duplicate.source!=job.source);continue
                    record=self.jobs.create(db,job); result=self.scorer.evaluate(job,self.profile,self.preferences); self.jobs.save_score(db,record.id,result);family=self.family_scorer.score(job,self.profile,self.preferences);self.jobs.save_family_fit(db,record.id,classification,family); run.jobs_added+=1; run.jobs_scored+=1; bands[family.recommendation]+=1
                source.last_success_at=datetime.now(timezone.utc); source.last_error=None; source.jobs_discovered_total+=len(fetched); run.successful_source_count+=1
            except Exception as exc:
                source.last_error=str(exc); run.failed_source_count+=1; errors.append({"source_id":source.id,"company":source.company,"error":str(exc)})
            db.add(source); db.commit()
        run.status="completed_with_errors" if errors and run.successful_source_count else "failed" if errors else "completed"; run.completed_at=datetime.now(timezone.utc); run.errors_json=errors; run.duration_seconds=round(perf_counter()-started,3)
        run.exceptional_count=bands["exceptional"]; run.strong_count=bands["strong"]; run.possible_count=bands["possible"]; run.weak_count=bands["weak"]; run.skip_count=bands["skip"]
        run.jobs_by_source_type=by_source;run.jobs_by_role_family=by_family
        db.add(run); db.commit(); db.refresh(run); return run
