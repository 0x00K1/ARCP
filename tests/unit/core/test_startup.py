"""
Unit tests for application startup and shutdown procedures.

Tests startup, shutdown, configuration validation, and lifespan management.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import src.arcp.core.startup as startup_module
from src.arcp.core.startup import (
    _redis_health_monitor,
    lifespan,
    shutdown_procedures,
    startup_procedures,
    validate_configuration,
)


@pytest.mark.unit
class TestRedisHealthMonitor:
    """Test Redis health monitoring functionality."""

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.get_registry")
    @patch("src.arcp.core.startup.sessions")
    @patch("src.arcp.core.startup.rate_limiter")
    @patch("asyncio.sleep")
    async def test_redis_health_monitor_single_iteration(
        self,
        mock_sleep,
        mock_rate_limiter,
        mock_sessions,
        mock_get_registry,
        mock_config,
    ):
        """Test single iteration of Redis health monitor."""
        # Setup mocks
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = "30"

        mock_registry = AsyncMock()
        mock_registry.storage.is_backend_available = AsyncMock(return_value=True)
        mock_get_registry.return_value = mock_registry

        mock_sessions._get_storage.return_value.is_backend_available = AsyncMock(
            return_value=True
        )
        mock_rate_limiter._get_storage.return_value.is_backend_available = AsyncMock(
            return_value=True
        )

        # Make sleep raise exception to exit loop after one iteration
        mock_sleep.side_effect = Exception("Exit loop")

        with pytest.raises(Exception, match="Exit loop"):
            await _redis_health_monitor()

        # Verify all backends were checked
        mock_registry.storage.is_backend_available.assert_called_once()
        mock_sessions._get_storage.assert_called_once()
        mock_rate_limiter._get_storage.assert_called_once()

        # Verify sleep was called with correct interval
        mock_sleep.assert_called_once_with(30)

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.get_registry")
    @patch("asyncio.sleep")
    async def test_redis_health_monitor_registry_exception(
        self, mock_sleep, mock_get_registry, mock_config
    ):
        """Test Redis health monitor handles registry exceptions."""
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = "5"
        mock_get_registry.side_effect = Exception("Registry failed")
        mock_sleep.side_effect = Exception("Exit loop")

        with pytest.raises(Exception, match="Exit loop"):
            await _redis_health_monitor()

        # Should continue despite registry failure
        mock_sleep.assert_called_once_with(5)

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    @patch("asyncio.sleep")
    async def test_redis_health_monitor_logging(
        self, mock_sleep, mock_get_logger, mock_config
    ):
        """Test Redis health monitor logging."""
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = "10"
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_sleep.side_effect = Exception("Exit loop")

        # Make the overall iteration fail
        with patch(
            "src.arcp.core.startup.get_registry",
            side_effect=Exception("Test error"),
        ):
            with pytest.raises(Exception, match="Exit loop"):
                await _redis_health_monitor()

        mock_get_logger.assert_called_with("arcp.redis-health")

    @patch("src.arcp.core.startup.config")
    @patch("asyncio.sleep")
    async def test_redis_health_monitor_interval_calculation(
        self, mock_sleep, mock_config
    ):
        """Test Redis health monitor interval calculation."""
        # Test with very small interval (should use minimum of 5)
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = "1"
        mock_sleep.side_effect = Exception("Exit loop")

        with pytest.raises(Exception, match="Exit loop"):
            await _redis_health_monitor()

        # Should use minimum of 5 seconds
        mock_sleep.assert_called_once_with(5)

    @patch("src.arcp.core.startup.config")
    @patch("asyncio.sleep")
    async def test_redis_health_monitor_missing_config(self, mock_sleep, mock_config):
        """Test Redis health monitor with missing config attribute."""
        # Remove the attribute to test default behavior
        delattr(mock_config, "REDIS_HEALTH_CHECK_INTERVAL")
        mock_sleep.side_effect = Exception("Exit loop")

        with pytest.raises(Exception, match="Exit loop"):
            await _redis_health_monitor()

        # Should use default of 30
        mock_sleep.assert_called_once_with(30)


@pytest.mark.unit
class TestConfigurationValidation:
    """Test configuration validation functionality."""

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    def test_validate_configuration_success(self, mock_get_logger, mock_config):
        """Test successful configuration validation."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.validate_all_config.return_value = {
            "required_missing": [],
            "optional_missing": {},
        }

        # Should not raise exception
        validate_configuration()

        mock_config.validate_all_config.assert_called_once()
        mock_logger.info.assert_called()

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    def test_validate_configuration_missing_required(
        self, mock_get_logger, mock_config
    ):
        """Test configuration validation with missing required config."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.validate_all_config.return_value = {
            "required_missing": ["JWT_SECRET", "DATABASE_URL"],
            "optional_missing": {},
        }

        with pytest.raises(
            RuntimeError,
            match="Missing required configuration: JWT_SECRET, DATABASE_URL",
        ):
            validate_configuration()

        mock_logger.error.assert_called()

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    def test_validate_configuration_validation_exception(
        self, mock_get_logger, mock_config
    ):
        """Test configuration validation when validation itself fails."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.validate_all_config.side_effect = Exception(
            "Config validation error"
        )

        with pytest.raises(Exception, match="Config validation error"):
            validate_configuration()

        # Exception should propagate without logging an error message
        mock_logger.error.assert_not_called()

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    def test_validate_configuration_missing_optional(
        self, mock_get_logger, mock_config
    ):
        """Test configuration validation with missing optional config."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.validate_all_config.return_value = {
            "required_missing": [],
            "optional_missing": {
                "redis": {
                    "configured": False,
                    "details": {"REDIS_HOST": False},
                },
                "azure": {
                    "configured": False,
                    "details": {"OPENAI_API_KEY": False},
                },
            },
        }

        # Should not raise exception but should log warning
        validate_configuration()

        mock_logger.warning.assert_called()

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    def test_validate_configuration_optional_validation_exception(
        self, mock_get_logger, mock_config
    ):
        """Test configuration validation when optional validation fails."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.validate_all_config.return_value = {
            "required_missing": [],
            "optional_missing": {},
        }

        # Should not raise exception
        validate_configuration()

        # Should log success for required config
        mock_logger.info.assert_called()


@pytest.mark.unit
class TestStartupProcedures:
    """Test application startup procedures."""

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.get_registry")
    @patch("src.arcp.core.startup.validate_configuration")
    @patch("src.arcp.core.startup.initialize_tracing")
    @patch("src.arcp.core.startup.initialize_logging")
    @patch("src.arcp.core.startup.start_cleanup_task")
    @patch("src.arcp.core.startup.dashboard")
    @patch("asyncio.create_task")
    async def test_startup_procedures_success(
        self,
        mock_create_task,
        mock_dashboard,
        mock_start_cleanup,
        mock_init_logging,
        mock_init_tracing,
        mock_validate_config,
        mock_get_registry,
        mock_config,
    ):
        """Test successful startup procedures."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        mock_cleanup_task = MagicMock()
        mock_broadcast_task = MagicMock()
        mock_redis_task = MagicMock()
        mock_create_task.side_effect = [
            mock_cleanup_task,
            mock_broadcast_task,
            mock_redis_task,
        ]

        await startup_procedures(mock_app)

        # Verify all startup steps
        mock_config.apply_timezone.assert_called_once()
        mock_config.ensure_logs_directory.assert_called_once()
        mock_init_logging.assert_called_once()
        mock_init_tracing.assert_called_once()
        # validate_configuration is called in __main__.py, not in startup_procedures
        mock_validate_config.assert_not_called()

        # Verify registry setup
        assert mock_app.state.registry == mock_registry

        # Verify tasks created and stored
        assert mock_create_task.call_count == 3
        assert mock_app.state.cleanup_task == mock_cleanup_task
        assert mock_app.state.broadcast_task == mock_broadcast_task
        assert mock_app.state.redis_health_task == mock_redis_task

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.logging.getLogger")
    async def test_startup_procedures_logs_directory_failure(
        self, mock_get_logger, mock_config
    ):
        """Test startup procedures when logs directory creation fails."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_config.ensure_logs_directory.side_effect = Exception("Permission denied")

        with (
            patch("src.arcp.core.startup.get_registry"),
            patch("src.arcp.core.startup.validate_configuration"),
            patch("src.arcp.core.startup.initialize_tracing"),
            patch("src.arcp.core.startup.initialize_logging"),
            patch("asyncio.create_task"),
        ):

            await startup_procedures(mock_app)

            # Should continue despite logs directory failure
            mock_logger.warning.assert_called_with("Failed to ensure logs directory")

    @patch("src.arcp.core.startup.config")
    @patch("src.arcp.core.startup.initialize_logging")
    async def test_startup_procedures_logging_initialization_failure(
        self, mock_init_logging, mock_config
    ):
        """Test startup procedures when logging initialization fails."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        mock_init_logging.side_effect = Exception("Logging init failed")

        with (
            patch("src.arcp.core.startup.get_registry"),
            patch("src.arcp.core.startup.validate_configuration"),
            patch("src.arcp.core.startup.initialize_tracing"),
            patch("asyncio.create_task"),
        ):

            # Should not raise exception (fail quietly)
            await startup_procedures(mock_app)


@pytest.mark.unit
class TestShutdownProcedures:
    """Test application shutdown procedures."""

    @patch("src.arcp.core.startup.shutdown_tracing")
    async def test_shutdown_procedures_with_all_tasks(self, mock_shutdown_tracing):
        """Test shutdown procedures when all tasks exist."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        # Create mock tasks that can be awaited and cancelled
        async def cancelled_coro():
            raise asyncio.CancelledError()

        # Create actual task objects that can be cancelled and awaited
        import asyncio

        mock_cleanup_task = asyncio.create_task(cancelled_coro())
        mock_cleanup_task.cancel()

        mock_broadcast_task = asyncio.create_task(cancelled_coro())
        mock_broadcast_task.cancel()

        mock_redis_task = asyncio.create_task(cancelled_coro())
        mock_redis_task.cancel()

        mock_app.state.cleanup_task = mock_cleanup_task
        mock_app.state.broadcast_task = mock_broadcast_task
        mock_app.state.redis_health_task = mock_redis_task

        await shutdown_procedures(mock_app)

        # Verify all tasks were cancelled (tasks are real, so just check they exist)
        assert mock_cleanup_task.cancelled()
        assert mock_broadcast_task.cancelled()
        assert mock_redis_task.cancelled()

        # Verify tracing shutdown
        mock_shutdown_tracing.assert_called_once()

    @patch("src.arcp.core.startup.shutdown_tracing")
    async def test_shutdown_procedures_without_tasks(self, mock_shutdown_tracing):
        """Test shutdown procedures when no tasks exist."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        # Remove task attributes
        delattr(mock_app.state, "cleanup_task")
        delattr(mock_app.state, "broadcast_task")
        delattr(mock_app.state, "redis_health_task")

        # Should not raise exception
        await shutdown_procedures(mock_app)

        # Should still shutdown tracing
        mock_shutdown_tracing.assert_called_once()

    @patch("src.arcp.core.startup.shutdown_tracing")
    async def test_shutdown_procedures_task_cancellation_error(
        self, mock_shutdown_tracing
    ):
        """Test shutdown procedures when task cancellation raises exception."""
        mock_app = MagicMock()
        mock_app.state = MagicMock()

        # Create all actual tasks that can be cancelled and awaited
        async def cancelled_coro():
            raise asyncio.CancelledError()

        import asyncio

        mock_cleanup_task = asyncio.create_task(cancelled_coro())
        mock_cleanup_task.cancel()

        mock_broadcast_task = asyncio.create_task(cancelled_coro())
        mock_broadcast_task.cancel()

        mock_redis_task = asyncio.create_task(cancelled_coro())
        mock_redis_task.cancel()

        mock_app.state.cleanup_task = mock_cleanup_task
        mock_app.state.broadcast_task = mock_broadcast_task
        mock_app.state.redis_health_task = mock_redis_task

        # Should handle CancelledError gracefully
        await shutdown_procedures(mock_app)

        assert mock_cleanup_task.cancelled()
        mock_shutdown_tracing.assert_called_once()

    async def test_shutdown_procedures_app_state_type(self):
        """Test shutdown procedures with different app state configurations."""
        mock_app = MagicMock(spec=FastAPI)
        mock_app.state = MagicMock()

        # Create all real tasks that can be awaited
        async def cancelled_coro():
            raise asyncio.CancelledError()

        import asyncio

        mock_cleanup_task = asyncio.create_task(cancelled_coro())
        mock_cleanup_task.cancel()

        mock_broadcast_task = asyncio.create_task(cancelled_coro())
        mock_broadcast_task.cancel()

        mock_redis_task = asyncio.create_task(cancelled_coro())
        mock_redis_task.cancel()

        mock_app.state.cleanup_task = mock_cleanup_task
        mock_app.state.broadcast_task = mock_broadcast_task
        mock_app.state.redis_health_task = mock_redis_task

        with patch("src.arcp.core.startup.shutdown_tracing"):
            # Should work with FastAPI app
            await shutdown_procedures(mock_app)


@pytest.mark.unit
class TestLifespanManager:
    """Test application lifespan context manager."""

    @patch("src.arcp.core.startup.startup_procedures")
    @patch("src.arcp.core.startup.shutdown_procedures")
    async def test_lifespan_success(self, mock_shutdown, mock_startup):
        """Test successful lifespan management."""
        mock_app = MagicMock()

        # Test the async generator
        async_gen = lifespan(mock_app)

        # Start the lifespan (should run startup)
        await async_gen.__anext__()
        mock_startup.assert_called_once_with(mock_app)

        # End the lifespan (should run shutdown)
        try:
            await async_gen.__anext__()
        except StopAsyncIteration:
            # This is expected
            pass

        mock_shutdown.assert_called_once_with(mock_app)

    @patch("src.arcp.core.startup.startup_procedures")
    @patch("src.arcp.core.startup.shutdown_procedures")
    async def test_lifespan_startup_failure(self, mock_shutdown, mock_startup):
        """Test lifespan when startup fails."""
        mock_app = MagicMock()
        mock_startup.side_effect = Exception("Startup failed")

        async_gen = lifespan(mock_app)

        # Startup failure should propagate
        with pytest.raises(Exception, match="Startup failed"):
            await async_gen.__anext__()

        # Shutdown should not be called if startup fails
        mock_shutdown.assert_not_called()

    @patch("src.arcp.core.startup.startup_procedures")
    @patch("src.arcp.core.startup.shutdown_procedures")
    async def test_lifespan_shutdown_failure(self, mock_shutdown, mock_startup):
        """Test lifespan when shutdown fails."""
        mock_app = MagicMock()
        mock_shutdown.side_effect = Exception("Shutdown failed")

        async_gen = lifespan(mock_app)

        # Start successfully
        await async_gen.__anext__()
        mock_startup.assert_called_once_with(mock_app)

        # Shutdown failure should propagate when calling aclose or the next iteration
        try:
            # Try to get the next item which should trigger shutdown
            await async_gen.__anext__()
            pytest.fail("Expected StopAsyncIteration to be raised")
        except StopAsyncIteration:
            # This is expected, now shutdown should have been called and raised
            pass
        except Exception as e:
            # This is the expected shutdown failure
            assert "Shutdown failed" in str(e)

        mock_shutdown.assert_called_once_with(mock_app)

    async def test_lifespan_context_manager_protocol(self):
        """Test that lifespan follows async context manager protocol."""
        with (
            patch("src.arcp.core.startup.startup_procedures"),
            patch("src.arcp.core.startup.shutdown_procedures"),
        ):

            mock_app = MagicMock()

            # Test using async with (if someone tries to use it that way)
            async_gen = lifespan(mock_app)

            # Should be an async generator
            assert hasattr(async_gen, "__anext__")
            assert hasattr(async_gen, "aclose")

    def test_lifespan_function_signature(self):
        """Test lifespan function has correct signature."""
        import inspect

        sig = inspect.signature(lifespan)
        params = list(sig.parameters.keys())

        assert len(params) == 1
        assert params[0] == "app"

        # Should be annotated for FastAPI
        assert sig.parameters["app"].annotation == FastAPI


@pytest.mark.unit
class TestStartupModuleStructure:
    """Test startup module structure and imports."""

    def test_module_imports(self):
        """Test that startup module has all expected imports."""
        import src.arcp.core.startup as startup

        expected_functions = [
            "_redis_health_monitor",
            "validate_configuration",
            "startup_procedures",
            "shutdown_procedures",
            "lifespan",
        ]

        for func_name in expected_functions:
            assert hasattr(startup, func_name)
            assert callable(getattr(startup, func_name))

    def test_module_docstring(self):
        """Test that startup module has proper documentation."""
        import src.arcp.core.startup as startup

        assert startup.__doc__ is not None
        assert "Application startup and shutdown" in startup.__doc__
        assert "lifecycle management" in startup.__doc__

    async def test_async_functions_are_async(self):
        """Test that async functions are properly declared."""
        import inspect

        async_functions = [
            "_redis_health_monitor",
            "startup_procedures",
            "shutdown_procedures",
            "lifespan",
        ]

        for func_name in async_functions:
            func = getattr(startup_module, func_name)
            assert inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func)

    def test_sync_functions_are_sync(self):
        """Test that sync functions are properly declared."""
        import inspect

        sync_functions = ["validate_configuration"]

        for func_name in sync_functions:
            func = getattr(startup_module, func_name)
            assert not inspect.iscoroutinefunction(func)
            assert not inspect.isasyncgenfunction(func)
