"""
ARCP (Agent Registry & Control Protocol).

Usage:
    Run with python -m:
        python -m arcp

    Run with uvicorn:
        uvicorn arcp.__main__:app --host 0.0.0.0 --port 8001

    Run with Docker:
        docker-compose up -d --build
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI

from .core.config import config
from .core.startup import validate_configuration
from .utils.logging import initialize_logging

try:
    validate_configuration()
except RuntimeError:
    exit(1)

try:
    config.ensure_logs_directory()
    initialize_logging()
except Exception:
    # Fail-quietly; stdout logging will still work
    pass

from .core.exceptions import register_exception_handlers
from .core.middleware import setup_middleware
from .core.routes import register_api_routes, register_basic_routes, setup_static_files
from .core.startup import lifespan

# FastAPI application
app = FastAPI(
    title="ARCP (Agent Registry & Control Protocol)",
    description="A sophisticated agent orchestration protocol that provides centralized service discovery, registration, communication, and control for distributed agent systems.",
    version="2.1.2",
    debug=bool(getattr(config, "DEBUG", False)),
    lifespan=lifespan,
)

# Setup middleware
setup_middleware(app)

# Register exception handlers
register_exception_handlers(app)

# Setup static files
setup_static_files(app)

# Register basic routes
register_basic_routes(app)

# Register API routers
register_api_routes(app)


if __name__ == "__main__":
    import uvicorn

    # Build uvicorn configuration
    uvicorn_config = {
        "app": "arcp.__main__:app",
        "host": config.HOST,
        "port": config.PORT,
        "reload": config.DEBUG,
        "log_level": "info",
    }

    # Add TLS/HTTPS configuration if enabled
    if config.TLS_ENABLED:
        cert_path = Path(config.TLS_CERT_DIR) / config.TLS_CERT_FILENAME
        key_path = Path(config.TLS_CERT_DIR) / config.TLS_KEY_FILENAME

        # Verify certificate files exist
        if not cert_path.exists():
            logging.error(f"TLS certificate not found: {cert_path}")
            logging.error(
                f"Set ARCP_TLS_ENABLED=false or mount certificates to {config.TLS_CERT_DIR}/"
            )
            sys.exit(1)

        if not key_path.exists():
            logging.error(f"TLS private key not found: {key_path}")
            logging.error(
                f"Set ARCP_TLS_ENABLED=false or mount certificates to {config.TLS_CERT_DIR}/"
            )
            sys.exit(1)

        # Add SSL configuration
        uvicorn_config.update(
            {
                "ssl_certfile": str(cert_path.resolve()),
                "ssl_keyfile": str(key_path.resolve()),
            }
        )

    # Start the server
    uvicorn.run(**uvicorn_config)
