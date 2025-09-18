"""
API Protection utilities for ARCP.

This module provides comprehensive protection for all API endpoints with a hierarchical permission system:

 PUBLIC:  Anyone with ARCP URL can access (no authentication)
 AGENT:   Authenticated agents (inherits Public access)
 ADMIN:   Authenticated admins (inherits Public + Agent access)
 ADMIN_PIN: Admin with PIN verification (inherits all above)

Usage Examples:
- @router.get("/public/discover")                    # PUBLIC
- @router.get("/agents", dependencies=[RequireAgent]) # AGENT
- @router.delete("/agents/{id}", dependencies=[RequireAdmin]) # ADMIN
- @router.post("/?/?", dependencies=[RequireAdminPin]) # ADMIN_PIN
"""

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, Header, Request

from ..core.config import config
from ..core.exceptions import ARCPProblemTypes, ProblemException
from ..core.middleware import record_auth_attempt
from ..utils.sessions import get_session_info, get_token_payload, verify_session_pin

try:
    from ..utils.sessions import get_token_ref_from_request
except Exception:
    get_token_ref_from_request = None  # type: ignore
from ..utils.auth_logging import log_security_event

logger = logging.getLogger(__name__)


class PermissionLevel:
    """
    Hierarchical permission levels for ARCP API endpoints.

    Each level inherits permissions from lower levels:
    PUBLIC → AGENT → ADMIN → ADMIN_PIN
    """

    PUBLIC = "public"  # No authentication required
    AGENT = "agent"  # Agent authentication required (+ PUBLIC)
    ADMIN = "admin"  # Admin authentication required (+ PUBLIC + AGENT)
    ADMIN_PIN = "admin_pin"  # Admin + PIN verification (+ all above)

    # Hierarchical permission inheritance
    PERMISSION_HIERARCHY = {
        PUBLIC: [],
        AGENT: [PUBLIC],
        ADMIN: [PUBLIC, AGENT],
        ADMIN_PIN: [PUBLIC, AGENT, ADMIN],
    }

    # Role to permission mapping
    ROLE_PERMISSIONS = {
        "public": [PUBLIC],
        "agent": [PUBLIC, AGENT],
        "admin": [
            PUBLIC,
            AGENT,
            ADMIN,
            ADMIN_PIN,
        ],  # Admin has all permissions
    }

    @classmethod
    def can_access(cls, user_role: str, required_permission: str) -> bool:
        """
        Check if a user role can access an endpoint requiring specific permission.

        Args:
            user_role: User's role (public, agent, admin)
            required_permission: Required permission level

        Returns:
            True if access is allowed, False otherwise
        """
        user_permissions = cls.ROLE_PERMISSIONS.get(user_role, [])
        return required_permission in user_permissions


async def verify_api_token(
    request: Request,
    authorization: str = Header(None, alias="Authorization"),
    required_permission: str = PermissionLevel.AGENT,
    require_pin: bool = False,
) -> Dict[str, Any]:
    """
    Verify API token and check hierarchical permissions.

    Args:
        request: FastAPI request object
        authorization: Authorization header
        required_permission: Required permission level (PUBLIC, AGENT, ADMIN, ADMIN_PIN)
        require_pin: Whether PIN verification is required

    Returns:
        Token payload with user information

    Raises:
        ProblemException: If authentication or authorization fails
    """

    # PUBLIC endpoints - no authentication required
    if required_permission == PermissionLevel.PUBLIC:
        logger.debug(f"Public access granted to {request.url.path}")
        return {
            "role": "public",
            "sub": "anonymous",
            "permissions": [PermissionLevel.PUBLIC],
        }

    # Check for authorization header (required for AGENT, ADMIN, ADMIN_PIN)
    if not authorization or not authorization.startswith("Bearer "):
        await log_security_event(
            "unauthorized_access_attempt",
            f"Missing or invalid authorization header for {request.url.path}",
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.AUTHENTICATION_FAILED["type"],
            title=ARCPProblemTypes.AUTHENTICATION_FAILED["title"],
            status=401,
            detail=f"Authentication required for {required_permission} endpoint",
            instance=request.url.path,
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        # Verify and decode token
        payload = get_token_payload(token)
        if not payload:
            await log_security_event(
                "invalid_token_access",
                f"Invalid token used for {request.url.path}",
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
            )
            raise ProblemException(
                type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
                title=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["title"],
                status=401,
                detail="Invalid or expired token",
                instance=request.url.path,
            )

        user_role = payload.get(
            "role", "agent"
        )  # Default to agent for backward compatibility
        user_id = payload.get("sub")
        is_temp_token = payload.get("temp_registration", False)

        # Add permissions and convenience flags to payload for easier access
        user_permissions = PermissionLevel.ROLE_PERMISSIONS.get(
            user_role, [PermissionLevel.PUBLIC]
        )
        payload["permissions"] = user_permissions
        payload["is_admin"] = user_role == "admin"

        logger.debug(
            f"Token verification for {request.url.path}: "
            f"role={user_role}, user_id={user_id}, is_temp={is_temp_token}, "
            f"required={required_permission}, permissions={user_permissions}"
        )

        # Special handling for temporary registration tokens
        if is_temp_token and required_permission == PermissionLevel.AGENT:
            logger.info(
                f"Allowing temporary token access to AGENT endpoint: {request.url.path}"
            )
            return payload  # Allow temp tokens for agent registration

        # Check hierarchical permissions
        if not PermissionLevel.can_access(user_role, required_permission):
            await log_security_event(
                "insufficient_permissions",
                f"User {user_id} with role {user_role} attempted to access {request.url.path} requiring {required_permission}",
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
                user_id=user_id,
                user_role=user_role,
                required_permission=required_permission,
            )
            raise ProblemException(
                type_uri=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["type"],
                title=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["title"],
                status=403,
                detail=f"Access denied: {user_role} role cannot access {required_permission} endpoint",
                instance=request.url.path,
            )

        # Additional validation for admin users (but not for temp tokens)
        if user_role == "admin" and not is_temp_token:
            # Bind admin tokens to session context: fingerprint + token reference
            fingerprint = request.headers.get("X-Client-Fingerprint")
            token_ref = (
                get_token_ref_from_request(request)
                if get_token_ref_from_request
                else None
            )
            session = None
            if fingerprint and token_ref:
                session = get_session_info(user_id, fingerprint, token_ref)
            if not session:
                await log_security_event(
                    "missing_or_mismatched_admin_session",
                    f"Admin user {user_id} missing bound session for {request.url.path}",
                    severity="WARNING",
                    request=request,
                    endpoint=request.url.path,
                    user_id=user_id,
                )
                raise ProblemException(
                    type_uri=ARCPProblemTypes.SESSION_VALIDATION_FAILED["type"],
                    title=ARCPProblemTypes.SESSION_VALIDATION_FAILED["title"],
                    status=401,
                    detail="Admin session validation failed",
                    instance=request.url.path,
                )

        # Log successful access for privileged endpoints
        if required_permission in [
            PermissionLevel.ADMIN,
            PermissionLevel.ADMIN_PIN,
        ]:
            await log_security_event(
                "privileged_endpoint_access",
                f"User {user_id} ({user_role}) accessed {required_permission} endpoint: {request.url.path}",
                severity="INFO",
                request=request,
                endpoint=request.url.path,
                user_id=user_id,
                user_role=user_role,
                required_permission=required_permission,
            )

        return payload

    except ProblemException:
        raise
    except Exception as e:
        await log_security_event(
            "token_verification_error",
            f"Token verification error for {request.url.path}: {str(e)}",
            severity="ERROR",
            request=request,
            endpoint=request.url.path,
            error=str(e),
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.AUTHENTICATION_FAILED["type"],
            title=ARCPProblemTypes.AUTHENTICATION_FAILED["title"],
            status=401,
            detail="Authentication failed",
            instance=request.url.path,
        )


async def verify_pin_access(
    request: Request,
    user_payload: Dict[str, Any],
    x_session_pin: str = Header(None, alias="X-Session-Pin"),
) -> Dict[str, Any]:
    """
    Verify PIN for ADMIN_PIN protected endpoints.

    Args:
        request: FastAPI request object
        user_payload: Already verified user token payload
        x_session_pin: PIN from header

    Returns:
        Updated payload with PIN verification status

    Raises:
        ProblemException: If PIN verification fails
    """
    user_id = user_payload.get("sub")

    if not x_session_pin:
        await log_security_event(
            "missing_pin_access",
            f"PIN required but not provided for {request.url.path}",
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
            user_id=user_id,
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.PIN_REQUIRED["type"],
            title=ARCPProblemTypes.PIN_REQUIRED["title"],
            status=400,
            detail="PIN required for this operation",
            instance=request.url.path,
        )

    try:
        if not verify_session_pin(user_id, x_session_pin):
            await log_security_event(
                "invalid_pin_access",
                f"Invalid PIN provided for {request.url.path}",
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
                user_id=user_id,
            )
            await record_auth_attempt(request, False, "pin")
            raise ProblemException(
                type_uri=ARCPProblemTypes.PIN_INCORRECT["type"],
                title=ARCPProblemTypes.PIN_INCORRECT["title"],
                status=401,
                detail="Invalid PIN",
                instance=request.url.path,
            )

        await log_security_event(
            "pin_protected_access",
            f"PIN-protected endpoint {request.url.path} accessed by {user_id}",
            severity="INFO",
            request=request,
            endpoint=request.url.path,
            user_id=user_id,
        )
        await record_auth_attempt(request, True, "pin")

        # Add PIN verification to payload
        user_payload["pin_verified"] = True
        return user_payload

    except ProblemException:
        raise
    except Exception as e:
        await log_security_event(
            "pin_verification_error",
            f"PIN verification error for {request.url.path}: {str(e)}",
            severity="ERROR",
            request=request,
            endpoint=request.url.path,
            user_id=user_id,
            error=str(e),
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.INTERNAL_ERROR["type"],
            title=ARCPProblemTypes.INTERNAL_ERROR["title"],
            status=500,
            detail="PIN verification failed",
            instance=request.url.path,
        )


# ========================================
# PERMISSION DEPENDENCY FUNCTIONS
# ========================================


async def verify_public(request: Request) -> Dict[str, Any]:
    """PUBLIC: No authentication required - anyone can access."""
    return await verify_api_token(request, None, PermissionLevel.PUBLIC)


async def verify_agent(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """AGENT: Requires agent authentication (inherits PUBLIC access)."""
    return await verify_api_token(request, authorization, PermissionLevel.AGENT)


async def verify_admin(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """ADMIN: Requires admin authentication (inherits PUBLIC + AGENT access)."""
    return await verify_api_token(request, authorization, PermissionLevel.ADMIN)


async def verify_admin_pin(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_session_pin: Optional[str] = Header(None, alias="X-Session-Pin"),
) -> Dict[str, Any]:
    """ADMIN_PIN: Requires admin authentication + PIN (inherits all above access)."""
    # First verify admin token
    payload = await verify_api_token(request, authorization, PermissionLevel.ADMIN)
    # Then verify PIN
    return await verify_pin_access(request, payload, x_session_pin)


# Dependency objects - these will be used directly
RequirePublic = Depends(verify_public)
RequireAgent = Depends(verify_agent)
RequireAdmin = Depends(verify_admin)


# ========================================
# METRICS SCRAPER DEPENDENCY (pre-shared token)
# ========================================


async def verify_metrics_scraper(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Lightweight auth just for Prometheus scraping:
    - Accepts Authorization: Bearer <ARCP_METRICS_TOKEN>
    - Does NOT grant broader admin abilities

    Enabled only when config.METRICS_SCRAPE_TOKEN is set. Otherwise, denied.
    """
    # Require configured secret
    scrape_token = getattr(config, "METRICS_SCRAPE_TOKEN", None)
    if not scrape_token:
        # Feature disabled when no token is configured
        raise ProblemException(
            type_uri=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["type"],
            title=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["title"],
            status=403,
            detail="Metrics scraping not enabled",
            instance=request.url.path,
        )

    # Validate bearer token
    if not authorization or not authorization.startswith("Bearer "):
        raise ProblemException(
            type_uri=ARCPProblemTypes.AUTHENTICATION_FAILED["type"],
            title=ARCPProblemTypes.AUTHENTICATION_FAILED["title"],
            status=401,
            detail="Authentication required",
            instance=request.url.path,
        )

    provided = authorization[7:]
    if provided != scrape_token:
        raise ProblemException(
            type_uri=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["type"],
            title=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["title"],
            status=403,
            detail="Invalid scrape token",
            instance=request.url.path,
        )

    # Return minimal identity payload
    return {
        "role": "metrics_scraper",
        "sub": "prometheus",
        "permissions": [PermissionLevel.PUBLIC],
    }


RequireMetricsScraper = Depends(verify_metrics_scraper)
RequireAdminPin = Depends(verify_admin_pin)


# USER INFO HELPER FUNCTIONS


def get_current_agent():
    """Get current authenticated agent information."""

    def _get_agent(payload: Dict[str, Any] = RequireAgent) -> Dict[str, Any]:
        return {
            "user_id": payload.get("sub"),
            "agent_id": payload.get("agent_id"),
            "role": payload.get("role", "agent"),
            "is_admin": payload.get("role") == "admin",
            "is_temp": payload.get("temp_registration", False),
            "permissions": payload.get("permissions", []),
        }

    return Depends(_get_agent)


def get_current_admin():
    """Get current authenticated admin user information."""

    def _get_admin(payload: Dict[str, Any] = RequireAdmin) -> Dict[str, Any]:
        return {
            "user_id": payload.get("sub"),
            "agent_id": payload.get("agent_id"),
            "role": payload.get("role"),
            "is_admin": True,
            "permissions": payload.get("permissions", []),
        }

    return Depends(_get_admin)


def get_current_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Get current user information from any authentication level."""
    return {
        "user_id": payload.get("sub"),
        "agent_id": payload.get("agent_id"),
        "role": payload.get("role", "public"),
        "is_admin": payload.get("role") == "admin",
        "is_agent": payload.get("role") in ["agent", "admin"],
        "is_temp": payload.get("temp_registration", False),
        "permissions": payload.get("permissions", [PermissionLevel.PUBLIC]),
        "pin_verified": payload.get("pin_verified", False),
    }


# PERMISSION HELPER FUNCTIONS


def has_permission(user_payload: Dict[str, Any], required_permission: str) -> bool:
    """Check if user has specific permission."""
    user_permissions = user_payload.get("permissions", [])
    return required_permission in user_permissions


def require_permission(required_permission: str) -> Callable:
    """Create a dependency that requires a specific permission level."""

    # Closure that captures the required_permission
    def _check_permission_factory():
        async def _check_permission(
            request: Request,
            authorization: str = Header(None, alias="Authorization"),
        ) -> Dict[str, Any]:
            return await verify_api_token(request, authorization, required_permission)

        return _check_permission

    return Depends(_check_permission_factory())


def check_endpoint_access(user_role: str, endpoint_permission: str) -> bool:
    """Check if a user role can access an endpoint requiring specific permission."""
    return PermissionLevel.can_access(user_role, endpoint_permission)
