from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.model.deployment import DeploymentStatus


class DeploymentResponse(BaseModel):
    id: UUID
    project_id: UUID
    pipeline_id: UUID
    image_tag: str
    commit_sha: str
    namespace: str
    deployment_url: Optional[str] = None
    status: str
    replicas_desired: int
    replicas_ready: int
    previous_image_tag: Optional[str] = None
    duration_seconds: Optional[int] = None
    deployed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StatusUpdateRequest(BaseModel):
    status: DeploymentStatus
    replicas_ready: Optional[int] = None
    deployment_url: Optional[str] = None