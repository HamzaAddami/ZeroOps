from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.model.vm_request import VMRequestStatus, VMOperatingSystem


OS_TO_AMI = {
    "ubuntu-22.04": "ami-0c7217cdde317cfec",
    "ubuntu-24.04": "ami-0e86e20dae9224db8",
    "debian-12":    "ami-0b0ea68c435eb488d",
}

def get_instance_type(cpu: int, ram: int) -> str:
    if cpu <= 1 and ram <= 1:  return "t2.micro"
    if cpu <= 1 and ram <= 2:  return "t2.small"
    if cpu <= 2 and ram <= 4:  return "t2.medium"
    if cpu <= 2 and ram <= 8:  return "t3.large"
    return "t3.xlarge"


class VMRequestCreate(BaseModel):
    project_id:     UUID
    cpu_cores:      int = Field(..., ge=1, le=4,   description="Max 4GB")
    ram_gb:         int = Field(..., ge=1, le=8,   description="Max 8GB")
    disk_gb:        int = Field(..., ge=10, le=30, description="Max 30GB Free Tier")
    os:             VMOperatingSystem = VMOperatingSystem.ubuntu_22
    purpose:        str = Field(..., min_length=10, max_length=500)
    duration_hours: int = Field(24, ge=1, le=72,  description="Max 72h")


class VMRequestReject(BaseModel):
    reason: str = Field(..., min_length=5)


class VMRequestResponse(BaseModel):
    id:             UUID
    project_id:     UUID
    cpu_cores:      int
    ram_gb:         int
    disk_gb:        int
    os:             VMOperatingSystem
    purpose:        str
    duration_hours: int
    status:         VMRequestStatus
    vm_ip_address:  Optional[str] = None
    vm_ssh_user:    Optional[str] = None
    vm_ssh_port:    Optional[int] = None
    vm_id:          Optional[str] = None
    expires_at:     Optional[datetime] = None
    reviewed_at:    Optional[datetime] = None
    reject_reason:  Optional[str] = None
    created_at:     datetime
    updated_at:     datetime

    class Config:
        from_attributes = True