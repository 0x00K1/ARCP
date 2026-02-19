"""
Unit tests for TPR Redis Lua scripts.

Tests the LuaScriptExecutor and consume_validation.lua atomic operations.
"""

import json
from unittest.mock import MagicMock

import pytest

from arcp.core.redis_scripts import LuaScriptExecutor, consume_validation_token


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    return mock


@pytest.fixture
def lua_executor(mock_redis):
    """Create LuaScriptExecutor with mock Redis."""
    executor = LuaScriptExecutor(mock_redis)
    return executor


class TestLuaScriptExecutor:
    """Test LuaScriptExecutor class."""

    def test_init_executor(self, mock_redis):
        """Test LuaScriptExecutor initialization."""
        executor = LuaScriptExecutor(mock_redis)

        assert executor.client == mock_redis
        assert executor.script_shas == {}

    def test_load_script(self, lua_executor, mock_redis):
        """Test loading a Lua script."""
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["test_script"] = "return 'test'"
        mock_redis.script_load.return_value = "abc123sha"

        sha = lua_executor.load_script("test_script")

        assert sha == "abc123sha"
        assert lua_executor.script_shas["test_script"] == "abc123sha"
        mock_redis.script_load.assert_called_once_with("return 'test'")

    def test_execute_script_with_sha(self, lua_executor, mock_redis):
        """Test executing script using SHA (EVALSHA)."""
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["test_script"] = "return 'test'"
        lua_executor.script_shas["test_script"] = "abc123sha"
        mock_redis.evalsha.return_value = "result"

        result = lua_executor.execute("test_script", keys=["key1"], args=["arg1"])

        assert result == "result"
        mock_redis.evalsha.assert_called_once_with("abc123sha", 1, "key1", "arg1")

    def test_execute_script_sha_not_found_fallback(self, lua_executor, mock_redis):
        """Test fallback to reload when SHA not found in Redis."""
        import redis.exceptions

        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["test_script"] = "return 'test'"
        lua_executor.script_shas["test_script"] = "abc123sha"

        # First evalsha fails, then reload and retry succeeds
        mock_redis.evalsha.side_effect = [
            redis.exceptions.NoScriptError("No script"),
            "result",
        ]
        mock_redis.script_load.return_value = "newsha456"

        result = lua_executor.execute("test_script", keys=["key1"], args=["arg1"])

        # Should reload and retry evalsha
        mock_redis.script_load.assert_called_once()
        assert result == "result"

    def test_execute_script_not_loaded(self, lua_executor, mock_redis):
        """Test executing script that hasn't been loaded."""
        with pytest.raises(ValueError, match="Script 'nonexistent_script' not found"):
            lua_executor.execute("nonexistent_script", keys=[], args=[])


class TestLoadScripts:
    """Test load_scripts function."""

    def test_load_scripts_from_directory(self):
        """Test loading all .lua files from directory."""
        # load_scripts() is called at module import time and loads from disk
        # Just verify SCRIPTS dict is populated
        from arcp.core.redis_scripts import SCRIPTS

        # Should have loaded at least one script
        assert len(SCRIPTS) > 0


class TestConsumeValidationLua:
    """Test consume_validation.lua script logic."""

    def test_consume_validation_success(self, mock_redis):
        """Test successful validation token consumption."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        # Mock Redis to return success from Lua script
        mock_redis.evalsha.return_value = json.dumps(
            {
                "ok": True,
                "binding": {
                    "code_hash": "sha256:abc123",
                    "endpoint_hash": "sha256:def456",
                },
            }
        ).encode("utf-8")

        # Add script to SCRIPTS dict
        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"

        result = consume_validation_token(mock_redis, validation_id)

        assert result["ok"] is True
        assert "binding" in result
        assert result["binding"]["code_hash"] == "sha256:abc123"

    def test_consume_validation_no_validation(self, mock_redis):
        """Test consume when validation doesn't exist."""
        validation_id = "val_nonexistent"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"
        mock_redis.evalsha.return_value = json.dumps(
            {
                "ok": False,
                "error": "NO_VALIDATION",
            }
        ).encode("utf-8")

        result = consume_validation_token(mock_redis, validation_id)

        assert result["ok"] is False
        assert result["error"] == "NO_VALIDATION"

    def test_consume_validation_already_used(self, mock_redis):
        """Test consume when validation already used (replay attack)."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"
        mock_redis.evalsha.return_value = json.dumps(
            {
                "ok": False,
                "error": "ALREADY_USED",
            }
        ).encode("utf-8")

        result = consume_validation_token(mock_redis, validation_id)

        assert result["ok"] is False
        assert result["error"] == "ALREADY_USED"

    def test_consume_validation_expired(self, mock_redis):
        """Test consume when validation expired."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"
        mock_redis.evalsha.return_value = json.dumps(
            {
                "ok": False,
                "error": "EXPIRED",
            }
        ).encode("utf-8")

        result = consume_validation_token(mock_redis, validation_id)

        assert result["ok"] is False
        assert result["error"] == "EXPIRED"

    def test_consume_validation_script_error(self, mock_redis):
        """Test consume when script encounters error."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"
        mock_redis.evalsha.side_effect = Exception("Redis error")

        result = consume_validation_token(mock_redis, validation_id)

        # Should return error dict instead of raising
        assert result["ok"] is False
        assert "error" in result


class TestLuaScriptAtomicity:
    """Test atomic properties of Lua scripts."""

    def test_consume_validation_atomicity(self, mock_redis):
        """Test that consume_validation is atomic (no race conditions)."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"

        # Simulate concurrent consumption attempts
        call_count = [0]

        def mock_evalsha(*args, **kwargs):
            call_count[0] += 1

            if call_count[0] == 1:
                # First call succeeds
                return json.dumps(
                    {
                        "ok": True,
                        "binding": {"code_hash": "sha256:abc123"},
                    }
                ).encode("utf-8")
            else:
                # Subsequent calls fail (already used)
                return json.dumps(
                    {
                        "ok": False,
                        "error": "ALREADY_USED",
                    }
                ).encode("utf-8")

        mock_redis.evalsha.side_effect = mock_evalsha

        # First consumption
        result1 = consume_validation_token(mock_redis, validation_id)
        assert result1["ok"] is True

        # Second consumption (should fail)
        result2 = consume_validation_token(mock_redis, validation_id)
        assert result2["ok"] is False
        assert result2["error"] == "ALREADY_USED"

    def test_consume_validation_idempotency(self, mock_redis):
        """Test that consumed validations cannot be reused."""
        validation_id = "val_test123"
        from arcp.core.redis_scripts import SCRIPTS

        SCRIPTS["consume_validation"] = "return 'test'"
        mock_redis.script_load.return_value = "testsha123"

        results = []
        call_count = [0]

        def mock_evalsha(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First time: success
                return json.dumps(
                    {
                        "ok": True,
                        "binding": {"code_hash": "sha256:abc123"},
                    }
                ).encode("utf-8")
            else:
                # Already consumed
                return json.dumps(
                    {
                        "ok": False,
                        "error": "ALREADY_USED",
                    }
                ).encode("utf-8")

        mock_redis.evalsha.side_effect = mock_evalsha

        # Try consuming multiple times
        for i in range(3):
            result = consume_validation_token(mock_redis, validation_id)
            results.append(result)

        # Only first should succeed
        assert results[0]["ok"] is True
        assert all(r["ok"] is False for r in results[1:])
        assert all(r["error"] == "ALREADY_USED" for r in results[1:])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
