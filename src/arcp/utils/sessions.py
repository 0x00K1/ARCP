"""Session management utilities for ARCP dashboard authentication.

This module provides shared session helpers to avoid circular imports between
auth and dashboard modules.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import jwt
from fastapi import Header, Request

from ..core.config import config
from ..core.exceptions import (
    ARCPProblemTypes,
    authentication_failed_problem,
    create_problem_response,
    pin_problem,
    session_validation_failed_problem,
)
from ..core.storage_adapter import StorageAdapter
from ..core.token_service import get_token_service
from ..services import get_redis_service

logger = logging.getLogger(__name__)

# Buckets for storage
SESSION_PIN_BUCKET = "session:pins"
SESSION_INFO_BUCKET = "session:info"

# In-memory session stores act as a fallback if Redis is unavailable
session_pins: Dict[str, str] = {}
session_info: Dict[str, Dict[str, Any]] = {}

# Cached Redis client (module-level) and StorageAdapter
_redis_client = None
_storage: Optional[StorageAdapter] = None
# Replace hard disable with throttled retry
_last_redis_attempt: float = 0.0
_retry_interval_seconds: float = float(
    getattr(config, "REDIS_HEALTH_CHECK_INTERVAL", None) or 30
)


def _get_redis_client():
    """Get a cached Redis client if configuration is available.
    Returns None if Redis cannot be initialized or pinged.
    Retries on a throttled interval so that starting Redis later is detected.
    """
    global _redis_client, _last_redis_attempt
    if _redis_client is not None:
        return _redis_client

    now = time.time()
    if (now - _last_redis_attempt) < _retry_interval_seconds:
        return None
    _last_redis_attempt = now

    try:
        redis_service = get_redis_service()
        client = redis_service.get_client()
        if client:
            _redis_client = client
            logger.info("Session store using Redis backend")
            return _redis_client
        return None
    except Exception as e:  # pragma: no cover - environment dependent
        if _redis_client is None:
            logger.debug(f"Redis unavailable for sessions (will retry): {e}")
        _redis_client = None
        return None


def _get_storage() -> StorageAdapter:
    """Get a cached StorageAdapter wired to Redis if available, else fallback memory.
    Register session buckets pointing to the in-memory fallbacks.
    """
    global _storage
    if _storage is not None:
        return _storage

    client = _get_redis_client()
    _storage = StorageAdapter(client)
    # Register buckets using our module-level fallback dicts
    _storage.register_bucket(SESSION_PIN_BUCKET, session_pins)
    _storage.register_bucket(SESSION_INFO_BUCKET, session_info)
    return _storage


def _loop_is_running() -> bool:
    try:
        loop = asyncio.get_event_loop()
        return loop.is_running()
    except Exception:
        return False


def create_session_key(
    user_id: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
) -> str:
    """Create a unique session key for user + client fingerprint + token ref combination."""
    parts = [user_id]
    if client_fingerprint:
        parts.append(client_fingerprint)
    if token_ref:
        parts.append(token_ref)
    return ":".join(parts)


def get_token_ref_from_request(request: Request) -> Optional[str]:
    """Extract a short token reference from Authorization header for session isolation."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    # Use last 10 chars as lightweight token reference (matches login storage)
    try:
        return token[-10:]
    except Exception:
        return None


def hash_pin(pin: str) -> str:
    """Hash a PIN using SHA256."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def get_token_payload(token: str) -> Dict[str, Any]:
    """Get payload from JWT token with error handling.

    If token validation fails, attempt best-effort cleanup of session data for the
    corresponding user across both Redis and fallback memory.
    """
    try:
        service = get_token_service()
        payload = service.validate_token(token)
        return payload
    except Exception as e:
        # If token validation fails, clear session data
        logger.warning(f"Token validation failed: {e}")

        # Try to extract user_id from expired token for cleanup (best effort)
        try:
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            user_id = unverified_payload.get("sub")
            if user_id:
                _delete_all_sessions_for_user(user_id)
        except Exception as cleanup_error:
            logger.debug(
                f"Could not extract user info from invalid token for cleanup: {cleanup_error}"
            )

        return {}


def _delete_all_sessions_for_user(user_id: str) -> None:
    """Delete all session records for a given user from storage and fallback memory."""
    prefix = f"{user_id}:"

    # Try StorageAdapter via sync bridging
    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            # Delete direct key
            loop.run_until_complete(storage.hdel(SESSION_PIN_BUCKET, user_id))
            loop.run_until_complete(storage.hdel(SESSION_INFO_BUCKET, user_id))
            # Delete prefixed keys
            for key in loop.run_until_complete(storage.hkeys(SESSION_PIN_BUCKET)):
                if key == user_id or key.startswith(prefix):
                    loop.run_until_complete(storage.hdel(SESSION_PIN_BUCKET, key))
            for key in loop.run_until_complete(storage.hkeys(SESSION_INFO_BUCKET)):
                if key == user_id or key.startswith(prefix):
                    loop.run_until_complete(storage.hdel(SESSION_INFO_BUCKET, key))
        else:
            # Loop is running; do best-effort direct Redis cleanup if enabled
            client = _get_redis_client()
            if client is not None:
                try:
                    client.hdel(SESSION_PIN_BUCKET, user_id)
                except Exception:
                    pass
                try:
                    client.hdel(SESSION_INFO_BUCKET, user_id)
                except Exception:
                    pass
                try:
                    for key in [
                        k.decode() if isinstance(k, bytes) else str(k)
                        for k in client.hkeys(SESSION_PIN_BUCKET)
                    ]:
                        if key == user_id or key.startswith(prefix):
                            client.hdel(SESSION_PIN_BUCKET, key)
                except Exception:
                    pass
                try:
                    for key in [
                        k.decode() if isinstance(k, bytes) else str(k)
                        for k in client.hkeys(SESSION_INFO_BUCKET)
                    ]:
                        if key == user_id or key.startswith(prefix):
                            client.hdel(SESSION_INFO_BUCKET, key)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Storage cleanup error for user {user_id}: {e}")

    # Always cleanup fallback memory
    keys_to_remove = [
        key for key in session_pins.keys() if key == user_id or key.startswith(prefix)
    ]
    for key in keys_to_remove:
        session_pins.pop(key, None)
        logger.info(f"Cleared session PIN (fallback) for expired token: {key}")

    info_keys_to_remove = [
        key for key in session_info.keys() if key == user_id or key.startswith(prefix)
    ]
    for key in info_keys_to_remove:
        session_info.pop(key, None)
        logger.info(f"Cleared session info (fallback) for expired token: {key}")


def verify_token_header(request: Request) -> Dict[str, Any]:
    """Verify only token for read-only operations (no PIN required)."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(
            f"[{datetime.now()}] Access attempt without token from {request.client.host if request.client else 'unknown'}"
        )
        return authentication_failed_problem("Authentication required", request)

    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = get_token_payload(token)

    if not payload or payload.get("role") != "admin":
        logger.warning(
            f"[{datetime.now()}] Non-admin access attempt from {request.client.host if request.client else 'unknown'}"
        )
        return create_problem_response(
            problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
            detail="Admin role required",
            request=request,
        )

    user_id = payload.get("sub")
    if not user_id:
        logger.warning(
            f"[{datetime.now()}] Invalid token from {request.client.host if request.client else 'unknown'}"
        )
        return authentication_failed_problem("Invalid token", request)

    return payload


def verify_pin_header(
    request: Request,
    x_session_pin: Optional[str] = Header(None, alias="X-Session-Pin"),
    x_client_fingerprint: Optional[str] = Header(None, alias="X-Client-Fingerprint"),
) -> Dict[str, Any]:
    """Verify PIN header for critical dashboard operations."""
    # First verify token
    payload = verify_token_header(request)
    user_id = payload.get("sub")

    # Verify client fingerprint matches session using session isolation
    session = get_session_info(user_id, x_client_fingerprint)
    if session and session.get("client_fingerprint") and x_client_fingerprint:
        if session["client_fingerprint"] != x_client_fingerprint:
            logger.warning(
                f"[{datetime.now()}] Client fingerprint mismatch for user {user_id}: expected {session['client_fingerprint'][:8]}, got {x_client_fingerprint[:8]}"
            )
            return session_validation_failed_problem(
                "Session validation failed", request
            )
    elif session and session.get("client_fingerprint") and not x_client_fingerprint:
        logger.warning(
            f"[{datetime.now()}] Missing client fingerprint for user {user_id}"
        )
        return session_validation_failed_problem("Session validation failed", request)

    # Check if PIN is provided for critical operations
    if x_session_pin:
        # Verify the provided PIN using session isolation
        if not has_session_pin(user_id, x_client_fingerprint):
            logger.warning(
                f"[{datetime.now()}] PIN verification attempt with no PIN set. User: {user_id} from {request.client.host if request.client else 'unknown'}"
            )
            return pin_problem(
                ARCPProblemTypes.PIN_NOT_SET,
                "PIN not set for session",
                request,
            )

        if not verify_session_pin(user_id, x_session_pin, x_client_fingerprint):
            logger.warning(
                f"[{datetime.now()}] Incorrect PIN attempt by user: {user_id} from {request.client.host if request.client else 'unknown'}"
            )
            return pin_problem(ARCPProblemTypes.PIN_INCORRECT, "Incorrect PIN", request)

        logger.info(
            f"[{datetime.now()}] Successful PIN verification for user: {user_id} from {request.client.host if request.client else 'unknown'}"
        )
    else:
        # For non-critical operations, just log the access
        logger.info(
            f"[{datetime.now()}] Access by user: {user_id} from {request.client.host if request.client else 'unknown'}"
        )

    return payload


def store_session_info(
    user_id: str,
    client_ip: str,
    user_agent: str,
    client_fingerprint: Optional[str],
    token_ref: str,
):
    """Store session information for a user with session isolation. StorageAdapter-first with fallback.
    Adds expire_at based on SESSION_TIMEOUT configuration.
    """
    session_key = create_session_key(user_id, client_fingerprint, token_ref)
    payload = {
        "ip": client_ip,
        "user_agent": user_agent,
        "client_fingerprint": client_fingerprint,
        "login_time": datetime.now().isoformat(),
        "token_id": token_ref,
    }

    # Add expire_at to enforce server-side session TTL
    try:
        # Minutes → seconds; use SESSION_TIMEOUT
        timeout_minutes = int(getattr(config, "SESSION_TIMEOUT", 60) or 60)
        effective_minutes = max(1, timeout_minutes)
        payload["expire_at"] = int(time.time()) + int(effective_minutes * 60)
    except Exception:
        pass

    try:
        import asyncio

        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            loop.run_until_complete(
                storage.hset(SESSION_INFO_BUCKET, session_key, json.dumps(payload))
            )
            logger.debug(
                f"Stored session info via StorageAdapter for key: {session_key}"
            )
            # Enforce maximum concurrent sessions per user if configured
            try:
                _enforce_max_sessions(user_id)
            except Exception:
                pass
            return
        else:
            # Loop running; use direct Redis client synchronously if enabled
            client = _get_redis_client()
            if client is not None:
                client.hset(SESSION_INFO_BUCKET, session_key, json.dumps(payload))
                logger.debug(f"Stored session info in Redis for key: {session_key}")
                # Mirror to fallback for warm failover
                session_info[session_key] = payload
                try:
                    _enforce_max_sessions(user_id)
                except Exception:
                    pass
                return
    except Exception as e:
        logger.warning(f"Storage error storing session info (fallback to memory): {e}")

    # Fallback
    session_info[session_key] = payload
    logger.debug(
        f"Session stored in fallback memory. Total sessions: {len(session_info)}"
    )
    try:
        _enforce_max_sessions(user_id)
    except Exception:
        pass


def _enforce_max_sessions(user_id: str) -> None:
    """Best-effort enforcement of MAX_SESSIONS per user.

    Keeps only the most recent N sessions (by login_time/expire_at timestamp) for a user.
    Works across StorageAdapter if available; always mirrors changes to fallback memory.
    """
    try:
        max_sessions = int(getattr(config, "MAX_SESSIONS", 0) or 0)
    except Exception:
        max_sessions = 0
    if max_sessions <= 0:
        return

    # Collect all session entries for this user
    prefix = f"{user_id}:"
    records: list[tuple[str, int]] = []  # (key, sort_ts)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            keys = loop.run_until_complete(storage.hkeys(SESSION_INFO_BUCKET))
            for key in keys:
                if key == user_id or key.startswith(prefix):
                    value = loop.run_until_complete(
                        storage.hget(SESSION_INFO_BUCKET, key)
                    )
                    try:
                        text = value.decode() if isinstance(value, bytes) else value
                        data = (
                            json.loads(text)
                            if isinstance(text, str)
                            else (value if isinstance(value, dict) else None)
                        )
                        if isinstance(data, dict):
                            ts = int(data.get("expire_at") or 0)
                            # Prefer login_time as secondary if available
                            if ts == 0:
                                ts = int(time.time())
                            records.append((key, ts))
                    except Exception:
                        continue
        else:
            client = _get_redis_client()
            if client is not None:
                for raw in [
                    k.decode() if isinstance(k, bytes) else str(k)
                    for k in client.hkeys(SESSION_INFO_BUCKET)
                ]:
                    if raw == user_id or raw.startswith(prefix):
                        value = client.hget(SESSION_INFO_BUCKET, raw)
                        try:
                            text = value.decode() if isinstance(value, bytes) else value
                            data = json.loads(text) if isinstance(text, str) else None
                            if isinstance(data, dict):
                                ts = int(data.get("expire_at") or 0)
                                if ts == 0:
                                    ts = int(time.time())
                                records.append((raw, ts))
                        except Exception:
                            continue
    except Exception:
        # Fall back to in-memory inspection only
        pass

    # Include fallback sessions as well
    for key, data in list(session_info.items()):
        if key == user_id or key.startswith(prefix):
            try:
                ts = int(data.get("expire_at") or 0) if isinstance(data, dict) else 0
                if ts == 0:
                    ts = int(time.time())
                records.append((key, ts))
            except Exception:
                continue

    # Sort newest first and determine excess
    unique: dict[str, int] = {}
    for k, ts in records:
        unique[k] = max(unique.get(k, 0), ts)
    sorted_keys = sorted(unique.items(), key=lambda it: it[1], reverse=True)
    if len(sorted_keys) <= max_sessions:
        return

    to_remove = [k for k, _ in sorted_keys[max_sessions:]]

    # Remove from storage and fallback
    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            for k in to_remove:
                loop.run_until_complete(storage.hdel(SESSION_INFO_BUCKET, k))
        else:
            client = _get_redis_client()
            if client is not None:
                for k in to_remove:
                    try:
                        client.hdel(SESSION_INFO_BUCKET, k)
                    except Exception:
                        pass
    except Exception:
        pass
    for k in to_remove:
        session_info.pop(k, None)


def clear_session_data(
    user_id: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
):
    """Clear session data for a user with optional client fingerprint for session isolation."""
    session_key = create_session_key(user_id, client_fingerprint, token_ref)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            loop.run_until_complete(storage.hdel(SESSION_PIN_BUCKET, session_key))
            loop.run_until_complete(storage.hdel(SESSION_INFO_BUCKET, session_key))
            if client_fingerprint:
                loop.run_until_complete(storage.hdel(SESSION_PIN_BUCKET, user_id))
                loop.run_until_complete(storage.hdel(SESSION_INFO_BUCKET, user_id))
        else:
            client = _get_redis_client()
            if client is not None:
                try:
                    client.hdel(SESSION_PIN_BUCKET, session_key)
                except Exception:
                    pass
                try:
                    client.hdel(SESSION_INFO_BUCKET, session_key)
                except Exception:
                    pass
                if client_fingerprint:
                    try:
                        client.hdel(SESSION_PIN_BUCKET, user_id)
                    except Exception:
                        pass
                    try:
                        client.hdel(SESSION_INFO_BUCKET, user_id)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Storage clear_session_data error: {e}")

    # Always cleanup fallback memory
    session_pins.pop(session_key, None)
    session_info.pop(session_key, None)
    if client_fingerprint and user_id in session_pins:
        session_pins.pop(user_id, None)
    if client_fingerprint and user_id in session_info:
        session_info.pop(user_id, None)


def set_session_pin(
    user_id: str,
    pin: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
):
    """Set a session PIN for a user with optional client fingerprint for session isolation."""
    session_key = create_session_key(user_id, client_fingerprint, token_ref)
    hashed = hash_pin(pin)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            loop.run_until_complete(
                storage.hset(SESSION_PIN_BUCKET, session_key, hashed)
            )
            logger.debug(
                f"Stored session PIN via StorageAdapter for key: {session_key}"
            )
            # Keep fallback updated as well (best-effort cache)
            session_pins[session_key] = hashed
            return
        else:
            client = _get_redis_client()
            if client is not None:
                client.hset(SESSION_PIN_BUCKET, session_key, hashed)
                logger.debug(f"Stored session PIN in Redis for key: {session_key}")
                session_pins[session_key] = hashed
                return
    except Exception as e:
        logger.warning(f"Storage error setting session PIN (fallback to memory): {e}")

    # Fallback
    session_pins[session_key] = hashed


def verify_session_pin(
    user_id: str,
    pin: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
) -> bool:
    """Verify a session PIN for a user with optional client fingerprint. StorageAdapter-first with fallback."""
    session_key = create_session_key(user_id, client_fingerprint, token_ref)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            value = loop.run_until_complete(
                storage.hget(SESSION_PIN_BUCKET, session_key)
            )
            if value is not None:
                stored_hash = (
                    value.decode()
                    if isinstance(value, bytes)
                    else (value if isinstance(value, str) else str(value))
                )
                return hash_pin(pin) == stored_hash
        else:
            client = _get_redis_client()
            if client is not None:
                value = client.hget(SESSION_PIN_BUCKET, session_key)
                if value is not None:
                    stored_hash = (
                        value.decode() if isinstance(value, bytes) else str(value)
                    )
                    return hash_pin(pin) == stored_hash
    except Exception as e:
        logger.warning(f"Storage error verifying session PIN (fallback to memory): {e}")

    # Fallback
    stored_hash = session_pins.get(session_key)
    if not stored_hash:
        return False
    return hash_pin(pin) == stored_hash


def has_session_pin(
    user_id: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
) -> bool:
    """Check if a user has a session PIN set with optional client fingerprint."""
    session_key = create_session_key(user_id, client_fingerprint, token_ref)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            return bool(
                loop.run_until_complete(storage.exists(SESSION_PIN_BUCKET, session_key))
            )
        else:
            client = _get_redis_client()
            if client is not None:
                return bool(client.hexists(SESSION_PIN_BUCKET, session_key))
    except Exception:
        pass

    return session_key in session_pins


def get_session_info(
    user_id: str,
    client_fingerprint: Optional[str] = None,
    token_ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get session information for a user with optional client fingerprint."""
    session_key = create_session_key(user_id, client_fingerprint, token_ref)

    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            value = loop.run_until_complete(
                storage.hget(SESSION_INFO_BUCKET, session_key)
            )
            if value is not None:
                try:
                    if isinstance(value, dict):
                        # Enforce TTL if present
                        exp = (
                            value.get("expire_at") if isinstance(value, dict) else None
                        )
                        if isinstance(exp, (int, float)) and time.time() > float(exp):
                            # Session expired; cleanup and return None
                            loop.run_until_complete(
                                storage.hdel(SESSION_INFO_BUCKET, session_key)
                            )
                            session_info.pop(session_key, None)
                            return None
                        return value
                    text = value.decode() if isinstance(value, bytes) else value
                    data = json.loads(text) if isinstance(text, str) else None
                    if isinstance(data, dict):
                        exp = data.get("expire_at")
                        if isinstance(exp, (int, float)) and time.time() > float(exp):
                            loop.run_until_complete(
                                storage.hdel(SESSION_INFO_BUCKET, session_key)
                            )
                            session_info.pop(session_key, None)
                            return None
                        return data
                    return None
                except Exception:
                    return None
        else:
            client = _get_redis_client()
            if client is not None:
                value = client.hget(SESSION_INFO_BUCKET, session_key)
                if value is not None:
                    try:
                        text = value.decode() if isinstance(value, bytes) else value
                        data = json.loads(text) if isinstance(text, str) else None
                        if isinstance(data, dict):
                            exp = data.get("expire_at")
                            if isinstance(exp, (int, float)) and time.time() > float(
                                exp
                            ):
                                try:
                                    client.hdel(SESSION_INFO_BUCKET, session_key)
                                except Exception:
                                    pass
                                session_info.pop(session_key, None)
                                return None
                            return data
                        return None
                    except Exception:
                        return None
    except Exception as e:
        logger.warning(f"Storage error getting session info (fallback to memory): {e}")

    # Fallback
    data = session_info.get(session_key)
    if isinstance(data, dict):
        exp = data.get("expire_at")
        if isinstance(exp, (int, float)) and time.time() > float(exp):
            session_info.pop(session_key, None)
            return None
    return data


def find_user_session(user_id: str) -> Optional[Dict[str, Any]]:
    """Find any session for a user, checking both old and new formats. StorageAdapter-first with fallback."""
    try:
        if not _loop_is_running():
            loop = asyncio.get_event_loop()
            storage = _get_storage()
            # First try direct user_id (old format)
            direct = loop.run_until_complete(storage.hget(SESSION_INFO_BUCKET, user_id))
            if direct is not None:
                try:
                    if isinstance(direct, dict):
                        return direct
                    text = direct.decode() if isinstance(direct, bytes) else direct
                    data = json.loads(text) if isinstance(text, str) else None
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
            # Then scan for any key with user_id prefix (new format)
            prefix = f"{user_id}:"
            for key in loop.run_until_complete(storage.hkeys(SESSION_INFO_BUCKET)):
                if key.startswith(prefix):
                    value = loop.run_until_complete(
                        storage.hget(SESSION_INFO_BUCKET, key)
                    )
                    if value is not None:
                        try:
                            if isinstance(value, dict):
                                return value
                            text = value.decode() if isinstance(value, bytes) else value
                            data = json.loads(text) if isinstance(text, str) else None
                            if isinstance(data, dict):
                                return data
                        except Exception:
                            continue
        else:
            client = _get_redis_client()
            if client is not None:
                # Direct user_id
                direct = client.hget(SESSION_INFO_BUCKET, user_id)
                if direct is not None:
                    try:
                        text = direct.decode() if isinstance(direct, bytes) else direct
                        data = json.loads(text) if isinstance(text, str) else None
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
                # Prefixed keys
                prefix = f"{user_id}:"
                try:
                    for key in [
                        k.decode() if isinstance(k, bytes) else str(k)
                        for k in client.hkeys(SESSION_INFO_BUCKET)
                    ]:
                        if key.startswith(prefix):
                            value = client.hget(SESSION_INFO_BUCKET, key)
                            if value is not None:
                                try:
                                    text = (
                                        value.decode()
                                        if isinstance(value, bytes)
                                        else value
                                    )
                                    data = (
                                        json.loads(text)
                                        if isinstance(text, str)
                                        else None
                                    )
                                    if isinstance(data, dict):
                                        return data
                                except Exception:
                                    continue
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Storage error in find_user_session: {e}")

    # Fallback lookups
    if user_id in session_info:
        return session_info[user_id]

    for key, sess in session_info.items():
        if key.startswith(f"{user_id}:"):
            return sess

    return None
