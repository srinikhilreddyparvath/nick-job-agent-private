#!/usr/bin/env python3
"""Read-only RoleCall setup and runtime diagnostics."""
from __future__ import annotations
import importlib.util,json,os,subprocess,sys,tempfile,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];BACKEND=ROOT/"backend";sys.path.insert(0,str(BACKEND))

def result(name,ok,reason="",fix="",status=None):return {"name":name,"ok":bool(ok),"reason":reason,"fix":fix,"status":status}
def reachable(url):
    try:
        with urllib.request.urlopen(url,timeout=3) as response:return response.status<500
    except Exception:return False
def fetch_json(url):
    try:
        with urllib.request.urlopen(url,timeout=3) as response:return json.loads(response.read())
    except Exception:return None
def compose_services():
    try:
        raw=subprocess.run(["docker","compose","ps","--all","--format","json"],cwd=ROOT,capture_output=True,text=True,timeout=10).stdout
        rows=[json.loads(line) for line in raw.splitlines() if line.strip()];return {r.get("Service"):(r.get("State"),r.get("Health")) for r in rows}
    except Exception:return {}

def docker_backend_snapshot():
    """Read backend-only diagnostics from the running API container.

    This keeps the documented Docker quick start from requiring a second,
    undocumented Python environment on the host.
    """
    code=(
        "import importlib.util,json,tempfile;"
        "from app.core.config import get_settings;"
        "from app.connectors import CONNECTORS;"
        "from app.services.candidate_extraction_service import ResumeTextExtractor,private_storage_path;"
        "s=get_settings();p=private_storage_path(s);"
        "txt=True;w=True;"
        "\ntry: ResumeTextExtractor().extract(b'Fictional resume text for parser health','txt')"
        "\nexcept Exception: txt=False"
        "\ntry:\n f=tempfile.NamedTemporaryFile(dir=p,delete=True);f.close()"
        "\nexcept Exception: w=False"
        "\nprint(json.dumps({'pdf':importlib.util.find_spec('pypdf') is not None,'docx':importlib.util.find_spec('docx') is not None,'txt':txt,'storage':w,'storage_path':str(p),'llm_enabled':s.llm_enabled,'llm_provider':s.llm_provider,'llm_model':s.llm_model,'credential':bool((s.llm_provider=='openai' and s.openai_api_key) or (s.llm_provider=='anthropic' and s.anthropic_api_key) or s.llm_provider=='mock'),'catalog_path':s.starter_discovery_catalog_path,'application_mode':s.application_mode,'auto_submit':s.auto_submit_enabled,'connectors':sorted(CONNECTORS)}))"
    )
    try:
        completed=subprocess.run(["docker","compose","exec","-T","api","python","-c",code],cwd=ROOT,capture_output=True,text=True,timeout=15)
        return json.loads(completed.stdout.strip()) if completed.returncode==0 else None
    except Exception:return None

def main():
    try:
        from app.core.config import get_settings
        from app.connectors import CONNECTORS
        from app.services.candidate_extraction_service import ResumeTextExtractor,private_storage_path
        settings=get_settings();snapshot=None
    except ModuleNotFoundError:
        settings=None;snapshot=docker_backend_snapshot();CONNECTORS={name:None for name in (snapshot or {}).get("connectors",[])}
    if settings is None and snapshot is None:
        print("RoleCall Doctor\n===============\n")
        print(f"{'Backend diagnostics':<28}FAIL")
        print("  Reason: Backend dependencies are not installed locally and the Docker API is unavailable.")
        print("  Fix: Start Docker, then run docker compose up -d --build and retry Doctor.")
        print("\nOverall: ACTION REQUIRED")
        return 1
    services=compose_services();checks=[]
    checks += [result("Frontend",reachable("http://localhost:3000"),"Not reachable","Run docker compose up -d --build"),result("Backend",reachable("http://localhost:8000/health"),"Not reachable","Run docker compose up -d --build api")]
    for service,label in (("postgres","PostgreSQL"),("migrate","Migrations"),("worker","Worker"),("scheduler","Scheduler")):
        state,health=services.get(service,("",""));ok=(state=="running" and (service!="postgres" or health=="healthy")) or (service=="migrate" and state=="exited")
        checks.append(result(label,ok,f"Compose state: {state or 'not found'}",f"Run docker compose up -d {service}"))
    checks += [result("PDF parser",snapshot["pdf"] if snapshot else importlib.util.find_spec("pypdf") is not None,"pypdf unavailable","Start the API container or install backend dependencies"),result("DOCX parser",snapshot["docx"] if snapshot else importlib.util.find_spec("docx") is not None,"python-docx unavailable","Start the API container or install backend dependencies")]
    if snapshot:txt_ok=snapshot["txt"]
    else:
        try:ResumeTextExtractor().extract(b"Fictional resume text for parser health", "txt");txt_ok=True
        except Exception:txt_ok=False
    checks.append(result("TXT parser",txt_ok,"Text decoding failed","Reinstall backend dependencies"))
    storage=Path(snapshot["storage_path"]) if snapshot else private_storage_path(settings)
    if snapshot:writable=snapshot["storage"]
    else:
        try:
            with tempfile.NamedTemporaryFile(dir=storage,delete=True):pass
            writable=True
        except Exception:writable=False
    checks.append(result("Resume storage",writable,f"Not writable: {storage}","Fix CANDIDATE_PRIVATE_STORAGE_PATH permissions"))
    llm_enabled=snapshot["llm_enabled"] if snapshot else settings.llm_enabled;llm_provider=snapshot["llm_provider"] if snapshot else settings.llm_provider;llm_model=snapshot["llm_model"] if snapshot else settings.llm_model
    provider_ok=(not llm_enabled) or (snapshot["credential"] if snapshot else bool(llm_provider and llm_model and ((llm_provider=="openai" and settings.openai_api_key) or (llm_provider=="anthropic" and settings.anthropic_api_key) or llm_provider=="mock")))
    llm_status="DISABLED (deterministic features remain available)" if not llm_enabled else f"{llm_provider}/{llm_model}; credential {'PRESENT' if provider_ok else 'MISSING'}"
    checks.append(result("LLM configuration",provider_ok,"Enabled but provider/model/credential is incomplete","Set LLM_PROVIDER, LLM_MODEL, and its API key",llm_status))
    try:
        catalog=Path(snapshot["catalog_path"] if snapshot else settings.starter_discovery_catalog_path);catalog=(BACKEND/catalog).resolve() if not catalog.is_absolute() else catalog
        source_count=len(json.loads(catalog.read_text(encoding="utf-8")));catalog_ok=source_count>0
    except Exception:catalog_ok=False;source_count=0
    checks.append(result("Job discovery",catalog_ok,"Starter catalog could not be loaded","Check STARTER_DISCOVERY_CATALOG_PATH",f"{source_count} starter sources"))
    public_sources=fetch_json("http://localhost:8000/sources") or []
    healthy=sum(x.get("health_status") in {"HEALTHY","EMPTY"} for x in public_sources);degraded=sum(x.get("health_status") in {"DEGRADED","TEMPORARILY_UNAVAILABLE","RATE_LIMITED"} for x in public_sources);unavailable=sum(x.get("health_status") in {"NOT_FOUND","AUTH_REQUIRED","BROKEN"} for x in public_sources)
    checks.append(result("Job providers",bool(CONNECTORS),"No job providers are enabled","Check connector registration",f"{len(CONNECTORS)} enabled: {', '.join(sorted(CONNECTORS))}"))
    checks.append(result("Discovered sources",True,status=f"{len(public_sources)} configured; {healthy} healthy; {degraded} degraded; {unavailable} unavailable"))
    scans=fetch_json("http://localhost:8000/scans") or []
    if scans:
        latest=scans[0];discovery=f"{latest.get('status','unknown')}; {latest.get('jobs_fetched',0)} seen; {latest.get('jobs_added',0)} unique; {latest.get('jobs_scored',0)} ranked"
    else:discovery="No scan yet"
    checks.append(result("Discovery status",True,status=discovery))
    application_mode=snapshot["application_mode"] if snapshot else settings.application_mode;auto_submit=snapshot["auto_submit"] if snapshot else settings.auto_submit_enabled
    checks += [result("Application mode",application_mode=="manual","Unsafe/non-default mode","Set APPLICATION_MODE=manual",application_mode.upper()),result("Auto-submit",not auto_submit,"Auto-submit is enabled","Set AUTO_SUBMIT_ENABLED=false","DISABLED" if not auto_submit else "ENABLED")]
    print("RoleCall Doctor\n===============\n")
    for c in checks:
        state=c["status"] or ("PASS" if c["ok"] else "FAIL");print(f'{c["name"]:<28}{state}')
        if not c["ok"]:print(f'  Reason: {c["reason"]}\n  Fix: {c["fix"]}')
    ok=all(c["ok"] for c in checks);print(f"\nOverall: {'READY' if ok else 'ACTION REQUIRED'}");return 0 if ok else 1
if __name__=="__main__":raise SystemExit(main())
