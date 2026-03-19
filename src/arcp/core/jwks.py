"""
JWKS (JSON Web Key Set) Service for ARCP.

Provides JWKS management including key retrieval, public key export,
and integration with the KeyManager for signing operations.

This module serves as the primary interface for JWKS operations,
abstracting away key management complexities.

Example Usage:
    >>> from arcp.core.jwks import get_jwks_service
    >>> service = get_jwks_service()
    >>> await service.initialize()
    >>> jwks = await service.get_jwks()
    >>> print(jwks)  # {"keys": [{"kty": "OKP", "crv": "Ed25519", ...}]}
"""

import logging
from typing import Any, Dict, Optional

from ..core.config import config
from ..utils.key_manager import JWKWrapper, KeyManager, get_key_manager

logger = logging.getLogger(__name__)


class JWKSService:
    """
    JWKS Service for managing JSON Web Key Sets.

    Provides:
    - JWKS endpoint data generation
    - Active key retrieval for signing
    - Key lookup by kid for verification
    - ARCP configuration metadata

    Note: This service provides both async and sync key access methods.
    The sync methods (_cached_signing_key, get_signing_key_sync, get_verification_key_sync)
    use cached values updated during initialization and key rotation.
    """

    def __init__(self, key_manager: Optional[KeyManager] = None):
        """
        Initialize JWKS service.

        Args:
            key_manager: Optional KeyManager instance (uses singleton if not provided)
        """
        self._key_manager = key_manager
        self._initialized = False
        # Cached keys for synchronous access
        self._cached_signing_key: Optional[JWKWrapper] = None
        self._cached_keys: Dict[str, JWKWrapper] = {}  # kid -> JWKWrapper

    @property
    def key_manager(self) -> KeyManager:
        """Get the KeyManager instance."""
        if self._key_manager is None:
            self._key_manager = get_key_manager()
        return self._key_manager

    @property
    def is_enabled(self) -> bool:
        """Check if JWKS is enabled."""
        return getattr(config, "JWKS_ENABLED", False)

    async def initialize(self) -> None:
        """Initialize the JWKS service and underlying KeyManager."""
        if self._initialized:
            return

        if not self.is_enabled:
            logger.info("JWKS is disabled, skipping initialization")
            return

        await self.key_manager.initialize()
        self._initialized = True

        # Cache keys for synchronous access
        await self._update_key_cache()
        logger.info("JWKS service initialized")

    async def _update_key_cache(self) -> None:
        """Update cached keys from key manager."""
        try:
            self._cached_signing_key = await self.key_manager.get_active_key()

            # Cache all keys by kid
            jwks = await self.key_manager.get_jwks()
            for key_dict in jwks.get("keys", []):
                kid = key_dict.get("kid")
                if kid:
                    key = await self.key_manager.get_key_by_kid(kid)
                    if key:
                        self._cached_keys[kid] = key

            logger.debug(
                f"Key cache updated: signing_key={self._cached_signing_key.kid if self._cached_signing_key else None}, cached_keys={list(self._cached_keys.keys())}"
            )
        except Exception as e:
            logger.warning(f"Failed to update key cache: {e}")

    def get_signing_key_sync(self) -> Optional[JWKWrapper]:
        """
        Get the current active signing key synchronously.

        Uses cached value from initialization. For real-time access, use get_signing_key().

        Returns:
            JWKWrapper for signing, or None if JWKS disabled or not initialized
        """
        if not self.is_enabled or not self._initialized:
            return None
        return self._cached_signing_key

    def get_verification_key_sync(self, kid: str) -> Optional[JWKWrapper]:
        """
        Get a key for verification by its kid synchronously.

        Uses cached values from initialization. For real-time access, use get_verification_key().

        Args:
            kid: Key ID from JWT header

        Returns:
            JWKWrapper for verification, or None if not found
        """
        if not self.is_enabled or not self._initialized:
            return None
        return self._cached_keys.get(kid)

    async def get_jwks(self) -> Dict[str, Any]:
        """
        Get the JWKS (JSON Web Key Set) for public consumption.

        Returns:
            Dict containing 'keys' array with public JWKs
        """
        if not self.is_enabled:
            return {"keys": []}

        return await self.key_manager.get_jwks()

    async def get_signing_key(self) -> Optional[JWKWrapper]:
        """
        Get the current active signing key.

        Returns:
            JWKWrapper for signing, or None if JWKS disabled
        """
        if not self.is_enabled:
            return None

        return await self.key_manager.get_active_key()

    async def get_verification_key(self, kid: str) -> Optional[JWKWrapper]:
        """
        Get a key for verification by its kid.

        Args:
            kid: Key ID from JWT header

        Returns:
            JWKWrapper for verification, or None if not found
        """
        if not self.is_enabled:
            return None

        return await self.key_manager.get_key_by_kid(kid)

    async def rotate_keys(self) -> Optional[str]:
        """
        Trigger key rotation.

        Returns:
            New kid, or None if JWKS disabled
        """
        if not self.is_enabled:
            return None

        new_kid = await self.key_manager.rotate_keys()

        # Update cache after rotation
        await self._update_key_cache()

        return new_kid

    def get_arcp_configuration(self) -> Dict[str, Any]:
        """
        Get ARCP server configuration for discovery.

        Returns OpenID Connect-style metadata for ARCP.
        """
        base_url = getattr(config, "ARCP_ISSUER", "https://arcp.example.com")

        # Determine supported algorithms
        algorithms = []
        if self.is_enabled:
            algo = getattr(config, "JWKS_ALGORITHM", "EdDSA")
            algorithms.append(algo)
            # Also support HS256 for backward compat
            algorithms.append("HS256")
        else:
            algorithms.append("HS256")

        return {
            "issuer": base_url,
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "token_endpoint": f"{base_url}/auth/agent/request_temp_token",
            "validation_endpoint": f"{base_url}/auth/agent/validate_compliance",
            "registration_endpoint": f"{base_url}/agents/register",
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
            "id_token_signing_alg_values_supported": algorithms,
            "dpop_signing_alg_values_supported": ["EdDSA", "ES256"],
            "response_types_supported": ["token"],
            "grant_types_supported": ["client_credentials"],
            "three_phase_registration_enabled": getattr(
                config, "FEATURE_THREE_PHASE", False
            ),
            "service_version": getattr(config, "SERVICE_VERSION", "2.1.2"),
        }

    async def get_active_kid(self) -> Optional[str]:
        """
        Get the current active key ID.

        Useful for including in token headers.
        """
        if not self.is_enabled:
            return None

        key = await self.key_manager.get_active_key()
        return key.kid if key else None

    async def cleanup(self) -> int:
        """
        Cleanup expired keys.

        Returns:
            Number of keys removed
        """
        if not self.is_enabled:
            return 0

        return await self.key_manager.cleanup_expired_keys()


# Singleton instance
_jwks_service: Optional[JWKSService] = None


def get_jwks_service() -> JWKSService:
    """
    Get the singleton JWKSService instance.

    Returns:
        JWKSService instance
    """
    global _jwks_service
    if _jwks_service is None:
        _jwks_service = JWKSService()
    return _jwks_service


async def initialize_jwks_service() -> JWKSService:
    """
    Initialize and return the JWKSService.

    Creates initial key if none exists.
    """
    service = get_jwks_service()
    await service.initialize()
    return service
