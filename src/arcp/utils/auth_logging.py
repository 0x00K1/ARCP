"""Authentication logging utilities for ARCP.

Provides convenient functions for logging authentication and security events
to both the dashboard (for admin visibility) and the security audit service
(for forensics, compliance, and SIEM integration).

This module acts as a facade over the security_audit service, providing
backward-compatible functions while unifying all security event handling.
"""

from typing import Optional

from fastapi import Request

from ..core.config import config
from .security_audit import (
    SecurityEventSeverity,
    SecurityEventType,
    get_security_audit_service,
    log_admin_login,
    log_agent_event,
)
from .security_audit import log_security_event as audit_security_event
from .security_audit import log_session_event as audit_session_event


async def _get_client_ip(request: Optional[Request]) -> Optional[str]:
    """Extract client IP from request."""
    if not request:
        return None
    return request.client.host if request.client else None


async def log_auth_event(
    level: str,
    event_type: str,
    message: str,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    request: Optional[Request] = None,
    **kwargs,
):
    """Log authentication events to both dashboard and security audit.

    Args:
        level: Log level (INFO, WARNING, ERROR)
        event_type: Type of auth event (login, logout, pin_set, etc.)
        message: Human-readable message
        user_id: User identifier
        agent_id: Agent identifier
        client_ip: Client IP address
        request: FastAPI request object (will extract IP if not provided)
        **kwargs: Additional context data
    """
    try:
        # Extract client IP from request if not provided
        if not client_ip:
            client_ip = await _get_client_ip(request)

        # Map event type string to SecurityEventType enum
        event_type_map = {
            "agent_login_success": SecurityEventType.AUTHENTICATION_SUCCESS,
            "agent_login_failed": SecurityEventType.AUTHENTICATION_FAILURE,
            "admin_login_success": SecurityEventType.ADMIN_LOGIN_SUCCESS,
            "admin_login_failed": SecurityEventType.ADMIN_LOGIN_FAILURE,
            "logout": SecurityEventType.ADMIN_LOGOUT,
            "pin_set": SecurityEventType.PIN_SET,
            "pin_verify_success": SecurityEventType.PIN_VERIFY_SUCCESS,
            "pin_verify_failed": SecurityEventType.PIN_VERIFY_FAILURE,
            "pin_verify_no_pin": SecurityEventType.PIN_VERIFY_FAILURE,
            "session_expired": SecurityEventType.SESSION_EXPIRED,
            "session_invalidated": SecurityEventType.SESSION_INVALIDATED,
        }

        security_event_type = event_type_map.get(event_type)

        if security_event_type:
            # Map level to severity
            severity_map = {
                "DEBUG": SecurityEventSeverity.DEBUG,
                "INFO": SecurityEventSeverity.INFO,
                "WARNING": SecurityEventSeverity.WARNING,
                "ERROR": SecurityEventSeverity.ERROR,
            }
            severity = severity_map.get(level.upper(), SecurityEventSeverity.INFO)

            # Log to security audit service
            service = get_security_audit_service()
            await service.log_event(
                security_event_type,
                message,
                agent_id=agent_id,
                user_id=user_id,
                client_ip=client_ip,
                details=kwargs,
                severity=severity,
                success="failed" not in event_type.lower(),
            )

        # Also forward to dashboard for admin visibility
        try:
            # Lazy import to avoid circular dependency
            from ..api.dashboard import add_log_entry

            context = {"event_type": event_type, **kwargs}
            if user_id:
                context["user_id"] = user_id
            if agent_id:
                context["agent_id"] = agent_id
            if client_ip:
                context["client_ip"] = client_ip

            await add_log_entry(level, message, "auth", **context)
        except Exception:
            pass  # Dashboard logging is best-effort

    except Exception as e:
        # Don't let logging failures break the auth flow
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to log auth event: {e}")


async def log_login_attempt(
    success: bool,
    username: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    client_ip: Optional[str] = None,
    request: Optional[Request] = None,
    error_message: Optional[str] = None,
):
    """Log login attempts (both admin and agent)."""
    if not client_ip:
        client_ip = await _get_client_ip(request)

    if success:
        if agent_id:
            # Agent authentication success
            await log_agent_event(
                SecurityEventType.AGENT_REGISTERED,
                agent_id=agent_id,
                agent_type=agent_type,
                client_ip=client_ip,
                details={"auth_method": "login"},
            )
            # Also log to dashboard
            await log_auth_event(
                "INFO",
                "agent_login_success",
                f"Agent authenticated successfully: {agent_id} ({agent_type})",
                agent_id=agent_id,
                agent_type=agent_type,
                client_ip=client_ip,
            )
        else:
            # Admin login success
            await log_admin_login(
                username=username or "unknown",
                success=True,
                client_ip=client_ip,
            )
    else:
        if agent_id:
            # Agent authentication failure
            await log_auth_event(
                "WARNING",
                "agent_login_failed",
                f"Agent authentication failed: {agent_id}",
                agent_id=agent_id,
                agent_type=agent_type,
                client_ip=client_ip,
                error=error_message,
            )
        else:
            # Admin login failure
            await log_admin_login(
                username=username or "unknown",
                success=False,
                client_ip=client_ip,
                error_message=error_message,
            )


async def log_session_event(
    event_type: str,
    user_id: str,
    message: Optional[str] = None,
    request: Optional[Request] = None,
    **kwargs,
):
    """Log session-related events (logout, PIN operations, etc.)."""
    client_ip = await _get_client_ip(request)

    # Map string event type to SecurityEventType
    event_type_map = {
        "logout": SecurityEventType.ADMIN_LOGOUT,
        "pin_set": SecurityEventType.PIN_SET,
        "pin_verify_success": SecurityEventType.PIN_VERIFY_SUCCESS,
        "pin_verify_failed": SecurityEventType.PIN_VERIFY_FAILURE,
        "pin_verify_no_pin": SecurityEventType.PIN_VERIFY_FAILURE,
        "session_expired": SecurityEventType.SESSION_EXPIRED,
        "session_invalidated": SecurityEventType.SESSION_INVALIDATED,
    }

    security_event_type = event_type_map.get(event_type)

    if not message:
        # Generate default messages based on event type
        messages = {
            "logout": f"Admin logout: {user_id}",
            "pin_set": f"Session PIN set for admin: {user_id}",
            "pin_verify_success": f"Successful PIN verification: {user_id}",
            "pin_verify_failed": f"Failed PIN verification attempt: {user_id}",
            "pin_verify_no_pin": f"PIN verification attempted but no PIN set: {user_id}",
            "session_expired": f"Session expired for user: {user_id}",
            "session_invalidated": f"Session invalidated for user: {user_id}",
        }
        message = messages.get(event_type, f"Session event ({event_type}): {user_id}")

    # Log to security audit service
    if security_event_type:
        await audit_session_event(
            security_event_type,
            user_id=user_id,
            client_ip=client_ip,
            details=kwargs,
        )

    # Also forward to dashboard
    warning_events = [
        "pin_verify_failed",
        "pin_verify_no_pin",
        "session_expired",
        "session_invalidated",
    ]
    level = "WARNING" if event_type in warning_events else "INFO"

    try:
        # Lazy import to avoid circular dependency
        from ..api.dashboard import add_log_entry

        await add_log_entry(
            level, f"[SECINFO] {message}", "auth", user_id=user_id, **kwargs
        )
    except Exception:
        pass


async def log_security_event(
    event_type: str,
    message: str,
    severity: str = "WARNING",
    request: Optional[Request] = None,
    **kwargs,
):
    """Log security-related events (suspicious activity, fingerprint mismatches, etc.).

    This function forwards to the unified security_audit service.
    """
    # Respect SECURITY_LOGGING flag; no-op when disabled
    if not getattr(config, "SECURITY_LOGGING", True):
        return

    client_ip = await _get_client_ip(request)

    # Use the security audit service
    await audit_security_event(
        event_type=event_type,
        message=message,
        severity=severity,
        request=request,
        **kwargs,
    )

    # Also forward to dashboard
    try:
        # Lazy import to avoid circular dependency
        from ..api.dashboard import add_log_entry

        await add_log_entry(
            severity, message, "security", client_ip=client_ip, **kwargs
        )
    except Exception:
        pass
