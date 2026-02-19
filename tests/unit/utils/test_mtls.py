"""
Unit tests for mTLS Handler.

Tests client certificate extraction and SPKI computation.
"""

import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest

from arcp.utils.mtls import (
    ClientCertificate,
    MTLSHandler,
    extract_client_cert,
    get_mtls_handler,
    parse_certificate,
)


def generate_test_certificate(cn: str = "test-agent", days_valid: int = 365):
    """Helper to generate a test certificate."""
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    # Generate key pair
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Create self-signed certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    pem_data = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return pem_data, cert, private_key


class TestClientCertificate:
    """Tests for ClientCertificate dataclass."""

    def test_create_client_certificate(self):
        """Test creating a ClientCertificate instance."""
        mock_cert = MagicMock()

        cert = ClientCertificate(
            cert=mock_cert,
            raw_pem="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
            spki_hash="base64url-encoded-hash",
            subject_cn="test-agent",
            issuer_cn="test-ca",
            serial_number="123456",
            not_before=datetime.now(timezone.utc) - timedelta(days=1),
            not_after=datetime.now(timezone.utc) + timedelta(days=365),
        )

        assert cert.subject_cn == "test-agent"
        assert cert.issuer_cn == "test-ca"
        assert cert.spki_hash == "base64url-encoded-hash"

    def test_is_valid_current_cert(self):
        """Test is_valid returns True for current certificate."""
        mock_cert = MagicMock()
        mock_cert.extensions = MagicMock()
        mock_cert.extensions.get_extension_for_oid = MagicMock(
            side_effect=Exception("No EKU")
        )

        cert = ClientCertificate(
            cert=mock_cert,
            raw_pem="pem",
            spki_hash="hash",
            subject_cn="test",
            issuer_cn="ca",
            serial_number="1",
            not_before=datetime.now(timezone.utc) - timedelta(days=1),
            not_after=datetime.now(timezone.utc) + timedelta(days=364),
        )

        valid, error = cert.is_valid()
        assert valid is True
        assert error is None

    def test_is_valid_expired_cert(self):
        """Test is_valid returns False for expired certificate."""
        mock_cert = MagicMock()

        cert = ClientCertificate(
            cert=mock_cert,
            raw_pem="pem",
            spki_hash="hash",
            subject_cn="test",
            issuer_cn="ca",
            serial_number="1",
            not_before=datetime.now(timezone.utc) - timedelta(days=400),
            not_after=datetime.now(timezone.utc) - timedelta(days=35),  # Expired
        )

        valid, error = cert.is_valid()
        assert valid is False
        assert "expired" in error.lower()

    def test_is_valid_not_yet_valid_cert(self):
        """Test is_valid returns False for not-yet-valid certificate."""
        mock_cert = MagicMock()

        cert = ClientCertificate(
            cert=mock_cert,
            raw_pem="pem",
            spki_hash="hash",
            subject_cn="test",
            issuer_cn="ca",
            serial_number="1",
            not_before=datetime.now(timezone.utc) + timedelta(days=1),  # Future
            not_after=datetime.now(timezone.utc) + timedelta(days=365),
        )

        valid, error = cert.is_valid()
        assert valid is False
        assert "not yet valid" in error.lower()


class TestParseCertificate:
    """Tests for parse_certificate function."""

    def test_parse_pem_certificate(self):
        """Test parsing a PEM certificate."""
        pem_data, _, _ = generate_test_certificate("pem-test-agent")

        client_cert = parse_certificate(pem_data)

        assert client_cert is not None
        assert client_cert.subject_cn == "pem-test-agent"
        assert client_cert.spki_hash is not None
        assert len(client_cert.spki_hash) > 20  # Base64url SHA-256

    def test_parse_url_encoded_certificate(self):
        """Test parsing a URL-encoded PEM certificate."""
        pem_data, _, _ = generate_test_certificate("url-encoded-agent")
        url_encoded = quote(pem_data, safe="")

        client_cert = parse_certificate(url_encoded)

        assert client_cert is not None
        assert client_cert.subject_cn == "url-encoded-agent"

    def test_parse_der_certificate(self):
        """Test parsing a DER (base64) certificate."""
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        # Generate certificate
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "der-agent"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=365))
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        der_data = cert.public_bytes(serialization.Encoding.DER)
        base64_der = base64.b64encode(der_data).decode("utf-8")

        client_cert = parse_certificate(base64_der)

        assert client_cert is not None
        assert client_cert.subject_cn == "der-agent"

    def test_parse_invalid_certificate(self):
        """Test parsing invalid certificate data."""
        result = parse_certificate("not a valid certificate")
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_certificate("")
        assert result is None


class TestMTLSHandler:
    """Tests for MTLSHandler class."""

    @pytest.fixture
    def handler(self):
        """Create an MTLSHandler for testing."""
        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = True
            mock_config.MTLS_REQUIRED_REMOTE = True
            mock_config.MTLS_VERIFY_CHAIN = False
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"
            yield MTLSHandler()

    def test_initialization(self, handler):
        """Test MTLSHandler initializes correctly."""
        assert handler.enabled is True
        assert handler.required_remote is True
        assert handler.verify_chain is False

    def test_extract_and_validate_disabled(self):
        """Test extraction when mTLS is disabled."""
        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = False
            mock_config.MTLS_REQUIRED_REMOTE = False
            mock_config.MTLS_VERIFY_CHAIN = False
            handler = MTLSHandler()

        mock_request = MagicMock()
        cert, error = handler.extract_and_validate(mock_request)
        assert cert is None
        assert error is None

    def test_get_spki_returns_none_when_no_cert(self, handler):
        """Test get_spki returns None when no certificate."""
        mock_request = MagicMock()

        with patch("arcp.utils.mtls.extract_client_cert", return_value=None):
            with patch("arcp.utils.mtls.is_mtls_required", return_value=False):
                spki = handler.get_spki(mock_request)

        assert spki is None

    def test_get_spki_returns_hash_when_valid_cert(self, handler):
        """Test get_spki returns hash when valid certificate."""
        mock_request = MagicMock()
        mock_cert = MagicMock()
        mock_cert.spki_hash = "test-spki-hash-base64url"
        mock_cert.is_valid.return_value = (True, None)

        with patch("arcp.utils.mtls.extract_client_cert", return_value=mock_cert):
            spki = handler.get_spki(mock_request)

        assert spki == "test-spki-hash-base64url"

    def test_extract_and_validate_returns_error_on_invalid_cert(self, handler):
        """Test extraction returns error when certificate is invalid."""
        mock_request = MagicMock()
        mock_cert = MagicMock()
        mock_cert.is_valid.return_value = (False, "Certificate expired")

        with patch("arcp.utils.mtls.extract_client_cert", return_value=mock_cert):
            cert, error = handler.extract_and_validate(mock_request)

        assert cert is None
        assert error == "Certificate expired"


class TestSpkiHashConsistency:
    """Tests for SPKI hash computation consistency."""

    def test_same_cert_same_spki(self):
        """Test that parsing same cert produces same SPKI hash."""
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        # Generate certificate
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "spki-test"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=365))
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        pem_data = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        # Parse same cert twice
        client_cert1 = parse_certificate(pem_data)
        client_cert2 = parse_certificate(pem_data)

        # SPKI hash should be consistent
        assert client_cert1.spki_hash == client_cert2.spki_hash

    def test_different_certs_different_spki(self):
        """Test that different certificates have different SPKI hashes."""
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        certs = []
        for i in range(2):
            private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            subject = issuer = x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, f"agent-{i}"),
                ]
            )

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
            certs.append(parse_certificate(pem))

        # Different keys = different SPKI hashes
        assert certs[0].spki_hash != certs[1].spki_hash


class TestExtractClientCert:
    """Tests for extract_client_cert function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"  # Remote client
        return request

    @pytest.fixture
    def valid_cert_pem(self):
        """Generate a valid PEM certificate for testing."""
        pem_data, _, _ = generate_test_certificate("test-client")
        return pem_data

    def test_extract_from_default_header(self, mock_request, valid_cert_pem):
        """Test extracting certificate from default header."""
        mock_request.headers = {"X-Client-Cert": valid_cert_pem}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            cert = extract_client_cert(mock_request)

        assert cert is not None
        assert cert.subject_cn == "test-client"

    def test_extract_from_url_encoded_header(self, mock_request, valid_cert_pem):
        """Test extracting URL-encoded certificate from header."""
        mock_request.headers = {"X-Client-Cert": quote(valid_cert_pem, safe="")}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            cert = extract_client_cert(mock_request)

        assert cert is not None
        assert cert.subject_cn == "test-client"

    def test_extract_no_header(self, mock_request):
        """Test extract returns None when no certificate header."""
        mock_request.headers = {}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            cert = extract_client_cert(mock_request)

        assert cert is None

    def test_extract_invalid_cert(self, mock_request):
        """Test extract returns None for invalid certificate."""
        mock_request.headers = {"X-Client-Cert": "invalid-cert-data"}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            cert = extract_client_cert(mock_request)

        assert cert is None

    def test_extract_fallback_headers(self, mock_request, valid_cert_pem):
        """Test fallback to other header names."""
        mock_request.headers = {"X-SSL-Client-Cert": valid_cert_pem}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"  # Not present

            cert = extract_client_cert(mock_request)

        assert cert is not None


class TestGetMTLSHandler:
    """Tests for get_mtls_handler singleton."""

    def test_returns_handler(self):
        """Test get_mtls_handler returns an MTLSHandler."""
        with patch("arcp.utils.mtls._mtls_handler", None):
            with patch("arcp.utils.mtls.config") as mock_config:
                mock_config.MTLS_ENABLED = True
                mock_config.MTLS_REQUIRED_REMOTE = True
                mock_config.MTLS_VERIFY_CHAIN = False

                handler = get_mtls_handler()
                assert isinstance(handler, MTLSHandler)

    def test_returns_same_instance(self):
        """Test get_mtls_handler returns the same instance."""
        with patch("arcp.utils.mtls._mtls_handler", None):
            with patch("arcp.utils.mtls.config") as mock_config:
                mock_config.MTLS_ENABLED = True
                mock_config.MTLS_REQUIRED_REMOTE = True
                mock_config.MTLS_VERIFY_CHAIN = False

                h1 = get_mtls_handler()
                h2 = get_mtls_handler()
                assert h1 is h2


class TestMTLSHandlerExtractAndValidate:
    """Tests for MTLSHandler.extract_and_validate method."""

    @pytest.fixture
    def handler(self):
        """Create an MTLSHandler for testing."""
        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = True
            mock_config.MTLS_REQUIRED_REMOTE = True
            mock_config.MTLS_VERIFY_CHAIN = False
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"
            yield MTLSHandler()

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"  # Remote client
        return request

    def test_extract_valid_cert(self, handler, mock_request):
        """Test extracting and validating a valid certificate."""
        pem_data, _, _ = generate_test_certificate("valid-agent")
        mock_request.headers = {"X-Client-Cert": pem_data}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = True
            mock_config.MTLS_REQUIRED_REMOTE = True
            mock_config.MTLS_VERIFY_CHAIN = False
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            cert, error = handler.extract_and_validate(mock_request)

        assert cert is not None
        assert error is None
        assert cert.subject_cn == "valid-agent"

    def test_disabled_mtls_returns_none(self, mock_request):
        """Test disabled mTLS returns None without error."""
        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = False
            mock_config.MTLS_REQUIRED_REMOTE = True
            mock_config.MTLS_VERIFY_CHAIN = False

            handler = MTLSHandler()
            cert, error = handler.extract_and_validate(mock_request)

        assert cert is None
        assert error is None

    def test_get_spki_from_request(self, handler, mock_request):
        """Test getting SPKI hash from request."""
        pem_data, _, _ = generate_test_certificate("spki-agent")
        mock_request.headers = {"X-Client-Cert": pem_data}

        with patch("arcp.utils.mtls.config") as mock_config:
            mock_config.MTLS_ENABLED = True
            mock_config.MTLS_REQUIRED_REMOTE = True
            mock_config.MTLS_VERIFY_CHAIN = False
            mock_config.MTLS_CERT_HEADER = "X-Client-Cert"

            spki = handler.get_spki(mock_request)

        assert spki is not None
        assert len(spki) > 20  # Base64url SHA-256
