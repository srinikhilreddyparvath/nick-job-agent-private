import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import JobRecord
from app.models.job import Job
from app.services.normalization_service import description_fingerprint,normalize_company,normalize_location


TRACKING_PARAMS = {"gh_src", "source", "ref", "referrer", "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term"}


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query) if key.lower() not in TRACKING_PARAMS))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


class DedupeService:
    def find_duplicate(self, db: Session, job: Job) -> JobRecord | None:
        canonical_url = canonicalize_url(str(job.apply_url))
        normalized_title = normalize_text(job.title)
        company = normalize_company(job.company)
        location = normalize_location(job.location,job.remote_type.value).lower()
        fingerprint=description_fingerprint(job.description)
        exact = db.scalar(select(JobRecord).where(JobRecord.source == job.source, JobRecord.external_id == job.external_id))
        if exact:
            return exact
        candidates = db.scalars(select(JobRecord).where(or_(JobRecord.canonical_apply_url == canonical_url,JobRecord.description_fingerprint==fingerprint, JobRecord.normalized_title == normalized_title))).all()
        return next((item for item in candidates if item.canonical_apply_url == canonical_url or (fingerprint and item.description_fingerprint==fingerprint) or (normalize_company(item.company) == company and (item.normalized_location or "").lower() == location and item.normalized_title==normalized_title)), None)

    def record_alternate(self,db:Session,record:JobRecord,job:Job)->None:
        alternates=list(record.alternate_sources or []); candidate={"source":job.source,"external_id":job.external_id,"source_url":str(job.source_url),"apply_url":str(job.apply_url)}
        if candidate not in alternates: alternates.append(candidate); record.alternate_sources=alternates; db.commit()
