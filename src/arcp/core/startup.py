"""
Application startup and shutdown procedures for ARCP.

This module handles application lifecycle management including initialization,
configuration validation, and cleanup procedures.
"""

import asyncio
import logging

from fastapi import FastAPI

from ..api import dashboard
from ..core.validation import start_validation_worker, stop_validation_workers
from ..services.container_scanner import get_container_scanner
from ..utils import rate_limiter, sessions
from ..utils.logging import initialize_logging
from ..utils.tracing import initialize_tracing, shutdown_tracing
from .cleanup import start_cleanup_task
from .config import config
from .dependencies import get_registry
from .jwks import get_jwks_service

logger = logging.getLogger(__name__)


async def _redis_health_monitor() -> None:
    """Periodically trigger backend checks so adapters adopt Redis when it comes online."""
    redis_interval = getattr(config, "REDIS_HEALTH_CHECK_INTERVAL", 30)
    interval = max(5, int(redis_interval or 30))
    logger = logging.getLogger("arcp.redis-health")
    while True:
        try:
            # Trigger registry storage check
            try:
                registry = get_registry()
                await registry.storage.is_backend_available()
            except Exception:
                pass
            # Sessions and rate limiter adapters
            try:
                await sessions._get_storage().is_backend_available()  # type: ignore
            except Exception:
                pass
            try:
                await rate_limiter._get_storage().is_backend_available()  # type: ignore
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Redis health monitor iteration error: {e}")
        await asyncio.sleep(interval)


def validate_configuration():
    """
    Validate application configuration using consolidated validation.
    Raises RuntimeError if required or invalid values are found.
    """
    results = config.validate_all_config()
    logger = logging.getLogger("arcp.config")

    # Required settings
    missing_req = results.get("required_missing", [])
    if missing_req:
        logger.error(f"Required configuration missing: {missing_req}")
        logger.error("INFO: https://github.com/0x00K1/ARCP-Test/blob/main/.env.example")
        raise RuntimeError(f"Missing required configuration: {', '.join(missing_req)}.")
    else:
        logger.info("All required configuration values are present")

    # Optional settings
    optional_missing = results.get("optional_missing", {})
    if any(optional_missing.values()):
        logger.warning(f"Optional configuration missing: {optional_missing}")
    else:
        logger.info("All optional configuration values are present")

    # Value errors
    value_errors = results.get("value_errors", [])
    if value_errors:
        logger.error(f"Configuration value errors: {value_errors}")
        raise RuntimeError(f"Invalid configuration values: {value_errors}")

    # Production-specific issues
    prod_issues = results.get("production_issues", [])
    if prod_issues:
        logger.warning(f"Production configuration issues: {prod_issues}")


async def _initialize_security_features():
    """
    Initializeadvanced security features and log their status.

    Features:
        - SBOM Verification
        - Container Scanning
        - Runtime Attestation
        - Endpoint Validation
    """
    features_enabled = []

    # Endpoint Validation
    if getattr(config, "ENDPOINT_VALIDATION_ENABLED", False):
        validation_mode = getattr(config, "ENDPOINT_VALIDATION_MODE", "static").upper()
        features_enabled.append(f"Endpoint Validation ({validation_mode})")

        if validation_mode == "STATIC":
            logger.info(
                "TPR Endpoint Validation: STATIC mode (14 predefined ARCP v1.0.0 contracts)"
            )
        else:
            contracts_file = getattr(
                config, "ENDPOINT_CONTRACTS_FILE", "Not configured"
            )
            logger.info(
                f"TPR Endpoint Validation: DYNAMIC mode (custom contracts from: {contracts_file})"
            )
    else:
        logger.info("TPR Endpoint Validation: DISABLED")

    # SBOM Verification
    if getattr(config, "SBOM_VERIFICATION_ENABLED", False):
        features_enabled.append("SBOM Verification")
        logger.info(
            f"SBOM Verification enabled (required={config.SBOM_REQUIRED}, "
            f"fail_on_critical={config.SBOM_FAIL_ON_CRITICAL})"
        )

    # Container Scanning
    if getattr(config, "CONTAINER_SCAN_ENABLED", False):
        features_enabled.append("Container Scanning")
        try:
            scanner = get_container_scanner()
            scanner_type = scanner.scanner_type
            if scanner_type:
                logger.info(
                    f"Container Scanning enabled using {scanner_type.value} "
                    f"(required={config.CONTAINER_SCAN_REQUIRED})"
                )
            else:
                logger.warning(
                    "Container Scanning enabled but no scanner found! "
                    "Install Trivy or Grype for scanning capability."
                )
        except Exception as e:
            logger.warning(f"Container Scanning initialization error: {e}")

    # Runtime Attestation
    if getattr(config, "ATTESTATION_ENABLED", False):
        features_enabled.append("Runtime Attestation")
        logger.info(
            f"Runtime Attestation enabled (type={config.ATTESTATION_TYPE}, "
            f"required={config.ATTESTATION_REQUIRED})"
        )

    if features_enabled:
        logger.info(f"Advanced security features active: {', '.join(features_enabled)}")
    else:
        logger.debug("No advanced security features enabled")


async def startup_procedures(app: FastAPI):
    """
    Execute application startup procedures.

    Args:
        app: FastAPI application instance
    """
    # Apply timezone configuration
    config.apply_timezone()

    # Ensure logs directory exists
    try:
        config.ensure_logs_directory()
    except Exception:
        logging.getLogger("arcp.startup").warning("Failed to ensure logs directory")

    # Initialize global logging (file + console) now that directory is ensured
    try:
        initialize_logging()
    except Exception:
        # Fail-quietly; stdout logging will still work
        pass

    # Initialize tracing
    initialize_tracing()

    # Initialize registry
    app.state.registry = get_registry()

    # Start cleanup task
    cleanup_task = asyncio.create_task(start_cleanup_task(get_registry()))
    app.state.cleanup_task = cleanup_task

    # Start dashboard broadcast task
    broadcast_task = asyncio.create_task(dashboard.dashboard_producer(get_registry()))
    app.state.broadcast_task = broadcast_task

    # Start Redis health monitor
    redis_task = asyncio.create_task(_redis_health_monitor())
    app.state.redis_health_task = redis_task

    # Start TPR validation workers (if enabled)
    if config.FEATURE_THREE_PHASE:
        start_validation_worker()
        logger.info("TPR validation workers started")

    # Initialize JWKS service (if enabled)
    if getattr(config, "JWKS_ENABLED", False):
        try:
            jwks_service = get_jwks_service()
            await jwks_service.initialize()
            logger.info("JWKS service initialized with key caching")
        except Exception as e:
            logger.error(f"Failed to initialize JWKS service: {e}")
            # Don't fail startup - will fall back to symmetric signing

    # Initialize advanced security features
    await _initialize_security_features()


async def shutdown_procedures(app: FastAPI):
    """
    Execute application shutdown procedures.

    Args:
        app: FastAPI application instance
    """
    # Cancel background tasks
    if hasattr(app.state, "cleanup_task"):
        app.state.cleanup_task.cancel()
        try:
            await app.state.cleanup_task
        except asyncio.CancelledError:
            pass

    if hasattr(app.state, "broadcast_task"):
        app.state.broadcast_task.cancel()
        try:
            await app.state.broadcast_task
        except asyncio.CancelledError:
            pass

    if hasattr(app.state, "redis_health_task"):
        app.state.redis_health_task.cancel()
        try:
            await app.state.redis_health_task
        except asyncio.CancelledError:
            pass

    # Stop TPR validation workers (if enabled)
    if config.FEATURE_THREE_PHASE:
        stop_validation_workers()
        logger.info("TPR validation workers stopped")

    # Shutdown tracing
    shutdown_tracing()


async def lifespan(app: FastAPI):
    """
    Application lifespan manager for ARCP.

    Handles startup and shutdown procedures for the FastAPI application:
    - Startup: Initializes tracing, agent registry, and starts background cleanup tasks
    - Shutdown: Gracefully stops background tasks, shuts down tracing, and cleans up resources

    Args:
        app: FastAPI application instance

    Yields:
        None: Control back to FastAPI during application runtime
    """
    # Startup procedures
    await startup_procedures(app)

    yield

    # Shutdown procedures
    await shutdown_procedures(app)
