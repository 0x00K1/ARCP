"""
Security Event Auditing Service for ARCP.

Provides comprehensive security event logging for:
- Authentication events (DPoP, mTLS, token operations)
- Key management events (JWKS rotation, revocation)
- Attestation events (challenge, verification)
- Security policy violations

Events are logged to multiple sinks:
- Application logs (structured JSON)
- Redis for real-time monitoring
- Optional external SIEM integration

Environment Variables:
    SECURITY_AUDIT_ENABLED: Enable security auditing (default: true)
    SECURITY_AUDIT_REDIS: Store events in Redis (default: true)
    SECURITY_AUDIT_RETENTION_HOURS: Redis retention (default: 168 = 7 days)
    SECURITY_AUDIT_SIEM_URL: Optional webhook URL for SIEM
    SECURITY_AUDIT_SIEM_TOKEN: Bearer token for SIEM webhook

Example Usage:
    >>> from arcp.utils.security_audit import audit_log, SecurityEventType
    >>> await audit_log.log_event(
    ...     SecurityEventType.AUTHENTICATION_SUCCESS,
    ...     agent_id="agent-001",
    ...     details={"method": "dpop", "jkt": "abc123..."}
    ... )
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

from ..core.config import config
from ..services.redis import get_redis_service

logger = logging.getLogger(__name__)

# Redis key prefixes
AUDIT_PREFIX = "arcp:audit:"
AUDIT_STREAM = "arcp:audit:stream"
AUDIT_COUNTER = "arcp:audit:counter"


class SecurityEventType(Enum):
    """Types of security events to audit."""

    # Authentication Events
    AUTHENTICATION_SUCCESS = "auth.success"
    AUTHENTICATION_FAILURE = "auth.failure"
    TOKEN_ISSUED = "token.issued"
    TOKEN_REVOKED = "token.revoked"
    TOKEN_EXPIRED = "token.expired"
    TOKEN_VALIDATION_FAILED = "token.validation_failed"

    # Admin/Dashboard Events
    ADMIN_LOGIN_SUCCESS = "admin.login_success"
    ADMIN_LOGIN_FAILURE = "admin.login_failure"
    ADMIN_LOGOUT = "admin.logout"

    # Session Events
    SESSION_CREATED = "session.created"
    SESSION_EXPIRED = "session.expired"
    SESSION_INVALIDATED = "session.invalidated"
    PIN_SET = "session.pin_set"
    PIN_VERIFY_SUCCESS = "session.pin_verify_success"
    PIN_VERIFY_FAILURE = "session.pin_verify_failure"

    # DPoP Events
    DPOP_PROOF_VALID = "dpop.proof_valid"
    DPOP_PROOF_INVALID = "dpop.proof_invalid"
    DPOP_REPLAY_DETECTED = "dpop.replay_detected"
    DPOP_BINDING_MISMATCH = "dpop.binding_mismatch"
    DPOP_SIGNATURE_INVALID = "dpop.signature_invalid"
    DPOP_EXPIRED = "dpop.expired"

    # mTLS Events
    MTLS_CERT_VALID = "mtls.cert_valid"
    MTLS_CERT_INVALID = "mtls.cert_invalid"
    MTLS_CERT_EXPIRED = "mtls.cert_expired"
    MTLS_CERT_REVOKED = "mtls.cert_revoked"
    MTLS_CHAIN_INVALID = "mtls.chain_invalid"
    MTLS_BINDING_MISMATCH = "mtls.binding_mismatch"
    MTLS_OCSP_CHECK_FAILED = "mtls.ocsp_check_failed"
    MTLS_CRL_CHECK_FAILED = "mtls.crl_check_failed"

    # JWKS Events
    JWKS_KEY_GENERATED = "jwks.key_generated"
    JWKS_KEY_ROTATED = "jwks.key_rotated"
    JWKS_KEY_REVOKED = "jwks.key_revoked"
    JWKS_KEY_EXPIRED = "jwks.key_expired"
    JWKS_ACCESSED = "jwks.accessed"
    JWKS_REVOKED_KEY_USED = "jwks.revoked_key_used"

    # Configuration Events
    CONFIG_ACCESSED = "config.accessed"
    CONFIG_MODIFIED = "config.modified"

    # Attestation Events
    ATTESTATION_CHALLENGE_CREATED = "attestation.challenge_created"
    ATTESTATION_CHALLENGE_EXPIRED = "attestation.challenge_expired"
    ATTESTATION_SUCCESS = "attestation.success"
    ATTESTATION_FAILURE = "attestation.failure"
    ATTESTATION_TPM_QUOTE_VERIFIED = "attestation.tpm_quote_verified"
    ATTESTATION_TPM_QUOTE_FAILED = "attestation.tpm_quote_failed"
    ATTESTATION_TPM_NONCE_INVALID = "attestation.tpm_nonce_invalid"
    ATTESTATION_SOFTWARE_VERIFIED = "attestation.software_verified"

    # SBOM Events
    SBOM_VERIFICATION_SUCCESS = "sbom.verification_success"
    SBOM_VERIFICATION_FAILURE = "sbom.verification_failure"
    SBOM_VULNERABILITY_DETECTED = "sbom.vulnerability_detected"
    SBOM_FORMAT_INVALID = "sbom.format_invalid"

    # Container Scan Events
    CONTAINER_SCAN_SUCCESS = "container.scan_success"
    CONTAINER_SCAN_FAILURE = "container.scan_failure"
    CONTAINER_VULNERABILITY_DETECTED = "container.vulnerability_detected"
    CONTAINER_SECRET_DETECTED = "container.secret_detected"

    # Agent Events
    AGENT_REGISTERED = "agent.registered"
    AGENT_DEREGISTERED = "agent.deregistered"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_HEARTBEAT_MISSED = "agent.heartbeat_missed"
    AGENT_SUSPENDED = "agent.suspended"
    AGENT_REACTIVATED = "agent.reactivated"

    # TPR (Third-Party Registration) Events
    TPR_TOKEN_GENERATED = "tpr.token_generated"
    TPR_TOKEN_USED = "tpr.token_used"
    TPR_TOKEN_EXPIRED = "tpr.token_expired"
    TPR_TOKEN_INVALID = "tpr.token_invalid"

    # Validation Events
    VALIDATION_PASSED = "validation.passed"
    VALIDATION_FAILED = "validation.failed"
    VALIDATION_STARTED = "validation.started"

    # Policy Violations
    RATE_LIMIT_EXCEEDED = "policy.rate_limit_exceeded"
    ACCESS_DENIED = "policy.access_denied"
    INVALID_REQUEST = "policy.invalid_request"
    SUSPICIOUS_ACTIVITY = "policy.suspicious_activity"
    FORBIDDEN_OPERATION = "policy.forbidden_operation"
    CLIENT_LOCKED_OUT = "policy.client_locked_out"

    # Access Events
    PRIVILEGED_ENDPOINT_ACCESS = "access.privileged_endpoint"
    UNAUTHORIZED_ACCESS_ATTEMPT = "access.unauthorized_attempt"
    INVALID_TOKEN_ACCESS = "access.invalid_token"
    INSUFFICIENT_PERMISSIONS = "access.insufficient_permissions"
    MISSING_ADMIN_SESSION = "access.missing_admin_session"
    PIN_PROTECTED_ACCESS = "access.pin_protected"

    # Token Verification Events
    TOKEN_VERIFICATION_ERROR = "token.verification_error"

    # PIN Events
    MISSING_PIN_ACCESS = "pin.missing_access"
    INVALID_PIN_ACCESS = "pin.invalid_access"
    PIN_VERIFICATION_ERROR = "pin.verification_error"

    # DPoP Enforcement Events
    DPOP_REQUIRED_MISSING = "dpop.required_missing"
    DPOP_VALIDATION_FAILED = "dpop.validation_failed"
    MISSING_DPOP_PROOF = "dpop.missing_proof"

    # mTLS Enforcement Events
    MTLS_REQUIRED_MISSING = "mtls.required_missing"

    # Session Security Events
    FINGERPRINT_MISMATCH = "session.fingerprint_mismatch"
    MISSING_FINGERPRINT = "session.missing_fingerprint"
    IP_CHANGE = "session.ip_change"
    USER_AGENT_CHANGE = "session.user_agent_change"

    # Attempt Events
    LOGIN_ATTEMPT_FAILED = "attempt.login_failed"
    PIN_ATTEMPT_FAILED = "attempt.pin_failed"
    GENERAL_ATTEMPT_FAILED = "attempt.general_failed"

    # WebSocket Events
    WEBSOCKET_CONNECTED = "websocket.connected"
    WEBSOCKET_DISCONNECTED = "websocket.disconnected"
    WEBSOCKET_AUTH_FAILED = "websocket.auth_failed"

    # System Events
    SERVICE_STARTED = "system.service_started"
    SERVICE_STOPPED = "system.service_stopped"
    CONFIG_CHANGED = "system.config_changed"
    SECURITY_CONFIG_CHANGED = "system.security_config_changed"


class SecurityEventSeverity(Enum):
    """Severity levels for security events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    """A security event for auditing."""

    event_id: str
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    timestamp: datetime

    # Context
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    client_ip: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None

    # Details
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    # Outcome
    success: bool = True
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "message": self.message,
            "details": self.details,
            "success": self.success,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


# Severity mappings for event types
EVENT_SEVERITY_MAP: Dict[SecurityEventType, SecurityEventSeverity] = {
    # Debug level
    SecurityEventType.DPOP_PROOF_VALID: SecurityEventSeverity.DEBUG,
    SecurityEventType.MTLS_CERT_VALID: SecurityEventSeverity.DEBUG,
    SecurityEventType.ATTESTATION_CHALLENGE_CREATED: SecurityEventSeverity.DEBUG,
    SecurityEventType.AGENT_HEARTBEAT: SecurityEventSeverity.DEBUG,
    SecurityEventType.JWKS_ACCESSED: SecurityEventSeverity.DEBUG,
    SecurityEventType.CONFIG_ACCESSED: SecurityEventSeverity.DEBUG,
    SecurityEventType.TOKEN_EXPIRED: SecurityEventSeverity.DEBUG,
    SecurityEventType.WEBSOCKET_CONNECTED: SecurityEventSeverity.DEBUG,
    SecurityEventType.WEBSOCKET_DISCONNECTED: SecurityEventSeverity.DEBUG,
    # Info level
    SecurityEventType.AUTHENTICATION_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.TOKEN_ISSUED: SecurityEventSeverity.INFO,
    SecurityEventType.JWKS_KEY_GENERATED: SecurityEventSeverity.INFO,
    SecurityEventType.JWKS_KEY_ROTATED: SecurityEventSeverity.INFO,
    SecurityEventType.ATTESTATION_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.ATTESTATION_TPM_QUOTE_VERIFIED: SecurityEventSeverity.INFO,
    SecurityEventType.ATTESTATION_SOFTWARE_VERIFIED: SecurityEventSeverity.INFO,
    SecurityEventType.SBOM_VERIFICATION_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.CONTAINER_SCAN_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.AGENT_REGISTERED: SecurityEventSeverity.INFO,
    SecurityEventType.AGENT_DEREGISTERED: SecurityEventSeverity.INFO,
    SecurityEventType.AGENT_REACTIVATED: SecurityEventSeverity.INFO,
    SecurityEventType.SERVICE_STARTED: SecurityEventSeverity.INFO,
    SecurityEventType.SERVICE_STOPPED: SecurityEventSeverity.INFO,
    SecurityEventType.JWKS_KEY_EXPIRED: SecurityEventSeverity.INFO,
    SecurityEventType.ADMIN_LOGIN_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.ADMIN_LOGOUT: SecurityEventSeverity.INFO,
    SecurityEventType.SESSION_CREATED: SecurityEventSeverity.INFO,
    SecurityEventType.PIN_SET: SecurityEventSeverity.INFO,
    SecurityEventType.PIN_VERIFY_SUCCESS: SecurityEventSeverity.INFO,
    SecurityEventType.TPR_TOKEN_GENERATED: SecurityEventSeverity.INFO,
    SecurityEventType.TPR_TOKEN_USED: SecurityEventSeverity.INFO,
    SecurityEventType.VALIDATION_PASSED: SecurityEventSeverity.INFO,
    SecurityEventType.VALIDATION_STARTED: SecurityEventSeverity.INFO,
    # Warning level
    SecurityEventType.AUTHENTICATION_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.TOKEN_VALIDATION_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.VALIDATION_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.DPOP_PROOF_INVALID: SecurityEventSeverity.WARNING,
    SecurityEventType.DPOP_EXPIRED: SecurityEventSeverity.WARNING,
    SecurityEventType.MTLS_CERT_INVALID: SecurityEventSeverity.WARNING,
    SecurityEventType.MTLS_CERT_EXPIRED: SecurityEventSeverity.WARNING,
    SecurityEventType.MTLS_OCSP_CHECK_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.MTLS_CRL_CHECK_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.ATTESTATION_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.ATTESTATION_CHALLENGE_EXPIRED: SecurityEventSeverity.WARNING,
    SecurityEventType.SBOM_VERIFICATION_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.SBOM_VULNERABILITY_DETECTED: SecurityEventSeverity.WARNING,
    SecurityEventType.SBOM_FORMAT_INVALID: SecurityEventSeverity.WARNING,
    SecurityEventType.CONTAINER_SCAN_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.CONTAINER_VULNERABILITY_DETECTED: SecurityEventSeverity.WARNING,
    SecurityEventType.AGENT_HEARTBEAT_MISSED: SecurityEventSeverity.WARNING,
    SecurityEventType.AGENT_SUSPENDED: SecurityEventSeverity.WARNING,
    SecurityEventType.RATE_LIMIT_EXCEEDED: SecurityEventSeverity.WARNING,
    SecurityEventType.INVALID_REQUEST: SecurityEventSeverity.WARNING,
    SecurityEventType.TOKEN_REVOKED: SecurityEventSeverity.WARNING,
    SecurityEventType.CONFIG_CHANGED: SecurityEventSeverity.WARNING,
    SecurityEventType.ADMIN_LOGIN_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.SESSION_EXPIRED: SecurityEventSeverity.WARNING,
    SecurityEventType.SESSION_INVALIDATED: SecurityEventSeverity.WARNING,
    SecurityEventType.PIN_VERIFY_FAILURE: SecurityEventSeverity.WARNING,
    SecurityEventType.TPR_TOKEN_EXPIRED: SecurityEventSeverity.WARNING,
    SecurityEventType.TPR_TOKEN_INVALID: SecurityEventSeverity.WARNING,
    SecurityEventType.WEBSOCKET_AUTH_FAILED: SecurityEventSeverity.WARNING,
    # Error level
    SecurityEventType.DPOP_REPLAY_DETECTED: SecurityEventSeverity.ERROR,
    SecurityEventType.DPOP_BINDING_MISMATCH: SecurityEventSeverity.ERROR,
    SecurityEventType.DPOP_SIGNATURE_INVALID: SecurityEventSeverity.ERROR,
    SecurityEventType.MTLS_CERT_REVOKED: SecurityEventSeverity.ERROR,
    SecurityEventType.MTLS_CHAIN_INVALID: SecurityEventSeverity.ERROR,
    SecurityEventType.MTLS_BINDING_MISMATCH: SecurityEventSeverity.ERROR,
    SecurityEventType.ATTESTATION_TPM_QUOTE_FAILED: SecurityEventSeverity.ERROR,
    SecurityEventType.ATTESTATION_TPM_NONCE_INVALID: SecurityEventSeverity.ERROR,
    SecurityEventType.CONTAINER_SECRET_DETECTED: SecurityEventSeverity.ERROR,
    SecurityEventType.ACCESS_DENIED: SecurityEventSeverity.ERROR,
    SecurityEventType.FORBIDDEN_OPERATION: SecurityEventSeverity.ERROR,
    SecurityEventType.SECURITY_CONFIG_CHANGED: SecurityEventSeverity.ERROR,
    # Critical level
    SecurityEventType.JWKS_KEY_REVOKED: SecurityEventSeverity.CRITICAL,
    SecurityEventType.JWKS_REVOKED_KEY_USED: SecurityEventSeverity.CRITICAL,
    SecurityEventType.SUSPICIOUS_ACTIVITY: SecurityEventSeverity.CRITICAL,
}


class SecurityAuditService:
    """
    Security event auditing service.

    Logs security events to multiple destinations for
    monitoring, alerting, and forensic analysis.
    """

    def __init__(self):
        self.enabled = getattr(config, "SECURITY_AUDIT_ENABLED", True)
        self.redis_enabled = getattr(config, "SECURITY_AUDIT_REDIS", True)
        self.retention_hours = getattr(config, "SECURITY_AUDIT_RETENTION_HOURS", 168)
        self.siem_url = getattr(config, "SECURITY_AUDIT_SIEM_URL", None)
        self.siem_token = getattr(config, "SECURITY_AUDIT_SIEM_TOKEN", None)

        self._redis = None
        self._event_counter = 0
        self._http_client = None

    def _get_redis(self):
        """Get Redis client."""
        if self._redis is None:
            try:
                redis_service = get_redis_service()
                if redis_service and redis_service.is_available():
                    self._redis = redis_service.get_client()
            except Exception:
                pass
        return self._redis

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        timestamp = int(time.time() * 1000)
        counter = self._event_counter % 10000
        random_part = os.urandom(4).hex()
        return f"evt_{timestamp}_{counter:04d}_{random_part}"

    async def log_event(
        self,
        event_type: SecurityEventType,
        message: str = "",
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        severity: Optional[SecurityEventSeverity] = None,
    ) -> Optional[str]:
        """
        Log a security event.

        Args:
            event_type: Type of security event
            message: Human-readable description
            agent_id: Related agent ID
            user_id: Related user ID
            client_ip: Client IP address
            request_id: Request correlation ID
            session_id: Session ID
            details: Additional event details
            success: Whether the operation succeeded
            error_code: Error code if failed
            error_message: Error message if failed
            severity: Override default severity

        Returns:
            Event ID or None if logging failed
        """
        if not self.enabled:
            return None

        # Determine severity
        if severity is None:
            severity = EVENT_SEVERITY_MAP.get(event_type, SecurityEventSeverity.INFO)

        # Create event
        event = SecurityEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            severity=severity,
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            user_id=user_id,
            client_ip=client_ip,
            request_id=request_id,
            session_id=session_id,
            message=message or f"{event_type.value}",
            details=details or {},
            success=success,
            error_code=error_code,
            error_message=error_message,
        )

        # Log to application logger
        self._log_to_logger(event)

        # Store in Redis for real-time monitoring
        if self.redis_enabled:
            await self._store_in_redis(event)

        # Send to SIEM if configured
        if self.siem_url:
            asyncio.create_task(self._send_to_siem(event))

        return event.event_id

    def _log_to_logger(self, event: SecurityEvent) -> None:
        """Log event to application logger."""
        log_data = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "agent_id": event.agent_id,
            "user_id": event.user_id,
            "client_ip": event.client_ip,
            "success": event.success,
            "details": event.details,
        }

        if event.error_code:
            log_data["error_code"] = event.error_code
        if event.error_message:
            log_data["error_message"] = event.error_message

        log_message = f"[SECURITY] {event.message} | {json.dumps(log_data)}"

        if event.severity == SecurityEventSeverity.DEBUG:
            logger.debug(log_message)
        elif event.severity == SecurityEventSeverity.INFO:
            logger.info(log_message)
        elif event.severity == SecurityEventSeverity.WARNING:
            logger.warning(log_message)
        elif event.severity == SecurityEventSeverity.ERROR:
            logger.error(log_message)
        elif event.severity == SecurityEventSeverity.CRITICAL:
            logger.critical(log_message)

    async def _store_in_redis(self, event: SecurityEvent) -> None:
        """Store event in Redis stream for real-time access."""
        redis = self._get_redis()
        if not redis:
            return

        try:
            # Store in Redis stream
            ttl_seconds = self.retention_hours * 3600

            # Convert event to dict and filter out None values (Redis can't store None)
            event_data = {k: v for k, v in event.to_dict().items() if v is not None}

            # Convert all values to Redis-compatible types (str, bytes, int, float)
            # Note: bool is subclass of int in Python, so check it first
            for key, value in event_data.items():
                if isinstance(value, bool):
                    # Convert bool to string "true"/"false" for clarity
                    event_data[key] = "true" if value else "false"
                elif isinstance(value, (dict, list)):
                    event_data[key] = json.dumps(value, default=str)
                elif not isinstance(value, (str, int, float, bytes)):
                    event_data[key] = str(value)

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: redis.xadd(
                    AUDIT_STREAM,
                    event_data,
                    maxlen=100000,  # Keep last 100k events
                ),
            )

            # Increment counters for metrics
            counter_key = f"{AUDIT_COUNTER}:{event.event_type.value}"
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: redis.incr(counter_key)
            )

            # Store indexed by agent/user for quick lookup
            if event.agent_id:
                agent_key = f"{AUDIT_PREFIX}agent:{event.agent_id}"
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.lpush(agent_key, event.to_json())
                )
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.ltrim(agent_key, 0, 999)  # Keep last 1000
                )
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.expire(agent_key, ttl_seconds)
                )

        except Exception as e:
            logger.warning(f"Failed to store audit event in Redis: {e}")

    async def _send_to_siem(self, event: SecurityEvent) -> None:
        """Send event to external SIEM via webhook."""
        if not self.siem_url:
            return

        try:
            headers = {"Content-Type": "application/json"}
            if self.siem_token:
                headers["Authorization"] = f"Bearer {self.siem_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.siem_url,
                    json=event.to_dict(),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status >= 400:
                        logger.warning(f"SIEM webhook failed: {response.status}")
        except Exception as e:
            logger.warning(f"Failed to send event to SIEM: {e}")

    async def get_recent_events(
        self,
        count: int = 100,
        event_type: Optional[SecurityEventType] = None,
        agent_id: Optional[str] = None,
        severity: Optional[SecurityEventSeverity] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent security events.

        Args:
            count: Maximum number of events to return
            event_type: Filter by event type
            agent_id: Filter by agent ID
            severity: Filter by severity

        Returns:
            List of event dictionaries
        """
        redis = self._get_redis()
        if not redis:
            return []

        try:
            if agent_id:
                # Get from agent-specific list
                agent_key = f"{AUDIT_PREFIX}agent:{agent_id}"
                raw_events = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.lrange(agent_key, 0, count - 1)
                )
                events = [json.loads(e) for e in raw_events]
            else:
                # Get from main stream
                raw_events = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis.xrevrange(AUDIT_STREAM, count=count)
                )
                events = [dict(e[1]) for e in raw_events]

            # Apply filters
            if event_type:
                events = [e for e in events if e.get("event_type") == event_type.value]
            if severity:
                events = [e for e in events if e.get("severity") == severity.value]

            return events[:count]

        except Exception as e:
            logger.warning(f"Failed to get audit events: {e}")
            return []

    async def get_event_counts(self, since_hours: int = 24) -> Dict[str, int]:
        """Get event counts by type for the specified period."""
        redis = self._get_redis()
        if not redis:
            return {}

        try:
            counts = {}
            for event_type in SecurityEventType:
                counter_key = f"{AUDIT_COUNTER}:{event_type.value}"
                count = await asyncio.get_event_loop().run_in_executor(
                    None, lambda k=counter_key: redis.get(k)
                )
                if count:
                    counts[event_type.value] = int(count)
            return counts
        except Exception as e:
            logger.warning(f"Failed to get event counts: {e}")
            return {}


# Singleton instance
_audit_service: Optional[SecurityAuditService] = None


def get_security_audit_service() -> SecurityAuditService:
    """Get the security audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = SecurityAuditService()
    return _audit_service


# Convenience alias
audit_log = get_security_audit_service()


# Convenience functions for common events
async def log_authentication_success(
    agent_id: str,
    method: str,
    client_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log successful authentication."""
    service = get_security_audit_service()
    return await service.log_event(
        SecurityEventType.AUTHENTICATION_SUCCESS,
        f"Agent {agent_id} authenticated via {method}",
        agent_id=agent_id,
        client_ip=client_ip,
        details={"method": method, **(details or {})},
    )


async def log_authentication_failure(
    agent_id: Optional[str],
    method: str,
    reason: str,
    client_ip: Optional[str] = None,
) -> Optional[str]:
    """Log failed authentication."""
    service = get_security_audit_service()
    return await service.log_event(
        SecurityEventType.AUTHENTICATION_FAILURE,
        f"Authentication failed for {agent_id or 'unknown'}: {reason}",
        agent_id=agent_id,
        client_ip=client_ip,
        details={"method": method, "reason": reason},
        success=False,
        error_message=reason,
    )


async def log_key_event(
    event_type: SecurityEventType,
    kid: str,
    reason: Optional[str] = None,
) -> Optional[str]:
    """Log JWKS key event."""
    service = get_security_audit_service()
    return await service.log_event(
        event_type,
        f"Key {kid}: {event_type.value}",
        details={"kid": kid, "reason": reason},
    )


async def log_security_event(
    event_type: str,
    message: str,
    severity: str = "INFO",
    request: Optional[Any] = None,
    **kwargs,
) -> Optional[str]:
    """Legacy-compatible security event logging."""
    service = get_security_audit_service()

    # Map string event type to enum
    try:
        enum_type = SecurityEventType(event_type)
    except ValueError:
        # Log warning about unknown event type and use INVALID_REQUEST as fallback
        logger.warning(
            f"Unknown security event type '{event_type}', using INVALID_REQUEST as fallback. "
            f"Consider adding this event type to SecurityEventType enum."
        )
        enum_type = SecurityEventType.INVALID_REQUEST

    # Map string severity to enum
    severity_map = {
        "DEBUG": SecurityEventSeverity.DEBUG,
        "INFO": SecurityEventSeverity.INFO,
        "WARNING": SecurityEventSeverity.WARNING,
        "ERROR": SecurityEventSeverity.ERROR,
        "CRITICAL": SecurityEventSeverity.CRITICAL,
    }
    enum_severity = severity_map.get(severity.upper(), SecurityEventSeverity.INFO)

    client_ip = None
    if request:
        client_ip = getattr(request, "client", {})
        if hasattr(client_ip, "host"):
            client_ip = client_ip.host
        else:
            client_ip = None

    return await service.log_event(
        enum_type,
        message,
        client_ip=client_ip,
        details=kwargs,
        severity=enum_severity,
    )


# ============================================================================
# Dashboard Integration - Forward events to dashboard for admin visibility
# ============================================================================


async def _forward_to_dashboard(event: SecurityEvent) -> None:
    """Forward security event to dashboard for admin visibility."""
    try:
        # Lazy import to avoid circular dependency
        from ..api.dashboard import add_log_entry

        # Map severity to dashboard level
        level_map = {
            SecurityEventSeverity.DEBUG: "DEBUG",
            SecurityEventSeverity.INFO: "INFO",
            SecurityEventSeverity.WARNING: "WARNING",
            SecurityEventSeverity.ERROR: "ERROR",
            SecurityEventSeverity.CRITICAL: "ERROR",
        }
        level = level_map.get(event.severity, "INFO")

        # Prepare context for dashboard
        context = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            **event.details,
        }

        if event.agent_id:
            context["agent_id"] = event.agent_id
        if event.user_id:
            context["user_id"] = event.user_id
        if event.client_ip:
            context["client_ip"] = event.client_ip
        if event.error_code:
            context["error_code"] = event.error_code

        await add_log_entry(level, event.message, "security", **context)

    except Exception as e:
        # Don't let dashboard logging break the main flow
        logger.debug(f"Failed to forward event to dashboard: {e}")


# ============================================================================
# Convenience Functions for Common Security Events
# ============================================================================

# --- Admin/Session Events ---


async def log_admin_login(
    username: str,
    success: bool,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    """Log admin login attempt."""
    service = get_security_audit_service()
    event_type = (
        SecurityEventType.ADMIN_LOGIN_SUCCESS
        if success
        else SecurityEventType.ADMIN_LOGIN_FAILURE
    )
    message = f"Admin login {'successful' if success else 'failed'}: {username}"

    return await service.log_event(
        event_type,
        message,
        user_id=username,
        client_ip=client_ip,
        success=success,
        error_message=error_message,
        details={"username": username},
    )


async def log_session_event(
    event_type: SecurityEventType,
    user_id: str,
    session_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log session-related event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.SESSION_CREATED: f"Session created for {user_id}",
        SecurityEventType.SESSION_EXPIRED: f"Session expired for {user_id}",
        SecurityEventType.SESSION_INVALIDATED: f"Session invalidated for {user_id}",
        SecurityEventType.PIN_SET: f"Session PIN set for {user_id}",
        SecurityEventType.PIN_VERIFY_SUCCESS: f"PIN verified for {user_id}",
        SecurityEventType.PIN_VERIFY_FAILURE: f"PIN verification failed for {user_id}",
        SecurityEventType.ADMIN_LOGOUT: f"Admin logout: {user_id}",
    }

    return await service.log_event(
        event_type,
        messages.get(event_type, f"{event_type.value}: {user_id}"),
        user_id=user_id,
        session_id=session_id,
        client_ip=client_ip,
        details=details or {},
    )


# --- DPoP Events ---


async def log_dpop_event(
    event_type: SecurityEventType,
    jti: Optional[str] = None,
    jkt: Optional[str] = None,
    agent_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log DPoP-related event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.DPOP_PROOF_VALID: (
            f"DPoP proof validated (jkt: {jkt[:16]}...)"
            if jkt
            else "DPoP proof validated"
        ),
        SecurityEventType.DPOP_PROOF_INVALID: f"DPoP proof invalid: {error_message}",
        SecurityEventType.DPOP_REPLAY_DETECTED: f"DPoP replay detected (jti: {jti})",
        SecurityEventType.DPOP_BINDING_MISMATCH: f"DPoP binding mismatch for {agent_id}",
        SecurityEventType.DPOP_SIGNATURE_INVALID: "DPoP signature verification failed",
        SecurityEventType.DPOP_EXPIRED: "DPoP proof expired",
    }

    event_details = {"jti": jti, "jkt": jkt, **(details or {})}

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        agent_id=agent_id,
        client_ip=client_ip,
        success=event_type == SecurityEventType.DPOP_PROOF_VALID,
        error_message=error_message,
        details=event_details,
    )


# --- mTLS Events ---


async def log_mtls_event(
    event_type: SecurityEventType,
    cert_subject: Optional[str] = None,
    spki_hash: Optional[str] = None,
    agent_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log mTLS-related event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.MTLS_CERT_VALID: f"mTLS certificate valid (subject: {cert_subject})",
        SecurityEventType.MTLS_CERT_INVALID: f"mTLS certificate invalid: {error_message}",
        SecurityEventType.MTLS_CERT_EXPIRED: f"mTLS certificate expired (subject: {cert_subject})",
        SecurityEventType.MTLS_CERT_REVOKED: f"mTLS certificate revoked (subject: {cert_subject})",
        SecurityEventType.MTLS_CHAIN_INVALID: "mTLS certificate chain validation failed",
        SecurityEventType.MTLS_BINDING_MISMATCH: f"mTLS binding mismatch for {agent_id}",
        SecurityEventType.MTLS_OCSP_CHECK_FAILED: "OCSP revocation check failed",
        SecurityEventType.MTLS_CRL_CHECK_FAILED: "CRL revocation check failed",
    }

    event_details = {
        "cert_subject": cert_subject,
        "spki_hash": spki_hash,
        **(details or {}),
    }

    success = event_type == SecurityEventType.MTLS_CERT_VALID

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        agent_id=agent_id,
        client_ip=client_ip,
        success=success,
        error_message=error_message,
        details=event_details,
    )


# --- Attestation Events ---


async def log_attestation_event(
    event_type: SecurityEventType,
    agent_id: str,
    attestation_type: Optional[str] = None,
    challenge_id: Optional[str] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log attestation-related event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.ATTESTATION_CHALLENGE_CREATED: f"Attestation challenge created for {agent_id}",
        SecurityEventType.ATTESTATION_CHALLENGE_EXPIRED: f"Attestation challenge expired for {agent_id}",
        SecurityEventType.ATTESTATION_SUCCESS: f"Attestation verified for {agent_id} (type: {attestation_type})",
        SecurityEventType.ATTESTATION_FAILURE: f"Attestation failed for {agent_id}: {error_message}",
        SecurityEventType.ATTESTATION_TPM_QUOTE_VERIFIED: f"TPM quote verified for {agent_id}",
        SecurityEventType.ATTESTATION_TPM_QUOTE_FAILED: f"TPM quote verification failed for {agent_id}",
        SecurityEventType.ATTESTATION_TPM_NONCE_INVALID: f"TPM nonce validation failed for {agent_id}",
        SecurityEventType.ATTESTATION_SOFTWARE_VERIFIED: f"Software attestation verified for {agent_id}",
    }

    success = event_type in (
        SecurityEventType.ATTESTATION_SUCCESS,
        SecurityEventType.ATTESTATION_TPM_QUOTE_VERIFIED,
        SecurityEventType.ATTESTATION_SOFTWARE_VERIFIED,
        SecurityEventType.ATTESTATION_CHALLENGE_CREATED,
    )

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        agent_id=agent_id,
        success=success,
        error_message=error_message,
        details={
            "attestation_type": attestation_type,
            "challenge_id": challenge_id,
            **(details or {}),
        },
    )


# --- Agent Events ---


async def log_agent_event(
    event_type: SecurityEventType,
    agent_id: str,
    agent_type: Optional[str] = None,
    client_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log agent lifecycle event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.AGENT_REGISTERED: f"Agent registered: {agent_id} (type: {agent_type})",
        SecurityEventType.AGENT_DEREGISTERED: f"Agent deregistered: {agent_id}",
        SecurityEventType.AGENT_HEARTBEAT: f"Agent heartbeat: {agent_id}",
        SecurityEventType.AGENT_HEARTBEAT_MISSED: f"Agent heartbeat missed: {agent_id}",
        SecurityEventType.AGENT_SUSPENDED: f"Agent suspended: {agent_id}",
        SecurityEventType.AGENT_REACTIVATED: f"Agent reactivated: {agent_id}",
    }

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        agent_id=agent_id,
        client_ip=client_ip,
        details={"agent_type": agent_type, **(details or {})},
    )


# --- TPR Events ---


async def log_tpr_event(
    event_type: SecurityEventType,
    token_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    """Log TPR (Third-Party Registration) token event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.TPR_TOKEN_GENERATED: f"TPR token generated: {token_id}",
        SecurityEventType.TPR_TOKEN_USED: f"TPR token used for agent: {agent_id}",
        SecurityEventType.TPR_TOKEN_EXPIRED: f"TPR token expired: {token_id}",
        SecurityEventType.TPR_TOKEN_INVALID: f"TPR token invalid: {error_message}",
    }

    success = event_type in (
        SecurityEventType.TPR_TOKEN_GENERATED,
        SecurityEventType.TPR_TOKEN_USED,
    )

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        agent_id=agent_id,
        client_ip=client_ip,
        success=success,
        error_message=error_message,
        details={"token_id": token_id},
    )


# --- Policy Violations ---


async def log_policy_violation(
    event_type: SecurityEventType,
    message: str,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Log policy violation event."""
    service = get_security_audit_service()

    return await service.log_event(
        event_type,
        message,
        agent_id=agent_id,
        user_id=user_id,
        client_ip=client_ip,
        success=False,
        details=details or {},
    )


# --- WebSocket Events ---


async def log_websocket_event(
    event_type: SecurityEventType,
    user_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    """Log WebSocket connection event."""
    service = get_security_audit_service()

    messages = {
        SecurityEventType.WEBSOCKET_CONNECTED: f"WebSocket connected: {user_id}",
        SecurityEventType.WEBSOCKET_DISCONNECTED: f"WebSocket disconnected: {user_id}",
        SecurityEventType.WEBSOCKET_AUTH_FAILED: f"WebSocket auth failed: {error_message}",
    }

    success = event_type != SecurityEventType.WEBSOCKET_AUTH_FAILED

    return await service.log_event(
        event_type,
        messages.get(event_type, event_type.value),
        user_id=user_id,
        client_ip=client_ip,
        success=success,
        error_message=error_message,
    )
