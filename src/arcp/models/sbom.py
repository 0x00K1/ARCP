"""
SBOM (Software Bill of Materials) data models.

This module defines data structures for parsing and validating SBOM
documents in CycloneDX and SPDX formats for agent registration.

SBOM verification ensures that agent dependencies are known, tracked,
and checked against vulnerability databases during registration.

Supported Formats:
- CycloneDX 1.4+ (recommended)
- SPDX 2.2+ (supported)

Example Usage:
    >>> from arcp.models.sbom import SBOMData, Dependency, SBOMFormat
    >>> dependency = Dependency(
    ...     name="fastapi",
    ...     version="0.115.0",
    ...     purl="pkg:pypi/fastapi@0.115.0"
    ... )
    >>> sbom = SBOMData(
    ...     format=SBOMFormat.CYCLONEDX,
    ...     version="1.4",
    ...     dependencies=[dependency],
    ...     raw_hash="sha256:abc123..."
    ... )
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, field_validator


class SBOMFormat(Enum):
    """Supported SBOM formats."""

    CYCLONEDX = "cyclonedx"
    SPDX = "spdx"
    UNKNOWN = "unknown"


class SeverityLevel(Enum):
    """Vulnerability severity levels (CVSS-based)."""

    CRITICAL = "CRITICAL"  # CVSS 9.0-10.0
    HIGH = "HIGH"  # CVSS 7.0-8.9
    MEDIUM = "MEDIUM"  # CVSS 4.0-6.9
    LOW = "LOW"  # CVSS 0.1-3.9
    NONE = "NONE"  # CVSS 0.0
    UNKNOWN = "UNKNOWN"  # Unrated


@dataclass
class Dependency:
    """
    Parsed dependency from SBOM.

    Represents a software component with version information
    and optional Package URL (purl) for precise identification.
    """

    name: str
    version: str
    purl: Optional[str] = None  # Package URL (purl spec)
    license: Optional[str] = None
    ecosystem: Optional[str] = None  # npm, pypi, maven, etc.
    sha256: Optional[str] = None  # Hash of package contents

    def __hash__(self):
        return hash((self.name, self.version, self.purl))

    def __eq__(self, other):
        if not isinstance(other, Dependency):
            return False
        return (
            self.name == other.name
            and self.version == other.version
            and self.purl == other.purl
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "purl": self.purl,
            "license": self.license,
            "ecosystem": self.ecosystem,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dependency":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "unknown"),
            purl=data.get("purl"),
            license=data.get("license"),
            ecosystem=data.get("ecosystem"),
            sha256=data.get("sha256"),
        )

    def get_ecosystem_from_purl(self) -> Optional[str]:
        """Extract ecosystem from Package URL if available."""
        if not self.purl:
            return self.ecosystem

        # purl format: pkg:<ecosystem>/<namespace>/<name>@<version>
        if self.purl.startswith("pkg:"):
            parts = self.purl[4:].split("/")
            if parts:
                return parts[0]

        return self.ecosystem


@dataclass
class VulnerabilityInfo:
    """
    Information about a vulnerability found in a dependency.
    """

    id: str  # CVE-XXXX-XXXXX or similar
    severity: SeverityLevel
    package_name: str
    installed_version: str
    fixed_version: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "package_name": self.package_name,
            "installed_version": self.installed_version,
            "fixed_version": self.fixed_version,
            "title": self.title,
            "description": self.description,
            "cvss_score": self.cvss_score,
            "cvss_vector": self.cvss_vector,
            "references": self.references,
        }


@dataclass
class SBOMData:
    """
    Parsed SBOM data.

    Contains the complete software bill of materials with
    dependency information and metadata.
    """

    format: SBOMFormat
    version: str  # Spec version (e.g., "1.4" for CycloneDX)
    dependencies: List[Dependency]
    raw_hash: str  # SHA256 of raw SBOM document

    # Metadata
    component_name: Optional[str] = None  # Name of the main component
    component_version: Optional[str] = None
    created_at: Optional[datetime] = None
    creator_tool: Optional[str] = None
    signature: Optional[str] = None  # JWS signature if signed

    def get_dependency_count(self) -> int:
        """Get total number of dependencies."""
        return len(self.dependencies)

    def get_dependency_names(self) -> List[str]:
        """Get list of dependency names."""
        return [d.name for d in self.dependencies]

    def get_unique_ecosystems(self) -> Set[str]:
        """Get set of unique ecosystems in the SBOM."""
        ecosystems = set()
        for dep in self.dependencies:
            eco = dep.get_ecosystem_from_purl()
            if eco:
                ecosystems.add(eco)
        return ecosystems

    def get_dependencies_by_ecosystem(self) -> Dict[str, List[Dependency]]:
        """Group dependencies by ecosystem."""
        result: Dict[str, List[Dependency]] = {}
        for dep in self.dependencies:
            eco = dep.get_ecosystem_from_purl() or "unknown"
            if eco not in result:
                result[eco] = []
            result[eco].append(dep)
        return result

    def compute_hash(self) -> str:
        """Compute hash of the SBOM content for binding."""
        content = json.dumps(
            {
                "format": self.format.value,
                "version": self.version,
                "component_name": self.component_name,
                "component_version": self.component_version,
                "dependencies": sorted(
                    [f"{d.name}:{d.version}" for d in self.dependencies]
                ),
            },
            sort_keys=True,
        )
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "format": self.format.value,
            "version": self.version,
            "raw_hash": self.raw_hash,
            "component_name": self.component_name,
            "component_version": self.component_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "creator_tool": self.creator_tool,
            "dependency_count": len(self.dependencies),
            "dependencies": [d.to_dict() for d in self.dependencies],
        }


class SBOMVerificationResult(BaseModel):
    """
    Result of SBOM verification during validation.
    """

    valid: bool = Field(..., description="Whether the SBOM passed verification")
    sbom_hash: str = Field(..., description="SHA256 hash of the SBOM document")
    format: str = Field(..., description="SBOM format (cyclonedx or spdx)")
    dependency_count: int = Field(
        default=0, description="Number of dependencies in SBOM"
    )
    vulnerabilities_found: int = Field(
        default=0, description="Total vulnerabilities found"
    )
    critical_vulns: int = Field(
        default=0, description="Number of CRITICAL severity vulnerabilities"
    )
    high_vulns: int = Field(
        default=0, description="Number of HIGH severity vulnerabilities"
    )
    vulnerabilities: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of vulnerability details"
    )
    errors: List[str] = Field(
        default_factory=list, description="Errors encountered during verification"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Warnings from verification"
    )
    checked_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the verification was performed",
    )

    def has_blocking_vulnerabilities(
        self, block_on_critical: bool = True, block_on_high: bool = False
    ) -> bool:
        """Check if there are vulnerabilities that should block registration."""
        if block_on_critical and self.critical_vulns > 0:
            return True
        if block_on_high and self.high_vulns > 0:
            return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the verification result."""
        return {
            "valid": self.valid,
            "sbom_hash": self.sbom_hash[:32] + "...",
            "format": self.format,
            "dependencies": self.dependency_count,
            "vulnerabilities": {
                "total": self.vulnerabilities_found,
                "critical": self.critical_vulns,
                "high": self.high_vulns,
            },
            "checked_at": self.checked_at.isoformat(),
        }

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "sbom_hash": "sha256:abc123def456...",
                "format": "cyclonedx",
                "dependency_count": 42,
                "vulnerabilities_found": 2,
                "critical_vulns": 0,
                "high_vulns": 1,
                "vulnerabilities": [
                    {
                        "id": "CVE-2024-1234",
                        "severity": "HIGH",
                        "package_name": "requests",
                        "installed_version": "2.28.0",
                        "fixed_version": "2.31.0",
                    }
                ],
                "errors": [],
                "warnings": ["Outdated SBOM format version"],
            }
        }


class SBOMRequest(BaseModel):
    """
    SBOM submission request for agent validation.

    Agents can submit their SBOM during the validation phase
    for dependency tracking and vulnerability checking.
    """

    sbom_content: str = Field(
        ...,
        min_length=100,
        max_length=10_000_000,  # 10MB max
        description="Raw SBOM document content (JSON string)",
    )
    sbom_format: Optional[str] = Field(
        None,
        description="SBOM format hint (cyclonedx or spdx). Auto-detected if not provided.",
    )
    signature: Optional[str] = Field(
        None, description="JWS signature of the SBOM for authenticity verification"
    )

    @field_validator("sbom_content")
    @classmethod
    def validate_sbom_is_json(cls, v: str) -> str:
        """Validate that SBOM content is valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"SBOM content must be valid JSON: {e}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "sbom_content": '{"bomFormat": "CycloneDX", "specVersion": "1.4", ...}',
                "sbom_format": "cyclonedx",
                "signature": None,
            }
        }


# =============================================================================
# SBOM API Request/Response Models
# =============================================================================


class SBOMVerifyRequest(BaseModel):
    """Request to verify an SBOM."""

    sbom_content: str = Field(
        ..., description="SBOM content in CycloneDX or SPDX JSON format"
    )
    agent_id: str = Field(..., description="ID of the agent providing the SBOM")
    signature: Optional[str] = Field(
        None, description="Optional JWS signature for SBOM integrity"
    )
    verify_vulnerabilities: bool = Field(
        True, description="Whether to check dependencies for vulnerabilities"
    )
    fail_on_critical: bool = Field(
        True, description="Fail verification if critical vulnerabilities found"
    )
    fail_on_high: bool = Field(
        False, description="Fail verification if high-severity vulnerabilities found"
    )


class SBOMVerifyResponse(BaseModel):
    """Response from SBOM verification."""

    valid: bool
    format: str
    component_count: int
    dependency_count: int
    vulnerability_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    hash: str
    timestamp: datetime
    warnings: List[str] = []
    error: Optional[str] = None
