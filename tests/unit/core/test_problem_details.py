"""
Tests for RFC 9457 Problem Details implementation.

This test suite validates the Problem Details for HTTP APIs implementation
including security sanitization, proper formatting, and FastAPI integration.
"""

from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from src.arcp.core.exceptions import (
    AgentNotFoundError,
    ARCPException,
    ARCPProblemTypes,
    AuthenticationError,
    ProblemDetail,
    ProblemException,
    ProblemResponse,
    TokenValidationError,
    agent_not_found_problem,
    authentication_failed_problem,
    create_problem_detail,
    create_problem_response,
    general_exception_handler,
    validation_error_problem,
    validation_exception_handler,
)


class TestProblemDetail:
    """Test the core ProblemDetail class."""

    def test_basic_problem_detail_creation(self):
        """Test basic Problem Detail object creation."""
        problem = ProblemDetail(
            type="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="This is a test problem",
            instance="/api/test",
        )

        assert problem.type == "https://example.com/problems/test"
        assert problem.title == "Test Problem"
        assert problem.status == 400
        assert problem.detail == "This is a test problem"
        assert problem.instance == "/api/test"
        assert problem.timestamp is not None

    def test_default_values(self):
        """Test Problem Detail with default values."""
        problem = ProblemDetail()

        assert problem.type == "about:blank"
        assert problem.title is None
        assert problem.status is None
        assert problem.detail is None
        assert problem.instance is None
        assert problem.timestamp is not None

    def test_sanitized_creation(self):
        """Test sanitized Problem Detail creation."""
        # Mock request
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"

        problem = ProblemDetail.create_sanitized(
            type_uri="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="This is a test with <script>alert('xss')</script>",
            request=mock_request,
            custom_field="<img src=x onerror=alert(1)>",
        )

        assert problem.type == "https://example.com/problems/test"
        assert problem.title == "Test Problem"
        assert problem.status == 400
        assert (
            "&lt;[FILTERED]&gt;" in problem.detail or "&lt;script&gt;" in problem.detail
        )  # Should be sanitized
        assert problem.instance == "/api/test"
        assert "[FILTERED]" in problem.custom_field  # Should be sanitized

    def test_extra_fields_allowed(self):
        """Test that extra fields are allowed in Problem Details."""
        problem = ProblemDetail(
            type="https://example.com/problems/test",
            title="Test Problem",
            agent_id="test-agent",
            error_code="TEST_ERROR",
        )

        assert problem.agent_id == "test-agent"
        assert problem.error_code == "TEST_ERROR"


class TestProblemResponse:
    """Test the ProblemResponse class."""

    def test_problem_response_from_problem_detail(self):
        """Test creating ProblemResponse from ProblemDetail."""
        problem = ProblemDetail(
            type="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="Test detail",
        )

        response = ProblemResponse(problem)

        assert response.status_code == 400
        assert response.media_type == "application/problem+json"

        # Check content
        content = response.body.decode()
        assert '"type":"https://example.com/problems/test"' in content
        assert '"title":"Test Problem"' in content
        assert '"status":400' in content

    def test_problem_response_from_dict(self):
        """Test creating ProblemResponse from dictionary."""
        problem_dict = {
            "type": "https://example.com/problems/test",
            "title": "Test Problem",
            "status": 400,
            "detail": "Test detail",
        }

        response = ProblemResponse(problem_dict)

        assert response.status_code == 400
        assert response.media_type == "application/problem+json"


class TestProblemException:
    """Test the ProblemException class."""

    def test_problem_exception_creation(self):
        """Test creating ProblemException."""
        exc = ProblemException(
            type_uri="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="Test detail",
            agent_id="test-agent",
        )

        assert exc.type_uri == "https://example.com/problems/test"
        assert exc.title == "Test Problem"
        assert exc.status == 400
        assert exc.detail == "Test detail"
        assert exc.extensions["agent_id"] == "test-agent"

    def test_to_problem_detail(self):
        """Test converting ProblemException to ProblemDetail."""
        exc = ProblemException(
            type_uri="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="Test detail",
        )

        problem = exc.to_problem_detail()

        assert isinstance(problem, ProblemDetail)
        assert problem.type == "https://example.com/problems/test"
        assert problem.title == "Test Problem"
        assert problem.status == 400
        assert problem.detail == "Test detail"

    def test_to_response(self):
        """Test converting ProblemException to ProblemResponse."""
        exc = ProblemException(
            type_uri="https://example.com/problems/test",
            title="Test Problem",
            status=400,
            detail="Test detail",
        )

        response = exc.to_response()

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 400


class TestARCPProblemTypes:
    """Test the ARCP problem type definitions."""

    def test_problem_types_structure(self):
        """Test that all problem types have required fields."""
        for attr_name in dir(ARCPProblemTypes):
            if not attr_name.startswith("_") and attr_name != "BASE_URI":
                problem_type = getattr(ARCPProblemTypes, attr_name)
                if isinstance(problem_type, dict):
                    assert "type" in problem_type
                    assert "title" in problem_type
                    assert "default_status" in problem_type
                    assert problem_type["type"].startswith(ARCPProblemTypes.BASE_URI)

    def test_specific_problem_types(self):
        """Test specific ARCP problem types."""
        assert ARCPProblemTypes.AGENT_NOT_FOUND["default_status"] == 404
        assert ARCPProblemTypes.AUTHENTICATION_FAILED["default_status"] == 401
        assert ARCPProblemTypes.INSUFFICIENT_PERMISSIONS["default_status"] == 403
        assert ARCPProblemTypes.VALIDATION_ERROR["default_status"] == 422
        assert ARCPProblemTypes.INTERNAL_ERROR["default_status"] == 500


class TestARCPExceptionEnhancements:
    """Test enhanced ARCP exceptions with Problem Details support."""

    def test_arcp_exception_problem_type(self):
        """Test ARCPException has default problem type."""
        exc = ARCPException("Test error")

        assert hasattr(exc, "problem_type")
        assert exc.problem_type == ARCPProblemTypes.INTERNAL_ERROR

    def test_specific_exception_problem_types(self):
        """Test specific exception problem types."""
        agent_not_found = AgentNotFoundError("Agent not found", agent_id="test-agent")
        auth_error = AuthenticationError("Auth failed")
        token_error = TokenValidationError("Token invalid")

        assert agent_not_found.problem_type == ARCPProblemTypes.AGENT_NOT_FOUND
        assert auth_error.problem_type == ARCPProblemTypes.AUTHENTICATION_FAILED
        assert token_error.problem_type == ARCPProblemTypes.TOKEN_VALIDATION_ERROR

        # Test AgentNotFoundError with agent_id
        assert agent_not_found.details["agent_id"] == "test-agent"

    def test_to_problem_detail_conversion(self):
        """Test converting ARCP exceptions to Problem Details."""
        exc = AgentNotFoundError("Agent not found", agent_id="test-agent")

        problem = exc.to_problem_detail()

        assert isinstance(problem, ProblemDetail)
        assert problem.type == ARCPProblemTypes.AGENT_NOT_FOUND["type"]
        assert problem.title == ARCPProblemTypes.AGENT_NOT_FOUND["title"]
        assert problem.status == 404
        assert problem.detail == "Agent not found"
        assert problem.agent_id == "test-agent"

    def test_to_problem_response_conversion(self):
        """Test converting ARCP exceptions to Problem Response."""
        exc = AuthenticationError("Authentication failed")

        response = exc.to_problem_response()

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 401
        assert response.media_type == "application/problem+json"


class TestHelperFunctions:
    """Test Problem Details helper functions."""

    def test_create_problem_detail(self):
        """Test create_problem_detail helper."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"

        problem = create_problem_detail(
            problem_type=ARCPProblemTypes.AGENT_NOT_FOUND,
            detail="Agent not found",
            request=mock_request,
            agent_id="test-agent",
        )

        assert problem.type == ARCPProblemTypes.AGENT_NOT_FOUND["type"]
        assert problem.title == ARCPProblemTypes.AGENT_NOT_FOUND["title"]
        assert problem.status == 404
        assert problem.detail == "Agent not found"
        assert problem.instance == "/api/test"
        assert problem.agent_id == "test-agent"

    def test_create_problem_response(self):
        """Test create_problem_response helper."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"

        response = create_problem_response(
            problem_type=ARCPProblemTypes.AUTHENTICATION_FAILED,
            detail="Authentication failed",
            request=mock_request,
        )

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 401

    def test_agent_not_found_problem(self):
        """Test agent_not_found_problem convenience function."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/agents/test"

        response = agent_not_found_problem("test-agent", mock_request)

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 404

        # Check content includes agent_id
        content = response.body.decode()
        assert '"agent_id":"test-agent"' in content

    def test_authentication_failed_problem(self):
        """Test authentication_failed_problem convenience function."""
        response = authentication_failed_problem("Invalid credentials")

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 401

        content = response.body.decode()
        assert "Authentication failed: Invalid credentials" in content

    def test_validation_error_problem(self):
        """Test validation_error_problem convenience function."""
        errors = [{"field": "email", "message": "Invalid email"}]

        response = validation_error_problem(errors)

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 422


@pytest.mark.asyncio
class TestExceptionHandlers:
    """Test FastAPI exception handlers with Problem Details."""

    async def test_validation_exception_handler(self):
        """Test validation exception handler returns Problem Details."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"

        # Create mock validation error
        mock_error = Mock(spec=RequestValidationError)
        mock_error.errors.return_value = [{"field": "email", "message": "Invalid"}]

        response = await validation_exception_handler(mock_request, mock_error)

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 422
        assert response.media_type == "application/problem+json"

    async def test_general_exception_handler_arcp_exception(self):
        """Test general exception handler with ARCP exception."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/agents/test"

        exc = AgentNotFoundError("Agent not found", agent_id="test-agent")

        response = await general_exception_handler(mock_request, exc)

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        content = response.body.decode()
        assert '"agent_id":"test-agent"' in content

    async def test_general_exception_handler_generic_exception(self):
        """Test general exception handler with generic exception."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/test"

        exc = ValueError("Invalid input")

        response = await general_exception_handler(mock_request, exc)

        assert isinstance(response, ProblemResponse)
        assert response.status_code == 500
        assert response.media_type == "application/problem+json"


class TestSecuritySanitization:
    """Test security sanitization in Problem Details."""

    def test_xss_prevention(self):
        """Test XSS prevention in Problem Details."""
        problem = ProblemDetail.create_sanitized(
            type_uri="https://example.com/problems/test",
            detail="<script>alert('xss')</script>",
            custom_field="<img src=x onerror=alert(1)>",
        )

        assert (
            "&lt;[FILTERED]&gt;" in problem.detail or "&lt;script&gt;" in problem.detail
        )
        assert "[FILTERED]" in problem.custom_field

    def test_dangerous_strings_filtered(self):
        """Test dangerous strings are filtered."""
        problem = ProblemDetail.create_sanitized(
            type_uri="https://example.com/problems/test",
            detail="javascript:alert(1)",
            custom_field="document.cookie",
        )

        assert "[FILTERED]" in problem.detail
        assert "[FILTERED]" in problem.custom_field

    def test_length_limits(self):
        """Test length limits are enforced."""
        long_string = "A" * 1000

        problem = ProblemDetail.create_sanitized(
            type_uri="https://example.com/problems/test", detail=long_string
        )

        assert len(problem.detail) <= 503  # 500 + "..."


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_handle_exception_with_problem_details(self):
        """Test handle_exception_with_problem_details function."""
        import logging

        from src.arcp.core.exceptions import handle_exception_with_problem_details

        logger = logging.getLogger("test")

        exc = AgentNotFoundError("Agent not found", agent_id="test-agent")

        problem_response = handle_exception_with_problem_details(
            logger, "Test operation", exc, agent_id="test-agent"
        )

        assert hasattr(problem_response, "status_code")
        assert problem_response.status_code == 404


class TestRFC9457Compliance:
    """Test RFC 9457 compliance."""

    def test_required_content_type(self):
        """Test that Problem Details use the correct Content-Type."""
        response = ProblemResponse(ProblemDetail())

        assert response.media_type == "application/problem+json"

    def test_all_fields_optional(self):
        """Test that all Problem Detail fields are optional."""
        # Should not raise any validation errors
        problem = ProblemDetail()

        assert problem.type == "about:blank"  # Default value
        assert problem.title is None
        assert problem.status is None
        assert problem.detail is None
        assert problem.instance is None

    def test_type_uri_format(self):
        """Test that type URIs are properly formatted."""
        for attr_name in dir(ARCPProblemTypes):
            if not attr_name.startswith("_") and attr_name != "BASE_URI":
                problem_type = getattr(ARCPProblemTypes, attr_name)
                if isinstance(problem_type, dict) and "type" in problem_type:
                    type_uri = problem_type["type"]
                    # Should be a valid URI (basic check)
                    assert type_uri.startswith(("http://", "https://", "urn:"))

    def test_extension_fields_allowed(self):
        """Test that extension fields are allowed."""
        problem = ProblemDetail(
            type="https://example.com/problems/test",
            title="Test Problem",
            custom_field="custom_value",
            another_field=123,
        )

        assert problem.custom_field == "custom_value"
        assert problem.another_field == 123

        # Should appear in serialized output
        problem_dict = problem.dict()
        assert "custom_field" in problem_dict
        assert "another_field" in problem_dict
