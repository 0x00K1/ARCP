"""
Unit tests for ARCP API protection utilities.

This test module comprehensively tests the hierarchical permission system,
token validation, session management, and PIN verification.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from src.arcp.core.exceptions import ProblemException
from src.arcp.utils.api_protection import (
    PermissionLevel,
    check_endpoint_access,
    get_current_user,
    has_permission,
    verify_admin,
    verify_admin_pin,
    verify_agent,
    verify_api_token,
    verify_pin_access,
    verify_public,
)


@pytest.mark.unit
class TestPermissionLevel:
    """Test cases for PermissionLevel class and hierarchy."""

    def test_permission_hierarchy_structure(self):
        """Test permission hierarchy is correctly defined."""
        assert PermissionLevel.PUBLIC == "public"
        assert PermissionLevel.AGENT == "agent"
        assert PermissionLevel.ADMIN == "admin"
        assert PermissionLevel.ADMIN_PIN == "admin_pin"

        # Test hierarchy structure
        assert PermissionLevel.PERMISSION_HIERARCHY[PermissionLevel.PUBLIC] == []
        assert PermissionLevel.PERMISSION_HIERARCHY[PermissionLevel.AGENT] == [
            PermissionLevel.PUBLIC
        ]
        assert PermissionLevel.PERMISSION_HIERARCHY[PermissionLevel.ADMIN] == [
            PermissionLevel.PUBLIC,
            PermissionLevel.AGENT,
        ]
        assert PermissionLevel.PERMISSION_HIERARCHY[PermissionLevel.ADMIN_PIN] == [
            PermissionLevel.PUBLIC,
            PermissionLevel.AGENT,
            PermissionLevel.ADMIN,
        ]

    def test_role_permissions_mapping(self):
        """Test role to permissions mapping."""
        assert PermissionLevel.ROLE_PERMISSIONS["public"] == [PermissionLevel.PUBLIC]
        assert PermissionLevel.ROLE_PERMISSIONS["agent"] == [
            PermissionLevel.PUBLIC,
            PermissionLevel.AGENT,
        ]
        assert PermissionLevel.ROLE_PERMISSIONS["admin"] == [
            PermissionLevel.PUBLIC,
            PermissionLevel.AGENT,
            PermissionLevel.ADMIN,
            PermissionLevel.ADMIN_PIN,
        ]

    def test_can_access_public_level(self):
        """Test public access permissions."""
        assert PermissionLevel.can_access("public", PermissionLevel.PUBLIC) is True
        assert PermissionLevel.can_access("public", PermissionLevel.AGENT) is False
        assert PermissionLevel.can_access("public", PermissionLevel.ADMIN) is False
        assert PermissionLevel.can_access("public", PermissionLevel.ADMIN_PIN) is False

    def test_can_access_agent_level(self):
        """Test agent access permissions."""
        assert PermissionLevel.can_access("agent", PermissionLevel.PUBLIC) is True
        assert PermissionLevel.can_access("agent", PermissionLevel.AGENT) is True
        assert PermissionLevel.can_access("agent", PermissionLevel.ADMIN) is False
        assert PermissionLevel.can_access("agent", PermissionLevel.ADMIN_PIN) is False

    def test_can_access_admin_level(self):
        """Test admin access permissions."""
        assert PermissionLevel.can_access("admin", PermissionLevel.PUBLIC) is True
        assert PermissionLevel.can_access("admin", PermissionLevel.AGENT) is True
        assert PermissionLevel.can_access("admin", PermissionLevel.ADMIN) is True
        assert PermissionLevel.can_access("admin", PermissionLevel.ADMIN_PIN) is True

    def test_can_access_invalid_role(self):
        """Test access with invalid role."""
        assert (
            PermissionLevel.can_access("invalid_role", PermissionLevel.PUBLIC) is False
        )
        assert (
            PermissionLevel.can_access("invalid_role", PermissionLevel.AGENT) is False
        )

    def test_can_access_edge_cases(self):
        """Test edge cases for permission checking."""
        assert PermissionLevel.can_access("", PermissionLevel.PUBLIC) is False
        assert PermissionLevel.can_access(None, PermissionLevel.PUBLIC) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyApiToken:
    """Test cases for verify_api_token function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.url.path = "/api/test"

    async def test_verify_api_token_public_access(self):
        """Test public access requires no authentication."""
        result = await verify_api_token(self.mock_request, None, PermissionLevel.PUBLIC)

        assert result["role"] == "public"
        assert result["sub"] == "anonymous"
        assert PermissionLevel.PUBLIC in result["permissions"]

    async def test_verify_api_token_missing_header(self):
        """Test missing authorization header."""
        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(self.mock_request, None, PermissionLevel.AGENT)

            assert exc_info.value.status == 401
            assert "Authentication required" in exc_info.value.detail
            mock_log.assert_called_once()

    async def test_verify_api_token_invalid_header_format(self):
        """Test invalid authorization header format."""
        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(
                    self.mock_request, "InvalidFormat", PermissionLevel.AGENT
                )

            assert exc_info.value.status == 401
            mock_log.assert_called_once()

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_verify_api_token_invalid_token(self, mock_get_token):
        """Test invalid token handling."""
        mock_get_token.return_value = None

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(
                    self.mock_request,
                    "Bearer invalid_token",
                    PermissionLevel.AGENT,
                )

            assert exc_info.value.status == 401
            assert "Invalid or expired token" in exc_info.value.detail
            mock_log.assert_called_once()

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_verify_api_token_valid_agent_token(self, mock_get_token):
        """Test valid agent token."""
        mock_payload = {
            "sub": "test-agent",
            "agent_id": "test-agent",
            "role": "agent",
            "temp_registration": False,
        }
        mock_get_token.return_value = mock_payload

        result = await verify_api_token(
            self.mock_request, "Bearer valid_token", PermissionLevel.AGENT
        )

        assert result["role"] == "agent"
        assert result["is_admin"] is False
        assert PermissionLevel.AGENT in result["permissions"]
        assert PermissionLevel.PUBLIC in result["permissions"]

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_verify_api_token_temp_registration_token(self, mock_get_token):
        """Test temporary registration token access."""
        mock_payload = {
            "sub": "temp-agent",
            "agent_id": "temp-agent",
            "role": "agent",
            "temp_registration": True,
        }
        mock_get_token.return_value = mock_payload

        result = await verify_api_token(
            self.mock_request, "Bearer temp_token", PermissionLevel.AGENT
        )

        assert result["temp_registration"] is True
        assert result["role"] == "agent"

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_verify_api_token_insufficient_permissions(self, mock_get_token):
        """Test insufficient permissions."""
        mock_payload = {
            "sub": "test-agent",
            "agent_id": "test-agent",
            "role": "agent",
            "temp_registration": False,
        }
        mock_get_token.return_value = mock_payload

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(
                    self.mock_request,
                    "Bearer agent_token",
                    PermissionLevel.ADMIN,
                )

            assert exc_info.value.status == 403
            assert "Access denied" in exc_info.value.detail
            mock_log.assert_called_once()

    @patch("src.arcp.utils.api_protection.get_token_payload")
    @patch("src.arcp.utils.api_protection.get_session_info")
    @patch("src.arcp.utils.api_protection.get_token_ref_from_request")
    async def test_verify_api_token_admin_without_session(
        self, mock_get_token_ref, mock_get_session, mock_get_token
    ):
        """Test admin token without valid session."""
        mock_payload = {
            "sub": "admin",
            "agent_id": "admin",
            "role": "admin",
            "temp_registration": False,
        }
        mock_get_token.return_value = mock_payload
        mock_get_token_ref.return_value = "token_ref"
        mock_get_session.return_value = None
        self.mock_request.headers = {"X-Client-Fingerprint": "fingerprint123"}

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(
                    self.mock_request,
                    "Bearer admin_token",
                    PermissionLevel.ADMIN,
                )

            assert exc_info.value.status == 401
            assert "Admin session validation failed" in exc_info.value.detail
            mock_log.assert_called_once()

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_verify_api_token_exception_handling(self, mock_get_token):
        """Test exception handling during token verification."""
        mock_get_token.side_effect = Exception("Database error")

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_api_token(
                    self.mock_request, "Bearer token", PermissionLevel.AGENT
                )

            assert exc_info.value.status == 401
            assert "Authentication failed" in exc_info.value.detail
            mock_log.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyPinAccess:
    """Test cases for verify_pin_access function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.url.path = "/api/admin/critical"
        self.user_payload = {
            "sub": "admin_user",
            "role": "admin",
            "is_admin": True,
        }

    async def test_verify_pin_access_missing_pin(self):
        """Test missing PIN header."""
        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_pin_access(self.mock_request, self.user_payload, None)

            assert exc_info.value.status == 400
            assert "PIN required" in exc_info.value.detail
            mock_log.assert_called_once()

    @patch("src.arcp.utils.api_protection.verify_session_pin")
    @patch("src.arcp.utils.api_protection.record_auth_attempt")
    async def test_verify_pin_access_invalid_pin(
        self, mock_record_auth, mock_verify_pin
    ):
        """Test invalid PIN."""
        mock_verify_pin.return_value = False
        mock_record_auth.return_value = None

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_pin_access(
                    self.mock_request, self.user_payload, "wrong_pin"
                )

            assert exc_info.value.status == 401
            assert "Invalid PIN" in exc_info.value.detail
            mock_log.assert_called_once()
            mock_record_auth.assert_called_once_with(self.mock_request, False, "pin")

    @patch("src.arcp.utils.api_protection.verify_session_pin")
    @patch("src.arcp.utils.api_protection.record_auth_attempt")
    async def test_verify_pin_access_valid_pin(self, mock_record_auth, mock_verify_pin):
        """Test valid PIN."""
        mock_verify_pin.return_value = True
        mock_record_auth.return_value = None

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            result = await verify_pin_access(
                self.mock_request, self.user_payload, "correct_pin"
            )

            assert result["pin_verified"] is True
            assert result["sub"] == "admin_user"
            mock_log.assert_called_once()
            mock_record_auth.assert_called_once_with(self.mock_request, True, "pin")

    @patch("src.arcp.utils.api_protection.verify_session_pin")
    async def test_verify_pin_access_exception_handling(self, mock_verify_pin):
        """Test exception handling during PIN verification."""
        mock_verify_pin.side_effect = Exception("Session error")

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException) as exc_info:
                await verify_pin_access(self.mock_request, self.user_payload, "any_pin")

            assert exc_info.value.status == 500
            assert "PIN verification failed" in exc_info.value.detail
            mock_log.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestPermissionVerifiers:
    """Test cases for permission verification functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.url.path = "/api/test"

    @patch("src.arcp.utils.api_protection.verify_api_token")
    async def test_verify_public(self, mock_verify):
        """Test public endpoint verification."""
        mock_verify.return_value = {"role": "public"}

        result = await verify_public(self.mock_request)

        mock_verify.assert_called_once_with(
            self.mock_request, None, PermissionLevel.PUBLIC
        )
        assert result["role"] == "public"

    @patch("src.arcp.utils.api_protection.verify_api_token")
    async def test_verify_agent(self, mock_verify):
        """Test agent endpoint verification."""
        mock_verify.return_value = {"role": "agent"}

        result = await verify_agent(self.mock_request, "Bearer token")

        mock_verify.assert_called_once_with(
            self.mock_request, "Bearer token", PermissionLevel.AGENT
        )
        assert result["role"] == "agent"

    @patch("src.arcp.utils.api_protection.verify_api_token")
    async def test_verify_admin(self, mock_verify):
        """Test admin endpoint verification."""
        mock_verify.return_value = {"role": "admin"}

        result = await verify_admin(self.mock_request, "Bearer admin_token")

        mock_verify.assert_called_once_with(
            self.mock_request, "Bearer admin_token", PermissionLevel.ADMIN
        )
        assert result["role"] == "admin"

    @patch("src.arcp.utils.api_protection.verify_api_token")
    @patch("src.arcp.utils.api_protection.verify_pin_access")
    async def test_verify_admin_pin(self, mock_verify_pin, mock_verify_token):
        """Test admin PIN endpoint verification."""
        mock_verify_token.return_value = {"role": "admin", "sub": "admin_user"}
        mock_verify_pin.return_value = {
            "role": "admin",
            "sub": "admin_user",
            "pin_verified": True,
        }

        result = await verify_admin_pin(self.mock_request, "Bearer admin_token", "1234")

        mock_verify_token.assert_called_once_with(
            self.mock_request, "Bearer admin_token", PermissionLevel.ADMIN
        )
        mock_verify_pin.assert_called_once()
        assert result["pin_verified"] is True


@pytest.mark.unit
class TestHelperFunctions:
    """Test cases for helper functions."""

    def test_get_current_user_public(self):
        """Test getting current user info for public user."""
        payload = {"role": "public", "sub": "anonymous"}

        user_info = get_current_user(payload)

        assert user_info["role"] == "public"
        assert user_info["is_admin"] is False
        assert user_info["is_agent"] is False
        assert PermissionLevel.PUBLIC in user_info["permissions"]

    def test_get_current_user_agent(self):
        """Test getting current user info for agent."""
        payload = {
            "role": "agent",
            "sub": "test-agent",
            "agent_id": "test-agent",
            "permissions": [PermissionLevel.PUBLIC, PermissionLevel.AGENT],
        }

        user_info = get_current_user(payload)

        assert user_info["role"] == "agent"
        assert user_info["is_admin"] is False
        assert user_info["is_agent"] is True
        assert user_info["agent_id"] == "test-agent"

    def test_get_current_user_admin(self):
        """Test getting current user info for admin."""
        payload = {
            "role": "admin",
            "sub": "admin_user",
            "permissions": [
                PermissionLevel.PUBLIC,
                PermissionLevel.AGENT,
                PermissionLevel.ADMIN,
                PermissionLevel.ADMIN_PIN,
            ],
            "pin_verified": True,
        }

        user_info = get_current_user(payload)

        assert user_info["role"] == "admin"
        assert user_info["is_admin"] is True
        assert user_info["is_agent"] is True
        assert user_info["pin_verified"] is True

    def test_get_current_user_temp_registration(self):
        """Test getting current user info for temp registration."""
        payload = {
            "role": "agent",
            "sub": "temp-agent",
            "temp_registration": True,
        }

        user_info = get_current_user(payload)

        assert user_info["is_temp"] is True
        assert user_info["role"] == "agent"

    def test_has_permission(self):
        """Test permission checking helper."""
        payload = {"permissions": [PermissionLevel.PUBLIC, PermissionLevel.AGENT]}

        assert has_permission(payload, PermissionLevel.PUBLIC) is True
        assert has_permission(payload, PermissionLevel.AGENT) is True
        assert has_permission(payload, PermissionLevel.ADMIN) is False

    def test_check_endpoint_access(self):
        """Test endpoint access checking."""
        assert check_endpoint_access("admin", PermissionLevel.ADMIN) is True
        assert check_endpoint_access("agent", PermissionLevel.ADMIN) is False
        assert check_endpoint_access("agent", PermissionLevel.AGENT) is True
        assert check_endpoint_access("public", PermissionLevel.PUBLIC) is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrencyAndPerformance:
    """Test cases for concurrency and performance scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.url.path = "/api/test"

    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_concurrent_token_verification(self, mock_get_token):
        """Test concurrent token verification."""
        mock_get_token.return_value = {
            "sub": "test-agent",
            "role": "agent",
            "temp_registration": False,
        }

        # Create multiple concurrent verification tasks
        tasks = [
            verify_api_token(self.mock_request, "Bearer token", PermissionLevel.AGENT)
            for _ in range(10)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        for result in results:
            assert isinstance(result, dict)
            assert result["role"] == "agent"

        # Token should be called for each verification
        assert mock_get_token.call_count == 10

    @patch("src.arcp.utils.api_protection.verify_session_pin")
    @patch("src.arcp.utils.api_protection.record_auth_attempt")
    async def test_concurrent_pin_verification(self, mock_record_auth, mock_verify_pin):
        """Test concurrent PIN verification."""
        mock_verify_pin.return_value = True
        mock_record_auth.return_value = None

        user_payload = {"sub": "admin", "role": "admin"}

        # Create multiple concurrent PIN verification tasks
        tasks = [
            verify_pin_access(self.mock_request, user_payload, "1234") for _ in range(5)
        ]

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            for result in results:
                assert isinstance(result, dict)
                assert result["pin_verified"] is True


@pytest.mark.unit
class TestSecurityEdgeCases:
    """Test cases for security edge cases and attack scenarios."""

    def test_permission_level_case_sensitivity(self):
        """Test permission system is not affected by case changes."""
        # The system should be case-sensitive for security
        assert PermissionLevel.can_access("Admin", PermissionLevel.ADMIN) is False
        assert PermissionLevel.can_access("ADMIN", PermissionLevel.ADMIN) is False
        assert PermissionLevel.can_access("admin", PermissionLevel.ADMIN) is True

    def test_permission_level_injection_attempts(self):
        """Test permission system against injection attempts."""
        malicious_roles = [
            "admin'; DROP TABLE users; --",
            "admin OR 1=1",
            "<script>alert('xss')</script>",
            "admin\x00admin",
            "admin\nadmin",
        ]

        for malicious_role in malicious_roles:
            assert (
                PermissionLevel.can_access(malicious_role, PermissionLevel.ADMIN)
                is False
            )

    @pytest.mark.asyncio
    @patch("src.arcp.utils.api_protection.get_token_payload")
    async def test_token_manipulation_attempts(self, mock_get_token):
        """Test resistance to token manipulation."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/test"

        # Test with various malicious tokens
        malicious_tokens = [
            "Bearer ",  # Empty token
            "Bearer null",
            "Bearer undefined",
            "Bearer <script>",
            "Bearer ' OR '1'='1",
            "Bearer \x00\x01\x02",
            "Bearer " + "A" * 10000,  # Very long token
        ]

        mock_get_token.return_value = None  # All should be rejected

        for token in malicious_tokens:
            with pytest.raises(ProblemException):
                await verify_api_token(mock_request, token, PermissionLevel.AGENT)

    @pytest.mark.asyncio
    async def test_path_traversal_in_logging(self):
        """Test that path traversal attempts don't affect logging."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "../../../../etc/passwd"

        with patch("src.arcp.utils.api_protection.log_security_event") as mock_log:
            mock_log.return_value = None

            with pytest.raises(ProblemException):
                await verify_api_token(mock_request, None, PermissionLevel.AGENT)

            # Verify the malicious path was logged (for security monitoring)
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert "../../../../etc/passwd" in str(call_args)
