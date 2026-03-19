"""
Unit tests for JWKS Service.

Tests JWKS service layer and endpoint functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcp.core.jwks import JWKSService, get_jwks_service
from arcp.utils.key_manager import KeyManager


class TestJWKSService:
    """Tests for JWKSService class."""

    @pytest.fixture
    def mock_key_manager(self):
        """Create a mock KeyManager."""
        manager = MagicMock(spec=KeyManager)
        manager.algorithm = "EdDSA"
        manager.rotation_days = 30
        manager.overlap_days = 7
        manager._initialized = False
        manager.initialize = AsyncMock()
        manager.get_jwks = AsyncMock(return_value={"keys": []})
        manager.get_active_key = AsyncMock(return_value=None)
        manager.get_key_by_kid = AsyncMock(return_value=None)
        manager.rotate_keys = AsyncMock(return_value="arcp-test-key-001")
        manager.cleanup_expired_keys = AsyncMock(return_value=0)
        return manager

    @pytest.fixture
    def jwks_service(self, mock_key_manager):
        """Create a JWKSService for testing."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True
            mock_config.JWKS_ALGORITHM = "EdDSA"
            mock_config.ARCP_ISSUER = "https://arcp.example.com"
            mock_config.FEATURE_THREE_PHASE = True
            mock_config.SERVICE_VERSION = "2.1.2"

            service = JWKSService(key_manager=mock_key_manager)
            yield service

    def test_initialization(self, jwks_service, mock_key_manager):
        """Test JWKSService initializes correctly."""
        assert jwks_service.key_manager is mock_key_manager
        assert jwks_service._initialized is False

    def test_is_enabled_true(self, jwks_service):
        """Test is_enabled returns True when JWKS is enabled."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True
            assert jwks_service.is_enabled is True

    def test_is_enabled_false(self):
        """Test is_enabled returns False when JWKS is disabled."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = False
            service = JWKSService()
            assert service.is_enabled is False

    @pytest.mark.asyncio
    async def test_initialize(self, jwks_service, mock_key_manager):
        """Test initialize calls KeyManager.initialize."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            await jwks_service.initialize()

            mock_key_manager.initialize.assert_called_once()
            assert jwks_service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, jwks_service, mock_key_manager):
        """Test initialize is idempotent."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            await jwks_service.initialize()
            await jwks_service.initialize()

            # Should only be called once
            assert mock_key_manager.initialize.call_count == 1

    @pytest.mark.asyncio
    async def test_get_jwks(self, jwks_service, mock_key_manager):
        """Test getting JWKS document."""
        expected_jwks = {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "kid": "test-key-001",
                    "use": "sig",
                    "alg": "EdDSA",
                    "x": "test-x-value",
                }
            ]
        }
        mock_key_manager.get_jwks = AsyncMock(return_value=expected_jwks)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            jwks = await jwks_service.get_jwks()

        assert "keys" in jwks
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["alg"] == "EdDSA"

    @pytest.mark.asyncio
    async def test_get_jwks_disabled(self):
        """Test get_jwks returns empty keys when disabled."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = False

            service = JWKSService()
            jwks = await service.get_jwks()

        assert jwks == {"keys": []}

    @pytest.mark.asyncio
    async def test_get_signing_key(self, jwks_service, mock_key_manager):
        """Test getting the current signing key."""
        mock_key = MagicMock()
        mock_key.kid = "signing-key-001"
        mock_key_manager.get_active_key = AsyncMock(return_value=mock_key)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            key = await jwks_service.get_signing_key()

        assert key is not None
        assert key.kid == "signing-key-001"

    @pytest.mark.asyncio
    async def test_get_verification_key(self, jwks_service, mock_key_manager):
        """Test getting a verification key by kid."""
        mock_key = MagicMock()
        mock_key.kid = "verify-key-001"
        mock_key_manager.get_key_by_kid = AsyncMock(return_value=mock_key)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            key = await jwks_service.get_verification_key("verify-key-001")

        assert key is not None
        assert key.kid == "verify-key-001"
        mock_key_manager.get_key_by_kid.assert_called_with("verify-key-001")

    @pytest.mark.asyncio
    async def test_get_verification_key_not_found(self, jwks_service, mock_key_manager):
        """Test get_verification_key returns None for unknown kid."""
        mock_key_manager.get_key_by_kid = AsyncMock(return_value=None)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            key = await jwks_service.get_verification_key("unknown-kid")

        assert key is None

    @pytest.mark.asyncio
    async def test_rotate_keys(self, jwks_service, mock_key_manager):
        """Test key rotation."""
        mock_key_manager.rotate_keys = AsyncMock(return_value="new-key-001")

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            new_kid = await jwks_service.rotate_keys()

        assert new_kid == "new-key-001"
        mock_key_manager.rotate_keys.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_keys_disabled(self):
        """Test rotate_keys returns None when disabled."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = False

            service = JWKSService()
            result = await service.rotate_keys()

        assert result is None

    def test_get_arcp_configuration(self, jwks_service):
        """Test getting ARCP configuration document."""
        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.ARCP_ISSUER = "https://arcp.example.com"
            mock_config.JWKS_ENABLED = True
            mock_config.JWKS_ALGORITHM = "EdDSA"
            mock_config.FEATURE_THREE_PHASE = True
            mock_config.SERVICE_VERSION = "2.1.2"

            config_doc = jwks_service.get_arcp_configuration()

        assert "issuer" in config_doc
        assert config_doc["issuer"] == "https://arcp.example.com"

        assert "jwks_uri" in config_doc
        assert "/.well-known/jwks.json" in config_doc["jwks_uri"]

        assert "token_endpoint" in config_doc
        assert "dpop_signing_alg_values_supported" in config_doc

    @pytest.mark.asyncio
    async def test_get_active_kid(self, jwks_service, mock_key_manager):
        """Test getting active key ID."""
        mock_key = MagicMock()
        mock_key.kid = "active-key-001"
        mock_key_manager.get_active_key = AsyncMock(return_value=mock_key)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            kid = await jwks_service.get_active_kid()

        assert kid == "active-key-001"

    @pytest.mark.asyncio
    async def test_cleanup(self, jwks_service, mock_key_manager):
        """Test cleanup expired keys."""
        mock_key_manager.cleanup_expired_keys = AsyncMock(return_value=2)

        with patch("arcp.core.jwks.config") as mock_config:
            mock_config.JWKS_ENABLED = True

            removed = await jwks_service.cleanup()

        assert removed == 2


class TestGetJWKSService:
    """Tests for get_jwks_service singleton."""

    def test_returns_service(self):
        """Test get_jwks_service returns a JWKSService."""
        with patch("arcp.core.jwks._jwks_service", None):
            service = get_jwks_service()
            assert isinstance(service, JWKSService)

    def test_returns_same_instance(self):
        """Test get_jwks_service returns the same instance."""
        with patch("arcp.core.jwks._jwks_service", None):
            s1 = get_jwks_service()
            s2 = get_jwks_service()
            assert s1 is s2
