"""
Redis service for ARCP.

This module provides a centralized interface for Redis operations,
including client management and connection health monitoring.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    import redis
try:
    import redis as _redis  # type: ignore
except ImportError:
    _redis = None

from ..core.config import config

logger = logging.getLogger(__name__)


class RedisService:
    """Service for Redis operations."""

    def __init__(self):
        """Initialize the Redis service."""
        self.client: Optional[Any] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Redis client."""
        if not _redis:
            logger.warning("redis package not installed - Redis features unavailable")
            return

        try:
            redis_config = config.get_redis_config()
        except Exception as e:
            logger.error(f"Failed to get Redis configuration: {e}")
            return

        if not all(
            v is not None
            for v in [
                redis_config["host"],
                redis_config["port"],
                redis_config["db"],
            ]
        ):
            logger.warning("Redis not configured - missing optional configuration")
            return

        try:
            # Filter out non-client configuration keys (e.g., max_memory is a server setting)
            client_kwargs = {
                "host": redis_config.get("host"),
                "port": redis_config.get("port"),
                "db": redis_config.get("db"),
                "password": redis_config.get("password"),
                "decode_responses": redis_config.get("decode_responses", False),
            }
            if redis_config.get("health_check_interval") is not None:
                client_kwargs["health_check_interval"] = redis_config.get(
                    "health_check_interval"
                )

            self.client = _redis.Redis(**client_kwargs)
            self.client.ping()  # Test connection
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Redis connection failed: {str(e)}")
            self.client = None

    def is_available(self) -> bool:
        """Check if the Redis service is available."""
        return self.client is not None

    def get_client(self) -> Optional["redis.Redis"]:
        """Get the Redis client."""
        return self.client

    async def ping(self) -> bool:
        """
        Test Redis connection health.

        Returns:
            True if Redis is healthy, False otherwise
        """
        if not self.client:
            return False

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: self.client.ping())
            return result
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to Redis.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            self._initialize_client()
            return self.client is not None
        except Exception as e:
            logger.error(f"Redis reconnection failed: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the Redis service."""
        if not _redis:
            return {"status": "unavailable", "reason": "package_not_installed"}

        try:
            redis_config = config.get_redis_config()
        except Exception as e:
            return {
                "status": "configuration_error",
                "reason": f"Failed to get config: {e}",
            }

        if not all(
            v is not None
            for v in [
                redis_config["host"],
                redis_config["port"],
                redis_config["db"],
            ]
        ):
            return {
                "status": "not_configured",
                "reason": "missing_configuration",
            }

        if self.client is None:
            return {"status": "disconnected", "reason": "connection_failed"}

        try:
            self.client.ping()
            return {"status": "connected", "reason": "healthy"}
        except Exception as e:
            return {"status": "connection_error", "reason": str(e)}


# Global Redis service instance
redis_service = RedisService()


def get_redis_client() -> Optional["redis.Redis"]:
    """Get the Redis client."""
    return redis_service.get_client()


def get_redis_service() -> RedisService:
    """Get the Redis service instance."""
    return redis_service
