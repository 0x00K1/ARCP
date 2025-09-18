"""Authentication-related data models"""

import re
from typing import Optional

from pydantic import BaseModel
from pydantic import field_validator as validator


class LoginRequest(BaseModel):
    """Request model for user/agent login"""

    username: Optional[str] = None
    password: Optional[str] = None
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_key: Optional[str] = None  # Required for agent authentication

    @validator("username")
    def validate_username(cls, v):
        if v is not None:
            if len(v) > 255:
                raise ValueError("username too long (max 255 characters)")
            # Remove empty validation that causes timing differences
            # Empty validation moved to endpoint for constant-time processing
        return v.strip() if v else v

    @validator("password")
    def validate_password(cls, v):
        if v is not None:
            if len(v) > 1024:
                raise ValueError("password too long (max 1024 characters)")
            if not v:
                raise ValueError("password cannot be empty")
        return v

    @validator("agent_id")
    def validate_agent_id(cls, v):
        if v is not None:
            if len(v) > 100:
                raise ValueError("agent_id too long (max 100 characters)")
            if not v or not v.strip():
                raise ValueError("agent_id cannot be empty")
            # Validate agent_id format (alphanumeric, underscore, hyphen only)
            if not re.match(r"^[a-zA-Z0-9_-]+$", v.strip()):
                raise ValueError(
                    "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
                )
        return v.strip() if v else v

    @validator("agent_type")
    def validate_agent_type(cls, v):
        if v is not None:
            if len(v) > 50:
                raise ValueError("agent_type too long (max 50 characters)")
            if not v or not v.strip():
                raise ValueError("agent_type cannot be empty")
            # Validate agent_type format
            if not re.match(r"^[a-zA-Z0-9_-]+$", v.strip()):
                raise ValueError(
                    "agent_type contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
                )
        return v.strip() if v else v

    @validator("agent_key")
    def validate_agent_key(cls, v):
        if v is not None:
            if len(v) > 200:
                raise ValueError("agent_key too long (max 200 characters)")
            # Remove length validation that causes timing differences
            # Length validation moved to endpoint for constant-time processing
        return v.strip() if v else v


class LoginResponse(BaseModel):
    """Response model for successful login"""

    access_token: str
    token_type: str
    expires_in: int
    agent_id: Optional[str] = None

    @validator("access_token")
    def validate_access_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("access_token cannot be empty")
        if len(v.strip()) < 16:
            raise ValueError("access_token too short (min 16 characters)")
        return v.strip()

    @validator("token_type")
    def validate_token_type(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("token_type cannot be empty")
        v_norm = v.strip().lower()
        if v_norm != "bearer":
            raise ValueError("token_type must be 'bearer'")
        return v_norm

    @validator("expires_in")
    def validate_expires_in(cls, v: int) -> int:
        if not isinstance(v, int):
            raise ValueError("expires_in must be an integer")
        if v <= 0:
            raise ValueError("expires_in must be positive")
        return v

    @validator("agent_id")
    def validate_agent_id_resp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v


class TempTokenResponse(BaseModel):
    """Response model for temporary token issuance"""

    temp_token: str
    token_type: str
    expires_in: int
    message: str

    @validator("temp_token")
    def validate_temp_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("temp_token cannot be empty")
        if len(v.strip()) < 16:
            raise ValueError("temp_token too short (min 16 characters)")
        return v.strip()

    @validator("token_type")
    def validate_token_type_temp(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("token_type cannot be empty")
        v_norm = v.strip().lower()
        if v_norm != "bearer":
            raise ValueError("token_type must be 'bearer'")
        return v_norm

    @validator("expires_in")
    def validate_expires_in_temp(cls, v: int) -> int:
        if not isinstance(v, int):
            raise ValueError("expires_in must be an integer")
        if v <= 0:
            raise ValueError("expires_in must be positive")
        return v

    @validator("message")
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        if len(v.strip()) > 500:
            raise ValueError("message too long (max 500 characters)")
        return v.strip()


class SetPinRequest(BaseModel):
    """Request model for setting session PIN"""

    pin: str

    @validator("pin")
    def validate_pin(cls, v):
        if not v:
            raise ValueError("PIN cannot be empty")
        if len(v) < 4:
            raise ValueError("PIN must be at least 4 characters")
        if len(v) > 32:
            raise ValueError("PIN must be no more than 32 characters")
        # Prevent common weak PINs
        weak_pins = [
            "1234",
            "0000",
            "1111",
            "2222",
            "3333",
            "4444",
            "5555",
            "6666",
            "7777",
            "8888",
            "9999",
            "password",
            "admin",
            "12345",
            "123456",
        ]
        if v.lower() in weak_pins:
            raise ValueError("PIN is too weak")
        return v


class VerifyPinRequest(BaseModel):
    """Request model for PIN verification"""

    pin: str

    @validator("pin")
    def validate_pin(cls, v):
        if not v:
            raise ValueError("PIN cannot be empty")
        if len(v) > 32:
            raise ValueError("PIN too long (max 32 characters)")
        return v
