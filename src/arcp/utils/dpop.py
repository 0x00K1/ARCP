"""
DPoP (Demonstrating Proof-of-Possession) Validator per RFC 9449.

Validates DPoP proof JWTs and prevents replay attacks using jti tracking.
DPoP binds access tokens to a specific client key pair, ensuring that
stolen tokens cannot be used by attackers.

Key Features:
- Full RFC 9449 compliance
- Replay protection via Redis-backed jti tracking
- JWK thumbprint computation for token binding
- Access token hash (ath) verification
- Clock skew tolerance

Environment Variables:
    DPOP_ENABLED: Accept DPoP proofs (default: true)
    DPOP_REQUIRED: Require DPoP for token endpoints (default: false)
    DPOP_PROOF_TTL: Proof validity window in seconds (default: 120)
    DPOP_CLOCK_SKEW: Allowed clock skew in seconds (default: 60)
    DPOP_ALGORITHMS: Comma-separated allowed algorithms (default: EdDSA,ES256)

Example Usage:
    >>> from arcp.utils.dpop import get_dpop_validator
    >>> validator = get_dpop_validator()
    >>> result = await validator.validate_proof(
    ...     dpop_header="eyJ0eXAi...",
    ...     http_method="POST",
    ...     http_uri="https://arcp.example.com/auth/agent/request_temp_token"
    ... )
    >>> if result.valid:
    ...     print(f"JWK Thumbprint: {result.jkt}")
"""

import asyncio
import base64
import hashlib
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..core.config import config
from ..models.dpop import DPoPProof, DPoPValidationError, DPoPValidationResult
from ..services import get_redis_service
from .security_audit import SecurityEventType, log_dpop_event

logger = logging.getLogger(__name__)

# Redis key prefix for jti tracking
DPOP_JTI_PREFIX = "arcp:dpop:jti:"


class DPoPValidator:
    """
    Validates DPoP proofs according to RFC 9449.

    DPoP (Demonstrating Proof-of-Possession) provides a mechanism to
    bind access tokens to a client's public key, preventing token theft.

    Validation Steps:
    1. Parse JWT without verification to get algorithm
    2. Validate header (typ=dpop+jwt, jwk present, alg allowed)
    3. Verify signature using embedded JWK
    4. Validate required claims (jti, htm, htu, iat)
    5. Verify htm matches request method
    6. Verify htu matches request URI
    7. Verify iat is within acceptable window
    8. Check jti for replay
    9. Optionally verify ath (access token hash)
    10. Optionally verify expected jkt
    11. Mark jti as used
    """

    def __init__(self):
        self.enabled = getattr(config, "DPOP_ENABLED", True)
        self.required = getattr(config, "DPOP_REQUIRED", False)
        self.proof_ttl = getattr(config, "DPOP_PROOF_TTL", 120)
        self.clock_skew = getattr(config, "DPOP_CLOCK_SKEW", 60)
        self.allowed_algorithms = getattr(config, "DPOP_ALGORITHMS", ["EdDSA", "ES256"])
        self._redis = None

    def _get_redis(self):
        """Get Redis client, cached."""
        if self._redis is None:
            try:
                redis_service = get_redis_service()
                self._redis = redis_service.get_client()
            except Exception:
                pass
        return self._redis

    async def _audit_dpop_event(
        self,
        event: str,
        jti: Optional[str] = None,
        jkt: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Log DPoP event to security audit service."""
        try:
            event_map = {
                "valid": SecurityEventType.DPOP_PROOF_VALID,
                "invalid": SecurityEventType.DPOP_PROOF_INVALID,
                "replay_detected": SecurityEventType.DPOP_REPLAY_DETECTED,
                "binding_mismatch": SecurityEventType.DPOP_BINDING_MISMATCH,
                "signature_invalid": SecurityEventType.DPOP_SIGNATURE_INVALID,
                "expired": SecurityEventType.DPOP_EXPIRED,
            }

            event_type = event_map.get(event, SecurityEventType.DPOP_PROOF_INVALID)
            await log_dpop_event(
                event_type=event_type,
                jti=jti,
                jkt=jkt,
                agent_id=agent_id,
                error_message=error_message,
            )
        except Exception as e:
            logger.debug(f"Failed to audit DPoP event: {e}")

    async def validate_proof(
        self,
        dpop_header: str,
        http_method: str,
        http_uri: str,
        access_token: Optional[str] = None,
        expected_jkt: Optional[str] = None,
    ) -> DPoPValidationResult:
        """
        Validate a DPoP proof.

        Args:
            dpop_header: Raw DPoP header value (JWT string)
            http_method: HTTP method of the request (GET, POST, etc.)
            http_uri: Full request URI
            access_token: If present, verify ath claim matches
            expected_jkt: If present, verify JWK thumbprint matches

        Returns:
            DPoPValidationResult with validation outcome
        """
        if not self.enabled:
            return DPoPValidationResult.failure(
                DPoPValidationError.VALIDATION_ERROR, "DPoP validation is disabled"
            )

        if not dpop_header:
            return DPoPValidationResult.failure(
                DPoPValidationError.MISSING_HEADER, "DPoP header is missing"
            )

        try:
            # Step 1: Parse JWT without verification
            try:
                unverified = jwt.decode(
                    dpop_header, options={"verify_signature": False}
                )
                header = jwt.get_unverified_header(dpop_header)
            except jwt.exceptions.DecodeError as e:
                return DPoPValidationResult.failure(
                    DPoPValidationError.INVALID_JWT, f"Invalid JWT format: {str(e)}"
                )

            # Step 2: Validate header
            # Check typ
            if header.get("typ") != "dpop+jwt":
                return DPoPValidationResult.failure(
                    DPoPValidationError.INVALID_TYP,
                    f"Invalid typ: expected 'dpop+jwt', got '{header.get('typ')}'",
                )

            # Check jwk
            if "jwk" not in header:
                return DPoPValidationResult.failure(
                    DPoPValidationError.MISSING_JWK, "Missing 'jwk' in DPoP JWT header"
                )

            # Check algorithm
            alg = header.get("alg")
            if alg not in self.allowed_algorithms:
                return DPoPValidationResult.failure(
                    DPoPValidationError.UNSUPPORTED_ALGORITHM,
                    f"Unsupported algorithm: {alg}. Allowed: {self.allowed_algorithms}",
                )

            # Step 3: Verify signature using embedded JWK
            jwk_dict = header["jwk"]
            try:
                public_key = self._jwk_to_public_key(jwk_dict, alg)
                jwt.decode(
                    dpop_header,
                    public_key,
                    algorithms=[alg],
                    options={"verify_aud": False},
                    leeway=self.clock_skew,  # Allow configured clock skew tolerance
                )
            except jwt.exceptions.InvalidSignatureError:
                return DPoPValidationResult.failure(
                    DPoPValidationError.INVALID_SIGNATURE,
                    "DPoP proof signature verification failed",
                )
            except Exception as e:
                return DPoPValidationResult.failure(
                    DPoPValidationError.INVALID_SIGNATURE,
                    f"Signature verification error: {str(e)}",
                )

            # Step 4: Validate required claims
            if "jti" not in unverified:
                return DPoPValidationResult.failure(
                    DPoPValidationError.MISSING_JTI, "Missing 'jti' claim in DPoP proof"
                )
            if "htm" not in unverified:
                return DPoPValidationResult.failure(
                    DPoPValidationError.MISSING_HTM, "Missing 'htm' claim in DPoP proof"
                )
            if "htu" not in unverified:
                return DPoPValidationResult.failure(
                    DPoPValidationError.MISSING_HTU, "Missing 'htu' claim in DPoP proof"
                )
            if "iat" not in unverified:
                return DPoPValidationResult.failure(
                    DPoPValidationError.MISSING_IAT, "Missing 'iat' claim in DPoP proof"
                )

            # Create proof object
            try:
                proof = DPoPProof(
                    jti=unverified["jti"],
                    htm=unverified["htm"],
                    htu=unverified["htu"],
                    iat=unverified["iat"],
                    ath=unverified.get("ath"),
                    nonce=unverified.get("nonce"),
                    jwk=jwk_dict,
                    alg=alg,
                )
            except Exception as e:
                return DPoPValidationResult.failure(
                    DPoPValidationError.VALIDATION_ERROR,
                    f"Invalid DPoP claims: {str(e)}",
                )

            # Step 5: Verify htm matches request method
            if proof.htm.upper() != http_method.upper():
                return DPoPValidationResult.failure(
                    DPoPValidationError.HTM_MISMATCH,
                    f"HTTP method mismatch: proof has '{proof.htm}', request is '{http_method}'",
                )

            # Step 6: Verify htu matches request URI
            if not self._uri_matches(proof.htu, http_uri):
                return DPoPValidationResult.failure(
                    DPoPValidationError.HTU_MISMATCH,
                    f"URI mismatch: proof has '{proof.htu}', request is '{http_uri}'",
                )

            # Step 7: Verify iat is within acceptable window
            now = time.time()
            if proof.iat < now - self.proof_ttl:
                return DPoPValidationResult.failure(
                    DPoPValidationError.PROOF_EXPIRED,
                    f"Proof expired: iat is {int(now - proof.iat)} seconds old (max: {self.proof_ttl})",
                )
            if proof.iat > now + self.clock_skew:
                return DPoPValidationResult.failure(
                    DPoPValidationError.PROOF_FUTURE,
                    f"Proof iat is {int(proof.iat - now)} seconds in the future (max: {self.clock_skew})",
                )

            # Step 8: Check jti for replay
            if await self._is_jti_used(proof.jti):
                await self._audit_dpop_event(
                    "replay_detected",
                    jti=proof.jti,
                    error_message="DPoP proof replay detected: jti already used",
                )
                return DPoPValidationResult.failure(
                    DPoPValidationError.JTI_REPLAY,
                    "DPoP proof replay detected: jti already used",
                )

            # Step 9: Verify ath if access token provided and ath present
            if access_token and proof.ath:
                if not proof.verify_ath(access_token):
                    return DPoPValidationResult.failure(
                        DPoPValidationError.ATH_MISMATCH, "Access token hash mismatch"
                    )

            # Step 10: Verify expected jkt if provided
            actual_jkt = proof.compute_jkt()
            if expected_jkt and actual_jkt != expected_jkt:
                await self._audit_dpop_event(
                    "binding_mismatch",
                    jti=proof.jti,
                    jkt=actual_jkt,
                    error_message=f"JWK thumbprint mismatch: expected '{expected_jkt}', got '{actual_jkt}'",
                )
                return DPoPValidationResult.failure(
                    DPoPValidationError.JKT_MISMATCH,
                    f"JWK thumbprint mismatch: expected '{expected_jkt}', got '{actual_jkt}'",
                )

            # Step 11: Mark jti as used
            await self._mark_jti_used(proof.jti)

            # Success! Audit the successful validation
            await self._audit_dpop_event("valid", jti=proof.jti, jkt=actual_jkt)
            logger.debug(
                f"DPoP proof validated: jti={proof.jti[:16]}..., jkt={actual_jkt[:16]}..."
            )
            return DPoPValidationResult.success(proof)

        except Exception as e:
            logger.error(f"DPoP validation error: {e}", exc_info=True)
            return DPoPValidationResult.failure(
                DPoPValidationError.VALIDATION_ERROR, f"Validation error: {str(e)}"
            )

    def _jwk_to_public_key(self, jwk_dict: Dict[str, Any], alg: str):
        """
        Convert JWK dictionary to a public key object for verification.

        Args:
            jwk_dict: JWK as dictionary
            alg: Algorithm (EdDSA, ES256, etc.)

        Returns:
            Public key object suitable for PyJWT verification
        """
        kty = jwk_dict.get("kty")

        if kty == "OKP":
            x = jwk_dict.get("x")
            if not x:
                raise ValueError("Missing 'x' in OKP JWK")

            # Decode x (base64url)
            x_bytes = self._base64url_decode(x)

            public_key = Ed25519PublicKey.from_public_bytes(x_bytes)
            return public_key

        elif kty == "EC":
            crv = jwk_dict.get("crv", "P-256")
            x = jwk_dict.get("x")
            y = jwk_dict.get("y")

            if not x or not y:
                raise ValueError("Missing 'x' or 'y' in EC JWK")

            x_bytes = self._base64url_decode(x)
            y_bytes = self._base64url_decode(y)

            # Determine curve
            if crv == "P-256":
                curve = ec.SECP256R1()
                coord_size = 32
            elif crv == "P-384":
                curve = ec.SECP384R1()
                coord_size = 48
            elif crv == "P-521":
                curve = ec.SECP521R1()
                coord_size = 66
            else:
                raise ValueError(f"Unsupported curve: {crv}")

            # Pad coordinates if needed
            x_bytes = x_bytes.rjust(coord_size, b"\x00")
            y_bytes = y_bytes.rjust(coord_size, b"\x00")

            x_int = int.from_bytes(x_bytes, byteorder="big")
            y_int = int.from_bytes(y_bytes, byteorder="big")

            public_numbers = ec.EllipticCurvePublicNumbers(x_int, y_int, curve)
            public_key = public_numbers.public_key(default_backend())

            return public_key

        else:
            raise ValueError(f"Unsupported key type: {kty}")

    def _base64url_decode(self, data: str) -> bytes:
        """Decode base64url with padding."""
        # Add padding if needed
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)

    def _uri_matches(self, proof_htu: str, request_uri: str) -> bool:
        """
        Compare URIs ignoring query and fragment.

        Per RFC 9449, the htu should match the request URI without
        query parameters and fragment.
        """
        proof_parsed = urlparse(proof_htu)
        request_parsed = urlparse(request_uri)

        # Compare scheme, netloc, and path
        return (
            proof_parsed.scheme.lower() == request_parsed.scheme.lower()
            and proof_parsed.netloc.lower() == request_parsed.netloc.lower()
            and proof_parsed.path == request_parsed.path
        )

    async def _is_jti_used(self, jti: str) -> bool:
        """Check if jti has been used (replay detection)."""
        redis = self._get_redis()

        if redis:
            try:
                exists = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.exists(f"{DPOP_JTI_PREFIX}{jti}")
                )
                return bool(exists)
            except Exception as e:
                logger.warning(f"Redis check failed for jti: {e}")

        # Without Redis, we can't track jti - log warning
        logger.warning(
            "Redis unavailable for DPoP jti tracking - replay protection degraded"
        )
        return False

    async def _mark_jti_used(self, jti: str) -> None:
        """Mark jti as used with TTL."""
        redis = self._get_redis()

        if redis:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: redis.setex(
                        f"{DPOP_JTI_PREFIX}{jti}",
                        self.proof_ttl
                        + self.clock_skew,  # TTL slightly longer than proof validity
                        "1",
                    ),
                )
            except Exception as e:
                logger.warning(f"Redis set failed for jti: {e}")

    def compute_ath(self, access_token: str) -> str:
        """
        Compute access token hash for ath claim.

        Args:
            access_token: The access token to hash

        Returns:
            Base64url-encoded SHA-256 hash
        """
        digest = hashlib.sha256(access_token.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# Singleton instance
_dpop_validator: Optional[DPoPValidator] = None


def get_dpop_validator() -> DPoPValidator:
    """
    Get the singleton DPoPValidator instance.

    Returns:
        DPoPValidator instance
    """
    global _dpop_validator
    if _dpop_validator is None:
        _dpop_validator = DPoPValidator()
    return _dpop_validator
