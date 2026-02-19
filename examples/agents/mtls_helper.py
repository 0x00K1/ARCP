"""
mTLS Certificate Generator for ARCP Agents.

This module provides client certificate generation for agents that need
to authenticate with ARCP when MTLS_REQUIRED_REMOTE=true.

mTLS binds access tokens to a client's X.509 certificate, providing strong
authentication that complements DPoP.

Usage:
    from mtls_helper import MTLSGenerator

    # Create generator (generates certificate automatically)
    mtls = MTLSGenerator()

    # Get certificate and key for requests
    cert_pem = mtls.get_cert_pem()
    key_pem = mtls.get_key_pem()
    spki_hash = mtls.get_spki_hash()

    # Use with requests library
    import requests
    response = requests.get(
        "https://arcp.example.com/agents",
        cert=(cert_pem, key_pem)
    )

References:
    - RFC 8446: Transport Layer Security (TLS) Version 1.3
    - RFC 5280: Internet X.509 Public Key Infrastructure Certificate
"""

import base64
import hashlib
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

# Use cryptography library for certificate generation
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class MTLSGenerator:
    """
    Generator for mTLS client certificates.

    Creates self-signed X.509 certificates suitable for client authentication
    with ARCP servers. Automatically generates a key pair on initialization.

    Attributes:
        algorithm: Key algorithm (RSA or ECDSA)
        spki_hash: SPKI hash of the public key for token binding
        subject_cn: Common Name in certificate subject
    """

    def __init__(
        self,
        algorithm: str = "RSA",
        key_size: int = 2048,
        subject_cn: str = "ARCP Agent",
        validity_days: int = 365,
        san_dns: Optional[List[str]] = None,
        san_ips: Optional[List[str]] = None,
    ):
        """
        Initialize mTLS generator with a new certificate.

        Args:
            algorithm: Key algorithm (RSA, ECDSA)
            key_size: Key size in bits (for RSA)
            subject_cn: Common Name for the certificate subject
            validity_days: Certificate validity period in days
            san_dns: Subject Alternative Names (DNS)
            san_ips: Subject Alternative Names (IP addresses)
        """
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("cryptography library is required for mTLS support")

        self.algorithm = algorithm
        self.subject_cn = subject_cn
        self.san_dns = san_dns or []
        self.san_ips = san_ips or []

        if algorithm == "RSA":
            self._init_rsa(key_size)
        elif algorithm == "ECDSA":
            self._init_ecdsa()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Generate self-signed certificate
        self._generate_certificate(validity_days)

        # Compute SPKI hash
        self.spki_hash = self._compute_spki_hash()

    def _init_rsa(self, key_size: int):
        """Initialize RSA key pair."""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=key_size, backend=default_backend()
        )
        self._public_key = self._private_key.public_key()

    def _init_ecdsa(self):
        """Initialize ECDSA key pair with P-256 curve."""
        self._private_key = ec.generate_private_key(
            ec.SECP256R1(), backend=default_backend()
        )
        self._public_key = self._private_key.public_key()

    def _generate_certificate(self, validity_days: int):
        """Generate self-signed X.509 certificate."""
        # Create subject and issuer (same for self-signed)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Test"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Test"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ARCP Test"),
                x509.NameAttribute(NameOID.COMMON_NAME, self.subject_cn),
            ]
        )

        # Certificate validity
        now = datetime.now(timezone.utc)
        not_before = now
        not_after = now + timedelta(days=validity_days)

        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(issuer)
        builder = builder.public_key(self._public_key)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(not_before)
        builder = builder.not_valid_after(not_after)

        # Add extensions
        # Basic constraints (not a CA)
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )

        # Key usage (client authentication)
        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )

        # Extended key usage (client authentication)
        builder = builder.add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]
            ),
            critical=True,
        )

        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(self._public_key),
            critical=False,
        )

        # Authority Key Identifier (same as subject for self-signed)
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(self._public_key),
            critical=False,
        )

        # Subject Alternative Names (if provided)
        san_list = []
        for dns_name in self.san_dns:
            san_list.append(x509.DNSName(dns_name))
        for ip_str in self.san_ips:
            try:
                ip_addr = ipaddress.ip_address(ip_str)
                san_list.append(x509.IPAddress(ip_addr))
            except ValueError:
                pass  # Skip invalid IP addresses

        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )

        # Sign the certificate
        self._certificate = builder.sign(
            self._private_key, hashes.SHA256(), backend=default_backend()
        )

    def _compute_spki_hash(self) -> str:
        """
        Compute SPKI (Subject Public Key Info) hash.

        This is used for token binding in mTLS (x5t#S256 claim).

        Returns:
            Base64url-encoded SHA-256 hash of the SPKI
        """
        spki = self._public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashlib.sha256(spki).digest()
        return _base64url_encode(digest)

    def get_cert_pem(self) -> str:
        """
        Get the certificate in PEM format.

        Returns:
            PEM-encoded certificate string
        """
        return self._certificate.public_bytes(serialization.Encoding.PEM).decode()

    def get_key_pem(self) -> str:
        """
        Get the private key in PEM format.

        Returns:
            PEM-encoded private key string
        """
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

    def get_cert_der(self) -> bytes:
        """
        Get the certificate in DER format.

        Returns:
            DER-encoded certificate bytes
        """
        return self._certificate.public_bytes(serialization.Encoding.DER)

    def get_key_der(self) -> bytes:
        """
        Get the private key in DER format.

        Returns:
            DER-encoded private key bytes
        """
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def get_spki_hash(self) -> str:
        """
        Get the SPKI hash for token binding.

        Returns:
            Base64url-encoded SHA-256 hash
        """
        return self.spki_hash

    def get_cert_info(self) -> dict:
        """
        Get certificate information.

        Returns:
            Dictionary with certificate details
        """
        return {
            "subject_cn": self.subject_cn,
            "algorithm": self.algorithm,
            "serial_number": format(self._certificate.serial_number, "x"),
            "not_before": self._certificate.not_valid_before_utc.isoformat(),
            "not_after": self._certificate.not_valid_after_utc.isoformat(),
            "spki_hash": self.spki_hash,
            "issuer_cn": self._certificate.issuer.get_attributes_for_oid(
                NameOID.COMMON_NAME
            )[0].value,
        }

    def save_to_files(self, cert_path: Union[str, Path], key_path: Union[str, Path]):
        """
        Save certificate and key to files.

        Args:
            cert_path: Path to save the certificate PEM file
            key_path: Path to save the private key PEM file
        """
        cert_path = Path(cert_path)
        key_path = Path(key_path)

        # Write certificate
        with open(cert_path, "w") as f:
            f.write(self.get_cert_pem())

        # Write private key
        with open(key_path, "w") as f:
            f.write(self.get_key_pem())

    def get_cert_and_key_pem(self) -> Tuple[str, str]:
        """
        Get both certificate and key in PEM format.

        Convenient for use with requests library.

        Returns:
            Tuple of (cert_pem, key_pem)
        """
        return self.get_cert_pem(), self.get_key_pem()

    def is_valid(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the certificate is currently valid.

        Returns:
            Tuple of (is_valid, error_message)
        """
        now = datetime.now(timezone.utc)

        not_before = self._certificate.not_valid_before_utc
        not_after = self._certificate.not_valid_after_utc

        if not_before > now:
            return (
                False,
                f"Certificate not yet valid (valid from {not_before.isoformat()})",
            )

        if not_after < now:
            return False, f"Certificate expired on {not_after.isoformat()}"

        return True, None


def create_mtls_generator(
    algorithm: str = "RSA",
    subject_cn: str = "ARCP Agent",
    validity_days: int = 365,
) -> MTLSGenerator:
    """
    Create a new mTLS certificate generator.

    Args:
        algorithm: Key algorithm (RSA or ECDSA)
        subject_cn: Common Name for the certificate
        validity_days: Certificate validity in days

    Returns:
        MTLSGenerator instance
    """
    return MTLSGenerator(
        algorithm=algorithm,
        subject_cn=subject_cn,
        validity_days=validity_days,
    )


def get_localhost_ips() -> List[str]:
    """
    Get localhost IP addresses for certificate SAN.

    Returns:
        List of IP addresses
    """
    return ["127.0.0.1", "::1"]


def get_hostname() -> str:
    """
    Get current hostname.

    Returns:
        Hostname string
    """
    return socket.gethostname()


if __name__ == "__main__":
    # Quick test
    print("Testing mTLS Generator...")

    mtls = MTLSGenerator(
        algorithm="RSA",
        subject_cn="Test Agent",
        san_dns=["localhost", get_hostname()],
        san_ips=get_localhost_ips(),
    )

    print(f"SPKI Hash: {mtls.get_spki_hash()}")
    print(f"Certificate Info: {mtls.get_cert_info()}")

    # Test validity
    valid, error = mtls.is_valid()
    print(f"Valid: {valid}")
    if error:
        print(f"Error: {error}")

    # Show PEM formats
    print(f"\nCertificate PEM:\n{mtls.get_cert_pem()}")
    print(f"\nPrivate Key PEM (first 200 chars):\n{mtls.get_key_pem()[:200]}...")
