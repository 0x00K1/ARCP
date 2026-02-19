"""
Integration tests for Well-Known endpoints.

Tests /.well-known/jwks.json and /.well-known/arcp-configuration endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestWellKnownEndpoints:
    """Integration tests for well-known endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client with well-known routes."""
        from fastapi import FastAPI

        from arcp.api.well_known import router

        app = FastAPI()
        app.include_router(router)

        return TestClient(app)

    @pytest.fixture
    def mock_jwks_service(self):
        """Create a mock JWKS service."""
        mock = MagicMock()
        mock.get_jwks = AsyncMock(
            return_value={
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "kid": "test-key-12345678",
                        "use": "sig",
                        "alg": "EdDSA",
                        "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
                    }
                ]
            }
        )
        mock.get_arcp_configuration = MagicMock(
            return_value={
                "issuer": "urn:arcp:test",
                "jwks_uri": "https://example.com/.well-known/jwks.json",
                "token_endpoint": "https://example.com/auth/agent/token",
                "registration_endpoint": "https://example.com/agents/register",
                "validation_endpoint": "https://example.com/auth/agent/validate_compliance",
                "token_endpoint_auth_methods_supported": ["private_key_jwt", "dpop"],
                "dpop_signing_alg_values_supported": ["EdDSA", "ES256"],
            }
        )
        return mock


class TestJWKSEndpoint:
    """Tests for /.well-known/jwks.json endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi import FastAPI

        from arcp.api.well_known import router

        app = FastAPI()
        app.include_router(router)

        return TestClient(app)

    def test_jwks_endpoint_returns_keys(self, client):
        """Test JWKS endpoint returns keys."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(
                return_value={
                    "keys": [
                        {
                            "kty": "OKP",
                            "crv": "Ed25519",
                            "kid": "key-abc123",
                            "use": "sig",
                            "alg": "EdDSA",
                            "x": "base64url-x-coordinate",
                        }
                    ]
                }
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) == 1
        assert data["keys"][0]["kid"] == "key-abc123"

    def test_jwks_endpoint_cache_headers(self, client):
        """Test JWKS endpoint has appropriate cache headers."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(return_value={"keys": []})
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        # Should have cache control header
        cache_control = response.headers.get("cache-control") or response.headers.get(
            "Cache-Control"
        )
        assert cache_control is not None
        assert "max-age" in cache_control

    def test_jwks_endpoint_content_type(self, client):
        """Test JWKS endpoint returns correct content type."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(return_value={"keys": []})
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_jwks_contains_required_fields(self, client):
        """Test JWKS keys contain all required fields."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(
                return_value={
                    "keys": [
                        {
                            "kty": "OKP",
                            "crv": "Ed25519",
                            "kid": "test-key",
                            "use": "sig",
                            "alg": "EdDSA",
                            "x": "test-x-coordinate",
                        }
                    ]
                }
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        key = response.json()["keys"][0]

        # RFC 7517 required fields
        assert "kty" in key
        assert "kid" in key

        # Recommended fields
        assert "use" in key
        assert "alg" in key

    def test_jwks_no_private_key(self, client):
        """Test JWKS does not expose private key components."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(
                return_value={
                    "keys": [
                        {
                            "kty": "OKP",
                            "crv": "Ed25519",
                            "kid": "test-key",
                            "use": "sig",
                            "alg": "EdDSA",
                            "x": "public-x",
                            # d should NOT be present
                        }
                    ]
                }
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        key = response.json()["keys"][0]

        # Private key component must NOT be present
        assert "d" not in key


class TestARCPConfigurationEndpoint:
    """Tests for /.well-known/arcp-configuration endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi import FastAPI

        from arcp.api.well_known import router

        app = FastAPI()
        app.include_router(router)

        return TestClient(app)

    def test_config_endpoint_returns_metadata(self, client):
        """Test configuration endpoint returns metadata."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_arcp_configuration = MagicMock(
                return_value={
                    "issuer": "urn:arcp:test",
                    "jwks_uri": "https://example.com/.well-known/jwks.json",
                    "token_endpoint": "https://example.com/auth/agent/token",
                }
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/arcp-configuration")

        assert response.status_code == 200
        data = response.json()
        assert "issuer" in data

    def test_config_endpoint_jwks_uri(self, client):
        """Test configuration includes JWKS URI."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_arcp_configuration.return_value = {
                "issuer": "urn:arcp:test",
                "jwks_uri": "https://example.com/.well-known/jwks.json",
            }
            mock_get.return_value = mock_service

            response = client.get("/.well-known/arcp-configuration")

        data = response.json()
        assert "jwks_uri" in data
        assert "jwks.json" in data["jwks_uri"]

    def test_config_endpoint_dpop_support(self, client):
        """Test configuration advertises DPoP support."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_arcp_configuration.return_value = {
                "issuer": "urn:arcp:test",
                "token_endpoint_auth_methods_supported": ["dpop"],
                "dpop_signing_alg_values_supported": ["EdDSA", "ES256"],
            }
            mock_get.return_value = mock_service

            response = client.get("/.well-known/arcp-configuration")

        data = response.json()
        assert "dpop_signing_alg_values_supported" in data
        assert "EdDSA" in data["dpop_signing_alg_values_supported"]

    def test_config_endpoint_tpr_endpoints(self, client):
        """Test configuration includes TPR endpoints."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_arcp_configuration.return_value = {
                "issuer": "urn:arcp:test",
                "token_endpoint": "https://example.com/auth/agent/token",
                "registration_endpoint": "https://example.com/agents/register",
                "validation_endpoint": "https://example.com/auth/agent/validate_compliance",
            }
            mock_get.return_value = mock_service

            response = client.get("/.well-known/arcp-configuration")

        data = response.json()
        assert "token_endpoint" in data
        assert "registration_endpoint" in data
        assert "validation_endpoint" in data


class TestWellKnownCORS:
    """Tests for CORS support on well-known endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        from arcp.api.well_known import router

        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.include_router(router)

        return TestClient(app)

    def test_jwks_cors_preflight(self, client):
        """Test JWKS endpoint handles CORS preflight."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(return_value={"keys": []})
            mock_get.return_value = mock_service

            response = client.options(
                "/.well-known/jwks.json",
                headers={
                    "Origin": "https://client.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

        # Should allow the request
        assert response.status_code in [200, 204]


class TestWellKnownErrorHandling:
    """Tests for error handling in well-known endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client with raise_server_exceptions=False."""
        from fastapi import FastAPI

        from arcp.api.well_known import router

        app = FastAPI()
        app.include_router(router)

        return TestClient(app, raise_server_exceptions=False)

    def test_jwks_service_error(self, client):
        """Test JWKS endpoint handles service errors gracefully."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_jwks = AsyncMock(
                side_effect=Exception("Service unavailable")
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/jwks.json")

        # Should return error response, not crash
        assert response.status_code >= 400

    def test_config_service_error(self, client):
        """Test configuration endpoint handles service errors gracefully."""
        with patch("arcp.api.well_known.get_jwks_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_arcp_configuration = MagicMock(
                side_effect=Exception("Service error")
            )
            mock_get.return_value = mock_service

            response = client.get("/.well-known/arcp-configuration")

        # Should return error response, not crash
        assert response.status_code >= 400
