# Chat request model with validation for security and LLM readiness

import re
from pydantic import BaseModel, Field, field_validator

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=2000)
    restaurant_id: str = Field(default="restaurant_1", min_length=1, max_length=64)

    @field_validator("session_id")
    @classmethod
    def session_id_alphanumeric(cls, v: str) -> str:
        if not SESSION_ID_PATTERN.match(v):
            raise ValueError("session_id must be 1-128 chars: letters, numbers, underscore, hyphen only")
        return v

    @field_validator("restaurant_id")
    @classmethod
    def restaurant_id_safe(cls, v: str) -> str:
        if not v or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", v):
            raise ValueError("restaurant_id must be 1-64 chars: letters, numbers, underscore, hyphen only")
        return v

    @field_validator("message", mode="before")
    @classmethod
    def message_strip(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v