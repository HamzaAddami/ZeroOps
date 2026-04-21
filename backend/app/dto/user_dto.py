from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    name: str = Field(...)
    email: str = Field(...)
    password: str = Field(...)
    confirm_password: str = Field(...)