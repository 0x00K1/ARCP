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
from .dpop import get_dpop_validator

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
            "access.unauthorized_attempt",
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
                "access.invalid_token",
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

        # TPR Enforcement: When Three-Phase Registration is enabled, enforce token audiences
        if config.FEATURE_THREE_PHASE:
            token_audience = payload.get("aud", "")
            token_type = payload.get("token_type", "")
            request_path = request.url.path

            # Define which paths require which token types
            # Phase 2: validate_compliance requires temp token with aud=arcp:validate
            if request_path.endswith("/validate_compliance"):
                if token_type != "temp" or token_audience != config.TOKEN_AUD_VALIDATE:
                    logger.warning(
                        f"TPR enforcement: {request_path} requires temp token with aud={config.TOKEN_AUD_VALIDATE}, "
                        f"got token_type={token_type}, aud={token_audience}"
                    )
                    raise ProblemException(
                        type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
                        title="Invalid Token for Validation",
                        status=403,
                        detail=f"Validation requires temporary token with audience '{config.TOKEN_AUD_VALIDATE}'. "
                        f"Please request a temp token first via /auth/agent/request_temp_token",
                        instance=request_path,
                    )
                logger.info(f"TPR Phase 2: Valid temp token for {request_path}")
                return payload

            # Phase 3: /agents/register requires validated token with aud=arcp:register
            if request_path.endswith("/agents/register"):
                if (
                    token_type != "validated"
                    or token_audience != config.TOKEN_AUD_REGISTER
                ):
                    logger.warning(
                        f"TPR enforcement: {request_path} requires validated token with aud={config.TOKEN_AUD_REGISTER}, "
                        f"got token_type={token_type}, aud={token_audience}"
                    )
                    raise ProblemException(
                        type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
                        title="Invalid Token for Registration",
                        status=403,
                        detail=f"Registration requires validated token with audience '{config.TOKEN_AUD_REGISTER}'. "
                        f"Please complete validation first via /auth/agent/validate_compliance",
                        instance=request_path,
                    )
                logger.info(
                    f"TPR Phase 3: Valid validated token for registration of agent {user_id}"
                )
                return payload
        else:
            # Basic mode: Allow temp tokens for agent registration when TPR is disabled
            if is_temp_token and required_permission == PermissionLevel.AGENT:
                logger.info(
                    f"Basic mode: Allowing temporary token access to AGENT endpoint: {request.url.path}"
                )
                return payload  # Allow temp tokens for agent registration

        # Check hierarchical permissions
        if not PermissionLevel.can_access(user_role, required_permission):
            await log_security_event(
                "access.insufficient_permissions",
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
                    "access.missing_admin_session",
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
                "access.privileged_endpoint",
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
            "token.verification_error",
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
            "pin.missing_access",
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
                "pin.invalid_access",
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
            "access.pin_protected",
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
            "pin.verification_error",
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


# ========================================
# DPoP VERIFICATION DEPENDENCY
# ========================================


async def verify_dpop(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
    dpop_header: Optional[str] = Header(None, alias="DPoP"),
) -> Dict[str, Any]:
    """
    Verify DPoP proof for sender-constrained tokens.

    Used on endpoints that require proof-of-possession per RFC 9449.

    Flow:
    1. Verify the access token normally
    2. If DPoP required and no header, reject
    3. Extract expected jkt from token's cnf claim
    4. Validate DPoP proof
    5. Verify proof's jkt matches token's cnf.jkt

    Args:
        request: FastAPI request object
        authorization: Bearer token
        dpop_header: DPoP proof JWT

    Returns:
        Token payload with dpop_jkt added

    Raises:
        ProblemException: If DPoP validation fails
    """
    dpop_required = getattr(config, "DPOP_REQUIRED", False)
    dpop_enabled = getattr(config, "DPOP_ENABLED", True)

    # Verify the token first
    payload = await verify_api_token(request, authorization, PermissionLevel.AGENT)

    # If DPoP is disabled entirely, just return the payload
    if not dpop_enabled:
        return payload

    # Check if DPoP proof is required
    if dpop_required and not dpop_header:
        await log_security_event(
            "dpop.missing_proof",
            f"DPoP proof required but not provided for {request.url.path}",
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.DPOP_REQUIRED["type"],
            title=ARCPProblemTypes.DPOP_REQUIRED["title"],
            status=ARCPProblemTypes.DPOP_REQUIRED["default_status"],
            detail="This endpoint requires a DPoP proof header",
            instance=request.url.path,
        )

    # If no DPoP header and not required, return payload
    if not dpop_header:
        return payload

    # Extract expected jkt from token's cnf claim
    cnf = payload.get("cnf", {})
    expected_jkt = cnf.get("jkt")

    # If token has no cnf.jkt but DPoP is required, that's an error
    if dpop_required and not expected_jkt:
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_NOT_DPOP_BOUND["type"],
            title=ARCPProblemTypes.TOKEN_NOT_DPOP_BOUND["title"],
            status=ARCPProblemTypes.TOKEN_NOT_DPOP_BOUND["default_status"],
            detail="Access token does not have DPoP binding (missing cnf.jkt)",
            instance=request.url.path,
        )

    # Get full request URI
    # Handle both HTTP and HTTPS (proxy may set X-Forwarded-Proto)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    http_uri = f"{scheme}://{host}{request.url.path}"
    http_method = request.method

    # Get access token from Authorization header
    access_token = authorization.replace("Bearer ", "")

    # Validate DPoP proof
    validator = get_dpop_validator()
    result = await validator.validate_proof(
        dpop_header=dpop_header,
        http_method=http_method,
        http_uri=http_uri,
        access_token=access_token,
        expected_jkt=expected_jkt,
    )

    if not result.valid:
        await log_security_event(
            "dpop.validation_failed",
            f"DPoP validation failed: {result.error_detail}",
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
            error=result.error.value if result.error else "unknown",
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.DPOP_INVALID["type"],
            title=ARCPProblemTypes.DPOP_INVALID["title"],
            status=ARCPProblemTypes.DPOP_INVALID["default_status"],
            detail=result.error_detail or "DPoP proof validation failed",
            instance=request.url.path,
        )

    # Add DPoP info to payload
    payload["dpop_jkt"] = result.jkt
    payload["dpop_validated"] = True

    logger.debug(
        f"DPoP proof validated for {request.url.path}, jkt={result.jkt[:16]}..."
    )

    return payload


# Dependency for DPoP-protected endpoints
RequireDPoP = Depends(verify_dpop)


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


# ========== TPR Token Dependencies ==========


async def verify_temp_token(
    request: Request, authorization: str = Header(None, alias="Authorization")
) -> Dict[str, Any]:
    """
    Verify temporary token (Phase 1 → Phase 2).

    Validates that the token:
    - Is a valid Bearer token
    - Has audience = arcp:validate
    - Has token_type = temp
    - Is not expired

    Args:
        request: FastAPI request
        authorization: Authorization header

    Returns:
        Token payload with agent information

    Raises:
        ProblemException: If token is invalid or wrong type

    Usage:
        @router.post("/validate_compliance")
        async def validate(
            current_token: Dict = Depends(verify_temp_token)
        ):
            agent_id = current_token["agent_id"]
            ...
    """
    # Check for authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise ProblemException(
            type_uri=ARCPProblemTypes.AUTHENTICATION_FAILED["type"],
            title="Missing or invalid authorization",
            status=401,
            detail="Bearer token required",
            instance=request.url.path,
        )

    token = authorization[7:]  # Remove "Bearer " prefix
    payload = get_token_payload(token)

    if not payload:
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token",
            status=401,
            detail="Token is invalid or expired",
            instance=request.url.path,
        )

    # Check audience
    aud = payload.get("aud")
    if aud != config.TOKEN_AUD_VALIDATE:
        logger.warning(
            f"Token audience mismatch: expected '{config.TOKEN_AUD_VALIDATE}', got '{aud}'"
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token audience",
            status=403,
            detail=f"Token audience must be '{config.TOKEN_AUD_VALIDATE}' for validation",
            instance=request.url.path,
        )

    # Check token type
    token_type = payload.get("token_type")
    if token_type != "temp":
        logger.warning(f"Token type mismatch: expected 'temp', got '{token_type}'")
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token type",
            status=403,
            detail="Token type must be 'temp' for validation",
            instance=request.url.path,
        )

    logger.debug(
        f"Temp token verified for agent {payload.get('agent_id')} "
        f"(aud={aud}, type={token_type})"
    )

    return payload


async def verify_validated_token(
    request: Request, authorization: str = Header(None, alias="Authorization")
) -> Dict[str, Any]:
    """
    Verify validated token (Phase 2 → Phase 3).

    Validates that the token:
    - Is a valid Bearer token
    - Has audience = arcp:register
    - Has token_type = validated
    - Has validation_id
    - Is not expired

    Args:
        request: FastAPI request
        authorization: Authorization header

    Returns:
        Token payload with agent and validation information

    Raises:
        ProblemException: If token is invalid or wrong type

    Usage:
        @router.post("/agents/register")
        async def register(
            current_token: Dict = Depends(verify_validated_token)
        ):
            agent_id = current_token["agent_id"]
            validation_id = current_token["validation_id"]
            ...
    """
    # Check for authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise ProblemException(
            type_uri=ARCPProblemTypes.AUTHENTICATION_FAILED["type"],
            title="Missing or invalid authorization",
            status=401,
            detail="Bearer token required",
            instance=request.url.path,
        )

    token = authorization[7:]  # Remove "Bearer " prefix
    payload = get_token_payload(token)

    if not payload:
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token",
            status=401,
            detail="Token is invalid or expired",
            instance=request.url.path,
        )

    # Check audience
    aud = payload.get("aud")
    if aud != config.TOKEN_AUD_REGISTER:
        logger.warning(
            f"Token audience mismatch: expected '{config.TOKEN_AUD_REGISTER}', got '{aud}'"
        )
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token audience",
            status=403,
            detail=f"Token audience must be '{config.TOKEN_AUD_REGISTER}' for registration",
            instance=request.url.path,
        )

    # Check token type
    token_type = payload.get("token_type")
    if token_type != "validated":
        logger.warning(f"Token type mismatch: expected 'validated', got '{token_type}'")
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid token type",
            status=403,
            detail="Token type must be 'validated' for registration",
            instance=request.url.path,
        )

    # Check validation_id exists
    validation_id = payload.get("validation_id")
    if not validation_id:
        logger.error("Validated token missing validation_id")
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_VALIDATION_ERROR["type"],
            title="Invalid validated token",
            status=403,
            detail="Validated token must contain validation_id",
            instance=request.url.path,
        )

    logger.debug(
        f"Validated token verified for agent {payload.get('agent_id')} "
        f"(aud={aud}, type={token_type}, validation_id={validation_id})"
    )

    return payload


# Convenience dependency instances for FastAPI routes
RequireTemp = Depends(verify_temp_token)
RequireValidated = Depends(verify_validated_token)
