from datetime import datetime,timedelta,timezone
import httpx

FAILURE_TYPES=(
    (httpx.TimeoutException,"NETWORK_TIMEOUT"),(httpx.ConnectError,"DNS_FAILURE"),
)
def classify_source_failure(exc:Exception)->str:
    for kind,label in FAILURE_TYPES:
        if isinstance(exc,kind):return label
    status=getattr(getattr(exc,"response",None),"status_code",None) or getattr(exc,"status_code",None)
    if status==404:return "HTTP_404"
    if status in (401,403):return "HTTP_401_403"
    if status==429:return "HTTP_429"
    if status and status>=500:return "HTTP_5XX"
    text=str(exc).casefold()
    if "404 not found" in text:return "HTTP_404"
    if "401 unauthorized" in text or "403 forbidden" in text:return "HTTP_401_403"
    if "429 too many requests" in text:return "HTTP_429"
    if any(f"{code} server error" in text for code in range(500, 600)):return "HTTP_5XX"
    if "rate limit" in text:return "HTTP_429"
    if "timeout" in text:return "NETWORK_TIMEOUT"
    if "json" in text or "parse" in text:return "PARSE_ERROR"
    if "not active" in text or "invalid" in text:return "INVALID_SOURCE"
    return "OTHER"

def record_source_success(source,job_count:int,latency_ms:float):
    now=datetime.now(timezone.utc);source.last_success_at=now;source.last_attempt_at=now;source.last_error=None;source.failure_type=None;source.consecutive_failures=0;source.retry_after=None;source.last_job_count=job_count;source.health_status="EMPTY" if job_count==0 else "HEALTHY";source.average_latency_ms=round(latency_ms if source.average_latency_ms is None else source.average_latency_ms*.7+latency_ms*.3,1)

def record_source_failure(source,exc:Exception,latency_ms:float):
    now=datetime.now(timezone.utc);source.last_attempt_at=now;source.last_failure_at=now;source.last_error=str(exc)[:1000];source.failure_type=classify_source_failure(exc);source.consecutive_failures=(source.consecutive_failures or 0)+1;source.average_latency_ms=round(latency_ms if source.average_latency_ms is None else source.average_latency_ms*.7+latency_ms*.3,1)
    source.health_status={"HTTP_404":"NOT_FOUND","HTTP_401_403":"AUTH_REQUIRED","HTTP_429":"RATE_LIMITED"}.get(source.failure_type,"TEMPORARILY_UNAVAILABLE" if source.consecutive_failures<3 else "DEGRADED")
    source.retry_after=now+timedelta(minutes=min(1440,15*(2**min(source.consecutive_failures,6))))
