"""Authentication logging utilities for ARCP.

Provides convenient functions for logging authentication and security events
to the dashboard with consistent formatting.
"""

from typing import Optional

from fastapi import Request

from ..core.config import config


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
    """Log authentication events to the dashboard.

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
        # Import here to avoid circular imports
        from ..api.dashboard import add_log_entry

        # Extract client IP from request if not provided
        if not client_ip and request:
            client_ip = request.client.host if request.client else "unknown"

        # Prepare additional context
        context = {"event_type": event_type, **kwargs}

        # Add identifiers if provided
        if user_id:
            context["user_id"] = user_id
        if agent_id:
            context["agent_id"] = agent_id
        if client_ip:
            context["client_ip"] = client_ip

        await add_log_entry(level, message, "auth", **context)

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
    if success:
        if agent_id:
            await log_auth_event(
                "INFO",
                "agent_login_success",
                f"Agent authenticated successfully: {agent_id} ({agent_type})",
                agent_id=agent_id,
                agent_type=agent_type,
                client_ip=client_ip,
                request=request,
            )
        else:
            await log_auth_event(
                "INFO",
                "admin_login_success",
                f"Admin login successful: {username}",
                user_id=username,
                client_ip=client_ip,
                request=request,
            )
    else:
        level = "WARNING"
        if agent_id:
            message = f"Agent authentication failed: {agent_id}"
            event_type = "agent_login_failed"
            context = {"agent_id": agent_id, "agent_type": agent_type}
        else:
            message = f"Admin login failed: {username}"
            event_type = "admin_login_failed"
            context = {"username": username}

        if error_message:
            context["error"] = error_message

        await log_auth_event(
            level,
            event_type,
            message,
            client_ip=client_ip,
            request=request,
            **context,
        )


async def log_session_event(
    event_type: str,
    user_id: str,
    message: Optional[str] = None,
    request: Optional[Request] = None,
    **kwargs,
):
    """Log session-related events (logout, PIN operations, etc.)."""
    if not message:
        # Generate default messages based on event type
        messages = {
            "logout": f"[SECINFO] Admin logout: {user_id}",
            "pin_set": f"[SECINFO] Session PIN set for admin: {user_id}",
            "pin_verify_success": f"[SECINFO] Successful PIN verification: {user_id}",
            "pin_verify_failed": f"[SECINFO] Failed PIN verification attempt: {user_id}",
            "pin_verify_no_pin": f"[SECINFO] PIN verification attempted but no PIN set: {user_id}",
            "session_expired": f"[SECINFO] Session expired for user: {user_id}",
            "session_invalidated": f"[SECINFO] Session invalidated for user: {user_id}",
        }
        message = messages.get(event_type, f"Session event ({event_type}): {user_id}")

    # Determine log level based on event type
    warning_events = [
        "pin_verify_failed",
        "pin_verify_no_pin",
        "session_expired",
        "session_invalidated",
    ]
    level = "WARNING" if event_type in warning_events else "INFO"

    await log_auth_event(
        level, event_type, message, user_id=user_id, request=request, **kwargs
    )


async def log_security_event(
    event_type: str,
    message: str,
    severity: str = "WARNING",
    request: Optional[Request] = None,
    **kwargs,
):
    """Log security-related events (suspicious activity, fingerprint mismatches, etc.)."""
    # Respect SECURITY_LOGGING flag; no-op when disabled
    if not getattr(config, "SECURITY_LOGGING", True):
        return
    await log_auth_event(severity, event_type, message, request=request, **kwargs)
