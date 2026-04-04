from sqlalchemy import Column, Enum, String, DateTime as SQLEnum
from sqlalchemy.orm import DeclarativeMeta, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import UUID
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
