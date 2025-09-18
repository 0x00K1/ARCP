"""
RFC 9457 Problem Details for HTTP APIs - ARCP.

This module provides standardized error handling using RFC 9457 Problem Details
for all API error responses.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..utils.security_sanitizer import SecuritySanitizer

# =============================================================================
# RFC 9457 Problem Details for HTTP APIs Implementation
# =============================================================================


class ProblemDetail(BaseModel):
    """
    RFC 9457 Problem Details object.

    Represents an error condition in a standardized, machine-readable format.
    All fields are optional per the RFC, but type and title are recommended.
    """

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type",
    )
    title: Optional[str] = Field(
        default=None,
        description="Short, human-readable summary of the problem type",
    )
    status: Optional[int] = Field(
        default=None,
        description="HTTP status code for this occurrence of the problem",
    )
    detail: Optional[str] = Field(
        default=None,
        description="Human-readable explanation specific to this occurrence",
    )
    instance: Optional[str] = Field(
        default=None,
        description="URI reference identifying this specific occurrence",
    )

    # ARCP-specific extensions
    timestamp: Optional[str] = Field(
        default=None,
        description="Timestamp when the problem occurred (ISO format)",
    )
    request_id: Optional[str] = Field(
        default=None, description="Request ID for tracing"
    )

    class Config:
        extra = "allow"  # Allow additional custom fields

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        super().__init__(**data)

    @classmethod
    def create_sanitized(
        cls,
        type_uri: str = "about:blank",
        title: Optional[str] = None,
        status: Optional[int] = None,
        detail: Optional[str] = None,
        instance: Optional[str] = None,
        request: Optional[Request] = None,
        **extensions: Any,
    ) -> ProblemDetail:
        """
        Create a Problem Detail with security sanitization applied.

        Args:
            type_uri: Problem type URI
            title: Problem title
            status: HTTP status code
            detail: Detailed explanation
            instance: Instance URI (auto-generated from request if not provided)
            request: FastAPI Request object for context
            **extensions: Additional custom fields

        Returns:
            Sanitized ProblemDetail instance
        """
        # Sanitize all string fields
        sanitized_data = {
            "type": SecuritySanitizer.sanitize_string(str(type_uri), 200),
        }

        if title:
            sanitized_data["title"] = SecuritySanitizer.sanitize_string(title, 100)

        if status:
            sanitized_data["status"] = int(status)

        if detail:
            sanitized_data["detail"] = SecuritySanitizer.sanitize_string(detail, 500)

        # Generate instance URI from request if not provided
        if instance:
            sanitized_data["instance"] = SecuritySanitizer.sanitize_string(
                instance, 200
            )
        elif request:
            # Use the request path as instance identifier
            sanitized_data["instance"] = str(request.url.path)

        # Add request ID if available
        if request and hasattr(request.state, "request_id"):
            request_id = request.state.request_id
            if request_id:
                sanitized_data["request_id"] = SecuritySanitizer.sanitize_string(
                    str(request_id), 100
                )

        # Sanitize extension fields
        for key, value in extensions.items():
            safe_key = SecuritySanitizer.sanitize_string(str(key), 50)
            if isinstance(value, str):
                sanitized_data[safe_key] = SecuritySanitizer.sanitize_string(value, 200)
            else:
                # For non-string values, convert to string and sanitize
                sanitized_data[safe_key] = SecuritySanitizer.sanitize_string(
                    str(value), 200
                )

        return cls(**sanitized_data)


class ProblemResponse(JSONResponse):
    """
    FastAPI response class for RFC 9457 Problem Details.

    Automatically sets the correct Content-Type and formats the response.
    """

    media_type = "application/problem+json"

    def __init__(
        self,
        problem: Union[ProblemDetail, Dict[str, Any]],
        status_code: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """
        Create a Problem Details response.

        Args:
            problem: ProblemDetail instance or dictionary
            status_code: HTTP status code (uses problem.status if not provided)
            headers: Additional headers
            **kwargs: Additional arguments for JSONResponse
        """
        if isinstance(problem, ProblemDetail):
            content = problem.dict(exclude_none=True)
            if status_code is None:
                status_code = problem.status
        else:
            content = problem
            if status_code is None:
                status_code = problem.get("status", 500)

        # Ensure status code is valid
        if status_code is None:
            status_code = 500

        super().__init__(
            content=content, status_code=status_code, headers=headers, **kwargs
        )


class ProblemException(Exception):
    """
    Exception class that can be automatically converted to Problem Details.

    This allows raising domain-specific exceptions that are automatically
    converted to RFC 9457 Problem Details responses.
    """

    def __init__(
        self,
        type_uri: str = "about:blank",
        title: Optional[str] = None,
        status: int = 500,
        detail: Optional[str] = None,
        instance: Optional[str] = None,
        **extensions: Any,
    ):
        self.type_uri = type_uri
        self.title = title
        self.status = status
        self.detail = detail or str(self)
        self.instance = instance
        self.extensions = extensions

        super().__init__(self.detail)

    def to_problem_detail(self, request: Optional[Request] = None) -> ProblemDetail:
        """Convert this exception to a ProblemDetail object."""
        return ProblemDetail.create_sanitized(
            type_uri=self.type_uri,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=self.instance,
            request=request,
            **self.extensions,
        )

    def to_response(self, request: Optional[Request] = None) -> ProblemResponse:
        """Convert this exception to a Problem Details response."""
        problem = self.to_problem_detail(request)
        return ProblemResponse(problem)


# Problem type registry for ARCP-specific problem types
class ARCPProblemTypes:
    """Registry of ARCP-specific problem type URIs and metadata."""

    BASE_URI = "https://arcp.0x001.tech/docs/problems"

    # Agent-related problems
    AGENT_NOT_FOUND = {
        "type": f"{BASE_URI}/agent-not-found",
        "title": "Agent Not Found",
        "default_status": 404,
    }

    DUPLICATE_AGENT = {
        "type": f"{BASE_URI}/duplicate-agent",
        "title": "Duplicate Agent",
        "default_status": 409,
    }

    AGENT_REGISTRATION_ERROR = {
        "type": f"{BASE_URI}/agent-registration-failed",
        "title": "Agent Registration Failed",
        "default_status": 400,
    }

    AGENT_NOT_AVAILABLE = {
        "type": f"{BASE_URI}/agent-not-available",
        "title": "Agent Not Available",
        "default_status": 404,
    }

    # Authentication problems
    AUTHENTICATION_FAILED = {
        "type": f"{BASE_URI}/authentication-failed",
        "title": "Authentication Failed",
        "default_status": 401,
    }

    TOKEN_VALIDATION_ERROR = {
        "type": f"{BASE_URI}/token-invalid",
        "title": "Invalid or Expired Token",
        "default_status": 401,
    }

    SESSION_VALIDATION_FAILED = {
        "type": f"{BASE_URI}/session-invalid",
        "title": "Session Validation Failed",
        "default_status": 401,
    }

    SESSION_EXPIRED = {
        "type": f"{BASE_URI}/session-expired",
        "title": "Session Expired",
        "default_status": 401,
    }

    # Authorization problems
    INSUFFICIENT_PERMISSIONS = {
        "type": f"{BASE_URI}/insufficient-permissions",
        "title": "Insufficient Permissions",
        "default_status": 403,
    }

    # PIN-related problems
    PIN_REQUIRED = {
        "type": f"{BASE_URI}/pin-required",
        "title": "PIN Required",
        "default_status": 400,
    }

    PIN_ALREADY_SET = {
        "type": f"{BASE_URI}/pin-already-set",
        "title": "PIN Already Set",
        "default_status": 400,
    }

    PIN_NOT_SET = {
        "type": f"{BASE_URI}/pin-not-set",
        "title": "PIN Not Set",
        "default_status": 400,
    }

    PIN_INCORRECT = {
        "type": f"{BASE_URI}/pin-incorrect",
        "title": "Incorrect PIN",
        "default_status": 401,
    }

    PIN_INVALID_LENGTH = {
        "type": f"{BASE_URI}/pin-invalid-length",
        "title": "Invalid PIN Length",
        "default_status": 400,
    }

    # Configuration problems
    CONFIGURATION_ERROR = {
        "type": f"{BASE_URI}/configuration-error",
        "title": "Service Configuration Error",
        "default_status": 500,
    }

    # Service problems
    VECTOR_SEARCH_ERROR = {
        "type": f"{BASE_URI}/vector-search-unavailable",
        "title": "Vector Search Unavailable",
        "default_status": 500,
    }

    TIMEOUT_ERROR = {
        "type": f"{BASE_URI}/operation-timeout",
        "title": "Operation Timeout",
        "default_status": 504,
    }

    CONNECTION_TIMEOUT = {
        "type": f"{BASE_URI}/connection-timeout",
        "title": "Connection Timeout",
        "default_status": 504,
    }

    ENDPOINT_UNREACHABLE = {
        "type": f"{BASE_URI}/endpoint-unreachable",
        "title": "Endpoint Unreachable",
        "default_status": 502,
    }

    # Validation problems
    VALIDATION_ERROR = {
        "type": f"{BASE_URI}/validation-failed",
        "title": "Request Validation Failed",
        "default_status": 422,
    }

    INVALID_INPUT = {
        "type": f"{BASE_URI}/invalid-input",
        "title": "Invalid Input Data",
        "default_status": 400,
    }

    REQUIRED_HEADER_MISSING = {
        "type": f"{BASE_URI}/required-header-missing",
        "title": "Required Header Missing",
        "default_status": 400,
    }

    INVALID_URL = {
        "type": f"{BASE_URI}/invalid-url",
        "title": "Invalid URL Format",
        "default_status": 400,
    }

    # Rate limiting problems
    RATE_LIMIT_EXCEEDED = {
        "type": f"{BASE_URI}/rate-limit-exceeded",
        "title": "Rate Limit Exceeded",
        "default_status": 429,
    }

    # Request size problems
    REQUEST_TOO_LARGE = {
        "type": f"{BASE_URI}/request-too-large",
        "title": "Request Too Large",
        "default_status": 413,
    }

    HEADERS_TOO_LARGE = {
        "type": f"{BASE_URI}/headers-too-large",
        "title": "Request Headers Too Large",
        "default_status": 413,
    }

    # Generic problems
    INTERNAL_ERROR = {
        "type": f"{BASE_URI}/internal-error",
        "title": "Internal Server Error",
        "default_status": 500,
    }

    REQUEST_ERROR = {
        "type": f"{BASE_URI}/request-error",
        "title": "Request Processing Error",
        "default_status": 400,
    }

    FORBIDDEN = {
        "type": f"{BASE_URI}/forbidden",
        "title": "Forbidden",
        "default_status": 403,
    }

    NOT_FOUND = {
        "type": f"{BASE_URI}/not-found",
        "title": "Resource Not Found",
        "default_status": 404,
    }


# =============================================================================
# Enhanced ARCP Exception Classes
# =============================================================================


class ARCPException(Exception):
    """Base exception for ARCP-specific errors with RFC 9457 Problem Details support."""

    # Default problem type for this exception class
    problem_type = ARCPProblemTypes.INTERNAL_ERROR

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_problem_detail(self, request: Optional[Request] = None) -> ProblemDetail:
        """Convert this exception to RFC 9457 Problem Details."""
        return ProblemDetail.create_sanitized(
            type_uri=self.problem_type["type"],
            title=self.problem_type["title"],
            status=self.problem_type["default_status"],
            detail=self.message,
            request=request,
            **self.details,
        )

    def to_problem_response(self, request: Optional[Request] = None) -> ProblemResponse:
        """Convert this exception to a Problem Details response."""
        return ProblemResponse(self.to_problem_detail(request))


class AgentRegistrationError(ARCPException):
    """Exception raised during agent registration."""

    problem_type = ARCPProblemTypes.AGENT_REGISTRATION_ERROR


class DuplicateAgentError(AgentRegistrationError):
    """Exception raised when attempting to register an already registered agent."""

    problem_type = ARCPProblemTypes.DUPLICATE_AGENT


class AgentNotFoundError(ARCPException):
    """Exception raised when agent is not found."""

    problem_type = ARCPProblemTypes.AGENT_NOT_FOUND

    def __init__(self, message: str, agent_id: Optional[str] = None, **details):
        super().__init__(message, details)
        if agent_id:
            self.details["agent_id"] = agent_id


class ConfigurationError(ARCPException):
    """Exception raised for configuration-related errors."""

    problem_type = ARCPProblemTypes.CONFIGURATION_ERROR


class AuthenticationError(ARCPException):
    """Exception raised for authentication failures."""

    problem_type = ARCPProblemTypes.AUTHENTICATION_FAILED


class TokenValidationError(ARCPException):
    """Exception raised for token validation failures."""

    problem_type = ARCPProblemTypes.TOKEN_VALIDATION_ERROR


class VectorSearchError(ARCPException):
    """Exception raised during vector search operations."""

    problem_type = ARCPProblemTypes.VECTOR_SEARCH_ERROR


# =============================================================================
# FastAPI Exception Handlers
# =============================================================================


async def problem_exception_handler(request: Request, exc: ProblemException):
    """Handle ProblemException specifically."""
    return exc.to_response(request)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with RFC 9457 Problem Details."""
    logging.getLogger(__name__).warning(
        f"Validation error on {request.url.path}: {exc}"
    )
    return validation_error_problem(exc.errors(), request)


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with RFC 9457 Problem Details."""
    logging.getLogger(__name__).error(
        f"Unexpected error on {request.url.path}: {exc}", exc_info=True
    )

    # Check if it's a ProblemException that can be converted to Problem Details
    if isinstance(exc, ProblemException):
        return exc.to_response(request)

    # Check if it's an ARCP exception that can be converted to Problem Details
    if isinstance(exc, ARCPException):
        return exc.to_problem_response(request)

    # For other exceptions, create a generic internal error Problem Detail
    return create_problem_response(
        problem_type=ARCPProblemTypes.INTERNAL_ERROR,
        detail="An unexpected error occurred. Try again later.",
        request=request,
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(ProblemException, problem_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


# =============================================================================
# Problem Details Helper Functions
# =============================================================================


def create_problem_detail(
    problem_type: Dict[str, Any],
    detail: Optional[str] = None,
    instance: Optional[str] = None,
    request: Optional[Request] = None,
    **extensions: Any,
) -> ProblemDetail:
    """
    Create a Problem Detail from an ARCP problem type definition.

    Args:
        problem_type: Problem type from ARCPProblemTypes
        detail: Specific detail message
        instance: Instance URI
        request: FastAPI Request object
        **extensions: Additional custom fields

    Returns:
        ProblemDetail instance
    """
    return ProblemDetail.create_sanitized(
        type_uri=problem_type["type"],
        title=problem_type["title"],
        status=problem_type["default_status"],
        detail=detail,
        instance=instance,
        request=request,
        **extensions,
    )


def create_problem_response(
    problem_type: Dict[str, Any],
    detail: Optional[str] = None,
    instance: Optional[str] = None,
    request: Optional[Request] = None,
    **extensions: Any,
) -> ProblemResponse:
    """
    Create a Problem Details response from an ARCP problem type definition.

    Args:
        problem_type: Problem type from ARCPProblemTypes
        detail: Specific detail message
        instance: Instance URI
        request: FastAPI Request object
        **extensions: Additional custom fields

    Returns:
        ProblemResponse for FastAPI
    """
    problem = create_problem_detail(
        problem_type=problem_type,
        detail=detail,
        instance=instance,
        request=request,
        **extensions,
    )
    return ProblemResponse(problem)


def raise_problem(
    problem_type: Dict[str, Any],
    detail: str,
    logger: logging.Logger,
    operation: str,
    request: Optional[Request] = None,
    **extensions: Any,
) -> None:
    """
    Create and raise a Problem Details exception with logging.

    Args:
        problem_type: Problem type from ARCPProblemTypes
        detail: Specific error detail
        logger: Logger instance
        operation: Operation being performed
        request: FastAPI Request object
        **extensions: Additional custom fields

    Raises:
        ProblemException
    """
    context_parts = []
    for key, value in extensions.items():
        if key in ["agent_id", "user_id", "session_id"]:
            context_parts.append(f"{key}={value}")

    context_str = f" ({', '.join(context_parts)})" if context_parts else ""
    logger.error(f"{operation} failed{context_str}: {detail}")

    raise ProblemException(
        type_uri=problem_type["type"],
        title=problem_type["title"],
        status=problem_type["default_status"],
        detail=detail,
        instance=request.url.path if request else None,
        **extensions,
    )


def handle_exception_with_problem_details(
    logger: logging.Logger,
    operation: str,
    exception: Exception,
    request: Optional[Request] = None,
    **context: Any,
) -> ProblemResponse:
    """
    Handle any exception and convert to Problem Details response.

    Args:
        logger: Logger instance for the calling module
        operation: Description of the operation that failed
        exception: The caught exception
        request: FastAPI Request object
        **context: Additional context (agent_id, user_id, etc.)

    Returns:
        ProblemResponse with appropriate Problem Details
    """
    # Build context string for logging
    context_parts = []
    for key, value in context.items():
        if key in ["agent_id", "user_id", "session_id"] and value:
            context_parts.append(f"{key}={value}")
    context_str = f" ({', '.join(context_parts)})" if context_parts else ""

    # Log the error with full context
    logger.error(f"{operation} failed{context_str}: {str(exception)}")

    # Handle ARCP exceptions first
    if isinstance(exception, ARCPException):
        # Add context to the exception details
        for key, value in context.items():
            if value is not None:
                exception.details[key] = value
        return exception.to_problem_response(request)

    # Handle standard exceptions
    if isinstance(exception, asyncio.TimeoutError):
        problem_type = ARCPProblemTypes.TIMEOUT_ERROR
        detail = f"{operation} timeout"
    elif isinstance(exception, ValueError):
        problem_type = ARCPProblemTypes.INVALID_INPUT
        detail = str(exception)
    else:
        # Generic error handling
        problem_type = ARCPProblemTypes.INTERNAL_ERROR
        detail = f"{operation} failed: {str(exception)}"

    return create_problem_response(
        problem_type=problem_type, detail=detail, request=request, **context
    )


# Convenience functions for common ARCP problem types
def agent_not_found_problem(
    agent_id: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create an Agent Not Found problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.AGENT_NOT_FOUND,
        detail=f"Agent '{agent_id}' was not found in the registry",
        request=request,
        agent_id=agent_id,
    )


def agent_not_available_problem(
    agent_id: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create an Agent Not Available problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.AGENT_NOT_AVAILABLE,
        detail=f"Agent '{agent_id}' is not available for connections",
        request=request,
        agent_id=agent_id,
    )


def authentication_failed_problem(
    reason: Optional[str] = None, request: Optional[Request] = None
) -> ProblemResponse:
    """Create an Authentication Failed problem response."""
    detail = f"Authentication failed: {reason}" if reason else "Authentication failed"
    return create_problem_response(
        problem_type=ARCPProblemTypes.AUTHENTICATION_FAILED,
        detail=detail,
        request=request,
    )


def session_validation_failed_problem(
    reason: Optional[str] = None, request: Optional[Request] = None
) -> ProblemResponse:
    """Create a Session Validation Failed problem response."""
    detail = (
        f"Session validation failed: {reason}"
        if reason
        else "Session validation failed"
    )
    return create_problem_response(
        problem_type=ARCPProblemTypes.SESSION_VALIDATION_FAILED,
        detail=detail,
        request=request,
    )


def session_expired_problem(
    request: Optional[Request] = None,
) -> ProblemResponse:
    """Create a Session Expired problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.SESSION_EXPIRED,
        detail="Session has expired",
        request=request,
    )


def invalid_input_problem(
    field: str, reason: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create an Invalid Input problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.INVALID_INPUT,
        detail=f"Invalid {field}: {reason}",
        request=request,
        field=field,
    )


def required_header_missing_problem(
    header_name: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create a Required Header Missing problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.REQUIRED_HEADER_MISSING,
        detail=f"{header_name} header is required",
        request=request,
        header=header_name,
    )


def pin_problem(
    problem_type: Dict[str, Any],
    detail: str,
    request: Optional[Request] = None,
) -> ProblemResponse:
    """Create a PIN-related problem response."""
    return create_problem_response(
        problem_type=problem_type, detail=detail, request=request
    )


def validation_error_problem(
    errors: Any, request: Optional[Request] = None
) -> ProblemResponse:
    """Create a Validation Error problem response."""
    # Sanitize validation errors
    sanitized_errors = SecuritySanitizer.sanitize_error_detail(errors)

    return create_problem_response(
        problem_type=ARCPProblemTypes.VALIDATION_ERROR,
        detail=f"Input validation failed: {sanitized_errors}",
        request=request,
        validation_errors=sanitized_errors,
    )


def timeout_problem(
    operation: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create a Timeout problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.CONNECTION_TIMEOUT,
        detail=f"{operation} timed out",
        request=request,
    )


def endpoint_unreachable_problem(
    endpoint: str, request: Optional[Request] = None
) -> ProblemResponse:
    """Create an Endpoint Unreachable problem response."""
    return create_problem_response(
        problem_type=ARCPProblemTypes.ENDPOINT_UNREACHABLE,
        detail=f"Endpoint '{endpoint}' is unreachable",
        request=request,
        endpoint=endpoint,
    )


# Production-ready exports
__all__ = [
    # Problem Details classes
    "ProblemDetail",
    "ProblemResponse",
    "ProblemException",
    "ARCPProblemTypes",
    # ARCP Exception classes
    "ARCPException",
    "AgentRegistrationError",
    "DuplicateAgentError",
    "AgentNotFoundError",
    "ConfigurationError",
    "AuthenticationError",
    "TokenValidationError",
    "VectorSearchError",
    # Exception handlers
    "validation_exception_handler",
    "general_exception_handler",
    "register_exception_handlers",
    # Problem Details helpers
    "create_problem_detail",
    "create_problem_response",
    "raise_problem",
    "handle_exception_with_problem_details",
    # Convenience functions
    "agent_not_found_problem",
    "agent_not_available_problem",
    "authentication_failed_problem",
    "session_validation_failed_problem",
    "session_expired_problem",
    "invalid_input_problem",
    "required_header_missing_problem",
    "pin_problem",
    "validation_error_problem",
    "timeout_problem",
    "endpoint_unreachable_problem",
]
