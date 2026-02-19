"""
Unit tests for idempotency middleware.

Tests the IdempotencyMiddleware and helper functions for request deduplication.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from arcp.core.exceptions import ProblemException
from arcp.utils.idempotency import (
    IDEMPOTENCY_PREFIX,
    IdempotencyMiddleware,
    IdempotencyResult,
    check_idempotency,
    compute_request_hash,
    get_idempotency_key,
    require_idempotency_key,
    store_idempotency_result,
)


class MockRequest:
    """Mock FastAPI Request for testing."""

    def __init__(self, path: str = "/test", method: str = "POST", headers: dict = None):
        self.url = MagicMock()
        self.url.path = path
        self.method = method
        self.headers = headers or {}
        self._body = b'{"test": "data"}'

    async def body(self):
        return self._body


@pytest.fixture
def mock_redis():
    """Mock Redis service."""
    with patch("arcp.utils.idempotency.get_redis_service") as mock:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_client = MagicMock()
        mock_service.get_client.return_value = mock_client
        mock.return_value = mock_service
        yield mock_client


class TestComputeRequestHash:
    """Test request hash computation."""

    def test_compute_hash_consistent(self):
        """Test hash is consistent for same input."""
        body = b'{"key": "value"}'
        path = "/agents/register"
        method = "POST"

        hash1 = compute_request_hash(body, path, method)
        hash2 = compute_request_hash(body, path, method)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_hash_different_body(self):
        """Test hash differs for different body."""
        path = "/agents/register"
        method = "POST"

        hash1 = compute_request_hash(b'{"key": "value1"}', path, method)
        hash2 = compute_request_hash(b'{"key": "value2"}', path, method)

        assert hash1 != hash2

    def test_compute_hash_different_path(self):
        """Test hash differs for different path."""
        body = b'{"key": "value"}'
        method = "POST"

        hash1 = compute_request_hash(body, "/path1", method)
        hash2 = compute_request_hash(body, "/path2", method)

        assert hash1 != hash2

    def test_compute_hash_different_method(self):
        """Test hash differs for different method."""
        body = b'{"key": "value"}'
        path = "/agents/register"

        hash1 = compute_request_hash(body, path, "POST")
        hash2 = compute_request_hash(body, path, "PUT")

        assert hash1 != hash2


class TestCheckIdempotency:
    """Test idempotency checking."""

    @pytest.mark.asyncio
    async def test_check_no_existing_key(self, mock_redis):
        """Test check when no existing key exists."""
        mock_redis.get.return_value = None

        result = await check_idempotency("test-key-123", "hash123")

        assert not result.is_duplicate
        assert result.cached_response is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_exact_duplicate(self, mock_redis):
        """Test check when exact duplicate exists."""
        cached_data = {
            "request_hash": "hash123",
            "response": {"status": "success"},
            "status_code": 200,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await check_idempotency("test-key-123", "hash123")

        assert result.is_duplicate
        assert result.cached_response == {"status": "success"}
        assert result.cached_status == 200
        assert not result.conflict

    @pytest.mark.asyncio
    async def test_check_conflict_different_body(self, mock_redis):
        """Test check when same key with different body."""
        cached_data = {
            "request_hash": "different_hash",
            "response": {"status": "success"},
            "status_code": 200,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await check_idempotency("test-key-123", "new_hash")

        assert result.is_duplicate
        assert result.conflict
        assert result.cached_response is None

    @pytest.mark.asyncio
    async def test_check_redis_unavailable(self):
        """Test check when Redis is unavailable."""
        with patch("arcp.utils.idempotency.get_redis_service") as mock:
            mock.return_value = None

            result = await check_idempotency("test-key-123", "hash123")

            assert not result.is_duplicate
            assert result.key_hash == "test-key-123:hash123"


class TestStoreIdempotencyResult:
    """Test storing idempotency results."""

    @pytest.mark.asyncio
    async def test_store_success(self, mock_redis):
        """Test successful storage."""
        result = await store_idempotency_result(
            "test-key-123",
            "hash123",
            {"status": "success"},
            200,
            ttl=600,
        )

        assert result is True
        mock_redis.setex.assert_called_once()

        # Verify stored data format
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        ttl = call_args[0][1]
        data = json.loads(call_args[0][2])

        assert key == f"{IDEMPOTENCY_PREFIX}test-key-123"
        assert ttl == 600
        assert data["request_hash"] == "hash123"
        assert data["response"] == {"status": "success"}
        assert data["status_code"] == 200

    @pytest.mark.asyncio
    async def test_store_redis_unavailable(self):
        """Test storage when Redis is unavailable."""
        with patch("arcp.utils.idempotency.get_redis_service") as mock:
            mock.return_value = None

            result = await store_idempotency_result(
                "test-key-123",
                "hash123",
                {"status": "success"},
                200,
            )

            assert result is False


class TestGetIdempotencyKey:
    """Test idempotency key extraction."""

    @pytest.mark.asyncio
    async def test_get_key_provided(self):
        """Test getting provided idempotency key."""
        request = MockRequest()
        key = await get_idempotency_key(request, "valid-key-12345678")

        assert key == "valid-key-12345678"

    @pytest.mark.asyncio
    async def test_get_key_not_provided(self):
        """Test when no idempotency key provided."""
        request = MockRequest()
        key = await get_idempotency_key(request, None)

        assert key is None

    @pytest.mark.asyncio
    async def test_get_key_too_short(self):
        """Test key that's too short."""
        request = MockRequest()
        key = await get_idempotency_key(request, "short")

        assert key is None

    @pytest.mark.asyncio
    async def test_get_key_whitespace_trimmed(self):
        """Test whitespace is trimmed."""
        request = MockRequest()
        key = await get_idempotency_key(request, "  valid-key-12345678  ")

        assert key == "valid-key-12345678"


class TestRequireIdempotencyKey:
    """Test required idempotency key dependency."""

    @pytest.mark.asyncio
    async def test_require_key_provided(self):
        """Test with valid key provided."""
        request = MockRequest()
        key = await require_idempotency_key(request, "valid-key-12345678")

        assert key == "valid-key-12345678"

    @pytest.mark.asyncio
    async def test_require_key_missing(self):
        """Test exception when key missing."""
        request = MockRequest()

        with pytest.raises(ProblemException) as exc_info:
            await require_idempotency_key(request, None)

        assert exc_info.value.status == 400
        assert "required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_require_key_too_short(self):
        """Test exception when key too short."""
        request = MockRequest()

        with pytest.raises(ProblemException) as exc_info:
            await require_idempotency_key(request, "short")

        assert exc_info.value.status == 400
        assert "8-128 characters" in exc_info.value.detail


class TestIdempotencyResult:
    """Test IdempotencyResult container."""

    def test_default_values(self):
        """Test default values."""
        result = IdempotencyResult()

        assert not result.is_duplicate
        assert result.cached_response is None
        assert result.cached_status is None
        assert result.key_hash is None
        assert not result.conflict

    def test_duplicate_result(self):
        """Test duplicate result values."""
        result = IdempotencyResult(
            is_duplicate=True,
            cached_response={"data": "value"},
            cached_status=200,
            key_hash="key:hash",
        )

        assert result.is_duplicate
        assert result.cached_response == {"data": "value"}
        assert result.cached_status == 200
        assert result.key_hash == "key:hash"

    def test_conflict_result(self):
        """Test conflict result."""
        result = IdempotencyResult(
            is_duplicate=True,
            conflict=True,
        )

        assert result.is_duplicate
        assert result.conflict
        assert result.cached_response is None


class TestIdempotencyMiddleware:
    """Test IdempotencyMiddleware class."""

    def test_middleware_initialization(self):
        """Test middleware initializes with paths."""
        app = MagicMock()
        middleware = IdempotencyMiddleware(app, protected_paths=["/test"])

        assert "/test" in middleware.protected_paths

    def test_middleware_default_paths(self):
        """Test middleware uses default paths."""
        app = MagicMock()
        middleware = IdempotencyMiddleware(app)

        assert "/agents/register" in middleware.protected_paths
        assert "/auth/agent/validate_compliance" in middleware.protected_paths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
