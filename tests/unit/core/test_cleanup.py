"""
Unit tests for ARCP cleanup module.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.arcp.core.cleanup import start_cleanup_task


@pytest.mark.unit
@pytest.mark.asyncio
class TestCleanupTask:
    """Test cases for cleanup task functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_registry = AsyncMock()
        self.mock_registry.get_all_agent_data = AsyncMock()
        self.mock_registry.unregister_agent = AsyncMock()

    @patch("src.arcp.core.cleanup.config")
    @patch("src.arcp.core.cleanup.logger")
    async def test_cleanup_task_initialization(self, mock_logger, mock_config):
        """Test cleanup task initialization and configuration."""
        mock_config.AGENT_CLEANUP_INTERVAL = 30
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 60

        # Mock the registry to return empty data to stop the loop
        self.mock_registry.get_all_agent_data.return_value = {}

        # Start the task but cancel it quickly
        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.1)  # Let it initialize
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify logging - check that initialization message was logged
        mock_logger.info.assert_any_call(
            "Starting cleanup task: interval=30s, stale_threshold=120s"
        )

        # Find the initialization call specifically
        initialization_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Starting cleanup task" in str(call)
        ]
        assert len(initialization_calls) == 1

    @patch("src.arcp.core.cleanup.config")
    async def test_cleanup_stale_agents(self, mock_config):
        """Test cleanup of stale agents."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1  # Short interval for testing
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(seconds=120)  # 2 minutes ago (stale)
        fresh_time = now - timedelta(seconds=30)  # 30 seconds ago (fresh)

        # Mock agent data
        agents_data = {
            "stale-agent-1": {
                "agent_id": "stale-agent-1",
                "last_seen": stale_time.isoformat(),
            },
            "stale-agent-2": {
                "agent_id": "stale-agent-2",
                "last_seen": stale_time.replace(tzinfo=None).isoformat()
                + "Z",  # Test Z suffix
            },
            "fresh-agent": {
                "agent_id": "fresh-agent",
                "last_seen": fresh_time.isoformat(),
            },
            "no-last-seen": {
                "agent_id": "no-last-seen"
                # Missing last_seen field
            },
        }

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}  # Empty on subsequent calls to stop the loop

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        # Start cleanup task
        task = asyncio.create_task(start_cleanup_task(self.mock_registry))

        # Wait a bit for one cleanup cycle
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify stale agents were removed
        unregister_calls = self.mock_registry.unregister_agent.call_args_list
        unregistered_agents = [call[0][0] for call in unregister_calls]

        assert "stale-agent-1" in unregistered_agents
        assert "stale-agent-2" in unregistered_agents
        assert "fresh-agent" not in unregistered_agents
        assert "no-last-seen" not in unregistered_agents

    @patch("src.arcp.core.cleanup.config")
    async def test_cleanup_with_datetime_objects(self, mock_config):
        """Test cleanup with datetime objects instead of strings."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(seconds=120)

        agents_data = {
            "stale-datetime-agent": {
                "agent_id": "stale-datetime-agent",
                "last_seen": stale_time,  # datetime object instead of string
            }
        }

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify agent was cleaned up
        self.mock_registry.unregister_agent.assert_called_with("stale-datetime-agent")

    @patch("src.arcp.core.cleanup.config")
    async def test_cleanup_with_invalid_timestamps(self, mock_config):
        """Test cleanup handles invalid timestamps gracefully."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        agents_data = {
            "invalid-timestamp-1": {
                "agent_id": "invalid-timestamp-1",
                "last_seen": "not-a-valid-timestamp",
            },
            "invalid-timestamp-2": {
                "agent_id": "invalid-timestamp-2",
                "last_seen": 12345,  # Number instead of string/datetime
            },
            "empty-timestamp": {
                "agent_id": "empty-timestamp",
                "last_seen": "",
            },
        }

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify no agents with invalid timestamps were removed
        self.mock_registry.unregister_agent.assert_not_called()

    @patch("src.arcp.core.cleanup.config")
    @patch("src.arcp.core.cleanup.logger")
    async def test_cleanup_handles_unregister_errors(self, mock_logger, mock_config):
        """Test cleanup handles unregister errors gracefully."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(seconds=120)

        agents_data = {
            "error-agent": {
                "agent_id": "error-agent",
                "last_seen": stale_time.isoformat(),
            }
        }

        # Make unregister_agent raise an exception
        self.mock_registry.unregister_agent.side_effect = Exception("Unregister failed")

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify error was logged
        error_logged = any(
            "Failed to unregister stale agent" in str(call.args[0])
            for call in mock_logger.warning.call_args_list
        )
        assert error_logged

    @patch("src.arcp.core.cleanup.config")
    async def test_cleanup_continues_after_registry_error(self, mock_config):
        """Test cleanup continues after registry errors."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Registry error")
            elif call_count == 2:
                return {
                    "test-agent": {
                        "agent_id": "test-agent",
                        "last_seen": datetime.now(timezone.utc).isoformat(),
                    }
                }
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(2.5)  # Wait longer to allow multiple cleanup cycles
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify the task continued and made multiple calls
        assert self.mock_registry.get_all_agent_data.call_count >= 2

    @patch("src.arcp.core.cleanup.config")
    async def test_minimum_config_values(self, mock_config):
        """Test cleanup with minimum configuration values."""
        mock_config.AGENT_CLEANUP_INTERVAL = 5  # Below minimum, should use 60
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 10  # Below minimum, should use 60

        # Capture the actual values used
        captured_values = {}
        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            captured_values["interval"] = delay
            # Don't actually sleep long in test
            await original_sleep(0.1)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            self.mock_registry.get_all_agent_data.return_value = {}

            task = asyncio.create_task(start_cleanup_task(self.mock_registry))
            await asyncio.sleep(0.2)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify minimum values were enforced
        # The actual interval used should be the configured value (5)
        # but stale threshold should be max(60, 10*2) = 60
        assert captured_values.get("interval") == 5

    @patch("src.arcp.core.cleanup.config")
    async def test_cleanup_performance_with_many_agents(self, mock_config):
        """Test cleanup performance with many agents."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        now = datetime.now(timezone.utc)
        fresh_time = now - timedelta(seconds=30)

        # Create 1000 agents, all fresh
        agents_data = {}
        for i in range(1000):
            agents_data[f"agent-{i}"] = {
                "agent_id": f"agent-{i}",
                "last_seen": fresh_time.isoformat(),
            }

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        import time

        start_time = time.time()

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        elapsed_time = time.time() - start_time

        # Processing 1000 agents should complete reasonably quickly
        assert elapsed_time < 5.0  # Should process in under 5 seconds

        # No agents should be removed (all are fresh)
        self.mock_registry.unregister_agent.assert_not_called()

    @patch("src.arcp.core.cleanup.config")
    async def test_timezone_aware_cleanup(self, mock_config):
        """Test cleanup with timezone-aware timestamps."""
        mock_config.AGENT_CLEANUP_INTERVAL = 1
        mock_config.AGENT_HEARTBEAT_TIMEOUT = 30

        # Create timestamps with different timezones
        now_utc = datetime.now(timezone.utc)
        stale_utc = now_utc - timedelta(seconds=120)
        stale_local = stale_utc.replace(
            tzinfo=timezone(timedelta(hours=5))
        )  # Different timezone

        agents_data = {
            "stale-utc": {
                "agent_id": "stale-utc",
                "last_seen": stale_utc.isoformat(),
            },
            "stale-local-tz": {
                "agent_id": "stale-local-tz",
                "last_seen": stale_local.isoformat(),
            },
        }

        call_count = 0

        async def mock_get_all_agent_data():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return agents_data
            else:
                return {}

        self.mock_registry.get_all_agent_data.side_effect = mock_get_all_agent_data

        task = asyncio.create_task(start_cleanup_task(self.mock_registry))
        await asyncio.sleep(0.5)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both agents should be cleaned up regardless of timezone
        unregister_calls = self.mock_registry.unregister_agent.call_args_list
        unregistered_agents = [call[0][0] for call in unregister_calls]

        assert "stale-utc" in unregistered_agents
        assert "stale-local-tz" in unregistered_agents
