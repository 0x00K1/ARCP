"""
Unit tests for ARCP token service module.
"""

import pytest

from src.arcp.core.token_service import TokenService
from src.arcp.models.token import TokenMintRequest, TokenResponse


@pytest.mark.unit
class TestTokenService:
    """Test suite for TokenService class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.token_service = TokenService(
            secret="test-secret-key", algo="HS256", expire_minutes=60
        )

    def test_mint_token_basic(self):
        """Test basic token minting functionality."""
        request = TokenMintRequest(
            user_id="test-user",
            agent_id="test-agent",
            scopes=["read", "write"],
        )

        response = self.token_service.mint_token(request)

        assert isinstance(response, TokenResponse)
        assert response.access_token is not None
        assert response.token_type == "bearer"
        assert response.expires_in == 3600  # 60 minutes in seconds

        # Check that the scopes are in the token payload
        payload = self.token_service.validate_token(response.access_token)
        assert "read" in payload["scopes"]
        assert "write" in payload["scopes"]

    def test_validate_token_success(self):
        """Test successful token validation."""
        # First mint a token
        request = TokenMintRequest(
            user_id="test-user", agent_id="test-agent", scopes=["read"]
        )

        response = self.token_service.mint_token(request)
        payload = self.token_service.validate_token(response.access_token)

        assert payload["sub"] == "test-user"
        assert payload["agent_id"] == "test-agent"
        assert payload["scopes"] == ["read"]
        assert "exp" in payload
        assert "iat" in payload
