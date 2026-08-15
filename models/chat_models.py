# Chat request model with validation for security and LLM readiness

from pydantic import BaseModel, Field, field_validator

from validation import (
    RESTAURANT_ID_MAX_LEN,
    SESSION_ID_MAX_LEN,
    validate_restaurant_id,
    validate_session_id,
)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=SESSION_ID_MAX_LEN)
    message: str = Field(..., min_length=1, max_length=2000)
    restaurant_id: str = Field(..., min_length=1, max_length=RESTAURANT_ID_MAX_LEN)

    @field_validator("session_id")
    @classmethod
    def session_id_alphanumeric(cls, v: str) -> str:
        return validate_session_id(v)

    @field_validator("restaurant_id")
    @classmethod
    def restaurant_id_safe(cls, v: str) -> str:
        return validate_restaurant_id(v)

    @field_validator("message", mode="before")
    @classmethod
    def message_strip(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v
