"""Dashboard-related data models"""

from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel
from pydantic import validator as validator


class DashboardFrame(BaseModel):
    """Base structure for dashboard WebSocket frames."""

    type: str
    timestamp: str
    data: Dict[str, Any]

    @validator("type")
    def validate_type(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("type must be a non-empty string")
        return v.strip()

    @validator("timestamp")
    def validate_timestamp(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("timestamp must be a non-empty ISO 8601 string")
        # Validate ISO-8601 format
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError("timestamp must be ISO 8601 format") from exc
        return v

    @validator("data")
    def validate_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("data must be a dictionary")
        return v


class DashboardLogRequest(BaseModel):
    """Request model for dashboard log entries"""

    level: str
    message: str
    timestamp: str

    @validator("level")
    def validate_level(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("level must be a string")
        v = v.upper().strip()
        # Canonical levels used across dashboard UI
        allowed = {"INFO", "SUCS", "WARN", "CRIT", "ERR"}
        # Map common long-form aliases to canonical short forms
        alias_map = {
            "INFORMATION": "INFO",
            "SUCCESS": "SUCS",
            "WARNING": "WARN",
            "CRITICAL": "CRIT",
            "ERROR": "ERR",
        }
        v = alias_map.get(v, v)
        if v not in allowed:
            raise ValueError(f"level must be one of {sorted(allowed)}")
        return v

    @validator("message")
    def validate_message(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("message cannot be empty")
        return v.strip()

    @validator("timestamp")
    def validate_log_timestamp(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("timestamp must be provided for log entries")
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as exc:
            raise ValueError("timestamp must be ISO 8601 format") from exc
        return v
