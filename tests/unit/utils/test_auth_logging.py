"""
Unit tests for authentication logging utilities.

Tests the auth_logging module which provides authentication event logging functionality.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from src.arcp.utils.auth_logging import (
    log_auth_event,
    log_login_attempt,
    log_security_event,
    log_session_event,
)


@pytest.mark.unit
class TestAuthLogging:
    """Test authentication logging functionality."""

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_basic(self, mock_add_log_entry):
        """Test basic auth event logging."""
        await log_auth_event(
            level="INFO",
            event_type="test_event",
            message="Test authentication event",
            user_id="test_user",
            agent_id="test_agent",
            client_ip="192.168.1.1",
        )

        mock_add_log_entry.assert_called_once_with(
            "INFO",
            "Test authentication event",
            "auth",
            event_type="test_event",
            user_id="test_user",
            agent_id="test_agent",
            client_ip="192.168.1.1",
        )

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_with_request(self, mock_add_log_entry):
        """Test auth event logging with FastAPI request object."""
        # Mock request object
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "10.0.0.1"

        await log_auth_event(
            level="WARNING",
            event_type="login_attempt",
            message="Failed login attempt",
            request=mock_request,
        )

        mock_add_log_entry.assert_called_once_with(
            "WARNING",
            "Failed login attempt",
            "auth",
            event_type="login_attempt",
        )

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_no_client(self, mock_add_log_entry):
        """Test auth event logging when request has no client."""
        mock_request = MagicMock(spec=Request)
        mock_request.client = None

        await log_auth_event(
            level="INFO",
            event_type="test_event",
            message="Test message",
            request=mock_request,
        )

        mock_add_log_entry.assert_called_once_with(
            "INFO", "Test message", "auth", event_type="test_event"
        )

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_with_kwargs(self, mock_add_log_entry):
        """Test auth event logging with additional keyword arguments."""
        await log_auth_event(
            level="ERROR",
            event_type="security_violation",
            message="Security violation detected",
            user_id="suspicious_user",
            violation_type="brute_force",
            attempt_count=5,
            blocked=True,
        )

        mock_add_log_entry.assert_called_once_with(
            "ERROR",
            "Security violation detected",
            "auth",
            event_type="security_violation",
            user_id="suspicious_user",
            violation_type="brute_force",
            attempt_count=5,
            blocked=True,
        )

    async def test_log_login_attempt(self):
        """Test login attempt logging."""
        with patch("src.arcp.api.dashboard.add_log_entry") as mock_add_log_entry:
            mock_request = MagicMock(spec=Request)
            mock_request.client.host = "192.168.1.1"

            await log_login_attempt(
                success=True, username="test_user", request=mock_request
            )

            mock_add_log_entry.assert_called_once_with(
                "INFO",
                "Admin login successful: test_user",
                "auth",
                event_type="admin_login_success",
                user_id="test_user",
            )

    async def test_log_session_event(self):
        """Test session event logging."""
        with patch("src.arcp.api.dashboard.add_log_entry") as mock_add_log_entry:
            mock_request = MagicMock(spec=Request)

            await log_session_event(
                event_type="session_created",
                user_id="admin",
                request=mock_request,
            )

            mock_add_log_entry.assert_called_once_with(
                "INFO",
                "Session event (session_created): admin",
                "auth",
                event_type="session_created",
                user_id="admin",
            )

    async def test_log_security_event(self):
        """Test security event logging."""
        with patch("src.arcp.api.dashboard.add_log_entry") as mock_add_log_entry:
            mock_request = MagicMock(spec=Request)

            await log_security_event(
                event_type="rate_limit_exceeded",
                message="Rate limit exceeded for user",
                severity="WARNING",
                user_id="suspicious_user",
                request=mock_request,
            )

            mock_add_log_entry.assert_called_once_with(
                "WARNING",
                "Rate limit exceeded for user",
                "auth",
                event_type="rate_limit_exceeded",
                user_id="suspicious_user",
            )

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_import_error(self, mock_add_log_entry):
        """Test auth event logging handles import errors gracefully."""
        mock_add_log_entry.side_effect = ImportError("Cannot import dashboard")

        # Should not raise exception
        await log_auth_event(
            level="INFO", event_type="test_event", message="Test message"
        )

    @patch("src.arcp.api.dashboard.add_log_entry")
    async def test_log_auth_event_general_exception(self, mock_add_log_entry):
        """Test auth event logging handles general exceptions gracefully."""
        mock_add_log_entry.side_effect = Exception("Unexpected error")

        # Should not raise exception
        await log_auth_event(
            level="ERROR", event_type="test_event", message="Test message"
        )

    async def test_log_auth_event_no_parameters(self):
        """Test auth event logging with minimal parameters."""
        with patch("src.arcp.api.dashboard.add_log_entry") as mock_add_log_entry:
            await log_auth_event(
                level="INFO",
                event_type="minimal_event",
                message="Minimal test message",
            )

            mock_add_log_entry.assert_called_once_with(
                "INFO",
                "Minimal test message",
                "auth",
                event_type="minimal_event",
            )
