"""
Comprehensive unit tests for security audit service.

Tests the security_audit module which provides security event auditing,
logging to multiple sinks (app logs, Redis, SIEM), and convenience functions
for common security events.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.arcp.utils.security_audit import (
    EVENT_SEVERITY_MAP,
    SecurityAuditService,
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
    get_security_audit_service,
    log_admin_login,
    log_agent_event,
    log_attestation_event,
    log_authentication_failure,
    log_authentication_success,
    log_dpop_event,
    log_key_event,
    log_mtls_event,
    log_policy_violation,
    log_security_event,
    log_session_event,
    log_tpr_event,
    log_websocket_event,
)


@pytest.mark.unit
class TestSecurityEventType:
    """Test SecurityEventType enum."""

    def test_event_type_values(self):
        """Test that event types have correct string values."""
        assert SecurityEventType.AUTHENTICATION_SUCCESS.value == "auth.success"
        assert SecurityEventType.AUTHENTICATION_FAILURE.value == "auth.failure"
        assert SecurityEventType.DPOP_PROOF_VALID.value == "dpop.proof_valid"
        assert SecurityEventType.MTLS_CERT_VALID.value == "mtls.cert_valid"
        assert SecurityEventType.JWKS_KEY_ROTATED.value == "jwks.key_rotated"
        assert SecurityEventType.AGENT_REGISTERED.value == "agent.registered"

    def test_all_event_types_defined(self):
        """Test that all expected event categories exist."""
        event_types = [e.value for e in SecurityEventType]

        # Check for authentication events
        assert any("auth." in e for e in event_types)

        # Check for DPoP events
        assert any("dpop." in e for e in event_types)

        # Check for mTLS events
        assert any("mtls." in e for e in event_types)

        # Check for attestation events
        assert any("attestation." in e for e in event_types)

        # Check for agent events
        assert any("agent." in e for e in event_types)


@pytest.mark.unit
class TestSecurityEventSeverity:
    """Test SecurityEventSeverity enum."""

    def test_severity_levels(self):
        """Test severity level values."""
        assert SecurityEventSeverity.DEBUG.value == "debug"
        assert SecurityEventSeverity.INFO.value == "info"
        assert SecurityEventSeverity.WARNING.value == "warning"
        assert SecurityEventSeverity.ERROR.value == "error"
        assert SecurityEventSeverity.CRITICAL.value == "critical"


@pytest.mark.unit
class TestSecurityEvent:
    """Test SecurityEvent dataclass."""

    def test_event_creation(self):
        """Test creating a security event."""
        event = SecurityEvent(
            event_id="evt_123",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            agent_id="agent-001",
            user_id="user-001",
            client_ip="192.168.1.1",
            message="Test event",
            success=True,
        )

        assert event.event_id == "evt_123"
        assert event.event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert event.severity == SecurityEventSeverity.INFO
        assert event.agent_id == "agent-001"
        assert event.user_id == "user-001"
        assert event.client_ip == "192.168.1.1"
        assert event.message == "Test event"
        assert event.success is True

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        timestamp = datetime.utcnow()
        event = SecurityEvent(
            event_id="evt_456",
            event_type=SecurityEventType.TOKEN_ISSUED,
            severity=SecurityEventSeverity.INFO,
            timestamp=timestamp,
            agent_id="agent-002",
            details={"token_type": "access", "expires_in": 3600},
            message="Token issued",
        )

        event_dict = event.to_dict()

        assert event_dict["event_id"] == "evt_456"
        assert event_dict["event_type"] == "token.issued"
        assert event_dict["severity"] == "info"
        assert event_dict["timestamp"] == timestamp.isoformat()
        assert event_dict["agent_id"] == "agent-002"
        assert event_dict["details"] == {"token_type": "access", "expires_in": 3600}
        assert event_dict["message"] == "Token issued"

    def test_event_to_json(self):
        """Test converting event to JSON string."""
        timestamp = datetime.utcnow()
        event = SecurityEvent(
            event_id="evt_789",
            event_type=SecurityEventType.DPOP_PROOF_VALID,
            severity=SecurityEventSeverity.DEBUG,
            timestamp=timestamp,
            message="DPoP proof validated",
        )

        json_str = event.to_json()
        parsed = json.loads(json_str)

        assert parsed["event_id"] == "evt_789"
        assert parsed["event_type"] == "dpop.proof_valid"
        assert parsed["severity"] == "debug"

    def test_event_with_error_details(self):
        """Test event with error information."""
        event = SecurityEvent(
            event_id="evt_error",
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=SecurityEventSeverity.WARNING,
            timestamp=datetime.utcnow(),
            message="Authentication failed",
            success=False,
            error_code="INVALID_CREDENTIALS",
            error_message="Invalid username or password",
        )

        assert event.success is False
        assert event.error_code == "INVALID_CREDENTIALS"
        assert event.error_message == "Invalid username or password"

        event_dict = event.to_dict()
        assert event_dict["error_code"] == "INVALID_CREDENTIALS"
        assert event_dict["error_message"] == "Invalid username or password"


@pytest.mark.unit
class TestEventSeverityMap:
    """Test EVENT_SEVERITY_MAP configuration."""

    def test_critical_events_mapped(self):
        """Test critical severity events."""
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.SUSPICIOUS_ACTIVITY]
            == SecurityEventSeverity.CRITICAL
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.JWKS_KEY_REVOKED]
            == SecurityEventSeverity.CRITICAL
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.JWKS_REVOKED_KEY_USED]
            == SecurityEventSeverity.CRITICAL
        )

    def test_error_events_mapped(self):
        """Test error severity events."""
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.DPOP_REPLAY_DETECTED]
            == SecurityEventSeverity.ERROR
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.MTLS_CERT_REVOKED]
            == SecurityEventSeverity.ERROR
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.ACCESS_DENIED]
            == SecurityEventSeverity.ERROR
        )

    def test_warning_events_mapped(self):
        """Test warning severity events."""
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.AUTHENTICATION_FAILURE]
            == SecurityEventSeverity.WARNING
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.RATE_LIMIT_EXCEEDED]
            == SecurityEventSeverity.WARNING
        )

    def test_info_events_mapped(self):
        """Test info severity events."""
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.AUTHENTICATION_SUCCESS]
            == SecurityEventSeverity.INFO
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.AGENT_REGISTERED]
            == SecurityEventSeverity.INFO
        )

    def test_debug_events_mapped(self):
        """Test debug severity events."""
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.DPOP_PROOF_VALID]
            == SecurityEventSeverity.DEBUG
        )
        assert (
            EVENT_SEVERITY_MAP[SecurityEventType.AGENT_HEARTBEAT]
            == SecurityEventSeverity.DEBUG
        )


@pytest.mark.unit
class TestSecurityAuditService:
    """Test SecurityAuditService class."""

    @pytest.fixture
    def audit_service(self):
        """Create audit service instance for testing."""
        with patch("src.arcp.utils.security_audit.config") as mock_config:
            mock_config.SECURITY_AUDIT_ENABLED = True
            mock_config.SECURITY_AUDIT_REDIS = True
            mock_config.SECURITY_AUDIT_RETENTION_HOURS = 168
            mock_config.SECURITY_AUDIT_SIEM_URL = None
            mock_config.SECURITY_AUDIT_SIEM_TOKEN = None
            service = SecurityAuditService()
            yield service

    def test_service_initialization(self, audit_service):
        """Test service initialization with config."""
        assert audit_service.enabled is True
        assert audit_service.redis_enabled is True
        assert audit_service.retention_hours == 168

    def test_service_disabled(self):
        """Test service when auditing is disabled."""
        with patch("src.arcp.utils.security_audit.config") as mock_config:
            mock_config.SECURITY_AUDIT_ENABLED = False
            service = SecurityAuditService()
            assert service.enabled is False

    def test_generate_event_id(self, audit_service):
        """Test event ID generation."""
        event_id1 = audit_service._generate_event_id()
        event_id2 = audit_service._generate_event_id()

        # Event IDs should be unique
        assert event_id1 != event_id2

        # Event IDs should have correct format
        assert event_id1.startswith("evt_")
        assert event_id2.startswith("evt_")

    @pytest.mark.asyncio
    async def test_log_event_basic(self, audit_service):
        """Test basic event logging."""
        with patch.object(audit_service, "_log_to_logger") as mock_logger:
            event_id = await audit_service.log_event(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                message="Test authentication",
                agent_id="test-agent",
                client_ip="192.168.1.1",
            )

            assert event_id is not None
            assert event_id.startswith("evt_")
            mock_logger.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_disabled(self):
        """Test that logging does nothing when disabled."""
        with patch("src.arcp.utils.security_audit.config") as mock_config:
            mock_config.SECURITY_AUDIT_ENABLED = False
            service = SecurityAuditService()

            event_id = await service.log_event(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                message="Test event",
            )

            assert event_id is None

    @pytest.mark.asyncio
    async def test_log_event_with_details(self, audit_service):
        """Test logging event with additional details."""
        with patch.object(audit_service, "_log_to_logger"):
            event_id = await audit_service.log_event(
                SecurityEventType.TOKEN_ISSUED,
                message="Token issued",
                agent_id="agent-001",
                details={
                    "token_type": "access",
                    "expires_in": 3600,
                    "scopes": ["read", "write"],
                },
            )

            assert event_id is not None

    @pytest.mark.asyncio
    async def test_log_event_with_error(self, audit_service):
        """Test logging event with error information."""
        with patch.object(audit_service, "_log_to_logger"):
            event_id = await audit_service.log_event(
                SecurityEventType.AUTHENTICATION_FAILURE,
                message="Authentication failed",
                agent_id="agent-002",
                success=False,
                error_code="INVALID_TOKEN",
                error_message="Token has expired",
            )

            assert event_id is not None

    @pytest.mark.asyncio
    async def test_log_event_auto_severity(self, audit_service):
        """Test that severity is auto-assigned from EVENT_SEVERITY_MAP."""
        with patch.object(audit_service, "_log_to_logger") as mock_logger:
            await audit_service.log_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                message="Suspicious activity detected",
            )

            # Should use CRITICAL severity from map
            call_args = mock_logger.call_args[0][0]
            assert call_args.severity == SecurityEventSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_log_event_override_severity(self, audit_service):
        """Test overriding auto-assigned severity."""
        with patch.object(audit_service, "_log_to_logger") as mock_logger:
            await audit_service.log_event(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                message="Test event",
                severity=SecurityEventSeverity.WARNING,
            )

            # Should use provided severity
            call_args = mock_logger.call_args[0][0]
            assert call_args.severity == SecurityEventSeverity.WARNING

    def test_log_to_logger_info(self, audit_service):
        """Test logging to logger at INFO level."""
        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test info event",
            agent_id="agent-001",
        )

        with patch("src.arcp.utils.security_audit.logger") as mock_logger:
            audit_service._log_to_logger(event)
            mock_logger.info.assert_called_once()

    def test_log_to_logger_warning(self, audit_service):
        """Test logging to logger at WARNING level."""
        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=SecurityEventSeverity.WARNING,
            timestamp=datetime.utcnow(),
            message="Test warning event",
        )

        with patch("src.arcp.utils.security_audit.logger") as mock_logger:
            audit_service._log_to_logger(event)
            mock_logger.warning.assert_called_once()

    def test_log_to_logger_error(self, audit_service):
        """Test logging to logger at ERROR level."""
        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.ACCESS_DENIED,
            severity=SecurityEventSeverity.ERROR,
            timestamp=datetime.utcnow(),
            message="Test error event",
            error_code="FORBIDDEN",
        )

        with patch("src.arcp.utils.security_audit.logger") as mock_logger:
            audit_service._log_to_logger(event)
            mock_logger.error.assert_called_once()

    def test_log_to_logger_critical(self, audit_service):
        """Test logging to logger at CRITICAL level."""
        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            severity=SecurityEventSeverity.CRITICAL,
            timestamp=datetime.utcnow(),
            message="Test critical event",
        )

        with patch("src.arcp.utils.security_audit.logger") as mock_logger:
            audit_service._log_to_logger(event)
            mock_logger.critical.assert_called_once()

    def test_log_to_logger_debug(self, audit_service):
        """Test logging to logger at DEBUG level."""
        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AGENT_HEARTBEAT,
            severity=SecurityEventSeverity.DEBUG,
            timestamp=datetime.utcnow(),
            message="Test debug event",
        )

        with patch("src.arcp.utils.security_audit.logger") as mock_logger:
            audit_service._log_to_logger(event)
            mock_logger.debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_in_redis_success(self, audit_service):
        """Test successful Redis storage."""
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "1234-0"
        mock_redis.incr.return_value = 1
        mock_redis.lpush.return_value = 1
        mock_redis.ltrim.return_value = True
        mock_redis.expire.return_value = True
        audit_service._redis = mock_redis

        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test event",
            agent_id="agent-001",
        )

        # Mock asyncio run_in_executor to execute synchronously
        async def mock_run_in_executor(executor, func):
            return func()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = mock_run_in_executor

            await audit_service._store_in_redis(event)

            # Verify Redis operations were called
            assert mock_redis.xadd.called
            assert mock_redis.incr.called

    @pytest.mark.asyncio
    async def test_store_in_redis_no_client(self, audit_service):
        """Test Redis storage when no Redis client available."""
        audit_service._redis = None

        with patch.object(audit_service, "_get_redis", return_value=None):
            event = SecurityEvent(
                event_id="evt_test",
                event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
                severity=SecurityEventSeverity.INFO,
                timestamp=datetime.utcnow(),
                message="Test event",
            )

            # Should not raise exception
            await audit_service._store_in_redis(event)

    @pytest.mark.asyncio
    async def test_store_in_redis_error_handling(self, audit_service):
        """Test Redis storage error handling."""
        mock_redis = MagicMock()
        mock_redis.xadd.side_effect = Exception("Redis error")
        audit_service._redis = mock_redis

        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test event",
        )

        # Mock asyncio run_in_executor to execute synchronously
        async def mock_run_in_executor(executor, func):
            return func()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = mock_run_in_executor

            # Should not raise exception, just log warning
            await audit_service._store_in_redis(event)

    @pytest.mark.asyncio
    async def test_send_to_siem_success(self, audit_service):
        """Test sending event to SIEM."""
        audit_service.siem_url = "https://siem.example.com/events"
        audit_service.siem_token = "test-token"

        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test event",
        )

        mock_response = AsyncMock()
        mock_response.status = 200

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session

            await audit_service._send_to_siem(event)

            # Verify POST was called with correct data
            assert mock_session.post.called

    @pytest.mark.asyncio
    async def test_send_to_siem_no_url(self, audit_service):
        """Test SIEM send when no URL configured."""
        audit_service.siem_url = None

        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test event",
        )

        # Should return early without error
        await audit_service._send_to_siem(event)

    @pytest.mark.asyncio
    async def test_send_to_siem_error(self, audit_service):
        """Test SIEM send error handling."""
        audit_service.siem_url = "https://siem.example.com/events"

        event = SecurityEvent(
            event_id="evt_test",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=SecurityEventSeverity.INFO,
            timestamp=datetime.utcnow(),
            message="Test event",
        )

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session_class.side_effect = Exception("Network error")

            # Should not raise exception
            await audit_service._send_to_siem(event)

    @pytest.mark.asyncio
    async def test_get_recent_events_from_stream(self, audit_service):
        """Test getting recent events from Redis stream."""
        mock_redis = MagicMock()
        mock_redis.xrevrange.return_value = [
            ("1234-0", {"event_type": "auth.success", "message": "Test 1"}),
            ("1235-0", {"event_type": "auth.failure", "message": "Test 2"}),
        ]
        audit_service._redis = mock_redis

        # Mock asyncio run_in_executor to execute synchronously
        async def mock_run_in_executor(executor, func):
            return func()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = mock_run_in_executor

            events = await audit_service.get_recent_events(count=10)

            assert len(events) == 2
            assert events[0]["event_type"] == "auth.success"
            assert events[1]["event_type"] == "auth.failure"

    @pytest.mark.asyncio
    async def test_get_recent_events_by_agent(self, audit_service):
        """Test getting recent events for specific agent."""
        mock_redis = MagicMock()
        event_json = json.dumps({"event_type": "auth.success", "agent_id": "agent-001"})
        mock_redis.lrange.return_value = [event_json.encode()]
        audit_service._redis = mock_redis

        # Mock asyncio run_in_executor to execute synchronously
        async def mock_run_in_executor(executor, func):
            return func()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = mock_run_in_executor

            events = await audit_service.get_recent_events(agent_id="agent-001")

            assert len(events) == 1
            assert events[0]["agent_id"] == "agent-001"

    @pytest.mark.asyncio
    async def test_get_recent_events_no_redis(self, audit_service):
        """Test getting events when Redis unavailable."""
        audit_service._redis = None

        with patch.object(audit_service, "_get_redis", return_value=None):
            events = await audit_service.get_recent_events()
            assert events == []

    @pytest.mark.asyncio
    async def test_get_event_counts(self, audit_service):
        """Test getting event counts by type."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: b"5" if "auth.success" in key else None
        audit_service._redis = mock_redis

        # Mock asyncio run_in_executor to execute synchronously
        async def mock_run_in_executor(executor, func):
            return func()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = mock_run_in_executor

            counts = await audit_service.get_event_counts()

            # Should have at least the auth.success count
            assert "auth.success" in counts
            assert counts["auth.success"] == 5


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test convenience functions for common events."""

    @pytest.mark.asyncio
    async def test_log_authentication_success(self):
        """Test log_authentication_success function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_123")
            mock_get_service.return_value = mock_service

            event_id = await log_authentication_success(
                agent_id="agent-001",
                method="dpop",
                client_ip="192.168.1.1",
                details={"jkt": "abc123"},
            )

            assert event_id == "evt_123"
            mock_service.log_event.assert_called_once()
            call_args = mock_service.log_event.call_args
            assert call_args[0][0] == SecurityEventType.AUTHENTICATION_SUCCESS

    @pytest.mark.asyncio
    async def test_log_authentication_failure(self):
        """Test log_authentication_failure function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_456")
            mock_get_service.return_value = mock_service

            event_id = await log_authentication_failure(
                agent_id="agent-002",
                method="mtls",
                reason="Invalid certificate",
                client_ip="10.0.0.1",
            )

            assert event_id == "evt_456"
            mock_service.log_event.assert_called_once()
            call_args = mock_service.log_event.call_args
            assert call_args[0][0] == SecurityEventType.AUTHENTICATION_FAILURE

    @pytest.mark.asyncio
    async def test_log_key_event(self):
        """Test log_key_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_789")
            mock_get_service.return_value = mock_service

            event_id = await log_key_event(
                SecurityEventType.JWKS_KEY_ROTATED,
                kid="key-001",
                reason="Scheduled rotation",
            )

            assert event_id == "evt_789"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_admin_login_success(self):
        """Test log_admin_login for successful login."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_admin")
            mock_get_service.return_value = mock_service

            event_id = await log_admin_login(
                username="admin",
                success=True,
                client_ip="192.168.1.100",
            )

            assert event_id == "evt_admin"
            call_args = mock_service.log_event.call_args
            assert call_args[0][0] == SecurityEventType.ADMIN_LOGIN_SUCCESS

    @pytest.mark.asyncio
    async def test_log_admin_login_failure(self):
        """Test log_admin_login for failed login."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_fail")
            mock_get_service.return_value = mock_service

            event_id = await log_admin_login(
                username="hacker",
                success=False,
                client_ip="1.2.3.4",
                error_message="Invalid credentials",
            )

            assert event_id == "evt_fail"
            call_args = mock_service.log_event.call_args
            assert call_args[0][0] == SecurityEventType.ADMIN_LOGIN_FAILURE

    @pytest.mark.asyncio
    async def test_log_session_event(self):
        """Test log_session_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_session")
            mock_get_service.return_value = mock_service

            event_id = await log_session_event(
                SecurityEventType.PIN_SET,
                user_id="admin",
                session_id="sess-123",
                client_ip="192.168.1.1",
            )

            assert event_id == "evt_session"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_dpop_event(self):
        """Test log_dpop_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_dpop")
            mock_get_service.return_value = mock_service

            event_id = await log_dpop_event(
                SecurityEventType.DPOP_PROOF_VALID,
                jti="jti-123",
                jkt="jkt-abc123def456",
                agent_id="agent-001",
            )

            assert event_id == "evt_dpop"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_mtls_event(self):
        """Test log_mtls_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_mtls")
            mock_get_service.return_value = mock_service

            event_id = await log_mtls_event(
                SecurityEventType.MTLS_CERT_VALID,
                cert_subject="CN=agent-001",
                spki_hash="sha256:abc123",
                agent_id="agent-001",
            )

            assert event_id == "evt_mtls"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_attestation_event(self):
        """Test log_attestation_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_attest")
            mock_get_service.return_value = mock_service

            event_id = await log_attestation_event(
                SecurityEventType.ATTESTATION_SUCCESS,
                agent_id="agent-001",
                attestation_type="tpm",
                challenge_id="challenge-123",
            )

            assert event_id == "evt_attest"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_agent_event(self):
        """Test log_agent_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_agent")
            mock_get_service.return_value = mock_service

            event_id = await log_agent_event(
                SecurityEventType.AGENT_REGISTERED,
                agent_id="agent-001",
                agent_type="monitor",
                client_ip="192.168.1.1",
            )

            assert event_id == "evt_agent"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_tpr_event(self):
        """Test log_tpr_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_tpr")
            mock_get_service.return_value = mock_service

            event_id = await log_tpr_event(
                SecurityEventType.TPR_TOKEN_GENERATED,
                token_id="tpr-123",
                agent_id="agent-001",
            )

            assert event_id == "evt_tpr"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_policy_violation(self):
        """Test log_policy_violation function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_policy")
            mock_get_service.return_value = mock_service

            event_id = await log_policy_violation(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                message="Rate limit exceeded",
                agent_id="agent-001",
                client_ip="192.168.1.1",
            )

            assert event_id == "evt_policy"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_websocket_event(self):
        """Test log_websocket_event function."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_ws")
            mock_get_service.return_value = mock_service

            event_id = await log_websocket_event(
                SecurityEventType.WEBSOCKET_CONNECTED,
                user_id="admin",
                client_ip="192.168.1.1",
            )

            assert event_id == "evt_ws"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_security_event_with_valid_type(self):
        """Test log_security_event with valid event type."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_sec")
            mock_get_service.return_value = mock_service

            event_id = await log_security_event(
                event_type="auth.success",
                message="Security event",
                severity="INFO",
            )

            assert event_id == "evt_sec"
            mock_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_security_event_with_invalid_type(self):
        """Test log_security_event with invalid event type (fallback behavior)."""
        with patch(
            "src.arcp.utils.security_audit.get_security_audit_service"
        ) as mock_get_service:
            mock_service = AsyncMock()
            mock_service.log_event = AsyncMock(return_value="evt_invalid")
            mock_get_service.return_value = mock_service

            # Should use INVALID_REQUEST as fallback for unknown event types
            event_id = await log_security_event(
                event_type="unknown.event.type",
                message="Unknown event",
                severity="WARNING",
            )

            assert event_id == "evt_invalid"
            call_args = mock_service.log_event.call_args
            # Should fallback to INVALID_REQUEST
            assert call_args[0][0] == SecurityEventType.INVALID_REQUEST


@pytest.mark.unit
class TestSingleton:
    """Test singleton pattern for audit service."""

    def test_get_security_audit_service_singleton(self):
        """Test that get_security_audit_service returns same instance."""
        # Reset singleton for test
        import src.arcp.utils.security_audit as audit_module

        audit_module._audit_service = None

        service1 = get_security_audit_service()
        service2 = get_security_audit_service()

        assert service1 is service2


@pytest.mark.unit
class TestRedisDataTypes:
    """Test Redis data type handling."""

    @pytest.mark.asyncio
    async def test_store_in_redis_bool_conversion(self):
        """Test that booleans are converted to strings for Redis."""
        with patch("src.arcp.utils.security_audit.config") as mock_config:
            mock_config.SECURITY_AUDIT_ENABLED = True
            mock_config.SECURITY_AUDIT_REDIS = True
            service = SecurityAuditService()

            mock_redis = MagicMock()
            service._redis = mock_redis

            event = SecurityEvent(
                event_id="evt_test",
                event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
                severity=SecurityEventSeverity.INFO,
                timestamp=datetime.utcnow(),
                message="Test event",
                success=True,  # Boolean value
            )

            # Capture the data being sent to Redis
            captured_data = {}

            def capture_xadd(stream, data, **kwargs):
                captured_data.update(data)
                return "1234-0"

            mock_redis.xadd = capture_xadd

            # Mock asyncio run_in_executor to execute synchronously
            async def mock_run_in_executor(executor, func):
                return func()

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_run_in_executor

                await service._store_in_redis(event)

                # Verify boolean is converted to string
                assert captured_data.get("success") == "true"

    @pytest.mark.asyncio
    async def test_store_in_redis_dict_conversion(self):
        """Test that dicts/lists are JSON-serialized for Redis."""
        with patch("src.arcp.utils.security_audit.config") as mock_config:
            mock_config.SECURITY_AUDIT_ENABLED = True
            mock_config.SECURITY_AUDIT_REDIS = True
            service = SecurityAuditService()

            mock_redis = MagicMock()
            service._redis = mock_redis

            event = SecurityEvent(
                event_id="evt_test",
                event_type=SecurityEventType.TOKEN_ISSUED,
                severity=SecurityEventSeverity.INFO,
                timestamp=datetime.utcnow(),
                message="Test event",
                details={"key": "value", "count": 42},  # Dict
            )

            captured_data = {}

            def capture_xadd(stream, data, **kwargs):
                captured_data.update(data)
                return "1234-0"

            mock_redis.xadd = capture_xadd

            # Mock asyncio run_in_executor to execute synchronously
            async def mock_run_in_executor(executor, func):
                return func()

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_run_in_executor

                await service._store_in_redis(event)

                # Verify dict is JSON serialized
                details_json = captured_data.get("details")
                assert isinstance(details_json, str)
                parsed = json.loads(details_json)
                assert parsed == {"key": "value", "count": 42}
