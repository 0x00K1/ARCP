"""
Unit tests for ARCP logging utilities.
"""

import logging
import time
from io import StringIO
from unittest.mock import patch

import pytest

from src.arcp.utils.logging import log_performance, setup_logger


@pytest.mark.unit
class TestSetupLogger:
    """Test cases for setup_logger function."""

    def test_setup_logger_basic(self):
        """Test basic logger setup."""
        logger = setup_logger("test_logger")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert len(logger.handlers) > 0

    def test_setup_logger_with_custom_level(self):
        """Test logger setup with custom level."""
        logger = setup_logger("test_logger_level", level="DEBUG")

        assert logger.level == logging.DEBUG

    def test_setup_logger_with_custom_format(self):
        """Test logger setup with custom format."""
        custom_format = "%(name)s - %(message)s"
        logger = setup_logger("test_logger_format", format_string=custom_format)

        # Check that handler has the custom formatter
        if logger.handlers:
            formatter = logger.handlers[0].formatter
            assert formatter is not None

    def test_setup_logger_idempotent(self):
        """Test that setup_logger is idempotent."""
        logger1 = setup_logger("idempotent_test")
        logger2 = setup_logger("idempotent_test")

        # Should be the same logger instance
        assert logger1 is logger2

        # Should not add duplicate handlers
        handler_count = len(logger1.handlers)
        setup_logger("idempotent_test")
        assert len(logger1.handlers) == handler_count

    @patch("src.arcp.utils.logging.config")
    def test_setup_logger_uses_config_defaults(self, mock_config):
        """Test that setup_logger uses config defaults."""
        mock_config.LOG_LEVEL = "WARNING"
        mock_config.LOG_FORMAT = "%(levelname)s: %(message)s"

        logger = setup_logger("config_test")

        assert logger.level == logging.WARNING

    def test_setup_logger_invalid_level_fallback(self):
        """Test that invalid log level falls back to INFO."""
        logger = setup_logger("invalid_level_test", level="INVALID")

        assert logger.level == logging.INFO


@pytest.mark.unit
class TestPerformanceLogging:
    """Test cases for performance logging decorators."""

    def test_log_performance_sync_function(self):
        """Test performance logging for synchronous functions."""
        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("performance_test")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        @log_performance("test_function", logger)
        def test_function(x, y):
            time.sleep(0.1)  # Simulate work
            return x + y

        result = test_function(1, 2)

        assert result == 3
        log_output = log_stream.getvalue()
        assert "test_function" in log_output
        assert "Completed test_function in" in log_output

    def test_log_performance_with_exception(self):
        """Test performance logging when function raises exception."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("performance_exception_test")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        @log_performance("failing_function", logger)
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

        log_output = log_stream.getvalue()
        assert "failing_function" in log_output
        assert "Failed failing_function after" in log_output

    # NOTE: Commented out because log_async_performance doesn't exist
    # @pytest.mark.asyncio
    # async def test_log_async_performance(self):
    #     """Test performance logging for async functions."""
    #     log_stream = StringIO()
    #     handler = logging.StreamHandler(log_stream)
    #     logger = logging.getLogger("async_performance_test")
    #     logger.addHandler(handler)
    #     logger.setLevel(logging.DEBUG)
    #
    #     @log_async_performance(logger)
    #     async def async_test_function(x, y):
    #         await asyncio.sleep(0.1)  # Simulate async work
    #         return x * y
    #
    #     result = await async_test_function(3, 4)
    #
    #     assert result == 12
    #     log_output = log_stream.getvalue()
    #     assert "async_test_function" in log_output
    #     assert "executed in" in log_output

    # @pytest.mark.asyncio
    # async def test_log_async_performance_with_exception(self):
    #     """Test async performance logging when function raises exception."""
    #     log_stream = StringIO()
    #     handler = logging.StreamHandler(log_stream)
    #     logger = logging.getLogger("async_performance_exception_test")
    #     logger.addHandler(handler)
    #     logger.setLevel(logging.DEBUG)
    #
    #     @log_async_performance(logger)
    #     async def async_failing_function():
    #         await asyncio.sleep(0.05)
    #         raise RuntimeError("Async test error")
    #
    #     with pytest.raises(RuntimeError):
    #         await async_failing_function()
    #
    #     log_output = log_stream.getvalue()
    #     assert "async_failing_function" in log_output
    #     assert "failed after" in log_output

    def test_performance_logging_preserves_function_metadata(self):
        """Test that performance logging preserves function metadata."""
        logger = logging.getLogger("metadata_test")

        @log_performance(logger)
        def documented_function(x: int, y: int) -> int:
            """A well-documented function."""
            return x + y

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "A well-documented function."
        assert hasattr(documented_function, "__annotations__")


# NOTE: TestStructuredLogger commented out because StructuredLogger doesn't exist
# @pytest.mark.unit
# class TestStructuredLogger:
#     """Test cases for StructuredLogger class."""

#     def setup_method(self):
#         """Set up test fixtures."""
#         self.log_stream = StringIO()
#         self.handler = logging.StreamHandler(self.log_stream)
#         self.base_logger = logging.getLogger("structured_test")
#         self.base_logger.addHandler(self.handler)
#         self.base_logger.setLevel(logging.DEBUG)
#
#         self.structured_logger = StructuredLogger(self.base_logger)

#     def test_structured_logger_basic_logging(self):
#         """Test basic structured logging."""
#         self.structured_logger.info("Test message", extra_field="extra_value")
#
#         log_output = self.log_stream.getvalue()
#         assert "Test message" in log_output

#     def test_structured_logger_with_context(self):
#         """Test structured logging with context."""
#         context = {"user_id": "test_user", "request_id": "req_123"}
#         logger_with_context = self.structured_logger.with_context(context)
#
#         logger_with_context.info("Context test")
#
#         # Context should be included in subsequent logs
#         log_output = self.log_stream.getvalue()
#         assert "Context test" in log_output

#     def test_structured_logger_error_with_exception(self):
#         """Test structured error logging with exception."""
#         try:
#             raise ValueError("Test exception")
#         except ValueError as e:
#             self.structured_logger.error("Error occurred", exception=e)
#
#         log_output = self.log_stream.getvalue()
#         assert "Error occurred" in log_output

#     def test_structured_logger_performance_tracking(self):
#         """Test performance tracking in structured logger."""
#         self.structured_logger.start_timer("operation_test")
#         time.sleep(0.1)
#         self.structured_logger.end_timer("operation_test", "Operation completed")
#
#         log_output = self.log_stream.getvalue()
#         assert "Operation completed" in log_output

#     def test_structured_logger_debug_level(self):
#         """Test structured logging at debug level."""
#         self.structured_logger.debug("Debug message", debug_info="detailed")
#
#         log_output = self.log_stream.getvalue()
#         assert "Debug message" in log_output

#     def test_structured_logger_warning_level(self):
#         """Test structured logging at warning level."""
#         self.structured_logger.warning("Warning message", warning_code="W001")
#
#         log_output = self.log_stream.getvalue()
#         assert "Warning message" in log_output

#     def test_structured_logger_critical_level(self):
#         """Test structured logging at critical level."""
#         self.structured_logger.critical("Critical message", severity="high")
#
#         log_output = self.log_stream.getvalue()
#         assert "Critical message" in log_output

#     def test_structured_logger_timer_without_start(self):
#         """Test ending timer without starting it."""
#         # Should handle gracefully without crashing
#         self.structured_logger.end_timer("nonexistent_timer", "Timer end")
#
#         log_output = self.log_stream.getvalue()
#         assert "Timer end" in log_output

#     def test_structured_logger_nested_timers(self):
#         """Test nested timer operations."""
#         self.structured_logger.start_timer("outer_operation")
#         self.structured_logger.start_timer("inner_operation")
#
#         time.sleep(0.05)
#
#         self.structured_logger.end_timer("inner_operation", "Inner completed")
#         self.structured_logger.end_timer("outer_operation", "Outer completed")
#
#         log_output = self.log_stream.getvalue()
#         assert "Inner completed" in log_output
#         assert "Outer completed" in log_output

#     def test_structured_logger_with_none_context(self):
#         """Test structured logger with None context values."""
#         self.structured_logger.info("Test with None", none_field=None, valid_field="valid")
#
#         log_output = self.log_stream.getvalue()
#         assert "Test with None" in log_output

#     def test_structured_logger_context_inheritance(self):
#         """Test that context is properly inherited."""
#         context1 = {"session_id": "sess_123"}
#         context2 = {"user_id": "user_456"}
#
#         logger_with_context1 = self.structured_logger.with_context(context1)
#         logger_with_context2 = logger_with_context1.with_context(context2)
#
#         logger_with_context2.info("Inherited context test")
#
#         # Both contexts should be present
#         log_output = self.log_stream.getvalue()
#         assert "Inherited context test" in log_output


@pytest.mark.unit
class TestLoggingIntegration:
    """Integration tests for logging utilities."""

    def test_logger_setup_and_performance_integration(self):
        """Test integration between logger setup and performance logging."""
        logger = setup_logger("integration_test", level="DEBUG")

        @log_performance(logger)
        def integrated_function():
            return "integration_result"

        result = integrated_function()

        assert result == "integration_result"
        # Function should execute without errors

    # NOTE: Commented out because log_async_performance doesn't exist
    # @pytest.mark.asyncio
    # async def test_async_logger_integration(self):
    #     """Test integration with async logging."""
    #     logger = setup_logger("async_integration_test", level="INFO")
    #
    #     @log_async_performance(logger)
    #     async def async_integrated_function():
    #         await asyncio.sleep(0.01)
    #         return "async_result"
    #
    #     result = await async_integrated_function()
    #
    #     assert result == "async_result"

    # NOTE: Commented out because StructuredLogger doesn't exist
    # def test_structured_logger_with_setup_logger(self):
    #     """Test structured logger with setup_logger integration."""
    #     base_logger = setup_logger("structured_integration_test")
    #     structured = StructuredLogger(base_logger)
    #
    #     structured.info("Integration test", component="test_suite")
    #
    #     # Should execute without errors
    #     assert True

    def test_multiple_loggers_isolation(self):
        """Test that multiple loggers are properly isolated."""
        logger1 = setup_logger("isolation_test_1", level="DEBUG")
        logger2 = setup_logger("isolation_test_2", level="WARNING")

        assert logger1.level == logging.DEBUG
        assert logger2.level == logging.WARNING
        assert logger1 is not logger2

    @patch("src.arcp.utils.logging.config")
    def test_config_integration(self, mock_config):
        """Test integration with configuration module."""
        mock_config.LOG_LEVEL = "ERROR"
        mock_config.LOG_FORMAT = "%(name)s: %(message)s"

        logger = setup_logger("config_integration_test")

        assert logger.level == logging.ERROR
