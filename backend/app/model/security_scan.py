# app/models/security_scan.py
from sqlalchemy import Column, Enum, String, DateTime, Integer, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from ..core.db import Base
from datetime import datetime
import uuid
import enum


class ScanStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed  = "passed"
    failed  = "failed"


class SeverityLevel(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"
    info     = "info"


class SecurityScan(Base):
    __tablename__ = "security_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    pipeline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True
    )

    image_tag   = Column(String(255), nullable=False)
    scan_tool   = Column(String(50),  nullable=False, default="trivy")
    status      = Column(Enum(ScanStatus), nullable=False, default=ScanStatus.pending)

    critical_count = Column(Integer, nullable=False, default=0)
    high_count     = Column(Integer, nullable=False, default=0)
    medium_count   = Column(Integer, nullable=False, default=0)
    low_count      = Column(Integer, nullable=False, default=0)

    # Structure : [{"id": "CVE-...", "severity": "critical", "package": "...", ...}]
    vulnerabilities = Column(JSON, nullable=True, default=list)

    is_blocking = Column(Boolean, default=True)

    scanned_at  = Column(DateTime, nullable=True, default=None)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    pipeline = relationship("Pipeline", back_populates="security_scan")

    def record_results(self, vulnerabilities: list) -> None:

        self.vulnerabilities = vulnerabilities
        self.scanned_at      = datetime.utcnow()

        self.critical_count = sum(1 for v in vulnerabilities
                                  if v.get("severity") == "critical")
        self.high_count     = sum(1 for v in vulnerabilities
                                  if v.get("severity") == "high")
        self.medium_count   = sum(1 for v in vulnerabilities
                                  if v.get("severity") == "medium")
        self.low_count      = sum(1 for v in vulnerabilities
                                  if v.get("severity") == "low")

        self.status = ScanStatus.failed if self.critical_count > 0 else ScanStatus.passed

    def __repr__(self):
        return (f"<SecurityScan pipeline={self.pipeline_id} "
                f"status={self.status} "
                f"critical={self.critical_count}>")