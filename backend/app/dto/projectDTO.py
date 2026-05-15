from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from app.model.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=13, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    repository_url: Optional[str] = Field(None)

class ProjectUpdate(BaseModel):
    name: str = Field(..., min_length=13, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    repository_url: Optional[str] = Field(None)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    repository_url: Optional[str] = None
    status: ProjectStatus = ProjectStatus.pending
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True