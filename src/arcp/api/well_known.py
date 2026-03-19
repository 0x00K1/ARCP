"""
Well-Known Endpoints for ARCP.

Implements RFC 8615 well-known URIs for ARCP service discovery and JWKS.

Endpoints:
- /.well-known/jwks.json - JSON Web Key Set for token verification
- /.well-known/arcp-configuration - ARCP service configuration metadata

SECURITY NOTE:
These endpoints are intentionally PUBLIC and do NOT require authentication.
Per RFC 8615 and RFC 7517, JWKS and discovery endpoints MUST be publicly
accessible to allow:
1. Clients to discover ARCP server capabilities before authentication
2. Token verification by any party using the public keys
3. Service interoperability with standard OAuth2/OIDC clients

These endpoints only expose PUBLIC keys and configuration metadata.
Private keys and sensitive data are NEVER exposed through these endpoints.
"""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, Response

from ..core.jwks import get_jwks_service
from ..utils.api_protection import RequirePublic
from ..utils.security_audit import SecurityEventType, log_security_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/.well-known", tags=["well-known"])


@router.get("/jwks.json", response_class=Response, dependencies=[RequirePublic])
async def get_jwks(request: Request) -> Response:
    """
    JSON Web Key Set endpoint.

    Returns public keys for JWT verification in JWKS format per RFC 7517.

    This endpoint is cached for 1 hour to reduce load while ensuring
    key rotations are visible within a reasonable time.

    Returns:
        JSON response with JWKS

    Headers:
        Cache-Control: public, max-age=3600
        X-Content-Type-Options: nosniff

    Example Response:
        {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": "base64url-encoded-key",
                    "kid": "arcp-20260130-a1b2c3d4",
                    "use": "sig",
                    "alg": "EdDSA"
                }
            ]
        }
    """
    service = get_jwks_service()

    try:
        jwks = await service.get_jwks()

        # Log JWKS access for security audit
        await log_security_event(
            event_type=SecurityEventType.JWKS_ACCESSED.value,
            message="JWKS endpoint accessed",
            severity="INFO",
            request=request,
            client_ip=request.client.host,
            keys_count=len(jwks.get("keys", [])),
            user_agent=request.headers.get("user-agent", "unknown"),
        )

        logger.debug(
            f"JWKS request from {request.client.host}, returning {len(jwks.get('keys', []))} keys"
        )

        return Response(
            content=json.dumps(jwks, indent=2),
            media_type="application/json",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        logger.error(f"Error generating JWKS: {e}")
        return Response(
            content=json.dumps({"keys": [], "error": "JWKS temporarily unavailable"}),
            media_type="application/json",
            status_code=503,
            headers={"Cache-Control": "no-cache", "Retry-After": "60"},
        )


@router.get("/arcp-configuration", dependencies=[RequirePublic])
async def get_arcp_configuration(request: Request) -> Dict[str, Any]:
    """
    ARCP server configuration discovery endpoint.

    Returns metadata about the ARCP server capabilities and endpoints,
    similar to OpenID Connect Discovery.

    Returns:
        JSON response with ARCP configuration

    Example Response:
        {
            "issuer": "https://arcp.example.com",
            "jwks_uri": "https://arcp.example.com/.well-known/jwks.json",
            "token_endpoint": "https://arcp.example.com/auth/agent/request_temp_token",
            "validation_endpoint": "https://arcp.example.com/auth/agent/validate_compliance",
            "registration_endpoint": "https://arcp.example.com/agents/register",
            "id_token_signing_alg_values_supported": ["EdDSA", "HS256"],
            "dpop_signing_alg_values_supported": ["EdDSA", "ES256"],
            "three_phase_registration_enabled": true,
            "service_version": "2.1.2"
        }
    """
    service = get_jwks_service()

    config_data = service.get_arcp_configuration()

    # Log configuration access for security audit
    await log_security_event(
        event_type=SecurityEventType.CONFIG_ACCESSED.value,
        message="ARCP configuration endpoint accessed",
        severity="INFO",
        request=request,
        client_ip=request.client.host,
        user_agent=request.headers.get("user-agent", "unknown"),
        tpr_enabled=config_data.get("three_phase_registration_enabled", False),
    )

    # Add request-specific information
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)

    # If issuer is default, try to use actual host
    if config_data.get("issuer") == "https://arcp.example.com" and host:
        actual_base = f"{scheme}://{host}"
        config_data["issuer"] = actual_base
        config_data["jwks_uri"] = f"{actual_base}/.well-known/jwks.json"
        config_data["token_endpoint"] = f"{actual_base}/auth/agent/request_temp_token"
        config_data["validation_endpoint"] = (
            f"{actual_base}/auth/agent/validate_compliance"
        )
        config_data["registration_endpoint"] = f"{actual_base}/agents/register"

    logger.debug(f"ARCP configuration request from {request.client.host}")

    return config_data


@router.options("/jwks.json")
async def jwks_options() -> Response:
    """Handle CORS preflight for JWKS endpoint."""
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        },
    )


@router.options("/arcp-configuration")
async def arcp_config_options() -> Response:
    """Handle CORS preflight for ARCP configuration endpoint."""
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        },
    )
