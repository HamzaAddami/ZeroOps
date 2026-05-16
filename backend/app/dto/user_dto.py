from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.model.user import UserStatus
from uuid import UUID
from app.model.user import UserRole

class UserCreateByAdmin(BaseModel):
    full_name: str = Field(..., max_length=150)
    email: str
    role: UserRole

class AdminCreateUserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: UserRole
    temp_password: str

class UserLogin(BaseModel):
    username: str = Field(...)
    password: str = Field(...)

class UserChangePassword(BaseModel):
    old_password: str = Field(...)
    new_password: str = Field(...)
    confirm_password: str = Field(...)

    def passwords_match(self) -> bool:
        return self.new_password == self.confirm_password

class MFAVerifyRequest(BaseModel):
    code: str =  Field(...)

class MFAConfirmRequest(BaseModel):
    code: str = Field(...)

class UserResponse(BaseModel):
    id: UUID
    full_name: str
    username: str
    email: str
    role: UserRole
    status: UserStatus
    is_active: bool
    mfa_enabled: bool
    must_change_password: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
class UserCreatedResponse(BaseModel):
    user: UserResponse
    temp_password: str

class UpdateRoleRequest(BaseModel):
    role: UserRole


class BanRequest(BaseModel):
    reason: str = Field(..., min_length=5)

