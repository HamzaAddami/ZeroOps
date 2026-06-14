from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class StageResponse(BaseModel):
    id: UUID
    order: int
    type: str
    status: str
    logs: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PipelineResponse(BaseModel):
    id: UUID
    project_id: UUID
    commit_sha: str
    commit_message: Optional[str] = None
    branch: str
    status: str
    duration_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    stages: List[StageResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True