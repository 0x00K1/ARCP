"""
Mock services and external dependencies for ARCP tests.

Provides mock implementations of Redis, OpenAI, and other external services.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._connected = True
        self._ping_calls = 0

    def ping(self) -> bool:
        """Mock ping method."""
        self._ping_calls += 1
        if not self._connected:
            raise ConnectionError("Mock Redis connection failed")
        return True

    async def hset(self, bucket: str, key: str, value: Any) -> None:
        """Mock hset method."""
        if bucket not in self._data:
            self._data[bucket] = {}
        if isinstance(value, (dict, list)):
            self._data[bucket][key] = json.dumps(value)
        else:
            self._data[bucket][key] = str(value)

    async def hget(self, bucket: str, key: str) -> Optional[str]:
        """Mock hget method."""
        if bucket not in self._data:
            return None
        return self._data[bucket].get(key)

    async def hkeys(self, bucket: str) -> List[str]:
        """Mock hkeys method."""
        if bucket not in self._data:
            return []
        return list(self._data[bucket].keys())

    async def hdel(self, bucket: str, key: str) -> None:
        """Mock hdel method."""
        if bucket in self._data and key in self._data[bucket]:
            del self._data[bucket][key]

    async def exists(self, bucket: str, key: str) -> bool:
        """Mock exists method."""
        return bucket in self._data and key in self._data[bucket]

    def set_connected(self, connected: bool):
        """Set connection status for testing."""
        self._connected = connected

    def get_ping_calls(self) -> int:
        """Get number of ping calls for testing."""
        return self._ping_calls

    def clear_data(self):
        """Clear all mock data."""
        self._data.clear()

    def get_data(self) -> Dict[str, Dict[str, Any]]:
        """Get all mock data."""
        return self._data.copy()


class MockOpenAIClient:
    """Mock OpenAI client for testing embeddings."""

    def __init__(self):
        self._available = True
        self._embedding_calls = 0
        self._default_embedding = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        self._custom_embeddings: Dict[str, List[float]] = {}

    def embeddings_create(self, model: str, input: str) -> MagicMock:
        """Mock embeddings create method."""
        self._embedding_calls += 1
        if not self._available:
            raise Exception("Mock OpenAI client unavailable")

        # Return custom embedding if set, otherwise default
        embedding = self._custom_embeddings.get(input, self._default_embedding)

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=embedding)]
        return mock_response

    async def async_embeddings_create(self, model: str, input: str) -> MagicMock:
        """Mock async embeddings create method with simulated delay."""
        import asyncio

        # Simulate small network delay to allow concurrency benefits in testing
        await asyncio.sleep(0.01)  # 10ms delay to simulate API latency
        return self.embeddings_create(model, input)

    def set_available(self, available: bool):
        """Set availability for testing."""
        self._available = available

    def set_custom_embedding(self, input_text: str, embedding: List[float]):
        """Set custom embedding for specific input."""
        self._custom_embeddings[input_text] = embedding

    def get_embedding_calls(self) -> int:
        """Get number of embedding calls for testing."""
        return self._embedding_calls

    def clear_custom_embeddings(self):
        """Clear custom embeddings."""
        self._custom_embeddings.clear()


class MockOpenAIService:
    """Mock OpenAI service for testing."""

    def __init__(self):
        self.client = MockOpenAIClient()
        self._available = True

    def is_available(self) -> bool:
        """Check if the OpenAI service is available."""
        return self._available

    def set_available(self, available: bool):
        """Set availability for testing."""
        self._available = available
        if hasattr(self.client, "set_available"):
            self.client.set_available(available)

    def get_client(self):
        """Get the mock OpenAI client."""
        return self.client

    def embed_text(self, text: str) -> Optional[List[float]]:
        """Generate embeddings for text using mock client."""
        if not self._available:
            return None
        try:
            response = self.client.embeddings_create("text-embedding-ada-002", text)
            return response.data[0].embedding
        except Exception:
            return None

    def set_custom_embedding(self, input_text: str, embedding: List[float]):
        """Set custom embedding for specific input."""
        if hasattr(self.client, "set_custom_embedding"):
            self.client.set_custom_embedding(input_text, embedding)


class MockStorageAdapter:
    """Mock storage adapter for testing."""

    def __init__(self):
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._backend_available = True

    async def initialize(self) -> None:
        """Mock initialize method."""

    def register_bucket(self, bucket: str, fallback_dict: Dict[str, Any]) -> None:
        """Mock register bucket method."""
        if bucket not in self._buckets:
            self._buckets[bucket] = fallback_dict.copy()

    async def is_backend_available(self) -> bool:
        """Mock backend availability check."""
        return self._backend_available

    async def hset(self, bucket: str, key: str, value: Any) -> None:
        """Mock hset method."""
        if bucket not in self._buckets:
            self._buckets[bucket] = {}
        self._buckets[bucket][key] = value

    async def hget(self, bucket: str, key: str) -> Optional[Any]:
        """Mock hget method."""
        if bucket not in self._buckets:
            return None
        return self._buckets[bucket].get(key)

    async def hkeys(self, bucket: str) -> List[str]:
        """Mock hkeys method."""
        if bucket not in self._buckets:
            return []
        return list(self._buckets[bucket].keys())

    async def hgetall(self, bucket: str) -> Dict[str, Any]:
        """Mock hgetall method."""
        if bucket not in self._buckets:
            return {}
        return self._buckets[bucket].copy()

    async def hdel(self, bucket: str, key: str) -> None:
        """Mock hdel method."""
        if bucket in self._buckets and key in self._buckets[bucket]:
            del self._buckets[bucket][key]

    async def exists(self, bucket: str, key: str) -> bool:
        """Mock exists method."""
        return bucket in self._buckets and key in self._buckets[bucket]

    async def get(self, bucket: str, key: str) -> Optional[Any]:
        """Mock get method."""
        return await self.hget(bucket, key)

    async def set(self, bucket: str, key: str, value: Any) -> None:
        """Mock set method."""
        await self.hset(bucket, key, value)

    async def delete(self, bucket: str, key: str) -> None:
        """Mock delete method."""
        await self.hdel(bucket, key)

    def set_backend_available(self, available: bool):
        """Set backend availability for testing."""
        self._backend_available = available

    def clear_all_data(self):
        """Clear all mock data."""
        self._buckets.clear()

    def get_bucket_data(self, bucket: str) -> Dict[str, Any]:
        """Get bucket data for testing."""
        return self._buckets.get(bucket, {}).copy()


class MockRateLimiter:
    """Mock rate limiter for testing."""

    def __init__(self):
        self._attempts: Dict[str, int] = {}
        self._locked_identifiers: set = set()
        self._rate_limit_enabled = True

    async def check_rate_limit(
        self, identifier: str, attempt_type: str = "global"
    ) -> tuple:
        """Mock rate limit check."""
        if not self._rate_limit_enabled:
            return (True, None, None)

        if identifier in self._locked_identifiers:
            return (False, 300.0, "Rate limit exceeded - locked")

        attempts = self._attempts.get(f"{identifier}:{attempt_type}", 0)
        if attempts >= 5:  # Mock threshold
            self._locked_identifiers.add(identifier)
            return (False, 300.0, "Rate limit exceeded")

        return (True, None, None)

    async def record_attempt(
        self, identifier: str, success: bool, attempt_type: str = "global"
    ) -> Optional[float]:
        """Mock record attempt."""
        key = f"{identifier}:{attempt_type}"
        if success:
            # Reset on success
            self._attempts[key] = 0
            self._locked_identifiers.discard(identifier)
            return None
        else:
            # Increment on failure
            self._attempts[key] = self._attempts.get(key, 0) + 1
            if self._attempts[key] >= 5:
                self._locked_identifiers.add(identifier)
                return 300.0  # Mock lockout duration
        return None

    def set_rate_limit_enabled(self, enabled: bool):
        """Enable/disable rate limiting for testing."""
        self._rate_limit_enabled = enabled

    def clear_attempts(self):
        """Clear all attempts for testing."""
        self._attempts.clear()
        self._locked_identifiers.clear()

    def lock_identifier(self, identifier: str):
        """Manually lock identifier for testing."""
        self._locked_identifiers.add(identifier)


class MockMetricsService:
    """Mock metrics service for testing."""

    def __init__(self):
        self._prometheus_available = True
        self._psutil_available = True
        self._resource_data = {
            "cpu": 15.5,
            "memory": 62.3,
            "network": 8.2,
            "storage": 45.1,
        }

    def is_prometheus_available(self) -> bool:
        """Mock Prometheus availability."""
        return self._prometheus_available

    def is_psutil_available(self) -> bool:
        """Mock psutil availability."""
        return self._psutil_available

    def get_prometheus_metrics(self) -> tuple:
        """Mock Prometheus metrics."""
        if not self._prometheus_available:
            return b"# Prometheus unavailable", "text/plain"

        metrics = [
            "# HELP arcp_agents_total Total number of registered agents",
            "# TYPE arcp_agents_total gauge",
            "arcp_agents_total 5",
            "# HELP arcp_agents_alive Number of alive agents",
            "# TYPE arcp_agents_alive gauge",
            "arcp_agents_alive 4",
        ]
        return (
            "\n".join(metrics).encode(),
            "text/plain; version=0.0.4; charset=utf-8",
        )

    async def get_resource_utilization(self) -> Dict[str, float]:
        """Mock resource utilization."""
        if not self._psutil_available:
            return {"cpu": 0.0, "memory": 0.0, "network": 0.0, "storage": 0.0}
        return self._resource_data.copy()

    def set_prometheus_available(self, available: bool):
        """Set Prometheus availability."""
        self._prometheus_available = available

    def set_psutil_available(self, available: bool):
        """Set psutil availability."""
        self._psutil_available = available

    def set_resource_data(self, resource_data: Dict[str, float]):
        """Set custom resource data."""
        self._resource_data.update(resource_data)


@pytest.fixture
def mock_redis_client():
    """Fixture providing mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_openai_client():
    """Fixture providing mock OpenAI client."""
    return MockOpenAIClient()


@pytest.fixture
def mock_storage_adapter():
    """Fixture providing mock storage adapter."""
    return MockStorageAdapter()


@pytest.fixture
def mock_rate_limiter():
    """Fixture providing mock rate limiter."""
    return MockRateLimiter()


@pytest.fixture
def mock_metrics_service():
    """Fixture providing mock metrics service."""
    return MockMetricsService()


@pytest.fixture
def mock_async_sleep():
    """Mock asyncio.sleep for faster tests."""

    async def _mock_sleep(duration):
        # Don't actually sleep, just yield control
        await asyncio.sleep(0)

    return _mock_sleep


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""

    def __init__(self):
        self.sent_messages: List[str] = []
        self.received_messages: List[str] = []
        self.connected = True
        self.client_state = "CONNECTED"
        self.close_code: Optional[int] = None
        self.close_reason: Optional[str] = None

    async def send_text(self, message: str):
        """Mock send text method."""
        if not self.connected:
            raise Exception("WebSocket not connected")
        self.sent_messages.append(message)

    async def receive_text(self) -> str:
        """Mock receive text method."""
        if not self.connected:
            raise Exception("WebSocket not connected")
        if not self.received_messages:
            # Simulate timeout or disconnection
            await asyncio.sleep(0.1)
            raise Exception("No messages to receive")
        return self.received_messages.pop(0)

    async def accept(self):
        """Mock accept method."""
        self.connected = True

    async def close(self, code: int = 1000, reason: str = ""):
        """Mock close method."""
        self.connected = False
        self.close_code = code
        self.close_reason = reason

    def add_received_message(self, message: str):
        """Add message to received queue for testing."""
        self.received_messages.append(message)

    def get_sent_messages(self) -> List[str]:
        """Get all sent messages."""
        return self.sent_messages.copy()

    def clear_messages(self):
        """Clear all message history."""
        self.sent_messages.clear()
        self.received_messages.clear()


@pytest.fixture
def mock_websocket():
    """Fixture providing mock WebSocket connection."""
    return MockWebSocketConnection()


def create_mock_request(
    method: str = "GET",
    path: str = "/",
    headers: Optional[Dict[str, str]] = None,
    client_ip: str = "127.0.0.1",
) -> MagicMock:
    """Create mock FastAPI request for testing."""
    mock_request = MagicMock()
    mock_request.method = method
    mock_request.url.path = path
    mock_request.headers = headers or {}
    mock_request.client.host = client_ip
    return mock_request
