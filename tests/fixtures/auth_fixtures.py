"""
Authentication-related test fixtures for ARCP tests.

Provides reusable authentication data, tokens, sessions, and user credentials.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
import pytest

from src.arcp.models.auth import (
    LoginRequest,
    LoginResponse,
    SetPinRequest,
    TempTokenResponse,
    VerifyPinRequest,
)
from src.arcp.models.token import TokenMintRequest, TokenResponse


@pytest.fixture
def admin_login_request() -> LoginRequest:
    """Sample admin login request."""
    return LoginRequest(username="admin", password="admin_password")


@pytest.fixture
def agent_login_request() -> LoginRequest:
    """Sample agent login request."""
    return LoginRequest(
        agent_id="test-agent-001",
        agent_type="security",
        agent_key="valid_agent_registration_key_12345",
    )


@pytest.fixture
def temp_token_request() -> LoginRequest:
    """Sample temporary token request for agent registration."""
    return LoginRequest(
        agent_id="new-agent-001",
        agent_type="automation",
        agent_key="valid_agent_registration_key_67890",
    )


@pytest.fixture
def invalid_login_requests() -> Dict[str, LoginRequest]:
    """Collection of invalid login requests for testing."""
    return {
        "missing_username": LoginRequest(password="password"),
        "missing_password": LoginRequest(username="admin"),
        "empty_username": LoginRequest(username="", password="password"),
        "empty_password": LoginRequest(username="admin", password=""),
        "invalid_agent_key": LoginRequest(
            agent_id="test-agent",
            agent_type="security",
            agent_key="invalid_key",
        ),
        "missing_agent_id": LoginRequest(agent_type="security", agent_key="valid_key"),
        "missing_agent_type": LoginRequest(
            agent_id="test-agent", agent_key="valid_key"
        ),
        "mixed_credentials": LoginRequest(
            username="admin", password="password", agent_id="test-agent"
        ),
    }


@pytest.fixture
def admin_login_response() -> LoginResponse:
    """Sample admin login response."""
    return LoginResponse(
        access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImFnZW50X2lkIjoidXNlcl9hZG1pbiIsInNjb3BlcyI6WyJhZG1pbiIsImFnZW50X21hbmFnZW1lbnQiXSwiZXhwIjoxNjQwOTk1MjAwfQ.test_signature",
        token_type="bearer",
        expires_in=3600,
        agent_id="user_admin",
    )


@pytest.fixture
def agent_login_response() -> LoginResponse:
    """Sample agent login response."""
    return LoginResponse(
        access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWFnZW50LTAwMSIsInJvbGUiOiJhZ2VudCIsImFnZW50X2lkIjoidGVzdC1hZ2VudC0wMDEiLCJzY29wZXMiOltdLCJleHAiOjE2NDA5OTUyMDB9.test_signature",
        token_type="bearer",
        expires_in=3600,
        agent_id="test-agent-001",
    )


@pytest.fixture
def temp_token_response() -> TempTokenResponse:
    """Sample temporary token response."""
    return TempTokenResponse(
        temp_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZW1wX25ld19hZ2VudF8wMDEiLCJhZ2VudF9pZCI6Im5ldy1hZ2VudC0wMDEiLCJhZ2VudF90eXBlIjoiYW5hbHl0aWNzIiwicm9sZSI6ImFnZW50IiwidGVtcF9yZWdpc3RyYXRpb24iOnRydWUsInVzZWRfa2V5IjoidmFsaWRfYWdlbnQifQ.temp_signature",
        token_type="bearer",
        expires_in=900,
        message="Temporary token issued. Use this token to complete agent registration.",
    )


@pytest.fixture
def token_mint_requests() -> Dict[str, TokenMintRequest]:
    """Sample token mint requests for different scenarios."""
    return {
        "admin": TokenMintRequest(
            user_id="admin",
            agent_id="user_admin",
            scopes=["admin", "agent_management"],
            role="admin",
        ),
        "agent": TokenMintRequest(
            user_id="test-agent-001",
            agent_id="test-agent-001",
            scopes=[],
            role="agent",
        ),
        "temp_registration": TokenMintRequest(
            user_id="temp_new-agent-001",
            agent_id="new-agent-001",
            scopes=[],
            role="agent",
            temp_registration=True,
        ),
    }


@pytest.fixture
def token_responses() -> Dict[str, TokenResponse]:
    """Sample token responses."""
    return {
        "admin": TokenResponse(
            access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.admin_token.signature",
            token_type="bearer",
            expires_in=3600,
        ),
        "agent": TokenResponse(
            access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.agent_token.signature",
            token_type="bearer",
            expires_in=3600,
        ),
        "temp": TokenResponse(
            access_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.temp_token.signature",
            token_type="bearer",
            expires_in=900,
        ),
    }


@pytest.fixture
def jwt_token_payloads() -> Dict[str, Dict[str, Any]]:
    """Sample JWT token payloads for different user types."""
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    return {
        "admin": {
            "sub": "admin",
            "role": "admin",
            "agent_id": "user_admin",
            "scopes": ["admin", "agent_management"],
            "exp": exp,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "iss": "arcp",
        },
        "agent": {
            "sub": "test-agent-001",
            "role": "agent",
            "agent_id": "test-agent-001",
            "scopes": [],
            "exp": exp,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "iss": "arcp",
        },
        "temp_registration": {
            "sub": "temp_new-agent-001",
            "role": "agent",
            "agent_id": "new-agent-001",
            "agent_type": "automation",
            "scopes": [],
            "temp_registration": True,
            "exp": int(
                (datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()
            ),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "iss": "arcp",
        },
        "expired": {
            "sub": "expired-user",
            "role": "agent",
            "agent_id": "expired-agent",
            "scopes": [],
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
            "iss": "arcp",
        },
    }


@pytest.fixture
def session_data() -> Dict[str, Dict[str, Any]]:
    """Sample session data for testing session management."""
    return {
        "admin_session": {
            "user_id": "admin",
            "ip": "192.168.1.100",
            "user_agent": "Mozilla/5.0 (Test Browser)",
            "client_fingerprint": "test_fingerprint_123",
            "token_ref": "admin_token_ref",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        },
        "agent_session": {
            "user_id": "test-agent-001",
            "ip": "10.0.0.1",
            "user_agent": "ARCP-Agent/1.0",
            "client_fingerprint": "agent_fingerprint_456",
            "token_ref": "agent_token_ref",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        },
    }


@pytest.fixture
def pin_requests() -> Dict[str, Any]:
    """Sample PIN-related requests."""
    return {
        "set_pin": SetPinRequest(pin="1234"),
        "verify_pin": VerifyPinRequest(pin="1234"),
        "invalid_short_pin": SetPinRequest(pin="12"),
        "invalid_long_pin": SetPinRequest(pin="a" * 33),
        "invalid_empty_pin": SetPinRequest(pin=""),
        "complex_pin": SetPinRequest(pin="Secure123!"),
    }


@pytest.fixture
def client_fingerprints() -> Dict[str, str]:
    """Sample client fingerprints for testing."""
    return {
        "chrome": "fp_chrome_browser_12345",
        "firefox": "fp_firefox_browser_67890",
        "agent": "fp_agent_client_abcdef",
        "mobile": "fp_mobile_app_ghijkl",
        "invalid": "",
        "long": "fp_" + "a" * 100,
    }


def create_jwt_token(payload: Dict[str, Any], secret: str = "test_secret") -> str:
    """Create a JWT token for testing."""
    return jwt.encode(payload, secret, algorithm="HS256")


def create_expired_token(user_id: str, role: str = "agent") -> str:
    """Create an expired JWT token for testing."""
    payload = {
        "sub": user_id,
        "role": role,
        "agent_id": user_id,
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    from src.arcp.core.config import config

    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def create_valid_token(
    user_id: str, role: str = "agent", expires_in_hours: int = 1
) -> str:
    """Create a valid JWT token for testing."""
    from src.arcp.core.config import config

    payload = {
        "sub": user_id,
        "role": role,
        "agent_id": user_id,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).timestamp()
        ),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "arcp",
    }
    # Use the actual JWT secret from config to match application validation
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def create_admin_token(username: str = "admin", expires_in_hours: int = 1) -> str:
    """Create a valid admin JWT token for testing."""
    return create_valid_token(f"user_{username}", "admin", expires_in_hours)


def create_temp_registration_token(
    agent_id: str, agent_type: str = "automation"
) -> str:
    """Create a temporary registration token for testing."""
    from src.arcp.core.config import config

    payload = {
        "sub": f"temp_{agent_id}",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "role": "agent",
        "temp_registration": True,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "arcp",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
