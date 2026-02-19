"""
Unit tests for TPR validation models.

Tests all validation-related Pydantic models including SecurityBinding,
ValidationRequest, ValidationResult, and ValidatedTokenResponse.
"""

import pytest
from pydantic import ValidationError

from arcp.models.validation import SecurityBinding, ValidatedTokenResponse
from arcp.models.validation import ValidationError as ValidationErrorModel
from arcp.models.validation import (
    ValidationRequest,
    ValidationResult,
    ValidationWarning,
)


class TestSecurityBinding:
    """Test SecurityBinding model."""

    def test_create_valid_security_binding(self):
        """Test creating a valid SecurityBinding."""
        binding = SecurityBinding(
            code_hash="sha256:abc123",
            endpoint_hash="sha256:def456",
            jkt="sha256:ghi789",
            mtls_spki=None,
        )

        assert binding.code_hash == "sha256:abc123"
        assert binding.endpoint_hash == "sha256:def456"
        assert binding.jkt == "sha256:ghi789"
        assert binding.mtls_spki is None

    def test_security_binding_with_mtls(self):
        """Test SecurityBinding with mTLS SPKI."""
        binding = SecurityBinding(
            code_hash="sha256:abc123",
            endpoint_hash="sha256:def456",
            jkt="sha256:ghi789",
            mtls_spki="sha256:jkl012",
        )

        assert binding.mtls_spki == "sha256:jkl012"

    def test_security_binding_minimal(self):
        """Test SecurityBinding with minimal required fields."""
        binding = SecurityBinding(
            code_hash="sha256:abc123",
            endpoint_hash="sha256:def456",
        )

        assert binding.code_hash == "sha256:abc123"
        assert binding.endpoint_hash == "sha256:def456"
        assert binding.jkt is None
        assert binding.mtls_spki is None

    def test_security_binding_serialization(self):
        """Test SecurityBinding JSON serialization."""
        binding = SecurityBinding(
            code_hash="sha256:abc123",
            endpoint_hash="sha256:def456",
            jkt="sha256:ghi789",
        )

        data = binding.model_dump()
        assert data["code_hash"] == "sha256:abc123"
        assert data["endpoint_hash"] == "sha256:def456"
        assert data["jkt"] == "sha256:ghi789"

    def test_security_binding_deserialization(self):
        """Test SecurityBinding JSON deserialization."""
        data = {
            "code_hash": "sha256:abc123",
            "endpoint_hash": "sha256:def456",
            "jkt": "sha256:ghi789",
            "mtls_spki": "sha256:jkl012",
        }

        binding = SecurityBinding(**data)
        assert binding.code_hash == "sha256:abc123"
        assert binding.endpoint_hash == "sha256:def456"
        assert binding.jkt == "sha256:ghi789"
        assert binding.mtls_spki == "sha256:jkl012"


class TestValidationRequest:
    """Test ValidationRequest model."""

    def test_create_valid_validation_request(self):
        """Test creating a valid ValidationRequest."""
        request = ValidationRequest(
            agent_id="test-agent-001",
            agent_type="test",
            endpoint="https://agent.example.com:8443",
            capabilities=["rag", "function_calling"],
        )

        assert request.agent_id == "test-agent-001"
        assert request.agent_type == "test"
        assert request.endpoint == "https://agent.example.com:8443"
        assert request.capabilities == ["rag", "function_calling"]

    def test_validation_request_with_version(self):
        """Test ValidationRequest with optional version."""
        request = ValidationRequest(
            agent_id="test-agent-001",
            agent_type="test",
            endpoint="https://agent.example.com:8443",
            capabilities=["rag"],
            version="1.0.0",
        )

        assert request.version == "1.0.0"

    def test_validation_request_minimal(self):
        """Test ValidationRequest with minimal required fields."""
        request = ValidationRequest(
            agent_id="test-agent-001",
            agent_type="test",
            endpoint="https://agent.example.com:8443",
            capabilities=["rag"],
        )

        assert request.agent_id == "test-agent-001"
        assert request.agent_type == "test"

    def test_validation_request_invalid_agent_id(self):
        """Test ValidationRequest rejects invalid agent_id."""
        with pytest.raises(ValidationError):
            ValidationRequest(
                agent_id="ab",  # Too short (min 3)
                agent_type="test",
                endpoint="https://agent.example.com:8443",
                capabilities=["rag"],
            )


class TestValidationErrorModel:
    """Test ValidationError model."""

    def test_create_validation_error(self):
        """Test creating a ValidationError."""
        error = ValidationErrorModel(
            type="ENDPOINT_TIMEOUT",
            message="Health endpoint timed out after 3000ms",
            field="endpoint",
        )

        assert error.type == "ENDPOINT_TIMEOUT"
        assert error.message == "Health endpoint timed out after 3000ms"
        assert error.field == "endpoint"

    def test_validation_error_without_field(self):
        """Test ValidationError without specific field."""
        error = ValidationErrorModel(
            type="GENERAL_ERROR",
            message="Something went wrong",
        )

        assert error.type == "GENERAL_ERROR"
        assert error.message == "Something went wrong"
        assert error.field is None


class TestValidationWarning:
    """Test ValidationWarning model."""

    def test_create_validation_warning(self):
        """Test creating a ValidationWarning."""
        warning = ValidationWarning(
            type="SLOW_RESPONSE",
            message="Health endpoint responded slowly (850ms)",
        )

        assert warning.type == "SLOW_RESPONSE"
        assert warning.message == "Health endpoint responded slowly (850ms)"


class TestValidationResult:
    """Test ValidationResult model."""

    def test_create_successful_validation_result(self):
        """Test creating a successful ValidationResult."""
        result = ValidationResult(
            validation_id="val_abc123",
            agent_id="test-agent-001",
            status="passed",
            binding=SecurityBinding(
                code_hash="sha256:abc123",
                endpoint_hash="sha256:def456",
            ),
            endpoint_checks={
                "health": {"status": "passed", "response_time_ms": 45},
            },
        )

        assert result.validation_id == "val_abc123"
        assert result.agent_id == "test-agent-001"
        assert result.status == "passed"
        assert result.binding is not None
        assert "health" in result.endpoint_checks
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_create_failed_validation_result(self):
        """Test creating a failed ValidationResult."""
        result = ValidationResult(
            validation_id="val_abc123",
            agent_id="test-agent-001",
            status="failed",
            errors=[{"type": "ENDPOINT_TIMEOUT", "message": "Health check timed out"}],
        )

        assert result.status == "failed"
        assert len(result.errors) == 1
        assert result.errors[0]["type"] == "ENDPOINT_TIMEOUT"
        assert result.binding is None

    def test_validation_result_with_warnings(self):
        """Test ValidationResult with warnings."""
        result = ValidationResult(
            validation_id="val_abc123",
            agent_id="test-agent-001",
            status="passed",
            binding=SecurityBinding(
                code_hash="sha256:abc123",
                endpoint_hash="sha256:def456",
            ),
            warnings=[
                {"type": "SLOW_RESPONSE", "message": "Endpoint responded slowly"}
            ],
        )

        assert result.status == "passed"
        assert len(result.warnings) == 1
        assert result.warnings[0]["type"] == "SLOW_RESPONSE"

    def test_validation_result_serialization(self):
        """Test ValidationResult JSON serialization."""
        result = ValidationResult(
            validation_id="val_abc123",
            agent_id="test-agent-001",
            status="passed",
            binding=SecurityBinding(
                code_hash="sha256:abc123",
                endpoint_hash="sha256:def456",
            ),
        )

        data = result.model_dump()
        assert data["validation_id"] == "val_abc123"
        assert data["status"] == "passed"
        assert "binding" in data


class TestValidatedTokenResponse:
    """Test ValidatedTokenResponse model."""

    def test_create_validated_token_response(self):
        """Test creating a ValidatedTokenResponse."""
        response = ValidatedTokenResponse(
            validated_token="validated.token.here",
            validation_id="val_abc123",
            expires_in=300,
            token_type="bearer",
        )

        assert response.validated_token == "validated.token.here"
        assert response.validation_id == "val_abc123"
        assert response.expires_in == 300
        assert response.token_type == "bearer"

    def test_validated_token_response_serialization(self):
        """Test ValidatedTokenResponse JSON serialization."""
        response = ValidatedTokenResponse(
            validated_token="validated.token.here",
            validation_id="val_abc123",
            expires_in=300,
            token_type="bearer",
        )

        data = response.model_dump()
        assert data["validated_token"] == "validated.token.here"
        assert data["validation_id"] == "val_abc123"
        assert data["expires_in"] == 300
        assert data["token_type"] == "bearer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
