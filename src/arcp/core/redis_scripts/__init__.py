"""
Redis Lua script loader and executor for ARCP.

This module loads Lua scripts from the redis_scripts directory
and provides an executor class for running them against Redis.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import redis

logger = logging.getLogger(__name__)

# Load Lua scripts
SCRIPT_DIR = Path(__file__).parent
SCRIPTS: Dict[str, str] = {}


def load_scripts():
    """
    Load all .lua files from the redis_scripts directory.

    Scripts are loaded into the SCRIPTS dictionary with their
    filename (without extension) as the key.
    """
    if not SCRIPT_DIR.exists():
        logger.warning(f"Redis scripts directory not found: {SCRIPT_DIR}")
        return

    for lua_file in SCRIPT_DIR.glob("*.lua"):
        script_name = lua_file.stem
        try:
            with open(lua_file, "r", encoding="utf-8") as f:
                script_content = f.read()
                SCRIPTS[script_name] = script_content
                logger.debug(
                    f"Loaded Lua script: {script_name} ({len(script_content)} bytes)"
                )
        except Exception as e:
            logger.error(f"Failed to load Lua script {lua_file}: {e}")

    logger.info(f"Loaded {len(SCRIPTS)} Lua script(s) from {SCRIPT_DIR}")


# Load scripts on module import
load_scripts()


class LuaScriptExecutor:
    """
    Execute Redis Lua scripts with automatic SHA caching.

    This class manages loading scripts into Redis via SCRIPT LOAD,
    caching their SHAs, and executing them via EVALSHA for performance.
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Lua script executor.

        Args:
            redis_client: Redis client instance
        """
        self.client = redis_client
        self.script_shas: Dict[str, str] = {}

    def get_script(self, name: str) -> Optional[str]:
        """
        Get Lua script content by name.

        Args:
            name: Script name (without .lua extension)

        Returns:
            Script content if found, None otherwise
        """
        return SCRIPTS.get(name)

    def load_script(self, name: str) -> Optional[str]:
        """
        Load a script into Redis and cache its SHA.

        Args:
            name: Script name (without .lua extension)

        Returns:
            SHA hash of loaded script, None if script not found
        """
        script = self.get_script(name)
        if not script:
            logger.error(f"Script '{name}' not found in loaded scripts")
            return None

        try:
            sha = self.client.script_load(script)
            self.script_shas[name] = sha
            logger.debug(f"Loaded script '{name}' into Redis: SHA={sha}")
            return sha
        except Exception as e:
            logger.error(f"Failed to load script '{name}' into Redis: {e}")
            return None

    def execute(self, script_name: str, keys: List[str], args: List) -> str:
        """
        Execute a Lua script using EVALSHA.

        The script is loaded into Redis on first execution and
        cached for subsequent calls.

        Args:
            script_name: Name of script to execute
            keys: List of Redis keys (KEYS in Lua)
            args: List of arguments (ARGV in Lua)

        Returns:
            Script execution result as string

        Raises:
            ValueError: If script not found
            redis.RedisError: If execution fails
        """
        script = self.get_script(script_name)
        if not script:
            raise ValueError(f"Script '{script_name}' not found")

        # Load script if not already cached
        if script_name not in self.script_shas:
            sha = self.load_script(script_name)
            if not sha:
                raise ValueError(f"Failed to load script '{script_name}'")
        else:
            sha = self.script_shas[script_name]

        try:
            # Execute via EVALSHA for performance
            result = self.client.evalsha(sha, len(keys), *keys, *args)

            # Decode bytes to string if needed
            if isinstance(result, bytes):
                return result.decode("utf-8")
            return result

        except redis.exceptions.NoScriptError:
            # Script not in Redis cache, reload and retry
            logger.warning(f"Script '{script_name}' not in Redis, reloading")
            sha = self.load_script(script_name)
            if not sha:
                raise ValueError(f"Failed to reload script '{script_name}'")

            result = self.client.evalsha(sha, len(keys), *keys, *args)
            if isinstance(result, bytes):
                return result.decode("utf-8")
            return result

    async def execute_async(self, script_name: str, keys: List[str], args: List) -> str:
        """
        Execute a Lua script asynchronously (for async Redis clients).

        Note: This is a placeholder for future async support.
        Currently just calls synchronous execute().

        Args:
            script_name: Name of script to execute
            keys: List of Redis keys
            args: List of arguments

        Returns:
            Script execution result as string

        Note:
            Current implementation uses run_in_executor to avoid blocking
            the event loop. Compatible with synchronous redis-py client.

            Alternative for async Redis (redis.asyncio):
              If migrating to redis.asyncio, use native async methods
        """
        # Use asyncio executor to run synchronous Redis without blocking
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,  # Uses default ThreadPoolExecutor
            lambda: self.execute(script_name, keys, args),
        )


def consume_validation_token(
    redis_client: redis.Redis, validation_id: str, now_timestamp: Optional[int] = None
) -> dict:
    """
    Atomically consume a validation token using Lua script.

    This is a convenience wrapper around the consume_validation.lua script.

    Args:
        redis_client: Redis client instance
        validation_id: Validation ID to consume
        now_timestamp: Current timestamp (epoch seconds), defaults to current time

    Returns:
        Dict with:
        - ok: bool - whether consumption succeeded
        - binding: dict - security binding (if ok=true)
        - error: str - error code (if ok=false)

    Example:
        >>> result = consume_validation_token(redis_client, "val_abc123")
        >>> if result["ok"]:
        ...     print(f"Consumed! Binding: {result['binding']}")
        ... else:
        ...     print(f"Failed: {result['error']}")
    """
    if now_timestamp is None:
        now_timestamp = int(time.time())

    executor = LuaScriptExecutor(redis_client)

    keys = [f"val:{validation_id}"]
    args = [str(now_timestamp)]

    try:
        result_json = executor.execute("consume_validation", keys, args)
        result = json.loads(result_json)
        return result
    except Exception as e:
        logger.error(f"Failed to execute consume_validation script: {e}")
        return {"ok": False, "error": "SCRIPT_ERROR", "details": str(e)}
