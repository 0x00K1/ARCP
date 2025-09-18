"""
Common test helpers and utilities for ARCP tests.

Provides utility functions, decorators, and helpers for testing.
"""

import asyncio
import json
import tempfile
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import pytest


class TimeTravel:
    """Helper for controlling time in tests."""

    def __init__(self):
        self._frozen_time: Optional[datetime] = None
        self._time_offset: timedelta = timedelta()

    def freeze(self, at_time: datetime):
        """Freeze time at specific datetime."""
        self._frozen_time = at_time

    def advance(self, delta: timedelta):
        """Advance frozen time by delta."""
        if self._frozen_time:
            self._frozen_time += delta
        else:
            self._time_offset += delta

    def now(self) -> datetime:
        """Get current time (frozen or offset)."""
        if self._frozen_time:
            return self._frozen_time
        return datetime.now(timezone.utc) + self._time_offset

    def reset(self):
        """Reset time to normal."""
        self._frozen_time = None
        self._time_offset = timedelta()


@contextmanager
def temp_config_override(**config_overrides):
    """Context manager to temporarily override configuration values."""
    from src.arcp.core.config import config

    original_values = {}
    for key, value in config_overrides.items():
        original_values[key] = getattr(config, key, None)
        setattr(config, key, value)

    try:
        yield
    finally:
        for key, original_value in original_values.items():
            if original_value is None and hasattr(config, key):
                delattr(config, key)
            else:
                setattr(config, key, original_value)


@contextmanager
def temp_environment(**env_vars):
    """Context manager to temporarily set environment variables."""
    import os

    original_values = {}

    for key, value in env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = str(value)

    try:
        yield
    finally:
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


@contextmanager
def temp_directory():
    """Context manager providing temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@asynccontextmanager
async def async_timeout(seconds: float):
    """Async context manager for enforcing timeouts in tests."""
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.current_task()), timeout=seconds)
        yield
    except asyncio.TimeoutError:
        pytest.fail(f"Test timed out after {seconds} seconds")


class ResponseValidator:
    """Helper for validating API responses."""

    @staticmethod
    def assert_success_response(response, expected_status: int = 200):
        """Assert response is successful with expected status."""
        assert (
            response.status_code == expected_status
        ), f"Expected {expected_status}, got {response.status_code}: {response.text}"

        # Check content type for JSON responses
        if expected_status != 204:  # No content
            content_type = response.headers.get("content-type", "")
            assert "json" in content_type, f"Expected JSON response, got {content_type}"

    @staticmethod
    def assert_error_response(
        response, expected_status: int, expected_error_type: str = None
    ):
        """Assert response is an error with expected status and type."""
        assert (
            response.status_code == expected_status
        ), f"Expected {expected_status}, got {response.status_code}: {response.text}"

        # Check if it's a Problem Details response
        content_type = response.headers.get("content-type", "")
        if "application/problem+json" in content_type:
            data = response.json()
            assert "type" in data, "Problem Details response missing 'type'"
            assert "title" in data, "Problem Details response missing 'title'"
            assert "status" in data, "Problem Details response missing 'status'"

            if expected_error_type:
                assert (
                    expected_error_type in data["type"]
                ), f"Expected error type {expected_error_type}, got {data['type']}"

    @staticmethod
    def assert_validation_error(response, field_name: str = None):
        """Assert response is a validation error."""
        ResponseValidator.assert_error_response(response, 422)

        data = response.json()
        if field_name:
            # Check if field is mentioned in error details
            detail = data.get("detail", "")
            assert (
                field_name in str(detail).lower()
            ), f"Field '{field_name}' not found in validation error: {detail}"

    @staticmethod
    def assert_auth_error(response):
        """Assert response is an authentication error."""
        ResponseValidator.assert_error_response(response, 401, "authentication-failed")

    @staticmethod
    def assert_permission_error(response):
        """Assert response is a permission error."""
        ResponseValidator.assert_error_response(
            response, 403, "insufficient-permissions"
        )

    @staticmethod
    def assert_not_found_error(response):
        """Assert response is a not found error."""
        ResponseValidator.assert_error_response(response, 404)

    @staticmethod
    def assert_rate_limit_error(response):
        """Assert response is a rate limit error."""
        ResponseValidator.assert_error_response(response, 429, "rate-limit-exceeded")


class AgentTestHelper:
    """Helper for agent-related test operations."""

    @staticmethod
    def create_test_agent_data(
        agent_id: str = "test-agent",
        agent_type: str = "generic",
        capabilities: List[str] = None,
        status: str = "alive",
    ) -> Dict[str, Any]:
        """Create test agent data dictionary."""
        if capabilities is None:
            capabilities = ["test_capability"]

        return {
            "agent_id": agent_id,
            "name": f"Test {agent_type.title()} Agent",
            "agent_type": agent_type,
            "endpoint": f"https://{agent_id}.example.com/api",
            "capabilities": capabilities,
            "context_brief": f"Test agent for {agent_type} operations",
            "version": "1.0.0",
            "owner": "Test Suite",
            "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8W9X0Y1Z2A3B4C5D6E7F8G9H0I1J2K3L4M5N6O7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F6 test-helper-key",
            "metadata": {"test": True},
            "communication_mode": "remote",
            "status": status,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def register_test_agent(
        registry, agent_id: str = "test-agent", agent_type: str = "generic"
    ):
        """Register a test agent in registry."""
        from tests.fixtures.agent_fixtures import create_test_agent_registration

        registration = create_test_agent_registration(agent_id, agent_type)
        return await registry.register_agent(registration)

    @staticmethod
    def assert_agent_data_valid(agent_data: Dict[str, Any]):
        """Assert agent data contains required fields."""
        required_fields = [
            "agent_id",
            "name",
            "agent_type",
            "endpoint",
            "capabilities",
        ]
        for field in required_fields:
            assert (
                field in agent_data
            ), f"Required field '{field}' missing from agent data"
            assert agent_data[field] is not None, f"Required field '{field}' is None"

    @staticmethod
    def assert_metrics_valid(metrics: Dict[str, Any]):
        """Assert metrics data is valid."""
        required_fields = [
            "success_rate",
            "avg_response_time",
            "total_requests",
        ]
        for field in required_fields:
            assert field in metrics, f"Required metrics field '{field}' missing"
            assert isinstance(
                metrics[field], (int, float)
            ), f"Metrics field '{field}' should be numeric"


class AuthTestHelper:
    """Helper for authentication-related test operations."""

    @staticmethod
    def create_auth_headers(token: str) -> Dict[str, str]:
        """Create authorization headers with token."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def create_admin_headers() -> Dict[str, str]:
        """Create headers for admin authentication."""
        from tests.fixtures.auth_fixtures import create_admin_token

        token = create_admin_token()
        return AuthTestHelper.create_auth_headers(token)

    @staticmethod
    def create_agent_headers(agent_id: str = "test-agent") -> Dict[str, str]:
        """Create headers for agent authentication."""
        from tests.fixtures.auth_fixtures import create_valid_token

        token = create_valid_token(agent_id, "agent")
        return AuthTestHelper.create_auth_headers(token)

    @staticmethod
    def assert_token_valid(token: str):
        """Assert JWT token is valid."""
        import jwt

        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            assert "sub" in payload, "Token missing 'sub' claim"
            assert "exp" in payload, "Token missing 'exp' claim"

            # Check expiration
            exp = payload["exp"]
            now = datetime.now(timezone.utc).timestamp()
            assert exp > now, "Token is expired"
        except jwt.InvalidTokenError as e:
            pytest.fail(f"Invalid JWT token: {e}")


class WebSocketTestHelper:
    """Helper for WebSocket testing."""

    @staticmethod
    async def send_json_message(websocket, message_type: str, data: Any = None):
        """Send JSON message over WebSocket."""
        message = {"type": message_type}
        if data is not None:
            message["data"] = data
        await websocket.send_text(json.dumps(message))

    @staticmethod
    async def receive_json_message(websocket) -> Dict[str, Any]:
        """Receive and parse JSON message from WebSocket."""
        text = await websocket.receive_text()
        return json.loads(text)

    @staticmethod
    def assert_websocket_message(message: Dict[str, Any], expected_type: str):
        """Assert WebSocket message has expected type and structure."""
        assert "type" in message, "WebSocket message missing 'type' field"
        assert (
            message["type"] == expected_type
        ), f"Expected message type '{expected_type}', got '{message['type']}'"
        assert (
            "timestamp" in message or "data" in message
        ), "WebSocket message missing timestamp or data"


class DatabaseTestHelper:
    """Helper for database/storage testing."""

    @staticmethod
    async def clear_test_data(storage_adapter):
        """Clear all test data from storage."""
        if hasattr(storage_adapter, "clear_all_data"):
            storage_adapter.clear_all_data()

    @staticmethod
    async def populate_test_agents(registry, count: int = 5):
        """Populate registry with test agents."""
        agents = []
        for i in range(count):
            agent_id = f"test-agent-{i:03d}"
            agent_type = ["security", "automation", "monitoring", "testing"][i % 4]
            agent = await AgentTestHelper.register_test_agent(
                registry, agent_id, agent_type
            )
            agents.append(agent)
        return agents


def skip_if_no_redis(reason: str = "Redis not available"):
    """Skip test if Redis is not available."""

    def decorator(func):
        try:
            import redis

            # Try to connect to Redis
            client = redis.Redis(host="localhost", port=6379, db=0)
            client.ping()
            return func
        except Exception:
            return pytest.mark.skip(reason=reason)(func)

    return decorator


def skip_if_no_openai(reason: str = "OpenAI not configured"):
    """Skip test if OpenAI is not configured."""

    def decorator(func):
        import os

        if not os.getenv("AZURE_OPENAI_API_KEY"):
            return pytest.mark.skip(reason=reason)(func)
        return func

    return decorator


def requires_network(func):
    """Mark test as requiring network access."""
    return pytest.mark.network(func)


def slow_test(func):
    """Mark test as slow running."""
    return pytest.mark.slow(func)


def integration_test(func):
    """Mark test as integration test."""
    return pytest.mark.integration(func)


def performance_test(func):
    """Mark test as performance test."""
    return pytest.mark.performance(func)


def security_test(func):
    """Mark test as security test."""
    return pytest.mark.security(func)


async def wait_for_condition(
    condition_func: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.1,
    error_message: str = "Condition not met within timeout",
):
    """Wait for a condition to become true with timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return
        await asyncio.sleep(interval)
    pytest.fail(error_message)


def assert_performance_within_limit(
    duration: float, limit: float, operation: str = "operation"
):
    """Assert operation completed within performance limit."""
    assert duration <= limit, f"{operation} took {duration:.3f}s, expected <= {limit}s"


def assert_approximately_equal(
    actual: Union[int, float],
    expected: Union[int, float],
    tolerance: float = 0.01,
    message: str = None,
):
    """Assert two numbers are approximately equal within tolerance."""
    diff = abs(actual - expected)
    max_diff = abs(expected * tolerance) if expected != 0 else tolerance

    if message is None:
        message = f"Expected {expected} ± {tolerance*100}%, got {actual} (diff: {diff})"

    assert diff <= max_diff, message


class TestDataGenerator:
    """Generate test data for various scenarios."""

    @staticmethod
    def create_large_text(size_kb: int) -> str:
        """Create large text for testing size limits."""
        # Create text of approximately size_kb kilobytes
        pattern = "abcdefghijklmnopqrstuvwxyz0123456789 " * 30  # ~90 chars
        repeats = (size_kb * 1024) // len(pattern) + 1
        return (pattern * repeats)[: size_kb * 1024]

    @staticmethod
    def create_malicious_input_samples() -> List[str]:
        """Create samples of potentially malicious input for testing."""
        return [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "data:text/html,<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "../../../etc/passwd",
            "'; DROP TABLE users; --",
            "\x00\x01\x02\x03",  # Control characters
            "а" * 1000,  # Unicode overflow
            '{"__proto__": {"polluted": true}}',  # Prototype pollution
            "{{7*7}}",  # Template injection
            "\\u0000\\u0001\\u0002",  # Encoded control chars
        ]

    @staticmethod
    def create_performance_test_data(item_count: int) -> List[Dict[str, Any]]:
        """Create large dataset for performance testing."""
        data = []
        for i in range(item_count):
            data.append(
                {
                    "id": f"item-{i:06d}",
                    "name": f"Test Item {i}",
                    "description": f"This is test item number {i} for performance testing",
                    "category": f"category-{i % 10}",
                    "tags": [f"tag-{j}" for j in range(i % 5)],
                    "metadata": {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "version": "1.0.0",
                        "priority": i % 3,
                    },
                }
            )
        return data
