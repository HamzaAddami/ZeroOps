from pydantic import BaseModel
from pydantic.v1 import UUID1


class User(BaseModel):
    id: UUID1 | None = None
    name: str
    username: str
    email: str
