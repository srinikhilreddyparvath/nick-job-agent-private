from types import SimpleNamespace
import httpx
from app.services.source_health_service import classify_source_failure,record_source_failure,record_source_success

def source():return SimpleNamespace(last_success_at=None,last_attempt_at=None,last_error=None,failure_type=None,consecutive_failures=0,average_latency_ms=None,last_job_count=0,retry_after=None,health_status="UNKNOWN",last_failure_at=None)

def test_source_health_success_and_empty():
    item=source();record_source_success(item,12,100);assert item.health_status=="HEALTHY" and item.last_job_count==12
    record_source_success(item,0,200);assert item.health_status=="EMPTY" and item.consecutive_failures==0

def test_source_failure_is_classified_and_backed_off():
    item=source();record_source_failure(item,httpx.TimeoutException("timeout"),50)
    assert item.failure_type=="NETWORK_TIMEOUT" and item.health_status=="TEMPORARILY_UNAVAILABLE" and item.retry_after
    record_source_failure(item,RuntimeError("parse error"),60);record_source_failure(item,RuntimeError("parse error"),70)
    assert item.health_status=="DEGRADED" and item.consecutive_failures==3

def test_http_failure_categories():
    assert classify_source_failure(httpx.HTTPStatusError("x",request=httpx.Request("GET","https://example.test"),response=httpx.Response(429)))=="HTTP_429"
    assert classify_source_failure(RuntimeError("connector request failed: 404 Not Found"))=="HTTP_404"
    assert classify_source_failure(RuntimeError("connector request failed: 403 Forbidden"))=="HTTP_401_403"
