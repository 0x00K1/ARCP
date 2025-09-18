"""
Middleware components for ARCP application.

This module contains all FastAPI middleware including request logging,
security headers, CORS configuration, rate limiting, and other cross-cutting concerns.
"""

import asyncio
import asyncio as _asyncio
import ipaddress
import json as _json
import logging
import time
import uuid
from typing import List

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from ..core.config import config
from ..services.metrics import get_metrics_service
from ..utils.auth_logging import log_security_event
from ..utils.logging import create_request_logger, log_with_context, mask_sensitive_data
from ..utils.rate_limiter import (
    general_rate_limiter,
    get_client_identifier,
    login_rate_limiter,
    pin_rate_limiter,
)
from ..utils.security_sanitizer import ContentRiskDetector
from .exceptions import ARCPProblemTypes, create_problem_response

logger = logging.getLogger(__name__)


class _SuppressUpgradeWarnings(logging.Filter):
    """Filter to suppress misleading upgrade warnings from Uvicorn.
    These warnings are triggered by the browser's 'Upgrade-Insecure-Requests' header and
    are not indicative of real WebSocket issues. They clutter logs and confuse users.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return (
            "Unsupported upgrade request" not in msg
            and "No supported WebSocket library detected" not in msg
        )


def configure_logging_filters():
    """Configure logging filters to suppress unwanted warnings."""
    # Register the filter for both error & access loggers used by Uvicorn
    logging.getLogger("uvicorn.error").addFilter(_SuppressUpgradeWarnings())
    logging.getLogger("uvicorn.access").addFilter(_SuppressUpgradeWarnings())


async def metrics_middleware(request: Request, call_next):
    """
    Metrics collection middleware for HTTP requests.

    Records request count, duration, and status codes for all HTTP requests.
    """
    start_time = time.time()
    metrics_service = get_metrics_service()

    # Get basic request information
    method = request.method
    path = str(request.url.path)

    # Simplify path for common patterns (remove IDs, etc.)
    simplified_path = path
    if "/agents/" in path and path != "/agents/register" and path != "/agents/search":
        # Replace agent IDs with placeholder
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == "agents":
            # Pattern like /agents/{agent_id} or /agents/{agent_id}/heartbeat
            simplified_path = "/agents/{agent_id}" + (
                "/" + "/".join(parts[3:]) if len(parts) > 3 else ""
            )
    elif "/auth/tokens/" in path:
        # Pattern like /auth/tokens/{token_id}
        simplified_path = "/auth/tokens/{token_id}"

    response = None
    status_code = 500  # Default to error if something goes wrong

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    except Exception:
        status_code = 500
        raise

    finally:
        # Record metrics regardless of success or failure
        duration = time.time() - start_time
        try:
            metrics_service.record_http_request(
                method=method,
                endpoint=simplified_path,
                status_code=status_code,
                duration=duration,
            )
        except Exception as e:
            # Don't let metrics collection break the request
            logger.debug(f"Failed to record request metrics: {e}")


async def rate_limiting_middleware(request: Request, call_next):
    """
    Rate limiting middleware for authentication endpoints.

    Provides comprehensive rate limiting and brute force protection
    for sensitive authentication endpoints.
    """
    # Define protected endpoints
    protected_endpoints = {
        "/auth/login": ("login", login_rate_limiter),
        "/auth/agent/request_temp_token": ("login", login_rate_limiter),
        "/auth/verify_pin": ("pin", pin_rate_limiter),
        "/auth/set_pin": ("pin", pin_rate_limiter),
    }

    # Re-enable another endpoint rate limiting only in production environments
    try:
        env_name = str(getattr(config, "ENVIRONMENT", "")).lower()
    except Exception:
        env_name = ""
    if env_name == "production":
        protected_endpoints.update(
            {
                "/tokens/validate": ("general", general_rate_limiter),
                "/tokens/refresh": ("general", general_rate_limiter),
                "/tokens/mint": ("general", general_rate_limiter),
                "/agents/register": ("general", general_rate_limiter),
            }
        )

    # Check if this is a protected endpoint
    endpoint_info = None
    request_path = request.url.path

    # Exact match first
    if request_path in protected_endpoints:
        endpoint_info = protected_endpoints[request_path]
    else:
        # Check for partial matches (useful for parameterized endpoints)
        for protected_path, info in protected_endpoints.items():
            if request_path.startswith(protected_path.rstrip("/")):
                endpoint_info = info
                break

    if endpoint_info:
        protected_start = time.perf_counter()
        # Target minimum response time for protected endpoints (seconds)
        # Slightly higher floor for login-like endpoints to further reduce timing variance
        protected_min_duration = 1.5
        attempt_type, rate_limiter = endpoint_info
        client_id = get_client_identifier(request)
        if attempt_type == "login":
            protected_min_duration = 1.8

        # Check rate limit before processing request
        allowed, delay, reason = await rate_limiter.check_rate_limit(
            client_id, attempt_type
        )

        if not allowed:
            # Log security event for rate limit hit
            await log_security_event(
                "rate_limit_exceeded",
                f"Rate limit exceeded for {attempt_type} endpoint: {reason}",
                severity="WARNING",
                request=request,
                endpoint=request_path,
                attempt_type=attempt_type,
                delay_seconds=delay,
                client_id=client_id[:16],  # Truncate for privacy
            )

            # Return rate limit error using RFC 9457 Problem Details
            problem_response = create_problem_response(
                problem_type=ARCPProblemTypes.RATE_LIMIT_EXCEEDED,
                detail=reason,
                request=request,
                attempt_type=attempt_type,
                retry_after=int(delay) if delay else 60,
                client_id=client_id[:16],  # Truncate for privacy
            )

            # Add rate limiting headers
            problem_response.headers.update(
                {
                    "Retry-After": str(int(delay) if delay else 60),
                    "X-RateLimit-Limit": str(rate_limiter.max_attempts),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + (delay or 60))),
                }
            )
            # Ensure constant-time behavior for protected endpoints even on rate-limit
            elapsed = time.perf_counter() - protected_start
            if elapsed < protected_min_duration:
                await asyncio.sleep(protected_min_duration - elapsed)
            return problem_response

    # Enforce basic request constraints from config before processing
    # 1) Reject if too many query params
    try:
        max_query_params = int(getattr(config, "MAX_QUERY_PARAMS", 50))
        if len(request.query_params) > max_query_params:
            return create_problem_response(
                problem_type=ARCPProblemTypes.REQUEST_ERROR,
                detail=f"Too many query parameters: {len(request.query_params)} exceeds limit of {max_query_params}",
                request=request,
                query_param_count=len(request.query_params),
                max_query_params=max_query_params,
            )
    except Exception:
        pass

    # 2) IP filtering: supports Forward (default-allow) and Discard (default-deny)
    # Forward: permit unless expressly prohibited
    # Discard: prohibit unless expressly permitted
    try:
        client_ip = request.client.host if request.client else None
        if client_ip:
            if getattr(config, "IP_DEFAULT_DENY", False):
                allow_list = getattr(config, "ALLOWED_IP_RANGES_LIST", []) or []
                is_allowed = False
                if allow_list:
                    is_allowed = _is_ip_allowed(client_ip)
                # In default-deny, empty allow list means deny all
                if (not is_allowed) or _is_ip_blocked(client_ip):
                    return create_problem_response(
                        problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                        detail="Access from this IP address is not allowed",
                        request=request,
                        client_ip=(
                            client_ip[:8] + "..." if len(client_ip) > 8 else client_ip
                        ),  # Partial IP for security
                    )
            else:
                if _is_ip_blocked(client_ip):
                    return create_problem_response(
                        problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                        detail="Access from this IP address is blocked",
                        request=request,
                        client_ip=(
                            client_ip[:8] + "..." if len(client_ip) > 8 else client_ip
                        ),  # Partial IP for security
                    )
    except Exception:
        pass

    # Process the request
    response = await call_next(request)

    # Record attempt result if this was a protected endpoint
    if endpoint_info:
        attempt_type, rate_limiter = endpoint_info
        client_id = get_client_identifier(request)

        # Determine if attempt was successful based on response status
        success = _is_successful_response(response.status_code, request_path)

        # Record the attempt
        lockout_duration = await rate_limiter.record_attempt(
            client_id, success, attempt_type
        )

        if lockout_duration:
            # Log lockout event
            await log_security_event(
                "client_locked_out",
                f"Client locked out for {lockout_duration}s due to repeated {attempt_type} failures",
                severity="ERROR",
                request=request,
                endpoint=request_path,
                attempt_type=attempt_type,
                lockout_duration=lockout_duration,
                client_id=client_id[:16],
            )
        elif not success:
            # Log failed attempt
            attempt_info = rate_limiter.get_attempt_info(client_id, attempt_type)
            if attempt_info:
                await log_security_event(
                    f"{attempt_type}_attempt_failed",
                    f"Failed {attempt_type} attempt ({attempt_info.count}/{rate_limiter.max_attempts})",
                    severity="WARNING",
                    request=request,
                    endpoint=request_path,
                    attempt_type=attempt_type,
                    attempt_count=attempt_info.count,
                    max_attempts=rate_limiter.max_attempts,
                    client_id=client_id[:16],
                )

    # Equalize timing for protected endpoints (allowed path)
    if endpoint_info:
        elapsed = time.perf_counter() - protected_start
        if elapsed < protected_min_duration:
            await asyncio.sleep(protected_min_duration - elapsed)
    return response


def _is_successful_response(status_code: int, path: str) -> bool:
    """
    Determine if response indicates successful authentication.

    Args:
        status_code: HTTP response status code
        path: Request path

    Returns:
        True if successful, False if failed attempt
    """
    # Success codes
    if status_code in [200, 201]:
        return True

    # Explicit failure codes for authentication
    if status_code in [401, 403]:
        return False

    # For other codes, consider context
    if path in ["/auth/login", "/auth/verify_pin"]:
        # Any non-200 response is a failure for these endpoints
        return status_code == 200

    # For other endpoints, only explicit auth failures count as attempts
    return status_code not in [401, 403]


async def security_headers_middleware(request: Request, call_next):
    """
    Security headers middleware following OWASP recommendations.

    Adds comprehensive security headers to protect against various attacks:
    - XSS, CSRF, clickjacking, MIME sniffing, etc.
    """
    response = await call_next(request)

    # Content Security Policy
    # Build connect-src from configuration
    connect_src_parts = ["'self'", "ws:", "wss:"]
    if config.CSP_ALLOW_CONNECT_HTTP:
        connect_src_parts.append("http:")
    if config.CSP_ALLOW_CONNECT_HTTPS:
        connect_src_parts.append("https:")
    connect_src = " ".join(connect_src_parts)

    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://speedcf.cloudflareaccess.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://speedcf.cloudflareaccess.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://speedcf.cloudflareaccess.com https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        f"connect-src {connect_src}; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # Security Headers
    security_headers = {
        # Prevent MIME type sniffing
        "X-Content-Type-Options": "nosniff",
        # Prevent clickjacking
        "X-Frame-Options": "DENY",
        # XSS Protection
        "X-XSS-Protection": "1; mode=block",
        # Content Security Policy
        "Content-Security-Policy": csp_policy,
        # Referrer Policy
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # Permissions Policy (formerly Feature Policy)
        "Permissions-Policy": (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        ),
        # Prevent caching of sensitive content
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        # Try to remove server information
        "Server": "ARCP/2.0.0",
    }

    # Add HSTS for HTTPS environments
    if (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    ):
        security_headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    # Apply headers
    for header, value in security_headers.items():
        response.headers[header] = value

    # Optional content filtering for JSON responses (very conservative)
    try:
        if getattr(config, "CONTENT_FILTERING", True):
            ctype = response.headers.get("content-type", "")
            if (
                "application/json" in ctype
                and hasattr(response, "body")
                and response.body
            ):
                try:
                    payload = None
                    try:
                        payload = _json.loads(response.body)
                    except Exception:
                        payload = None
                    if payload is not None:
                        scan = ContentRiskDetector.scan_json_for_risk(payload)
                        if scan.get("flagged"):
                            response.headers["X-Content-Filter"] = "flagged"
                            # Log a security event without mutating response
                            try:
                                _asyncio.create_task(
                                    log_security_event(
                                        "content_filter_flag",
                                        "Potentially unsafe content detected in JSON response",
                                        severity="WARNING",
                                        request=request,
                                        indicators=scan.get("indicators", [])[:10],
                                    )
                                )
                            except Exception:
                                pass
                except Exception:
                    # Fail-quietly
                    pass
    except Exception:
        pass

    return response


async def request_size_limit_middleware(request: Request, call_next):
    """
    Request size limiting middleware to prevent large payload attacks.

    Limits request body size to prevent memory exhaustion attacks.
    """
    # Use configured limit with sane default (bytes)
    MAX_REQUEST_SIZE = int(getattr(config, "MAX_JSON_SIZE", 10 * 1024 * 1024))

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_length = int(content_length)
            if content_length > MAX_REQUEST_SIZE:
                return create_problem_response(
                    problem_type=ARCPProblemTypes.REQUEST_TOO_LARGE,
                    detail=f"Request body size {content_length} bytes exceeds maximum limit of {MAX_REQUEST_SIZE} bytes",
                    request=request,
                    content_length=content_length,
                    max_size=MAX_REQUEST_SIZE,
                )
        except ValueError:
            pass

    # Enforce max header size BEFORE processing request (sum of header lengths)
    MAX_HEADER_SIZE = int(getattr(config, "MAX_HEADER_SIZE", 8192))
    try:
        total_header_bytes = sum(len(k) + len(v) for k, v in request.headers.items())
        if total_header_bytes > MAX_HEADER_SIZE:
            return create_problem_response(
                problem_type=ARCPProblemTypes.HEADERS_TOO_LARGE,
                detail=f"Request headers size {total_header_bytes} bytes exceeds maximum limit of {MAX_HEADER_SIZE} bytes",
                request=request,
                header_size=total_header_bytes,
                max_header_size=MAX_HEADER_SIZE,
            )
    except Exception:
        pass

    response = await call_next(request)

    # Enforce max header size AFTER processing response (sum of header lengths)
    try:
        total_response_header_bytes = sum(
            len(k) + len(v) for k, v in response.headers.items()
        )
        if total_response_header_bytes > MAX_HEADER_SIZE:
            return create_problem_response(
                problem_type=ARCPProblemTypes.INTERNAL_ERROR,
                detail=f"Response headers size {total_response_header_bytes} bytes exceeds maximum limit of {MAX_HEADER_SIZE} bytes",
                request=request,
                response_header_size=total_response_header_bytes,
                max_header_size=MAX_HEADER_SIZE,
            )
    except Exception:
        pass

    return response


async def request_logging_middleware(request: Request, call_next):
    """
    Request logging middleware for comprehensive request/response logging.

    Logs incoming requests and their responses with sanitized headers
    and performance metrics.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    logger = create_request_logger(request_id)

    # Sanitize headers for logging (remove sensitive data)
    sanitized_headers = mask_sensitive_data(dict(request.headers))

    log_with_context(
        logger,
        "info",
        "Incoming request",
        method=request.method,
        path=request.url.path,
        headers=sanitized_headers,
        client_ip=request.client.host if request.client else "unknown",
    )

    response = await call_next(request)

    # Calculate response time
    response_time = time.time() - start_time

    log_with_context(
        logger,
        "info",
        "Request completed",
        status_code=response.status_code,
        response_time_ms=round(response_time * 1000, 2),
    )

    # Add response time header for monitoring
    response.headers["X-Response-Time"] = f"{response_time:.3f}s"
    response.headers["X-Request-ID"] = request_id

    return response


def get_allowed_origins() -> List[str]:
    """
    Get allowed CORS origins based on environment.

    Returns:
        List of allowed origins for CORS configuration
    """
    # In development, allow localhost and config host with common ports
    if config.ENVIRONMENT.lower() == "development":
        origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://localhost:8080",
            f"http://localhost:{config.PORT}",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8080",
            f"http://127.0.0.1:{config.PORT}",
        ]

        # Add the actual configured host if it's not localhost/127.0.0.1
        if config.HOST not in ["localhost", "127.0.0.1", "0.0.0.0"]:
            origins.extend(
                [
                    f"http://{config.HOST}:3000",
                    f"http://{config.HOST}:8000",
                    f"http://{config.HOST}:{config.PORT}",
                ]
            )

        return origins

    # In production, use configured origins or default secure list
    allowed_origins = getattr(config, "ALLOWED_ORIGINS", None)
    if allowed_origins:
        return (
            allowed_origins.split(",")
            if isinstance(allowed_origins, str)
            else allowed_origins
        )

    # Fallback: very restrictive for security
    return ["https://yourdomain.com"]


def _is_ip_allowed(ip_address: str) -> bool:
    """Evaluate IP allow/deny based on config lists.

    Rules:
    - If `ALLOWED_IP_RANGES_LIST` is non-empty, the IP must match at least one entry
      (CIDR or exact IP) to be allowed
    - If `BLOCKED_IPS_LIST` contains the IP, it is denied
    - If no allow list configured, allow by default unless explicitly blocked
    Fail-open on evaluation error.
    """
    try:
        # Explicit block (exact IPs)
        for blocked in getattr(config, "BLOCKED_IPS_LIST", []) or []:
            if ip_address == blocked:
                return False

        allow_list = getattr(config, "ALLOWED_IP_RANGES_LIST", []) or []
        if allow_list:
            ip_obj = ipaddress.ip_address(ip_address)
            for entry in allow_list:
                try:
                    network = ipaddress.ip_network(entry, strict=False)
                    if ip_obj in network:
                        return True
                except ValueError:
                    # Fallback exact string match
                    if ip_address == entry:
                        return True
            return False

        return True
    except Exception:
        return True


def _is_ip_blocked(ip_address: str) -> bool:
    """Check if an IP is explicitly blocked.

    Supports exact IP matches and CIDR ranges in BLOCKED_IPS_LIST.
    Defaults to not blocked on errors.
    """
    try:
        entries = getattr(config, "BLOCKED_IPS_LIST", []) or []
        if not entries:
            return False
        ip_obj = ipaddress.ip_address(ip_address)
        for entry in entries:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                if ip_obj in network:
                    return True
            except ValueError:
                if ip_address == entry:
                    return True
        return False
    except Exception:
        return False


def get_trusted_hosts() -> List[str]:
    """
    Get trusted hosts for the TrustedHost middleware.

    Returns:
        List of trusted hostnames
    """
    # In development and testing, allow all hosts
    env = getattr(config, "ENVIRONMENT", "").lower()
    if env in ["development", "testing"]:
        return ["*"]

    # In production, use configured hosts
    trusted_hosts = getattr(config, "TRUSTED_HOSTS", None)
    if trusted_hosts:
        return (
            trusted_hosts.split(",")
            if isinstance(trusted_hosts, str)
            else trusted_hosts
        )

    # Fallback: your production domain
    return ["yourdomain.com", "*.yourdomain.com"]


# Global flag to prevent duplicate middleware setup logging
_middleware_setup_logged = False


def setup_middleware(app):
    """
    Configure all middleware for the FastAPI application with security best practices.

    Middleware is applied in reverse order (last added = first executed)
    """
    global _middleware_setup_logged

    # 1. Trusted Host middleware (first layer of protection)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_trusted_hosts())

    # 2. Metrics middleware (collect request metrics)
    app.middleware("http")(metrics_middleware)

    # 3. Request size limiting (prevent large payload attacks)
    app.middleware("http")(request_size_limit_middleware)

    # 4. Rate limiting middleware (authentication protection)
    app.middleware("http")(rate_limiting_middleware)

    # 5. Security headers middleware (comprehensive security headers)
    app.middleware("http")(security_headers_middleware)

    # 6. CORS middleware with secure configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,  # Allow credentials for authentication
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "OPTIONS",
            "PATCH",
        ],  # Explicit methods
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Client-Fingerprint",
            "X-Session-Pin",
            "X-Requested-With",
            "X-CSRF-Token",
        ],
        expose_headers=[
            "X-Response-Time",
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        max_age=600,  # Cache preflight requests for 10 minutes
    )

    # 6. Request logging middleware (last, so it captures everything)
    app.middleware("http")(request_logging_middleware)

    # 7. Configure logging filters
    configure_logging_filters()

    # Log middleware setup (only once to prevent duplicate logs during pytest imports)
    if not _middleware_setup_logged:
        logger = logging.getLogger("arcp.middleware")
        logger.info(
            f"Security middleware configured for {config.ENVIRONMENT} environment"
        )
        logger.info(f"Allowed origins: {get_allowed_origins()}")
        logger.info(f"Trusted hosts: {get_trusted_hosts()}")
        _middleware_setup_logged = True


# Helper functions for manual rate limiting (if needed)
async def require_rate_limit_check(request: Request, attempt_type: str = "general"):
    """
    Dependency function for manual rate limit checking.

    Usage:
        @app.post("/protected")
        async def protected_endpoint(
            request: Request,
            _: None = Depends(lambda req: require_rate_limit_check(req, "custom"))
        ):
            # endpoint logic
    """

    client_id = get_client_identifier(request)

    # Select appropriate rate limiter
    if attempt_type == "login":
        rate_limiter = login_rate_limiter
    elif attempt_type == "pin":
        rate_limiter = pin_rate_limiter
    else:
        rate_limiter = general_rate_limiter

    # Check rate limit
    allowed, delay, reason = await rate_limiter.check_rate_limit(
        client_id, attempt_type
    )

    if not allowed:
        # Log security event
        await log_security_event(
            "rate_limit_exceeded",
            f"Rate limit exceeded for {attempt_type}: {reason}",
            severity="WARNING",
            request=request,
            attempt_type=attempt_type,
            delay_seconds=delay,
            client_id=client_id[:16],
        )

        # Create Problem Details response for rate limiting
        response = create_problem_response(
            problem_type=ARCPProblemTypes.RATE_LIMIT_EXCEEDED,
            detail=reason,
            attempt_type=attempt_type,
            delay_seconds=delay,
            client_id=client_id[:16],
        )

        # Add rate limiting headers
        response.headers.update(
            {
                "Retry-After": str(int(delay) if delay else 60),
                "X-RateLimit-Limit": str(rate_limiter.max_attempts),
                "X-RateLimit-Remaining": "0",
            }
        )

        return response


async def record_auth_attempt(
    request: Request, success: bool, attempt_type: str = "general"
):
    """
    Manually record an authentication attempt.

    Usage:
        # After processing authentication
        await record_auth_attempt(request, success, "login")
    """
    client_id = get_client_identifier(request)

    # Select appropriate rate limiter
    if attempt_type == "login":
        rate_limiter = login_rate_limiter
    elif attempt_type == "pin":
        rate_limiter = pin_rate_limiter
    else:
        rate_limiter = general_rate_limiter

    # Record attempt
    lockout_duration = await rate_limiter.record_attempt(
        client_id, success, attempt_type
    )

    if lockout_duration:
        # Log lockout event
        await log_security_event(
            "client_locked_out",
            f"Client locked out for {lockout_duration}s due to repeated {attempt_type} failures",
            severity="ERROR",
            request=request,
            attempt_type=attempt_type,
            lockout_duration=lockout_duration,
            client_id=client_id[:16],
        )
