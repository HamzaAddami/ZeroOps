from ..core.db import Base
from sqlalchemy import Column, Enum, String, DateTime, Table, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.model.pipeline import Pipeline
from app.model.vm_request import VMRequest
from datetime import datetime
import uuid
import enum

class ProjectStatus(str, enum.Enum):

    pending = 'pending'
    building = 'building'
    deployed = 'deployed'
    failed = 'failed'

project_members = Table(
    'project_members',
    Base.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete="CASCADE"), primary_key=True, index=True),
    Column('project_id', UUID(as_uuid=True), ForeignKey('projects.id', ondelete="CASCADE"), primary_key=True, index=True),
)

class Project(Base):
    __tablename__ = 'projects'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    repository_url = Column(String(255), nullable=True)
    branch = Column(String(100), nullable=True, default='main')
    last_commit_sha = Column(String(40), nullable=True)
    deployment_url = Column(String(255), nullable=True)

    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True, default=None)

    status = Column(Enum(ProjectStatus), nullable=False, default=ProjectStatus.pending)

    members = relationship("User", secondary=project_members, back_populates="projects", lazy="select")
    pipelines = relationship("Pipeline", back_populates="project", cascade="all, delete-orphan", order_by="Pipeline.created_at.desc()", lazy="select")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan", lazy="select")
    vm_requests = relationship("VMRequest", back_populates="project", cascade="all, delete-orphan", lazy="select")


    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def soft_delete(self)-> None:
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    @property
    def last_pipeline(self):
        return self.pipelines[0] if self.pipelines else None

    @property
    def last_deployment(self):
        return self.deployments[0] if self.deployments else None

    def __repr__(self):
        return f"<Project name={self.name!r} status={self.status}>"



