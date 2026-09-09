from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sqlalchemy import delete, func, select

from app.core.config import Settings, get_settings
from app.db.models import CompanyRecord, CompanyResearchRecord, ContactDiscoveryRunRecord, ContactRecord, JobRecord, JobSourceRecord
from app.models.contact import ContactCandidate, ContactList, ContactRead, OutreachPreview, RelationshipStatus
from app.services.contact_discovery_adapters import CompanyPublicPagesAdapter
from app.services.evidence_service import EvidenceService


EXECUTIVE = {"ceo","chief executive","president","cfo","chief financial","chief marketing","chief operating","founder"}
RECRUITER = {"recruiter","talent acquisition","talent partner","sourcer"}
SENIOR = {"senior","staff","principal","lead"}
STOP = {"and","the","of","for","to","a","an","engineer","engineering","scientist","research","software","machine","learning"}

def tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", value.casefold()) if len(x)>2 and x not in STOP}

def similarity(left: str, right: str) -> float:
    a,b=tokens(left),tokens(right)
    return 0 if not a or not b else 100*len(a&b)/len(a|b)

def context_coverage(job_text: str, contact_terms: str) -> float:
    """Measures how much of a person's explicit team/domain context appears in the job."""
    job_tokens, contact_tokens = tokens(job_text), tokens(contact_terms)
    return 0 if not job_tokens or not contact_tokens else 100 * len(job_tokens & contact_tokens) / len(contact_tokens)


class ContactIntelligenceService:
    """Ranks only evidenced public contacts; it never sends outreach or changes job fit."""
    def __init__(self,settings:Settings|None=None,adapters=None):
        self.settings=settings or get_settings()
        self.adapters=adapters if adapters is not None else [CompanyPublicPagesAdapter(self.settings)]
    def score(self,job:JobRecord,candidate:ContactCandidate)->dict|None:
        if candidate.company.casefold()!=job.company.casefold():return None
        title=candidate.current_title.casefold();is_exec=any(term in title for term in EXECUTIVE)
        if is_exec and not (candidate.company_is_small and candidate.direct_function_ownership):return None
        role=similarity(job.title,candidate.current_title)
        job_text=f"{job.title} {job.description}"
        domain=context_coverage(job_text," ".join(candidate.domains))
        team=context_coverage(job_text,candidate.team or "")
        seniority=90 if any(x in title for x in SENIOR) else 70
        location=similarity(job.location or "",candidate.location or "")
        recruiting=any(term in title for term in RECRUITER)
        if recruiting: seniority=25;role=min(role,30)
        evidence_strength=min(100,35+20*len(candidate.evidence))
        score=.38*role+.24*team+.20*domain+.08*seniority+.04*location+.06*evidence_strength
        if recruiting:
            score*=.72
            if candidate.recruiting_relevance and max(team,domain)>=50:
                score=max(score,float(self.settings.contact_discovery_min_relevance_score))
        if max(role,team,domain)<18 and not candidate.recruiting_relevance:return None
        strongest=max((role,"same or closely related role"),(team,"same team or function"),(domain,"same technical domain"),key=lambda x:x[0])[1]
        reason=f"Public evidence supports a {strongest} connection at {job.company}."
        return {"role_similarity":round(role,1),"team_similarity":round(team,1),"domain_similarity":round(domain,1),"company_match":True,"seniority_usefulness":seniority,"location_relevance":round(location,1),"relevance_score":round(score,1),"relevance_reason":reason}

    @staticmethod
    def _merge(candidates:list[ContactCandidate])->list[ContactCandidate]:
        merged={}
        for candidate in candidates:
            key=(re.sub(r"[^a-z0-9]","",candidate.name.casefold()),candidate.company.casefold())
            current=merged.get(key)
            if current is None:merged[key]=candidate;continue
            evidence={str(item.source_url):item for item in current.evidence}
            evidence.update({str(item.source_url):item for item in candidate.evidence})
            current.evidence=list(evidence.values());current.domains=sorted(set(current.domains+candidate.domains))
            current.relationship_confidence=min(.98,max(current.relationship_confidence,candidate.relationship_confidence)+.05)
            if len(candidate.current_title)>len(current.current_title):current.current_title=candidate.current_title
        return list(merged.values())

    def replace(self,db,job_id:int,candidates:list[ContactCandidate])->ContactList:
        job=db.get(JobRecord,job_id)
        if not job:raise LookupError("Job not found")
        scored=[]
        for candidate in self._merge(candidates):
            result=self.score(job,candidate)
            if result and result["relevance_score"]>=self.settings.contact_discovery_min_relevance_score:scored.append((candidate,result))
        scored.sort(key=lambda item:(-item[1]["relevance_score"],item[0].name.casefold()))
        scored=scored[:self.settings.contact_discovery_max_contacts]
        db.execute(delete(ContactRecord).where(ContactRecord.job_id==job_id))
        for candidate,result in scored:
            db.add(ContactRecord(job_id=job_id,**candidate.model_dump(mode="json",exclude={"evidence"}),evidence=[x.model_dump(mode="json") for x in candidate.evidence],**result))
        db.commit();return self.list(db,job_id)

    def list(self,db,job_id:int,*,cached:bool=False)->ContactList:
        rows=list(db.scalars(select(ContactRecord).where(ContactRecord.job_id==job_id).order_by(ContactRecord.relevance_score.desc(),ContactRecord.id.asc())).all())
        items=[ContactRead(contact_id=row.id,job_id=row.job_id,**{key:getattr(row,key) for key in ContactCandidate.model_fields},role_similarity=row.role_similarity,team_similarity=row.team_similarity,domain_similarity=row.domain_similarity,company_match=row.company_match,seniority_usefulness=row.seniority_usefulness,location_relevance=row.location_relevance,relevance_score=row.relevance_score,relevance_reason=row.relevance_reason,discovered_at=row.discovered_at,last_checked_at=row.last_checked_at) for row in rows]
        run=db.scalar(select(ContactDiscoveryRunRecord).where(ContactDiscoveryRunRecord.job_id==job_id).order_by(ContactDiscoveryRunRecord.id.desc()))
        return ContactList(items=items,message=None if items else "No sufficiently relevant public contacts found yet.",sources_checked=run.sources_checked if run else 0,pages_checked=run.pages_checked if run else 0,candidates_discovered=run.candidates_discovered if run else 0,cached=cached)

    def _seeds(self,db,job:JobRecord)->list[str]:
        seeds=[]
        company=db.scalar(select(CompanyRecord).where(func.lower(CompanyRecord.name)==job.company.casefold()))
        if company:seeds.extend([company.website_url,company.careers_url])
        sources=db.scalars(select(JobSourceRecord).where(func.lower(JobSourceRecord.company)==job.company.casefold())).all()
        for source in sources:seeds.extend([source.careers_url,(source.configuration or {}).get("website_url")])
        research=db.scalar(select(CompanyResearchRecord).where(CompanyResearchRecord.job_id==job.id).order_by(CompanyResearchRecord.id.desc()))
        if research:seeds.extend(item.get("url") for item in research.sources or [] if item.get("url"))
        catalog_path=Path(self.settings.starter_discovery_catalog_path)
        if not catalog_path.is_absolute():catalog_path=(Path(__file__).resolve().parents[2]/catalog_path).resolve()
        if catalog_path.exists():
            for item in json.loads(catalog_path.read_text(encoding="utf-8")):
                if item.get("company","").casefold()==job.company.casefold():seeds.append(item.get("website_url"))
        return list(dict.fromkeys(value for value in seeds if value))

    def discover(self,db,job_id:int,*,force:bool=False)->ContactList:
        job=db.get(JobRecord,job_id)
        if not job:raise LookupError("Job not found")
        latest=db.scalar(select(ContactDiscoveryRunRecord).where(ContactDiscoveryRunRecord.job_id==job_id).order_by(ContactDiscoveryRunRecord.id.desc()))
        cutoff=datetime.now(timezone.utc)-timedelta(hours=self.settings.contact_discovery_freshness_hours)
        checked_at = latest.last_checked_at if latest else None
        if checked_at and checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        if latest and latest.status in {"COMPLETED","COMPLETED_WITH_ERRORS"} and checked_at and checked_at >= cutoff and not force:
            return self.list(db,job_id,cached=True)
        run=ContactDiscoveryRunRecord(job_id=job_id,status="RUNNING");db.add(run);db.commit();db.refresh(run)
        candidates=[];errors=[];pages=sources=0;seeds=self._seeds(db,job)
        for adapter in self.adapters:
            try:
                result=adapter.discover(job.company,seeds);candidates.extend(result.candidates);errors.extend(result.errors);pages+=result.pages_checked;sources+=result.sources_checked
            except Exception as exc:errors.append({"source":getattr(adapter,"name","unknown"),"category":type(exc).__name__})
        contacts=self.replace(db,job_id,candidates)
        run.status="COMPLETED_WITH_ERRORS" if errors else "COMPLETED";run.sources_checked=sources;run.pages_checked=pages;run.candidates_discovered=len(candidates);run.contacts_retained=len(contacts.items);run.errors_json=errors;run.completed_at=datetime.now(timezone.utc);run.last_checked_at=run.completed_at;db.add(run);db.commit()
        return self.list(db,job_id)

    def outreach(self,db,job_id:int,contact_id:int)->OutreachPreview:
        job=db.get(JobRecord,job_id);contact=db.get(ContactRecord,contact_id)
        if not job or not contact or contact.job_id!=job_id:raise LookupError("Contact not found")
        evidence=[item for item in EvidenceService().all() if item.verified]
        evidence_ids=[item.id for item in evidence[:2]]
        background=(evidence[0].statement if evidence else "my relevant technical background")
        message=f"Hi {contact.name.split()[0]} — I came across the {job.title} opening at {job.company} and noticed your work appears closely related. My background includes {background}. I’d value learning more about the problems this team is working on."
        return OutreachPreview(contact_id=contact_id,message=message,evidence_ids=evidence_ids,sent=False)
