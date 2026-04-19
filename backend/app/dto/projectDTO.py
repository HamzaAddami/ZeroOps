from typing import Optional

from pydantic.v1 import BaseModel
from pydantic import BaseModel, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=13,
        max_length=100,
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
    )
    repository_url: Optional[str] = Field(
        None,
    )
