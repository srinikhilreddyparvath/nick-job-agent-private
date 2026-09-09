from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, applications, application_packages, browser_applications, career_intelligence, companies, contacts, feedback, jobs, onboarding, operations, profile, scans, sources, semantic
from app.core.config import get_settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().environment != "production": init_db()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(jobs.router); app.include_router(profile.router); app.include_router(applications.router)
app.include_router(sources.router); app.include_router(scans.router); app.include_router(feedback.router)
app.include_router(agents.router)
app.include_router(companies.router)
app.include_router(semantic.router)
app.include_router(application_packages.router)
app.include_router(browser_applications.router)
app.include_router(operations.router)
app.include_router(onboarding.router)
app.include_router(career_intelligence.router)
app.include_router(contacts.router)


@app.get("/health", tags=["system"])
def health(): return {"status": "ok", "service": settings.app_name, "phase": 7}
