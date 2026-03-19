"""
Cryptographic Key Manager for ARCP.

Manages asymmetric key pairs (EdDSA/ES256) for JWT signing with automatic rotation.
Keys are stored in Redis with graceful fallback to in-memory storage.

Features:
- EdDSA (Ed25519) and ES256 key generation
- Automatic key rotation with overlap period
- Redis-backed storage with in-memory fallback
- Thread-safe singleton pattern

Environment Variables:
    JWKS_ENABLED: Enable asymmetric signing (default: false)
    JWKS_ALGORITHM: Algorithm to use (EdDSA or ES256, default: EdDSA)
    JWKS_ROTATION_DAYS: Days between key rotations (default: 30)
    JWKS_OVERLAP_DAYS: Days old keys remain valid (default: 7)

Example Usage:
    >>> from arcp.utils.key_manager import get_key_manager
    >>> km = get_key_manager()
    >>> await km.initialize()
    >>> key = await km.get_active_key()
    >>> print(key.kid)  # 'arcp-20260130-a1b2c3d4'
"""

import asyncio
import base64
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..core.config import config
from ..services import get_redis_service
from .security_audit import SecurityEventType, log_key_event

logger = logging.getLogger(__name__)

# Redis key prefixes
JWKS_KEY_PREFIX = "arcp:jwks:"
JWKS_ACTIVE_KEY = "arcp:jwks:active"
JWKS_KEYS_HASH = "arcp:jwks:keys"
JWKS_REVOKED_HASH = "arcp:jwks:revoked"


@dataclass
class KeyRevocationInfo:
    """Information about a revoked key."""

    kid: str
    reason: str
    revoked_at: datetime
    revoked_by: Optional[str] = None


@dataclass
class KeyMetadata:
    """Metadata for a stored key."""

    kid: str
    algorithm: str
    created_at: datetime
    expires_at: datetime
    status: str  # 'active', 'rotating', 'expired'


class JWKWrapper:
    """
    Wrapper around a JSON Web Key with convenience methods.

    Uses jwcrypto for JWK operations when available, with fallback
    to PyJWT-compatible format.
    """

    def __init__(
        self,
        private_key_bytes: bytes,
        public_key_bytes: bytes,
        algorithm: str,
        kid: str,
    ):
        self.private_key_bytes = private_key_bytes
        self.public_key_bytes = public_key_bytes
        self.algorithm = algorithm
        self.kid = kid
        self._private_key = None
        self._public_key = None

    @property
    def private_key(self):
        """Get the private key object for signing."""
        if self._private_key is None:
            self._private_key = serialization.load_pem_private_key(
                self.private_key_bytes, password=None
            )
        return self._private_key

    @property
    def public_key(self):
        """Get the public key object for verification."""
        if self._public_key is None:
            self._public_key = serialization.load_pem_public_key(self.public_key_bytes)
        return self._public_key

    def thumbprint(self) -> str:
        """
        Compute JWK Thumbprint per RFC 7638.

        Returns base64url-encoded SHA-256 hash of the canonical JWK.
        """
        # Get public key in JWK format
        jwk_dict = self.to_public_jwk()

        # Create canonical representation per RFC 7638
        # Must include only required members in lexicographic order
        if self.algorithm == "EdDSA":
            canonical = {
                "crv": jwk_dict.get("crv", "Ed25519"),
                "kty": "OKP",
                "x": jwk_dict["x"],
            }
        else:  # ES256
            canonical = {
                "crv": jwk_dict.get("crv", "P-256"),
                "kty": "EC",
                "x": jwk_dict["x"],
                "y": jwk_dict["y"],
            }

        # Sort keys and serialize
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

        # SHA-256 hash
        digest = hashlib.sha256(canonical_json.encode()).digest()

        # Base64url encode
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def to_public_jwk(self) -> Dict[str, Any]:
        """Export public key as JWK dictionary."""
        pub_key = self.public_key

        if self.algorithm == "EdDSA":
            # Ed25519 public key
            raw_bytes = pub_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode(),
                "kid": self.kid,
                "use": "sig",
                "alg": "EdDSA",
            }
        else:
            numbers = pub_key.public_numbers()

            # Convert to 32-byte big-endian
            x_bytes = numbers.x.to_bytes(32, byteorder="big")
            y_bytes = numbers.y.to_bytes(32, byteorder="big")

            return {
                "kty": "EC",
                "crv": "P-256",
                "x": base64.urlsafe_b64encode(x_bytes).rstrip(b"=").decode(),
                "y": base64.urlsafe_b64encode(y_bytes).rstrip(b"=").decode(),
                "kid": self.kid,
                "use": "sig",
                "alg": "ES256",
            }

    def to_storage_dict(self) -> Dict[str, Any]:
        """Serialize key for storage."""
        return {
            "private_key": base64.b64encode(self.private_key_bytes).decode(),
            "public_key": base64.b64encode(self.public_key_bytes).decode(),
            "algorithm": self.algorithm,
            "kid": self.kid,
        }

    @classmethod
    def from_storage_dict(cls, data: Dict[str, Any]) -> "JWKWrapper":
        """Deserialize key from storage."""
        return cls(
            private_key_bytes=base64.b64decode(data["private_key"]),
            public_key_bytes=base64.b64decode(data["public_key"]),
            algorithm=data["algorithm"],
            kid=data["kid"],
        )


class KeyManager:
    """
    Manages cryptographic keys for ARCP JWT signing.

    Supports:
    - EdDSA (Ed25519): Fast, secure, no RNG needed for signing
    - ES256 (P-256): FIPS-approved, widely compatible

    Keys are stored in Redis with automatic rotation and overlap periods.
    """

    def __init__(self):
        self.algorithm = getattr(config, "JWKS_ALGORITHM", "EdDSA")
        self.rotation_days = getattr(config, "JWKS_ROTATION_DAYS", 30)
        self.overlap_days = getattr(config, "JWKS_OVERLAP_DAYS", 7)
        self._redis = None
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._revoked_keys: Dict[str, Dict[str, Any]] = {}
        self._active_kid: Optional[str] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    def _get_redis(self):
        """Get Redis client, cached."""
        if self._redis is None:
            try:
                redis_service = get_redis_service()
                self._redis = redis_service.get_client()
            except Exception as e:
                logger.warning(f"Redis unavailable for JWKS: {e}")
        return self._redis

    async def _audit_key_event(
        self,
        event: str,
        kid: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log JWKS key event to security audit service."""
        try:
            event_map = {
                "generated": SecurityEventType.JWKS_KEY_GENERATED,
                "rotated": SecurityEventType.JWKS_KEY_ROTATED,
                "revoked": SecurityEventType.JWKS_KEY_REVOKED,
                "expired": SecurityEventType.JWKS_KEY_EXPIRED,
                "access": SecurityEventType.JWKS_ACCESS,
                "revoked_key_used": SecurityEventType.JWKS_REVOKED_KEY_USED,
            }

            event_type = event_map.get(event, SecurityEventType.JWKS_ACCESS)
            reason = details.get("reason") if details else None
            await log_key_event(event_type, kid, reason=reason)
        except Exception as e:
            logger.debug(f"Failed to audit key event: {e}")

    async def initialize(self) -> None:
        """
        Initialize the key manager.

        Creates initial key if none exists.
        """
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True

        # Check for existing non-expired active key (outside lock to avoid deadlock)
        active_key = await self.get_active_key()

        if active_key is None:
            # Generate initial key (rotate_keys acquires its own lock)
            logger.info("No active JWKS key found, generating initial key")
            await self.rotate_keys()

        logger.info(f"KeyManager initialized with algorithm={self.algorithm}")

    async def generate_key_pair(self) -> Tuple[str, JWKWrapper]:
        """
        Generate a new key pair.

        Returns:
            Tuple of (kid, JWKWrapper)
        """
        # Generate unique kid
        kid = f"arcp-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

        if self.algorithm == "EdDSA":
            private_key = Ed25519PrivateKey.generate()
        else:
            private_key = ec.generate_private_key(ec.SECP256R1())

        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        wrapper = JWKWrapper(
            private_key_bytes=private_pem,
            public_key_bytes=public_pem,
            algorithm=self.algorithm,
            kid=kid,
        )

        logger.info(f"Generated new {self.algorithm} key with kid={kid}")

        # Audit the key generation
        await self._audit_key_event("generated", kid)

        return kid, wrapper

    async def rotate_keys(self) -> str:
        """
        Rotate signing keys with overlap period.

        - Generates new active key
        - Marks old active as 'rotating'
        - Returns new kid
        """
        async with self._lock:
            now = datetime.utcnow()
            old_kid = self._active_kid

            # Mark existing active key as rotating
            await self._transition_old_keys()

            # Generate new key
            kid, key_wrapper = await self.generate_key_pair()

            # Prepare key data for storage
            key_data = {
                "key": key_wrapper.to_storage_dict(),
                "created_at": now.isoformat(),
                "expires_at": (
                    now + timedelta(days=self.rotation_days + self.overlap_days)
                ).isoformat(),
                "status": "active",
            }

            # Store key
            await self._store_key(kid, key_data)
            await self._set_active_kid(kid)

            # Audit the key rotation
            await self._audit_key_event("rotated", kid, details={"old_kid": old_kid})

            logger.info(f"Key rotation complete. New active key: {kid}")
            return kid

    async def _transition_old_keys(self) -> None:
        """Mark old active key as rotating."""
        current_active = self._active_kid
        if current_active:
            # Update status to rotating
            key_data = await self._get_key_data(current_active)
            if key_data:
                key_data["status"] = "rotating"
                await self._store_key(current_active, key_data)

    async def _store_key(self, kid: str, key_data: Dict[str, Any]) -> None:
        """Store key in Redis or memory."""
        # Always mirror in memory so verification/JWKS can still function if Redis
        # is temporarily unavailable or out-of-sync.
        self._keys[kid] = key_data

        redis = self._get_redis()

        if redis:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hset(JWKS_KEYS_HASH, kid, json.dumps(key_data))
                )
                return
            except Exception as e:
                logger.warning(f"Redis store failed, using memory: {e}")

    async def _get_key_data(self, kid: str) -> Optional[Dict[str, Any]]:
        """Get key data from Redis or memory."""
        redis = self._get_redis()

        if redis:
            try:
                data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hget(JWKS_KEYS_HASH, kid)
                )
                if data:
                    return json.loads(data if isinstance(data, str) else data.decode())
            except Exception as e:
                logger.warning(f"Redis get failed, using memory: {e}")

        return self._keys.get(kid)

    async def _set_active_kid(self, kid: str) -> None:
        """Set the active key ID."""
        redis = self._get_redis()

        if redis:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.set(JWKS_ACTIVE_KEY, kid)
                )
                self._active_kid = kid
                return
            except Exception as e:
                logger.warning(f"Redis set failed, using memory: {e}")

        self._active_kid = kid

    async def _get_active_kid(self) -> Optional[str]:
        """Get the active key ID."""
        redis = self._get_redis()

        if redis:
            try:
                kid = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.get(JWKS_ACTIVE_KEY)
                )
                if kid:
                    self._active_kid = kid if isinstance(kid, str) else kid.decode()
                    return self._active_kid
            except Exception as e:
                logger.warning(f"Redis get failed, using memory: {e}")

        return self._active_kid

    async def get_active_key(self) -> Optional[JWKWrapper]:
        """Get the current active signing key."""
        kid = await self._get_active_kid()
        if not kid:
            return None

        key_data = await self._get_key_data(kid)
        if not key_data:
            return None

        # Never sign with an expired key. If active key is stale, rotate now.
        try:
            expires_at = datetime.fromisoformat(key_data["expires_at"])
            if expires_at <= datetime.utcnow():
                logger.warning(
                    "Active JWKS key %s is expired; rotating before signing", kid
                )
                await self._audit_key_event("expired", kid)
                await self.rotate_keys()
                # Re-resolve active key after rotation.
                kid = await self._get_active_kid()
                if not kid:
                    return None
                key_data = await self._get_key_data(kid)
                if not key_data:
                    return None
        except Exception as e:
            logger.warning(f"Failed active key expiry check for kid={kid}: {e}")

        return JWKWrapper.from_storage_dict(key_data["key"])

    async def get_key_by_kid(self, kid: str) -> Optional[JWKWrapper]:
        """Get a specific key by its kid (returns None if revoked or expired)."""
        # Check if key is revoked
        if await self.is_key_revoked(kid):
            logger.warning(f"Attempted to use revoked key: {kid}")
            # Audit this critical event
            await self._audit_key_event("revoked_key_used", kid)
            return None

        key_data = await self._get_key_data(kid)
        if not key_data:
            return None

        # Check if expired
        expires_at = datetime.fromisoformat(key_data["expires_at"])
        if expires_at < datetime.utcnow():
            return None

        return JWKWrapper.from_storage_dict(key_data["key"])

    async def get_all_valid_keys(self) -> List[JWKWrapper]:
        """Get all non-expired and non-revoked keys."""
        keys = []
        now = datetime.utcnow()
        seen_kids = set()

        # Get set of revoked kids for efficient lookup
        revoked_kids = await self._get_revoked_kids()

        redis = self._get_redis()

        if redis:
            try:
                all_keys = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hgetall(JWKS_KEYS_HASH)
                )
                for kid, data in all_keys.items():
                    kid_str = kid if isinstance(kid, str) else kid.decode()

                    # Skip revoked keys
                    if kid_str in revoked_kids:
                        continue

                    data_str = data if isinstance(data, str) else data.decode()
                    key_data = json.loads(data_str)

                    expires_at = datetime.fromisoformat(key_data["expires_at"])
                    if expires_at > now:
                        keys.append(JWKWrapper.from_storage_dict(key_data["key"]))
                        seen_kids.add(kid_str)
            except Exception as e:
                logger.warning(f"Redis getall failed, using memory: {e}")

        # Merge memory-backed keys as well. This protects verification when a key
        # was generated while Redis was unavailable.
        for kid, key_data in self._keys.items():
            # Skip revoked keys
            if kid in revoked_kids:
                continue

            # Avoid duplicates if key was already loaded from Redis
            if kid in seen_kids:
                continue

            expires_at = datetime.fromisoformat(key_data["expires_at"])
            if expires_at > now:
                keys.append(JWKWrapper.from_storage_dict(key_data["key"]))

        return keys

    async def get_jwks(self) -> Dict[str, Any]:
        """
        Get JWKS (JSON Web Key Set) with all valid public keys.

        Returns:
            Dict with 'keys' array containing public JWKs
        """
        valid_keys = await self.get_all_valid_keys()

        return {"keys": [key.to_public_jwk() for key in valid_keys]}

    async def cleanup_expired_keys(self) -> int:
        """
        Remove expired keys from storage.

        Returns:
            Number of keys removed
        """
        removed = 0
        now = datetime.utcnow()

        redis = self._get_redis()

        if redis:
            try:
                all_keys = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hgetall(JWKS_KEYS_HASH)
                )
                for kid, data in all_keys.items():
                    kid_str = kid if isinstance(kid, str) else kid.decode()
                    data_str = data if isinstance(data, str) else data.decode()
                    key_data = json.loads(data_str)

                    expires_at = datetime.fromisoformat(key_data["expires_at"])
                    if expires_at < now:
                        await asyncio.get_event_loop().run_in_executor(
                            None, lambda k=kid_str: redis.hdel(JWKS_KEYS_HASH, k)
                        )
                        removed += 1
                        logger.info(f"Removed expired key: {kid_str}")
                return removed
            except Exception as e:
                logger.warning(f"Redis cleanup failed: {e}")

        # Memory cleanup
        to_remove = []
        for kid, key_data in self._keys.items():
            expires_at = datetime.fromisoformat(key_data["expires_at"])
            if expires_at < now:
                to_remove.append(kid)

        for kid in to_remove:
            del self._keys[kid]
            removed += 1

        return removed

    async def revoke_key(
        self, kid: str, reason: str = "key_compromise", revoked_by: Optional[str] = None
    ) -> bool:
        """
        Revoke a signing key immediately.

        Use this when a key is suspected to be compromised. The key will
        no longer be returned by get_key_by_kid or get_all_valid_keys,
        and will be excluded from the JWKS endpoint.

        Args:
            kid: Key ID to revoke
            reason: Revocation reason (e.g., 'key_compromise', 'superseded',
                    'cessation_of_operation', 'privilege_withdrawn')
            revoked_by: Optional identifier of who initiated revocation

        Returns:
            True if key was revoked, False if key not found
        """
        # Check if key exists
        key_data = await self._get_key_data(kid)
        if not key_data:
            logger.warning(f"Attempted to revoke non-existent key: {kid}")
            return False

        # Check if already revoked
        if await self.is_key_revoked(kid):
            logger.info(f"Key already revoked: {kid}")
            return True

        now = datetime.utcnow()

        revocation_info = {
            "kid": kid,
            "reason": reason,
            "revoked_at": now.isoformat(),
            "revoked_by": revoked_by,
        }

        # Store revocation
        redis = self._get_redis()

        if redis:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: redis.hset(
                        JWKS_REVOKED_HASH, kid, json.dumps(revocation_info)
                    ),
                )
                logger.warning(
                    f"Key revoked: {kid} (reason: {reason}, by: {revoked_by})"
                )

                # Audit the critical key revocation event
                await self._audit_key_event(
                    "revoked", kid, details={"reason": reason, "revoked_by": revoked_by}
                )

                # If this was the active key, rotate immediately
                if kid == self._active_kid:
                    logger.warning(
                        "Revoked key was active, initiating emergency rotation"
                    )
                    await self.rotate_keys()

                return True
            except Exception as e:
                logger.error(f"Failed to store key revocation in Redis: {e}")

        # Fallback to memory
        self._revoked_keys[kid] = revocation_info
        logger.warning(f"Key revoked (in-memory): {kid} (reason: {reason})")

        # Audit the critical key revocation event
        await self._audit_key_event(
            "revoked", kid, details={"reason": reason, "revoked_by": revoked_by}
        )

        # If this was the active key, rotate immediately
        if kid == self._active_kid:
            logger.warning("Revoked key was active, initiating emergency rotation")
            await self.rotate_keys()

        return True

    async def is_key_revoked(self, kid: str) -> bool:
        """
        Check if a key has been revoked.

        Args:
            kid: Key ID to check

        Returns:
            True if key is revoked, False otherwise
        """
        redis = self._get_redis()

        if redis:
            try:
                exists = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hexists(JWKS_REVOKED_HASH, kid)
                )
                return bool(exists)
            except Exception as e:
                logger.warning(f"Redis revocation check failed: {e}")

        # Fallback to memory
        return kid in self._revoked_keys

    async def get_revocation_info(self, kid: str) -> Optional[KeyRevocationInfo]:
        """
        Get revocation details for a key.

        Args:
            kid: Key ID to check

        Returns:
            KeyRevocationInfo if revoked, None otherwise
        """
        redis = self._get_redis()

        if redis:
            try:
                data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hget(JWKS_REVOKED_HASH, kid)
                )
                if data:
                    data_str = data if isinstance(data, str) else data.decode()
                    info = json.loads(data_str)
                    return KeyRevocationInfo(
                        kid=info["kid"],
                        reason=info["reason"],
                        revoked_at=datetime.fromisoformat(info["revoked_at"]),
                        revoked_by=info.get("revoked_by"),
                    )
            except Exception as e:
                logger.warning(f"Redis revocation info get failed: {e}")

        # Fallback to memory
        if kid in self._revoked_keys:
            info = self._revoked_keys[kid]
            return KeyRevocationInfo(
                kid=info["kid"],
                reason=info["reason"],
                revoked_at=datetime.fromisoformat(info["revoked_at"]),
                revoked_by=info.get("revoked_by"),
            )

        return None

    async def get_all_revoked_keys(self) -> List[KeyRevocationInfo]:
        """
        Get all revoked keys.

        Returns:
            List of KeyRevocationInfo for all revoked keys
        """
        revoked = []

        redis = self._get_redis()

        if redis:
            try:
                all_revoked = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hgetall(JWKS_REVOKED_HASH)
                )
                for kid, data in all_revoked.items():
                    data_str = data if isinstance(data, str) else data.decode()
                    info = json.loads(data_str)
                    revoked.append(
                        KeyRevocationInfo(
                            kid=info["kid"],
                            reason=info["reason"],
                            revoked_at=datetime.fromisoformat(info["revoked_at"]),
                            revoked_by=info.get("revoked_by"),
                        )
                    )
                return revoked
            except Exception as e:
                logger.warning(f"Redis get all revoked failed: {e}")

        # Fallback to memory
        for kid, info in self._revoked_keys.items():
            revoked.append(
                KeyRevocationInfo(
                    kid=info["kid"],
                    reason=info["reason"],
                    revoked_at=datetime.fromisoformat(info["revoked_at"]),
                    revoked_by=info.get("revoked_by"),
                )
            )

        return revoked

    async def _get_revoked_kids(self) -> set:
        """Get set of all revoked key IDs for efficient lookup."""
        revoked_kids = set()

        redis = self._get_redis()

        if redis:
            try:
                all_keys = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.hkeys(JWKS_REVOKED_HASH)
                )
                for kid in all_keys:
                    kid_str = kid if isinstance(kid, str) else kid.decode()
                    revoked_kids.add(kid_str)
                return revoked_kids
            except Exception as e:
                logger.warning(f"Redis get revoked kids failed: {e}")

        # Fallback to memory
        return set(self._revoked_keys.keys())


# Singleton instance
_key_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    """
    Get the singleton KeyManager instance.

    Returns:
        KeyManager instance (not yet initialized - call initialize() first)
    """
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager()
    return _key_manager


async def initialize_key_manager() -> KeyManager:
    """
    Initialize and return the KeyManager.

    Creates initial key if none exists.
    """
    km = get_key_manager()
    await km.initialize()
    return km
