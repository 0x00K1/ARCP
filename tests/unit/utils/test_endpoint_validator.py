"""
Unit tests for TPR endpoint validator.

Tests the EndpointValidator class and validation functions for ARCP contract compliance.
Tests both Static and Dynamic validation modes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcp.utils.endpoint_validator import (
    STATIC_ENDPOINTS,
    DynamicEndpointSchema,
    EndpointCheckResult,
    EndpointValidationResult,
    EndpointValidator,
    ValidationError,
    ValidationWarning,
    validate_agent_endpoints,
    validate_field,
    validate_response_schema,
)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for testing."""
    with patch("arcp.utils.endpoint_validator.httpx.AsyncClient") as mock:
        yield mock


@pytest.fixture
def endpoint_validator():
    """Create EndpointValidator instance for testing in static mode."""
    return EndpointValidator(
        agent_id="test-agent-001",
        agent_endpoint="https://agent.example.com:8443",
        declared_capabilities=["rag", "function_calling"],
        mode="static",
    )


class TestEndpointValidator:
    """Test EndpointValidator class."""

    def test_init_validator_static_mode(self):
        """Test EndpointValidator initialization with static mode."""
        validator = EndpointValidator(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag", "function_calling"],
            mode="static",
        )

        assert validator.agent_endpoint == "https://agent.example.com:8443"
        assert validator.agent_id == "test-agent-001"
        assert validator.declared_capabilities == ["rag", "function_calling"]
        assert validator.mode == "static"
        assert len(validator.endpoints) == 14  # 14 static endpoints (v1.0.0)

    def test_init_validator_strips_trailing_slash(self):
        """Test validator strips trailing slash from agent_endpoint."""
        validator = EndpointValidator(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443/",
            declared_capabilities=["rag"],
        )

        assert validator.agent_endpoint == "https://agent.example.com:8443"

    def test_static_endpoints_defined(self):
        """Test that static endpoints are properly defined."""
        assert len(STATIC_ENDPOINTS) == 14  # v1.0.0 standard

        paths = [ep.path for ep in STATIC_ENDPOINTS]
        # Core service endpoints
        assert "/" in paths
        assert "/ping" in paths
        # Health & monitoring endpoints
        assert "/health" in paths
        assert "/health/detailed" in paths
        assert "/metrics" in paths
        # ARCP integration endpoints
        assert "/agents/{agent_id}/heartbeat" in paths
        assert "/agents/{agent_id}/metrics" in paths
        assert "/agents/report-metrics/{agent_id}" in paths
        # Connection management endpoints
        assert "/connection/request" in paths
        assert "/connection/configure" in paths
        assert "/connection/status/{user_id}" in paths
        assert "/connection/disconnect" in paths
        assert "/connection/notify" in paths
        # Discovery endpoints
        assert "/search/agents" in paths

    def test_static_endpoints_health_required(self):
        """Test that /health endpoint is required."""
        health_ep = next(ep for ep in STATIC_ENDPOINTS if ep.path == "/health")
        assert health_ep.required is True
        assert health_ep.method == "GET"
        assert health_ep.timeout == 5
        assert "status" in health_ep.required_fields
        assert "agent_id" in health_ep.required_fields
        assert "timestamp" in health_ep.required_fields

    def test_static_endpoints_metrics_required(self):
        """Test that /metrics endpoint is required."""
        metrics_ep = next(ep for ep in STATIC_ENDPOINTS if ep.path == "/metrics")
        assert metrics_ep.required is True
        assert metrics_ep.timeout == 10


class TestValidateField:
    """Test field-level validation logic."""

    def test_validate_string_field_success(self):
        """Test successful string field validation."""
        errors = validate_field("status", "healthy", {"type": "string"})
        assert len(errors) == 0

    def test_validate_string_field_wrong_type(self):
        """Test string field with wrong type."""
        errors = validate_field("status", 123, {"type": "string"})
        assert len(errors) == 1
        assert "expected string" in errors[0].lower()

    def test_validate_enum_field_success(self):
        """Test successful enum validation."""
        errors = validate_field(
            "status",
            "healthy",
            {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
        )
        assert len(errors) == 0

    def test_validate_enum_field_invalid(self):
        """Test enum validation with invalid value."""
        errors = validate_field(
            "status",
            "unknown",
            {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
        )
        assert len(errors) == 1
        assert "not in allowed values" in errors[0].lower()

    def test_validate_pattern_field_success(self):
        """Test successful pattern validation."""
        errors = validate_field(
            "agent_id",
            "test-agent-001",
            {"type": "string", "pattern": r"^[a-zA-Z0-9_-]{3,64}$"},
        )
        assert len(errors) == 0

    def test_validate_pattern_field_invalid(self):
        """Test pattern validation with non-matching value."""
        errors = validate_field(
            "agent_id",
            "ab",  # Too short
            {"type": "string", "pattern": r"^[a-zA-Z0-9_-]{3,64}$"},
        )
        assert len(errors) == 1
        assert "doesn't match pattern" in errors[0].lower()

    def test_validate_integer_min_success(self):
        """Test integer min validation success."""
        errors = validate_field("uptime", 100, {"type": "integer", "min": 0})
        assert len(errors) == 0

    def test_validate_integer_min_fail(self):
        """Test integer min validation failure."""
        errors = validate_field("uptime", -5, {"type": "integer", "min": 0})
        assert len(errors) == 1
        assert "below minimum" in errors[0].lower()

    def test_validate_optional_field_missing(self):
        """Test optional field that is missing."""
        errors = validate_field("version", None, {"type": "string", "required": False})
        assert len(errors) == 0

    def test_validate_required_field_missing(self):
        """Test required field that is missing."""
        errors = validate_field("status", None, {"type": "string", "required": True})
        assert len(errors) == 1
        assert "missing" in errors[0].lower()


class TestValidateResponseSchema:
    """Test response schema validation."""

    def test_validate_response_all_fields_present(self):
        """Test validation when all required fields are present."""
        data = {"status": "healthy", "agent_id": "test-001"}
        errors = validate_response_schema(
            data,
            required_fields=["status", "agent_id"],
            field_validations=None,
        )
        assert len(errors) == 0

    def test_validate_response_missing_required_field(self):
        """Test validation when required field is missing."""
        data = {"status": "healthy"}
        errors = validate_response_schema(
            data,
            required_fields=["status", "agent_id"],
            field_validations=None,
        )
        assert len(errors) == 1
        assert "agent_id" in errors[0]

    def test_validate_response_with_field_validations(self):
        """Test validation with field-level rules."""
        data = {
            "status": "healthy",
            "agent_id": "test-agent-001",
        }
        errors = validate_response_schema(
            data,
            required_fields=["status", "agent_id"],
            field_validations={
                "status": {
                    "type": "string",
                    "enum": ["healthy", "degraded", "unhealthy"],
                },
                "agent_id": {"type": "string"},
            },
        )
        assert len(errors) == 0

    def test_validate_response_invalid_field_value(self):
        """Test validation when field value is invalid."""
        data = {
            "status": "unknown",  # Invalid enum value
            "agent_id": "test-agent-001",
        }
        errors = validate_response_schema(
            data,
            required_fields=["status", "agent_id"],
            field_validations={
                "status": {
                    "type": "string",
                    "enum": ["healthy", "degraded", "unhealthy"],
                },
            },
        )
        assert len(errors) == 1
        assert "not in allowed values" in errors[0].lower()


class TestDynamicEndpointSchema:
    """Test DynamicEndpointSchema model."""

    def test_create_basic_endpoint(self):
        """Test creating a basic dynamic endpoint definition."""
        ep = DynamicEndpointSchema(
            path="/custom-health",
            method="GET",
            timeout=5,
            required_fields=["status"],
        )
        assert ep.path == "/custom-health"
        assert ep.method == "GET"
        assert ep.timeout == 5
        assert ep.required is True  # Default
        assert ep.expected_status == [200]  # Default

    def test_create_post_endpoint_with_body(self):
        """Test creating a POST endpoint with request body."""
        ep = DynamicEndpointSchema(
            path="/custom-notify",
            method="POST",
            timeout=10,
            request_body={"event": "test"},
            required_fields=["acknowledged"],
        )
        assert ep.method == "POST"
        assert ep.request_body == {"event": "test"}

    def test_create_optional_endpoint(self):
        """Test creating an optional endpoint."""
        ep = DynamicEndpointSchema(
            path="/optional-endpoint",
            required=False,
        )
        assert ep.required is False


class TestEndpointValidationResult:
    """Test EndpointValidationResult container."""

    def test_create_result(self):
        """Test creating validation result."""
        result = EndpointValidationResult("test-agent", "static")
        assert result.agent_id == "test-agent"
        assert result.mode == "static"
        assert result.is_valid() is True  # No errors yet

    def test_add_error_makes_invalid(self):
        """Test that adding error makes result invalid."""
        result = EndpointValidationResult("test-agent", "static")
        result.add_error(
            ValidationError(
                endpoint="/health",
                type="connection_error",
                message="Connection refused",
            )
        )
        assert result.is_valid() is False

    def test_add_warning_stays_valid(self):
        """Test that warnings don't affect validity."""
        result = EndpointValidationResult("test-agent", "static")
        result.add_warning(
            ValidationWarning(
                endpoint="/metrics",
                type="empty_response",
                message="Empty metrics response",
            )
        )
        assert result.is_valid() is True

    def test_get_summary(self):
        """Test getting validation summary."""
        result = EndpointValidationResult("test-agent", "static")
        result.add_check(
            EndpointCheckResult(
                endpoint="/health",
                method="GET",
                status="passed",
                response_time_ms=45,
            )
        )
        result.complete()

        summary = result.get_summary()
        assert summary["agent_id"] == "test-agent"
        assert summary["mode"] == "static"
        assert summary["valid"] is True
        assert "GET:/health" in summary["checks"]


class TestValidationFunctions:
    """Test high-level validation functions."""

    @pytest.mark.asyncio
    async def test_validate_agent_endpoints_static_success(self, mock_httpx_client):
        """Test static validation with all endpoints succeeding."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "status": "healthy",
            "agent_id": "test-agent-001",
            "capabilities": ["rag"],
            "requests_total": 100,
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        assert result.agent_id == "test-agent-001"
        assert result.mode == "static"

    @pytest.mark.asyncio
    async def test_validate_agent_endpoints_static_timeout(self, mock_httpx_client):
        """Test static validation with timeout."""
        import httpx

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        mock_client_instance.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        assert result.agent_id == "test-agent-001"
        # Should have errors for required endpoints
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_validate_agent_endpoints_dynamic(self, mock_httpx_client):
        """Test dynamic validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Dynamic mode without config falls back to static
        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="dynamic",
        )

        assert result.agent_id == "test-agent-001"

    @pytest.mark.asyncio
    async def test_validate_agent_endpoints_main_entry(self, mock_httpx_client):
        """Test main entry point function."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "status": "healthy",
            "agent_id": "test-agent-001",
            "capabilities": ["rag"],
            "requests_total": 100,
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Test with explicit mode
        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        assert result.mode == "static"


class TestEndpointValidation:
    """Test specific endpoint validation scenarios."""

    @pytest.mark.asyncio
    async def test_health_endpoint_identity_mismatch(self, mock_httpx_client):
        """Test that agent_id mismatch is detected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "status": "healthy",
            "agent_id": "different-agent",  # Wrong agent_id
            "capabilities": ["rag"],
            "requests_total": 100,
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        # Should have identity mismatch error
        identity_errors = [e for e in result.errors if e.type == "identity_mismatch"]
        assert len(identity_errors) > 0

    @pytest.mark.asyncio
    async def test_metrics_prometheus_format_accepted(self, mock_httpx_client):
        """Test that Prometheus format metrics are accepted."""
        mock_json_response = MagicMock()
        mock_json_response.status_code = 200
        mock_json_response.headers = {"content-type": "application/json"}
        mock_json_response.json.return_value = {
            "status": "healthy",
            "agent_id": "test-agent-001",
            "capabilities": ["rag"],
        }

        mock_metrics_response = MagicMock()
        mock_metrics_response.status_code = 200
        mock_metrics_response.headers = {"content-type": "text/plain"}
        mock_metrics_response.text = "# HELP requests_total\nrequests_total 100\n"
        mock_metrics_response.json.side_effect = Exception("Not JSON")

        mock_client_instance = AsyncMock()

        # Return different responses based on the endpoint
        async def mock_get(url, **kwargs):
            if "/metrics" in url:
                return mock_metrics_response
            return mock_json_response

        mock_client_instance.get = mock_get
        mock_client_instance.post = AsyncMock(return_value=mock_json_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        # Metrics should pass with Prometheus format
        metrics_check = result.checks.get("GET:/metrics")
        assert metrics_check is not None
        assert metrics_check.status in ["passed", "warning"]

    @pytest.mark.asyncio
    async def test_optional_endpoint_failure_is_warning(self, mock_httpx_client):
        """Test that optional endpoint failure is a warning, not an error."""
        import httpx

        mock_json_response = MagicMock()
        mock_json_response.status_code = 200
        mock_json_response.headers = {"content-type": "application/json"}
        mock_json_response.json.return_value = {
            "status": "healthy",
            "agent_id": "test-agent-001",
            "capabilities": ["rag"],
        }

        mock_client_instance = AsyncMock()

        # Return different responses based on the endpoint
        async def mock_get(url, **kwargs):
            # /search/agents and /agents/{agent_id}/metrics are optional endpoints
            if "/search/agents" in url:
                raise httpx.TimeoutException("Timeout")
            return mock_json_response

        mock_client_instance.get = mock_get
        mock_client_instance.post = AsyncMock(return_value=mock_json_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await validate_agent_endpoints(
            agent_id="test-agent-001",
            agent_endpoint="https://agent.example.com:8443",
            declared_capabilities=["rag"],
            mode="static",
        )

        # /search/agents is optional, so failure should be a warning
        search_check = result.checks.get("GET:/search/agents")
        assert search_check is not None
        assert search_check.status == "warning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
