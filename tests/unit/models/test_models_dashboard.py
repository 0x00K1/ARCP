"""
Unit tests for ARCP dashboard models.
"""

import pytest
from pydantic import ValidationError

from src.arcp.models.dashboard import DashboardFrame, DashboardLogRequest


@pytest.mark.unit
class TestDashboardFrame:
    """Test cases for DashboardFrame model."""

    def test_dashboard_frame_basic(self):
        """Test basic dashboard frame creation."""
        frame = DashboardFrame(
            type="agent_update",
            timestamp="2023-01-01T12:00:00Z",
            data={"agent_id": "test-agent", "status": "online"},
        )

        assert frame.type == "agent_update"
        assert frame.timestamp == "2023-01-01T12:00:00Z"
        assert frame.data == {"agent_id": "test-agent", "status": "online"}

    def test_dashboard_frame_complex_data(self):
        """Test dashboard frame with complex data structure."""
        complex_data = {
            "agents": [
                {"id": "agent1", "status": "online", "metrics": {"cpu": 45.2}},
                {"id": "agent2", "status": "offline", "metrics": {"cpu": 0.0}},
            ],
            "summary": {"total": 2, "online": 1, "offline": 1},
            "metadata": {
                "timestamp": "2023-01-01T12:00:00Z",
                "source": "registry",
            },
        }

        frame = DashboardFrame(
            type="system_status",
            timestamp="2023-01-01T12:00:00Z",
            data=complex_data,
        )

        assert frame.type == "system_status"
        assert frame.data["agents"][0]["id"] == "agent1"
        assert frame.data["summary"]["total"] == 2

    def test_type_validation_strips_whitespace(self):
        """Test type validation strips whitespace."""
        frame = DashboardFrame(
            type="  agent_update  ", timestamp="2023-01-01T12:00:00Z", data={}
        )

        assert frame.type == "agent_update"

    def test_type_validation_empty_fails(self):
        """Test type validation fails for empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardFrame(type="", timestamp="2023-01-01T12:00:00Z", data={})

        assert "type must be a non-empty string" in str(exc_info.value)

    def test_type_validation_whitespace_only_fails(self):
        """Test type validation fails for whitespace-only strings."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardFrame(type="   ", timestamp="2023-01-01T12:00:00Z", data={})

        assert "type must be a non-empty string" in str(exc_info.value)

    def test_type_validation_non_string_fails(self):
        """Test type validation fails for non-string types."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardFrame(type=123, timestamp="2023-01-01T12:00:00Z", data={})

        assert "Input should be a valid string" in str(exc_info.value)

    def test_timestamp_validation_iso8601_formats(self):
        """Test timestamp validation accepts various ISO 8601 formats."""
        valid_timestamps = [
            "2023-01-01T12:00:00Z",
            "2023-01-01T12:00:00+00:00",
            "2023-01-01T12:00:00-05:00",
            "2023-01-01T12:00:00.123Z",
            "2023-01-01T12:00:00.123456+02:00",
            "2023-12-31T23:59:59Z",
        ]

        for timestamp in valid_timestamps:
            frame = DashboardFrame(type="test", timestamp=timestamp, data={})
            assert frame.timestamp == timestamp

    def test_timestamp_validation_invalid_formats(self):
        """Test timestamp validation rejects invalid formats."""
        # Note: Some timestamp formats that appear invalid may actually be accepted by
        # Python's datetime.fromisoformat(). Only testing the most obviously invalid ones.
        invalid_timestamps = [
            "not-a-timestamp",
            "",
            # "2023-01-01" is actually valid ISO format (date only)
        ]

        for timestamp in invalid_timestamps:
            with pytest.raises(ValidationError) as exc_info:
                DashboardFrame(type="test", timestamp=timestamp, data={})
            # Different error messages for different invalid types
            error_msg = str(exc_info.value)
            assert (
                "timestamp must be ISO 8601 format" in error_msg
                or "timestamp must be a non-empty ISO 8601 string" in error_msg
            )

    def test_timestamp_validation_empty_fails(self):
        """Test timestamp validation fails for empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardFrame(type="test", timestamp="", data={})

        assert "timestamp must be a non-empty ISO 8601 string" in str(exc_info.value)

    def test_timestamp_validation_non_string_fails(self):
        """Test timestamp validation fails for non-string types."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardFrame(type="test", timestamp=1672574400, data={})  # Unix timestamp

        assert "Input should be a valid string" in str(exc_info.value)

    def test_data_validation_basic(self):
        """Test data validation with basic dictionary."""
        frame = DashboardFrame(
            type="test",
            timestamp="2023-01-01T12:00:00Z",
            data={"key": "value", "number": 42, "nested": {"inner": "data"}},
        )

        assert frame.data["key"] == "value"
        assert frame.data["number"] == 42
        assert frame.data["nested"]["inner"] == "data"

    def test_data_validation_empty_dict(self):
        """Test data validation accepts empty dictionary."""
        frame = DashboardFrame(type="test", timestamp="2023-01-01T12:00:00Z", data={})

        assert frame.data == {}

    def test_data_validation_non_dict_fails(self):
        """Test data validation fails for non-dictionary types."""
        invalid_data_types = ["string", 123, ["list", "items"], None, True]

        for invalid_data in invalid_data_types:
            with pytest.raises(ValidationError) as exc_info:
                DashboardFrame(
                    type="test",
                    timestamp="2023-01-01T12:00:00Z",
                    data=invalid_data,
                )
            assert "Input should be a valid dictionary" in str(exc_info.value)


@pytest.mark.unit
class TestDashboardLogRequest:
    """Test cases for DashboardLogRequest model."""

    def test_dashboard_log_request_basic(self):
        """Test basic dashboard log request creation."""
        log_request = DashboardLogRequest(
            level="INFO",
            message="Agent registered successfully",
            timestamp="2023-01-01T12:00:00Z",
        )

        assert log_request.level == "INFO"
        assert log_request.message == "Agent registered successfully"
        assert log_request.timestamp == "2023-01-01T12:00:00Z"

    def test_level_validation_canonical_levels(self):
        """Test level validation accepts canonical levels."""
        canonical_levels = ["INFO", "SUCS", "WARN", "CRIT", "ERR"]

        for level in canonical_levels:
            log_request = DashboardLogRequest(
                level=level,
                message="Test message",
                timestamp="2023-01-01T12:00:00Z",
            )
            assert log_request.level == level

    def test_level_validation_case_conversion(self):
        """Test level validation converts to uppercase."""
        lowercase_levels = ["info", "sucs", "warn", "crit", "err"]
        expected_levels = ["INFO", "SUCS", "WARN", "CRIT", "ERR"]

        for lowercase, expected in zip(lowercase_levels, expected_levels):
            log_request = DashboardLogRequest(
                level=lowercase,
                message="Test message",
                timestamp="2023-01-01T12:00:00Z",
            )
            assert log_request.level == expected

    def test_level_validation_mixed_case(self):
        """Test level validation with mixed case."""
        mixed_case_levels = ["Info", "SUCS", "warn", "CrIt", "ErR"]
        expected_levels = ["INFO", "SUCS", "WARN", "CRIT", "ERR"]

        for mixed, expected in zip(mixed_case_levels, expected_levels):
            log_request = DashboardLogRequest(
                level=mixed,
                message="Test message",
                timestamp="2023-01-01T12:00:00Z",
            )
            assert log_request.level == expected

    def test_level_validation_strips_whitespace(self):
        """Test level validation strips whitespace."""
        log_request = DashboardLogRequest(
            level="  INFO  ",
            message="Test message",
            timestamp="2023-01-01T12:00:00Z",
        )

        assert log_request.level == "INFO"

    def test_level_validation_invalid_levels(self):
        """Test level validation rejects invalid levels."""
        # NOTE: Common aliases like ERROR->ERR, SUCCESS->SUCS are mapped automatically
        # Only truly invalid levels should raise ValidationError
        invalid_levels = [
            "DEBUG",  # Not in canonical set and no mapping
            "FATAL",
            "TRACE",
            "",
            "   ",
            "INVALID",
        ]

        for invalid_level in invalid_levels:
            with pytest.raises(ValidationError) as exc_info:
                DashboardLogRequest(
                    level=invalid_level,
                    message="Test message",
                    timestamp="2023-01-01T12:00:00Z",
                )
            assert "must be one of" in str(exc_info.value)

    def test_level_validation_non_string_fails(self):
        """Test level validation fails for non-string types."""
        with pytest.raises(ValidationError) as exc_info:
            DashboardLogRequest(
                level=1,  # Integer instead of string
                message="Test message",
                timestamp="2023-01-01T12:00:00Z",
            )

        assert "Input should be a valid string" in str(exc_info.value)

    def test_message_validation_basic(self):
        """Test message validation with basic strings."""
        messages = [
            "Simple message",
            "Message with special characters: !@#$%^&*()",
            "Message with numbers: 12345",
            "Multi-line\nmessage\nwith\nbreaks",
            "Very long message " + "x" * 1000,
            # NOTE: Empty message removed as it's not allowed by the model validator
        ]

        for message in messages:
            log_request = DashboardLogRequest(
                level="INFO", message=message, timestamp="2023-01-01T12:00:00Z"
            )
            assert log_request.message == message

    def test_message_validation_strips_whitespace(self):
        """Test message validation strips whitespace."""
        log_request = DashboardLogRequest(
            level="INFO",
            message="  Test message with spaces  ",
            timestamp="2023-01-01T12:00:00Z",
        )

        assert log_request.message == "Test message with spaces"

    def test_message_validation_non_string_fails(self):
        """Test message validation fails for non-string types."""
        invalid_messages = [123, True, None, ["list"], {"dict": "value"}]

        for invalid_message in invalid_messages:
            with pytest.raises(ValidationError) as exc_info:
                DashboardLogRequest(
                    level="INFO",
                    message=invalid_message,
                    timestamp="2023-01-01T12:00:00Z",
                )
            assert "Input should be a valid string" in str(exc_info.value)

    def test_timestamp_validation_iso8601(self):
        """Test timestamp validation with ISO 8601 formats."""
        valid_timestamps = [
            "2023-01-01T12:00:00Z",
            "2023-01-01T12:00:00+00:00",
            "2023-01-01T12:00:00.123Z",
            "2023-12-31T23:59:59-05:00",
        ]

        for timestamp in valid_timestamps:
            log_request = DashboardLogRequest(
                level="INFO", message="Test message", timestamp=timestamp
            )
            assert log_request.timestamp == timestamp

    def test_timestamp_validation_invalid_formats(self):
        """Test timestamp validation rejects invalid formats."""
        # Note: Python's datetime.fromisoformat() accepts many formats.
        # Only testing clearly invalid ones.
        invalid_timestamps = ["invalid-timestamp", "", "   "]

        for timestamp in invalid_timestamps:
            with pytest.raises(ValidationError) as exc_info:
                DashboardLogRequest(
                    level="INFO", message="Test message", timestamp=timestamp
                )
            assert "timestamp must be" in str(exc_info.value)

    def test_complete_log_scenarios(self):
        """Test complete logging scenarios."""
        # Success scenario
        success_log = DashboardLogRequest(
            level="sucs",  # Lowercase, should convert
            message="Operation completed successfully",
            timestamp="2023-01-01T12:00:00Z",
        )
        assert success_log.level == "SUCS"

        # Error scenario
        error_log = DashboardLogRequest(
            level="ERR",
            message="Failed to connect to database",
            timestamp="2023-01-01T12:01:00Z",
        )
        assert error_log.level == "ERR"

        # Warning scenario
        warning_log = DashboardLogRequest(
            level="WARN",
            message="Connection timeout, retrying...",
            timestamp="2023-01-01T12:02:00Z",
        )
        assert warning_log.level == "WARN"

    def test_edge_cases(self):
        """Test edge cases for dashboard log requests."""
        # NOTE: Empty message test removed as the model validator doesn't allow empty messages
        # This is by design - all log messages should have content

        # Very long message
        long_message = "x" * 10000
        log_request = DashboardLogRequest(
            level="INFO",
            message=long_message,
            timestamp="2023-01-01T12:00:00Z",
        )
        assert len(log_request.message) == 10000

    def test_unicode_in_messages(self):
        """Test unicode characters in messages."""
        unicode_message = "测试消息 with émojis 🚀 and spëcial chars"

        log_request = DashboardLogRequest(
            level="INFO",
            message=unicode_message,
            timestamp="2023-01-01T12:00:00Z",
        )

        assert log_request.message == unicode_message
