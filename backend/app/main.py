from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, applications, companies, feedback, jobs, profile, scans, sources, semantic
from app.core.config import get_settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(jobs.router); app.include_router(profile.router); app.include_router(applications.router)
app.include_router(sources.router); app.include_router(scans.router); app.include_router(feedback.router)
app.include_router(agents.router)
app.include_router(companies.router)
app.include_router(semantic.router)


@app.get("/health", tags=["system"])
def health(): return {"status": "ok", "service": settings.app_name, "phase": 3}
