"""
Integration tests for complete TPR flow.

Tests the end-to-end Three-Phase Registration flow:
Phase 1: Request temp token → Phase 2: Validate compliance → Phase 3: Register agent
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from arcp.__main__ import app
from arcp.core.config import config


@pytest.fixture
def test_client_tpr():
    """FastAPI test client with TPR enabled and security enforcement disabled for flow testing.

    Security enforcement (DPoP/mTLS) is disabled here to test the TPR flow logic.
    Dedicated security tests in tests/security/ test DPoP/mTLS enforcement.
    """
    with (
        patch.object(config, "FEATURE_THREE_PHASE", True),
        patch.object(config, "DPOP_REQUIRED", False),
        patch.object(config, "DPOP_ENABLED", False),
        patch.object(config, "MTLS_REQUIRED_REMOTE", False),
        patch.object(config, "MTLS_ENABLED", False),
    ):
        with TestClient(app) as client:
            yield client
            # Cleanup after each test - reset the registry
            from arcp.core.registry import AgentRegistry

            registry = AgentRegistry()
            # Clear test agent data
            test_agent_ids = [
                k for k in registry.backup_agents.keys() if k.startswith("test-agent")
            ]
            for agent_id in test_agent_ids:
                registry.backup_agents.pop(agent_id, None)
                registry.backup_embeddings.pop(agent_id, None)
                registry.backup_metrics.pop(agent_id, None)
                registry.backup_info_hashes.pop(agent_id, None)
                registry.backup_agent_keys.pop(agent_id, None)


@pytest.fixture
def mock_validation_success():
    """Mock successful validation."""
    with (
        patch("arcp.core.validation.perform_fast_checks") as mock_fast,
        patch("arcp.core.validation.perform_endpoint_validation") as mock_endpoint,
        patch("arcp.core.validation.verify_capabilities") as mock_capabilities,
        patch("arcp.core.validation.create_security_binding") as mock_binding,
    ):

        from arcp.models.validation import SecurityBinding
        from arcp.utils.endpoint_validator import EndpointCheckResult

        # Mock successful validation stages
        mock_fast.return_value = (
            [],  # no errors
            [],  # no warnings
            {
                "health": EndpointCheckResult(
                    endpoint="/health", status="passed", response_time_ms=45
                )
            },
        )
        mock_endpoint.return_value = ([], [], {})
        mock_capabilities.return_value = ([], [])
        mock_binding.return_value = SecurityBinding(
            code_hash="sha256:abc123def456",
            endpoint_hash="sha256:789ghi012jkl",
        )

        yield


@pytest.fixture
def agent_registration_data():
    """Sample agent registration data with unique ID per test."""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    return {
        "agent_id": f"test-agent-tpr-{unique_id}",
        "name": "TPR Test Agent",
        "agent_type": "automation",
        "endpoint": "https://agent.example.com:8443",
        "context_brief": "A test agent for validating the Three-Phase Registration flow",
        "description": "Agent for testing Three-Phase Registration",
        "capabilities": ["rag", "function_calling"],
        "owner": "test-owner",
        "public_key": "test-public-key-abc123-def456-ghi789-jkl012",
        "version": "1.0.0",
        "communication_mode": "remote",
        "metadata": {
            "version": "1.0.0",
            "environment": "testing",
        },
    }


class TestTPRPhase1:
    """Test Phase 1: Request Temporary Token."""

    def test_request_temp_token_success(self, test_client_tpr):
        """Test requesting temporary token with valid registration key."""
        response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "agent_key": "test-registration-key-123",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "temp_token" in data
        assert "expires_in" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == config.TOKEN_TTL_TEMP

    def test_request_temp_token_invalid_key(self, test_client_tpr):
        """Test requesting temp token with invalid registration key."""
        response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "agent_key": "invalid-key",
            },
        )

        assert response.status_code == 401

    def test_request_temp_token_missing_key(self, test_client_tpr):
        """Test requesting temp token without registration key."""
        response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                # Missing agent_key
            },
        )

        assert (
            response.status_code == 400
        )  # Changed from 401 - missing field returns 400

    @pytest.mark.skip(
        reason="RATE_LIMIT_ENABLED attribute not available in config, rate limiting tested elsewhere"
    )
    def test_request_temp_token_rate_limit(self, test_client_tpr):
        """Test rate limiting on temp token requests."""
        # Make multiple requests
        for i in range(10):
            response = test_client_tpr.post(
                "/auth/agent/request_temp_token",
                json={
                    "agent_id": f"test-agent-{i:03d}",
                    "agent_type": "automation",
                    "agent_key": "test-registration-key-123",
                },
            )

            if i < 9:
                assert response.status_code in [200, 401]  # Either valid or invalid key
            else:
                assert response.status_code in [200, 401, 429]  # May be rate limited


class TestTPRPhase2:
    """Test Phase 2: Validate Compliance."""

    def test_validate_compliance_success(
        self, test_client_tpr, mock_validation_success
    ):
        """Test successful compliance validation with 202 Accepted and polling."""
        # Phase 1: Get temp token
        temp_response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "agent_key": "test-registration-key-123",
            },
        )
        assert (
            temp_response.status_code == 200
        ), f"Expected 200, got {temp_response.status_code}: {temp_response.text}"
        temp_token = temp_response.json()["temp_token"]

        # Phase 2: Validate compliance - now returns 202 Accepted with async polling
        with (
            patch("arcp.api.auth.enqueue_validation") as mock_enqueue,
            patch("arcp.api.auth.get_validation_result") as mock_get_result,
            patch("arcp.api.auth.get_validation_context") as mock_get_context,
            patch("arcp.api.auth.store_validation_context") as mock_store_context,
        ):

            from arcp.models.validation import SecurityBinding, ValidationResult

            mock_enqueue.return_value = "val_test123"
            mock_store_context.return_value = None
            mock_get_context.return_value = {}  # No security bindings in test

            # First call returns 202 Accepted
            response = test_client_tpr.post(
                "/auth/agent/validate_compliance",
                json={
                    "agent_id": "test-agent-001",
                    "agent_type": "automation",
                    "endpoint": "https://agent.example.com:8443",
                    "capabilities": ["rag"],
                },
                headers={"Authorization": f"Bearer {temp_token}"},
            )

            assert response.status_code == 202
            data = response.json()

            assert "validation_id" in data
            assert data["validation_id"] == "val_test123"
            assert data["status"] == "pending"
            assert "Location" in response.headers

            # Now simulate polling - mock the result as complete
            mock_get_result.return_value = ValidationResult(
                validation_id="val_test123",
                agent_id="test-agent-001",
                status="passed",
                binding=SecurityBinding(
                    code_hash="sha256:abc123",
                    endpoint_hash="sha256:def456",
                ),
            )

            # Poll the validation status
            poll_response = test_client_tpr.get(
                "/auth/agent/validation/val_test123",
                headers={"Authorization": f"Bearer {temp_token}"},
            )

            assert poll_response.status_code == 200
            poll_data = poll_response.json()

            assert poll_data["status"] == "passed"
            assert "validated_token" in poll_data
            assert poll_data["validation_id"] == "val_test123"

    def test_validate_compliance_without_temp_token(self, test_client_tpr):
        """Test validation without temp token fails."""
        response = test_client_tpr.post(
            "/auth/agent/validate_compliance",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "endpoint": "https://agent.example.com:8443",
                "capabilities": ["rag"],
            },
        )

        assert response.status_code == 401

    def test_validate_compliance_with_invalid_token(self, test_client_tpr):
        """Test validation with invalid temp token."""
        response = test_client_tpr.post(
            "/auth/agent/validate_compliance",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "endpoint": "https://agent.example.com:8443",
                "capabilities": ["rag"],
            },
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401

    def test_validate_compliance_validation_failure(self, test_client_tpr):
        """Test validation when agent fails compliance checks (via polling)."""
        # Get temp token
        temp_response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": "test-agent-001",
                "agent_type": "automation",
                "agent_key": "test-registration-key-123",
            },
        )
        temp_token = temp_response.json()["temp_token"]

        # Mock failed validation - first submit, then poll
        with (
            patch("arcp.api.auth.enqueue_validation") as mock_enqueue,
            patch("arcp.api.auth.get_validation_result") as mock_get_result,
            patch("arcp.api.auth.get_validation_context") as mock_get_context,
            patch("arcp.api.auth.store_validation_context") as mock_store_context,
        ):

            from arcp.models.validation import ValidationError, ValidationResult

            mock_enqueue.return_value = "val_test123"
            mock_store_context.return_value = None
            mock_get_context.return_value = {}  # No security bindings in test
            mock_get_result.return_value = None  # Not ready yet

            # Submit validation - returns 202 Accepted
            response = test_client_tpr.post(
                "/auth/agent/validate_compliance",
                json={
                    "agent_id": "test-agent-001",
                    "agent_type": "automation",
                    "endpoint": "https://agent.example.com:8443",
                    "capabilities": ["rag"],
                },
                headers={"Authorization": f"Bearer {temp_token}"},
            )

            assert response.status_code == 202

            # Now simulate polling with failed result
            mock_get_result.return_value = ValidationResult(
                validation_id="val_test123",
                agent_id="test-agent-001",
                status="failed",
                errors=[
                    ValidationError(
                        type="HEALTH_FAILED", message="Health endpoint timeout"
                    ).to_dict(),
                ],
            )

            poll_response = test_client_tpr.get(
                "/auth/agent/validation/val_test123",
                headers={"Authorization": f"Bearer {temp_token}"},
            )

            assert poll_response.status_code == 200
            data = poll_response.json()
            assert data["status"] == "failed"
            assert len(data.get("errors", [])) > 0


class TestTPRPhase3:
    """Test Phase 3: Agent Registration."""

    def test_register_agent_with_validated_token(
        self, test_client_tpr, agent_registration_data
    ):
        """Test agent registration with validated token (via 202 Accepted + polling)."""
        # Phase 1: Get temp token
        temp_response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": agent_registration_data["agent_id"],
                "agent_type": "automation",
                "agent_key": "test-registration-key-123",
            },
        )
        temp_token = temp_response.json()["temp_token"]

        # Phase 2: Submit validation and poll for result
        with (
            patch("arcp.api.auth.enqueue_validation") as mock_enqueue,
            patch("arcp.api.auth.get_validation_result") as mock_get_result,
            patch("arcp.api.auth.get_validation_context") as mock_get_context,
            patch("arcp.api.auth.store_validation_context") as mock_store_context,
        ):

            from arcp.models.validation import SecurityBinding, ValidationResult

            mock_enqueue.return_value = "val_test123"
            mock_store_context.return_value = None
            mock_get_context.return_value = {}

            # Submit validation - returns 202 Accepted
            validation_response = test_client_tpr.post(
                "/auth/agent/validate_compliance",
                json={
                    "agent_id": agent_registration_data["agent_id"],
                    "agent_type": "automation",
                    "endpoint": agent_registration_data["endpoint"],
                    "capabilities": agent_registration_data["capabilities"],
                },
                headers={"Authorization": f"Bearer {temp_token}"},
            )
            assert validation_response.status_code == 202

            # Mock result as complete for polling
            mock_get_result.return_value = ValidationResult(
                validation_id="val_test123",
                agent_id=agent_registration_data["agent_id"],
                status="passed",
                binding=SecurityBinding(
                    code_hash="sha256:abc123",
                    endpoint_hash="sha256:def456",
                ),
            )

            # Poll for validated token
            poll_response = test_client_tpr.get(
                "/auth/agent/validation/val_test123",
                headers={"Authorization": f"Bearer {temp_token}"},
            )
            assert poll_response.status_code == 200
            validated_token = poll_response.json()["validated_token"]

        # Phase 3: Register agent
        with (
            patch("arcp.api.agents.get_redis_service") as mock_redis_service,
            patch("arcp.api.agents.consume_validation_token") as mock_consume,
        ):
            mock_redis = MagicMock()
            mock_redis.is_available.return_value = True
            mock_redis.get_client.return_value = MagicMock()
            mock_redis_service.return_value = mock_redis
            mock_consume.return_value = {
                "ok": True,
                "binding": {
                    "code_hash": "sha256:abc123",
                    "endpoint_hash": "sha256:def456",
                },
            }

            response = test_client_tpr.post(
                "/agents/register",
                json=agent_registration_data,
                headers={"Authorization": f"Bearer {validated_token}"},
            )

            # Accept both 200 (update) and 201 (create) as valid responses
            assert response.status_code in [
                200,
                201,
            ], f"Expected 200 or 201, got {response.status_code}"
            data = response.json()

            # Check fields that actually exist in RegistrationResponse model
            assert data["agent_id"] == agent_registration_data["agent_id"]
            assert data["status"] == "success"
            assert "message" in data
            assert "access_token" in data

    def test_register_agent_validated_token_already_used(
        self, test_client_tpr, agent_registration_data
    ):
        """Test registration fails when validated token already consumed."""
        # Create a valid JWT token with validated token type
        from datetime import datetime, timedelta

        import jwt

        from arcp.core.config import config

        payload = {
            "sub": agent_registration_data["agent_id"],
            "agent_id": agent_registration_data["agent_id"],
            "token_type": "validated",
            "aud": "arcp:register",
            "validation_id": "val_test123",
            "role": "agent",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=5),
        }
        validated_token = jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

        # Mock Redis service to appear available
        with (
            patch("arcp.api.agents.get_redis_service") as mock_redis_service,
            patch("arcp.api.agents.consume_validation_token") as mock_consume,
        ):

            mock_redis = MagicMock()
            mock_redis.is_available.return_value = True
            mock_redis.get_client.return_value = MagicMock()
            mock_redis_service.return_value = mock_redis

            mock_consume.return_value = {
                "ok": False,
                "error": "ALREADY_USED",
            }

            response = test_client_tpr.post(
                "/agents/register",
                json=agent_registration_data,
                headers={"Authorization": f"Bearer {validated_token}"},
            )

            assert response.status_code == 403  # ALREADY_USED returns 403, not 401
            data = response.json()
            # API returns URL-format problem type
            assert "token-invalid" in data["type"] or "token_validation" in data["type"]
            assert data.get("error_code") == "ALREADY_USED"

    def test_register_agent_validated_token_expired(
        self, test_client_tpr, agent_registration_data
    ):
        """Test registration fails when validated token expired."""
        # Create a valid JWT token with validated token type
        from datetime import datetime, timedelta

        import jwt

        from arcp.core.config import config

        payload = {
            "sub": agent_registration_data["agent_id"],
            "agent_id": agent_registration_data["agent_id"],
            "token_type": "validated",
            "aud": "arcp:register",
            "validation_id": "val_expired",
            "role": "agent",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=5),
        }
        validated_token = jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

        # Mock Redis service to appear available
        with (
            patch("arcp.api.agents.get_redis_service") as mock_redis_service,
            patch("arcp.api.agents.consume_validation_token") as mock_consume,
        ):

            mock_redis = MagicMock()
            mock_redis.is_available.return_value = True
            mock_redis.get_client.return_value = MagicMock()
            mock_redis_service.return_value = mock_redis

            mock_consume.return_value = {
                "ok": False,
                "error": "EXPIRED",
            }

            response = test_client_tpr.post(
                "/agents/register",
                json=agent_registration_data,
                headers={"Authorization": f"Bearer {validated_token}"},
            )

            assert response.status_code == 401
            data = response.json()
            assert (
                "token-invalid" in data["type"] or "token_validation" in data["type"]
            )  # API returns URL format


class TestCompleteTPRFlow:
    """Test complete end-to-end TPR flow."""

    @pytest.mark.asyncio
    async def test_complete_tpr_flow_success(
        self, test_client_tpr, agent_registration_data, mock_validation_success
    ):
        """Test complete successful TPR flow with async validation (202 Accepted + polling)."""
        # Phase 1: Request temp token
        phase1_response = test_client_tpr.post(
            "/auth/agent/request_temp_token",
            json={
                "agent_id": agent_registration_data["agent_id"],
                "agent_type": "automation",
                "agent_key": "test-registration-key-123",
            },
        )
        assert phase1_response.status_code == 200
        temp_token = phase1_response.json()["temp_token"]

        # Phase 2: Validate compliance (202 Accepted + polling)
        with (
            patch("arcp.api.auth.enqueue_validation") as mock_enqueue,
            patch("arcp.api.auth.get_validation_result") as mock_get_result,
            patch("arcp.api.auth.get_validation_context") as mock_get_context,
            patch("arcp.api.auth.store_validation_context") as mock_store_context,
        ):

            from arcp.models.validation import SecurityBinding, ValidationResult

            mock_enqueue.return_value = "val_test123"
            mock_store_context.return_value = None
            mock_get_context.return_value = {}

            # Submit validation - returns 202 Accepted
            phase2_response = test_client_tpr.post(
                "/auth/agent/validate_compliance",
                json={
                    "agent_id": agent_registration_data["agent_id"],
                    "agent_type": "automation",
                    "endpoint": agent_registration_data["endpoint"],
                    "capabilities": agent_registration_data["capabilities"],
                },
                headers={"Authorization": f"Bearer {temp_token}"},
            )
            assert phase2_response.status_code == 202
            validation_id = phase2_response.json()["validation_id"]

            # Mock result as complete for polling
            mock_get_result.return_value = ValidationResult(
                validation_id="val_test123",
                agent_id=agent_registration_data["agent_id"],
                status="passed",
                binding=SecurityBinding(
                    code_hash="sha256:abc123",
                    endpoint_hash="sha256:def456",
                ),
            )

            # Poll for validated token
            poll_response = test_client_tpr.get(
                f"/auth/agent/validation/{validation_id}",
                headers={"Authorization": f"Bearer {temp_token}"},
            )
            assert poll_response.status_code == 200
            validated_token = poll_response.json()["validated_token"]

        # Phase 3: Register agent
        with (
            patch("arcp.api.agents.get_redis_service") as mock_redis_service,
            patch("arcp.api.agents.consume_validation_token") as mock_consume,
        ):
            mock_redis = MagicMock()
            mock_redis.is_available.return_value = True
            mock_redis.get_client.return_value = MagicMock()
            mock_redis_service.return_value = mock_redis
            mock_consume.return_value = {
                "ok": True,
                "binding": {
                    "code_hash": "sha256:abc123",
                    "endpoint_hash": "sha256:def456",
                },
            }

            phase3_response = test_client_tpr.post(
                "/agents/register",
                json=agent_registration_data,
                headers={"Authorization": f"Bearer {validated_token}"},
            )
            # Accept both 200 (update) and 201 (create) as valid
            assert phase3_response.status_code in [
                200,
                201,
            ], f"Expected 200 or 201, got {phase3_response.status_code}"

            agent_data = phase3_response.json()
            assert agent_data["agent_id"] == agent_registration_data["agent_id"]
            assert "access_token" in agent_data

        # Verify all phases completed
        assert temp_token is not None
        assert validated_token is not None
        assert validation_id == "val_test123"
        assert agent_data["access_token"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
