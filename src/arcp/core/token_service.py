"""
JWT Token Service for ARCP Authentication.

This module provides JWT token minting and validation capabilities for the
ARCP (Agent Registry & Control Protocol). It handles secure token
generation for agent authentication and authorization.

The service uses configurable JWT algorithms and expiration times, with
strict environment variable validation to ensure security.

Environment Variables Required:
    JWT_SECRET: Secret key for JWT signing
    JWT_ALGORITHM: JWT algorithm (e.g., HS256)
    JWT_EXPIRE_MINUTES: Token expiration time in minutes

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

from datetime import datetime, timedelta
from typing import Any, Dict

import jwt

from ..models.token import TokenMintRequest, TokenResponse
from .config import config


class TokenService:
    """
    JWT Token Service for ARCP.

    This service handles minting and validation of JWT tokens for agent
    authentication and authorization within the ARCP ecosystem.

    Attributes:
        secret: JWT signing secret key
        algo: JWT algorithm (typically HS256)
        expire_minutes: Token expiration time in minutes
    """

    def __init__(
        self, secret: str = None, algo: str = None, expire_minutes: int = None
    ):
        """
        Initialize the TokenService.

        Args:
            secret: JWT signing secret key (defaults to config.JWT_SECRET)
            algo: JWT algorithm to use for signing (defaults to config.JWT_ALGORITHM)
            expire_minutes: Token expiration in minutes (defaults to config.JWT_EXPIRE_MINUTES)
        """
        self.secret = (
            secret
            or config.JWT_SECRET
            or "default-library-jwt-secret-change-in-production"
        )
        self.algo = algo or config.JWT_ALGORITHM or "HS256"
        self.expire_minutes = expire_minutes or config.JWT_EXPIRE_MINUTES or 3600

    def mint_token(self, req: TokenMintRequest) -> TokenResponse:
        """
        Create a JWT token for agent authentication.

        Args:
            req: Token minting request containing user and agent information

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

        token = jwt.encode(payload, self.secret, algorithm=self.algo)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=self.expire_minutes * 60,
        )

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode a JWT token.

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
        return jwt.decode(token, self.secret, algorithms=[self.algo])


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
