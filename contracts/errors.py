from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SQUAD_NOT_FOUND = "SQUAD_NOT_FOUND"
    MALFORMED_FRAME = "MALFORMED_FRAME"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    detail: list[dict[str, object]] = Field(default_factory=list)
