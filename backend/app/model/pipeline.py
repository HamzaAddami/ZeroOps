from datetime import datetime
from sqlalchemy import Column, ForeignKey, String, Enum, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.db import Base
import enum
import uuid

class PipelineStatus(str, enum.Enum):
    triggered = "triggered"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"

class StageType(str, enum.Enum):
    source_checkout = "source_checkout"  # clone repo
    code_analysis = "code_analysis"  # SonarQube
    unit_tests = "unit_tests"
    build = "build"  # docker build
    security_scan = "security_scan"  # Trivy
    push_registry = "push_registry"  # push GHCR
    deploy = "deploy"  # Argo CD / K8s

class StageStatus(str, enum.Enum):
    pending  = "pending"
    running  = "running"
    success  = "success"
    failed   = "failed"
    skipped  = "skipped"



class Pipeline(Base):
    __tablename__ = 'pipelines'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete="CASCADE"), nullable=False, index=True)
    triggered_by_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete="SET NULL"), nullable=True)

    commit_sha = Column(String(40), nullable=False)
    commit_message = Column(String(255), nullable=True)
    branch = Column(String(100), nullable=False, default="main")

    status = Column(Enum(PipelineStatus), nullable=False, default=PipelineStatus.triggered)

    duration_seconds = Column(Integer, nullable=True, default=None)
    started_at = Column(DateTime, nullable=True, default=None)
    finished_at = Column(DateTime, nullable=True, default=None)

    project = relationship("Project", back_populates="pipelines")
    triggered_by = relationship("User", foreign_keys=[triggered_by_id])
    stages = relationship("PipelineStage", back_populates="pipeline", order_by="PipelineStage.order", cascade="all, delete-orphan")
    security_scan = relationship("SecurityScan", back_populates="pipeline", uselist=False)
    deployment = relationship("Deployment", back_populates="pipeline", uselist=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,onupdate=datetime.utcnow, nullable=False)

    def start(self) -> None:
        self.status = PipelineStatus.running
        self.started_at = datetime.utcnow()

    def finish(self, success: bool) -> None:
        self.status = PipelineStatus.success if success else PipelineStatus.failed
        self.finished_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int((self.finished_at - self.started_at).total_seconds())

    def cancel(self) -> None:
        self.status = PipelineStatus.canceled
        self.finished_at = datetime.utcnow()

    @property
    def is_finished(self) -> bool:
        return self.status in (PipelineStatus.success, PipelineStatus.failed, PipelineStatus.canceled)

    @property
    def blocking_stage(self):
        return next(
            (s for s in self.stages if s.status == StageStatus.failed),
            None
        )

class PipelineStage(Base):
    __tablename__ = "pipeline_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    pipeline_id = Column(UUID(as_uuid=True),ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True)

    order  = Column(Integer, nullable=False)
    type   = Column(Enum(StageType), nullable=False)
    status = Column(Enum(StageStatus), nullable=False, default=StageStatus.pending)

    logs = Column(Text, nullable=True, default=None)

    error_message = Column(Text, nullable=True, default=None)

    duration_seconds = Column(Integer, nullable=True, default=None)
    started_at       = Column(DateTime, nullable=True, default=None)
    finished_at      = Column(DateTime, nullable=True, default=None)

    pipeline = relationship("Pipeline", back_populates="stages")

    def start(self) -> None:
        self.status = StageStatus.running
        self.started_at = datetime.utcnow()

    def finish(self, success: bool) -> None:
        self.status = StageStatus.success if success else StageStatus.failed
        self.finished_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int((self.finished_at - self.started_at).total_seconds())

    def fail(self, error: str, logs: str) -> None:
        self.status = StageStatus.failed
        self.error_message = error
        self.logs = logs
        self.finished_at = datetime.utcnow()

    def skip(self, skipped: bool) -> None:
        self.status = StageStatus.skipped

    def succeed(self, logs: str = None) -> None:
        self.status = StageStatus.success
        self.logs = logs
        self.finished_at = datetime.utcnow()
        if self.started_at:
            self.duration_seconds = int(
                (self.finished_at - self.started_at).total_seconds()
            )






