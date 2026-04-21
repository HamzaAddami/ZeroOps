import enum
from datetime import datetime

from sqlalchemy import Column, UUID, ForeignKey, Integer, Enum, Text, DateTime, String
from sqlalchemy.orm import relationship
from ..core.db import Base

import uuid

class DeploymentStatus(str, enum.Enum):
    pending = "pending"
    deploying = "deploying"
    running = "running"
    degraded = "degraded"
    failed = "failed"
    rolled_back = "rolled_back"


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_id = Column(UUID(as_uuid=True),ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, unique=True)

    image_tag = Column(String(255), nullable=False)
    commit_sha = Column(String(40), nullable=False)
    namespace = Column(String(100), nullable=False)  # namespace K8s
    deployment_url = Column(String(255), nullable=True, default=None)

    status = Column(Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.pending)

    replicas_desired = Column(Integer, nullable=False, default=1)
    replicas_ready = Column(Integer, nullable=False, default=0)

    previous_image_tag = Column(String(255), nullable=True, default=None)

    duration_seconds = Column(Integer, nullable=True, default=None)
    deployed_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


    project = relationship("Project", back_populates="deployments")
    pipeline = relationship("Pipeline", back_populates="deployment")

    def mark_running(self, url: str = None) -> None:
        self.status = DeploymentStatus.running
        self.deployed_at = datetime.utcnow()
        if url:
            self.deployment_url = url

    def rollback(self) -> None:
        self.previous_image_tag = self.image_tag
        self.status = DeploymentStatus.rolled_back

