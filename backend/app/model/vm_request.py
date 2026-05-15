import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, UUID, ForeignKey, Integer, Enum, Text, DateTime, String
from sqlalchemy.orm import relationship

from ..core.db import Base

class VMRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    ready = "ready"
    running = "running"
    stopped = "stopped"
    destroyed = "destroyed"


class VMOperatingSystem(str, enum.Enum):
    ubuntu_22 = "ubuntu-22.04"
    ubuntu_24 = "ubuntu-24.04"
    debian_12 = "debian-12"

class VMRequest(Base):
    __tablename__ = "vm_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    requester_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    cpu_cores = Column(Integer, nullable=False)
    ram_gb = Column(Integer, nullable=False)
    disk_gb = Column(Integer, nullable=False)
    os = Column(Enum(VMOperatingSystem), nullable=False, default=VMOperatingSystem.ubuntu_22)

    purpose = Column(Text, nullable=False)

    duration_hours = Column(Integer, nullable=False, default=24)

    status = Column(Enum(VMRequestStatus), nullable=False, default=VMRequestStatus.pending)

    reviewed_by_id = Column(UUID(as_uuid=True),ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True, default=None)
    reject_reason = Column(Text, nullable=True, default=None)

    vm_id = Column(String(100), nullable=True, default=None)
    vm_ip_address = Column(String(45), nullable=True, default=None)
    vm_ssh_user = Column(String(50), nullable=True, default=None)
    vm_ssh_port = Column(Integer, nullable=True, default=22)

    expires_at = Column(DateTime, nullable=True, default=None)

    requester = relationship("User", foreign_keys=[requester_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_id])
    project = relationship("Project", back_populates="vm_requests")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


    def approve(self, reviewer_id) -> None:
        self.status = VMRequestStatus.approved
        self.reviewed_by_id = reviewer_id
        self.reviewed_at = datetime.utcnow()

    def reject(self, reviewer_id, reason: str) -> None:
        self.status = VMRequestStatus.rejected
        self.reviewed_by_id = reviewer_id
        self.reviewed_at = datetime.utcnow()
        self.reject_reason = reason

    def mark_ready(self, vm_id: str, ip: str, ssh_user: str) -> None:
        from datetime import timedelta
        self.status = VMRequestStatus.ready
        self.vm_id = vm_id
        self.vm_ip_address = ip
        self.vm_ssh_user = ssh_user
        self.expires_at = datetime.utcnow() + timedelta(hours=self.duration_hours)



