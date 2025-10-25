from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------
# Enums
# ---------------------------

class JobType(str, Enum):
    download = "download"
    metadata = "metadata"
    separation = "separation"
    transcription = "transcription"
    visualization = "visualization"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


# ---------------------------
# Base model config
# ---------------------------

class ORMModel(BaseModel):
    """
    Base model that works with Pydantic v2 and ORM objects.
    """
    model_config = ConfigDict(
        from_attributes=True,   # replaces orm_mode=True
        populate_by_name=True,  # lets you accept 'name' when an alias exists
        extra="ignore",         # ignore unknown fields if DB rows bring extras
    )


# ---------------------------
# Shared job shapes
# ---------------------------

class JobBase(ORMModel):
    """
    Fields common to most job shapes (but not necessarily required on create).
    """
    id: Optional[str] = Field(default=None, description="Opaque job identifier (UUID/string)")
    type: JobType = Field(description="Kind of job to run")
    status: JobStatus = Field(default=JobStatus.queued, description="Current status")
    message: Optional[str] = Field(default=None, description="Human-readable status message")
    # Progress 0-100 (optional)
    progress: Optional[int] = Field(default=None, ge=0, le=100)


class JobCreate(ORMModel):
    """
    Payload to enqueue a new job.
    Provide 'type' and optional 'params' describing inputs (URLs, paths, etc.).
    """
    type: JobType
    params: Dict[str, Any] = Field(default_factory=dict)


class JobUpdate(ORMModel):
    """
    Partial update from workers.
    """
    status: Optional[JobStatus] = None
    message: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    # Worker can attach a partial/complete result or error info
    result: Optional[Dict[str, Any]] = None
    error_detail: Optional[str] = None


class Job(ORMModel):
    """
    API-facing job object.
    No leading-underscore fields (so it serializes cleanly).
    """
    id: str
    type: JobType
    status: JobStatus
    message: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)

    # Outputs
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured result payload (e.g., file paths, features)"
    )
    error_detail: Optional[str] = Field(
        default=None, description="If status=error, a concise error string"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional runtime timing
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobInDB(Job):
    """
    DB representation. Mirrors Job but you can add DB-only columns here.
    For example, shard info, worker id, retry counters, etc.
    """
    # Example DB-only fields (adjust/remove as needed):
    retries: int = 0
    worker_id: Optional[str] = None


# ---------------------------
# Common response helpers
# ---------------------------

class JobID(ORMModel):
    id: str


class Pagination(ORMModel):
    page: int = 1
    size: int = 50
    total: int = 0


class JobList(ORMModel):
    items: list[Job]
    pagination: Pagination
