"""
Basic application routes for ARCP.

This module contains core application routes including root, dashboard,
metrics, and other utility endpoints.
"""

from pathlib import Path

try:
    from importlib import resources
except ImportError:
    resources = None
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ..api import agents, auth, dashboard, health, public, tokens
from ..services.metrics import get_metrics_service
from ..utils.api_protection import RequireAdmin, RequireMetricsScraper, RequirePublic


def _web_directory():
    """
    Find the web directory using multiple strategies.

    Returns:
        Path: Path to the web directory, or None if not found
    """
    # Strategy 1: Try to use importlib.resources for installed packages
    if resources:
        try:
            if hasattr(resources, "files"):
                # Python 3.9+
                web_path = resources.files("web")
                if web_path.is_dir():
                    return Path(str(web_path))
            else:
                # Python 3.7-3.8 fallback
                with resources.path("web", "__init__.py") as p:
                    return p.parent
        except (ImportError, ModuleNotFoundError, FileNotFoundError):
            pass

    # Strategy 2: Look relative to this module (development/source scenario)
    current_file = Path(__file__).resolve()

    # From src/arcp/core/routes.py, go up to project root
    project_root_candidates = [
        current_file.parent.parent.parent.parent / "web",  # ../../../../web
        current_file.parent.parent.parent / "web",  # ../../../web
    ]

    for candidate in project_root_candidates:
        if candidate.exists() and candidate.is_dir():
            templates_path = candidate / "templates" / "index.html"
            if templates_path.exists():
                return candidate

    # Strategy 3: Look in the installed package location
    try:
        import arcp

        arcp_path = Path(arcp.__file__).parent.parent
        web_candidate = arcp_path / "web"
        if web_candidate.exists():
            return web_candidate
    except ImportError:
        pass

    # Strategy 4: Check if web directory exists in current working directory
    cwd_web = Path.cwd() / "web"
    if cwd_web.exists() and (cwd_web / "templates" / "index.html").exists():
        return cwd_web

    return None


async def options_root():
    """Handle CORS preflight requests for root endpoint"""
    response = Response(
        content='{"message": "CORS preflight OK"}',
        media_type="application/json",
    )
    response.headers["access-control-allow-origin"] = "*"
    response.headers["access-control-allow-methods"] = "*"
    response.headers["access-control-allow-headers"] = "*"
    response.headers["access-control-allow-credentials"] = "true"
    return response


async def root(_: dict = RequirePublic):
    """
    Root endpoint providing service information.

    Returns basic information about the ARCP service including
    version, status, and links to key endpoints.

    Returns:
        dict: Service information with links to dashboard and documentation
    """
    return {
        "service": "ARCP",
        "version": "2.0.2",
        "status": "healthy",
        "dashboard": "/dashboard",
        "docs": "/docs",
    }


async def dashboard_page(_: dict = RequirePublic):
    """
    Serve the ARCP web dashboard.

    Provides a comprehensive web interface for monitoring and managing
    the ARCP service and registered agents. Features include:
    - Real-time agent status monitoring
    - Performance metrics and charts
    - Agent registration/deregistration
    - System health indicators
    - Live WebSocket updates

    Returns:
        HTMLResponse: Dashboard HTML page or error page if static files not found
    """
    web_dir = _web_directory()

    if web_dir:
        index_path = web_dir / "templates" / "index.html"
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                # Log the error and re-raise for proper error handling
                print(f"Error reading dashboard template: {e}")
                raise

    # Fallback error page
    return """<!DOCTYPE html>
<html>
<head>
    <title>ARCP Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>ARCP Dashboard</h1>
    <p class="error">Dashboard files not found. Ensure static files are properly deployed.</p>
</body>
</html>"""


async def metrics(_: dict = RequireAdmin):
    """
    Prometheus metrics endpoint.

    Exposes application metrics in Prometheus format for monitoring
    and observability. Includes custom ARCP metrics such as:
    - Agent registration counts
    - Request/response metrics
    - Performance indicators
    - System health metrics

    Returns:
        PlainTextResponse: Prometheus-formatted metrics data

    Raises:
        HTTPException: 403 if not authenticated as admin
    """
    metrics_service = get_metrics_service()
    data, content_type = metrics_service.get_prometheus_metrics()
    return Response(content=data, media_type=content_type)


async def metrics_scrape(_: dict = RequireMetricsScraper):
    """
    Prometheus scrape endpoint using a pre-shared bearer token.

    Use this for Prometheus to scrape without granting full admin access.
    Enable by setting METRICS_SCRAPE_TOKEN in env/config and point Prometheus to
    /metrics/scrape with the same bearer token.
    """
    metrics_service = get_metrics_service()
    data, content_type = metrics_service.get_prometheus_metrics()
    return Response(content=data, media_type=content_type)


def setup_static_files(app: FastAPI):
    """
    Mount static files for the dashboard.

    Sets up static file serving for the web dashboard including CSS, JavaScript,
    and other static assets.

    Args:
        app: FastAPI application instance
    """
    web_dir = _web_directory()

    if web_dir:
        static_path = web_dir / "static"
        if static_path.exists():
            app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        else:
            print(f"Warning: Static directory not found at {static_path}")
    else:
        print("Warning: Web directory not found, static files will not be served")


def register_basic_routes(app: FastAPI):
    """Register basic application routes with the FastAPI app."""
    app.add_api_route("/", root, methods=["GET"])
    app.add_api_route("/", options_root, methods=["OPTIONS"])
    app.add_api_route(
        "/dashboard",
        dashboard_page,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/metrics", metrics, methods=["GET"], response_class=PlainTextResponse
    )
    app.add_api_route(
        "/metrics/scrape",
        metrics_scrape,
        methods=["GET"],
        response_class=PlainTextResponse,
    )


def register_api_routes(app):
    """Register API routes with the FastAPI app."""
    app.include_router(agents.router, prefix="/agents", tags=["agents"])
    app.include_router(tokens.router, prefix="/tokens", tags=["tokens"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    app.include_router(health.router, tags=["health"])
    app.include_router(public.router, prefix="/public", tags=["public"])
