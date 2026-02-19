"""
mTLS-enabled ARCP Client Extension.

This module extends the ARCP client to support mTLS (Mutual TLS) client
certificate authentication for agents that need to authenticate with ARCP
when MTLS_REQUIRED_REMOTE=true.

Usage:
    from mtls_client import MTLSARCPClient

    # Use instead of regular ARCPClient
    client = MTLSARCPClient("https://arcp.example.com")

    # All methods automatically include client certificate
    agent = await client.register_agent(
        agent_id="my-agent",
        ...
    )
"""

import logging

# Import original client
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from mtls_helper import MTLSGenerator

_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from arcp import ARCPClient  # noqa: E402

logger = logging.getLogger(__name__)


class MTLSARCPClient(ARCPClient):
    """
    ARCP Client with mTLS client certificate support.

    Extends the standard ARCPClient to automatically include client
    certificates in all requests. This is required when the ARCP server
    has MTLS_REQUIRED_REMOTE=true.
    """

    def __init__(
        self,
        base_url: str,
        mtls_enabled: bool = True,
        cert_path: Optional[Union[str, Path]] = None,
        key_path: Optional[Union[str, Path]] = None,
        cert_pem: Optional[str] = None,
        key_pem: Optional[str] = None,
        mtls_generator: Optional[MTLSGenerator] = None,
        algorithm: str = "RSA",
        subject_cn: str = "ARCP Agent",
        verify_ssl: bool = False,  # Default to False for development
        **kwargs,
    ):
        """
        Initialize mTLS-enabled ARCP client.

        Args:
            base_url: Base URL of the ARCP server
            mtls_enabled: Whether to use client certificates (default: True)
            cert_path: Path to certificate PEM file
            key_path: Path to private key PEM file
            cert_pem: Certificate PEM content (alternative to cert_path)
            key_pem: Private key PEM content (alternative to key_path)
            mtls_generator: Existing MTLSGenerator instance
            algorithm: Algorithm for auto-generated certificate (RSA, ECDSA)
            subject_cn: Common Name for auto-generated certificate
            verify_ssl: Whether to verify SSL certificates (default: False for development)
            **kwargs: Additional arguments passed to ARCPClient
        """
        super().__init__(base_url, **kwargs)

        self.mtls_enabled = mtls_enabled
        self.verify_ssl = verify_ssl
        self._cert_files: Optional[Tuple[str, str]] = None
        self._temp_cert_file = None
        self._temp_key_file = None

        if not mtls_enabled:
            logger.info("mTLS disabled")
            return

        # Option 1: Use existing MTLSGenerator
        if mtls_generator:
            self._setup_from_generator(mtls_generator)
            logger.info(
                f"mTLS enabled with generator: SPKI={mtls_generator.get_spki_hash()[:16]}..."
            )

        # Option 2: Use provided file paths
        elif cert_path and key_path:
            self._setup_from_files(cert_path, key_path)
            logger.info(f"mTLS enabled with files: {cert_path}, {key_path}")

        # Option 3: Use provided PEM content
        elif cert_pem and key_pem:
            self._setup_from_pem(cert_pem, key_pem)
            logger.info("mTLS enabled with PEM content")

        # Option 4: Generate new certificate
        else:
            generator = MTLSGenerator(
                algorithm=algorithm,
                subject_cn=subject_cn,
                san_dns=["localhost"],
                san_ips=["127.0.0.1", "::1"],
            )
            self._setup_from_generator(generator)
            logger.info(
                f"mTLS enabled with auto-generated cert: SPKI={generator.get_spki_hash()[:16]}..."
            )

    def _setup_from_generator(self, generator: MTLSGenerator):
        """Setup mTLS from an MTLSGenerator instance."""
        # Create temporary files for the certificate and key
        self._temp_cert_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )
        self._temp_key_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )

        # Write certificate and key
        self._temp_cert_file.write(generator.get_cert_pem())
        self._temp_cert_file.close()

        self._temp_key_file.write(generator.get_key_pem())
        self._temp_key_file.close()

        self._cert_files = (self._temp_cert_file.name, self._temp_key_file.name)
        self._mtls_generator = generator

    def _setup_from_files(
        self, cert_path: Union[str, Path], key_path: Union[str, Path]
    ):
        """Setup mTLS from existing certificate files."""
        cert_path = Path(cert_path)
        key_path = Path(key_path)

        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {cert_path}")
        if not key_path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")

        self._cert_files = (str(cert_path), str(key_path))
        self._mtls_generator = None

    def _setup_from_pem(self, cert_pem: str, key_pem: str):
        """Setup mTLS from PEM content strings."""
        # Create temporary files for the PEM content
        self._temp_cert_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )
        self._temp_key_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )

        # Write PEM content
        self._temp_cert_file.write(cert_pem)
        self._temp_cert_file.close()

        self._temp_key_file.write(key_pem)
        self._temp_key_file.close()

        self._cert_files = (self._temp_cert_file.name, self._temp_key_file.name)
        self._mtls_generator = None

    def get_mtls_spki(self) -> Optional[str]:
        """
        Get the SPKI hash of the mTLS client certificate.

        Returns:
            SPKI hash string if mTLS is enabled, None otherwise
        """
        if self._mtls_generator:
            return self._mtls_generator.get_spki_hash()
        return None

    def get_cert_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the client certificate.

        Returns:
            Certificate information dict if available, None otherwise
        """
        if self._mtls_generator:
            return self._mtls_generator.get_cert_info()
        return None

    async def _ensure_client(self):
        """Ensure HTTP client is initialized with mTLS certificate."""
        if self._client is None:
            import httpx

            # Build client kwargs
            client_kwargs = {
                "timeout": httpx.Timeout(self.timeout),
                "headers": {
                    "User-Agent": self.user_agent,
                    "X-Client-Fingerprint": self._client_fingerprint,
                },
                "verify": self.verify_ssl,  # Control SSL verification
            }

            # Add mTLS certificate if available
            if self.mtls_enabled and self._cert_files:
                client_kwargs["cert"] = self._cert_files

            self._client = httpx.AsyncClient(**client_kwargs)

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_required: bool = True,
        public_api: bool = False,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with client certificate if mTLS is enabled.

        Overrides the base _request method to inject client certificates.
        """
        # Ensure client is created with mTLS support
        await self._ensure_client()

        return await super()._request(
            method=method,
            endpoint=endpoint,
            json_data=json_data,
            params=params,
            headers=headers,
            auth_required=auth_required,
            public_api=public_api,
        )

    async def close(self):
        """
        Clean up resources including temporary certificate files.
        """
        # Clean up temporary files if created
        if self._temp_cert_file:
            try:
                Path(self._temp_cert_file.name).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up temp cert file: {e}")

        if self._temp_key_file:
            try:
                Path(self._temp_key_file.name).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up temp key file: {e}")

        # Call parent cleanup
        await super().close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class DualAuthARCPClient(ARCPClient):
    """
    ARCP Client with both DPoP and mTLS support.

    Combines DPoP proof generation and mTLS client certificate authentication
    for maximum security when both are enabled on the server.
    """

    def __init__(
        self,
        base_url: str,
        dpop_enabled: bool = True,
        mtls_enabled: bool = True,
        dpop_algorithm: str = "EdDSA",
        mtls_algorithm: str = "RSA",
        cert_path: Optional[Union[str, Path]] = None,
        key_path: Optional[Union[str, Path]] = None,
        verify_ssl: bool = False,  # Default to False for development
        **kwargs,
    ):
        """
        Initialize client with both DPoP and mTLS support.

        Args:
            base_url: Base URL of the ARCP server
            dpop_enabled: Whether to generate DPoP proofs
            mtls_enabled: Whether to use client certificates
            dpop_algorithm: DPoP signing algorithm (EdDSA, ES256)
            mtls_algorithm: mTLS key algorithm (RSA, ECDSA)
            cert_path: Path to certificate file (if not auto-generated)
            key_path: Path to key file (if not auto-generated)
            verify_ssl: Whether to verify SSL certificates (default: False for development)
            **kwargs: Additional arguments passed to ARCPClient
        """
        super().__init__(base_url, **kwargs)

        # Store SSL verification setting
        self.verify_ssl = verify_ssl

        # Initialize DPoP if enabled
        self.dpop_enabled = dpop_enabled
        self._dpop_generator: Optional[Any] = None
        if dpop_enabled:
            try:
                from dpop_helper import DPoPGenerator

                self._dpop_generator = DPoPGenerator(algorithm=dpop_algorithm)
                logger.info(f"DPoP enabled: jkt={self._dpop_generator.jkt[:16]}...")
            except ImportError:
                logger.warning("DPoP requested but dpop_helper not available")
                self.dpop_enabled = False

        # Initialize mTLS if enabled
        self.mtls_enabled = mtls_enabled
        self._mtls_generator: Optional[MTLSGenerator] = None
        self._cert_files: Optional[Tuple[str, str]] = None
        self._spki_hash: Optional[str] = None

        if mtls_enabled:
            if cert_path and key_path:
                # Use existing files
                self._cert_files = (str(cert_path), str(key_path))
                # Manually load certificate for SPKI computation
                try:
                    import base64
                    from pathlib import Path

                    from cryptography import x509
                    from cryptography.hazmat.primitives import hashes, serialization

                    cert_data = Path(cert_path).read_bytes()
                    cert = x509.load_pem_x509_certificate(cert_data)

                    # Get SPKI and compute SHA-256 hash
                    spki_bytes = cert.public_key().public_bytes(
                        encoding=serialization.Encoding.DER,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    digest = hashes.Hash(hashes.SHA256())
                    digest.update(spki_bytes)
                    spki_hash = (
                        base64.urlsafe_b64encode(digest.finalize())
                        .decode("utf-8")
                        .rstrip("=")
                    )

                    # Store for get_mtls_spki method
                    self._spki_hash = spki_hash
                    logger.info(f"mTLS enabled: spki={spki_hash[:16]}...")
                except Exception as e:
                    logger.warning(f"Could not compute SPKI hash from certificate: {e}")
                    self._spki_hash = None
                    logger.info("mTLS enabled: spki=unknown...")
            else:
                # Generate new certificate
                self._mtls_generator = MTLSGenerator(
                    algorithm=mtls_algorithm,
                    subject_cn="ARCP Dual Auth Agent",
                    san_dns=["localhost"],
                    san_ips=["127.0.0.1"],
                )

                # Create temporary files
                import tempfile

                self._temp_cert_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".pem", delete=False
                )
                self._temp_key_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".pem", delete=False
                )

                self._temp_cert_file.write(self._mtls_generator.get_cert_pem())
                self._temp_cert_file.close()

                self._temp_key_file.write(self._mtls_generator.get_key_pem())
                self._temp_key_file.close()

                self._cert_files = (self._temp_cert_file.name, self._temp_key_file.name)

            logger.info(
                f"mTLS enabled: spki={self.get_mtls_spki()[:16] if self.get_mtls_spki() else 'unknown'}..."
            )

    def get_dpop_jkt(self) -> Optional[str]:
        """Get DPoP JWK Thumbprint."""
        if self._dpop_generator:
            return self._dpop_generator.jkt
        return None

    def get_mtls_spki(self) -> Optional[str]:
        """Get mTLS SPKI hash."""
        if self._mtls_generator:
            return self._mtls_generator.get_spki_hash()
        elif hasattr(self, "_spki_hash"):
            return self._spki_hash
        return None

    def _generate_dpop_proof(
        self,
        method: str,
        url: str,
        access_token: Optional[str] = None,
    ) -> Optional[str]:
        """Generate DPoP proof for a request."""
        if not self.dpop_enabled or not self._dpop_generator:
            return None

        try:
            return self._dpop_generator.create_proof(
                method=method,
                uri=url,
                access_token=access_token,
            )
        except Exception as e:
            logger.warning(f"Failed to generate DPoP proof: {e}")
            return None

    async def _ensure_client(self):
        """Ensure HTTP client is initialized with mTLS certificate."""
        if self._client is None:
            import httpx

            # Build client kwargs
            client_kwargs = {
                "timeout": httpx.Timeout(self.timeout),
                "headers": {
                    "User-Agent": self.user_agent,
                    "X-Client-Fingerprint": self._client_fingerprint,
                },
                "verify": self.verify_ssl,  # Control SSL verification
            }

            # Add mTLS certificate if available
            if self.mtls_enabled and self._cert_files:
                client_kwargs["cert"] = self._cert_files

            self._client = httpx.AsyncClient(**client_kwargs)

    async def _request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """Make request with both DPoP and mTLS if enabled."""
        headers = headers or {}

        # Add DPoP proof if enabled
        if self.dpop_enabled:
            full_url = f"{self.base_url}{endpoint}"
            auth_header = headers.get("Authorization")
            access_token = None
            if auth_header and auth_header.startswith("Bearer "):
                access_token = auth_header[7:]  # Remove 'Bearer ' prefix

            dpop_proof = self._generate_dpop_proof(
                method=method.upper(),
                url=full_url,
                access_token=access_token,
            )
            if dpop_proof:
                headers["DPoP"] = dpop_proof

        # Ensure client is created with mTLS support
        await self._ensure_client()

        # Convert to base class parameters and call ARCPClient._request directly
        return await ARCPClient._request(
            self,
            method=method,
            endpoint=endpoint,
            json_data=json_data,
            headers=headers,
            auth_required=kwargs.get("auth_required", True),
            public_api=kwargs.get("public_api", False),
            params=kwargs.get("params"),
        )


# Convenience functions
def create_mtls_client(
    base_url: str,
    algorithm: str = "RSA",
    subject_cn: str = "ARCP Agent",
) -> MTLSARCPClient:
    """
    Create a new mTLS-enabled ARCP client.

    Args:
        base_url: ARCP server URL
        algorithm: Certificate key algorithm
        subject_cn: Certificate common name

    Returns:
        MTLSARCPClient instance
    """
    return MTLSARCPClient(
        base_url=base_url,
        algorithm=algorithm,
        subject_cn=subject_cn,
    )


def create_dual_auth_client(
    base_url: str,
    dpop_algorithm: str = "EdDSA",
    mtls_algorithm: str = "RSA",
) -> DualAuthARCPClient:
    """
    Create a client with both DPoP and mTLS enabled.

    Args:
        base_url: ARCP server URL
        dpop_algorithm: DPoP signing algorithm
        mtls_algorithm: mTLS certificate algorithm

    Returns:
        DualAuthARCPClient instance
    """
    return DualAuthARCPClient(
        base_url=base_url,
        dpop_algorithm=dpop_algorithm,
        mtls_algorithm=mtls_algorithm,
    )


if __name__ == "__main__":
    import asyncio

    async def test_mtls_client():
        """Test the mTLS client functionality."""
        print("Testing mTLS Client...")

        # Create client with auto-generated certificate
        async with MTLSARCPClient("http://localhost:8001") as client:
            print(f"SPKI Hash: {client.get_mtls_spki()}")
            print(f"Cert Info: {client.get_cert_info()}")

            # Test basic connectivity (will fail if server not running, but shows structure)
            try:
                result = await client.get_public_info()
                print(f"Server response: {result}")
            except Exception as e:
                print(f"Connection failed (expected if server not running): {e}")

    asyncio.run(test_mtls_client())
