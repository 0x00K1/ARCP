"""
Runtime integrity and attestation models.

Data structures for runtime attestation, supporting both
TPM-based hardware attestation and software-based measurements.

Attestation ensures agents maintain integrity during operation
by verifying code measurements and runtime state.

Attestation Types:
- TPM: Hardware-based using Trusted Platform Module
- Software: Code measurement and process verification
- Remote: Third-party attestation services

Example Usage:
    >>> from arcp.models.attestation import AttestationEvidence, AttestationType
    >>> evidence = AttestationEvidence(
    ...     type=AttestationType.SOFTWARE,
    ...     nonce="challenge-123",
    ...     code_measurements={"main.py": "sha256:abc..."}
    ... )
    >>> print(evidence.compute_evidence_hash())
"""

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, field_validator


class AttestationType(Enum):
    """Types of attestation supported."""

    TPM = "tpm"  # Hardware TPM attestation
    SOFTWARE = "software"  # Software-based measurement
    REMOTE = "remote"  # Remote attestation service
    NONE = "none"  # No attestation


class AttestationStatus(Enum):
    """Status of an attestation verification."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass
class PCRValue:
    """
    TPM Platform Configuration Register value.

    PCRs store measurements of system state and are
    extended (not directly written) to create a
    tamper-evident log.
    """

    index: int
    algorithm: str  # sha1, sha256, sha384
    value: str  # Hex-encoded hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "algorithm": self.algorithm,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PCRValue":
        return cls(
            index=data.get("index", 0),
            algorithm=data.get("algorithm", "sha256"),
            value=data.get("value", ""),
        )


@dataclass
class CodeMeasurement:
    """
    Measurement of a code file or module.

    Used for software-based attestation to verify
    code integrity at runtime.
    """

    path: str  # File path or module name
    hash_algorithm: str  # sha256, sha384
    hash_value: str  # Hex-encoded hash
    size: Optional[int] = None  # File size in bytes
    modified_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "hash_algorithm": self.hash_algorithm,
            "hash_value": self.hash_value,
            "size": self.size,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeMeasurement":
        modified = data.get("modified_at")
        return cls(
            path=data.get("path", ""),
            hash_algorithm=data.get("hash_algorithm", "sha256"),
            hash_value=data.get("hash_value", ""),
            size=data.get("size"),
            modified_at=datetime.fromisoformat(modified) if modified else None,
        )


@dataclass
class ProcessInfo:
    """
    Information about the running agent process.

    Used for runtime verification to detect
    process tampering or unexpected state.
    """

    pid: int
    name: str
    executable_path: str
    executable_hash: str
    command_line: Optional[str] = None
    user: Optional[str] = None
    start_time: Optional[datetime] = None
    memory_usage_bytes: Optional[int] = None
    parent_pid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "executable_path": self.executable_path,
            "executable_hash": self.executable_hash,
            "command_line": self.command_line,
            "user": self.user,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "memory_usage_bytes": self.memory_usage_bytes,
            "parent_pid": self.parent_pid,
        }


@dataclass
class AttestationEvidence:
    """
    Evidence provided by an agent for attestation.

    Contains measurements and proofs depending on
    the attestation type (TPM, software, etc.).
    """

    type: AttestationType
    timestamp: datetime
    nonce: str  # Server-provided challenge
    agent_id: str

    # For TPM attestation
    quote: Optional[str] = None  # TPM quote signature
    pcr_values: Optional[List[PCRValue]] = None
    ak_cert: Optional[str] = None  # Attestation Key certificate (PEM)
    event_log: Optional[str] = None  # TCG event log (base64)

    # For software attestation
    code_measurements: Optional[List[CodeMeasurement]] = None
    process_info: Optional[ProcessInfo] = None
    environment_hash: Optional[str] = None  # Hash of relevant env vars
    loaded_modules: Optional[List[str]] = None  # Loaded libraries/modules

    # For remote attestation
    remote_token: Optional[str] = None  # Token from remote attestation service
    remote_service: Optional[str] = None  # Service identifier

    def compute_evidence_hash(self) -> str:
        """
        Compute hash of evidence for binding.

        This hash ties the attestation to a specific state,
        used in security bindings.
        """
        data = {
            "type": self.type.value,
            "nonce": self.nonce,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.quote:
            data["quote"] = self.quote

        if self.pcr_values:
            data["pcr_values"] = {str(pcr.index): pcr.value for pcr in self.pcr_values}

        if self.code_measurements:
            data["code_measurements"] = {
                m.path: m.hash_value for m in self.code_measurements
            }

        if self.process_info:
            data["executable_hash"] = self.process_info.executable_hash

        json_str = json.dumps(data, sort_keys=True)
        return f"sha256:{hashlib.sha256(json_str.encode()).hexdigest()}"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "nonce": self.nonce,
            "agent_id": self.agent_id,
        }

        if self.quote:
            result["quote"] = self.quote
        if self.pcr_values:
            result["pcr_values"] = [p.to_dict() for p in self.pcr_values]
        if self.ak_cert:
            result["ak_cert"] = self.ak_cert
        if self.code_measurements:
            result["code_measurements"] = [m.to_dict() for m in self.code_measurements]
        if self.process_info:
            result["process_info"] = self.process_info.to_dict()
        if self.environment_hash:
            result["environment_hash"] = self.environment_hash
        if self.loaded_modules:
            result["loaded_modules"] = self.loaded_modules
        if self.remote_token:
            result["remote_token"] = self.remote_token
        if self.remote_service:
            result["remote_service"] = self.remote_service

        return result


@dataclass
class AttestationResult:
    """
    Result of attestation verification.
    """

    valid: bool
    status: AttestationStatus
    type: AttestationType
    evidence_hash: str
    verified_at: datetime

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # TPM-specific results
    pcr_policy_match: Optional[bool] = None
    quote_verified: Optional[bool] = None
    ak_cert_valid: Optional[bool] = None

    # Software-specific results
    code_integrity_match: Optional[bool] = None
    process_verified: Optional[bool] = None
    measurement_count: Optional[int] = None

    # Validity period
    valid_until: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "status": self.status.value,
            "type": self.type.value,
            "evidence_hash": self.evidence_hash,
            "verified_at": self.verified_at.isoformat(),
            "errors": self.errors,
            "warnings": self.warnings,
            "pcr_policy_match": self.pcr_policy_match,
            "quote_verified": self.quote_verified,
            "code_integrity_match": self.code_integrity_match,
            "process_verified": self.process_verified,
            "measurement_count": self.measurement_count,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }


class AttestationChallenge(BaseModel):
    """
    Challenge sent to agent for attestation.

    The agent must respond with evidence that includes
    this nonce to prove freshness.
    """

    challenge_id: str = Field(..., description="Unique challenge identifier")
    nonce: str = Field(
        ..., min_length=32, max_length=128, description="Random nonce for freshness"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When challenge was issued"
    )
    expires_at: datetime = Field(..., description="Challenge expiration time")
    attestation_types: List[str] = Field(
        default_factory=lambda: ["software"], description="Accepted attestation types"
    )
    required_measurements: Optional[List[str]] = Field(
        None, description="Specific files/modules to measure"
    )

    @classmethod
    def create(
        cls,
        validity_seconds: int = 300,
        attestation_types: Optional[List[str]] = None,
        required_measurements: Optional[List[str]] = None,
    ) -> "AttestationChallenge":
        """Create a new attestation challenge."""
        now = datetime.utcnow()
        return cls(
            challenge_id=f"att_{secrets.token_hex(16)}",
            nonce=secrets.token_urlsafe(48),
            timestamp=now,
            expires_at=now + timedelta(seconds=validity_seconds),
            attestation_types=attestation_types or ["software"],
            required_measurements=required_measurements,
        )

    def is_expired(self) -> bool:
        """Check if challenge has expired."""
        return datetime.utcnow() > self.expires_at

    class Config:
        json_schema_extra = {
            "example": {
                "challenge_id": "att_abc123def456",
                "nonce": "dGhpcyBpcyBhIHJhbmRvbSBub25jZQ...",
                "timestamp": "2026-02-03T10:00:00Z",
                "expires_at": "2026-02-03T10:05:00Z",
                "attestation_types": ["software", "tpm"],
                "required_measurements": ["main.py", "config.py"],
            }
        }


class AttestationRequest(BaseModel):
    """
    Attestation evidence submission from agent.
    """

    challenge_id: str = Field(..., description="Challenge being responded to")
    nonce: str = Field(..., description="Nonce from challenge (proves freshness)")
    attestation_type: str = Field(
        ..., description="Type of attestation (tpm, software, remote)"
    )

    # TPM attestation fields
    quote: Optional[str] = Field(None, description="TPM quote signature (base64)")
    pcr_values: Optional[Dict[str, str]] = Field(
        None, description="PCR index to value mapping"
    )
    ak_cert: Optional[str] = Field(
        None, description="Attestation key certificate (PEM)"
    )
    event_log: Optional[str] = Field(None, description="TCG event log (base64)")

    # Software attestation fields
    code_measurements: Optional[Dict[str, str]] = Field(
        None, description="File path to hash mapping"
    )
    executable_hash: Optional[str] = Field(
        None, description="Hash of the agent executable"
    )
    process_info: Optional[Dict[str, Any]] = Field(
        None, description="Process runtime information"
    )
    loaded_modules: Optional[List[str]] = Field(
        None, description="List of loaded Python modules"
    )
    environment_hash: Optional[str] = Field(
        None, description="Hash of relevant environment variables"
    )

    # Remote attestation fields
    remote_token: Optional[str] = Field(
        None, description="Token from remote attestation service"
    )
    remote_service: Optional[str] = Field(
        None, description="Remote attestation service identifier"
    )

    @field_validator("attestation_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"tpm", "software", "remote"}
        if v.lower() not in allowed:
            raise ValueError(f"Invalid attestation type. Allowed: {allowed}")
        return v.lower()

    class Config:
        json_schema_extra = {
            "example": {
                "challenge_id": "att_abc123def456",
                "nonce": "dGhpcyBpcyBhIHJhbmRvbSBub25jZQ...",
                "attestation_type": "software",
                "code_measurements": {
                    "main.py": "sha256:abc123...",
                    "config.py": "sha256:def456...",
                },
                "executable_hash": "sha256:789xyz...",
                "process_info": {"pid": 12345, "name": "agent", "user": "appuser"},
            }
        }


class AttestationResponse(BaseModel):
    """
    Response from attestation verification.
    """

    valid: bool = Field(..., description="Whether attestation passed")
    status: str = Field(..., description="Attestation status")
    evidence_hash: str = Field(..., description="Hash of verified evidence")
    verified_at: datetime = Field(
        default_factory=datetime.utcnow, description="When verification completed"
    )
    valid_until: Optional[datetime] = Field(
        None, description="Attestation validity period end"
    )

    errors: List[str] = Field(default_factory=list, description="Verification errors")
    warnings: List[str] = Field(
        default_factory=list, description="Verification warnings"
    )

    # Detailed results
    measurements_verified: Optional[int] = Field(
        None, description="Number of measurements verified"
    )
    integrity_match: Optional[bool] = Field(
        None, description="Whether integrity checks passed"
    )

    @classmethod
    def from_result(cls, result: AttestationResult) -> "AttestationResponse":
        """Create response from AttestationResult."""
        return cls(
            valid=result.valid,
            status=result.status.value,
            evidence_hash=result.evidence_hash,
            verified_at=result.verified_at,
            valid_until=result.valid_until,
            errors=result.errors,
            warnings=result.warnings,
            measurements_verified=result.measurement_count,
            integrity_match=result.code_integrity_match,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "status": "valid",
                "evidence_hash": "sha256:abc123...",
                "verified_at": "2026-02-03T10:00:30Z",
                "valid_until": "2026-02-03T11:00:30Z",
                "errors": [],
                "warnings": [],
                "measurements_verified": 5,
                "integrity_match": True,
            }
        }


# Expected measurements for policy enforcement
@dataclass
class AttestationPolicy:
    """
    Policy defining expected attestation state.

    Used to verify agent measurements against
    known-good values.
    """

    agent_type: str
    version: Optional[str] = None

    # Expected code measurements
    expected_measurements: Dict[str, str] = field(default_factory=dict)

    # Expected PCR values for TPM
    expected_pcr_values: Dict[int, str] = field(default_factory=dict)

    # Allowed executable hashes
    allowed_executable_hashes: Set[str] = field(default_factory=set)

    # Required modules
    required_modules: Set[str] = field(default_factory=set)

    # Attestation interval (how often to re-attest)
    attestation_interval_seconds: int = 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "version": self.version,
            "expected_measurements": self.expected_measurements,
            "expected_pcr_values": {
                str(k): v for k, v in self.expected_pcr_values.items()
            },
            "allowed_executable_hashes": list(self.allowed_executable_hashes),
            "required_modules": list(self.required_modules),
            "attestation_interval_seconds": self.attestation_interval_seconds,
        }


# =============================================================================
# Attestation API Request/Response Models
# =============================================================================


class AttestationChallengeRequest(BaseModel):
    """Request for attestation challenge."""

    agent_id: str = Field(..., description="ID of the agent requesting attestation")
    attestation_types: List[str] = Field(
        default=["software"], description="Accepted attestation types (software, tpm)"
    )
    required_measurements: Optional[List[str]] = Field(
        None, description="Specific files to measure (optional)"
    )


class AttestationChallengeResponse(BaseModel):
    """Response with attestation challenge."""

    challenge_id: str
    nonce: str
    timestamp: datetime
    expires_at: datetime
    attestation_types: List[str]
    required_measurements: Optional[List[str]] = None


class AttestationVerifyRequest(BaseModel):
    """Request to verify attestation."""

    agent_id: str = Field(..., description="ID of the agent providing attestation")
    challenge_id: str = Field(
        ..., description="Challenge ID from /attestation/challenge"
    )
    nonce: str = Field(..., description="Nonce from challenge")
    attestation_type: str = Field(
        "software", description="Type of attestation (software, tpm)"
    )

    # Software attestation fields
    code_measurements: Optional[Dict[str, str]] = Field(
        None, description="Map of file paths to SHA-256 hashes"
    )
    executable_hash: Optional[str] = Field(
        None, description="SHA-256 hash of the agent executable"
    )
    process_info: Optional[Dict[str, Any]] = Field(
        None, description="Process information (pid, name, path, etc.)"
    )
    environment_hash: Optional[str] = Field(
        None, description="Hash of relevant environment variables"
    )
    loaded_modules: Optional[List[str]] = Field(
        None, description="List of loaded Python/JS modules"
    )

    # TPM attestation fields
    quote: Optional[str] = Field(None, description="Base64-encoded TPM quote")
    pcr_values: Optional[Dict[str, str]] = Field(
        None, description="Map of PCR index to value"
    )
    ak_cert: Optional[str] = Field(
        None, description="PEM-encoded Attestation Key certificate"
    )
    event_log: Optional[str] = Field(None, description="Base64-encoded TCG event log")


class AttestationVerifyResponse(BaseModel):
    """Response from attestation verification."""

    valid: bool
    status: str
    type: str
    evidence_hash: str
    verified_at: datetime
    valid_until: Optional[datetime] = None
    errors: List[str] = []
    warnings: List[str] = []

    # Verification details
    code_integrity_match: Optional[bool] = None
    process_verified: Optional[bool] = None
    pcr_policy_match: Optional[bool] = None
    quote_verified: Optional[bool] = None
