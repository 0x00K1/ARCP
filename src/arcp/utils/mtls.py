"""
mTLS (Mutual TLS) Client Certificate Handler.

Extracts and validates client certificates from reverse proxy headers,
computing SPKI (Subject Public Key Info) for token binding.

mTLS binds tokens to a client's X.509 certificate, providing strong
authentication that complements DPoP.

Features:
- Certificate extraction from proxy headers
- Multiple header format support (Nginx, Apache, Envoy)
- SPKI computation (SHA-256 hash of SubjectPublicKeyInfo)
- Certificate validation (expiry, key usage)
- Optional chain verification

Environment Variables:
    MTLS_ENABLED: Enable mTLS binding (default: false)
    MTLS_REQUIRED_REMOTE: Require for remote agents (default: true)
    MTLS_CERT_HEADER: Header from proxy (default: X-Client-Cert)
    MTLS_VERIFY_CHAIN: Verify cert chain (default: false)
    MTLS_CA_BUNDLE: Path to CA bundle for chain verification

Example Usage:
    >>> from arcp.utils.mtls import extract_client_cert
    >>> cert = extract_client_cert(request)
    >>> if cert:
    ...     print(f"SPKI: {cert.spki_hash}")
    ...     print(f"Subject: {cert.subject_cn}")
"""

import base64
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import unquote

import aiohttp
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp
from cryptography.x509.oid import (
    AuthorityInformationAccessOID,
    ExtendedKeyUsageOID,
    ExtensionOID,
    NameOID,
)
from cryptography.x509.verification import PolicyBuilder, Store
from fastapi import Request

from ..core.config import config

logger = logging.getLogger(__name__)

# Headers to check for client certificate (in order of preference)
CERT_HEADERS = [
    "X-Client-Cert",  # Nginx: $ssl_client_escaped_cert
    "X-SSL-Client-Cert",  # Apache
    "X-Forwarded-Client-Cert",  # Envoy (XFCC format)
    "X-Client-Certificate",  # Generic
]


@dataclass
class ClientCertificate:
    """
    Parsed client certificate data.

    Contains the certificate object and computed values for binding.
    """

    # Raw certificate object (cryptography.x509.Certificate)
    cert: object

    # PEM-encoded certificate string
    raw_pem: str

    # Base64url SHA-256 hash of SubjectPublicKeyInfo
    spki_hash: str

    # Subject Common Name (if present)
    subject_cn: Optional[str] = None

    # Subject Alternative Names (if present)
    sans: Optional[List[str]] = None

    # Certificate serial number as hex string
    serial_number: Optional[str] = None

    # Issuer Common Name (if present)
    issuer_cn: Optional[str] = None

    # Validity dates
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None

    def is_valid(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the certificate.

        Checks:
        - Not before current date
        - Not after current date (not expired)
        - Key usage allows client authentication (if extension present)

        Returns:
            Tuple of (is_valid, error_message)
        """
        now = datetime.now(timezone.utc)

        if self.not_before and self.not_before > now:
            return (
                False,
                f"Certificate not yet valid (valid from {self.not_before.isoformat()})",
            )

        if self.not_after and self.not_after < now:
            return False, f"Certificate expired on {self.not_after.isoformat()}"

        # Check extended key usage if available
        try:
            try:
                eku_ext = self.cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
                )
                usages = eku_ext.value

                # Check for client authentication
                if ExtendedKeyUsageOID.CLIENT_AUTH not in usages:
                    return False, "Certificate not authorized for client authentication"
            except x509.ExtensionNotFound:
                # No EKU extension - allow (many certs don't have it)
                pass
        except Exception as e:
            logger.warning(f"Could not check certificate key usage: {e}")

        return True, None

    def __repr__(self) -> str:
        return f"ClientCertificate(cn={self.subject_cn}, spki={self.spki_hash[:16]}...)"


def parse_certificate(cert_data: str) -> Optional[ClientCertificate]:
    """
    Parse a certificate from PEM or DER format.

    Args:
        cert_data: Certificate data (PEM, DER, or URL-encoded PEM)

    Returns:
        ClientCertificate or None if parsing fails
    """
    try:
        cert = None
        pem_data = None

        # Try URL-decoded PEM first (most common from Nginx)
        decoded = unquote(cert_data)

        if decoded.startswith("-----BEGIN"):
            # PEM format
            pem_data = decoded
            try:
                cert = x509.load_pem_x509_certificate(
                    pem_data.encode(), default_backend()
                )
            except Exception as e:
                logger.debug(f"Failed to parse as PEM: {e}")

        if cert is None:
            # Try DER format (base64 encoded)
            try:
                der_data = base64.b64decode(cert_data)
                cert = x509.load_der_x509_certificate(der_data, default_backend())
                pem_data = cert.public_bytes(serialization.Encoding.PEM).decode()
            except Exception as e:
                logger.debug(f"Failed to parse as DER: {e}")

        if cert is None:
            # Try raw DER (unlikely but possible)
            try:
                cert = x509.load_der_x509_certificate(
                    cert_data.encode("latin-1"), default_backend()
                )
                pem_data = cert.public_bytes(serialization.Encoding.PEM).decode()
            except Exception:
                pass

        if cert is None:
            logger.warning("Could not parse client certificate in any format")
            return None

        # Compute SPKI hash
        spki = cert.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        spki_hash = (
            base64.urlsafe_b64encode(hashlib.sha256(spki).digest())
            .rstrip(b"=")
            .decode()
        )

        # Extract subject CN
        subject_cn = None
        try:
            cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if cn_attrs:
                subject_cn = cn_attrs[0].value
        except Exception:
            pass

        # Extract issuer CN
        issuer_cn = None
        try:
            cn_attrs = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
            if cn_attrs:
                issuer_cn = cn_attrs[0].value
        except Exception:
            pass

        # Extract SANs
        sans = None
        try:
            san_ext = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            san_values = san_ext.value
            sans = []
            for san in san_values:
                if isinstance(san, x509.DNSName):
                    sans.append(f"DNS:{san.value}")
                elif isinstance(san, x509.IPAddress):
                    sans.append(f"IP:{san.value}")
                elif isinstance(san, x509.RFC822Name):
                    sans.append(f"email:{san.value}")
        except x509.ExtensionNotFound:
            pass
        except Exception as e:
            logger.debug(f"Could not extract SANs: {e}")

        # Get validity dates
        not_before = (
            cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else None
        )
        not_after = (
            cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else None
        )

        # Fallback for older cryptography versions
        if not_before is None:
            try:
                not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        if not_after is None:
            try:
                not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        return ClientCertificate(
            cert=cert,
            raw_pem=pem_data,
            spki_hash=spki_hash,
            subject_cn=subject_cn,
            sans=sans,
            serial_number=format(cert.serial_number, "x"),
            issuer_cn=issuer_cn,
            not_before=not_before,
            not_after=not_after,
        )

    except ImportError:
        logger.error("cryptography library not installed - cannot parse certificates")
        return None
    except Exception as e:
        logger.error(f"Error parsing client certificate: {e}")
        return None


def extract_client_cert(request: Request) -> Optional[ClientCertificate]:
    """
    Extract client certificate from request headers.

    Checks multiple header names used by different reverse proxies:
    - X-Client-Cert (Nginx)
    - X-SSL-Client-Cert (Apache)
    - X-Forwarded-Client-Cert (Envoy)

    Args:
        request: FastAPI request object

    Returns:
        ClientCertificate or None if not found/invalid
    """
    # Use configured header first, then fallback to known headers
    configured_header = getattr(config, "MTLS_CERT_HEADER", "X-Client-Cert")
    headers_to_check = [configured_header] + [
        h for h in CERT_HEADERS if h != configured_header
    ]

    for header in headers_to_check:
        value = request.headers.get(header)
        if value:
            # Handle Envoy XFCC format (key=value;key=value)
            if header == "X-Forwarded-Client-Cert" and "Cert=" in value:
                # Extract the Cert value from XFCC format
                for part in value.split(";"):
                    if part.startswith("Cert="):
                        value = part[5:]  # Remove "Cert=" prefix
                        break

            cert = parse_certificate(value)
            if cert:
                logger.debug(f"Extracted client cert from {header}: {cert.subject_cn}")
                return cert
            else:
                logger.warning(f"Failed to parse certificate from {header}")

    return None


def is_mtls_required(request: Request) -> bool:
    """
    Check if mTLS is required for this request.

    mTLS can be:
    - Disabled entirely (MTLS_ENABLED=false)
    - Required only for remote agents (MTLS_REQUIRED_REMOTE=true)
    - Always required

    Args:
        request: FastAPI request object

    Returns:
        True if mTLS is required for this request
    """
    if not getattr(config, "MTLS_ENABLED", False):
        return False

    # Check if request is from local agent
    if not getattr(config, "MTLS_REQUIRED_REMOTE", True):
        # mTLS not required for anyone
        return False

    # Check if request appears to be local
    client_host = request.client.host if request.client else None
    if client_host in ("127.0.0.1", "::1", "localhost"):
        logger.debug(f"mTLS not required for local request from {client_host}")
        return False

    return True


def verify_cert_chain(cert: ClientCertificate) -> Tuple[bool, Optional[str]]:
    """
    Verify certificate chain against CA bundle.

    Only performed if MTLS_VERIFY_CHAIN=true and CA bundle is configured.

    Args:
        cert: ClientCertificate to verify

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not getattr(config, "MTLS_VERIFY_CHAIN", False):
        return True, None

    ca_bundle_path = getattr(config, "MTLS_CA_BUNDLE", None)
    if not ca_bundle_path:
        logger.warning("Chain verification enabled but no CA bundle configured")
        return True, None

    try:
        # Load CA certificates
        with open(ca_bundle_path, "rb") as f:
            ca_data = f.read()

        # Parse CA certificates (may be multiple in bundle)
        ca_certs = []
        for pem_cert in ca_data.split(b"-----END CERTIFICATE-----"):
            if b"-----BEGIN CERTIFICATE-----" in pem_cert:
                pem_cert = pem_cert + b"-----END CERTIFICATE-----"
                try:
                    ca_cert = x509.load_pem_x509_certificate(
                        pem_cert, default_backend()
                    )
                    ca_certs.append(ca_cert)
                except Exception:
                    pass

        if not ca_certs:
            return False, "No valid CA certificates in bundle"

        # Create trust store
        store = Store(ca_certs)

        # Verify
        builder = PolicyBuilder().store(store)
        verifier = builder.build_client_verifier()

        verifier.verify(cert.cert, [])  # No intermediate certs provided

        return True, None

    except ImportError:
        logger.warning(
            "cryptography library version does not support chain verification"
        )
        return True, None
    except Exception as e:
        return False, f"Certificate chain verification failed: {str(e)}"


async def check_certificate_revocation(
    cert: ClientCertificate, issuer_cert: Optional[object] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if certificate has been revoked using OCSP or CRL.

    Checks revocation status in the following order:
    1. OCSP (Online Certificate Status Protocol) - preferred
    2. CRL (Certificate Revocation List) - fallback

    Environment Variables:
        MTLS_CHECK_REVOCATION: Enable revocation checking (default: false)
        MTLS_OCSP_TIMEOUT: OCSP request timeout in seconds (default: 5)
        MTLS_CRL_CACHE_TTL: CRL cache TTL in seconds (default: 3600)

    Args:
        cert: ClientCertificate to check
        issuer_cert: Optional issuer certificate for OCSP

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if not revoked or revocation check disabled
        - (False, message) if revoked or check failed
    """
    if not getattr(config, "MTLS_CHECK_REVOCATION", False):
        return True, None

    # Try OCSP first
    ocsp_result, ocsp_error = await _check_ocsp(cert, issuer_cert)
    if ocsp_result is not None:
        if ocsp_result:
            return True, None
        else:
            return False, ocsp_error or "Certificate revoked (OCSP)"

    # Fall back to CRL
    crl_result, crl_error = await _check_crl(cert)
    if crl_result is not None:
        if crl_result:
            return True, None
        else:
            return False, crl_error or "Certificate revoked (CRL)"

    # If both checks failed, decide based on policy
    if getattr(config, "MTLS_REVOCATION_SOFT_FAIL", True):
        logger.warning(
            "Revocation check failed, but soft-fail enabled - allowing certificate"
        )
        return True, None
    else:
        return False, "Could not verify revocation status"


async def _check_ocsp(
    cert: ClientCertificate, issuer_cert: Optional[object] = None
) -> Tuple[Optional[bool], Optional[str]]:
    """
    Check certificate revocation via OCSP.

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if not revoked
        - (False, message) if revoked
        - (None, None) if OCSP check not possible
    """
    try:
        # Get OCSP responder URL from certificate
        try:
            aia = cert.cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_INFORMATION_ACCESS
            )
            ocsp_urls = [
                desc.access_location.value
                for desc in aia.value
                if desc.access_method == AuthorityInformationAccessOID.OCSP
            ]
        except x509.ExtensionNotFound:
            logger.debug("Certificate does not have AIA extension with OCSP URL")
            return None, None

        if not ocsp_urls:
            logger.debug("No OCSP URL found in certificate")
            return None, None

        ocsp_url = ocsp_urls[0]
        logger.debug(f"OCSP responder URL: {ocsp_url}")

        # Get or load issuer certificate
        if issuer_cert is None:
            # Try to get from configured CA bundle
            issuer_cert = await _get_issuer_certificate(cert)
            if issuer_cert is None:
                logger.debug("Could not find issuer certificate for OCSP")
                return None, None

        # Build OCSP request
        builder = ocsp.OCSPRequestBuilder()
        builder = builder.add_certificate(cert.cert, issuer_cert, hashes.SHA256())
        ocsp_request = builder.build()

        request_data = ocsp_request.public_bytes(serialization.Encoding.DER)

        # Send OCSP request
        timeout = getattr(config, "MTLS_OCSP_TIMEOUT", 5)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    ocsp_url,
                    data=request_data,
                    headers={"Content-Type": "application/ocsp-request"},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"OCSP responder returned status {response.status}"
                        )
                        return None, None

                    ocsp_response_data = await response.read()
        except Exception as e:
            logger.warning(f"OCSP request failed: {e}")
            return None, None

        # Parse OCSP response
        ocsp_response = ocsp.load_der_ocsp_response(ocsp_response_data)

        if ocsp_response.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            logger.warning(f"OCSP response status: {ocsp_response.response_status}")
            return None, None

        # Check certificate status
        cert_status = ocsp_response.certificate_status

        if cert_status == ocsp.OCSPCertStatus.GOOD:
            logger.debug("OCSP status: GOOD (not revoked)")
            return True, None
        elif cert_status == ocsp.OCSPCertStatus.REVOKED:
            revocation_time = ocsp_response.revocation_time
            revocation_reason = ocsp_response.revocation_reason
            reason_str = revocation_reason.name if revocation_reason else "unknown"
            logger.warning(
                f"OCSP status: REVOKED (reason: {reason_str}, time: {revocation_time})"
            )
            return False, f"Certificate revoked via OCSP (reason: {reason_str})"
        else:
            logger.debug("OCSP status: UNKNOWN")
            return None, None

    except Exception as e:
        logger.warning(f"OCSP check error: {e}")
        return None, None


async def _check_crl(cert: ClientCertificate) -> Tuple[Optional[bool], Optional[str]]:
    """
    Check certificate revocation via CRL.

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if not revoked
        - (False, message) if revoked
        - (None, None) if CRL check not possible
    """
    try:
        # Get CRL distribution points from certificate
        try:
            cdp = cert.cert.extensions.get_extension_for_oid(
                ExtensionOID.CRL_DISTRIBUTION_POINTS
            )
            crl_urls = []
            for dp in cdp.value:
                if dp.full_name:
                    for name in dp.full_name:
                        if hasattr(name, "value") and isinstance(name.value, str):
                            if name.value.startswith("http"):
                                crl_urls.append(name.value)
        except x509.ExtensionNotFound:
            logger.debug("Certificate does not have CRL distribution points")
            return None, None

        if not crl_urls:
            logger.debug("No CRL URL found in certificate")
            return None, None

        crl_url = crl_urls[0]
        logger.debug(f"CRL distribution point: {crl_url}")

        # Fetch CRL (with caching)
        crl = await _fetch_crl(crl_url)
        if crl is None:
            return None, None

        # Check if certificate serial is in CRL
        serial = cert.cert.serial_number

        for revoked_cert in crl:
            if revoked_cert.serial_number == serial:
                # revocation_date = revoked_cert.revocation_date  # Reserved for logging
                try:
                    from cryptography.x509.oid import CRLEntryExtensionOID

                    reason = revoked_cert.extensions.get_extension_for_oid(
                        CRLEntryExtensionOID.CRL_REASON
                    ).value
                    reason_str = reason.name
                except x509.ExtensionNotFound:
                    reason_str = "unspecified"

                logger.warning(
                    f"Certificate found in CRL (serial: {serial}, reason: {reason_str})"
                )
                return False, f"Certificate revoked via CRL (reason: {reason_str})"

        logger.debug("Certificate not found in CRL (not revoked)")
        return True, None

    except Exception as e:
        logger.warning(f"CRL check error: {e}")
        return None, None


# CRL cache
_crl_cache: dict = {}
_crl_cache_times: dict = {}


async def _fetch_crl(crl_url: str) -> Optional[object]:
    """Fetch and cache CRL from URL."""
    cache_ttl = getattr(config, "MTLS_CRL_CACHE_TTL", 3600)

    # Check cache
    if crl_url in _crl_cache:
        cache_time = _crl_cache_times.get(crl_url, 0)
        if time.time() - cache_time < cache_ttl:
            return _crl_cache[crl_url]

    try:
        timeout = getattr(config, "MTLS_CRL_TIMEOUT", 10)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                crl_url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    logger.warning(f"CRL fetch failed: status {response.status}")
                    return None

                crl_data = await response.read()

        # Parse CRL (try DER first, then PEM)
        try:
            crl = x509.load_der_x509_crl(crl_data, default_backend())
        except Exception:
            try:
                crl = x509.load_pem_x509_crl(crl_data, default_backend())
            except Exception as e:
                logger.warning(f"Could not parse CRL: {e}")
                return None

        # Cache the CRL
        _crl_cache[crl_url] = crl
        _crl_cache_times[crl_url] = time.time()

        logger.debug(f"CRL fetched and cached from {crl_url}")
        return crl

    except Exception as e:
        logger.warning(f"CRL fetch error: {e}")
        return None


async def _get_issuer_certificate(cert: ClientCertificate) -> Optional[object]:
    """Try to get issuer certificate from CA bundle or AIA."""
    try:
        # Try to find in CA bundle first
        ca_bundle_path = getattr(config, "MTLS_CA_BUNDLE", None)
        if ca_bundle_path:
            try:
                with open(ca_bundle_path, "rb") as f:
                    ca_data = f.read()

                issuer_name = cert.cert.issuer

                for pem_cert in ca_data.split(b"-----END CERTIFICATE-----"):
                    if b"-----BEGIN CERTIFICATE-----" in pem_cert:
                        pem_cert = pem_cert + b"-----END CERTIFICATE-----"
                        try:
                            ca_cert = x509.load_pem_x509_certificate(
                                pem_cert, default_backend()
                            )
                            if ca_cert.subject == issuer_name:
                                return ca_cert
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Could not load CA bundle: {e}")

        # Try to fetch from AIA caIssuers
        try:
            aia = cert.cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_INFORMATION_ACCESS
            )
            issuer_urls = [
                desc.access_location.value
                for desc in aia.value
                if desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS
            ]

            if issuer_urls:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        issuer_urls[0], timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            cert_data = await response.read()
                            try:
                                return x509.load_der_x509_certificate(
                                    cert_data, default_backend()
                                )
                            except Exception:
                                try:
                                    return x509.load_pem_x509_certificate(
                                        cert_data, default_backend()
                                    )
                                except Exception:
                                    pass
        except x509.ExtensionNotFound:
            pass
        except Exception as e:
            logger.debug(f"Could not fetch issuer cert: {e}")

        return None

    except Exception:
        return None


class MTLSHandler:
    """
    Handler for mTLS certificate operations.

    Provides a unified interface for certificate extraction, validation,
    and SPKI computation.
    """

    def __init__(self):
        self.enabled = getattr(config, "MTLS_ENABLED", False)
        self.required_remote = getattr(config, "MTLS_REQUIRED_REMOTE", True)
        self.verify_chain = getattr(config, "MTLS_VERIFY_CHAIN", False)
        self.check_revocation = getattr(config, "MTLS_CHECK_REVOCATION", False)

    def extract_and_validate(
        self, request: Request
    ) -> Tuple[Optional[ClientCertificate], Optional[str]]:
        """
        Extract and validate client certificate from request (sync version).

        Note: For revocation checking, use extract_and_validate_async.

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (ClientCertificate, error_message)
            If cert is None and error is None, mTLS not required/provided
            If cert is None and error is set, validation failed
            If cert is set, validation passed
        """
        if not self.enabled:
            return None, None

        # Extract certificate
        cert = extract_client_cert(request)

        if cert is None:
            if is_mtls_required(request):
                return None, "Client certificate required but not provided"
            return None, None

        # Validate certificate
        valid, error = cert.is_valid()
        if not valid:
            return None, error

        # Verify chain if configured
        if self.verify_chain:
            valid, error = verify_cert_chain(cert)
            if not valid:
                return None, error

        return cert, None

    async def extract_and_validate_async(
        self, request: Request
    ) -> Tuple[Optional[ClientCertificate], Optional[str]]:
        """
        Extract and validate client certificate from request (async version).

        This version also performs revocation checking if enabled.

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (ClientCertificate, error_message)
            If cert is None and error is None, mTLS not required/provided
            If cert is None and error is set, validation failed
            If cert is set, validation passed
        """
        if not self.enabled:
            return None, None

        # Extract certificate
        cert = extract_client_cert(request)

        if cert is None:
            if is_mtls_required(request):
                return None, "Client certificate required but not provided"
            return None, None

        # Validate certificate
        valid, error = cert.is_valid()
        if not valid:
            return None, error

        # Verify chain if configured
        if self.verify_chain:
            valid, error = verify_cert_chain(cert)
            if not valid:
                return None, error

        # Check revocation status if enabled
        if self.check_revocation:
            valid, error = await check_certificate_revocation(cert)
            if not valid:
                return None, error

        return cert, None

    def get_spki(self, request: Request) -> Optional[str]:
        """
        Get SPKI hash from client certificate if present.

        Convenience method for token binding.

        Args:
            request: FastAPI request object

        Returns:
            SPKI hash or None
        """
        cert, _ = self.extract_and_validate(request)
        return cert.spki_hash if cert else None


# Singleton instance
_mtls_handler: Optional[MTLSHandler] = None


def get_mtls_handler() -> MTLSHandler:
    """
    Get the singleton MTLSHandler instance.

    Returns:
        MTLSHandler instance
    """
    global _mtls_handler
    if _mtls_handler is None:
        _mtls_handler = MTLSHandler()
    return _mtls_handler
