"""
JWT Token Service for ARCP Authentication.

This module provides JWT token minting and validation capabilities for the
ARCP (Agent Registry & Control Protocol). It handles secure token
generation for agent authentication and authorization.

Asymmetric Signing with JWKS
-------------------------------------------------
When JWKS_ENABLED is True, tokens are signed with EdDSA/ES256 private keys
instead of symmetric HS256. This enables:
- Public key verification (clients can verify without shared secret)
- Key rotation without disrupting existing tokens
- JWKS endpoint publishing at /.well-known/jwks.json

Environment Variables Required:
    JWT_SECRET: Secret key for JWT signing (fallback for symmetric)
    JWT_ALGORITHM: JWT algorithm (e.g., HS256)
    JWT_EXPIRE_MINUTES: Token expiration time in minutes
    JWKS_ENABLED: Enable asymmetric signing (default: False)
    JWKS_ALGORITHM: Asymmetric algorithm (EdDSA or ES256)

Example Usage:
    >>> from arcp.core.token_service import TokenService
    >>> from arcp.models.token import TokenMintRequest
    >>>
    >>> service = TokenService()
    >>> request = TokenMintRequest(
    ...     user_id="user123",
    ...     agent_id="vulnintel-scanner",
    ...     scopes=["read", "write"]
    ... )
    >>> response = service.mint_token(request)
    >>> token = response.access_token
    >>>
    >>> # Later, validate the token
    >>> payload = service.validate_token(token)
    >>> print(payload["agent"])  # "vulnintel-scanner"
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

import jwt

from ..models.token import TokenMintRequest, TokenResponse
from .config import config
from .jwks import get_jwks_service

logger = logging.getLogger(__name__)


class TokenService:
    """
    JWT Token Service for ARCP.

    This service handles minting and validation of JWT tokens for agent
    authentication and authorization within the ARCP ecosystem.

    Supports asymmetric signing via JWKS when enabled.

    Attributes:
        secret: JWT signing secret key (symmetric fallback)
        algo: JWT algorithm (typically HS256 or EdDSA)
        expire_minutes: Token expiration time in minutes
        jwks_enabled: Whether to use asymmetric signing
        issuer: Token issuer (iss claim)
    """

    def __init__(
        self,
        secret: str = None,
        algo: str = None,
        expire_minutes: int = None,
        jwks_enabled: bool = None,
    ):
        """
        Initialize the TokenService.

        Args:
            secret: JWT signing secret key (defaults to config.JWT_SECRET)
            algo: JWT algorithm to use for signing (defaults to config.JWT_ALGORITHM)
            expire_minutes: Token expiration in minutes (defaults to config.JWT_EXPIRE_MINUTES)
            jwks_enabled: Use asymmetric signing (defaults to config.JWKS_ENABLED)
        """
        self.secret = (
            secret
            or config.JWT_SECRET
            or "default-library-jwt-secret-change-in-production"
        )
        self.algo = algo or config.JWT_ALGORITHM or "HS256"
        self.expire_minutes = expire_minutes or config.JWT_EXPIRE_MINUTES or 3600
        self.jwks_enabled = (
            jwks_enabled
            if jwks_enabled is not None
            else getattr(config, "JWKS_ENABLED", False)
        )
        self.issuer = getattr(config, "ARCP_ISSUER", "urn:arcp:issuer")

        # Cache for JWKS service (lazy initialization)
        self._jwks_service = None

    def _get_jwks_service(self):
        """Lazily initialize JWKS service."""
        if self._jwks_service is None:
            try:
                self._jwks_service = get_jwks_service()
            except ImportError as e:
                logger.warning(f"JWKS service not available: {e}")
                return None
        return self._jwks_service

    def _get_signing_credentials(self) -> tuple:
        """
        Get signing key and algorithm.

        Uses synchronous cached key access for compatibility with sync callers.

        Returns:
            Tuple of (signing_key, algorithm, headers_dict)
        """
        if not self.jwks_enabled:
            return self.secret, self.algo, {}

        jwks_service = self._get_jwks_service()
        if jwks_service is None:
            logger.warning(
                "JWKS service unavailable, falling back to symmetric signing"
            )
            return self.secret, self.algo, {}

        try:
            # Use synchronous cached accessor (cache is populated during initialization)
            key_wrapper = jwks_service.get_signing_key_sync()
            if key_wrapper is None:
                logger.warning(
                    "No signing key available, falling back to symmetric signing"
                )
                return self.secret, self.algo, {}

            # Return private key, algorithm, and headers with kid
            # JWKWrapper is an object with properties, not a dict
            return (
                key_wrapper.private_key,
                key_wrapper.algorithm,
                {"kid": key_wrapper.kid},
            )
        except Exception as e:
            logger.error(f"Failed to get signing key: {e}")
            return self.secret, self.algo, {}

    def mint_token(
        self, req: TokenMintRequest, dpop_jkt: str = None, mtls_spki: str = None
    ) -> TokenResponse:
        """
        Create a JWT token for agent authentication.

        Supports asymmetric signing when JWKS is enabled.
        Adds DPoP binding (cnf.jkt claim) when dpop_jkt provided.
        Adds mTLS binding (cnf.x5t#S256 claim) when mtls_spki provided.

        Args:
            req: Token minting request containing user and agent information
            dpop_jkt: DPoP key JWK thumbprint for sender-constrained tokens
            mtls_spki: mTLS client certificate SPKI hash for cert-bound tokens

        Returns:
            TokenResponse containing the JWT token and metadata

        Example:
            >>> service = TokenService()
            >>> request = TokenMintRequest(
            ...     user_id="user123",
            ...     agent_id="agent456",
            ...     scopes=["read", "write"]
            ... )
            >>> response = service.mint_token(request)
            >>> print(response.access_token)  # JWT token string

            # With DPoP binding:
            >>> response = service.mint_token(request, dpop_jkt="abc123...")
        """
        now = datetime.utcnow()
        payload: Dict[str, Any] = {
            "sub": req.user_id,
            "agent_id": req.agent_id,  # Use agent_id instead of agent for consistency
            "scopes": req.scopes,
            "role": req.role,
            "iat": now,
            "exp": now + timedelta(minutes=self.expire_minutes),
        }

        # Add issuer for JWKS-signed tokens
        if self.jwks_enabled:
            payload["iss"] = self.issuer

        # Add temp_registration flag if present
        if req.temp_registration:
            payload["temp_registration"] = req.temp_registration

        # Add additional fields for temporary tokens
        if req.agent_type:
            payload["agent_type"] = req.agent_type
        if req.used_key:
            payload["used_key"] = req.used_key
        if req.agent_key_hash:
            payload["agent_key_hash"] = req.agent_key_hash

        # Add TPR-specific fields
        if req.aud:
            payload["aud"] = req.aud
        if req.token_type:
            payload["token_type"] = req.token_type

        # ========================================
        # Confirmation (cnf) claim
        # Per RFC 9449 for DPoP, RFC 8705 for mTLS
        # ========================================
        cnf: Dict[str, str] = {}

        if dpop_jkt:
            # DPoP key binding (RFC 9449)
            cnf["jkt"] = dpop_jkt
            logger.debug(f"Adding DPoP binding to token: jkt={dpop_jkt[:16]}...")

        if mtls_spki:
            # mTLS certificate binding (RFC 8705)
            # x5t#S256 is the base64url-encoded SHA-256 hash of the cert
            cnf["x5t#S256"] = mtls_spki
            logger.debug(f"Adding mTLS binding to token: x5t#S256={mtls_spki[:16]}...")

        if cnf:
            payload["cnf"] = cnf

        # Get signing credentials (symmetric or asymmetric)
        signing_key, algorithm, headers = self._get_signing_credentials()

        token = jwt.encode(
            payload,
            signing_key,
            algorithm=algorithm,
            headers=headers if headers else None,
        )
        return TokenResponse(
            access_token=token,
            token_type=(
                "DPoP" if dpop_jkt else "bearer"
            ),  # RFC 9449: DPoP tokens use DPoP type
            expires_in=self.expire_minutes * 60,
        )

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode a JWT token.

        Supports asymmetric verification when JWKS is enabled.
        For JWKS tokens, the 'kid' header is used to select the verification key.

        Args:
            token: JWT token string to validate

        Returns:
            Dictionary containing the decoded token payload

        Raises:
            jwt.ExpiredSignatureError: If token has expired
            jwt.InvalidTokenError: If token is invalid

        Example:
            >>> service = TokenService()
            >>> payload = service.validate_token("eyJ0eXAi...")
            >>> print(payload["sub"])  # user_id
            >>> print(payload["agent"])  # agent_id
        """
        # Try to determine if this is a JWKS-signed token by examining the header
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            # Can't parse header, use symmetric key
            clock_skew = getattr(config, "DPOP_CLOCK_SKEW", 60)
            return jwt.decode(
                token,
                self.secret,
                algorithms=[self.algo],
                options={"verify_aud": False},
                leeway=clock_skew,
            )

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", self.algo)

        # If token has a kid and JWKS is available, use asymmetric verification
        if kid and self.jwks_enabled:
            jwks_service = self._get_jwks_service()
            if jwks_service:
                try:
                    # Use synchronous cached accessor
                    key_wrapper = jwks_service.get_verification_key_sync(kid)
                    if key_wrapper:
                        # Use same clock skew tolerance as DPoP
                        clock_skew = getattr(config, "DPOP_CLOCK_SKEW", 60)
                        return jwt.decode(
                            token,
                            key_wrapper.public_key,
                            algorithms=[key_wrapper.algorithm],
                            options={"verify_aud": False},
                            issuer=(
                                self.issuer
                                if getattr(config, "JWKS_VERIFY_ISSUER", True)
                                else None
                            ),
                            leeway=clock_skew,
                        )
                except Exception as e:
                    logger.warning(f"JWKS verification failed for kid={kid}: {e}")
                    # Fall through to symmetric verification

        # Fallback to symmetric verification
        # Support both the configured algorithm and common algorithms
        allowed_algorithms = [self.algo]
        if alg in ["HS256", "HS384", "HS512"] and alg not in allowed_algorithms:
            allowed_algorithms.append(alg)

        # Use same clock skew tolerance as DPoP
        clock_skew = getattr(config, "DPOP_CLOCK_SKEW", 60)
        return jwt.decode(
            token,
            self.secret,
            algorithms=allowed_algorithms,
            options={"verify_aud": False},
            leeway=clock_skew,
        )

    def create_token(
        self,
        agent_id: str,
        token_type: str,
        audience: str,
        ttl: int,
        validation_id: str = None,
        dpop_jkt: str = None,
        mtls_spki: str = None,
    ) -> str:
        """
        Create a JWT token for testing or TPR flows.

        Supports asymmetric signing when JWKS is enabled.
        Adds DPoP binding when dpop_jkt provided.
        Adds mTLS binding when mtls_spki provided.

        Args:
            agent_id: Agent identifier
            token_type: Type of token (temp, validated, access)
            audience: Token audience
            ttl: Time to live in seconds
            validation_id: Optional validation ID for validated tokens
            dpop_jkt: DPoP key JWK thumbprint for sender-constrained tokens
            mtls_spki: mTLS client certificate SPKI hash

        Returns:
            JWT token string

        Example:
            >>> service = TokenService()
            >>> token = service.create_token(
            ...     agent_id="test-agent",
            ...     token_type="temp",
            ...     audience="arcp:validate",
            ...     ttl=900
            ... )
        """
        now = datetime.utcnow()
        payload: Dict[str, Any] = {
            "agent_id": agent_id,
            "token_type": token_type,
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(seconds=ttl),
        }

        # Add issuer for JWKS tokens
        if self.jwks_enabled:
            payload["iss"] = self.issuer

        if validation_id:
            payload["validation_id"] = validation_id

        # Add confirmation claim for DPoP/mTLS binding
        cnf: Dict[str, str] = {}
        if dpop_jkt:
            cnf["jkt"] = dpop_jkt
        if mtls_spki:
            cnf["x5t#S256"] = mtls_spki
        if cnf:
            payload["cnf"] = cnf

        # Get signing credentials
        signing_key, algorithm, headers = self._get_signing_credentials()

        return jwt.encode(
            payload,
            signing_key,
            algorithm=algorithm,
            headers=headers if headers else None,
        )


def get_token_service() -> TokenService:
    """
    Get a TokenService instance for dependency injection.

    This function is used by FastAPI's dependency injection system
    to provide a TokenService instance to route handlers.

    Returns:
        TokenService: Configured token service instance

    Example:
        >>> from fastapi import Depends
        >>>
        >>> @app.post("/endpoint")
        >>> async def my_endpoint(
        ...     token_service: TokenService = Depends(get_token_service)
        ... ):
        ...     # Use token_service here
        ...     pass
    """
    return TokenService()
