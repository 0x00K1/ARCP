"""Token minting endpoints"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response

from ..core.exceptions import (
    ARCPProblemTypes,
    TokenValidationError,
    create_problem_response,
    handle_exception_with_problem_details,
    invalid_input_problem,
)
from ..core.token_service import TokenService, get_token_service
from ..models.token import TokenMintRequest, TokenResponse
from ..utils.api_protection import RequireAdmin, RequirePublic
from ..utils.logging import log_performance

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/mint", response_model=TokenResponse, dependencies=[RequireAdmin])
@log_performance("token_mint")
async def mint_token(
    request: TokenMintRequest,
    http_request: Request,
    service: TokenService = Depends(get_token_service),
    _: Dict[str, Any] = RequireAdmin,
):
    """Mint a JWT token for user-agent communication"""
    try:
        return service.mint_token(request)
    except ValueError as e:
        # Use Problem Details for validation errors
        return invalid_input_problem("token request", str(e), http_request)
    except Exception as e:
        return handle_exception_with_problem_details(
            logger, "Token minting", e, http_request
        )


@router.post("/validate", dependencies=[RequirePublic])
@log_performance("token_validate")
async def validate_token(
    token: str, service: TokenService = Depends(get_token_service)
):
    """Validate a JWT token"""
    try:
        payload = service.validate_token(token)
        return {"valid": True, "payload": payload}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.get("/validate", dependencies=[RequirePublic])
@log_performance("token_validate_get")
async def validate_token_get(
    request: Request,
    response: Response,
    service: TokenService = Depends(get_token_service),
):
    """Validate a JWT token via GET request with Authorization header"""
    try:
        # Extract token from Authorization header
        authorization = request.headers.get("authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]  # Remove "Bearer " prefix
        else:
            response.status_code = 401
            return {"valid": False, "error": "No token provided"}

        payload = service.validate_token(token)
        return {
            "valid": True,
            "agent_id": payload.get("sub"),
            "payload": payload,
        }
    except Exception as e:
        response.status_code = 401
        return {"valid": False, "error": f"Invalid token: {str(e)}"}


@router.post("/refresh", dependencies=[RequirePublic])
@log_performance("token_refresh")
async def refresh_token(
    request: Request, service: TokenService = Depends(get_token_service)
):
    """Refresh a JWT token"""
    try:
        authorization = request.headers.get("authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return create_problem_response(
                problem_type=ARCPProblemTypes.AUTHENTICATION_FAILED,
                detail="No token provided in Authorization header",
                request=request,
            )

        token = authorization[7:]  # Remove "Bearer " prefix
        payload = service.validate_token(token)

        # Create new token with same payload
        token_request = TokenMintRequest(
            user_id=payload.get("sub"),
            agent_id=payload.get("agent_id", payload.get("sub")),
            scopes=payload.get("scopes", []),
            role=payload.get("role", "user"),
        )

        token_response = service.mint_token(token_request)
        return {
            "access_token": token_response.access_token,
            "token_type": "bearer",
        }
    except Exception as e:
        return handle_exception_with_problem_details(
            logger,
            "Token refresh",
            TokenValidationError(f"Token refresh failed: {e}"),
            request,
        )
