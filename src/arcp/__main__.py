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
    description="A sophisticated agent orchestration platform that provides centralized service discovery, registration, and control for distributed agent systems.",
    version="2.0.0",
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

    uvicorn.run(
        "arcp.__main__:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
    )
