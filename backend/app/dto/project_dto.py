from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.model.project import ProjectStatus


class ProjectCreate(BaseModel):
    name:           str           = Field(..., min_length=3, max_length=100)
    description:    Optional[str] = Field(None, max_length=2000)
    repository_url: Optional[str] = None
    branch:         Optional[str] = "main"


class ProjectUpdate(BaseModel):
    description:    Optional[str] = None
    repository_url: Optional[str] = None
    branch:         Optional[str] = None
    status:         Optional[ProjectStatus] = None


class MemberAdd(BaseModel):
    user_id: UUID


class ProjectResponse(BaseModel):
    id:             UUID
    name:           str
    description:    Optional[str]
    repository_url: Optional[str]
    branch:         Optional[str]
    status:         ProjectStatus
    deployment_url: Optional[str]
    is_deleted:     bool
    created_at:     datetime
    updated_at:     datetime

    class Config:
        from_attributes = True