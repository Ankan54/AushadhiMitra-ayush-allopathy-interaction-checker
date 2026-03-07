import re
from pydantic import BaseModel, field_validator
from typing import Optional

from app.config import INPUT_MAX_LENGTH, INPUT_MIN_LENGTH

_ALLOWED_CHARS = re.compile(r"^[\w\s\-'.,()]+$", re.UNICODE)


class InteractionRequest(BaseModel):
    ayush_name: str
    allopathy_name: str

    @field_validator("ayush_name", "allopathy_name")
    @classmethod
    def validate_drug_name(cls, v: str, info) -> str:
        v = v.strip()
        if len(v) < INPUT_MIN_LENGTH:
            raise ValueError(
                f"{info.field_name} must be at least {INPUT_MIN_LENGTH} characters"
            )
        if len(v) > INPUT_MAX_LENGTH:
            raise ValueError(
                f"{info.field_name} must be at most {INPUT_MAX_LENGTH} characters"
            )
        if not _ALLOWED_CHARS.match(v):
            raise ValueError(
                f"{info.field_name} contains invalid characters"
            )
        return v


class HealthResponse(BaseModel):
    status: str
    architecture: str
    execution_mode: str
    database: str
