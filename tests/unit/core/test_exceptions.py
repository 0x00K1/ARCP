"""
Unit tests for ARCP exceptions module.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from src.arcp.core.exceptions import (
    AgentNotFoundError,
    AgentRegistrationError,
    ARCPException,
    AuthenticationError,
    ConfigurationError,
    ProblemException,
    TokenValidationError,
    VectorSearchError,
    general_exception_handler,
    register_exception_handlers,
    validation_exception_handler,
)


@pytest.mark.unit
class TestARCPExceptions:
    """Test cases for ARCP exception classes."""

    def test_arcp_exception_basic(self):
        """Test basic ARCP exception creation."""
        exc = ARCPException("Test error")

        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.details == {}

    def test_arcp_exception_with_details(self):
        """Test ARCP exception with details."""
        details = {"error_code": "TEST001", "context": "unit_test"}
        exc = ARCPException("Test error with details", details)

        assert str(exc) == "Test error with details"
        assert exc.message == "Test error with details"
        assert exc.details == details

    def test_agent_registration_error(self):
        """Test AgentRegistrationError inheritance."""
        exc = AgentRegistrationError("Registration failed")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Registration failed"

    def test_agent_not_found_error(self):
        """Test AgentNotFoundError inheritance."""
        exc = AgentNotFoundError("Agent not found")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Agent not found"

    def test_configuration_error(self):
        """Test ConfigurationError inheritance."""
        exc = ConfigurationError("Config error")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Config error"

    def test_authentication_error(self):
        """Test AuthenticationError inheritance."""
        exc = AuthenticationError("Auth failed")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Auth failed"

    def test_token_validation_error(self):
        """Test TokenValidationError inheritance."""
        exc = TokenValidationError("Token invalid")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Token invalid"

    def test_vector_search_error(self):
        """Test VectorSearchError inheritance."""
        exc = VectorSearchError("Search failed")

        assert isinstance(exc, ARCPException)
        assert str(exc) == "Search failed"


@pytest.mark.unit
class TestExceptionHandlers:
    """Test cases for exception handlers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.url.path = "/test/path"

    @pytest.mark.asyncio
    async def test_validation_exception_handler(self):
        """Test validation exception handler."""
        # Create a mock validation error
        mock_validation_error = MagicMock(spec=RequestValidationError)
        mock_validation_error.errors.return_value = [
            {
                "loc": ["field"],
                "msg": "required",
                "type": "value_error.missing",
            }
        ]

        with patch("src.arcp.core.exceptions.logging.getLogger") as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            response = await validation_exception_handler(
                self.mock_request, mock_validation_error
            )

            # Should return ProblemResponse with Problem Details
            assert hasattr(response, "status_code")
            assert response.status_code == 422
            mock_log.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_general_exception_handler(self):
        """Test general exception handler."""
        general_exc = Exception("Unexpected error")

        with patch("src.arcp.core.exceptions.logging.getLogger") as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log

            response = await general_exception_handler(self.mock_request, general_exc)

            # Should return ProblemResponse with Problem Details
            assert hasattr(response, "status_code")
            assert response.status_code == 500
            mock_log.error.assert_called_once()
            # Verify exc_info=True was passed for full traceback
            call_args = mock_log.error.call_args
            assert call_args[1]["exc_info"] is True

    def test_register_exception_handlers(self):
        """Test exception handler registration."""
        mock_app = MagicMock()

        register_exception_handlers(mock_app)

        # Verify all handlers were registered (3 handlers: ProblemException, RequestValidationError and Exception)
        assert mock_app.add_exception_handler.call_count == 3

        # Check the calls
        calls = mock_app.add_exception_handler.call_args_list
        exception_types = [call[0][0] for call in calls]

        assert RequestValidationError in exception_types
        assert Exception in exception_types
        assert ProblemException in exception_types


@pytest.mark.unit
class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_arcp_exception(self):
        """Test that all custom exceptions inherit from ARCPException."""
        exception_classes = [
            AgentRegistrationError,
            AgentNotFoundError,
            ConfigurationError,
            AuthenticationError,
            TokenValidationError,
            VectorSearchError,
        ]

        for exc_class in exception_classes:
            assert issubclass(exc_class, ARCPException)

            # Test instantiation
            instance = exc_class("Test message")
            assert isinstance(instance, ARCPException)
            assert isinstance(instance, Exception)

    def test_exception_chaining(self):
        """Test exception chaining functionality."""
        original_error = ValueError("Original error")

        try:
            raise original_error
        except ValueError as e:
            chained_error = AgentRegistrationError("Registration failed")
            chained_error.__cause__ = e

            assert chained_error.__cause__ is original_error
            assert str(chained_error) == "Registration failed"


@pytest.mark.unit
class TestExceptionLogging:
    """Test exception logging functionality."""

    @pytest.mark.asyncio
    @patch("src.arcp.core.exceptions.logging.getLogger")
    async def test_validation_handler_logging(self, mock_get_logger):
        """Test that validation handler logs appropriately."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/test/validation"

        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = []

        await validation_exception_handler(mock_request, mock_exc)

        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        assert "/test/validation" in log_message
