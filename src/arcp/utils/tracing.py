"""
OpenTelemetry tracing utilities for ARCP.

This module provides comprehensive tracing setup and utilities for distributed
tracing and observability in the ARCP service.
"""

import logging
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes

from ..core.config import config
from ..core.storage_adapter import StorageAdapter
from ..services import get_redis_service

logger = logging.getLogger(__name__)

try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter

    JAEGER_AVAILABLE = True
except ImportError as e:
    logger.warning(
        f"Jaeger exporter not available: {e}. Jaeger tracing will be disabled."
    )
    JaegerExporter = None
    JAEGER_AVAILABLE = False

# Global tracer instance
_tracer: Optional[trace.Tracer] = None


def initialize_tracing() -> None:
    """
    Initialize OpenTelemetry tracing with configured exporters.

    This function sets up:
    - TracerProvider with service metadata
    - Configured exporters (Jaeger, OTLP, Console)
    - Automatic instrumentation for FastAPI, Redis, and HTTP clients
    - Sampling configuration

    Should be called once during application startup.
    """
    global _tracer

    if not config.TRACING_ENABLED:
        logger.info("Tracing is disabled")
        return

    try:
        # Create resource with service information
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: config.TRACE_SERVICE_NAME,
                ResourceAttributes.SERVICE_VERSION: config.TRACE_SERVICE_VERSION,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: config.TRACE_ENVIRONMENT,
            }
        )

        # Create tracer provider with sampling
        sampler = TraceIdRatioBased(config.TRACE_SAMPLE_RATE)
        provider = TracerProvider(resource=resource, sampler=sampler)

        # Configure exporters
        exporters = []
        console_fallback_needed = True  # Track if we need console fallback

        # Jaeger exporter
        if config.JAEGER_ENDPOINT and JAEGER_AVAILABLE:
            try:
                jaeger_exporter = JaegerExporter(
                    agent_host_name="localhost",
                    agent_port=6831,
                    collector_endpoint=config.JAEGER_ENDPOINT,
                )
                # Add Jaeger exporter without health check
                # Note: Health check removed as collector endpoint (14268) doesn't serve HTTP GET at root
                # The collector is specifically for receiving traces via POST to /api/traces
                exporters.append(jaeger_exporter)
                console_fallback_needed = (
                    False  # We have Jaeger configured, disable console
                )
                logger.info(f"Jaeger exporter configured: {config.JAEGER_ENDPOINT}")
            except Exception as e:
                logger.error(f"Failed to configure Jaeger exporter: {e}")
        elif config.JAEGER_ENDPOINT and not JAEGER_AVAILABLE:
            logger.warning(
                "Jaeger endpoint configured but Jaeger exporter is not available"
            )
        elif not config.JAEGER_ENDPOINT:
            logger.info("Jaeger endpoint not configured, skipping Jaeger exporter")

        # OTLP exporter
        if config.OTLP_ENDPOINT:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=config.OTLP_ENDPOINT,
                    insecure=True,  # Use secure=False for HTTP
                )
                exporters.append(otlp_exporter)
                console_fallback_needed = False  # We have a working remote exporter
                logger.info(f"OTLP exporter configured: {config.OTLP_ENDPOINT}")
            except Exception as e:
                logger.error(f"Failed to configure OTLP exporter: {e}")

        # Fallback: only add console exporter if no remote exporters are available
        if console_fallback_needed and not exporters:
            exporters.append(ConsoleSpanExporter())
            logger.info(
                "No remote exporters available - using console exporter as fallback"
            )
        elif not console_fallback_needed:
            logger.info(
                f"Using {len(exporters)} remote exporter(s) - console output disabled to prevent log spam"
            )
        else:
            logger.info(f"Using {len(exporters)} exporter(s) total")

        # Add batch span processors
        for exporter in exporters:
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Get tracer instance
        _tracer = trace.get_tracer(__name__)

        # Setup automatic instrumentation
        _setup_auto_instrumentation()

        logger.info(
            f"OpenTelemetry tracing initialized for service: {config.TRACE_SERVICE_NAME}"
        )

    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")
        _tracer = None


def _setup_auto_instrumentation() -> None:
    """Setup automatic instrumentation for various libraries."""
    try:
        # FastAPI instrumentation
        FastAPIInstrumentor().instrument()
        logger.debug("FastAPI instrumentation enabled")

        # Redis instrumentation only if storage backend is present
        try:
            redis_service = get_redis_service()

            if redis_service.is_available():
                # Build a StorageAdapter with the centralized Redis client
                try:
                    client = redis_service.get_client()
                    adapter = StorageAdapter(client)
                    if adapter.has_backend:
                        RedisInstrumentor().instrument()
                        logger.debug("Redis instrumentation enabled")
                    else:
                        logger.debug("Redis instrumentation skipped (no backend)")
                except Exception:
                    logger.debug("Redis client unavailable; instrumentation skipped")
            else:
                logger.debug("Redis instrumentation skipped (service unavailable)")
        except Exception:
            logger.debug("Redis instrumentation check failed; skipping")

        # HTTP client instrumentation
        HTTPXClientInstrumentor().instrument()
        logger.debug("HTTPX instrumentation enabled")

    except Exception as e:
        logger.error(f"Failed to setup auto instrumentation: {e}")


@contextmanager
def trace_operation(
    operation_name: str,
    attributes: Optional[Dict[str, Any]] = None,
    set_status_on_exception: bool = True,
):
    """
    Context manager for tracing operations.

    Args:
        operation_name: Name of the operation being traced
        attributes: Optional attributes to add to the span
        set_status_on_exception: Whether to set error status on exceptions

    Example:
        with trace_operation("agent_registration", {"agent_id": "123"}):
            # Your code here
            pass
    """
    if not _tracer:
        # If tracing is disabled, just yield without creating spans
        yield None
        return

    with _tracer.start_as_current_span(operation_name) as span:
        if attributes:
            span.set_attributes(attributes)

        try:
            yield span
        except Exception as e:
            if set_status_on_exception:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise


def trace_function(
    operation_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    include_args: bool = False,
    include_result: bool = False,
):
    """
    Decorator for tracing function calls.

    Args:
        operation_name: Optional custom operation name (defaults to function name)
        attributes: Optional attributes to add to the span
        include_args: Whether to include function arguments in span
        include_result: Whether to include function result in span

    Example:
        @trace_function("register_agent", {"component": "registry"})
        async def register_agent(agent_data):
            # Your code here
            pass
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not _tracer:
                return await func(*args, **kwargs)

            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            span_attributes = attributes or {}

            if include_args:
                span_attributes["function.args"] = str(args)[:200]
                span_attributes["function.kwargs"] = str(kwargs)[:200]

            with trace_operation(op_name, span_attributes) as span:
                try:
                    result = await func(*args, **kwargs)

                    if include_result and span:
                        span.set_attribute("function.result", str(result)[:200])

                    return result
                except Exception as e:
                    if span:
                        span.set_attribute("function.exception", str(e))
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not _tracer:
                return func(*args, **kwargs)

            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            span_attributes = attributes or {}

            if include_args:
                span_attributes["function.args"] = str(args)[:200]
                span_attributes["function.kwargs"] = str(kwargs)[:200]

            with trace_operation(op_name, span_attributes) as span:
                try:
                    result = func(*args, **kwargs)

                    if include_result and span:
                        span.set_attribute("function.result", str(result)[:200])

                    return result
                except Exception as e:
                    if span:
                        span.set_attribute("function.exception", str(e))
                    raise

        # Return appropriate wrapper based on function type
        if hasattr(func, "__code__") and func.__code__.co_flags & 0x80:  # CO_COROUTINE
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def set_span_attributes(attributes: Dict[str, Any]) -> None:
    """
    Set multiple attributes on the current span.

    Args:
        attributes: Dictionary of attributes to set
    """
    if not _tracer:
        return

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(attributes)


def shutdown_tracing() -> None:
    """
    Shutdown tracing and flush any remaining spans.

    Should be called during application shutdown.
    """
    if not _tracer:
        return

    try:
        # Force flush any remaining spans
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=5000)

        # Shutdown the provider
        if hasattr(provider, "shutdown"):
            provider.shutdown()

        logger.info("Tracing shutdown completed")

    except Exception as e:
        logger.error(f"Error during tracing shutdown: {e}")
