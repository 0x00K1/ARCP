"""
Rate limiting and brute force protection utilities for ARCP.

This module provides comprehensive rate limiting and brute force protection
for authentication endpoints, including progressive delays and temporary lockouts,
with advanced anti-bypass protection.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..core.config import config
from ..core.storage_adapter import StorageAdapter
from ..services import get_redis_service

logger = logging.getLogger(__name__)

# Buckets for StorageAdapter (Redis-first with in-memory fallback)
RL_BUCKET_LOGIN = "rl:login"
RL_BUCKET_PIN = "rl:pin"
RL_BUCKET_GLOBAL = "rl:global"

# Initialize a module-level StorageAdapter lazily to avoid import-order issues
_storage: Optional[StorageAdapter] = None


def _get_storage() -> StorageAdapter:
    """Get a cached StorageAdapter wired to Redis if available, else fallback memory.
    Registers required buckets on first use.
    """
    global _storage
    if _storage is not None:
        return _storage

    # Use Redis service
    redis_service = get_redis_service()
    redis_client = redis_service.get_client()

    if redis_client:
        logger.info("RateLimiter storage using Redis backend")
    else:
        logger.warning("Redis unavailable for RateLimiter, using in-memory fallback")

    _storage = StorageAdapter(redis_client)
    # Register buckets with empty fallback dicts
    _storage.register_bucket(RL_BUCKET_LOGIN, {})
    _storage.register_bucket(RL_BUCKET_PIN, {})
    _storage.register_bucket(RL_BUCKET_GLOBAL, {})
    return _storage


@dataclass
class AttemptInfo:
    """Information about authentication attempts for an IP/user."""

    count: int = 0
    first_attempt: float = 0
    last_attempt: float = 0
    locked_until: Optional[float] = None
    lockout_count: int = 0  # Track number of lockouts for escalating penalties

    def to_dict(self) -> Dict[str, float]:
        return {
            "count": self.count,
            "first_attempt": self.first_attempt,
            "last_attempt": self.last_attempt,
            "locked_until": (
                self.locked_until if self.locked_until is not None else None
            ),
            "lockout_count": self.lockout_count,
        }

    @staticmethod
    def from_value(value: Optional[object]) -> Optional["AttemptInfo"]:
        if value is None:
            return None
        try:
            if isinstance(value, bytes):
                value = value.decode()
            if isinstance(value, str):
                data = json.loads(value)
            elif isinstance(value, dict):
                data = value
            else:
                return None
            return AttemptInfo(
                count=int(data.get("count", 0)),
                first_attempt=float(data.get("first_attempt", 0)),
                last_attempt=float(data.get("last_attempt", 0)),
                locked_until=(
                    float(data["locked_until"])
                    if data.get("locked_until") is not None
                    else None
                ),
                lockout_count=int(data.get("lockout_count", 0)),
            )
        except Exception:
            return None


class RateLimiter:
    """
    Advanced rate limiter with brute force protection and anti-bypass features.

    Features:
    - Progressive delays (exponential backoff)
    - Temporary lockouts after multiple failures
    - Escalating penalties for repeat offenders
    - Automatic cleanup of old entries
    - Separate tracking for different attempt types
    - Anti-bypass protection against header spoofing and session rotation
    """

    def __init__(
        self,
        max_attempts: int = 5,
        lockout_duration: int = 300,  # 5 minutes
        window_duration: int = 900,  # 15 minutes
        progressive_delay: bool = True,
        max_lockout_duration: int = 3600,  # 1 hour max lockout
        cleanup_interval: int = 300,  # 5 minutes
    ):
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_duration
        self.window_duration = window_duration
        self.progressive_delay = progressive_delay
        self.max_lockout_duration = max_lockout_duration
        self.cleanup_interval = cleanup_interval
        self.last_cleanup = time.time()

    def _bucket_for_type(self, attempt_type: str) -> str:
        if attempt_type == "login":
            return RL_BUCKET_LOGIN
        elif attempt_type == "pin":
            return RL_BUCKET_PIN
        else:
            return RL_BUCKET_GLOBAL

    async def _load(self, attempt_type: str, identifier: str) -> Optional[AttemptInfo]:
        storage = _get_storage()
        try:
            value = await storage.hget(self._bucket_for_type(attempt_type), identifier)
            return AttemptInfo.from_value(value)
        except Exception:
            return None

    async def _save(
        self, attempt_type: str, identifier: str, info: AttemptInfo
    ) -> None:
        storage = _get_storage()
        try:
            # Store as JSON string for consistency
            await storage.hset(
                self._bucket_for_type(attempt_type),
                identifier,
                json.dumps(info.to_dict()),
            )
        except Exception:
            pass

    async def _delete(self, attempt_type: str, identifier: str) -> None:
        storage = _get_storage()
        try:
            await storage.hdel(self._bucket_for_type(attempt_type), identifier)
        except Exception:
            pass

    async def _hkeys(self, attempt_type: str) -> List[str]:
        storage = _get_storage()
        try:
            return await storage.hkeys(self._bucket_for_type(attempt_type))
        except Exception:
            return []

    def _perform_cleanup(self) -> None:
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            # Best-effort async cleanup without blocking request path
            asyncio.create_task(self._async_cleanup())
            self.last_cleanup = current_time
            logger.debug("Scheduled rate limiter cleanup")

    async def _async_cleanup(self) -> None:
        try:
            now = time.time()
            for attempt_type in ("login", "pin", "global"):
                for key in await self._hkeys(attempt_type):
                    info = await self._load(attempt_type, key)
                    if info is None:
                        continue
                    if now - info.last_attempt > self.window_duration and (
                        not info.locked_until or now > info.locked_until
                    ):
                        await self._delete(attempt_type, key)
        except Exception:
            pass

    def calculate_delay(self, attempt_count: int, lockout_count: int = 0) -> float:
        if not self.progressive_delay:
            return 1.0
        base_delay = min(2 ** (attempt_count - 1), 60)
        repeat_penalty = lockout_count * 30
        total_delay = base_delay + repeat_penalty
        return min(total_delay, 300)

    def calculate_lockout_duration(self, lockout_count: int) -> float:
        duration = self.lockout_duration * (2 ** (lockout_count - 1))
        return min(duration, self.max_lockout_duration)

    async def check_rate_limit(
        self, identifier: str, attempt_type: str = "global"
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        self._perform_cleanup()
        identifiers = identifier.split("|") if "|" in identifier else [identifier]
        max_delay = 0
        block_reason = None
        for single_id in identifiers:
            if not single_id.strip():
                continue
            allowed, delay, reason = await self._check_single_identifier(
                single_id.strip(), attempt_type
            )
            if not allowed and delay and delay > max_delay:
                max_delay = delay
                block_reason = reason
        if block_reason:
            return False, max_delay, block_reason
        return True, None, None

    async def _check_single_identifier(
        self, identifier: str, attempt_type: str = "global"
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        info = await self._load(attempt_type, identifier)
        if info is None:
            info = AttemptInfo()
        current_time = time.time()
        if info.locked_until and current_time < info.locked_until:
            remaining_time = info.locked_until - current_time
            return (
                False,
                remaining_time,
                f"Temporarily locked out due to too many {attempt_type} attempts",
            )
        if info.locked_until and current_time >= info.locked_until:
            info.locked_until = None
            logger.info(f"Lockout expired for {identifier} ({attempt_type})")
            await self._save(attempt_type, identifier, info)
        if info.count > 1:
            delay = self.calculate_delay(info.count, info.lockout_count)
            time_since_last = current_time - info.last_attempt
            if time_since_last < delay:
                remaining_delay = delay - time_since_last
                return (
                    False,
                    remaining_delay,
                    f"Too many {attempt_type} attempts, wait !",
                )
        return True, None, None

    async def record_attempt(
        self, identifier: str, success: bool, attempt_type: str = "global"
    ) -> Optional[float]:
        identifiers = identifier.split("|") if "|" in identifier else [identifier]
        max_lockout = None
        for single_id in identifiers:
            if not single_id.strip():
                continue
            lockout = await self._record_single_attempt(
                single_id.strip(), success, attempt_type
            )
            if lockout and (max_lockout is None or lockout > max_lockout):
                max_lockout = lockout
        return max_lockout

    async def _record_single_attempt(
        self, identifier: str, success: bool, attempt_type: str = "global"
    ) -> Optional[float]:
        info = await self._load(attempt_type, identifier)
        if info is None:
            info = AttemptInfo()
        current_time = time.time()
        if success:
            logger.info(
                f"Successful {attempt_type} attempt for {identifier}, resetting counters"
            )
            info.count = 0
            info.first_attempt = 0
            info.last_attempt = current_time
            info.locked_until = None
            await self._save(attempt_type, identifier, info)
            return None
        if info.count == 0:
            info.first_attempt = current_time
        info.count += 1
        info.last_attempt = current_time
        logger.warning(
            f"Failed {attempt_type} attempt {info.count}/{self.max_attempts} for {identifier}"
        )
        if info.count >= self.max_attempts:
            info.lockout_count += 1
            lockout_duration = self.calculate_lockout_duration(info.lockout_count)
            info.locked_until = current_time + lockout_duration
            info.count = 0
            logger.error(
                f"Locking out {identifier} for {lockout_duration}s due to {self.max_attempts} "
                f"failed {attempt_type} attempts (lockout #{info.lockout_count})"
            )
            await self._save(attempt_type, identifier, info)
            return lockout_duration
        await self._save(attempt_type, identifier, info)
        return None

    def is_locked_out(self, identifier: str, attempt_type: str = "global") -> bool:
        """Synchronous helper for rare usage; uses cached check path by calling async version."""
        # Conservative approach: if async path can't be executed here, return False
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Fire-and-forget not possible; return False to avoid blocking
                return False
            allowed, delay, _ = loop.run_until_complete(
                self.check_rate_limit(identifier, attempt_type)
            )
            return not allowed
        except Exception:
            return False

    def get_attempt_count(self, identifier: str, attempt_type: str = "global") -> int:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return 0
            # Load current info synchronously via the loop
            bucket = self._bucket_for_type(attempt_type)
            storage = _get_storage()
            value = loop.run_until_complete(storage.hget(bucket, identifier))
            info = AttemptInfo.from_value(value)
            return info.count if info else 0
        except Exception:
            return 0

    def get_attempt_info(
        self, identifier: str, attempt_type: str = "global"
    ) -> Optional[AttemptInfo]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return None
            bucket = self._bucket_for_type(attempt_type)
            storage = _get_storage()
            value = loop.run_until_complete(storage.hget(bucket, identifier))
            return AttemptInfo.from_value(value)
        except Exception:
            return None

    def get_lockout_info(
        self, identifier: str, attempt_type: str = "global"
    ) -> Optional[Tuple[float, int]]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return None
            bucket = self._bucket_for_type(attempt_type)
            storage = _get_storage()
            value = loop.run_until_complete(storage.hget(bucket, identifier))
            info = AttemptInfo.from_value(value)
            if not info or not info.locked_until:
                return None
            remaining = max(0, info.locked_until - time.time())
            if remaining <= 0:
                return None
            return remaining, info.lockout_count
        except Exception:
            return None

    def clear_attempts(
        self, identifier: str, attempt_type: Optional[str] = None
    ) -> None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return
            storage = _get_storage()
            if attempt_type:
                loop.run_until_complete(
                    storage.hdel(self._bucket_for_type(attempt_type), identifier)
                )
            else:
                for t in ("login", "pin", "global"):
                    loop.run_until_complete(
                        storage.hdel(self._bucket_for_type(t), identifier)
                    )
            logger.info(f"Cleared attempts for {identifier} ({attempt_type or 'all'})")
        except Exception:
            pass


def get_client_identifier(request) -> str:
    try:
        from fastapi import Request

        if not isinstance(request, Request):
            return "unknown"
        client_ip = "unknown"
        if request.client:
            client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")[:200]
        accept_header = request.headers.get("accept", "")[:100]
        accept_encoding = request.headers.get("accept-encoding", "")[:50]
        accept_language = request.headers.get("accept-language", "")[:50]
        method = request.method
        path = request.url.path
        ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
        browser_fingerprint = hashlib.sha256(
            f"{user_agent}:{accept_header}:{accept_encoding}:{accept_language}".encode()
        ).hexdigest()[:12]
        identifiers = [
            f"ip-{client_ip}",
            f"ua-combo-{client_ip}-{ua_hash}",
            f"browser-fp-{client_ip}-{browser_fingerprint}",
            f"full-fp-{hashlib.sha256(f'{client_ip}:{user_agent}:{accept_header}:{method}:{path}'.encode()).hexdigest()[:16]}",
        ]
        return "|".join(identifiers)
    except Exception as e:
        logger.warning(f"Failed to extract client identifier: {e}")
        return "unknown"


# Global rate limiter instances
login_rate_limiter = RateLimiter(
    max_attempts=int(getattr(config, "RATE_LIMIT_BURST", 5) or 5),
    lockout_duration=300,
    window_duration=int(getattr(config, "RATE_LIMIT_RPM", 100) or 100)
    * 9,  # approx 9x seconds window
    progressive_delay=True,
)

pin_rate_limiter = RateLimiter(
    max_attempts=max(1, int(getattr(config, "RATE_LIMIT_BURST", 3) or 3) // 2),
    lockout_duration=600,
    window_duration=max(300, int(getattr(config, "RATE_LIMIT_RPM", 100) or 100) * 12),
    progressive_delay=True,
)

general_rate_limiter = RateLimiter(
    max_attempts=max(5, int(getattr(config, "RATE_LIMIT_RPM", 100) or 100) // 10),
    lockout_duration=60,
    window_duration=300,
    progressive_delay=True,
)
