from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


@dataclass
class JobError:
    code: str
    message: str
    details: Any = None


@dataclass
class Job:
    id: str
    type: str
    params: dict[str, Any]
    status: JobStatus = "queued"
    created_at_ms: int = 0
    started_at_ms: Optional[int] = None
    finished_at_ms: Optional[int] = None
    progress: Optional[float] = None
    result: Any = None
    error: Optional[JobError] = None
    canceled: bool = False
    logs: list[str] = field(default_factory=list)


JobEventType = Literal["status", "log", "progress", "result", "error"]


@dataclass
class JobEvent:
    type: JobEventType
    data: dict[str, Any]
    ts_ms: int

