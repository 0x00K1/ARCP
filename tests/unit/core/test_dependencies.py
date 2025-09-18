"""
Unit tests for FastAPI dependencies.

Tests the dependency injection system for core application components.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.arcp.core.dependencies import get_registry


@pytest.mark.unit
class TestDependencies:
    """Test dependency injection functionality."""

    @patch("src.arcp.core.dependencies._get_registry")
    def test_get_registry(self, mock_get_registry):
        """Test getting registry dependency."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        result = get_registry()

        assert result == mock_registry
        mock_get_registry.assert_called_once()

    @patch("src.arcp.core.dependencies._get_registry")
    def test_get_registry_multiple_calls(self, mock_get_registry):
        """Test that get_registry returns same instance on multiple calls."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        result1 = get_registry()
        result2 = get_registry()
        result3 = get_registry()

        assert result1 == mock_registry
        assert result2 == mock_registry
        assert result3 == mock_registry
        assert result1 is result2 is result3

        # Should be called for each invocation
        assert mock_get_registry.call_count == 3

    def test_get_registry_return_type_annotation(self):
        """Test that get_registry has proper return type annotation."""
        import inspect

        from src.arcp.core.registry import AgentRegistry

        # Get the function signature
        sig = inspect.signature(get_registry)
        return_annotation = sig.return_annotation

        # Should be annotated to return AgentRegistry
        assert return_annotation == AgentRegistry

    @patch("src.arcp.core.dependencies._get_registry")
    def test_get_registry_exception_handling(self, mock_get_registry):
        """Test get_registry behavior when underlying registry fails."""
        mock_get_registry.side_effect = Exception("Registry initialization failed")

        with pytest.raises(Exception, match="Registry initialization failed"):
            get_registry()

    def test_module_structure(self):
        """Test that dependencies module has expected structure."""
        import src.arcp.core.dependencies as deps

        # Should have get_registry function
        assert hasattr(deps, "get_registry")
        assert callable(deps.get_registry)

        # Should import from registry module
        assert hasattr(deps, "_get_registry")

        # Module should have proper docstring
        assert deps.__doc__ is not None
        assert "Dependencies for FastAPI endpoints" in deps.__doc__
