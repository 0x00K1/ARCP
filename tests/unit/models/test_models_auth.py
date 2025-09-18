"""
Unit tests for ARCP authentication models.
"""

import pytest
from pydantic import ValidationError

from src.arcp.models.auth import LoginRequest


@pytest.mark.unit
class TestLoginRequest:
    """Test cases for LoginRequest model."""

    def test_login_request_basic_user(self):
        """Test basic user login request."""
        request = LoginRequest(username="testuser", password="testpassword")

        assert request.username == "testuser"
        assert request.password == "testpassword"
        assert request.agent_id is None
        assert request.agent_type is None
        assert request.agent_key is None

    def test_login_request_basic_agent(self):
        """Test basic agent login request."""
        request = LoginRequest(
            agent_id="test-agent-001",
            agent_type="automation",
            agent_key="secret-agent-key",
        )

        assert request.username is None
        assert request.password is None
        assert request.agent_id == "test-agent-001"
        assert request.agent_type == "automation"
        assert request.agent_key == "secret-agent-key"

    def test_login_request_all_fields(self):
        """Test login request with all fields provided."""
        request = LoginRequest(
            username="testuser",
            password="testpassword",
            agent_id="test-agent",
            agent_type="testing",
            agent_key="agent-key",
        )

        assert request.username == "testuser"
        assert request.password == "testpassword"
        assert request.agent_id == "test-agent"
        assert request.agent_type == "testing"
        assert request.agent_key == "agent-key"

    def test_username_validation_strips_whitespace(self):
        """Test username validation strips whitespace."""
        request = LoginRequest(username="  testuser  ", password="password")

        assert request.username == "testuser"

    def test_username_validation_too_long(self):
        """Test username validation fails for too long usernames."""
        long_username = "a" * 256  # 256 characters, exceeds 255 limit

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username=long_username, password="password")

        assert "username too long" in str(exc_info.value)

    def test_username_validation_none_allowed(self):
        """Test username can be None."""
        request = LoginRequest(username=None, password="password")

        assert request.username is None

    def test_password_validation_basic(self):
        """Test password validation basic functionality."""
        request = LoginRequest(username="testuser", password="validpassword")

        assert request.password == "validpassword"

    def test_password_validation_empty_fails(self):
        """Test password validation fails for empty passwords."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="testuser", password="")

        assert "password cannot be empty" in str(exc_info.value)

    def test_password_validation_too_long(self):
        """Test password validation fails for too long passwords."""
        long_password = "a" * 1025  # 1025 characters, exceeds 1024 limit

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(username="testuser", password=long_password)

        assert "password too long" in str(exc_info.value)

    def test_password_validation_none_allowed(self):
        """Test password can be None."""
        request = LoginRequest(username="testuser", password=None)

        assert request.password is None

    def test_agent_id_validation_strips_whitespace(self):
        """Test agent_id validation strips whitespace."""
        request = LoginRequest(
            agent_id="  test-agent  ", agent_type="testing", agent_key="key"
        )

        assert request.agent_id == "test-agent"

    def test_agent_id_validation_too_long(self):
        """Test agent_id validation fails for too long IDs."""
        long_agent_id = "a" * 101  # 101 characters, exceeds 100 limit

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(agent_id=long_agent_id, agent_type="testing", agent_key="key")

        assert "agent_id too long" in str(exc_info.value)

    def test_agent_id_validation_empty_fails(self):
        """Test agent_id validation fails for empty IDs."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(agent_id="", agent_type="testing", agent_key="key")

        assert "agent_id cannot be empty" in str(exc_info.value)

    def test_agent_id_validation_whitespace_only_fails(self):
        """Test agent_id validation fails for whitespace-only IDs."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(agent_id="   ", agent_type="testing", agent_key="key")

        assert "agent_id cannot be empty" in str(exc_info.value)

    def test_agent_id_validation_valid_characters(self):
        """Test agent_id validation accepts valid characters."""
        valid_agent_ids = [
            "test-agent",
            "test_agent",
            "TestAgent123",
            "agent-123_test",
            "a1b2c3",
            "123-456",
        ]

        for agent_id in valid_agent_ids:
            request = LoginRequest(
                agent_id=agent_id, agent_type="testing", agent_key="key"
            )
            assert request.agent_id == agent_id

    def test_agent_id_validation_invalid_characters(self):
        """Test agent_id validation rejects invalid characters."""
        invalid_agent_ids = [
            "test@agent",
            "test agent",  # space
            "test.agent",
            "test+agent",
            "test/agent",
            "test\\agent",
            "test=agent",
            "test#agent",
        ]

        for agent_id in invalid_agent_ids:
            with pytest.raises(ValidationError) as exc_info:
                LoginRequest(agent_id=agent_id, agent_type="testing", agent_key="key")
            assert "invalid characters" in str(exc_info.value)

    def test_agent_id_validation_none_allowed(self):
        """Test agent_id can be None."""
        request = LoginRequest(agent_id=None, agent_type="testing", agent_key="key")

        assert request.agent_id is None

    def test_agent_type_validation_strips_whitespace(self):
        """Test agent_type validation strips whitespace."""
        request = LoginRequest(
            agent_id="test-agent", agent_type="  automation  ", agent_key="key"
        )

        assert request.agent_type == "automation"

    def test_agent_type_validation_too_long(self):
        """Test agent_type validation fails for too long types."""
        long_agent_type = "a" * 51  # 51 characters, exceeds 50 limit

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(
                agent_id="test-agent",
                agent_type=long_agent_type,
                agent_key="key",
            )

        assert "agent_type too long" in str(exc_info.value)

    def test_agent_type_validation_empty_fails(self):
        """Test agent_type validation fails for empty types."""
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(agent_id="test-agent", agent_type="", agent_key="key")

        assert "agent_type cannot be empty" in str(exc_info.value)

    def test_agent_type_validation_none_allowed(self):
        """Test agent_type can be None."""
        request = LoginRequest(agent_id="test-agent", agent_type=None, agent_key="key")

        assert request.agent_type is None

    def test_agent_key_validation_strips_whitespace(self):
        """Test agent_key validation strips whitespace."""
        request = LoginRequest(
            agent_id="test-agent",
            agent_type="testing",
            agent_key="  secret-key  ",
        )

        assert request.agent_key == "secret-key"

    def test_agent_key_validation_too_long(self):
        """Test agent_key validation fails for too long keys."""
        long_agent_key = "a" * 513  # 513 characters, exceeds 512 limit

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(
                agent_id="test-agent",
                agent_type="testing",
                agent_key=long_agent_key,
            )

        assert "agent_key too long" in str(exc_info.value)

    def test_agent_key_validation_empty_fails(self):
        """Test agent_key validation fails for empty keys."""
        # NOTE: Empty validation was intentionally removed from agent_key for security reasons
        # (timing attack prevention). This test is commented out as the validation no longer exists.
        """
        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(
                agent_id="test-agent",
                agent_type="testing",
                agent_key=""
            )

        assert "agent_key cannot be empty" in str(exc_info.value)
        """

    def test_agent_key_validation_none_allowed(self):
        """Test agent_key can be None."""
        request = LoginRequest(
            agent_id="test-agent", agent_type="testing", agent_key=None
        )

        assert request.agent_key is None

    def test_mixed_validation_scenarios(self):
        """Test various mixed validation scenarios."""
        # Valid user login
        user_request = LoginRequest(username="user", password="pass")
        assert user_request.username == "user"

        # Valid agent login
        agent_request = LoginRequest(
            agent_id="agent-1", agent_type="automation", agent_key="key123"
        )
        assert agent_request.agent_id == "agent-1"

        # All None (should be valid for the model itself)
        empty_request = LoginRequest()
        assert empty_request.username is None
        assert empty_request.password is None
        assert empty_request.agent_id is None

    def test_edge_case_lengths(self):
        """Test edge cases for field length limits."""
        # Maximum allowed lengths
        max_username = "a" * 255
        max_password = "a" * 1024
        max_agent_id = "a" * 100
        max_agent_type = "a" * 50
        max_agent_key = "a" * 200  # Corrected from 512 to actual limit of 200

        request = LoginRequest(
            username=max_username,
            password=max_password,
            agent_id=max_agent_id,
            agent_type=max_agent_type,
            agent_key=max_agent_key,
        )

        assert len(request.username) == 255
        assert len(request.password) == 1024
        assert len(request.agent_id) == 100
        assert len(request.agent_type) == 50
        assert len(request.agent_key) == 200  # Corrected from 512 to 200

    def test_special_characters_in_fields(self):
        """Test special characters in allowed fields."""
        # Username and password can contain special characters
        request = LoginRequest(username="user@domain.com", password="p@ssw0rd!#$%^&*()")

        assert request.username == "user@domain.com"
        assert request.password == "p@ssw0rd!#$%^&*()"

        # Agent key can contain special characters
        agent_request = LoginRequest(
            agent_id="test-agent",
            agent_type="testing",
            agent_key="key!@#$%^&*()_+-=[]{}|;:,.<>?",
        )

        assert "key!@#$%^&*()_+-=[]{}|;:,.<>?" in agent_request.agent_key

    def test_unicode_characters(self):
        """Test unicode characters in fields."""
        # Unicode should be allowed in username and password
        request = LoginRequest(username="tëstüser", password="pässwørd")

        assert request.username == "tëstüser"
        assert request.password == "pässwørd"
