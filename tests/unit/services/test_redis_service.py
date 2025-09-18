"""
Unit tests for ARCP Redis service module.

This test module comprehensively tests Redis service initialization,
connection management, health monitoring, and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.arcp.services.redis import RedisService, get_redis_client, get_redis_service


@pytest.mark.unit
class TestRedisService:
    """Test cases for RedisService class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset the global service instance for testing
        import src.arcp.services.redis as redis_module

        redis_module.redis_service = RedisService()

    @patch("src.arcp.services.redis._redis", None)
    def test_initialization_without_redis_package(self):
        """Test initialization when redis package is not installed."""
        service = RedisService()

        assert service.client is None
        assert service.is_available() is False

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_missing_config(self, mock_config, mock_redis):
        """Test initialization with missing Redis configuration."""
        # Mock incomplete configuration
        mock_config.get_redis_config.return_value = {
            "host": None,
            "port": None,
            "db": None,
            "password": None,
            "decode_responses": False,
        }

        service = RedisService()

        assert service.client is None
        assert service.is_available() is False

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_successful_connection(self, mock_config, mock_redis_module):
        """Test successful Redis initialization and connection."""
        # Mock configuration
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": "password123",
            "decode_responses": False,
            "health_check_interval": 30,
        }

        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.return_value = mock_client

        service = RedisService()

        assert service.client is mock_client
        assert service.is_available() is True

        # Verify Redis client was configured correctly
        mock_redis_module.Redis.assert_called_once_with(
            host="localhost",
            port=6379,
            db=0,
            password="password123",
            decode_responses=False,
            health_check_interval=30,
        )
        mock_client.ping.assert_called_once()

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_connection_failure(self, mock_config, mock_redis_module):
        """Test Redis initialization with connection failure."""
        # Mock configuration
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "decode_responses": False,
        }

        # Mock Redis client that fails to connect
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_module.Redis.return_value = mock_client

        service = RedisService()

        assert service.client is None
        assert service.is_available() is False

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_without_optional_configs(
        self, mock_config, mock_redis_module
    ):
        """Test initialization without optional configuration parameters."""
        # Mock minimal configuration
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "decode_responses": False,
            "health_check_interval": None,
        }

        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.return_value = mock_client

        service = RedisService()

        # Should initialize without optional parameters
        mock_redis_module.Redis.assert_called_once_with(
            host="localhost",
            port=6379,
            db=0,
            password=None,
            decode_responses=False,
        )
        assert service.is_available() is True

    def test_is_available_with_client(self):
        """Test is_available returns True when client exists."""
        service = RedisService()
        service.client = MagicMock()

        assert service.is_available() is True

    def test_is_available_without_client(self):
        """Test is_available returns False when no client."""
        service = RedisService()
        service.client = None

        assert service.is_available() is False

    def test_get_client_with_client(self):
        """Test get_client returns client when available."""
        service = RedisService()
        mock_client = MagicMock()
        service.client = mock_client

        assert service.get_client() is mock_client

    def test_get_client_without_client(self):
        """Test get_client returns None when no client."""
        service = RedisService()
        service.client = None

        assert service.get_client() is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisServiceAsyncMethods:
    """Test cases for RedisService async methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RedisService()

    async def test_ping_without_client(self):
        """Test ping method when no client is available."""
        self.service.client = None

        result = await self.service.ping()

        assert result is False

    @patch("asyncio.get_event_loop")
    async def test_ping_successful(self, mock_get_loop):
        """Test successful ping to Redis."""
        # Mock client and event loop
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        self.service.client = mock_client

        mock_loop = AsyncMock()
        mock_loop.run_in_executor.return_value = True
        mock_get_loop.return_value = mock_loop

        result = await self.service.ping()

        assert result is True
        mock_loop.run_in_executor.assert_called_once()

    @patch("asyncio.get_event_loop")
    async def test_ping_failure(self, mock_get_loop):
        """Test ping failure to Redis."""
        # Mock client that fails ping
        mock_client = MagicMock()
        self.service.client = mock_client

        mock_loop = AsyncMock()
        mock_loop.run_in_executor.side_effect = Exception("Connection timeout")
        mock_get_loop.return_value = mock_loop

        result = await self.service.ping()

        assert result is False

    @patch("src.arcp.services.redis.RedisService._initialize_client")
    def test_reconnect_successful(self, mock_init):
        """Test successful reconnection."""
        mock_client = MagicMock()
        self.service.client = None

        # Mock successful reconnection
        def mock_initialize():
            self.service.client = mock_client

        mock_init.side_effect = mock_initialize

        result = self.service.reconnect()

        assert result is True
        assert self.service.client is mock_client
        mock_init.assert_called_once()

    @patch("src.arcp.services.redis.RedisService._initialize_client")
    def test_reconnect_failure(self, mock_init):
        """Test reconnection failure."""
        self.service.client = None

        # Mock failed reconnection
        mock_init.side_effect = Exception("Connection failed")

        result = self.service.reconnect()

        assert result is False
        assert self.service.client is None


@pytest.mark.unit
class TestRedisServiceStatus:
    """Test cases for RedisService status reporting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RedisService()

    @patch("src.arcp.services.redis._redis", None)
    def test_get_status_package_not_installed(self):
        """Test status when redis package is not installed."""
        status = self.service.get_status()

        assert status["status"] == "unavailable"
        assert status["reason"] == "package_not_installed"

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_get_status_not_configured(self, mock_config, mock_redis):
        """Test status when Redis is not configured."""
        mock_config.get_redis_config.return_value = {
            "host": None,
            "port": None,
            "db": None,
            "password": None,
        }

        status = self.service.get_status()

        assert status["status"] == "not_configured"
        assert status["reason"] == "missing_configuration"

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_get_status_disconnected(self, mock_config, mock_redis_module):
        """Test status when Redis client failed to initialize."""
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
        }

        # Mock client creation failure
        mock_redis_module.Redis.side_effect = Exception("Connection failed")

        self.service.client = None
        status = self.service.get_status()

        assert status["status"] == "disconnected"
        assert status["reason"] == "connection_failed"

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_get_status_connection_error(self, mock_config, mock_redis):
        """Test status when Redis client exists but ping fails."""
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
        }

        # Mock client that fails ping
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection timeout")
        self.service.client = mock_client

        status = self.service.get_status()

        assert status["status"] == "connection_error"
        assert "Connection timeout" in status["reason"]

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_get_status_healthy(self, mock_config, mock_redis):
        """Test status when Redis is healthy."""
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
        }

        # Mock healthy client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        self.service.client = mock_client

        status = self.service.get_status()

        assert status["status"] == "connected"
        assert status["reason"] == "healthy"


@pytest.mark.unit
class TestGlobalFunctions:
    """Test cases for global convenience functions."""

    @patch("src.arcp.services.redis.redis_service")
    def test_get_redis_client(self, mock_service):
        """Test get_redis_client function."""
        mock_client = MagicMock()
        mock_service.get_client.return_value = mock_client

        result = get_redis_client()

        assert result is mock_client
        mock_service.get_client.assert_called_once()

    @patch("src.arcp.services.redis.redis_service")
    def test_get_redis_service(self, mock_service):
        """Test get_redis_service function."""
        result = get_redis_service()

        assert result is mock_service


@pytest.mark.unit
class TestRedisServiceEdgeCases:
    """Test cases for edge cases and error scenarios."""

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_with_invalid_port(self, mock_config, mock_redis_module):
        """Test initialization with invalid port configuration."""
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": "invalid_port",  # Invalid type
            "db": 0,
            "password": None,
            "decode_responses": False,
        }

        # Mock Redis client that raises TypeError for invalid port
        mock_redis_module.Redis.side_effect = TypeError("Invalid port type")

        service = RedisService()

        assert service.client is None
        assert service.is_available() is False

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_initialization_with_timeout(self, mock_config, mock_redis_module):
        """Test initialization with connection timeout."""
        mock_config.get_redis_config.return_value = {
            "host": "unreachable-host",
            "port": 6379,
            "db": 0,
            "password": None,
            "decode_responses": False,
        }

        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection timeout")
        mock_redis_module.Redis.return_value = mock_client

        service = RedisService()

        assert service.client is None
        assert service.is_available() is False

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_reconnect_multiple_attempts(self, mock_config, mock_redis_module):
        """Test multiple reconnection attempts."""
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "decode_responses": False,
        }

        service = RedisService()
        service.client = None

        # First attempt fails
        mock_redis_module.Redis.side_effect = Exception("Connection failed")
        result1 = service.reconnect()
        assert result1 is False

        # Second attempt succeeds
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.side_effect = None
        mock_redis_module.Redis.return_value = mock_client

        result2 = service.reconnect()
        assert result2 is True
        assert service.client is mock_client

    @patch("asyncio.get_event_loop")
    async def test_ping_with_event_loop_error(self, mock_get_loop):
        """Test ping method when event loop operations fail."""
        mock_client = MagicMock()
        self.service = RedisService()
        self.service.client = mock_client

        # Mock event loop that raises exception
        mock_get_loop.side_effect = RuntimeError("No event loop")

        result = await self.service.ping()

        assert result is False

    @patch("src.arcp.services.redis.config")
    def test_status_with_config_error(self, mock_config):
        """Test status method when config access fails."""
        mock_config.get_redis_config.side_effect = Exception("Config error")

        service = RedisService()

        # Should handle config errors gracefully
        # The actual behavior depends on implementation details
        # but it should not crash
        status = service.get_status()
        assert isinstance(status, dict)


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrencyScenarios:
    """Test cases for concurrent operations on RedisService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = RedisService()

    @patch("asyncio.get_event_loop")
    async def test_concurrent_ping_operations(self, mock_get_loop):
        """Test concurrent ping operations."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        self.service.client = mock_client

        mock_loop = AsyncMock()
        mock_loop.run_in_executor.return_value = True
        mock_get_loop.return_value = mock_loop

        # Execute multiple ping operations concurrently
        ping_tasks = [self.service.ping() for _ in range(5)]
        results = await asyncio.gather(*ping_tasks)

        assert all(results)
        assert mock_loop.run_in_executor.call_count == 5

    @patch("src.arcp.services.redis.RedisService._initialize_client")
    def test_concurrent_reconnect_attempts(self, mock_init):
        """Test concurrent reconnection attempts."""
        self.service.client = None
        reconnect_count = 0

        def mock_initialize():
            nonlocal reconnect_count
            reconnect_count += 1
            if reconnect_count == 1:
                self.service.client = MagicMock()
            else:
                # Subsequent calls should see existing client
                pass

        mock_init.side_effect = mock_initialize

        # Simulate concurrent reconnection attempts
        results = []
        for _ in range(3):
            result = self.service.reconnect()
            results.append(result)

        # At least one should succeed
        assert any(results)
        # But we don't want excessive reconnection attempts
        assert mock_init.call_count <= 3


@pytest.mark.unit
class TestRedisServiceIntegration:
    """Integration-style tests for RedisService (still using mocks)."""

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_full_lifecycle_success(self, mock_config, mock_redis_module):
        """Test full lifecycle of RedisService - initialization, operation, reconnection."""
        # Setup configuration
        mock_config.get_redis_config.return_value = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": "test_password",
            "decode_responses": True,
            "health_check_interval": 30,
        }

        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.return_value = mock_client

        # Test initialization
        service = RedisService()
        assert service.is_available() is True
        assert service.get_client() is mock_client

        # Test status check
        status = service.get_status()
        assert status["status"] == "connected"
        assert status["reason"] == "healthy"

        # Simulate connection loss
        mock_client.ping.side_effect = Exception("Connection lost")
        status = service.get_status()
        assert status["status"] == "connection_error"

        # Test reconnection
        mock_client.ping.side_effect = None
        mock_client.ping.return_value = True
        result = service.reconnect()
        assert result is True

        # Verify service is healthy again
        status = service.get_status()
        assert status["status"] == "connected"

    @patch("src.arcp.services.redis._redis")
    @patch("src.arcp.services.redis.config")
    def test_full_lifecycle_failure(self, mock_config, mock_redis_module):
        """Test full lifecycle with persistent failures."""
        # Setup configuration
        mock_config.get_redis_config.return_value = {
            "host": "unreachable-host",
            "port": 6379,
            "db": 0,
            "password": None,
            "decode_responses": False,
        }

        # Mock Redis client that always fails
        mock_redis_module.Redis.side_effect = Exception("Connection refused")

        # Test initialization failure
        service = RedisService()
        assert service.is_available() is False
        assert service.get_client() is None

        # Test status
        status = service.get_status()
        assert status["status"] == "disconnected"

        # Test failed reconnection
        result = service.reconnect()
        assert result is False
        assert service.is_available() is False
