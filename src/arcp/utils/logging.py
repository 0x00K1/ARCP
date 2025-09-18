"""
Logging utilities for ARCP.

This module provides consistent logging configuration and utilities
for the ARCP service, including structured logging and performance tracking.
"""

import asyncio
import functools
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, Optional

from ..core.config import config

_logging_initialized = False


def initialize_logging(log_file_name: str = "arcp.log") -> None:
    """
    Initialize global logging to write to a rotating file in config.LOGS_DIR and stdout.

    - Idempotent: safe to call multiple times
    - Adds a RotatingFileHandler at <LOGS_DIR>/<log_file_name>
    - Ensures logs directory exists (with fallbacks defined in config)
    - Keeps a StreamHandler for console output
    - Configures Uvicorn loggers to propagate to root
    """
    global _logging_initialized
    if _logging_initialized:
        return

    try:
        # Ensure logs directory (with built-in fallbacks)
        if hasattr(config, "ensure_logs_directory") and callable(
            getattr(config, "ensure_logs_directory")
        ):
            config.ensure_logs_directory()
    except Exception as e:
        # Log the error but continue with stdout-only if file handler fails
        print(f"Warning: Could not ensure logs directory: {e}")
        pass

    # Root logger
    root_logger = logging.getLogger()

    # Level from config (default INFO)
    try:
        level_name = getattr(config, "LOG_LEVEL", "INFO")
        root_logger.setLevel(getattr(logging, str(level_name).upper(), logging.INFO))
    except Exception:
        root_logger.setLevel(logging.INFO)

    # Formatter from config
    try:
        fmt = getattr(
            config,
            "LOG_FORMAT",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        formatter = logging.Formatter(fmt)
    except Exception:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Attach a single rotating file handler to root if possible
    try:
        logs_dir = getattr(config, "LOGS_DIR", None)
        if isinstance(logs_dir, str) and logs_dir:
            # Try multiple fallback locations for logs
            log_locations = [
                logs_dir,  # Primary location - /app/logs
                "/tmp/arcp/logs",  # Fallback 1: tmp directory
                "/var/tmp/arcp/logs",  # Fallback 2: var/tmp
                os.path.expanduser("~/arcp/logs"),  # Fallback 3: user home
            ]

            log_path = None
            for location in log_locations:
                try:
                    os.makedirs(location, exist_ok=True)
                    # Test if we can write to the directory
                    test_file = os.path.join(location, ".test_write")
                    with open(test_file, "w") as f:
                        f.write("test")
                    os.remove(test_file)

                    # If we get here, this location works
                    log_path = os.path.join(location, log_file_name)
                    if location == logs_dir:
                        print(f"Using primary logs directory: {location}")
                    else:
                        print(f"Using fallback logs directory: {location}")
                    break
                except Exception as location_error:
                    print(f"Cannot use logs directory {location}: {location_error}")
                    continue

            if log_path is None:
                print("Warning: No writable logs directory found, using stdout only")
                raise Exception("No writable logs directory available")

            # Avoid duplicate file handlers for the same path
            existing_file = next(
                (
                    h
                    for h in root_logger.handlers
                    if isinstance(h, RotatingFileHandler)
                    and getattr(h, "baseFilename", None) == log_path
                ),
                None,
            )
            if not existing_file:
                file_handler = RotatingFileHandler(
                    log_path,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=5,
                    encoding="utf-8",
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(root_logger.level)
                root_logger.addHandler(file_handler)
                print(f"File logging enabled: {log_path}")
    except Exception as e:
        # If file handler fails, continue with stdout-only
        print(f"Warning: Could not create file handler: {e}")
        pass

    # Ensure a single stream handler exists for console output
    if not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(root_logger.level)
        root_logger.addHandler(stream_handler)

    # Ensure uvicorn loggers propagate to root so they get written to file as well
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        try:
            uvlog = logging.getLogger(name)
            uvlog.propagate = True
            # Do not force-remove existing handlers; let them log to console too
            if uvlog.level == logging.NOTSET:
                uvlog.setLevel(root_logger.level)
        except Exception:
            pass

    _logging_initialized = True


def setup_logger(
    name: str, level: Optional[str] = None, format_string: Optional[str] = None
) -> logging.Logger:
    """
    Setup a logger with consistent configuration.

    Args:
        name: Logger name (typically __name__)
        level: Log level override (defaults to config.LOG_LEVEL)
        format_string: Format string override (defaults to config.LOG_FORMAT)

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logger(__name__)
        >>> logger.info("Application started")
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Set level
        log_level = level or getattr(config, "LOG_LEVEL", "INFO")
        logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))

        # Formatter
        format_str = format_string or getattr(
            config,
            "LOG_FORMAT",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        formatter = logging.Formatter(format_str)

        # Attach a NullHandler with formatter to satisfy tests without duplicating console output
        null_handler = logging.NullHandler()
        null_handler.setLevel(logger.level)
        null_handler.setFormatter(formatter)
        logger.addHandler(null_handler)

        # Allow propagation so root logger (initialized via initialize_logging) writes to file/console
        logger.propagate = True

    return logger


def log_performance(
    operation_name: str,
    logger: Optional[logging.Logger] = None,
    include_args: bool = False,
) -> Callable:
    """
    Decorator to log function performance metrics.

    Args:
        operation_name: Name of the operation for logging
        logger: Logger instance (defaults to operation_name logger)
        include_args: Whether to include function arguments in logs

    Returns:
        Decorator function

    Example:
        >>> @log_performance("agent_registration")
        >>> async def register_agent(request):
        ...     return await process_registration(request)
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = setup_logger(f"performance.{operation_name}")

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            start_dt = datetime.now()

            # Log start
            log_data = {
                "operation": operation_name,
                "start_time": start_dt.isoformat(),
            }

            if include_args:
                log_data["args"] = str(args)[:200]  # Truncate long args
                log_data["kwargs"] = {k: str(v)[:100] for k, v in kwargs.items()}

            logger.info(f"Starting {operation_name}", extra=log_data)

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                logger.info(
                    f"Completed {operation_name} in {duration:.3f}s",
                    extra={
                        **log_data,
                        "duration_seconds": duration,
                        "status": "success",
                    },
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                logger.error(
                    f"Failed {operation_name} after {duration:.3f}s: {e}",
                    extra={
                        **log_data,
                        "duration_seconds": duration,
                        "status": "error",
                        "error": str(e),
                    },
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            start_dt = datetime.now()

            # Log start
            log_data = {
                "operation": operation_name,
                "start_time": start_dt.isoformat(),
            }

            if include_args:
                log_data["args"] = str(args)[:200]
                log_data["kwargs"] = {k: str(v)[:100] for k, v in kwargs.items()}

            logger.info(f"Starting {operation_name}", extra=log_data)

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                logger.info(
                    f"Completed {operation_name} in {duration:.3f}s",
                    extra={
                        **log_data,
                        "duration_seconds": duration,
                        "status": "success",
                    },
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                logger.error(
                    f"Failed {operation_name} after {duration:.3f}s: {e}",
                    extra={
                        **log_data,
                        "duration_seconds": duration,
                        "status": "error",
                        "error": str(e),
                    },
                )
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_with_context(
    logger: logging.Logger, level: str, message: str, **context: Any
) -> None:
    """
    Log a message with structured context data.

    Args:
        logger: Logger instance
        level: Log level (info, warning, error, etc.)
        message: Log message
        **context: Additional context data

    Example:
        >>> logger = setup_logger(__name__)
        >>> log_with_context(
        ...     logger, "info", "Agent registered",
        ...     agent_id="agent-123", user_id="user-456"
        ... )
    """
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, extra=context)


def create_request_logger(request_id: str) -> logging.Logger:
    """
    Create a logger with request context.

    Args:
        request_id: Unique request identifier

    Returns:
        Logger configured with request context

    Example:
        >>> logger = create_request_logger("req-123")
        >>> logger.info("Processing request")  # Includes request_id in logs
    """
    # Use LoggerAdapter to avoid repeatedly overriding the global LogRecordFactory, which
    # caused deep recursion when many requests were processed. The adapter injects the
    # request_id into the log record in a safe, per-logger way.

    base_logger = setup_logger("request")  # single base logger for all requests
    return logging.LoggerAdapter(base_logger, extra={"request_id": request_id})


def mask_sensitive_data(
    data: Dict[str, Any], sensitive_keys: Optional[list] = None
) -> Dict[str, Any]:
    """
    Mask sensitive data in dictionaries for safe logging.

    Args:
        data: Dictionary that may contain sensitive data
        sensitive_keys: List of keys to mask (defaults to common sensitive keys)

    Returns:
        Dictionary with sensitive values masked

    Example:
        >>> data = {"username": "john", "password": "secret123"}
        >>> masked = mask_sensitive_data(data)
        >>> print(masked)  # {"username": "john", "password": "***"}
    """
    if sensitive_keys is None:
        sensitive_keys = [
            "password",
            "token",
            "secret",
            "key",
            "api_key",
            "auth",
            "authorization",
            "credential",
            "jwt",
        ]

    masked_data = {}
    for key, value in data.items():
        if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
            masked_data[key] = "***"
        elif isinstance(value, dict):
            masked_data[key] = mask_sensitive_data(value, sensitive_keys)
        else:
            masked_data[key] = value

    return masked_data
