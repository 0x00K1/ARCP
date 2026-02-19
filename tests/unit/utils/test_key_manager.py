"""
Unit tests for KeyManager (JWKS).

Tests cryptographic key generation, rotation, and JWK operations.
"""

from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arcp.utils.key_manager import JWKWrapper, KeyManager, get_key_manager


def generate_ed25519_key():
    """Helper to generate Ed25519 key pair for testing."""
    private_key = Ed25519PrivateKey.generate()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


def generate_es256_key():
    """Helper to generate ES256 (P-256) key pair for testing."""
    private_key = ec.generate_private_key(ec.SECP256R1())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


class TestJWKWrapper:
    """Tests for JWKWrapper class."""

    def test_create_eddsa_wrapper(self):
        """Test creating an EdDSA (Ed25519) key wrapper."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-001",
        )

        assert wrapper is not None
        assert wrapper.kid == "test-key-001"
        assert wrapper.algorithm == "EdDSA"
        assert wrapper.private_key_bytes == private_pem
        assert wrapper.public_key_bytes == public_pem

    def test_create_es256_wrapper(self):
        """Test creating an ES256 (P-256) key wrapper."""
        private_pem, public_pem = generate_es256_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="ES256",
            kid="test-key-002",
        )

        assert wrapper is not None
        assert wrapper.kid == "test-key-002"
        assert wrapper.algorithm == "ES256"

    def test_private_key_property_eddsa(self):
        """Test getting EdDSA private key from wrapper."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-003",
        )

        private_key = wrapper.private_key

        assert private_key is not None
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        assert isinstance(private_key, Ed25519PrivateKey)

    def test_public_key_property_eddsa(self):
        """Test getting EdDSA public key from wrapper."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-004",
        )

        public_key = wrapper.public_key

        assert public_key is not None
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        assert isinstance(public_key, Ed25519PublicKey)

    def test_to_public_jwk_eddsa(self):
        """Test exporting EdDSA public key as JWK."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-005",
        )

        public_jwk = wrapper.to_public_jwk()

        assert public_jwk["kty"] == "OKP"
        assert public_jwk["crv"] == "Ed25519"
        assert public_jwk["kid"] == "test-key-005"
        assert public_jwk["use"] == "sig"
        assert public_jwk["alg"] == "EdDSA"
        assert "x" in public_jwk
        # Private key component should NOT be present
        assert "d" not in public_jwk

    def test_to_public_jwk_es256(self):
        """Test exporting ES256 public key as JWK."""
        private_pem, public_pem = generate_es256_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="ES256",
            kid="test-key-006",
        )

        public_jwk = wrapper.to_public_jwk()

        assert public_jwk["kty"] == "EC"
        assert public_jwk["crv"] == "P-256"
        assert public_jwk["kid"] == "test-key-006"
        assert public_jwk["alg"] == "ES256"
        assert "x" in public_jwk
        assert "y" in public_jwk
        # Private key component should NOT be present
        assert "d" not in public_jwk

    def test_thumbprint_eddsa(self):
        """Test computing JWK thumbprint (RFC 7638) for EdDSA."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-007",
        )

        thumbprint = wrapper.thumbprint()

        assert thumbprint is not None
        assert len(thumbprint) > 20  # Base64url SHA-256
        # Thumbprint should be consistent
        assert thumbprint == wrapper.thumbprint()

    def test_thumbprint_es256(self):
        """Test computing JWK thumbprint (RFC 7638) for ES256."""
        private_pem, public_pem = generate_es256_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="ES256",
            kid="test-key-008",
        )

        thumbprint = wrapper.thumbprint()

        assert thumbprint is not None
        assert len(thumbprint) > 20  # Base64url SHA-256

    def test_sign_and_verify_eddsa(self):
        """Test signing and verifying with EdDSA."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-009",
        )

        message = b"test message for signing"
        signature = wrapper.private_key.sign(message)

        # Verify with public key - no exception = success
        wrapper.public_key.verify(signature, message)

    def test_to_storage_dict(self):
        """Test serialization to storage dict."""
        private_pem, public_pem = generate_ed25519_key()

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-010",
        )

        data = wrapper.to_storage_dict()

        assert "private_key" in data
        assert "public_key" in data
        assert "algorithm" in data
        assert "kid" in data
        assert data["algorithm"] == "EdDSA"
        assert data["kid"] == "test-key-010"

    def test_from_storage_dict(self):
        """Test deserialization from storage dict."""
        private_pem, public_pem = generate_ed25519_key()

        original = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm="EdDSA",
            kid="test-key-011",
        )

        data = original.to_storage_dict()
        restored = JWKWrapper.from_storage_dict(data)

        assert restored.kid == original.kid
        assert restored.algorithm == original.algorithm
        # Keys should produce same thumbprint
        assert restored.thumbprint() == original.thumbprint()


class TestKeyManager:
    """Tests for KeyManager class."""

    @pytest.fixture
    async def key_manager(self):
        """Create a KeyManager for testing with mocked config."""
        import asyncio

        # Use start/stop pattern for proper async handling
        config_patcher = patch("arcp.utils.key_manager.config")
        redis_patcher = patch("arcp.utils.key_manager.get_redis_service")

        mock_config = config_patcher.start()
        mock_redis = redis_patcher.start()

        # Mock Redis to avoid connection attempts
        mock_redis.side_effect = Exception("Redis not available in test")

        mock_config.JWKS_ALGORITHM = "EdDSA"
        mock_config.JWKS_ROTATION_DAYS = 30
        mock_config.JWKS_OVERLAP_DAYS = 7

        manager = KeyManager()
        # Reset instance state for clean tests
        manager._keys = {}
        manager._active_kid = None
        manager._initialized = False
        manager._redis = None
        # Create fresh lock in async context
        manager._lock = asyncio.Lock()

        yield manager

        # Cleanup
        config_patcher.stop()
        redis_patcher.stop()

    def test_initialization(self, key_manager):
        """Test KeyManager initializes with config values."""
        assert key_manager.algorithm == "EdDSA"
        assert key_manager.rotation_days == 30
        assert key_manager.overlap_days == 7
        assert key_manager._initialized is False

    @pytest.mark.asyncio
    async def test_generate_key_pair_eddsa(self, key_manager):
        """Test generating EdDSA key pair."""
        kid, wrapper = await key_manager.generate_key_pair()

        assert kid is not None
        assert kid.startswith("arcp-")
        assert wrapper is not None
        assert wrapper.algorithm == "EdDSA"
        assert wrapper.kid == kid

    @pytest.mark.asyncio
    async def test_generate_key_pair_es256(self, key_manager):
        """Test generating ES256 key pair."""
        key_manager.algorithm = "ES256"

        kid, wrapper = await key_manager.generate_key_pair()

        assert kid is not None
        assert wrapper is not None
        assert wrapper.algorithm == "ES256"

    @pytest.mark.asyncio
    async def test_rotate_keys(self, key_manager):
        """Test key rotation creates new active key."""
        new_kid = await key_manager.rotate_keys()

        assert new_kid is not None
        assert new_kid.startswith("arcp-")
        assert key_manager._active_kid == new_kid

    @pytest.mark.asyncio
    async def test_rotate_keys_multiple(self, key_manager):
        """Test multiple key rotations."""
        first_kid = await key_manager.rotate_keys()
        second_kid = await key_manager.rotate_keys()

        assert first_kid != second_kid
        assert key_manager._active_kid == second_kid

    @pytest.mark.asyncio
    async def test_get_active_key(self, key_manager):
        """Test getting active key after rotation."""
        await key_manager.rotate_keys()

        active_key = await key_manager.get_active_key()

        assert active_key is not None
        assert active_key.kid == key_manager._active_kid

    @pytest.mark.asyncio
    async def test_get_active_key_none_before_rotation(self, key_manager):
        """Test get_active_key returns None when no keys exist."""
        active_key = await key_manager.get_active_key()
        assert active_key is None

    @pytest.mark.asyncio
    async def test_get_key_by_kid(self, key_manager):
        """Test retrieving a specific key by kid."""
        kid = await key_manager.rotate_keys()

        retrieved = await key_manager.get_key_by_kid(kid)

        assert retrieved is not None
        assert retrieved.kid == kid

    @pytest.mark.asyncio
    async def test_get_key_by_kid_not_found(self, key_manager):
        """Test get_key_by_kid returns None for unknown kid."""
        result = await key_manager.get_key_by_kid("unknown-kid-12345678")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_valid_keys(self, key_manager):
        """Test getting all non-expired keys."""
        await key_manager.rotate_keys()
        await key_manager.rotate_keys()

        all_keys = await key_manager.get_all_valid_keys()

        assert len(all_keys) >= 1

    @pytest.mark.asyncio
    async def test_get_jwks(self, key_manager):
        """Test generating JWKS format."""
        await key_manager.rotate_keys()

        jwks = await key_manager.get_jwks()

        assert "keys" in jwks
        assert len(jwks["keys"]) >= 1

        # Check first key has required fields
        first_key = jwks["keys"][0]
        assert "kty" in first_key
        assert "kid" in first_key
        assert "use" in first_key
        assert "alg" in first_key

    @pytest.mark.asyncio
    async def test_initialize_creates_key_if_none(self, key_manager):
        """Test initialize creates initial key if none exists."""
        await key_manager.initialize()

        assert key_manager._initialized is True
        assert key_manager._active_kid is not None

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, key_manager):
        """Test initialize is idempotent."""
        await key_manager.initialize()
        first_kid = key_manager._active_kid

        await key_manager.initialize()

        assert key_manager._active_kid == first_kid

    @pytest.mark.asyncio
    async def test_cleanup_expired_keys(self, key_manager):
        """Test cleaning up expired keys."""
        # Create a key
        await key_manager.rotate_keys()

        # Cleanup (should not remove non-expired keys)
        removed = await key_manager.cleanup_expired_keys()

        assert removed == 0

    def test_get_key_manager_singleton(self):
        """Test get_key_manager returns singleton instance."""
        with patch("arcp.utils.key_manager._key_manager", None):
            manager1 = get_key_manager()
            manager2 = get_key_manager()

            assert manager1 is manager2
