from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------
# Enums
# ---------------------------

class JobType(str, Enum):
    CSV_ENRICHMENT = "csv_enrichment"
    MIDI_CONVERSION = "midi_conversion"
    STEM_SEPARATION = "stem_separation"
    TRACK_DOWNLOAD = "track_download"
    VISUALIZATION = "visualization"
    # Legacy aliases for backward compatibility
    download = "track_download"
    metadata = "csv_enrichment"
    separation = "stem_separation"
    transcription = "midi_conversion"


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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: JobType = Field(description="Kind of job to run")
    status: JobStatus = Field(default=JobStatus.queued)
    message: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Job input parameters")

    # Outputs
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured result payload (e.g., file paths, features)"
    )
    error_detail: Optional[str] = Field(
        default=None, description="If status=error, a concise error string"
    )
    error_hint: Optional[str] = Field(default=None, description="If status=error, what the user can do about it")

    # Live progress (see app/core/progress.py)
    stage: Optional[str] = Field(default=None, description="The step the job is on right now")
    stages: List[Dict[str, Any]] = Field(default_factory=list, description="Steps so far, with start/end times")
    eta_s: Optional[float] = Field(default=None, description="Rough expected total run time in seconds")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional runtime timing
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def handle_type_alias(cls, data: Any) -> Any:
        """Handle both 'type' and 'job_type' in input data."""
        if isinstance(data, dict):
            if "type" in data and "job_type" not in data:
                data["job_type"] = data["type"]
            elif "job_type" in data and "type" not in data:
                data["type"] = data["job_type"]
        return data

    @property
    def type(self) -> JobType:
        """Alias for job_type for backward compatibility."""
        return self.job_type

    def mark_running(self, message: Optional[str] = None) -> None:
        """Mark job as running."""
        self.status = JobStatus.running
        self.started_at = datetime.utcnow()
        if message:
            self.message = message
        self.updated_at = datetime.utcnow()

    def mark_success(self, result: Dict[str, Any], message: Optional[str] = None) -> None:
        """Mark job as successfully completed."""
        self.status = JobStatus.done
        self.result = result
        self.finished_at = datetime.utcnow()
        if message:
            self.message = message
        self.progress = 100
        if self.stages and self.stages[-1].get("ended_at") is None:
            self.stages[-1]["ended_at"] = datetime.utcnow().isoformat()
        self.stage = None
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error_detail: str, message: Optional[str] = None) -> None:
        """Mark job as failed."""
        from app.core.progress import friendly_error

        self.status = JobStatus.error
        self.error_detail = error_detail
        self.error_hint = friendly_error(error_detail)
        self.finished_at = datetime.utcnow()
        if message:
            self.message = message
        self.updated_at = datetime.utcnow()


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
