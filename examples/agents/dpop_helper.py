"""
DPoP Proof Generator for ARCP Agents.

This module provides DPoP (Demonstrating Proof-of-Possession) proof
generation for agents that need to authenticate with ARCP when
DPOP_REQUIRED=true.

DPoP binds access tokens to a client's public key, preventing token
theft and replay attacks.

Usage:
    from dpop_helper import DPoPGenerator

    # Create generator (generates key pair automatically)
    dpop = DPoPGenerator()

    # Generate proof for each request
    proof = dpop.create_proof(
        method="POST",
        uri="http://localhost:8001/auth/agent/validate_compliance",
        access_token="eyJ..."  # Optional: for ath binding
    )

    # Add to request headers
    headers["DPoP"] = proof

References:
    - RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)
    - https://datatracker.ietf.org/doc/html/rfc9449
"""

import base64
import hashlib
import json
import time
import uuid
from typing import Optional
from urllib.parse import urlparse

# Use cryptography library for key generation
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# Use PyJWT for JWT creation
try:
    import jwt

    HAS_JWT = True
except ImportError:
    HAS_JWT = False


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    """Base64url decode with padding restoration."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


class DPoPGenerator:
    """
    Generator for DPoP (Demonstrating Proof-of-Possession) proofs.

    Creates RFC 9449 compliant DPoP proofs using Ed25519 signatures.
    Automatically generates a key pair on initialization.

    Attributes:
        algorithm: Signing algorithm (EdDSA for Ed25519)
        jkt: JWK Thumbprint of the public key
    """

    def __init__(self, algorithm: str = "EdDSA"):
        """
        Initialize DPoP generator with a new key pair.

        Args:
            algorithm: Signing algorithm. Currently only EdDSA is supported.
        """
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("cryptography library is required for DPoP support")
        if not HAS_JWT:
            raise ImportError("PyJWT library is required for DPoP support")

        self.algorithm = algorithm

        if algorithm == "EdDSA":
            self._init_ed25519()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Compute JWK Thumbprint
        self.jkt = self._compute_jkt()

    def _init_ed25519(self):
        """Initialize Ed25519 key pair."""
        # Generate private key
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

        # Get raw public key bytes
        public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

        # Create JWK representation
        self._jwk = {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": _base64url_encode(public_bytes),
        }

    def _compute_jkt(self) -> str:
        """
        Compute JWK Thumbprint per RFC 7638.

        Returns:
            Base64url-encoded SHA-256 hash of the JWK
        """
        # For OKP keys: {"crv":"...","kty":"OKP","x":"..."}
        # Sorted lexicographically by key name
        if self._jwk["kty"] == "OKP":
            canonical = json.dumps(
                {
                    "crv": self._jwk["crv"],
                    "kty": self._jwk["kty"],
                    "x": self._jwk["x"],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        else:
            raise ValueError(f"JKT computation not implemented for {self._jwk['kty']}")

        digest = hashlib.sha256(canonical.encode()).digest()
        return _base64url_encode(digest)

    def get_jwk(self) -> dict:
        """
        Get the public JWK for embedding in proofs.

        Returns:
            JWK dictionary (public key only)
        """
        return self._jwk.copy()

    def create_proof(
        self,
        method: str,
        uri: str,
        access_token: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> str:
        """
        Create a DPoP proof JWT.

        Args:
            method: HTTP method (GET, POST, etc.)
            uri: Full request URI (scheme://host/path)
            access_token: If provided, includes ath (access token hash) claim
            nonce: Server-provided nonce if required

        Returns:
            DPoP proof JWT string
        """
        now = int(time.time())

        # Build claims
        claims = {
            "jti": str(uuid.uuid4()),  # Unique identifier
            "htm": method.upper(),  # HTTP method
            "htu": self._normalize_uri(uri),  # HTTP URI
            "iat": now,  # Issued at
        }

        # Optional: access token hash
        if access_token:
            claims["ath"] = self._compute_ath(access_token)

        # Optional: server nonce
        if nonce:
            claims["nonce"] = nonce

        # Build header with typ and jwk
        headers = {
            "typ": "dpop+jwt",
            "alg": self.algorithm,
            "jwk": self._jwk,
        }

        # Sign the JWT
        # PyJWT requires the private key object
        token = jwt.encode(
            claims,
            self._private_key,
            algorithm=self.algorithm,
            headers=headers,
        )

        return token

    def _normalize_uri(self, uri: str) -> str:
        """
        Normalize URI for htu claim.

        Per RFC 9449, the htu should be the request URI without query
        string and fragment.

        Args:
            uri: Full request URI

        Returns:
            Normalized URI (scheme://host/path)
        """
        parsed = urlparse(uri)
        # Reconstruct without query and fragment
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _compute_ath(self, access_token: str) -> str:
        """
        Compute access token hash for ath claim.

        Args:
            access_token: The access token string

        Returns:
            Base64url-encoded SHA-256 hash
        """
        digest = hashlib.sha256(access_token.encode()).digest()
        return _base64url_encode(digest)


# Convenience function for quick usage
def create_dpop_generator(algorithm: str = "EdDSA") -> DPoPGenerator:
    """
    Create a new DPoP generator.

    Args:
        algorithm: Signing algorithm (default: EdDSA)

    Returns:
        DPoPGenerator instance
    """
    return DPoPGenerator(algorithm=algorithm)


if __name__ == "__main__":
    # Quick test
    print("Testing DPoP Generator...")

    dpop = DPoPGenerator()
    print(f"JWK Thumbprint (jkt): {dpop.jkt}")
    print(f"Public JWK: {json.dumps(dpop.get_jwk(), indent=2)}")

    # Create a test proof
    proof = dpop.create_proof(
        method="POST",
        uri="http://localhost:8001/auth/agent/validate_compliance",
        access_token="test-token-123",
    )
    print(f"\nDPoP Proof JWT:\n{proof}")

    # Decode and display (for verification)
    header = jwt.get_unverified_header(proof)
    claims = jwt.decode(proof, options={"verify_signature": False})
    print(f"\nHeader: {json.dumps(header, indent=2)}")
    print(f"Claims: {json.dumps(claims, indent=2)}")
