"""
Unit tests for core application routes.

Tests the basic application routes including root, dashboard, metrics, and route registration.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.arcp.core.routes import (
    dashboard_page,
    metrics,
    metrics_scrape,
    options_root,
    register_api_routes,
    register_basic_routes,
    root,
    setup_static_files,
)


@pytest.mark.unit
class TestCORSHandling:
    """Test CORS preflight request handling."""

    async def test_options_root_headers(self):
        """Test OPTIONS root endpoint returns proper CORS headers."""
        response = await options_root()

        assert isinstance(response, Response)
        assert response.media_type == "application/json"
        assert '{"message": "CORS preflight OK"}' in str(response.body)

        # Check CORS headers
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["access-control-allow-methods"] == "*"
        assert response.headers["access-control-allow-headers"] == "*"
        assert response.headers["access-control-allow-credentials"] == "true"

    async def test_options_root_response_format(self):
        """Test OPTIONS root endpoint response format."""
        response = await options_root()

        # Response should be valid JSON
        import json

        content = json.loads(response.body)
        assert content["message"] == "CORS preflight OK"


@pytest.mark.unit
class TestRootEndpoint:
    """Test root API endpoint functionality."""

    async def test_root_endpoint_response(self):
        """Test root endpoint returns service information."""
        mock_require_public = {}

        result = await root(mock_require_public)

        assert isinstance(result, dict)
        assert result["service"] == "ARCP"
        assert result["version"] == "2.0.3"
        assert result["status"] == "healthy"
        assert result["dashboard"] == "/dashboard"
        assert result["docs"] == "/docs"

    async def test_root_endpoint_with_different_protection(self):
        """Test root endpoint works with different protection contexts."""
        # Should work with empty dict
        result1 = await root({})
        assert result1["service"] == "ARCP"

        # Should work with populated dict (simulating auth context)
        result2 = await root({"user": "test", "authenticated": True})
        assert result2["service"] == "ARCP"

        # Both results should be identical
        assert result1 == result2

    async def test_root_endpoint_structure(self):
        """Test root endpoint response has all required fields."""
        result = await root({})

        required_fields = ["service", "version", "status", "dashboard", "docs"]
        for field in required_fields:
            assert field in result
            assert result[field] is not None
            assert isinstance(result[field], str)


@pytest.mark.unit
class TestDashboardEndpoint:
    """Test dashboard page serving functionality."""

    @patch("src.arcp.core.routes._web_directory")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="<html><body>Dashboard</body></html>",
    )
    async def test_dashboard_page_with_existing_file(self, mock_file, mock_web_dir):
        """Test dashboard page when dashboard file exists."""
        from pathlib import Path

        # Mock web directory exists and index.html exists
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_web_dir.return_value = mock_path
        mock_path.__truediv__ = MagicMock(return_value=mock_path)

        result = await dashboard_page({})

        assert result == "<html><body>Dashboard</body></html>"
        mock_web_dir.assert_called_once()
        mock_file.assert_called_once()

    @patch("src.arcp.core.routes._web_directory")
    async def test_dashboard_page_without_file(self, mock_web_dir):
        """Test dashboard page when dashboard file doesn't exist."""
        mock_web_dir.return_value = None

        result = await dashboard_page({})

        assert isinstance(result, str)
        assert "<title>ARCP Dashboard</title>" in result
        assert "Dashboard files not found" in result
        assert "error" in result
        mock_web_dir.assert_called_once()

    @patch("src.arcp.core.routes._web_directory")
    async def test_dashboard_page_path_construction(self, mock_web_dir):
        """Test that dashboard page constructs correct file path."""
        from pathlib import Path

        # Mock web directory exists but index.html doesn't exist
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_web_dir.return_value = mock_path
        mock_path.__truediv__ = MagicMock(return_value=mock_path)

        result = await dashboard_page({})

        # Should return fallback HTML when file doesn't exist
        assert "<title>ARCP Dashboard</title>" in result
        mock_web_dir.assert_called_once()

    @patch("src.arcp.core.routes._web_directory")
    @patch("builtins.open")
    async def test_dashboard_page_file_read_error(self, mock_file, mock_web_dir):
        """Test dashboard page behavior when file read fails."""
        from pathlib import Path

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_web_dir.return_value = mock_path
        mock_path.__truediv__ = MagicMock(return_value=mock_path)
        mock_file.side_effect = IOError("Permission denied")

        with pytest.raises(IOError):
            await dashboard_page({})

    @patch("src.arcp.core.routes._web_directory")
    @patch("builtins.open", new_callable=mock_open, read_data="")
    async def test_dashboard_page_empty_file(self, mock_file, mock_web_dir):
        """Test dashboard page with empty dashboard file."""
        from pathlib import Path

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_web_dir.return_value = mock_path
        mock_path.__truediv__ = MagicMock(return_value=mock_path)

        result = await dashboard_page({})

        assert result == ""

    @patch("src.arcp.core.routes._web_directory")
    async def test_dashboard_fallback_html_structure(self, mock_web_dir):
        """Test fallback dashboard HTML structure."""
        mock_web_dir.return_value = None

        result = await dashboard_page({})

        # Should be valid HTML structure
        assert result.startswith("<!DOCTYPE html>")
        assert "<html>" in result
        assert "<head>" in result
        assert "<body>" in result
        assert "</html>" in result

        # Should contain error styling
        assert "font-family: Arial" in result
        assert "color: red" in result


@pytest.mark.unit
class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint functionality."""

    @patch("src.arcp.core.routes.get_metrics_service")
    async def test_metrics_endpoint_success(self, mock_get_metrics_service):
        """Test metrics endpoint returns Prometheus data."""
        mock_service = MagicMock()
        mock_service.get_prometheus_metrics.return_value = (
            "# Metrics\ntest_metric 1.0",
            "text/plain",
        )
        mock_get_metrics_service.return_value = mock_service

        result = await metrics({})

        assert isinstance(result, Response)
        assert result.media_type == "text/plain"
        mock_get_metrics_service.assert_called_once()
        mock_service.get_prometheus_metrics.assert_called_once()

    @patch("src.arcp.core.routes.get_metrics_service")
    async def test_metrics_endpoint_different_content_types(
        self, mock_get_metrics_service
    ):
        """Test metrics endpoint with different content types."""
        mock_service = MagicMock()

        # Test with different content type
        mock_service.get_prometheus_metrics.return_value = (
            '{"metrics": "data"}',
            "application/json",
        )
        mock_get_metrics_service.return_value = mock_service

        result = await metrics({})

        assert isinstance(result, Response)
        assert result.media_type == "application/json"

    @patch("src.arcp.core.routes.get_metrics_service")
    async def test_metrics_endpoint_service_failure(self, mock_get_metrics_service):
        """Test metrics endpoint when metrics service fails."""
        mock_get_metrics_service.side_effect = Exception("Metrics service unavailable")

        with pytest.raises(Exception, match="Metrics service unavailable"):
            await metrics({})

    @patch("src.arcp.core.routes.get_metrics_service")
    async def test_metrics_endpoint_empty_response(self, mock_get_metrics_service):
        """Test metrics endpoint with empty metrics response."""
        mock_service = MagicMock()
        mock_service.get_prometheus_metrics.return_value = ("", "text/plain")
        mock_get_metrics_service.return_value = mock_service

        result = await metrics({})

        assert isinstance(result, Response)
        assert result.media_type == "text/plain"


@pytest.mark.unit
class TestStaticFileSetup:
    """Test static file mounting functionality."""

    @patch("src.arcp.core.routes._web_directory")
    def test_setup_static_files_with_existing_directory(self, mock_web_dir):
        """Test static file setup when static directory exists."""
        from pathlib import Path

        # Mock web directory exists and static directory exists
        mock_path = MagicMock(spec=Path)
        mock_static_path = MagicMock(spec=Path)
        mock_static_path.exists.return_value = True
        mock_static_path.__str__ = MagicMock(return_value="/fake/static/path")
        mock_path.__truediv__ = MagicMock(return_value=mock_static_path)
        mock_web_dir.return_value = mock_path
        mock_app = MagicMock()

        with patch("src.arcp.core.routes.StaticFiles") as mock_static_files:
            setup_static_files(mock_app)

        mock_app.mount.assert_called_once()
        call_args = mock_app.mount.call_args
        assert call_args[0][0] == "/static"  # mount path
        assert call_args[1]["name"] == "static"  # name parameter
        mock_web_dir.assert_called_once()
        mock_static_files.assert_called_once_with(directory="/fake/static/path")

    @patch("src.arcp.core.routes._web_directory")
    def test_setup_static_files_without_directory(self, mock_web_dir):
        """Test static file setup when web directory doesn't exist."""
        mock_web_dir.return_value = None
        mock_app = MagicMock()

        setup_static_files(mock_app)

        mock_app.mount.assert_not_called()
        mock_web_dir.assert_called_once()

    @patch("src.arcp.core.routes._web_directory")
    def test_setup_static_files_web_dir_exists_but_static_missing(self, mock_web_dir):
        """Test static file setup when web directory exists but static directory doesn't."""
        from pathlib import Path

        # Mock web directory exists but static directory doesn't exist
        mock_path = MagicMock(spec=Path)
        mock_static_path = MagicMock(spec=Path)
        mock_static_path.exists.return_value = False
        mock_path.__truediv__ = MagicMock(return_value=mock_static_path)
        mock_web_dir.return_value = mock_path
        mock_app = MagicMock()

        setup_static_files(mock_app)

        mock_app.mount.assert_not_called()
        mock_web_dir.assert_called_once()

    @patch("src.arcp.core.routes._web_directory")
    def test_setup_static_files_path_construction(self, mock_web_dir):
        """Test that static file setup constructs correct path."""
        from pathlib import Path

        # Mock web directory exists and static directory exists
        mock_path = MagicMock(spec=Path)
        mock_static_path = MagicMock(spec=Path)
        mock_static_path.exists.return_value = True
        mock_static_path.__str__ = MagicMock(return_value="/fake/web/static")
        mock_path.__truediv__ = MagicMock(return_value=mock_static_path)
        mock_web_dir.return_value = mock_path
        mock_app = MagicMock()

        with patch("src.arcp.core.routes.StaticFiles") as mock_static_files:
            setup_static_files(mock_app)

        # Verify web directory was called and path construction happened
        mock_web_dir.assert_called_once()
        mock_path.__truediv__.assert_called_once_with("static")
        mock_static_files.assert_called_once_with(directory="/fake/web/static")


@pytest.mark.unit
class TestRouteRegistration:
    """Test route registration functionality."""

    def test_register_basic_routes(self):
        """Test registration of basic application routes."""
        mock_app = MagicMock()

        register_basic_routes(mock_app)

        # Should register 5 routes (including metrics scrape endpoint)
        assert mock_app.add_api_route.call_count == 5

        calls = mock_app.add_api_route.call_args_list

        # Check root GET route
        assert calls[0][0] == ("/", root)
        assert calls[0][1]["methods"] == ["GET"]

        # Check root OPTIONS route
        assert calls[1][0] == ("/", options_root)
        assert calls[1][1]["methods"] == ["OPTIONS"]

        # Check dashboard route
        assert calls[2][0] == ("/dashboard", dashboard_page)
        assert calls[2][1]["methods"] == ["GET"]
        assert calls[2][1]["response_class"] == HTMLResponse

        # Check metrics route
        assert calls[3][0] == ("/metrics", metrics)
        assert calls[3][1]["methods"] == ["GET"]
        assert calls[3][1]["response_class"] == PlainTextResponse

        # Check metrics scrape route
        assert calls[4][0] == ("/metrics/scrape", metrics_scrape)
        assert calls[4][1]["methods"] == ["GET"]
        assert calls[4][1]["response_class"] == PlainTextResponse

    @patch("src.arcp.core.routes.agents")
    @patch("src.arcp.core.routes.tokens")
    @patch("src.arcp.core.routes.auth")
    @patch("src.arcp.core.routes.dashboard")
    @patch("src.arcp.core.routes.health")
    @patch("src.arcp.core.routes.public")
    def test_register_api_routes(
        self,
        mock_public,
        mock_health,
        mock_dashboard,
        mock_auth,
        mock_tokens,
        mock_agents,
    ):
        """Test registration of API routes."""
        mock_app = MagicMock()

        # Mock routers
        for mock_module in [
            mock_agents,
            mock_tokens,
            mock_auth,
            mock_dashboard,
            mock_health,
            mock_public,
        ]:
            mock_module.router = MagicMock()

        register_api_routes(mock_app)

        # Should include 6 routers
        assert mock_app.include_router.call_count == 6

        calls = mock_app.include_router.call_args_list

        # Check agents router
        assert calls[0][0][0] == mock_agents.router
        assert calls[0][1]["prefix"] == "/agents"
        assert calls[0][1]["tags"] == ["agents"]

        # Check tokens router
        assert calls[1][0][0] == mock_tokens.router
        assert calls[1][1]["prefix"] == "/tokens"
        assert calls[1][1]["tags"] == ["tokens"]

        # Check auth router
        assert calls[2][0][0] == mock_auth.router
        assert calls[2][1]["prefix"] == "/auth"
        assert calls[2][1]["tags"] == ["auth"]

        # Check dashboard router
        assert calls[3][0][0] == mock_dashboard.router
        assert calls[3][1]["prefix"] == "/dashboard"
        assert calls[3][1]["tags"] == ["dashboard"]

        # Check health router (no prefix)
        assert calls[4][0][0] == mock_health.router
        assert calls[4][1]["tags"] == ["health"]
        assert "prefix" not in calls[4][1]

        # Check public router
        assert calls[5][0][0] == mock_public.router
        assert calls[5][1]["prefix"] == "/public"
        assert calls[5][1]["tags"] == ["public"]

    def test_register_basic_routes_app_type(self):
        """Test that register_basic_routes expects FastAPI app."""
        mock_app = MagicMock(spec=FastAPI)

        # Should not raise exception
        register_basic_routes(mock_app)

        # Verify methods were called
        assert mock_app.add_api_route.called

    def test_register_api_routes_app_type(self):
        """Test that register_api_routes works with any app object."""
        mock_app = MagicMock()

        with patch("src.arcp.core.routes.agents") as mock_agents:
            mock_agents.router = MagicMock()
            with patch("src.arcp.core.routes.tokens") as mock_tokens:
                mock_tokens.router = MagicMock()
                with patch("src.arcp.core.routes.auth") as mock_auth:
                    mock_auth.router = MagicMock()
                    with patch("src.arcp.core.routes.dashboard") as mock_dashboard:
                        mock_dashboard.router = MagicMock()
                        with patch("src.arcp.core.routes.health") as mock_health:
                            mock_health.router = MagicMock()
                            with patch("src.arcp.core.routes.public") as mock_public:
                                mock_public.router = MagicMock()

                                # Should not raise exception
                                register_api_routes(mock_app)
                                assert mock_app.include_router.called


@pytest.mark.unit
class TestRouteModuleStructure:
    """Test routes module structure and imports."""

    def test_module_imports(self):
        """Test that routes module has all expected imports."""
        import src.arcp.core.routes as routes

        # Should have all required functions
        expected_functions = [
            "options_root",
            "root",
            "dashboard_page",
            "metrics",
            "setup_static_files",
            "register_basic_routes",
            "register_api_routes",
        ]

        for func_name in expected_functions:
            assert hasattr(routes, func_name)
            assert callable(getattr(routes, func_name))

    def test_module_docstring(self):
        """Test that routes module has proper documentation."""
        import src.arcp.core.routes as routes

        assert routes.__doc__ is not None
        assert "Basic application routes" in routes.__doc__
        assert "ARCP" in routes.__doc__

    async def test_endpoint_dependency_injection(self):
        """Test that endpoints use proper dependency injection."""
        import inspect

        from src.arcp.utils.api_protection import RequireAdmin, RequirePublic

        # Test root endpoint
        sig = inspect.signature(root)
        params = list(sig.parameters.values())
        assert len(params) == 1
        assert params[0].default == RequirePublic

        # Test dashboard_page endpoint
        sig = inspect.signature(dashboard_page)
        params = list(sig.parameters.values())
        assert len(params) == 1
        assert params[0].default == RequirePublic

        # Test metrics endpoint (requires admin access)
        sig = inspect.signature(metrics)
        params = list(sig.parameters.values())
        assert len(params) == 1
        assert params[0].default == RequireAdmin
