"""
Unit tests for ARCP storage adapter module.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.arcp.core.storage_adapter import StorageAdapter


@pytest.mark.unit
@pytest.mark.asyncio
class TestStorageAdapter:
    """Test cases for StorageAdapter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()  # Redis has sync methods
        self.storage = StorageAdapter(self.mock_redis)

    async def test_initialization_with_redis(self):
        """Test storage adapter initialization with Redis client."""
        storage = StorageAdapter(self.mock_redis)

        assert storage._redis is self.mock_redis
        assert storage._fallback == {}
        assert not storage._backend_checked
        assert not storage._backend_available
        assert storage._backend_last_check == 0.0

    async def test_initialization_without_redis(self):
        """Test storage adapter initialization without Redis client."""
        storage = StorageAdapter(None)

        assert storage._redis is None
        assert storage._fallback == {}

    async def test_initialize(self):
        """Test initialize method (no-op)."""
        await self.storage.initialize()
        # Should not raise any exceptions

    async def test_backend_availability_check_success(self):
        """Test backend availability check when Redis is available."""
        self.mock_redis.ping.return_value = True

        # Mock time to control TTL
        with patch("time.time", return_value=100.0):
            is_available = await self.storage.is_backend_available()

        assert is_available is True
        assert self.storage._backend_available is True
        assert self.storage._backend_checked is True
        assert self.storage._backend_last_check == 100.0

    async def test_backend_availability_check_failure(self):
        """Test backend availability check when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        with patch("time.time", return_value=100.0):
            is_available = await self.storage.is_backend_available()

        assert is_available is False
        assert self.storage._backend_available is False
        assert self.storage._backend_checked is True
        assert self.storage._backend_last_check == 100.0

    async def test_hset_with_redis_available(self):
        """Test hset operation when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hset.return_value = 1

        await self.storage.hset("test_key", "field1", "value1")

        self.mock_redis.hset.assert_called_once_with("test_key", "field1", "value1")

    async def test_hset_with_redis_unavailable(self):
        """Test hset operation when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        await self.storage.hset("test_key", "field1", "value1")

        # Should fall back to in-memory storage
        assert self.storage._fallback.get("test_key") == {"field1": "value1"}

    async def test_hget_with_redis_available(self):
        """Test hget operation when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hget.return_value = (
            b"redis_value"  # No JSON quotes for simple string
        )

        result = await self.storage.hget("test_key", "field1")

        assert result == "redis_value"
        self.mock_redis.hget.assert_called_once_with("test_key", "field1")

    async def test_hget_with_redis_unavailable(self):
        """Test hget operation when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Set up fallback data
        self.storage._fallback["test_key"] = {"field1": "fallback_value"}

        # Force backend to be detached
        self.storage._redis = None

        result = await self.storage.hget("test_key", "field1")

        assert result == "fallback_value"

    async def test_hget_nonexistent_key(self):
        """Test hget operation for nonexistent key."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hget.return_value = None

        result = await self.storage.hget("nonexistent", "field")

        assert result is None

    # TODO: hgetall method not implemented in StorageAdapter
    # async def test_hgetall_with_redis_available(self):
    #     """Test hgetall operation when Redis is available."""
    #     self.mock_redis.ping.return_value = True
    #     self.mock_redis.hgetall.return_value = {"field1": "value1", "field2": "value2"}
    #
    #     result = await self.storage.hgetall("test_key")
    #
    #     assert result == {"field1": "value1", "field2": "value2"}
    #     self.mock_redis.hgetall.assert_called_once_with("test_key")

    # TODO: hgetall method not implemented in StorageAdapter
    # async def test_hgetall_with_redis_unavailable(self):
    #     """Test hgetall operation when Redis is unavailable."""
    #     self.mock_redis.ping.side_effect = Exception("Connection failed")
    #
    #     # Set up fallback data manually
    #     self.storage._fallback["test_key"] = {"field1": "value1", "field2": "value2"}
    #
    #     result = await self.storage.hgetall("test_key")
    #
    #     assert result == {"field1": "value1", "field2": "value2"}

    async def test_hkeys_with_redis_available(self):
        """Test hkeys operation when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hkeys.return_value = [b"field1", b"field2"]

        result = await self.storage.hkeys("test_key")

        assert result == ["field1", "field2"]
        self.mock_redis.hkeys.assert_called_once_with("test_key")

    async def test_hkeys_with_redis_unavailable(self):
        """Test hkeys operation when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Set up fallback data
        self.storage._fallback["test_key"] = {
            "field1": "value1",
            "field2": "value2",
        }

        # Force backend to be detached
        self.storage._redis = None

        result = await self.storage.hkeys("test_key")

        assert result == ["field1", "field2"]

    async def test_hdel_with_redis_available(self):
        """Test hdel operation when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hdel.return_value = 1

        await self.storage.hdel("test_key", "field1")

        self.mock_redis.hdel.assert_called_once_with("test_key", "field1")

    async def test_hdel_with_redis_unavailable(self):
        """Test hdel operation when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Set up fallback data
        self.storage._fallback["test_key"] = {
            "field1": "value1",
            "field2": "value2",
        }

        await self.storage.hdel("test_key", "field1")

        # Should remove from fallback
        assert "field1" not in self.storage._fallback["test_key"]

    async def test_hdel_nonexistent_field(self):
        """Test hdel operation for nonexistent field."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hdel.return_value = 0

        await self.storage.hdel("test_key", "nonexistent")

        self.mock_redis.hdel.assert_called_once_with("test_key", "nonexistent")

    async def test_exists_with_redis_available(self):
        """Test exists operation when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hexists.return_value = True

        result = await self.storage.exists("bucket", "key")

        assert result is True
        self.mock_redis.hexists.assert_called_once_with("bucket", "key")

    async def test_exists_with_redis_unavailable(self):
        """Test exists operation when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Set up fallback data
        self.storage._fallback["bucket"] = {"key": "value"}

        result = await self.storage.exists("bucket", "key")

        assert result is True

    async def test_get_set_delete_with_redis_available(self):
        """Test basic get/set/delete operations when Redis is available."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hget.return_value = b'{"test": "data"}'  # Mock hget, not get
        self.mock_redis.hset.return_value = 1
        self.mock_redis.hdel.return_value = 1

        # Test set
        await self.storage.set("bucket", "key", {"test": "data"})

        # Test get
        result = await self.storage.get("bucket", "key")
        assert result == {"test": "data"}

        # Test delete
        await self.storage.delete("bucket", "key")

    async def test_get_set_delete_with_redis_unavailable(self):
        """Test basic get/set/delete operations when Redis is unavailable."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Force backend to be detached
        self.storage._redis = None

        # Test set
        await self.storage.set("bucket", "key", {"test": "data"})

        # Should use fallback with nested structure
        assert self.storage._fallback.get("bucket", {}).get("key") == {"test": "data"}

        # Test get
        result = await self.storage.get("bucket", "key")
        assert result == {"test": "data"}

        # Test delete
        await self.storage.delete("bucket", "key")
        assert "key" not in self.storage._fallback.get("bucket", {})

    async def test_concurrent_fallback_operations(self):
        """Test concurrent operations using fallback storage."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Force backend to be detached
        self.storage._redis = None

        # Simulate concurrent operations
        tasks = []
        for i in range(5):
            task = asyncio.create_task(
                self.storage.set("bucket", f"key{i}", {"value": str(i)})
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Check that all operations completed
        for i in range(5):
            result = await self.storage.get("bucket", f"key{i}")
            assert result == {"value": str(i)}

    async def test_redis_reconnection_throttling(self):
        """Test that Redis reconnection attempts are throttled."""
        # Initially no redis
        storage = StorageAdapter(None)

        with patch("time.time", return_value=100.0):
            await storage._ensure_backend()
            assert storage._reconnect_last_attempt == 100.0

        # Try again immediately - should be throttled
        with patch("time.time", return_value=105.0):
            await storage._ensure_backend()
            # Still should be 100.0 because it was throttled
            assert storage._reconnect_last_attempt == 100.0

    async def test_error_handling_in_operations(self):
        """Test proper error handling in storage operations."""
        self.mock_redis.ping.return_value = True
        self.mock_redis.hget.side_effect = Exception("Redis error")

        # Should fall back gracefully
        result = await self.storage.hget("test_key", "field1")

        # Should return None when fallback doesn't have data
        assert result is None

    async def test_fallback_data_persistence(self):
        """Test that fallback data persists across operations."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Force backend to be detached
        self.storage._redis = None

        # Set some data
        await self.storage.hset("persistent_key", "field1", "value1")
        await self.storage.hset("persistent_key", "field2", "value2")

        # Verify data persists
        result1 = await self.storage.hget("persistent_key", "field1")
        result2 = await self.storage.hget("persistent_key", "field2")

        assert result1 == "value1"
        assert result2 == "value2"

    async def test_empty_fallback_behavior(self):
        """Test behavior when fallback storage is empty."""
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Force backend to be detached
        self.storage._redis = None

        # Try to get from empty fallback
        result = await self.storage.hget("nonexistent", "field")

        assert result is None
