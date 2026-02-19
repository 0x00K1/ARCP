"""
DPoP (Demonstrating Proof-of-Possession) data models per RFC 9449.

This module defines the data structures used for DPoP proof validation
in the ARCP Three-Phase Registration flow.

DPoP binds access tokens to the client's public key, preventing token
theft and replay attacks.

Example DPoP Proof JWT:
    {
        "typ": "dpop+jwt",
        "alg": "EdDSA",
        "jwk": {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": "..."
        }
    }.{
        "jti": "unique-id-123",
        "htm": "POST",
        "htu": "https://arcp.example.com/auth/agent/request_temp_token",
        "iat": 1706630400,
        "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo"
    }
"""

import base64
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class DPoPValidationError(Enum):
    """Enumeration of DPoP validation error types."""

    MISSING_HEADER = "missing_dpop_header"
    INVALID_JWT = "invalid_jwt_format"
    INVALID_TYP = "invalid_typ_claim"
    MISSING_JWK = "missing_jwk_in_header"
    UNSUPPORTED_ALGORITHM = "unsupported_algorithm"
    INVALID_SIGNATURE = "invalid_signature"
    MISSING_JTI = "missing_jti_claim"
    MISSING_HTM = "missing_htm_claim"
    MISSING_HTU = "missing_htu_claim"
    MISSING_IAT = "missing_iat_claim"
    HTM_MISMATCH = "htm_mismatch"
    HTU_MISMATCH = "htu_mismatch"
    PROOF_EXPIRED = "proof_expired"
    PROOF_FUTURE = "proof_issued_in_future"
    JTI_REPLAY = "jti_already_used"
    ATH_MISMATCH = "access_token_hash_mismatch"
    JKT_MISMATCH = "jwk_thumbprint_mismatch"
    VALIDATION_ERROR = "validation_error"


class DPoPProof(BaseModel):
    """
    Parsed DPoP proof JWT claims per RFC 9449.

    Required claims:
    - jti: Unique identifier for replay prevention
    - htm: HTTP method of the request
    - htu: HTTP URI of the request (without query/fragment)
    - iat: Issued at timestamp

    Optional claims:
    - ath: Access token hash (when binding to existing token)
    - nonce: Server-provided nonce for freshness

    JWK is extracted from the JWT header.
    """

    jti: str = Field(
        ...,
        min_length=16,
        max_length=256,
        description="Unique identifier for the proof (UUID or random string)",
    )
    htm: str = Field(..., description="HTTP method (GET, POST, PUT, DELETE, PATCH)")
    htu: str = Field(..., min_length=1, description="HTTP URI of the request")
    iat: int = Field(..., description="Issued at timestamp (Unix epoch seconds)")
    ath: Optional[str] = Field(
        None, description="Base64url SHA256 hash of access token"
    )
    nonce: Optional[str] = Field(
        None, description="Server-provided nonce for additional freshness"
    )

    # JWK from the JWT header (public key)
    jwk: Dict[str, Any] = Field(..., description="Public key from proof JWT header")

    # Original algorithm from header
    alg: str = Field(..., description="Signing algorithm used")

    @field_validator("htm")
    @classmethod
    def validate_htm(cls, v: str) -> str:
        """Validate HTTP method."""
        allowed = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Invalid HTTP method: {v}")
        return v_upper

    @field_validator("iat")
    @classmethod
    def validate_iat_reasonable(cls, v: int) -> int:
        """Basic validation that iat is a reasonable timestamp."""
        # Must be after 2020-01-01
        if v < 1577836800:
            raise ValueError("iat timestamp is too old")
        # Can't be more than 1 year in future
        max_future = datetime.utcnow().timestamp() + (365 * 24 * 3600)
        if v > max_future:
            raise ValueError("iat timestamp is too far in future")
        return v

    def compute_jkt(self) -> str:
        """
        Compute JWK Thumbprint per RFC 7638.

        The thumbprint is a SHA-256 hash of the canonical JWK representation,
        base64url encoded.

        Returns:
            Base64url-encoded SHA-256 thumbprint
        """
        kty = self.jwk.get("kty")

        if kty == "OKP":
            # EdDSA (Ed25519, Ed448)
            canonical = {
                "crv": self.jwk.get("crv", "Ed25519"),
                "kty": "OKP",
                "x": self.jwk["x"],
            }
        elif kty == "EC":
            # ECDSA (P-256, P-384, P-521)
            canonical = {
                "crv": self.jwk.get("crv", "P-256"),
                "kty": "EC",
                "x": self.jwk["x"],
                "y": self.jwk["y"],
            }
        elif kty == "RSA":
            # RSA (not recommended for DPoP but supported)
            canonical = {"e": self.jwk["e"], "kty": "RSA", "n": self.jwk["n"]}
        else:
            raise ValueError(f"Unsupported key type: {kty}")

        # Serialize with sorted keys, no whitespace
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

        # SHA-256 hash
        digest = hashlib.sha256(canonical_json.encode()).digest()

        # Base64url encode (no padding)
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def verify_ath(self, access_token: str) -> bool:
        """
        Verify the access token hash claim.

        Args:
            access_token: The access token to verify against

        Returns:
            True if ath matches, False otherwise
        """
        if not self.ath:
            return True  # No ath claim to verify

        # Compute expected ath
        digest = hashlib.sha256(access_token.encode()).digest()
        expected_ath = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        return self.ath == expected_ath

    class Config:
        json_schema_extra = {
            "example": {
                "jti": "550e8400-e29b-41d4-a716-446655440000",
                "htm": "POST",
                "htu": "https://arcp.example.com/auth/agent/request_temp_token",
                "iat": 1706630400,
                "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo",
                "nonce": None,
                "jwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
                },
                "alg": "EdDSA",
            }
        }


class DPoPValidationResult(BaseModel):
    """
    Result of DPoP proof validation.

    Contains the validation outcome, parsed proof (if valid),
    computed JWK thumbprint, and any error details.
    """

    valid: bool = Field(..., description="Whether the DPoP proof is valid")
    proof: Optional[DPoPProof] = Field(None, description="Parsed DPoP proof (if valid)")
    jkt: Optional[str] = Field(
        None, description="JWK Thumbprint computed from proof (if valid)"
    )
    error: Optional[DPoPValidationError] = Field(
        None, description="Error type if validation failed"
    )
    error_detail: Optional[str] = Field(
        None, description="Human-readable error description"
    )

    @classmethod
    def success(cls, proof: DPoPProof) -> "DPoPValidationResult":
        """Create a successful validation result."""
        return cls(
            valid=True,
            proof=proof,
            jkt=proof.compute_jkt(),
            error=None,
            error_detail=None,
        )

    @classmethod
    def failure(cls, error: DPoPValidationError, detail: str) -> "DPoPValidationResult":
        """Create a failed validation result."""
        return cls(valid=False, proof=None, jkt=None, error=error, error_detail=detail)

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "proof": {
                    "jti": "unique-id",
                    "htm": "POST",
                    "htu": "https://arcp.example.com/...",
                    "iat": 1706630400,
                },
                "jkt": "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs",
                "error": None,
                "error_detail": None,
            }
        }


class DPoPNonceResponse(BaseModel):
    """
    Response when server requires a fresh nonce.

    Per RFC 9449, servers can require nonces by returning this with
    a 400 status and DPoP-Nonce header.
    """

    error: str = Field(default="use_dpop_nonce", description="Error code per RFC 9449")
    error_description: str = Field(
        default="Server requires DPoP nonce",
        description="Human-readable error description",
    )
    nonce: str = Field(..., description="Server-provided nonce to use in next request")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "use_dpop_nonce",
                "error_description": "Server requires DPoP nonce",
                "nonce": "eyJ7S_zG.eyJH0-Z.HX4w-7v",
            }
        }
