"""
Idempotency middleware for ARCP TPR endpoints.

This module provides idempotency support for critical TPR endpoints,
ensuring that duplicate requests with the same Idempotency-Key header
return the same response without causing duplicate side effects.

RFC Reference: Similar to Stripe's Idempotency Keys pattern.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from fastapi import Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import config
from ..core.exceptions import ARCPProblemTypes, ProblemException
from ..services.redis import get_redis_service

logger = logging.getLogger(__name__)


# Redis key prefix for idempotency
IDEMPOTENCY_PREFIX = "idemp:"


class IdempotencyResult:
    """
    Container for idempotency check result.

    Attributes:
        is_duplicate: Whether this is a duplicate request
        cached_response: Cached response body (if duplicate)
        cached_status: Cached status code (if duplicate)
        key_hash: Hash of idempotency key + request hash
    """

    def __init__(
        self,
        is_duplicate: bool = False,
        cached_response: Optional[Dict] = None,
        cached_status: Optional[int] = None,
        key_hash: Optional[str] = None,
        conflict: bool = False,
    ):
        self.is_duplicate = is_duplicate
        self.cached_response = cached_response
        self.cached_status = cached_status
        self.key_hash = key_hash
        self.conflict = conflict


def compute_request_hash(body: bytes, path: str, method: str) -> str:
    """
    Compute hash of request for duplicate detection.

    Args:
        body: Request body bytes
        path: Request path
        method: HTTP method

    Returns:
        SHA256 hash of request signature
    """
    signature = f"{method}:{path}:{body.decode('utf-8', errors='replace')}"
    return hashlib.sha256(signature.encode()).hexdigest()


async def check_idempotency(
    idempotency_key: str,
    request_hash: str,
) -> IdempotencyResult:
    """
    Check if this request has been seen before.

    Args:
        idempotency_key: Client-provided idempotency key
        request_hash: Hash of the request body + path

    Returns:
        IdempotencyResult indicating if duplicate and cached response
    """
    redis_service = get_redis_service()

    if not redis_service or not redis_service.is_available():
        # Redis not available, skip idempotency check
        logger.debug("Redis not available, skipping idempotency check")
        return IdempotencyResult(key_hash=f"{idempotency_key}:{request_hash}")

    client = redis_service.get_client()
    if not client:
        return IdempotencyResult(key_hash=f"{idempotency_key}:{request_hash}")

    try:
        key = f"{IDEMPOTENCY_PREFIX}{idempotency_key}"
        existing = client.get(key)

        if existing:
            try:
                data = json.loads(existing)
                stored_hash = data.get("request_hash")

                # Check if request body matches (detect replay with different body)
                if stored_hash != request_hash:
                    logger.warning(
                        f"Idempotency conflict: key={idempotency_key}, "
                        f"stored_hash={stored_hash[:16]}..., "
                        f"request_hash={request_hash[:16]}..."
                    )
                    return IdempotencyResult(
                        is_duplicate=True,
                        conflict=True,
                        key_hash=f"{idempotency_key}:{request_hash}",
                    )

                # Exact duplicate - return cached response
                logger.info(
                    f"Idempotency hit: returning cached response for key={idempotency_key}"
                )
                return IdempotencyResult(
                    is_duplicate=True,
                    cached_response=data.get("response"),
                    cached_status=data.get("status_code", 200),
                    key_hash=f"{idempotency_key}:{request_hash}",
                )

            except json.JSONDecodeError:
                logger.error(f"Invalid idempotency data for key={idempotency_key}")

        return IdempotencyResult(key_hash=f"{idempotency_key}:{request_hash}")

    except Exception as e:
        logger.error(f"Idempotency check failed: {e}")
        return IdempotencyResult(key_hash=f"{idempotency_key}:{request_hash}")


async def store_idempotency_result(
    idempotency_key: str,
    request_hash: str,
    response_body: Dict,
    status_code: int,
    ttl: Optional[int] = None,
) -> bool:
    """
    Store idempotency result for future duplicate detection.

    Args:
        idempotency_key: Client-provided idempotency key
        request_hash: Hash of the request body + path
        response_body: Response to cache
        status_code: HTTP status code
        ttl: Time-to-live in seconds (default: config.IDEMPOTENCY_TTL)

    Returns:
        True if stored successfully, False otherwise
    """
    redis_service = get_redis_service()

    if not redis_service or not redis_service.is_available():
        logger.debug("Redis not available, cannot store idempotency result")
        return False

    client = redis_service.get_client()
    if not client:
        return False

    try:
        if ttl is None:
            ttl = config.IDEMPOTENCY_TTL

        key = f"{IDEMPOTENCY_PREFIX}{idempotency_key}"
        data = {
            "request_hash": request_hash,
            "response": response_body,
            "status_code": status_code,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        client.setex(key, ttl, json.dumps(data))
        logger.debug(f"Stored idempotency result: key={idempotency_key}, ttl={ttl}s")
        return True

    except Exception as e:
        logger.error(f"Failed to store idempotency result: {e}")
        return False


async def get_idempotency_key(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    """
    FastAPI dependency to extract and validate idempotency key from headers.

    Args:
        request: FastAPI request
        idempotency_key: Idempotency-Key header value

    Returns:
        Idempotency key if provided and valid, None otherwise
    """
    if not idempotency_key:
        return None

    # Validate key format (should be UUID-like or similar)
    key = idempotency_key.strip()
    if len(key) < 8 or len(key) > 128:
        logger.warning(f"Invalid idempotency key length: {len(key)}")
        return None

    return key


async def require_idempotency_key(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> str:
    """
    FastAPI dependency that REQUIRES an idempotency key.

    Raises ProblemException if not provided.

    Args:
        request: FastAPI request
        idempotency_key: Idempotency-Key header value

    Returns:
        Idempotency key

    Raises:
        ProblemException: If idempotency key is missing
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ProblemException(
            type_uri=ARCPProblemTypes.REQUIRED_HEADER_MISSING["type"],
            title="Required header missing",
            status=400,
            detail="Idempotency-Key header is required for this endpoint",
            instance=request.url.path,
        )

    key = idempotency_key.strip()
    if len(key) < 8 or len(key) > 128:
        raise ProblemException(
            type_uri=ARCPProblemTypes.INVALID_INPUT["type"],
            title="Invalid idempotency key",
            status=400,
            detail="Idempotency-Key must be 8-128 characters",
            instance=request.url.path,
        )

    return key


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling idempotency across TPR endpoints.

    Intercepts requests to idempotency-protected endpoints,
    checks for duplicate requests, and caches responses.

    Usage:
        app.add_middleware(
            IdempotencyMiddleware,
            protected_paths=["/agents/register", "/auth/agent/validate_compliance"]
        )
    """

    def __init__(self, app, protected_paths: Optional[list] = None):
        """
        Initialize idempotency middleware.

        Args:
            app: FastAPI application
            protected_paths: List of paths to protect with idempotency
        """
        super().__init__(app)
        self.protected_paths = protected_paths or [
            "/agents/register",
            "/auth/agent/validate_compliance",
        ]
        logger.info(
            f"IdempotencyMiddleware initialized for paths: {self.protected_paths}"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with idempotency checking.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response (cached or fresh)
        """
        # Only apply to protected paths
        if not any(request.url.path.endswith(p) for p in self.protected_paths):
            return await call_next(request)

        # Only apply to POST/PUT/PATCH methods
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # Check for idempotency key header
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            # No idempotency key, proceed normally
            return await call_next(request)

        try:
            # Read request body for hashing
            body = await request.body()
            request_hash = compute_request_hash(body, request.url.path, request.method)

            # Check for existing idempotent request
            result = await check_idempotency(idempotency_key, request_hash)

            if result.is_duplicate:
                if result.conflict:
                    # Same key, different request body - conflict
                    logger.warning(
                        f"Idempotency conflict for key={idempotency_key}, path={request.url.path}"
                    )
                    return JSONResponse(
                        status_code=409,
                        content={
                            "type": ARCPProblemTypes.DUPLICATE_AGENT["type"],
                            "title": "Idempotency Conflict",
                            "status": 409,
                            "detail": (
                                "An idempotent request with this key was already processed "
                                "with a different request body. Use a new Idempotency-Key "
                                "for different requests."
                            ),
                            "instance": request.url.path,
                            "idempotency_key": idempotency_key,
                        },
                        headers={"X-Idempotent-Replayed": "conflict"},
                    )

                # Exact duplicate - return cached response
                logger.info(
                    f"Returning cached idempotent response for key={idempotency_key}"
                )
                return JSONResponse(
                    status_code=result.cached_status or 200,
                    content=result.cached_response,
                    headers={"X-Idempotent-Replayed": "true"},
                )

            # Not a duplicate - process normally and cache result
            response = await call_next(request)

            # Only cache successful responses (2xx and 4xx client errors)
            if 200 <= response.status_code < 500:
                # Read response body
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk

                try:
                    response_json = json.loads(response_body.decode("utf-8"))
                    await store_idempotency_result(
                        idempotency_key,
                        request_hash,
                        response_json,
                        response.status_code,
                    )
                except json.JSONDecodeError:
                    logger.debug("Response not JSON, skipping idempotency cache")

                # Return reconstructed response
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            return response

        except Exception as e:
            logger.error(f"Idempotency middleware error: {e}", exc_info=True)
            # On error, proceed without idempotency protection
            return await call_next(request)


# Dependency instances for FastAPI routes
GetIdempotencyKey = Depends(get_idempotency_key)
RequireIdempotencyKey = Depends(require_idempotency_key)
