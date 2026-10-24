from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware

from app.api.applications import router as applications_router
from app.api.jobs import router as jobs_router
from app.db.session import engine
from app.core.auth import CurrentAdmin, CurrentUser

app = FastAPI(
    title="AI Applier API",
    description="Backend API for the AI Applier job application platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(applications_router)


@app.get("/")
def root():
    return {
        "message": "AI Applier API",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )

@app.get("/api/me")
def get_current_user(user_id: CurrentUser):
    return {"user_id": user_id}


@app.get("/api/admin/status")
def get_admin_status(_admin_id: CurrentAdmin):
    return {"is_admin": True}
