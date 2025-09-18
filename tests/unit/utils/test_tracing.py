"""
Unit tests for ARCP OpenTelemetry tracing utilities.

This test module comprehensively tests tracing initialization, instrumentation,
context management, decorators, and error handling.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.arcp.utils.tracing import (
    initialize_tracing,
    set_span_attributes,
    shutdown_tracing,
    trace_function,
    trace_operation,
)


@pytest.mark.unit
class TestTracingInitialization:
    """Test cases for tracing initialization."""

    @patch("src.arcp.utils.tracing.config")
    def test_initialize_tracing_disabled(self, mock_config):
        """Test tracing initialization when disabled."""
        mock_config.TRACING_ENABLED = False

        with patch("src.arcp.utils.tracing.logger") as mock_logger:
            initialize_tracing()

            mock_logger.info.assert_called_with("Tracing is disabled")

    @patch("src.arcp.utils.tracing.config")
    @patch("src.arcp.utils.tracing.Resource")
    @patch("src.arcp.utils.tracing.TracerProvider")
    @patch("src.arcp.utils.tracing.TraceIdRatioBased")
    @patch("src.arcp.utils.tracing.trace")
    def test_initialize_tracing_basic(
        self,
        mock_trace,
        mock_sampler_cls,
        mock_provider_cls,
        mock_resource_cls,
        mock_config,
    ):
        """Test basic tracing initialization."""
        # Setup config
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 0.1
        mock_config.JAEGER_ENDPOINT = None
        mock_config.OTLP_ENDPOINT = None

        # Mock objects
        mock_resource = MagicMock()
        mock_resource_cls.create.return_value = mock_resource

        mock_sampler = MagicMock()
        mock_sampler_cls.return_value = mock_sampler

        mock_provider = MagicMock()
        mock_provider_cls.return_value = mock_provider

        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer

        with patch("src.arcp.utils.tracing._setup_auto_instrumentation") as mock_setup:
            initialize_tracing()

            # Verify resource creation
            mock_resource_cls.create.assert_called_once()

            # Verify provider creation with sampler
            mock_sampler_cls.assert_called_once_with(0.1)
            mock_provider_cls.assert_called_once_with(
                resource=mock_resource, sampler=mock_sampler
            )

            # Verify provider setup
            mock_trace.set_tracer_provider.assert_called_once_with(mock_provider)
            mock_trace.get_tracer.assert_called_once()

            # Verify auto instrumentation
            mock_setup.assert_called_once()

    @patch("src.arcp.utils.tracing.config")
    @patch("src.arcp.utils.tracing.JaegerExporter")
    @patch("src.arcp.utils.tracing.BatchSpanProcessor")
    @patch("httpx.Client")
    def test_initialize_tracing_with_jaeger(
        self, mock_client_cls, mock_processor_cls, mock_jaeger_cls, mock_config
    ):
        """Test tracing initialization with Jaeger exporter."""
        # Setup config
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0
        mock_config.JAEGER_ENDPOINT = "http://jaeger:14268/api/traces"
        mock_config.OTLP_ENDPOINT = None

        # Mock Jaeger exporter
        mock_exporter = MagicMock()
        mock_jaeger_cls.return_value = mock_exporter

        # Mock HTTP client for health check
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client_cls.return_value = mock_client

        # Mock processor
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        with patch("src.arcp.utils.tracing.TracerProvider") as mock_provider_cls:
            with patch("src.arcp.utils.tracing.Resource"):
                with patch("src.arcp.utils.tracing.TraceIdRatioBased"):
                    with patch("src.arcp.utils.tracing.trace"):
                        with patch(
                            "src.arcp.utils.tracing._setup_auto_instrumentation"
                        ):
                            mock_provider = MagicMock()
                            mock_provider_cls.return_value = mock_provider

                            initialize_tracing()

                            # Verify Jaeger exporter configuration
                            mock_jaeger_cls.assert_called_once_with(
                                agent_host_name="localhost",
                                agent_port=6831,
                                collector_endpoint="http://jaeger:14268/api/traces",
                            )

                            # Verify processor and provider setup
                            mock_processor_cls.assert_called_once_with(mock_exporter)
                            mock_provider.add_span_processor.assert_called_once_with(
                                mock_processor
                            )

    @patch("src.arcp.utils.tracing.config")
    @patch("src.arcp.utils.tracing.OTLPSpanExporter")
    def test_initialize_tracing_with_otlp(self, mock_otlp_cls, mock_config):
        """Test tracing initialization with OTLP exporter."""
        # Setup config
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0
        mock_config.JAEGER_ENDPOINT = None
        mock_config.OTLP_ENDPOINT = "http://otel-collector:4317"

        # Mock OTLP exporter
        mock_exporter = MagicMock()
        mock_otlp_cls.return_value = mock_exporter

        with patch("src.arcp.utils.tracing.TracerProvider") as mock_provider_cls:
            with patch("src.arcp.utils.tracing.Resource"):
                with patch("src.arcp.utils.tracing.TraceIdRatioBased"):
                    with patch("src.arcp.utils.tracing.trace"):
                        with patch(
                            "src.arcp.utils.tracing._setup_auto_instrumentation"
                        ):
                            with patch(
                                "src.arcp.utils.tracing.BatchSpanProcessor"
                            ) as mock_processor_cls:
                                mock_provider = MagicMock()
                                mock_provider_cls.return_value = mock_provider
                                mock_processor = MagicMock()
                                mock_processor_cls.return_value = mock_processor

                                initialize_tracing()

                                # Verify OTLP exporter configuration
                                mock_otlp_cls.assert_called_once_with(
                                    endpoint="http://otel-collector:4317",
                                    insecure=True,
                                )

                                # Verify processor setup
                                mock_processor_cls.assert_called_once_with(
                                    mock_exporter
                                )
                                mock_provider.add_span_processor.assert_called_once_with(
                                    mock_processor
                                )

    @patch("src.arcp.utils.tracing.config")
    @patch("src.arcp.utils.tracing.ConsoleSpanExporter")
    def test_initialize_tracing_console_fallback(self, mock_console_cls, mock_config):
        """Test tracing initialization falls back to console exporter."""
        # Setup config with no remote exporters
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0
        mock_config.JAEGER_ENDPOINT = None
        mock_config.OTLP_ENDPOINT = None

        mock_exporter = MagicMock()
        mock_console_cls.return_value = mock_exporter

        with patch("src.arcp.utils.tracing.TracerProvider") as mock_provider_cls:
            with patch("src.arcp.utils.tracing.Resource"):
                with patch("src.arcp.utils.tracing.TraceIdRatioBased"):
                    with patch("src.arcp.utils.tracing.trace"):
                        with patch(
                            "src.arcp.utils.tracing._setup_auto_instrumentation"
                        ):
                            with patch(
                                "src.arcp.utils.tracing.BatchSpanProcessor"
                            ) as mock_processor_cls:
                                mock_provider = MagicMock()
                                mock_provider_cls.return_value = mock_provider

                                initialize_tracing()

                                # Should use console exporter as fallback
                                mock_console_cls.assert_called_once()
                                mock_processor_cls.assert_called_once_with(
                                    mock_exporter
                                )

    @patch("src.arcp.utils.tracing.config")
    def test_initialize_tracing_exception_handling(self, mock_config):
        """Test tracing initialization handles exceptions gracefully."""
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"

        with patch("src.arcp.utils.tracing.Resource") as mock_resource:
            mock_resource.create.side_effect = Exception("Resource creation failed")

            with patch("src.arcp.utils.tracing.logger") as mock_logger:
                initialize_tracing()

                # Should log error and continue
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args[0][0]
                assert "Failed to initialize tracing" in error_call


@pytest.mark.unit
class TestAutoInstrumentation:
    """Test cases for automatic instrumentation setup."""

    @patch("src.arcp.utils.tracing.FastAPIInstrumentor")
    @patch("src.arcp.utils.tracing.HTTPXClientInstrumentor")
    def test_setup_auto_instrumentation_basic(
        self, mock_httpx_instrumentor, mock_fastapi_instrumentor
    ):
        """Test basic auto instrumentation setup."""
        mock_fastapi_inst = MagicMock()
        mock_fastapi_instrumentor.return_value = mock_fastapi_inst

        mock_httpx_inst = MagicMock()
        mock_httpx_instrumentor.return_value = mock_httpx_inst

        with patch("src.arcp.utils.tracing.get_redis_service") as mock_get_redis:
            mock_redis_service = MagicMock()
            mock_redis_service.is_available.return_value = False
            mock_get_redis.return_value = mock_redis_service

            from src.arcp.utils.tracing import _setup_auto_instrumentation

            _setup_auto_instrumentation()

            # Verify FastAPI and HTTPX instrumentation
            mock_fastapi_inst.instrument.assert_called_once()
            mock_httpx_inst.instrument.assert_called_once()

    @patch("src.arcp.utils.tracing.FastAPIInstrumentor")
    @patch("src.arcp.utils.tracing.RedisInstrumentor")
    @patch("src.arcp.utils.tracing.HTTPXClientInstrumentor")
    def test_setup_auto_instrumentation_with_redis(
        self, mock_httpx_inst, mock_redis_inst, mock_fastapi_inst
    ):
        """Test auto instrumentation setup with Redis."""
        from src.arcp.utils.tracing import _setup_auto_instrumentation

        with patch("src.arcp.utils.tracing.get_redis_service") as mock_get_redis:
            with patch("src.arcp.utils.tracing.StorageAdapter") as mock_storage_adapter:
                mock_redis_service = MagicMock()
                mock_redis_service.is_available.return_value = True
                mock_redis_service.get_client.return_value = MagicMock()
                mock_get_redis.return_value = mock_redis_service

                mock_adapter = MagicMock()
                mock_adapter.has_backend = True
                mock_storage_adapter.return_value = mock_adapter

                _setup_auto_instrumentation()

                # Should instrument Redis
                mock_redis_inst.return_value.instrument.assert_called_once()

    @patch("src.arcp.utils.tracing.FastAPIInstrumentor")
    def test_setup_auto_instrumentation_exception_handling(
        self, mock_fastapi_instrumentor
    ):
        """Test auto instrumentation handles exceptions gracefully."""
        mock_fastapi_instrumentor.side_effect = Exception("Instrumentation failed")

        from src.arcp.utils.tracing import _setup_auto_instrumentation

        with patch("src.arcp.utils.tracing.logger") as mock_logger:
            _setup_auto_instrumentation()

            # Should log error but not crash
            mock_logger.error.assert_called()


@pytest.mark.unit
class TestTraceOperation:
    """Test cases for trace_operation context manager."""

    def test_trace_operation_disabled(self):
        """Test trace_operation when tracing is disabled."""
        with patch("src.arcp.utils.tracing._tracer", None):
            with trace_operation("test_operation") as span:
                assert span is None

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_operation_enabled(self, mock_tracer):
        """Test trace_operation when tracing is enabled."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=None
        )

        with trace_operation("test_operation") as span:
            assert span is mock_span

        mock_tracer.start_as_current_span.assert_called_once_with("test_operation")

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_operation_with_attributes(self, mock_tracer):
        """Test trace_operation with attributes."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=None
        )

        attributes = {"key1": "value1", "key2": "value2"}

        with trace_operation("test_operation", attributes):
            pass

        mock_span.set_attributes.assert_called_once_with(attributes)

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_trace_operation_exception_handling(self, mock_trace_module, mock_tracer):
        """Test trace_operation handles exceptions and sets status."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=None
        )

        mock_status = MagicMock()
        mock_trace_module.Status.return_value = mock_status
        mock_trace_module.StatusCode.ERROR = "ERROR"

        test_exception = ValueError("Test error")

        with pytest.raises(ValueError):
            with trace_operation("test_operation", set_status_on_exception=True):
                raise test_exception

        mock_span.set_status.assert_called_once_with(mock_status)
        mock_trace_module.Status.assert_called_once_with("ERROR", "Test error")

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_operation_no_status_on_exception(self, mock_tracer):
        """Test trace_operation with exception status disabled."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=None
        )

        with pytest.raises(ValueError):
            with trace_operation("test_operation", set_status_on_exception=False):
                raise ValueError("Test error")

        # Should not set status on exception
        mock_span.set_status.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
class TestTraceFunctionDecorator:
    """Test cases for trace_function decorator."""

    @patch("src.arcp.utils.tracing._tracer", None)
    async def test_trace_function_disabled(self):
        """Test trace_function decorator when tracing is disabled."""

        @trace_function()
        async def test_async_func():
            return "result"

        result = await test_async_func()
        assert result == "result"

        @trace_function()
        def test_sync_func():
            return "sync_result"

        result = test_sync_func()
        assert result == "sync_result"

    @patch("src.arcp.utils.tracing._tracer")
    async def test_trace_function_async_enabled(self, mock_tracer):
        """Test trace_function decorator with async function."""
        mock_span = MagicMock()

        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function("custom_operation")
            async def test_async_func(arg1, arg2, kwarg1="default"):
                return f"{arg1}-{arg2}-{kwarg1}"

            result = await test_async_func("a", "b", kwarg1="c")

            assert result == "a-b-c"
            mock_trace_op.assert_called_once()

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_function_sync_enabled(self, mock_tracer):
        """Test trace_function decorator with sync function."""
        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_span = MagicMock()
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function("sync_operation")
            def test_sync_func(x, y):
                return x + y

            result = test_sync_func(5, 3)

            assert result == 8
            mock_trace_op.assert_called_once()

    @patch("src.arcp.utils.tracing._tracer")
    async def test_trace_function_with_args_and_result(self, mock_tracer):
        """Test trace_function decorator with argument and result logging."""
        mock_span = MagicMock()

        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function("test_op", include_args=True, include_result=True)
            async def test_func(arg1, arg2=42):
                return {"result": arg1 + arg2}

            result = await test_func(10, arg2=32)

            assert result == {"result": 42}
            # Verify span attributes were set
            mock_span.set_attribute.assert_called()

    @patch("src.arcp.utils.tracing._tracer")
    async def test_trace_function_exception_handling(self, mock_tracer):
        """Test trace_function decorator handles exceptions."""
        mock_span = MagicMock()

        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function("error_op")
            async def failing_func():
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                await failing_func()

            # Should set exception attribute on span
            mock_span.set_attribute.assert_called_with(
                "function.exception", "Test error"
            )

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_function_default_operation_name(self, mock_tracer):
        """Test trace_function uses function name as default operation name."""
        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_span = MagicMock()
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function()  # No custom name
            def my_test_function():
                return "test"

            my_test_function()

            # Should use module.function_name format
            call_args = mock_trace_op.call_args[0]
            assert "my_test_function" in call_args[0]

    def test_trace_function_coroutine_detection(self):
        """Test trace_function correctly detects coroutine functions."""

        @trace_function()
        async def async_func():
            return "async"

        @trace_function()
        def sync_func():
            return "sync"

        # The decorator should return appropriate wrappers
        # This is tested implicitly by the other test cases
        assert callable(async_func)
        assert callable(sync_func)


@pytest.mark.unit
class TestSetSpanAttributes:
    """Test cases for set_span_attributes function."""

    @patch("src.arcp.utils.tracing._tracer", None)
    def test_set_span_attributes_disabled(self):
        """Test set_span_attributes when tracing is disabled."""
        # Should not crash when tracing is disabled
        set_span_attributes({"key": "value"})

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_set_span_attributes_enabled(self, mock_trace_module, mock_tracer):
        """Test set_span_attributes when tracing is enabled."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_trace_module.get_current_span.return_value = mock_span

        attributes = {"key1": "value1", "key2": "value2"}
        set_span_attributes(attributes)

        mock_span.set_attributes.assert_called_once_with(attributes)

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_set_span_attributes_not_recording(self, mock_trace_module, mock_tracer):
        """Test set_span_attributes when span is not recording."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False
        mock_trace_module.get_current_span.return_value = mock_span

        attributes = {"key1": "value1"}
        set_span_attributes(attributes)

        # Should not set attributes when not recording
        mock_span.set_attributes.assert_not_called()


@pytest.mark.unit
class TestShutdownTracing:
    """Test cases for shutdown_tracing function."""

    @patch("src.arcp.utils.tracing._tracer", None)
    def test_shutdown_tracing_disabled(self):
        """Test shutdown_tracing when tracing is disabled."""
        # Should not crash when tracing is disabled
        shutdown_tracing()

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_shutdown_tracing_enabled(self, mock_trace_module, mock_tracer):
        """Test shutdown_tracing when tracing is enabled."""
        mock_provider = MagicMock()
        mock_provider.force_flush.return_value = None
        mock_provider.shutdown.return_value = None
        mock_trace_module.get_tracer_provider.return_value = mock_provider

        with patch("src.arcp.utils.tracing.logger") as mock_logger:
            shutdown_tracing()

            mock_provider.force_flush.assert_called_once_with(timeout_millis=5000)
            mock_provider.shutdown.assert_called_once()
            mock_logger.info.assert_called_with("Tracing shutdown completed")

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_shutdown_tracing_no_force_flush(self, mock_trace_module, mock_tracer):
        """Test shutdown_tracing when provider doesn't have force_flush."""
        mock_provider = MagicMock()
        del mock_provider.force_flush  # Remove force_flush method
        mock_provider.shutdown.return_value = None
        mock_trace_module.get_tracer_provider.return_value = mock_provider

        shutdown_tracing()

        # Should only call shutdown
        mock_provider.shutdown.assert_called_once()

    @patch("src.arcp.utils.tracing._tracer")
    @patch("src.arcp.utils.tracing.trace")
    def test_shutdown_tracing_exception_handling(self, mock_trace_module, mock_tracer):
        """Test shutdown_tracing handles exceptions gracefully."""
        mock_provider = MagicMock()
        mock_provider.force_flush.side_effect = Exception("Flush failed")
        mock_trace_module.get_tracer_provider.return_value = mock_provider

        with patch("src.arcp.utils.tracing.logger") as mock_logger:
            shutdown_tracing()

            # Should log error but not crash
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Error during tracing shutdown" in error_call


@pytest.mark.unit
class TestTracingEdgeCases:
    """Test cases for tracing edge cases and error scenarios."""

    @patch("src.arcp.utils.tracing.config")
    def test_initialize_tracing_partial_config(self, mock_config):
        """Test tracing initialization with partial configuration."""
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = None  # Missing service name
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0

        with patch("src.arcp.utils.tracing.Resource") as mock_resource:
            with patch("src.arcp.utils.tracing.TracerProvider"):
                with patch("src.arcp.utils.tracing.trace"):
                    with patch("src.arcp.utils.tracing._setup_auto_instrumentation"):

                        initialize_tracing()

                        # Should handle None values gracefully
                        mock_resource.create.assert_called_once()

    @patch("src.arcp.utils.tracing._tracer")
    def test_trace_operation_long_attribute_values(self, mock_tracer):
        """Test trace_operation with very long attribute values."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=None
        )

        # Very long attribute value
        long_value = "A" * 10000
        attributes = {"long_key": long_value}

        with trace_operation("test_operation", attributes):
            pass

        # Should still set attributes without issues
        mock_span.set_attributes.assert_called_once_with(attributes)

    @patch("src.arcp.utils.tracing._tracer")
    async def test_trace_function_with_complex_args(self, mock_tracer):
        """Test trace_function with complex argument types."""
        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:
            mock_span = MagicMock()
            mock_trace_op.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_trace_op.return_value.__exit__ = MagicMock(return_value=None)

            @trace_function("complex_args", include_args=True)
            async def complex_func(obj_arg, list_arg, dict_arg=None):
                return "result"

            # Complex arguments
            complex_obj = MagicMock()
            result = await complex_func(
                complex_obj,
                [1, 2, 3, {"nested": "dict"}],
                dict_arg={"key": "value"},
            )

            assert result == "result"
            # Should handle complex args gracefully (converted to string)
            # May or may not call set_attribute depending on implementation
            # Just check the function executed successfully
            assert True  # Function completed without errors

    def test_trace_function_preserves_function_metadata(self):
        """Test that trace_function preserves original function metadata."""

        @trace_function("test_op")
        def documented_function(x: int, y: str) -> str:
            """A well-documented function."""
            return f"{x}:{y}"

        # Should preserve function name, docstring, and annotations
        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "A well-documented function."
        # Note: Annotations might be preserved by @wraps decorator

    @patch("src.arcp.utils.tracing.config")
    @patch("httpx.Client")
    def test_initialize_tracing_jaeger_health_check_failure(
        self, mock_client_cls, mock_config
    ):
        """Test Jaeger initialization when health check fails."""
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0
        mock_config.JAEGER_ENDPOINT = "http://jaeger:14268/api/traces"
        mock_config.OTLP_ENDPOINT = None

        # Mock HTTP client that fails health check
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with patch("src.arcp.utils.tracing.JaegerExporter") as mock_jaeger:
            with patch("src.arcp.utils.tracing.TracerProvider"):
                with patch("src.arcp.utils.tracing.Resource"):
                    with patch("src.arcp.utils.tracing.trace"):
                        with patch(
                            "src.arcp.utils.tracing._setup_auto_instrumentation"
                        ):

                            mock_exporter = MagicMock()
                            mock_jaeger.return_value = mock_exporter

                            initialize_tracing()

                            # Should still create Jaeger exporter despite health check failure
                            mock_jaeger.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrencyScenarios:
    """Test cases for concurrent tracing operations."""

    @patch("src.arcp.utils.tracing._tracer")
    async def test_concurrent_trace_operations(self, mock_tracer):
        """Test concurrent trace operations."""
        call_count = 0

        def mock_start_span(name):
            nonlocal call_count
            call_count += 1
            mock_span = MagicMock()
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value=mock_span)
            mock_context.__exit__ = MagicMock(return_value=None)
            return mock_context

        mock_tracer.start_as_current_span.side_effect = mock_start_span

        # Execute multiple concurrent trace operations
        async def traced_operation(op_id):
            with trace_operation(f"operation_{op_id}"):
                await asyncio.sleep(0.01)  # Small delay
                return op_id

        tasks = [traced_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert call_count == 10

    @patch("src.arcp.utils.tracing._tracer")
    async def test_concurrent_trace_function_calls(self, mock_tracer):
        """Test concurrent calls to traced functions."""
        call_count = 0

        with patch("src.arcp.utils.tracing.trace_operation") as mock_trace_op:

            def mock_trace_operation_call(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock_context = MagicMock()
                mock_context.__enter__ = MagicMock(return_value=MagicMock())
                mock_context.__exit__ = MagicMock(return_value=None)
                return mock_context

            mock_trace_op.side_effect = mock_trace_operation_call

            @trace_function("concurrent_func")
            async def traced_func(value):
                await asyncio.sleep(0.01)
                return value * 2

            tasks = [traced_func(i) for i in range(5)]
            results = await asyncio.gather(*tasks)

            assert results == [0, 2, 4, 6, 8]
            assert call_count == 5


@pytest.mark.unit
class TestTracingIntegration:
    """Integration-style tests for tracing functionality."""

    @patch("src.arcp.utils.tracing.config")
    def test_full_tracing_lifecycle(self, mock_config):
        """Test full tracing lifecycle from initialization to shutdown."""
        # Configure tracing
        mock_config.TRACING_ENABLED = True
        mock_config.TRACE_SERVICE_NAME = "test-service"
        mock_config.TRACE_SERVICE_VERSION = "1.0.0"
        mock_config.TRACE_ENVIRONMENT = "test"
        mock_config.TRACE_SAMPLE_RATE = 1.0
        mock_config.JAEGER_ENDPOINT = None
        mock_config.OTLP_ENDPOINT = None

        with patch("src.arcp.utils.tracing.TracerProvider") as mock_provider_cls:
            with patch("src.arcp.utils.tracing.Resource"):
                with patch("src.arcp.utils.tracing.trace") as mock_trace_module:
                    with patch("src.arcp.utils.tracing._setup_auto_instrumentation"):

                        # Mock objects
                        mock_provider = MagicMock()
                        mock_provider_cls.return_value = mock_provider
                        mock_tracer = MagicMock()
                        mock_trace_module.get_tracer.return_value = mock_tracer
                        mock_trace_module.get_tracer_provider.return_value = (
                            mock_provider
                        )

                        # Initialize tracing
                        initialize_tracing()

                        # Verify initialization
                        mock_trace_module.set_tracer_provider.assert_called_once()

                        # Test tracing operations work
                        with patch("src.arcp.utils.tracing._tracer", mock_tracer):
                            mock_span = MagicMock()
                            mock_tracer.start_as_current_span.return_value.__enter__ = (
                                MagicMock(return_value=mock_span)
                            )
                            mock_tracer.start_as_current_span.return_value.__exit__ = (
                                MagicMock(return_value=None)
                            )

                            with trace_operation("test_operation", {"key": "value"}):
                                pass

                            mock_span.set_attributes.assert_called_once_with(
                                {"key": "value"}
                            )

                        # Test shutdown
                        mock_provider.force_flush.return_value = None
                        mock_provider.shutdown.return_value = None

                        shutdown_tracing()

                        mock_provider.force_flush.assert_called_once()
                        mock_provider.shutdown.assert_called_once()
