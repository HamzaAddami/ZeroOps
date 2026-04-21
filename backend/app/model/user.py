from sqlalchemy import Column, Enum, String, DateTime, Integer, Boolean
from sqlalchemy.orm import relationship

from ..core.db import Base
from ..model.project import project_members
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timedelta
import uuid
import enum


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30

class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    developer = "developer"
    viewer = "viewer"


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    banned = "banned"


class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(150), nullable=False)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)

    hashed_password = Column(String(255), nullable=False)
    must_change_password = Column(Boolean, nullable=False, default=True)
    password_reset_count = Column(Integer, nullable=False, default=0)
    last_reset_at = Column(DateTime, nullable=True, default=None)

    last_login = Column(DateTime, nullable=True, default=None)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True, default=None)


    projects = relationship("Project", secondary=project_members, back_populates="members", lazy="select")

    role = Column(Enum(UserRole), nullable=False, default=UserRole.developer)
    is_active = Column(Boolean, nullable=False, default=True)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.active)

    mfa_secret = Column(String(64), nullable=True, default=None)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    mfa_recovery_codes= Column(String(500), nullable=True, default=None)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def record_login(self):
        self.last_login = datetime.utcnow()
        self.failed_login_attempts = 0
        self.locked_until = None

    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            self.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)

    def is_locked(self) -> bool:

        if datetime.utcnow() > self.locked_until:
            self.locked_until = None
            self.failed_login_attempts = 0
            return False

        return self.locked_until is None

    def get_lockout_remaining(self):

        if not self.locked_until:
            return 0

        remaining = (self.locked_until - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None

    def active(self):
        self.status = UserStatus.active
        self.is_active = True
        self.failed_login_attempts = 0
        self.locked_until = None

    def deactivate(self):
        self.status = UserStatus.inactive
        self.is_active = False

    def ban(self, reason: str = None) -> None:
        self.status = UserStatus.banned
        self.is_active = False

    def force_password_change(self):
        self.must_change_password = True
        self.password_reset_count += 1
        self.last_reset_at = datetime.utcnow()

    def complete_password_change(self, new_hashed: str) -> None:
        self.hashed_password = new_hashed
        self.must_change_password = False
