"""
Storage Adapter for ARCP

This lightweight helper encapsulates common Redis hash operations while
providing an automatic in-memory fallback.  It eliminates the repetitive
``hset``/``hget``/``hkeys``/``hdel`` patterns currently duplicated across
AgentRegistry for agents, embeddings and metrics.

Usage (inside AgentRegistry):
    self.storage = StorageAdapter(self.redis_client)
    self.storage.register_bucket("agent:data", self.backup_agents)
    ...

The adapter is intentionally minimal - it only supports the few hash
operations ARCP actually needs.  Additional commands can be added as
required without changing the public interface of AgentRegistry.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from .config import config


class StorageAdapter:  # pragma: no cover - thin wrapper
    """Hash-like storage abstraction for Redis + memory fallback."""

    def __init__(self, redis_client: Optional[Any] = None):
        self._redis = redis_client
        self._fallback: Dict[str, Dict[str, Any]] = {}
        self._fallback_lock = asyncio.Lock()  # Protect fallback dict access
        # Backend availability cache
        self._backend_checked: bool = False
        self._backend_available: bool = False
        self._backend_last_check: float = 0.0
        self._backend_ttl_seconds: float = 30.0
        # Reconnect throttling
        self._reconnect_last_attempt: float = 0.0
        redis_interval = getattr(config, "REDIS_HEALTH_CHECK_INTERVAL", 30)
        self._reconnect_interval_seconds: float = float(redis_interval or 30)

    # ---------------------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------------------
    async def initialize(self) -> None:
        """Initialize the storage adapter. No-op for this simple implementation."""

    # ---------------------------------------------------------------------
    # Bucket registration helpers
    # ---------------------------------------------------------------------
    def register_bucket(self, bucket: str, fallback_dict: Dict[str, Any]) -> None:
        """Register a bucket name with its in-memory fallback dict."""
        self._fallback[bucket] = fallback_dict

    # ---------------------------------------------------------------------
    # Backend health helpers
    # ---------------------------------------------------------------------
    @property
    def has_backend(self) -> bool:
        """Return True if a Redis backend is configured (not necessarily healthy)."""
        return self._redis is not None

    async def _ensure_backend(self) -> None:
        """Attempt to initialize the Redis backend if not attached, throttled by interval."""
        if self._redis is not None:
            return
        now = time.time()
        if (now - self._reconnect_last_attempt) < self._reconnect_interval_seconds:
            return
        self._reconnect_last_attempt = now

        def _connect() -> Optional[Any]:
            try:
                # Use the centralized Redis service
                from ..services import get_redis_service

                redis_service = get_redis_service()
                client = redis_service.get_client()
                if client is not None:
                    # Validate connection
                    client.ping()
                    return client
                return None
            except Exception:
                return None

        client = await asyncio.get_event_loop().run_in_executor(None, _connect)
        if client is not None:
            self._redis = client
            # Reset health cache to force a fresh check next call
            self._backend_checked = False
            self._backend_last_check = 0.0

    async def is_backend_available(self) -> bool:
        """Return True if the Redis backend is available (ping succeeds).
        Uses a short TTL cache to avoid repeated pings.
        """
        # Try to attach a backend if we don't have one yet
        await self._ensure_backend()
        if self._redis is None:
            return False
        now = time.time()
        if (
            self._backend_checked
            and (now - self._backend_last_check) < self._backend_ttl_seconds
        ):
            return self._backend_available
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: self._redis.ping())
            self._backend_available = bool(result)
        except Exception:
            self._backend_available = False
            # Detach broken backend and allow reconnect attempts on next call
            self._redis = None
            self._backend_checked = False
            self._backend_last_check = 0.0
            # Allow immediate reconnect attempt
            self._reconnect_last_attempt = 0.0
        finally:
            self._backend_checked = True
            self._backend_last_check = now
        return self._backend_available

    # ---------------------------------------------------------------------
    # Basic hash ops - *all async* to match AgentRegistry's async context
    # ---------------------------------------------------------------------
    async def hset(self, bucket: str, key: str, value: Any) -> None:
        await self._ensure_backend()
        if self._redis is not None:
            try:
                # Serialize value if it's not a simple type
                redis_value = value
                if isinstance(value, (dict, list)):
                    redis_value = json.dumps(value, default=str)
                elif hasattr(value, "model_dump"):  # Pydantic model
                    redis_value = json.dumps(value.model_dump(), default=str)
                elif hasattr(value, "dict"):  # Pydantic v1 model
                    redis_value = json.dumps(value.dict(), default=str)
                elif not isinstance(value, (str, bytes, int, float)):
                    redis_value = str(value)

                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hset(bucket, key, redis_value)
                )
                # Also mirror to fallback cache for warm failover
                async with self._fallback_lock:
                    self._fallback.setdefault(bucket, {})[key] = value
                return
            except Exception:
                # Detach backend on error and fall back
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        # Fallback - store raw python object with lock protection
        async with self._fallback_lock:
            self._fallback.setdefault(bucket, {})[key] = value

    async def hget(self, bucket: str, key: str) -> Optional[Any]:
        await self._ensure_backend()
        if self._redis is not None:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hget(bucket, key)
                )
                if result is not None:
                    # Try to deserialize JSON if it looks like JSON
                    if isinstance(result, bytes):
                        result = result.decode()
                    if isinstance(result, str) and (
                        result.startswith("{") or result.startswith("[")
                    ):
                        try:
                            return json.loads(result)
                        except json.JSONDecodeError:
                            pass
                    return result
            except Exception:
                # Detach backend on error and fall back
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        async with self._fallback_lock:
            # Auto-register bucket if it doesn't exist
            if bucket not in self._fallback:
                self._fallback[bucket] = {}
            return self._fallback[bucket].get(key)

    async def hkeys(self, bucket: str) -> List[str]:
        await self._ensure_backend()
        if self._redis is not None:
            try:
                keys = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hkeys(bucket)
                )
                return [k.decode() if isinstance(k, bytes) else str(k) for k in keys]
            except Exception:
                # Detach backend on error and fall back
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        async with self._fallback_lock:
            return list(self._fallback.get(bucket, {}).keys())

    async def hgetall(self, bucket: str) -> Dict[str, Any]:
        """Return all key-value pairs in a bucket"""
        await self._ensure_backend()
        if self._redis is not None:
            try:
                data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hgetall(bucket)
                )
                # Convert bytes keys/values to strings
                result = {}
                for k, v in data.items():
                    key = k.decode() if isinstance(k, bytes) else str(k)
                    try:
                        # Try to parse as JSON first
                        value = json.loads(
                            v.decode() if isinstance(v, bytes) else str(v)
                        )
                    except (json.JSONDecodeError, AttributeError):
                        # If not JSON, use as string
                        value = v.decode() if isinstance(v, bytes) else str(v)
                    result[key] = value
                return result
            except Exception:
                # Detach backend on error and fall back
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        async with self._fallback_lock:
            return dict(self._fallback.get(bucket, {}))

    async def hdel(self, bucket: str, key: str) -> None:
        await self._ensure_backend()
        if self._redis is not None:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hdel(bucket, key)
                )
            except Exception:
                # Detach backend on error and continue
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        # Always ensure fallback is clean as well
        async with self._fallback_lock:
            self._fallback.get(bucket, {}).pop(key, None)

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if a key exists in the bucket"""
        await self._ensure_backend()
        if self._redis is not None:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._redis.hexists(bucket, key)
                )
                return bool(result)
            except Exception:
                # Detach backend on error and fall back
                self._redis = None
                self._backend_checked = False
                self._backend_last_check = 0.0
                self._reconnect_last_attempt = 0.0
        async with self._fallback_lock:
            # Auto-register bucket if it doesn't exist
            if bucket not in self._fallback:
                self._fallback[bucket] = {}
            return key in self._fallback[bucket]

    # ---------------------------------------------------------------------
    # Convenience methods for non-hash operations
    # ---------------------------------------------------------------------
    async def set(self, bucket: str, key: str, value: Any) -> None:
        """Convenience method for setting a simple key-value pair"""
        await self.hset(bucket, key, value)

    async def get(self, bucket: str, key: str) -> Optional[Any]:
        """Convenience method for getting a simple key-value pair"""
        return await self.hget(bucket, key)

    async def delete(self, bucket: str, key: str) -> None:
        """Convenience method for deleting a simple key-value pair"""
        await self.hdel(bucket, key)
