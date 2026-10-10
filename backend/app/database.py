from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional

from app.models.job import JobType, JobStatus

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).parent.parent / 'data' / 'supermusic.db'}"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobModel(Base):
    """SQLAlchemy model for jobs."""
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, index=True)
    job_type = Column(SQLEnum(JobType), nullable=False, index=True)
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.queued, index=True)
    message = Column(String, nullable=True)
    progress = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error_detail = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def job_to_dict(job: JobModel) -> dict:
    """Convert JobModel to dict compatible with Job Pydantic model."""
    from app.models.job import Job
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "message": job.message,
        "progress": job.progress,
        "payload": job.payload,
        "result": job.result,
        "error_detail": job.error_detail,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }

