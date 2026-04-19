from sqlalchemy import Column, Enum, String, DateTime
from sqlalchemy.orm import DeclarativeMeta, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum


class Base(DeclarativeMeta):
    pass


class ProjectStatus(str, enum.Enum):
    pending = 'pending'
    building = 'building'
    deployed = 'deployed'
    failed = 'failed'



class Project(Base):
    __tablename__ = 'projects'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=True)
    repository_url = Column(String(255), nullable=True)
    status = Column(Enum(ProjectStatus), nullable=False, default=ProjectStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, oneupdate=datetime.utcnow, nullable=False)




