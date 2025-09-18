"""Token-related data models"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic import field_validator as validator


class TokenMintRequest(BaseModel):
    user_id: str = Field(..., description="User issuing the request")
    agent_id: str = Field(..., description="Agent for which to mint token")
    scopes: List[str] = Field(
        default_factory=list, description="Optional scopes for the token"
    )
    role: str = Field(default="user", description="User role (user, admin, agent)")
    temp_registration: bool = Field(
        default=False,
        description="Whether this is a temporary registration token",
    )
    agent_type: Optional[str] = Field(
        None, description="Agent type for temporary tokens"
    )
    used_key: Optional[str] = Field(
        None, description="Partial agent key used for tracking"
    )
    agent_key_hash: Optional[str] = Field(
        None, description="Hash of agent key for validation"
    )

    @validator("user_id")
    def validate_user_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("user_id must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("user_id too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_@.-]+$", v):
            raise ValueError(
                "user_id contains invalid characters (only alphanumeric, underscore, hyphen, at symbol, dot allowed)"
            )
        return v

    @validator("agent_id")
    def validate_agent_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        v = v.strip()
        if len(v) < 3:
            raise ValueError("agent_id must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v

    @validator("scopes")
    def validate_scopes(cls, v: List[str]) -> List[str]:
        if v is None:
            return []
        if len(v) > 50:
            raise ValueError("too many scopes (max 50)")
        validated: List[str] = []
        for scope in v:
            if not isinstance(scope, str):
                raise ValueError("scope must be a string")
            scope = scope.strip()
            if not scope:
                continue
            if len(scope) > 100:
                raise ValueError("scope too long (max 100 characters)")
            if not re.match(r"^[a-zA-Z0-9_.:-]+$", scope):
                raise ValueError(
                    "scope contains invalid characters (allowed: letters, numbers, underscore, dot, colon, hyphen)"
                )
            validated.append(scope)
        return validated

    @validator("role")
    def validate_role(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("role cannot be empty")
        v_norm = v.strip().lower()
        allowed = {"user", "admin", "agent"}
        if v_norm not in allowed:
            raise ValueError(f"role must be one of: {', '.join(sorted(allowed))}")
        return v_norm

    @validator("temp_registration")
    def validate_temp_registration(cls, v: bool) -> bool:
        if not isinstance(v, bool):
            raise ValueError("temp_registration must be a boolean")
        return v

    @validator("agent_type")
    def validate_agent_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("agent_type must be a string")
        v = v.strip()
        if not v:
            return None
        if len(v) < 2:
            raise ValueError("agent_type must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("agent_type too long (max 50 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_type contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v.lower()

    @validator("used_key")
    def validate_used_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("used_key must be a string")
        v = v.strip()
        if not v:
            return None
        if len(v) < 3:
            raise ValueError("used_key must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("used_key too long (max 100 characters)")
        # Allow more characters for partial keys (could include special chars)
        if not re.match(r"^[a-zA-Z0-9_@.-]+$", v):
            raise ValueError(
                "used_key contains invalid characters (only alphanumeric, underscore, hyphen, at symbol, dot allowed)"
            )
        return v

    @validator("agent_key_hash")
    def validate_agent_key_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("agent_key_hash must be a string")
        v = v.strip()
        if not v:
            return None
        # SHA256 hash should be exactly 64 characters
        if len(v) != 64:
            raise ValueError(
                "agent_key_hash must be exactly 64 characters (SHA256 hex)"
            )
        if not re.match(r"^[a-fA-F0-9]+$", v):
            raise ValueError(
                "agent_key_hash must be a valid hexadecimal string (SHA256 hash)"
            )
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Seconds until expiration")

    @validator("access_token")
    def validate_access_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("access_token cannot be empty")
        v = v.strip()
        if len(v) < 16:
            raise ValueError("access_token too short (min 16 characters)")
        if len(v) > 8192:
            raise ValueError("access_token too long (max 8192 characters)")
        return v

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
        if v > 31_536_000:  # 365 days
            raise ValueError("expires_in too large (max 31,536,000 seconds ~ 365 days)")
        return v
