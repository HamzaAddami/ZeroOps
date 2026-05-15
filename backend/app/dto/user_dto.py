from pydantic import BaseModel, Field
from rich.status import Status

from app.dto.projectDTO import ProjectResponse
from app.model.user import UserRole

class UserCreateByAdmin(BaseModel):
    full_name: str = Field(...)
    email: str = Field(...)
    role: UserRole = Field(...)

class UserLogin(BaseModel):
    username: str = Field(...)
    password: str = Field(...)

class UserChangePassword(BaseModel):
    old_password: str = Field(...)
    new_password: str = Field(...)
    confirm_password: str = Field(...)

class UserResponse(BaseModel):
    full_name: str = Field(...)
    email: str = Field(...)
    last_login: str = Field(...)
    is_active: bool = Field(...)
    role: UserRole = Field(...)
    status: Status = Field(...)
    projects: list[ProjectResponse] = Field(...)
