"""Authentication endpoints for ARCP"""

import asyncio
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

from fastapi import APIRouter, Depends, Header, Request

from ..core.config import config
from ..core.dependencies import get_registry
from ..core.exceptions import (
    ARCPProblemTypes,
    authentication_failed_problem,
    create_problem_response,
    handle_exception_with_problem_details,
    invalid_input_problem,
    pin_problem,
    required_header_missing_problem,
    session_expired_problem,
    session_validation_failed_problem,
)
from ..core.middleware import record_auth_attempt, require_rate_limit_check
from ..core.registry import AgentRegistry
from ..core.token_service import TokenService, get_token_service
from ..models.auth import (
    LoginRequest,
    LoginResponse,
    SetPinRequest,
    TempTokenResponse,
    VerifyPinRequest,
)
from ..models.token import TokenMintRequest
from ..utils.api_protection import RequireAdmin
from ..utils.auth_logging import (
    log_login_attempt,
    log_security_event,
    log_session_event,
)
from ..utils.logging import log_performance
from ..utils.rate_limiter import get_client_identifier
from ..utils.sessions import (
    clear_session_data,
    get_session_info,
    get_token_ref_from_request,
    has_session_pin,
    session_info,
    session_pins,
    set_session_pin,
    store_session_info,
    verify_session_pin,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Rate limit dependencies for sensitive endpoints
async def _rate_limit_login(request: Request):
    await require_rate_limit_check(request, "login")


async def _rate_limit_pin(request: Request):
    await require_rate_limit_check(request, "pin")


async def _rate_limit_general(request: Request):
    await require_rate_limit_check(request, "general")


def constant_time_auth(target_duration: float = 1.5):
    """
    Decorator to ensure authentication endpoints take constant time as observed by the client.
    This version postpones returning or raising until after the delay to avoid responses being
    sent before the sleep occurs.

    Args:
        target_duration: Target duration in seconds for all requests
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            outcome_kind = None
            outcome_value = None
            try:
                # Execute the wrapped function
                result = await func(*args, **kwargs)
                outcome_kind = "result"
                outcome_value = result
            except Exception as e:
                # Capture exception so we can delay before raising
                outcome_kind = "exception"
                outcome_value = e
            finally:
                # Compute remaining time and sleep BEFORE returning/raising
                elapsed = time.perf_counter() - start_time
                if elapsed < target_duration:
                    remaining = target_duration - elapsed
                    # Small deterministic jitter based on start_time to mask micro variations
                    jitter = (hash(str(start_time)) % 100) / 10000  # 0-0.01s
                    await asyncio.sleep(remaining + jitter)
            # Now deliver the outcome
            if outcome_kind == "exception":
                raise outcome_value
            return outcome_value

        return wrapper

    return decorator


@router.post("/agent/request_temp_token", response_model=TempTokenResponse)
@constant_time_auth(target_duration=1.5)  # Same duration as login for consistency
@log_performance("auth_agent_temp_token")
async def request_temp_token(
    request: LoginRequest,
    http_request: Request,
    _: None = Depends(_rate_limit_login),
    registry: AgentRegistry = Depends(get_registry),
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
):
    """Request temporary token for agent registration using agent key"""

    client_id = get_client_identifier(http_request)
    success = False

    try:
        # Validation with constant-time processing
        # Normalize and validate inputs to prevent timing-based enumeration
        agent_id = (request.agent_id or "").strip()
        agent_type = (request.agent_type or "").strip()
        agent_key = (request.agent_key or "").strip()

        # Check for missing or invalid fields but continue processing for constant timing
        has_valid_inputs = bool(
            agent_id and agent_type and agent_key and len(agent_key) >= 10
        )

        if not has_valid_inputs:
            await record_auth_attempt(http_request, False, "login")

            # Determine specific error but with consistent timing
            if not agent_id or not agent_type or not agent_key:
                return invalid_input_problem(
                    "agent credentials",
                    "agent_id, agent_type, and agent_key are required for temporary token request",
                    http_request,
                )
            elif len(agent_key) < 10:
                return invalid_input_problem(
                    "agent_key",
                    "agent_key too short (minimum 10 characters required)",
                    http_request,
                )

        logger.info(
            f"Temporary token request from agent: {agent_id} ({agent_type}) | client={client_id[:16]}"
        )

        # Validate agent key against configured keys using constant-time comparison

        # ENHANCED CONSTANT-TIME AGENT KEY VALIDATION
        # This prevents timing-based enumeration of valid keys by ensuring
        # ALL code paths take exactly the same amount of time

        key_valid = False

        # Step 1: Normalize the input key to prevent length-based attacks
        input_key = agent_key if has_valid_inputs else "dummy_key_for_constant_timing"

        # Step 2: Pad to a fixed length (64 chars) to eliminate length-based timing
        normalized_input = input_key.ljust(64)[:64]
        input_key_bytes = normalized_input.encode("utf-8")

        # Step 3: Always compare against ALL configured keys + dummy keys for constant timing
        keys_to_check = list(config.AGENT_REGISTRATION_KEYS)

        # Ensure we always check exactly 8 keys (pad with dummies if needed)
        target_key_count = 8
        while len(keys_to_check) < target_key_count:
            keys_to_check.append(
                f"dummy_padding_key_{len(keys_to_check)}_for_timing_consistency"
            )

        # Truncate if we have too many (keep timing constant)
        keys_to_check = keys_to_check[:target_key_count]

        # Step 4: Perform exactly the same number of operations for all keys
        comparison_results = []
        for valid_key in keys_to_check:
            # Normalize each valid key to the same length
            normalized_valid = valid_key.ljust(64)[:64]
            valid_key_bytes = normalized_valid.encode("utf-8")

            # Perform constant-time comparison
            result = secrets.compare_digest(input_key_bytes, valid_key_bytes)
            comparison_results.append(result)

            # Update key_valid using OR operation (doesn't short-circuit)
            key_valid = key_valid or result

        # Step 5: Add deterministic delay based on input to mask timing differences
        # This provides additional protection beyond the constant-time decorator
        input_hash = hash(input_key_bytes) % 1000
        base_delay = 0.002 + (input_hash / 50000)  # 0.002-0.022s delay
        await asyncio.sleep(base_delay)

        if not key_valid:
            logger.warning(
                f"Invalid agent key attempt: {agent_id} with key: {agent_key[:8] if len(agent_key) >= 8 else 'short'}..."
            )

            # Log failed agent key attempt
            await log_login_attempt(
                success=False,
                agent_id=agent_id,
                agent_type=agent_type,
                request=http_request,
                error_message="Invalid agent registration key",
            )

            await record_auth_attempt(http_request, False, "login")

            return authentication_failed_problem(
                "Invalid agent registration key", http_request
            )

        # Generate temporary token (short-lived for registration process)
        temp_token_data = {
            "sub": f"temp_{request.agent_id}",
            "agent_id": request.agent_id,
            "agent_type": request.agent_type,
            "role": "agent",  # Give temporary tokens agent role
            "temp_registration": True,
            "used_key": request.agent_key[:8] + "...",  # Store partial key for tracking
            "agent_key_hash": hashlib.sha256(
                request.agent_key.encode()
            ).hexdigest(),  # Store full key hash for validation
        }

        # Create temporary token with shorter expiration (15 minutes)
        temp_token = registry.create_access_token(
            data=temp_token_data, expires_delta=timedelta(minutes=15)
        )

        logger.info(
            f"Temporary token issued for agent: {request.agent_id} ({request.agent_type})"
        )

        # Log successful temp token issuance
        await log_login_attempt(
            success=True,
            agent_id=request.agent_id,
            agent_type=request.agent_type,
            request=http_request,
        )

        success = True

        resp = TempTokenResponse(
            temp_token=temp_token,
            token_type="bearer",
            expires_in=900,  # 15 minutes
            message="Temporary token issued. Use this token to complete agent registration.",
        )
        # Light visibility into in-memory stores for debugging purposes
        logger.debug(
            f"Session stores after temp token: pins={len(session_pins)}, info={len(session_info)}"
        )
        return resp

    except Exception as e:
        return handle_exception_with_problem_details(
            logger, "Agent temp token request", e, user_id=request.agent_id
        )
    finally:
        await record_auth_attempt(http_request, success, "login")


@router.post("/login", response_model=LoginResponse)
@constant_time_auth(target_duration=1.5)
@log_performance("auth_login")
async def login(
    request: LoginRequest,
    http_request: Request,
    _: None = Depends(_rate_limit_login),
    # registry: AgentRegistry = Depends(get_registry),
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
):
    """Agent login endpoint for authentication"""

    client_id = get_client_identifier(http_request)

    try:
        logger.info(f"Authentication request received | client={client_id[:16]}")

        # Handle both username/password login and agent login
        if request.agent_id and request.agent_type:
            # NOTE: Agent direct login is DISABLED
            # Agents MUST use the temp token registration flow
            logger.warning(
                f"Attempted direct agent login (BLOCKED): {request.agent_id} ({request.agent_type})"
            )

            # Log failed agent authentication attempt
            await log_login_attempt(
                success=False,
                agent_id=request.agent_id,
                agent_type=request.agent_type,
                request=http_request,
                error_message="Direct agent login not allowed - use registration flow",
            )

            return authentication_failed_problem(
                "Direct agent login not allowed. Use agent registration flow with valid agent key",
                http_request,
            )
        elif request.username and request.password:
            # Admin login - validate credentials from configuration using constant-time comparison

            if not config.ADMIN_PASSWORD:
                logger.error("Admin password not configured")
                return create_problem_response(
                    problem_type=ARCPProblemTypes.CONFIGURATION_ERROR,
                    detail="Admin authentication not properly configured",
                    request=http_request,
                )

            # Require a fingerprint for session binding
            if not x_client_fingerprint:
                return required_header_missing_problem(
                    "X-Client-Fingerprint", http_request
                )

            # ENHANCED CONSTANT-TIME PROTECTION: Ensure absolutely constant time
            # Phase 1: Input normalization (always same operations)
            username_input = (request.username or "").strip()
            password_input = request.password or ""

            # Pad inputs to fixed lengths to ensure constant encoding time
            username_padded = username_input.ljust(255)[:255]  # Always 255 chars
            password_padded = password_input.ljust(1024)[:1024]  # Always 1024 chars

            # Phase 2: Always encode the same length strings
            username_bytes = username_padded.encode("utf-8")
            password_bytes = password_padded.encode("utf-8")
            admin_username_padded = config.ADMIN_USERNAME.ljust(255)[:255]
            admin_password_padded = config.ADMIN_PASSWORD.ljust(1024)[:1024]
            admin_username_bytes = admin_username_padded.encode("utf-8")
            admin_password_bytes = admin_password_padded.encode("utf-8")

            # Phase 3: Always perform both comparisons (constant time)
            username_valid = secrets.compare_digest(
                username_bytes, admin_username_bytes
            )
            password_valid = secrets.compare_digest(
                password_bytes, admin_password_bytes
            )

            # Phase 4: Validate input lengths (but continue processing for timing)
            input_valid = (
                len(username_input) > 0
                and len(username_input) <= 255
                and len(password_input) > 0
                and len(password_input) <= 1024
            )

            # Phase 5: Add deterministic delay based on input to mask timing variations
            input_hash = hash(username_bytes + password_bytes) % 1000
            timing_delay = 0.005 + (input_hash / 50000)  # 0.005-0.025s delay
            await asyncio.sleep(timing_delay)

            credentials_valid = username_valid and password_valid and input_valid

            # Phase 6: ALWAYS prepare both success AND failure responses (constant time)
            # This ensures the same amount of work is done regardless of authentication result

            # Always prepare success path data (even if not used)
            client_ip = http_request.client.host if http_request.client else "unknown"
            user_agent = http_request.headers.get("user-agent", "unknown")

            dummy_token_request = TokenMintRequest(
                user_id="dummy_user",
                agent_id="dummy_agent",
                scopes=["dummy"],
                # Use a valid role to avoid validation errors during constant-time dummy processing
                role="user",
            )

            # Always prepare failure response data (timing attack mitigation)
            {
                "detail": "Invalid credentials",
                "error_code": "AUTH_FAILED",
                "timestamp": datetime.utcnow().isoformat(),
            }

            # CONSTANT-TIME PROCESSING: Process both success and failure paths
            if credentials_valid:
                # Successful authentication - prepare response
                try:
                    client_ip = (
                        http_request.client.host if http_request.client else "unknown"
                    )
                    user_agent = http_request.headers.get("user-agent", "unknown")

                    token_request = TokenMintRequest(
                        user_id=username_input,
                        agent_id=f"user_{username_input}",  # Admin tokens get special agent_id
                        scopes=["admin", "agent_management"],
                        role="admin",  # Explicit admin role claim
                    )

                    # Create admin authentication token with SESSION_TIMEOUT (minutes)
                    try:
                        timeout_minutes = int(
                            getattr(config, "SESSION_TIMEOUT", 60) or 60
                        )
                    except Exception:
                        timeout_minutes = 60
                    if timeout_minutes <= 0:
                        timeout_minutes = 1
                    token_service = TokenService(expire_minutes=timeout_minutes)

                    # Add explicit admin role to token payload with session info
                    token_response = token_service.mint_token(token_request)

                    # Store session info for admin users with client fingerprint
                    store_session_info(
                        username_input,
                        client_ip,
                        user_agent,
                        x_client_fingerprint,
                        token_response.access_token[
                            -10:
                        ],  # Last 10 chars for reference
                    )

                    logger.info(
                        f"Admin login successful for user: {request.username} from {client_ip} with fingerprint: {x_client_fingerprint[:8] if x_client_fingerprint else 'none'}"
                    )

                    # Log successful admin login to dashboard
                    await log_login_attempt(
                        success=True,
                        username=request.username,
                        request=http_request,
                    )

                    resp = LoginResponse(
                        access_token=token_response.access_token,
                        token_type="bearer",
                        expires_in=token_response.expires_in,
                        agent_id=f"user_{request.username}",
                    )
                    logger.debug(
                        f"Session stores after login: pins={len(session_pins)}, info={len(session_info)}"
                    )
                    return resp
                except Exception as e:
                    return handle_exception_with_problem_details(
                        logger,
                        "Admin authentication",
                        e,
                        user_id=request.username,
                    )
            else:
                # Failed authentication - process with consistent timing
                # Do equivalent work to success path to maintain constant timing

                # Simulate token service work (same as success path)
                token_service = get_token_service()

                # Perform dummy token generation (but don't use it)
                try:
                    token_service.mint_token(dummy_token_request)
                except Exception:
                    pass  # Ignore errors in dummy operation

                # Simulate session storage work
                store_session_info(
                    "dummy_user",
                    client_ip,
                    user_agent,
                    x_client_fingerprint or "dummy_fingerprint",
                    "dummy_token",
                )

                logger.warning(f"Failed admin login attempt: {username_input}")

                # Log failed admin login attempt to dashboard (same as success path)
                await log_login_attempt(
                    success=False,
                    username=username_input,
                    request=http_request,
                    error_message="Invalid credentials",
                )

                return authentication_failed_problem(
                    "Invalid admin credentials", http_request
                )
        else:
            return authentication_failed_problem(
                "Invalid credentials - provide either agent_id/agent_type or username/password",
                http_request,
            )

    except Exception as e:
        return handle_exception_with_problem_details(
            logger, "Authentication", e, user_id=request.username
        )
    finally:
        # Attempt counts are recorded by middleware to avoid duplication
        pass


# Endpoint: Logout and clear session PIN
@router.post("/logout")
async def logout(
    request: Request,
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
    user_data: dict = RequireAdmin,
):
    """Logout and clear session PIN for admin with session isolation."""
    user_id = user_data.get("sub")
    if not user_id:
        return invalid_input_problem("user data", "Invalid user ID", request)

    # Clear session PIN and session info for this specific session
    token_ref = get_token_ref_from_request(request)
    clear_session_data(user_id, x_client_fingerprint, token_ref)

    # Log logout event to dashboard
    await log_session_event("logout", user_id, request=request)

    return {
        "status": "success",
        "message": "Logged out and session PIN cleared",
    }


@router.post("/set_pin")
@constant_time_auth(target_duration=1.0)  # Shorter duration for PIN operations
async def set_pin(
    request: Request,
    body: SetPinRequest,
    _: None = Depends(_rate_limit_pin),
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
    user_data: dict = RequireAdmin,
):
    """Set session PIN for admin. PIN can only be set if not already set for this session."""

    client_id = get_client_identifier(request)

    try:
        user_id = user_data.get("sub")  # JWT subject claim contains the user ID
        if not user_id:
            return invalid_input_problem("user data", "Invalid user ID", request)

        logger.info(
            f"[{datetime.now()}] PIN set attempt by user: {user_id} with fingerprint: {x_client_fingerprint[:8] if x_client_fingerprint else 'None'}"
        )

        # Verify client fingerprint matches session
        token_ref = get_token_ref_from_request(request)
        session = get_session_info(user_id, x_client_fingerprint, token_ref)
        logger.info(
            f"[{datetime.now()}] Session lookup result for {user_id}: {'Found' if session else 'Not found'} (token_ref={token_ref})"
        )

        if session and session.get("client_fingerprint") and x_client_fingerprint:
            if session["client_fingerprint"] != x_client_fingerprint:
                logger.warning(
                    f"[{datetime.now()}] Client fingerprint mismatch during PIN set for user {user_id}"
                )

                # Log security event for fingerprint mismatch
                await log_security_event(
                    "fingerprint_mismatch",
                    f"Client fingerprint mismatch during PIN set for user {user_id}",
                    severity="WARN",
                    request=request,
                    user_id=user_id,
                    expected_fingerprint=session["client_fingerprint"][:8],
                    received_fingerprint=x_client_fingerprint[:8],
                )

                # Session validation failed
                return session_validation_failed_problem(
                    "Session fingerprint mismatch", request
                )

        # Only allow setting PIN if not already set for this specific session
        if has_session_pin(user_id, x_client_fingerprint, token_ref):
            # Record failed attempt for rate limiting
            return pin_problem(
                ARCPProblemTypes.PIN_ALREADY_SET,
                "PIN already set for this session",
                request,
            )

        # Validate PIN strength (basic validation)
        if len(body.pin) < 4:
            return pin_problem(
                ARCPProblemTypes.PIN_INVALID_LENGTH,
                "PIN must be at least 4 characters",
                request,
            )

        if len(body.pin) > 32:
            return pin_problem(
                ARCPProblemTypes.PIN_INVALID_LENGTH,
                "PIN must be no more than 32 characters",
                request,
            )

        # Set new PIN for this specific session
        set_session_pin(user_id, body.pin, x_client_fingerprint, token_ref)
        logger.info(
            f"[{datetime.now()}] PIN set for user: {user_id} from {request.client.host if request.client else 'unknown'} | client={client_id[:16]}"
        )

        # Log PIN set event to dashboard
        await log_session_event("pin_set", user_id, request=request)

        return {"status": "success", "message": "PIN set for session"}

    finally:
        # Attempt counts are recorded by middleware to avoid duplication
        pass


@router.post("/verify_pin")
@constant_time_auth(target_duration=1.0)  # Shorter duration for PIN operations
async def verify_pin(
    request: Request,
    body: VerifyPinRequest,
    _: None = Depends(_rate_limit_pin),
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
    user_data: dict = RequireAdmin,
):
    """Verify session PIN for admin critical actions."""

    client_id = get_client_identifier(request)

    try:
        user_id = user_data.get("sub")
        if not user_id:
            return invalid_input_problem("user data", "Invalid user ID", request)

        # Additional security: verify session info and client fingerprint using session isolation
        token_ref = get_token_ref_from_request(request)
        session = get_session_info(user_id, x_client_fingerprint, token_ref)
        if session:
            current_ip = request.client.host if request.client else "unknown"
            current_user_agent = request.headers.get("user-agent", "unknown")

            # Check if IP or user agent changed significantly
            if session["ip"] != current_ip:
                logger.warning(
                    f"IP change detected for user {user_id}: {session['ip']} -> {current_ip} | client={client_id[:16]}"
                )

                # Log IP change event
                await log_security_event(
                    "ip_change",
                    f"IP address change detected for user {user_id}: {session['ip']} -> {current_ip} | client={client_id[:16]}",
                    severity="INFO",
                    request=request,
                    user_id=user_id,
                    previous_ip=session["ip"],
                    current_ip=current_ip,
                )

            if session["user_agent"] != current_user_agent:
                logger.warning(
                    f"User agent change detected for user {user_id} | client={client_id[:16]}"
                )

                # Log user agent change event
                await log_security_event(
                    "user_agent_change",
                    f"User agent change detected for user {user_id}",
                    severity="INFO",
                    request=request,
                    user_id=user_id,
                    previous_user_agent=session["user_agent"][:50],
                    current_user_agent=current_user_agent[:50],
                )

            # Check client fingerprint
            if session.get("client_fingerprint") and x_client_fingerprint:
                if session["client_fingerprint"] != x_client_fingerprint:
                    logger.warning(
                        f"[{datetime.now()}] Client fingerprint mismatch for user {user_id}: expected {session['client_fingerprint'][:8]}, got {x_client_fingerprint[:8]}"
                    )

                    # Log security event for fingerprint mismatch
                    await log_security_event(
                        "fingerprint_mismatch",
                        f"Client fingerprint mismatch during PIN verification for user {user_id}",
                        severity="WARN",
                        request=request,
                        user_id=user_id,
                        expected_fingerprint=session["client_fingerprint"][:8],
                        received_fingerprint=x_client_fingerprint[:8],
                    )

                    return session_validation_failed_problem(
                        "Session validation failed", request
                    )
            elif session.get("client_fingerprint") and not x_client_fingerprint:
                logger.warning(
                    f"[{datetime.now()}] Missing client fingerprint for user {user_id}"
                )

                # Log security event for missing fingerprint
                await log_security_event(
                    "missing_fingerprint",
                    f"Missing client fingerprint for user {user_id}",
                    severity="WARN",
                    request=request,
                    user_id=user_id,
                )

                return session_validation_failed_problem(
                    "Session validation failed", request
                )

        # Verify PIN using session isolation
        if not verify_session_pin(user_id, body.pin, x_client_fingerprint, token_ref):
            if not has_session_pin(user_id, x_client_fingerprint, token_ref):
                logger.warning(
                    f"[{datetime.now()}] PIN verify attempt with no PIN set. User: {user_id}"
                )
                # Log PIN verification attempt with no PIN set
                await log_session_event("pin_verify_no_pin", user_id, request=request)

                return pin_problem(
                    ARCPProblemTypes.PIN_NOT_SET,
                    "PIN not set for session",
                    request,
                )
            else:
                logger.warning(
                    f"[{datetime.now()}] Incorrect PIN attempt by user: {user_id} from {request.client.host if request.client else 'unknown'}"
                )
                # Log failed PIN verification
                await log_session_event("pin_verify_failed", user_id, request=request)

                return pin_problem(
                    ARCPProblemTypes.PIN_INCORRECT, "Incorrect PIN", request
                )

        logger.info(
            f"[{datetime.now()}] Successful PIN verification by user: {user_id} from {request.client.host if request.client else 'unknown'}"
        )

        # Log successful PIN verification to dashboard
        await log_session_event("pin_verify_success", user_id, request=request)

        return {"status": "success", "message": "PIN verified"}

    finally:
        # Attempt counts are recorded by middleware to avoid duplication
        pass


# Endpoint: Check if PIN is set for session
@router.get("/pin_status")
async def pin_status(
    request: Request,
    x_client_fingerprint: str = Header(None, alias="X-Client-Fingerprint"),
    user_data: dict = RequireAdmin,
):
    """Check if session PIN is set for admin with session isolation."""
    user_id = user_data.get("sub")
    if not user_id:
        return invalid_input_problem("user data", "Invalid user ID", request)

    token_ref = get_token_ref_from_request(request)
    return {"pin_set": has_session_pin(user_id, x_client_fingerprint, token_ref)}


# Endpoint: Check token validity and session status
@router.get("/session_status")
async def session_status(request: Request, token_data: dict = RequireAdmin):
    """Check if token is valid and session is active."""
    user_id = token_data.get("sub")  # JWT subject claim contains the user ID
    if not user_id:
        return invalid_input_problem("token data", "Invalid token data", request)

    # Check if this is an admin user and if session info exists
    is_admin = token_data.get("role") == "admin"
    session_valid = True
    pin_set = False
    if is_admin:
        # Validate admin session TTL and fingerprint-bound info
        token_ref = get_token_ref_from_request(request)
        fingerprint = request.headers.get("X-Client-Fingerprint")
        sess = get_session_info(user_id, fingerprint, token_ref)
        session_valid = sess is not None
        pin_set = (
            has_session_pin(user_id, fingerprint, token_ref) if session_valid else False
        )
        if not session_valid:
            # Treat as unauthorized if server-side session has expired/invalidated
            return session_expired_problem(request)

    return {
        "valid": True,
        "user_id": user_id,
        "role": token_data.get("role"),
        "agent_id": token_data.get("agent_id"),
        "expires": token_data.get("exp"),
        "is_admin": is_admin,
        "session_exists": session_valid,
        "pin_set": pin_set,
    }
