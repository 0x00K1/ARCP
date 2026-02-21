"""Validation-related models for Three-Phase Registration (TPR)"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SecurityBinding(BaseModel):
    """
    Security binding created during validation phase.

    This binding ties the validated token to specific security characteristics
    of the agent, preventing token reuse by different agents or modified configurations.

    Added jkt for DPoP binding
    Added mtls_spki for mTLS binding
    Added sbom_hash for SBOM binding
    Added container_scan_hash for container scan binding
    Added attestation_hash for attestation binding
    """

    code_hash: str = Field(
        ..., description="SHA256 hash of agent code (format: sha256:<hex>)"
    )
    endpoint_hash: str = Field(
        ..., description="SHA256 hash of canonical endpoint configuration"
    )
    jkt: Optional[str] = Field(
        None, description="DPoP JWK thumbprint (RFC 9449) for proof-of-possession"
    )
    mtls_spki: Optional[str] = Field(
        None,
        description="mTLS client certificate SPKI (Subject Public Key Info) base64",
    )
    # SBOM verification hash
    sbom_hash: Optional[str] = Field(
        None, description="SHA256 hash of verified SBOM document"
    )
    # Container scan hash
    container_scan_hash: Optional[str] = Field(
        None, description="Hash of container scan result"
    )
    # Added attestation evidence hash
    attestation_hash: Optional[str] = Field(
        None, description="Hash of verified attestation evidence"
    )
    validation_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when validation was completed",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "code_hash": "sha256:abc123...",
                "endpoint_hash": "sha256:def456...",
                "jkt": "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs",
                "mtls_spki": None,
                "validation_timestamp": "2026-01-27T10:00:00Z",
            }
        }


class ValidationRequest(BaseModel):
    """
    Request for Phase 2 validation (POST /auth/agent/validate_compliance).

    The agent must provide this information along with a temp token to
    initiate the validation process.

    Optional DPoP JWK thumbprint for proof-of-possession.
    Optional mTLS SPKI hash for certificate binding.
    """

    agent_id: str = Field(
        ..., min_length=3, max_length=64, description="Unique agent identifier"
    )
    agent_type: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Type of agent (e.g., 'security', 'monitoring')",
    )
    endpoint: str = Field(
        ...,
        description="Base URL where agent is listening (e.g., 'https://agent.example.com')",
    )
    capabilities: List[str] = Field(
        ..., min_items=1, max_items=64, description="List of agent capabilities"
    )
    communication_mode: Literal["remote", "local", "hybrid"] = Field(
        default="remote",
        description="How the agent communicates (remote=network, local=same machine, hybrid=both)",
    )
    version: Optional[str] = Field(
        None, max_length=32, description="Agent version string"
    )
    dpop_jkt: Optional[str] = Field(
        None, description="DPoP JWK thumbprint for proof-of-possession"
    )
    mtls_spki: Optional[str] = Field(
        None, description="mTLS client certificate SPKI hash"
    )

    # SBOM data for verification
    sbom: Optional[str] = Field(
        None, description="SBOM content in CycloneDX or SPDX JSON format"
    )
    sbom_signature: Optional[str] = Field(
        None, description="JWS signature for SBOM integrity verification"
    )

    # Container image for scanning
    container_image: Optional[str] = Field(
        None,
        description="Container image reference (e.g., myimage:latest, registry/image:tag)",
    )
    is_containerized: bool = Field(
        False, description="Whether this agent runs in a container"
    )

    # Attestation data
    attestation: Optional[Dict] = Field(
        None,
        description="Attestation evidence data (challenge_id, nonce, measurements, etc.)",
    )

    # Context fields (set by server, not provided by client)
    client_ip: Optional[str] = Field(
        None,
        description="Client IP address (automatically extracted by server for audit logging)",
        exclude=True,  # Don't include in API schema or client examples
    )

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "security-scanner-001",
                "agent_type": "security",
                "endpoint": "https://scanner.example.com:8080",
                "capabilities": ["vulnerability_scan", "compliance_check"],
                "communication_mode": "remote",
                "version": "2.1.1",
            }
        }


class ValidationError(BaseModel):
    """An error encountered during validation"""

    type: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field that caused the error")
    details: Optional[Dict] = Field(None, description="Additional error details")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump(exclude_none=True)


class ValidationWarning(BaseModel):
    """A warning encountered during validation (non-fatal)"""

    type: str = Field(..., description="Warning type identifier")
    message: str = Field(..., description="Human-readable warning message")
    field: Optional[str] = Field(None, description="Field that caused the warning")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump(exclude_none=True)


class ValidationResult(BaseModel):
    """
    Result of the validation process.

    Contains validation ID, status, security binding (if successful),
    and any errors/warnings encountered during validation.
    """

    validation_id: str = Field(
        ..., description="Unique validation identifier (format: val_<hex>)"
    )
    agent_id: str = Field(..., description="Agent ID that was validated")
    status: Literal["passed", "failed", "pending"] = Field(
        ..., description="Validation status"
    )
    binding: Optional[SecurityBinding] = Field(
        None, description="Security binding (only present if validation passed)"
    )
    errors: List[Dict] = Field(
        default_factory=list, description="List of errors encountered during validation"
    )
    warnings: List[Dict] = Field(
        default_factory=list,
        description="List of warnings encountered during validation",
    )
    endpoint_checks: Dict = Field(
        default_factory=dict, description="Results of endpoint contract validation"
    )
    duration_ms: int = Field(
        default=0, description="Time taken for validation in milliseconds"
    )
    current_step: Optional[str] = Field(
        None,
        description="Current validation step being performed (for progress tracking)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "validation_id": "val_abc123def456",
                "agent_id": "security-scanner-001",
                "status": "passed",
                "binding": {
                    "code_hash": "sha256:abc123...",
                    "endpoint_hash": "sha256:def456...",
                    "jkt": None,
                    "mtls_spki": None,
                    "validation_timestamp": "2026-01-27T10:00:00Z",
                },
                "errors": [],
                "warnings": [],
                "endpoint_checks": {
                    "health": {"status": "passed", "response_time_ms": 45},
                    "metrics": {"status": "passed", "response_time_ms": 120},
                    "connection": {"status": "passed", "response_time_ms": 89},
                },
                "duration_ms": 2450,
            }
        }


class ValidatedTokenResponse(BaseModel):
    """
    Response containing a validated token (Phase 2 output).

    This token must be used immediately to complete registration
    before it expires (typically 5 minutes).
    """

    validated_token: str = Field(
        ..., description="Single-use validated token for registration"
    )
    token_type: str = Field(
        default="bearer", description="Token type (always 'bearer')"
    )
    expires_in: int = Field(
        default=300,
        description="Token expiration time in seconds (typically 300 = 5 minutes)",
    )
    validation_id: str = Field(..., description="Validation ID tied to this token")
    message: str = Field(
        default="Validation passed. Use this token to complete registration.",
        description="Human-readable message",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "validated_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 300,
                "validation_id": "val_abc123def456",
                "message": "Validation passed. Use this token to complete registration.",
            }
        }


class ValidationStatusResponse(BaseModel):
    """
    Response for polling validation status (GET /auth/agent/validation/{id}).

    Returns current status and, if complete, the validated token or errors.
    """

    status: Literal["pending", "passed", "failed"] = Field(
        ..., description="Current validation status"
    )
    validation_id: str = Field(..., description="Validation ID being polled")
    message: str = Field(default="", description="Human-readable status message")

    # Present when status="passed"
    validated_token: Optional[str] = Field(
        None, description="Single-use validated token (only when status=passed)"
    )
    expires_in: Optional[int] = Field(
        None, description="Token expiration time in seconds (only when status=passed)"
    )

    # Present when status="pending"
    retry_after: Optional[int] = Field(
        None,
        description="Suggested polling interval in seconds (only when status=pending)",
    )
    progress: Optional[str] = Field(
        None,
        description="Progress indicator (e.g., 'Checking endpoints...', 'Scanning container...')",
    )
    current_step: Optional[str] = Field(
        None, description="Current validation step being performed"
    )

    # Present when status="failed"
    errors: Optional[List[Dict]] = Field(
        None, description="List of validation errors (only when status=failed)"
    )
    warnings: Optional[List[Dict]] = Field(
        None, description="List of validation warnings"
    )
    endpoint_checks: Optional[Dict] = Field(
        None, description="Results of endpoint contract validation"
    )

    # Timing info
    duration_ms: Optional[int] = Field(
        None, description="Time taken for validation in milliseconds"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "status": "pending",
                    "validation_id": "val_abc123def456",
                    "message": "Validation in progress",
                    "retry_after": 2,
                },
                {
                    "status": "passed",
                    "validation_id": "val_abc123def456",
                    "message": "Validation passed",
                    "validated_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "expires_in": 300,
                    "duration_ms": 2450,
                },
                {
                    "status": "failed",
                    "validation_id": "val_abc123def456",
                    "message": "Validation failed",
                    "errors": [
                        {
                            "type": "endpoint_unreachable",
                            "message": "Health endpoint not responding",
                        }
                    ],
                    "duration_ms": 5000,
                },
            ]
        }
