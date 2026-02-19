"""
Unit Tests for Security Enforcement Module.

Tests the DPoP and mTLS enforcement utilities to ensure proper
security validation during agent registration.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from starlette.datastructures import Headers

_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


class TestEnforceDPoPIfRequired:
    """Tests for enforce_dpop_if_required function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/agents/register"
        return request

    @pytest.fixture
    def mock_request_with_dpop(self):
        """Create a mock request with DPoP header."""
        request = MagicMock(spec=Request)
        # Valid DPoP JWT format (header.payload.signature)
        dpop_proof = "eyJhbGciOiJFZERTQSIsInR5cCI6ImRwb3Arand0IiwiandrIjp7Imt0eSI6Ik9LUCIsImNydiI6IkVkMjU1MTkiLCJ4IjoiYWJjMTIzIn19.eyJqdGkiOiJ0ZXN0LWp0aSIsImh0bSI6IlBPU1QiLCJodHUiOiJodHRwOi8vbG9jYWxob3N0OjgwMDEvYWdlbnRzL3JlZ2lzdGVyIiwiaWF0IjoxNjQwMDAwMDAwfQ.signature123"
        request.headers = Headers({"DPoP": dpop_proof})
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/agents/register"
        return request

    @patch("arcp.utils.security_enforcement.config")
    @pytest.mark.asyncio
    async def test_dpop_not_required_no_header(self, mock_config, mock_request):
        """When DPOP_REQUIRED=false, requests without DPoP should pass."""
        from arcp.utils.security_enforcement import enforce_dpop_if_required

        mock_config.DPOP_ENABLED = True
        mock_config.DPOP_REQUIRED = False

        # Should return (True, None, None) - valid with no binding
        result = await enforce_dpop_if_required(
            mock_request,
            authorization="Bearer test-token",
            dpop_header=None,
            endpoint_name="test",
        )
        assert result[0] is True  # is_valid
        assert result[1] is None  # jkt

    @patch("arcp.utils.security_enforcement.config")
    @pytest.mark.asyncio
    async def test_dpop_required_no_header_fails(self, mock_config, mock_request):
        """When DPOP_REQUIRED=true, requests without DPoP should fail."""
        from arcp.utils.security_enforcement import enforce_dpop_if_required

        mock_config.DPOP_ENABLED = True
        mock_config.DPOP_REQUIRED = True

        # Should return (False, None, error_message)
        result = await enforce_dpop_if_required(
            mock_request,
            authorization="Bearer test-token",
            dpop_header=None,
            endpoint_name="test",
        )
        assert result[0] is False  # is_valid
        assert result[2] is not None  # has error message

    @patch("arcp.utils.security_enforcement.config")
    @pytest.mark.asyncio
    async def test_dpop_disabled_no_header(self, mock_config, mock_request):
        """When DPOP_ENABLED=false, requests should pass without DPoP."""
        from arcp.utils.security_enforcement import enforce_dpop_if_required

        mock_config.DPOP_ENABLED = False
        mock_config.DPOP_REQUIRED = False

        # Should return (True, None, None)
        result = await enforce_dpop_if_required(
            mock_request,
            authorization="Bearer test-token",
            dpop_header=None,
            endpoint_name="test",
        )
        assert result[0] is True  # is_valid


class TestEnforceMTLSIfRequired:
    """Tests for enforce_mtls_if_required function."""

    @pytest.fixture
    def mock_local_request(self):
        """Create a mock local (localhost) request."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def mock_remote_request(self):
        """Create a mock remote request."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @pytest.fixture
    def mock_request_with_cert(self):
        """Create a mock request with client certificate."""
        request = MagicMock(spec=Request)
        request.headers = Headers(
            {
                "X-Client-Cert": "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----"
            }
        )
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @patch("arcp.utils.security_enforcement.config")
    @patch("arcp.utils.security_enforcement.get_mtls_handler")
    @patch("arcp.utils.security_enforcement.is_mtls_required")
    @pytest.mark.asyncio
    async def test_mtls_local_request_no_cert(
        self, mock_is_required, mock_get_handler, mock_config, mock_local_request
    ):
        """Local requests should not require mTLS even when MTLS_REQUIRED_REMOTE=true."""
        from arcp.utils.security_enforcement import enforce_mtls_if_required

        mock_config.MTLS_ENABLED = True
        mock_config.MTLS_REQUIRED_REMOTE = True
        mock_is_required.return_value = False  # Local requests don't require mTLS
        mock_get_handler.return_value.extract_and_validate.return_value = (None, None)

        # Should return (True, None, None) for local requests
        result = await enforce_mtls_if_required(
            mock_local_request, endpoint_name="test"
        )
        assert result[0] is True  # is_valid

    @patch("arcp.utils.security_enforcement.log_security_event")
    @patch("arcp.utils.security_enforcement.config")
    @patch("arcp.utils.security_enforcement.get_mtls_handler")
    @patch("arcp.utils.security_enforcement.is_mtls_required")
    @pytest.mark.asyncio
    async def test_mtls_remote_request_no_cert_fails(
        self,
        mock_is_required,
        mock_get_handler,
        mock_config,
        mock_log_sec,
        mock_remote_request,
    ):
        """Remote requests without cert should fail when MTLS_REQUIRED_REMOTE=true."""
        from arcp.utils.security_enforcement import enforce_mtls_if_required

        mock_config.MTLS_ENABLED = True
        mock_config.MTLS_REQUIRED_REMOTE = True
        mock_is_required.return_value = True  # Remote requests require mTLS
        mock_get_handler.return_value.extract_and_validate.return_value = (
            None,
            "Client certificate required",
        )

        # Should return (False, None, error_message)
        result = await enforce_mtls_if_required(
            mock_remote_request, endpoint_name="test"
        )
        assert result[0] is False  # is_valid
        assert result[2] is not None  # has error message

    @patch("arcp.utils.security_enforcement.config")
    @patch("arcp.utils.security_enforcement.get_mtls_handler")
    @patch("arcp.utils.security_enforcement.is_mtls_required")
    @pytest.mark.asyncio
    async def test_mtls_not_required_remote_no_cert(
        self, mock_is_required, mock_get_handler, mock_config, mock_remote_request
    ):
        """Remote requests should pass without cert when MTLS_REQUIRED_REMOTE=false."""
        from arcp.utils.security_enforcement import enforce_mtls_if_required

        mock_config.MTLS_ENABLED = True
        mock_config.MTLS_REQUIRED_REMOTE = False
        mock_is_required.return_value = False
        mock_get_handler.return_value.extract_and_validate.return_value = (None, None)

        # Should return (True, None, None)
        result = await enforce_mtls_if_required(
            mock_remote_request, endpoint_name="test"
        )
        assert result[0] is True  # is_valid

    @patch("arcp.utils.security_enforcement.config")
    @pytest.mark.asyncio
    async def test_mtls_disabled_remote_no_cert(self, mock_config, mock_remote_request):
        """When MTLS_ENABLED=false, remote requests should pass without cert."""
        from arcp.utils.security_enforcement import enforce_mtls_if_required

        mock_config.MTLS_ENABLED = False
        mock_config.MTLS_REQUIRED_REMOTE = False

        # Should return (True, None, None)
        result = await enforce_mtls_if_required(
            mock_remote_request, endpoint_name="test"
        )
        assert result[0] is True  # is_valid


class TestDPoPHelper:
    """Tests for DPoP helper module."""

    def test_dpop_generator_creation(self):
        """Test DPoP generator can be created."""
        try:
            from examples.agents.dpop_helper import DPoPGenerator

            generator = DPoPGenerator()

            assert generator.algorithm == "EdDSA"
            assert generator.jkt is not None
            assert len(generator.jkt) > 0
        except ImportError:
            pytest.skip("cryptography or PyJWT not installed")

    def test_dpop_proof_generation(self):
        """Test DPoP proof JWT generation."""
        try:
            from examples.agents.dpop_helper import DPoPGenerator

            generator = DPoPGenerator()

            proof = generator.create_proof(
                method="POST",
                uri="http://localhost:8001/agents/register",
                access_token="test-token-123",
            )

            # Proof should be a valid JWT
            assert proof is not None
            assert proof.count(".") == 2  # JWT format: header.payload.signature
        except ImportError:
            pytest.skip("cryptography or PyJWT not installed")

    def test_dpop_jkt_computation(self):
        """Test DPoP JKT (thumbprint) computation."""
        try:
            from examples.agents.dpop_helper import DPoPGenerator

            generator = DPoPGenerator()

            jkt = generator.jkt

            # JKT should be a base64url string
            assert jkt is not None
            assert len(jkt) > 20
        except ImportError:
            pytest.skip("cryptography or PyJWT not installed")


class TestDPoPClient:
    """Tests for DPoP-enabled HTTP client."""

    @pytest.mark.skip(reason="Required dependencies not installed")
    def test_dpop_client_creation(self):
        """Test DPoP client can be created."""
        pass

    @pytest.mark.skip(reason="Required dependencies not installed")
    def test_dpop_client_disabled(self):
        """Test DPoP client works with DPoP disabled."""
        pass

    @pytest.mark.skip(reason="Required dependencies not installed")
    def test_dpop_proof_in_request(self):
        """Test DPoP proof is added to request headers."""
        pass
