"""
Security Enforcement Utilities for ARCP.

This module provides unified enforcement of DPoP and mTLS security
requirements for the agent registration flow.

When DPOP_REQUIRED=true and/or MTLS_REQUIRED_REMOTE=true,
these utilities ensure that requests without proper credentials are
rejected rather than just logged.

Usage:
    from arcp.utils.security_enforcement import (
        enforce_dpop_if_required,
        enforce_mtls_if_required,
        RequireSecureAgent,
    )

    # In endpoint:
    @router.post("/register", dependencies=[RequireSecureAgent])
    async def register_agent(...):
        ...
"""

import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, Header, Request

from ..core.config import config
from ..core.exceptions import ARCPProblemTypes, ProblemException
from .api_protection import PermissionLevel, verify_api_token
from .auth_logging import log_security_event
from .dpop import DPoPValidationResult, get_dpop_validator
from .mtls import get_mtls_handler, is_mtls_required

logger = logging.getLogger(__name__)


async def enforce_dpop_if_required(
    request: Request,
    authorization: str,
    dpop_header: Optional[str],
    endpoint_name: str = "endpoint",
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Enforce DPoP proof if DPOP_REQUIRED is true.

    Args:
        request: FastAPI request object
        authorization: Bearer token from Authorization header
        dpop_header: DPoP proof JWT from DPoP header
        endpoint_name: Name of endpoint for logging

    Returns:
        Tuple of (is_valid, jkt_thumbprint, error_message)
        - If DPoP not required/enabled: (True, None, None)
        - If DPoP valid: (True, jkt, None)
        - If DPoP invalid/missing: (False, None, error_message)
    """
    dpop_enabled = getattr(config, "DPOP_ENABLED", False)
    dpop_required = getattr(config, "DPOP_REQUIRED", False)

    # If DPoP is disabled entirely, skip
    if not dpop_enabled:
        logger.debug(f"DPoP disabled, skipping enforcement for {endpoint_name}")
        return True, None, None

    # If DPoP is not required, capture if present but don't reject
    if not dpop_required:
        if dpop_header:
            # Validate if provided, but don't reject on failure
            result = await _validate_dpop_proof(request, authorization, dpop_header)
            if result.valid:
                logger.debug(
                    f"DPoP proof valid (optional) for {endpoint_name}: jkt={result.jkt[:16]}..."
                )
                return True, result.jkt, None
            else:
                logger.warning(
                    f"DPoP proof invalid (optional) for {endpoint_name}: {result.error_detail}"
                )
        return True, None, None

    # DPoP is REQUIRED
    if not dpop_header:
        error_msg = f"DPoP proof required but not provided for {endpoint_name}"
        logger.warning(error_msg)
        await log_security_event(
            "dpop.required_missing",
            error_msg,
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
        )
        return False, None, "DPoP proof header is required"

    # Validate the DPoP proof
    result = await _validate_dpop_proof(request, authorization, dpop_header)

    if not result.valid:
        error_msg = (
            f"DPoP proof validation failed for {endpoint_name}: {result.error_detail}"
        )
        logger.warning(error_msg)
        await log_security_event(
            "dpop.validation_failed",
            error_msg,
            severity="WARNING",
            request=request,
            endpoint=request.url.path,
            error=result.error.value if result.error else "unknown",
        )
        return False, None, result.error_detail or "DPoP proof validation failed"

    logger.debug(f"DPoP proof validated for {endpoint_name}: jkt={result.jkt[:16]}...")
    return True, result.jkt, None


async def _validate_dpop_proof(
    request: Request,
    authorization: str,
    dpop_header: str,
) -> DPoPValidationResult:
    """
    Internal helper to validate a DPoP proof.

    Args:
        request: FastAPI request object
        authorization: Bearer token
        dpop_header: DPoP proof JWT

    Returns:
        DPoPValidationResult with validation outcome
    """
    validator = get_dpop_validator()

    # Get full request URI
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    http_uri = f"{scheme}://{host}{request.url.path}"
    http_method = request.method

    # Get access token from Authorization header
    access_token = (
        authorization.replace("Bearer ", "")
        if authorization.startswith("Bearer ")
        else authorization
    )

    return await validator.validate_proof(
        dpop_header=dpop_header,
        http_method=http_method,
        http_uri=http_uri,
        access_token=access_token if access_token else None,
    )


async def enforce_mtls_if_required(
    request: Request,
    endpoint_name: str = "endpoint",
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Enforce mTLS client certificate if required for this request.

    mTLS is required for remote agents when:
    - MTLS_ENABLED=true
    - MTLS_REQUIRED_REMOTE=true
    - Request is from remote client (not localhost)

    Args:
        request: FastAPI request object
        endpoint_name: Name of endpoint for logging

    Returns:
        Tuple of (is_valid, spki_hash, error_message)
        - If mTLS not required: (True, None, None)
        - If mTLS valid: (True, spki_hash, None)
        - If mTLS invalid/missing: (False, None, error_message)
    """
    mtls_enabled = getattr(config, "MTLS_ENABLED", False)

    # If mTLS is disabled entirely, skip
    if not mtls_enabled:
        logger.debug(f"mTLS disabled, skipping enforcement for {endpoint_name}")
        return True, None, None

    # Check if mTLS is required for this specific request
    mtls_required = is_mtls_required(request)

    # Extract and validate certificate
    handler = get_mtls_handler()
    cert, error = handler.extract_and_validate(request)

    if cert is None:
        if mtls_required:
            # Certificate required but not provided/valid
            error_msg = error or "Client certificate required for remote agents"
            logger.warning(f"mTLS required but failed for {endpoint_name}: {error_msg}")
            await log_security_event(
                "mtls.required_missing",
                error_msg,
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
            )
            return False, None, error_msg
        else:
            # Not required for this request (e.g., localhost)
            logger.debug(f"mTLS not required for local request to {endpoint_name}")
            return True, None, None

    # Certificate provided and valid
    logger.debug(
        f"mTLS certificate validated for {endpoint_name}: spki={cert.spki_hash[:16]}..."
    )
    return True, cert.spki_hash, None


async def verify_secure_agent(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
    dpop_header: Optional[str] = Header(None, alias="DPoP"),
) -> Dict[str, Any]:
    """
    Verify agent token with DPoP and mTLS enforcement.

    This is a FastAPI dependency that combines:
    1. Standard token verification (RequireAgent)
    2. DPoP proof validation (if DPOP_REQUIRED=true)
    3. mTLS certificate validation (if MTLS_REQUIRED_REMOTE=true for remote agents)

    Args:
        request: FastAPI request object
        authorization: Authorization header
        dpop_header: DPoP header

    Returns:
        Token payload with additional security bindings

    Raises:
        ProblemException: If any security check fails
    """
    # Step 1: Verify the base token
    payload = await verify_api_token(request, authorization, PermissionLevel.AGENT)

    # Step 2: Enforce DPoP if required
    dpop_valid, dpop_jkt, dpop_error = await enforce_dpop_if_required(
        request=request,
        authorization=authorization,
        dpop_header=dpop_header,
        endpoint_name=request.url.path,
    )

    if not dpop_valid:
        raise ProblemException(
            type_uri=ARCPProblemTypes.DPOP_REQUIRED["type"],
            title=ARCPProblemTypes.DPOP_REQUIRED["title"],
            status=ARCPProblemTypes.DPOP_REQUIRED["default_status"],
            detail=dpop_error or "DPoP proof is required for this endpoint",
            instance=request.url.path,
        )

    # Step 3: Enforce mTLS if required
    mtls_valid, mtls_spki, mtls_error = await enforce_mtls_if_required(
        request=request,
        endpoint_name=request.url.path,
    )

    if not mtls_valid:
        raise ProblemException(
            type_uri=ARCPProblemTypes.MTLS_REQUIRED["type"],
            title=ARCPProblemTypes.MTLS_REQUIRED["title"],
            status=ARCPProblemTypes.MTLS_REQUIRED["default_status"],
            detail=mtls_error
            or "mTLS client certificate is required for remote agents",
            instance=request.url.path,
        )

    # Step 4: If token has security bindings, verify they match
    cnf = payload.get("cnf", {})

    # Verify DPoP binding if present in token
    expected_jkt = cnf.get("jkt")
    if expected_jkt and dpop_jkt:
        if expected_jkt != dpop_jkt:
            await log_security_event(
                "dpop.binding_mismatch",
                f"DPoP JKT mismatch: token has {expected_jkt[:16]}..., proof has {dpop_jkt[:16]}...",
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
            )
            raise ProblemException(
                type_uri=ARCPProblemTypes.DPOP_BINDING_MISMATCH["type"],
                title=ARCPProblemTypes.DPOP_BINDING_MISMATCH["title"],
                status=ARCPProblemTypes.DPOP_BINDING_MISMATCH["default_status"],
                detail="DPoP proof key does not match token binding",
                instance=request.url.path,
            )

    # Verify mTLS binding if present in token
    expected_spki = cnf.get("x5t#S256")
    if expected_spki and mtls_spki:
        if expected_spki != mtls_spki:
            await log_security_event(
                "mtls.binding_mismatch",
                f"mTLS SPKI mismatch: token has {expected_spki[:16]}..., cert has {mtls_spki[:16]}...",
                severity="WARNING",
                request=request,
                endpoint=request.url.path,
            )
            raise ProblemException(
                type_uri=ARCPProblemTypes.MTLS_BINDING_MISMATCH["type"],
                title=ARCPProblemTypes.MTLS_BINDING_MISMATCH["title"],
                status=ARCPProblemTypes.MTLS_BINDING_MISMATCH["default_status"],
                detail="Client certificate does not match token binding",
                instance=request.url.path,
            )

    # Add security bindings to payload for downstream use
    payload["dpop_jkt"] = dpop_jkt
    payload["mtls_spki"] = mtls_spki
    payload["dpop_validated"] = dpop_jkt is not None
    payload["mtls_validated"] = mtls_spki is not None

    return payload


# FastAPI dependency for endpoints requiring full security enforcement
RequireSecureAgent = Depends(verify_secure_agent)


async def extract_security_bindings(
    request: Request,
    authorization: str,
    dpop_header: Optional[str],
) -> Dict[str, Optional[str]]:
    """
    Extract and validate security bindings for token creation.

    Used during Phase 2 (validate_compliance) to capture DPoP/mTLS
    bindings that will be embedded in the validated token.

    Security requirements are enforced INDEPENDENTLY:
    - If DPOP_REQUIRED=true: DPoP proof MUST be provided
    - If MTLS_ENABLED=true AND MTLS_REQUIRED_REMOTE=true AND remote client:
      mTLS certificate MUST be provided
    - If BOTH are required: BOTH must be provided (no fallback)
    - If neither is required: both are optional but will be captured if present

    Args:
        request: FastAPI request object
        authorization: Bearer token
        dpop_header: DPoP proof JWT

    Returns:
        Dict with 'dpop_jkt', 'mtls_spki', and any 'error'

    Raises:
        ProblemException: If required security is missing
    """
    result = {
        "dpop_jkt": None,
        "mtls_spki": None,
        "error": None,
    }

    # Check DPoP - enforce if required
    dpop_valid, dpop_jkt, dpop_error = await enforce_dpop_if_required(
        request=request,
        authorization=authorization,
        dpop_header=dpop_header,
        endpoint_name="validate_compliance",
    )

    # If DPoP was required but failed, reject immediately
    if not dpop_valid:
        raise ProblemException(
            type_uri=ARCPProblemTypes.DPOP_REQUIRED["type"],
            title=ARCPProblemTypes.DPOP_REQUIRED["title"],
            status=ARCPProblemTypes.DPOP_REQUIRED["default_status"],
            detail=dpop_error or "DPoP proof is required for validation",
            instance=request.url.path,
        )

    result["dpop_jkt"] = dpop_jkt

    # Check mTLS - enforce if required (independent of DPoP)
    mtls_valid, mtls_spki, mtls_error = await enforce_mtls_if_required(
        request=request,
        endpoint_name="validate_compliance",
    )

    # If mTLS was required but failed, reject immediately
    if not mtls_valid:
        raise ProblemException(
            type_uri=ARCPProblemTypes.MTLS_REQUIRED["type"],
            title=ARCPProblemTypes.MTLS_REQUIRED["title"],
            status=ARCPProblemTypes.MTLS_REQUIRED["default_status"],
            detail=mtls_error or "mTLS client certificate is required",
            instance=request.url.path,
        )

    result["mtls_spki"] = mtls_spki

    # Log security bindings captured
    has_dpop = dpop_jkt is not None
    has_mtls = mtls_spki is not None

    if has_dpop or has_mtls:
        logger.debug(
            f"Security bindings captured: dpop_jkt={has_dpop}, mtls_spki={has_mtls}"
        )

    return result
