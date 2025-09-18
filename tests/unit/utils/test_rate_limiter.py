"""
Unit tests for ARCP rate limiter module.

This test module comprehensively tests the rate limiting functionality,
brute force protection, progressive delays, and anti-bypass features.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.arcp.utils.rate_limiter import (
    AttemptInfo,
    RateLimiter,
    general_rate_limiter,
    get_client_identifier,
    login_rate_limiter,
    pin_rate_limiter,
)


@pytest.mark.unit
class TestAttemptInfo:
    """Test cases for AttemptInfo dataclass."""

    def test_attempt_info_initialization(self):
        """Test AttemptInfo initialization with default values."""
        info = AttemptInfo()

        assert info.count == 0
        assert info.first_attempt == 0
        assert info.last_attempt == 0
        assert info.locked_until is None
        assert info.lockout_count == 0

    def test_attempt_info_initialization_with_values(self):
        """Test AttemptInfo initialization with custom values."""
        current_time = time.time()
        info = AttemptInfo(
            count=5,
            first_attempt=current_time - 100,
            last_attempt=current_time,
            locked_until=current_time + 300,
            lockout_count=2,
        )

        assert info.count == 5
        assert info.first_attempt == current_time - 100
        assert info.last_attempt == current_time
        assert info.locked_until == current_time + 300
        assert info.lockout_count == 2

    def test_attempt_info_to_dict(self):
        """Test AttemptInfo to_dict conversion."""
        current_time = time.time()
        info = AttemptInfo(
            count=3,
            first_attempt=current_time - 50,
            last_attempt=current_time,
            locked_until=current_time + 200,
            lockout_count=1,
        )

        dict_result = info.to_dict()

        assert dict_result["count"] == 3
        assert dict_result["first_attempt"] == current_time - 50
        assert dict_result["last_attempt"] == current_time
        assert dict_result["locked_until"] == current_time + 200
        assert dict_result["lockout_count"] == 1

    def test_attempt_info_to_dict_none_locked_until(self):
        """Test AttemptInfo to_dict with None locked_until."""
        info = AttemptInfo(count=1)
        dict_result = info.to_dict()

        assert dict_result["locked_until"] is None

    def test_attempt_info_from_value_dict(self):
        """Test AttemptInfo from_value with dictionary input."""
        data = {
            "count": 3,
            "first_attempt": 1000.0,
            "last_attempt": 1100.0,
            "locked_until": 1200.0,
            "lockout_count": 1,
        }

        info = AttemptInfo.from_value(data)

        assert info.count == 3
        assert info.first_attempt == 1000.0
        assert info.last_attempt == 1100.0
        assert info.locked_until == 1200.0
        assert info.lockout_count == 1

    def test_attempt_info_from_value_json_string(self):
        """Test AttemptInfo from_value with JSON string input."""
        import json

        data_dict = {
            "count": 2,
            "first_attempt": 900.0,
            "last_attempt": 950.0,
            "locked_until": None,
            "lockout_count": 0,
        }
        json_string = json.dumps(data_dict)

        info = AttemptInfo.from_value(json_string)

        assert info.count == 2
        assert info.first_attempt == 900.0
        assert info.last_attempt == 950.0
        assert info.locked_until is None
        assert info.lockout_count == 0

    def test_attempt_info_from_value_bytes(self):
        """Test AttemptInfo from_value with bytes input."""
        import json

        data_dict = {
            "count": 1,
            "first_attempt": 800.0,
            "last_attempt": 850.0,
            "locked_until": None,
            "lockout_count": 0,
        }
        json_bytes = json.dumps(data_dict).encode("utf-8")

        info = AttemptInfo.from_value(json_bytes)

        assert info.count == 1
        assert info.first_attempt == 800.0
        assert info.last_attempt == 850.0

    def test_attempt_info_from_value_none(self):
        """Test AttemptInfo from_value with None input."""
        info = AttemptInfo.from_value(None)
        assert info is None

    def test_attempt_info_from_value_invalid(self):
        """Test AttemptInfo from_value with invalid input."""
        # These should return None
        none_inputs = [
            "invalid json",
            123,
            [],
        ]

        for invalid_input in none_inputs:
            info = AttemptInfo.from_value(invalid_input)
            assert info is None

        # Partial data should create object with defaults
        partial_data = {"invalid": "data"}  # Missing required fields
        info = AttemptInfo.from_value(partial_data)
        assert info is not None
        assert info.count == 0
        assert info.first_attempt == 0.0


@pytest.mark.unit
class TestRateLimiter:
    """Test cases for RateLimiter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(
            max_attempts=3,
            lockout_duration=60,
            window_duration=300,
            progressive_delay=True,
            max_lockout_duration=600,
            cleanup_interval=30,
        )

    def test_rate_limiter_initialization(self):
        """Test RateLimiter initialization."""
        assert self.limiter.max_attempts == 3
        assert self.limiter.lockout_duration == 60
        assert self.limiter.window_duration == 300
        assert self.limiter.progressive_delay is True
        assert self.limiter.max_lockout_duration == 600
        assert self.limiter.cleanup_interval == 30

    def test_bucket_for_type(self):
        """Test bucket selection for different attempt types."""
        assert "login" in self.limiter._bucket_for_type("login")
        assert "pin" in self.limiter._bucket_for_type("pin")
        assert "global" in self.limiter._bucket_for_type("other")
        assert "global" in self.limiter._bucket_for_type("unknown")

    def test_calculate_delay(self):
        """Test delay calculation."""
        # No progressive delay
        no_progress = RateLimiter(progressive_delay=False)
        assert no_progress.calculate_delay(5) == 1.0

        # With progressive delay
        assert self.limiter.calculate_delay(1) == 1  # 2^0
        assert self.limiter.calculate_delay(2) == 2  # 2^1
        assert self.limiter.calculate_delay(3) == 4  # 2^2
        assert self.limiter.calculate_delay(4) == 8  # 2^3

        # With repeat penalty
        delay_with_penalty = self.limiter.calculate_delay(2, lockout_count=1)
        assert delay_with_penalty == 2 + 30  # base delay + penalty

        # Max delay cap
        large_delay = self.limiter.calculate_delay(10, lockout_count=5)
        assert large_delay == 210  # base_delay(60) + repeat_penalty(150) = 210

    def test_calculate_lockout_duration(self):
        """Test lockout duration calculation."""
        assert self.limiter.calculate_lockout_duration(1) == 60  # base duration
        assert self.limiter.calculate_lockout_duration(2) == 120  # 60 * 2
        assert self.limiter.calculate_lockout_duration(3) == 240  # 60 * 4

        # Max lockout cap
        long_lockout = self.limiter.calculate_lockout_duration(10)
        assert long_lockout == 600  # Maximum lockout


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiterAsyncMethods:
    """Test cases for RateLimiter async methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(max_attempts=3, lockout_duration=60)

    @patch("src.arcp.utils.rate_limiter._get_storage")
    async def test_load_nonexistent_attempt_info(self, mock_get_storage):
        """Test loading non-existent attempt info."""
        mock_storage = AsyncMock()
        mock_storage.hget.return_value = None
        mock_get_storage.return_value = mock_storage

        info = await self.limiter._load("login", "user123")

        assert info is None
        mock_storage.hget.assert_called_once()

    @patch("src.arcp.utils.rate_limiter._get_storage")
    async def test_load_existing_attempt_info(self, mock_get_storage):
        """Test loading existing attempt info."""
        import json

        mock_storage = AsyncMock()
        attempt_data = {
            "count": 2,
            "first_attempt": 1000.0,
            "last_attempt": 1050.0,
            "locked_until": None,
            "lockout_count": 0,
        }
        mock_storage.hget.return_value = json.dumps(attempt_data)
        mock_get_storage.return_value = mock_storage

        info = await self.limiter._load("login", "user123")

        assert info.count == 2
        assert info.first_attempt == 1000.0
        assert info.last_attempt == 1050.0

    @patch("src.arcp.utils.rate_limiter._get_storage")
    async def test_save_attempt_info(self, mock_get_storage):
        """Test saving attempt info."""
        mock_storage = AsyncMock()
        mock_get_storage.return_value = mock_storage

        info = AttemptInfo(count=3, first_attempt=1000.0, last_attempt=1100.0)

        await self.limiter._save("login", "user123", info)

        mock_storage.hset.assert_called_once()
        call_args = mock_storage.hset.call_args[0]
        assert "login" in call_args[0]  # bucket name
        assert call_args[1] == "user123"  # identifier
        # JSON string should contain the data
        import json

        saved_data = json.loads(call_args[2])
        assert saved_data["count"] == 3

    @patch("src.arcp.utils.rate_limiter._get_storage")
    async def test_delete_attempt_info(self, mock_get_storage):
        """Test deleting attempt info."""
        mock_storage = AsyncMock()
        mock_get_storage.return_value = mock_storage

        await self.limiter._delete("login", "user123")

        mock_storage.hdel.assert_called_once()
        call_args = mock_storage.hdel.call_args[0]
        assert "login" in call_args[0]  # bucket name
        assert call_args[1] == "user123"  # identifier

    @patch("src.arcp.utils.rate_limiter._get_storage")
    async def test_hkeys(self, mock_get_storage):
        """Test getting keys from storage."""
        mock_storage = AsyncMock()
        mock_storage.hkeys.return_value = ["user1", "user2", "user3"]
        mock_get_storage.return_value = mock_storage

        keys = await self.limiter._hkeys("login")

        assert keys == ["user1", "user2", "user3"]
        mock_storage.hkeys.assert_called_once()

    @patch("time.time")
    async def test_check_rate_limit_no_previous_attempts(self, mock_time):
        """Test rate limit check with no previous attempts."""
        mock_time.return_value = 1000.0

        with patch.object(self.limiter, "_load", return_value=None):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "user123", "login"
            )

            assert allowed is True
            assert delay is None
            assert reason is None

    @patch("time.time")
    async def test_check_rate_limit_under_limit(self, mock_time):
        """Test rate limit check under the limit."""
        mock_time.return_value = 1000.0

        # Simulate 2 previous attempts (under limit of 3)
        mock_info = AttemptInfo(count=2, last_attempt=950.0, lockout_count=0)

        with patch.object(self.limiter, "_load", return_value=mock_info):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "user123", "login"
            )

            assert allowed is True
            assert delay is None
            assert reason is None

    @patch("time.time")
    async def test_check_rate_limit_progressive_delay_needed(self, mock_time):
        """Test rate limit check when progressive delay is needed."""
        mock_time.return_value = 1000.0

        # Simulate 2 attempts with recent last attempt (needs delay)
        mock_info = AttemptInfo(
            count=2, last_attempt=999.0, lockout_count=0
        )  # 1 second ago

        with patch.object(self.limiter, "_load", return_value=mock_info):
            with patch.object(self.limiter, "_save"):
                allowed, delay, reason = await self.limiter.check_rate_limit(
                    "user123", "login"
                )

                assert allowed is False
                assert delay is not None
                assert delay > 0
                assert "Too many" in reason

    @patch("time.time")
    async def test_check_rate_limit_locked_out(self, mock_time):
        """Test rate limit check when user is locked out."""
        mock_time.return_value = 1000.0

        # Simulate locked out user
        mock_info = AttemptInfo(
            count=0,  # Reset after lockout
            locked_until=1100.0,  # Locked until future time
            lockout_count=1,
        )

        with patch.object(self.limiter, "_load", return_value=mock_info):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "user123", "login"
            )

            assert allowed is False
            assert delay == 100.0  # 1100 - 1000
            assert "locked out" in reason

    @patch("time.time")
    async def test_check_rate_limit_lockout_expired(self, mock_time):
        """Test rate limit check when lockout has expired."""
        mock_time.return_value = 1000.0

        # Simulate expired lockout
        mock_info = AttemptInfo(
            count=0,
            locked_until=900.0,
            lockout_count=1,  # Locked until past time
        )

        with patch.object(self.limiter, "_load", return_value=mock_info):
            with patch.object(self.limiter, "_save") as mock_save:
                allowed, delay, reason = await self.limiter.check_rate_limit(
                    "user123", "login"
                )

                assert allowed is True
                assert delay is None
                assert reason is None
                # Should clear the lockout
                mock_save.assert_called_once()

    @patch("time.time")
    async def test_record_attempt_successful(self, mock_time):
        """Test recording a successful attempt."""
        mock_time.return_value = 1000.0

        mock_info = AttemptInfo(count=2, lockout_count=0)

        with patch.object(self.limiter, "_load", return_value=mock_info):
            with patch.object(self.limiter, "_save") as mock_save:
                lockout = await self.limiter.record_attempt("user123", True, "login")

                assert lockout is None
                # Should reset counters on success
                mock_save.assert_called_once()
                saved_info = mock_save.call_args[0][2]
                assert saved_info.count == 0
                assert saved_info.first_attempt == 0

    @patch("time.time")
    async def test_record_attempt_failed_under_limit(self, mock_time):
        """Test recording a failed attempt under the limit."""
        mock_time.return_value = 1000.0

        mock_info = AttemptInfo(count=1, first_attempt=950.0)

        with patch.object(self.limiter, "_load", return_value=mock_info):
            with patch.object(self.limiter, "_save") as mock_save:
                lockout = await self.limiter.record_attempt("user123", False, "login")

                assert lockout is None
                # Should increment counter
                mock_save.assert_called_once()
                saved_info = mock_save.call_args[0][2]
                assert saved_info.count == 2

    @patch("time.time")
    async def test_record_attempt_failed_triggers_lockout(self, mock_time):
        """Test recording a failed attempt that triggers lockout."""
        mock_time.return_value = 1000.0

        mock_info = AttemptInfo(count=2, first_attempt=950.0)  # At limit - 1

        with patch.object(self.limiter, "_load", return_value=mock_info):
            with patch.object(self.limiter, "_save") as mock_save:
                lockout = await self.limiter.record_attempt("user123", False, "login")

                assert lockout is not None
                assert lockout == 60  # lockout duration

                # Should set lockout and reset count
                mock_save.assert_called_once()
                saved_info = mock_save.call_args[0][2]
                assert saved_info.count == 0  # Reset after lockout
                assert saved_info.lockout_count == 1
                assert saved_info.locked_until == 1060.0  # 1000 + 60

    @patch("time.time")
    async def test_record_attempt_first_failure(self, mock_time):
        """Test recording the first failed attempt."""
        mock_time.return_value = 1000.0

        with patch.object(self.limiter, "_load", return_value=None):
            with patch.object(self.limiter, "_save") as mock_save:
                lockout = await self.limiter.record_attempt("user123", False, "login")

                assert lockout is None

                # Should create new attempt info
                mock_save.assert_called_once()
                saved_info = mock_save.call_args[0][2]
                assert saved_info.count == 1
                assert saved_info.first_attempt == 1000.0
                assert saved_info.last_attempt == 1000.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiterMultipleIdentifiers:
    """Test cases for rate limiter with multiple identifiers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(max_attempts=3, lockout_duration=60)

    @patch("time.time")
    async def test_check_rate_limit_multiple_identifiers(self, mock_time):
        """Test rate limiting with multiple identifiers (pipe-separated)."""
        mock_time.return_value = 1000.0

        # Mock one identifier as blocked
        # Note: mock_info_blocked and mock_info_clean are intentionally unused
        # as they represent test setup that would be used in more complex scenarios

        async def mock_check_single(identifier, attempt_type):
            if identifier == "blocked_id":
                return False, 100.0, "locked out"
            else:
                return True, None, None

        with patch.object(
            self.limiter,
            "_check_single_identifier",
            side_effect=mock_check_single,
        ):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "clean_id|blocked_id", "login"
            )

            assert allowed is False
            assert delay == 100.0
            assert "locked out" in reason

    @patch("time.time")
    async def test_record_attempt_multiple_identifiers(self, mock_time):
        """Test recording attempts with multiple identifiers."""
        mock_time.return_value = 1000.0

        async def mock_record_single(identifier, success, attempt_type):
            if identifier == "user1":
                return 60.0  # Lockout for user1
            else:
                return None  # No lockout for user2

        with patch.object(
            self.limiter,
            "_record_single_attempt",
            side_effect=mock_record_single,
        ):
            lockout = await self.limiter.record_attempt("user1|user2", False, "login")

            assert lockout == 60.0  # Should return the maximum lockout


@pytest.mark.unit
class TestRateLimiterSyncMethods:
    """Test cases for synchronous RateLimiter methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(max_attempts=3)

    @patch("asyncio.get_event_loop")
    def test_is_locked_out_with_running_loop(self, mock_get_loop):
        """Test is_locked_out when event loop is running."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_get_loop.return_value = mock_loop

        result = self.limiter.is_locked_out("user123")

        # Should return False conservatively when loop is running
        assert result is False

    @patch("asyncio.get_event_loop")
    async def test_is_locked_out_not_running_loop(self, mock_get_loop):
        """Test is_locked_out when event loop is not running."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_loop.run_until_complete.return_value = (
            False,
            100.0,
            "locked out",
        )
        mock_get_loop.return_value = mock_loop

        result = self.limiter.is_locked_out("user123")

        assert result is True

    @patch("asyncio.get_event_loop")
    def test_get_attempt_count(self, mock_get_loop):
        """Test get_attempt_count method."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False

        # Mock storage operations
        with patch.object(self.limiter, "_bucket_for_type", return_value="test_bucket"):
            with patch("src.arcp.utils.rate_limiter._get_storage") as mock_get_storage:
                mock_storage = MagicMock()
                mock_storage.hget = MagicMock()
                mock_get_storage.return_value = mock_storage

                # Mock successful data retrieval
                import json

                attempt_data = {
                    "count": 5,
                    "first_attempt": 1000.0,
                    "last_attempt": 1100.0,
                    "locked_until": None,
                    "lockout_count": 0,
                }
                mock_loop.run_until_complete.return_value = json.dumps(attempt_data)
                mock_get_loop.return_value = mock_loop

                count = self.limiter.get_attempt_count("user123", "login")

                assert count == 5

    @patch("asyncio.get_event_loop")
    def test_get_attempt_info(self, mock_get_loop):
        """Test get_attempt_info method."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False

        with patch.object(self.limiter, "_bucket_for_type", return_value="test_bucket"):
            with patch("src.arcp.utils.rate_limiter._get_storage") as mock_get_storage:
                mock_storage = MagicMock()
                mock_get_storage.return_value = mock_storage

                # Mock successful data retrieval
                import json

                attempt_data = {
                    "count": 3,
                    "first_attempt": 1000.0,
                    "last_attempt": 1100.0,
                    "locked_until": 1200.0,
                    "lockout_count": 1,
                }
                mock_loop.run_until_complete.return_value = json.dumps(attempt_data)
                mock_get_loop.return_value = mock_loop

                info = self.limiter.get_attempt_info("user123", "login")

                assert info.count == 3
                assert info.locked_until == 1200.0

    @patch("time.time")
    @patch("asyncio.get_event_loop")
    def test_get_lockout_info(self, mock_get_loop, mock_time):
        """Test get_lockout_info method."""
        mock_time.return_value = 1000.0
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False

        with patch.object(self.limiter, "_bucket_for_type", return_value="test_bucket"):
            with patch("src.arcp.utils.rate_limiter._get_storage") as mock_get_storage:
                mock_storage = MagicMock()
                mock_get_storage.return_value = mock_storage

                # Mock locked out user
                import json

                attempt_data = {
                    "count": 0,
                    "first_attempt": 900.0,
                    "last_attempt": 950.0,
                    "locked_until": 1100.0,
                    "lockout_count": 2,
                }
                mock_loop.run_until_complete.return_value = json.dumps(attempt_data)
                mock_get_loop.return_value = mock_loop

                remaining_time, lockout_count = self.limiter.get_lockout_info(
                    "user123", "login"
                )

                assert remaining_time == 100.0  # 1100 - 1000
                assert lockout_count == 2

    @patch("asyncio.get_event_loop")
    def test_clear_attempts_single_type(self, mock_get_loop):
        """Test clearing attempts for a single attempt type."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_get_loop.return_value = mock_loop

        with patch("src.arcp.utils.rate_limiter._get_storage") as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage

            self.limiter.clear_attempts("user123", "login")

            # Should call hdel once for the specific type
            assert mock_loop.run_until_complete.call_count == 1

    @patch("asyncio.get_event_loop")
    def test_clear_attempts_all_types(self, mock_get_loop):
        """Test clearing attempts for all attempt types."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_get_loop.return_value = mock_loop

        with patch("src.arcp.utils.rate_limiter._get_storage") as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage

            self.limiter.clear_attempts("user123", None)

            # Should call hdel for each attempt type (login, pin, global)
            assert mock_loop.run_until_complete.call_count == 3


@pytest.mark.unit
class TestGetClientIdentifier:
    """Test cases for get_client_identifier function."""

    def test_get_client_identifier_full_request(self):
        """Test client identifier generation with full request info."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-encoding": "gzip, deflate",
            "accept-language": "en-US,en;q=0.5",
        }
        mock_request.method = "POST"
        mock_request.url.path = "/api/login"

        identifier = get_client_identifier(mock_request)

        assert "ip-192.168.1.100" in identifier
        assert "|" in identifier  # Should contain multiple identifiers
        parts = identifier.split("|")
        assert len(parts) == 4  # ip, ua-combo, browser-fp, full-fp

    def test_get_client_identifier_minimal_request(self):
        """Test client identifier generation with minimal request info."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}
        mock_request.method = "GET"
        mock_request.url.path = "/health"

        identifier = get_client_identifier(mock_request)

        assert "ip-127.0.0.1" in identifier
        assert "|" in identifier

    def test_get_client_identifier_no_client(self):
        """Test client identifier generation when no client info available."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client = None
        mock_request.headers = {"user-agent": "TestBot/1.0"}
        mock_request.method = "POST"
        mock_request.url.path = "/api/test"

        identifier = get_client_identifier(mock_request)

        assert "ip-unknown" in identifier

    def test_get_client_identifier_long_user_agent(self):
        """Test client identifier with very long user agent."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "10.0.0.1"
        long_ua = "A" * 500  # Very long user agent
        mock_request.headers = {"user-agent": long_ua}
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        identifier = get_client_identifier(mock_request)

        # Should handle long user agents gracefully
        assert "ip-10.0.0.1" in identifier
        assert len(identifier) < 1000  # Should not be excessively long

    def test_get_client_identifier_special_characters(self):
        """Test client identifier with special characters in headers."""
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {
            "user-agent": "Mozilla/5.0 <script>alert('xss')</script>",
            "accept": "text/html; charset=UTF-8",
        }
        mock_request.method = "POST"
        mock_request.url.path = "/api/endpoint"

        identifier = get_client_identifier(mock_request)

        # Should generate identifier without errors
        assert "ip-192.168.1.1" in identifier
        assert isinstance(identifier, str)

    def test_get_client_identifier_exception_handling(self):
        """Test client identifier generation handles exceptions gracefully."""
        # Test with invalid request object
        invalid_request = "not a request"

        identifier = get_client_identifier(invalid_request)

        assert identifier == "unknown"

    def test_get_client_identifier_none_request(self):
        """Test client identifier generation with None request."""
        identifier = get_client_identifier(None)

        assert identifier == "unknown"


@pytest.mark.unit
class TestGlobalRateLimiters:
    """Test cases for global rate limiter instances."""

    def test_login_rate_limiter_configuration(self):
        """Test login rate limiter is properly configured."""
        assert isinstance(login_rate_limiter, RateLimiter)
        assert login_rate_limiter.progressive_delay is True
        assert login_rate_limiter.lockout_duration == 300

    def test_pin_rate_limiter_configuration(self):
        """Test PIN rate limiter is properly configured."""
        assert isinstance(pin_rate_limiter, RateLimiter)
        assert pin_rate_limiter.progressive_delay is True
        assert pin_rate_limiter.lockout_duration == 600
        # PIN limiter should be more restrictive
        assert pin_rate_limiter.max_attempts <= login_rate_limiter.max_attempts

    def test_general_rate_limiter_configuration(self):
        """Test general rate limiter is properly configured."""
        assert isinstance(general_rate_limiter, RateLimiter)
        assert general_rate_limiter.progressive_delay is True
        assert general_rate_limiter.lockout_duration == 60  # Shorter lockout


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiterCleanup:
    """Test cases for rate limiter cleanup functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(cleanup_interval=10)

    @patch("time.time")
    @patch("asyncio.create_task")
    def test_cleanup_triggered(self, mock_create_task, mock_time):
        """Test that cleanup is triggered after interval."""
        mock_time.return_value = 1000.0
        self.limiter.last_cleanup = 900.0  # 100 seconds ago

        self.limiter._perform_cleanup()

        # Should trigger cleanup
        mock_create_task.assert_called_once()
        assert self.limiter.last_cleanup == 1000.0

    @patch("time.time")
    @patch("asyncio.create_task")
    def test_cleanup_not_triggered(self, mock_create_task, mock_time):
        """Test that cleanup is not triggered before interval."""
        mock_time.return_value = 1000.0
        self.limiter.last_cleanup = 995.0  # 5 seconds ago (less than interval)

        self.limiter._perform_cleanup()

        # Should not trigger cleanup
        mock_create_task.assert_not_called()
        assert self.limiter.last_cleanup == 995.0

    @patch("time.time")
    async def test_async_cleanup_removes_old_entries(self, mock_time):
        """Test async cleanup removes old entries."""
        mock_time.return_value = 2000.0

        # Mock old attempt info
        old_info = AttemptInfo(
            count=1,
            last_attempt=1000.0,  # 1000 seconds old (beyond window)
            locked_until=None,
        )

        with patch.object(
            self.limiter, "_hkeys", return_value=["old_user", "recent_user"]
        ):
            with patch.object(self.limiter, "_load") as mock_load:
                with patch.object(self.limiter, "_delete") as mock_delete:

                    # Mock load to return old data for old_user, None for recent_user
                    async def mock_load_func(attempt_type, key):
                        if key == "old_user":
                            return old_info
                        return None

                    mock_load.side_effect = mock_load_func

                    await self.limiter._async_cleanup()

                    # Should delete the old user
                    mock_delete.assert_called()

    @patch("time.time")
    async def test_async_cleanup_preserves_locked_users(self, mock_time):
        """Test async cleanup preserves locked out users."""
        mock_time.return_value = 2000.0

        # Mock locked user with old last_attempt but active lockout
        locked_info = AttemptInfo(
            count=0,
            last_attempt=1000.0,  # Old last attempt
            locked_until=2100.0,  # Still locked out
        )

        with patch.object(self.limiter, "_hkeys", return_value=["locked_user"]):
            with patch.object(self.limiter, "_load", return_value=locked_info):
                with patch.object(self.limiter, "_delete") as mock_delete:

                    await self.limiter._async_cleanup()

                    # Should not delete locked user
                    mock_delete.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrencyAndEdgeCases:
    """Test cases for concurrency scenarios and edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter(max_attempts=5, lockout_duration=30)

    async def test_concurrent_rate_limit_checks(self):
        """Test concurrent rate limit checks for same user."""
        # Mock storage operations
        with patch.object(self.limiter, "_load", return_value=None):

            # Execute multiple concurrent checks
            tasks = [
                self.limiter.check_rate_limit("user123", "login") for _ in range(10)
            ]
            results = await asyncio.gather(*tasks)

            # All should be allowed for first-time user
            for allowed, delay, reason in results:
                assert allowed is True
                assert delay is None

    async def test_concurrent_attempt_recording(self):
        """Test concurrent attempt recording."""
        attempt_count = 0

        async def mock_load(attempt_type, identifier):
            if attempt_count == 0:
                return None  # First load
            else:
                return AttemptInfo(
                    count=attempt_count,
                    first_attempt=1000.0,
                    last_attempt=1000.0,
                )

        async def mock_save(attempt_type, identifier, info):
            nonlocal attempt_count
            attempt_count = info.count

        with patch.object(self.limiter, "_load", side_effect=mock_load):
            with patch.object(self.limiter, "_save", side_effect=mock_save):

                # Record multiple concurrent failed attempts
                tasks = [
                    self.limiter.record_attempt("user123", False, "login")
                    for _ in range(3)
                ]
                results = await asyncio.gather(*tasks)

                # Should handle concurrent updates
                assert all(
                    result is None or isinstance(result, (int, float))
                    for result in results
                )

    @patch("time.time")
    async def test_edge_case_zero_delay_calculation(self, mock_time):
        """Test edge case where delay calculation might return zero."""
        mock_time.return_value = 1000.0

        # Test with attempt at exactly the delay boundary
        mock_info = AttemptInfo(
            count=1, last_attempt=998.0
        )  # 2 seconds ago, exactly at delay

        with patch.object(self.limiter, "_load", return_value=mock_info):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "user123", "login"
            )

            # Should be allowed when delay time has passed
            assert allowed is True or (
                allowed is False and delay is not None and delay >= 0
            )

    async def test_edge_case_empty_identifier(self):
        """Test edge case with empty identifier."""
        allowed, delay, reason = await self.limiter.check_rate_limit("", "login")

        # Should handle empty identifier gracefully
        assert isinstance(allowed, bool)

    async def test_edge_case_whitespace_identifier(self):
        """Test edge case with whitespace-only identifier."""
        allowed, delay, reason = await self.limiter.check_rate_limit("   ", "login")

        # Should handle whitespace identifier gracefully
        assert isinstance(allowed, bool)

    async def test_edge_case_very_long_identifier(self):
        """Test edge case with very long identifier."""
        long_identifier = "A" * 1000
        allowed, delay, reason = await self.limiter.check_rate_limit(
            long_identifier, "login"
        )

        # Should handle long identifiers gracefully
        assert isinstance(allowed, bool)

    @patch("time.time")
    async def test_edge_case_time_going_backwards(self, mock_time):
        """Test edge case where system time might go backwards."""
        # Start with a future time, then go backwards
        mock_time.return_value = 2000.0

        mock_info = AttemptInfo(count=1, last_attempt=2100.0)  # Future timestamp

        with patch.object(self.limiter, "_load", return_value=mock_info):
            allowed, delay, reason = await self.limiter.check_rate_limit(
                "user123", "login"
            )

            # Should handle gracefully without crashing
            assert isinstance(allowed, bool)
            if not allowed and delay is not None:
                assert delay >= 0  # Delay should not be negative
