"""
Container scanning result models.

Data structures for container image vulnerability scanning
results from Trivy, Grype, or similar scanners.

These models represent the output of container scanning
during the agent validation phase.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScannerType(Enum):
    """Supported container scanner types."""

    TRIVY = "trivy"
    GRYPE = "grype"
    CLAIR = "clair"
    CUSTOM = "custom"


class VulnerabilitySeverity(Enum):
    """Vulnerability severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEGLIGIBLE = "NEGLIGIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class ContainerVulnerability:
    """
    A vulnerability found in a container image.
    """

    id: str  # CVE-XXXX-XXXXX
    severity: VulnerabilitySeverity
    package_name: str
    installed_version: str
    fixed_version: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    layer: Optional[str] = None  # Docker layer hash
    target: Optional[str] = None  # OS, library, etc.

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
            "layer": self.layer,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContainerVulnerability":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            severity=VulnerabilitySeverity(data.get("severity", "UNKNOWN")),
            package_name=data.get("package_name", ""),
            installed_version=data.get("installed_version", ""),
            fixed_version=data.get("fixed_version"),
            title=data.get("title"),
            description=data.get("description"),
            layer=data.get("layer"),
            target=data.get("target"),
        )


@dataclass
class Misconfiguration:
    """
    A misconfiguration found in a container image.
    """

    id: str  # Rule ID
    severity: VulnerabilitySeverity
    title: str
    description: str
    resolution: Optional[str] = None
    file_path: Optional[str] = None
    category: Optional[str] = None  # Security, Compliance, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "resolution": self.resolution,
            "file_path": self.file_path,
            "category": self.category,
        }


@dataclass
class Secret:
    """
    A secret found in a container image.
    """

    rule_id: str
    category: str  # API key, password, etc.
    severity: VulnerabilitySeverity
    title: str
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    match: Optional[str] = None  # Redacted match

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity.value,
            "title": self.title,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass
class ScanResult:
    """
    Complete result of a container image scan.
    """

    image: str
    image_digest: Optional[str]
    scanner: ScannerType
    scanner_version: Optional[str]
    scan_time: float  # Seconds
    scanned_at: datetime

    vulnerabilities: List[ContainerVulnerability] = field(default_factory=list)
    misconfigurations: List[Misconfiguration] = field(default_factory=list)
    secrets: List[Secret] = field(default_factory=list)

    os_family: Optional[str] = None  # alpine, debian, etc.
    os_version: Optional[str] = None

    raw_output: Optional[str] = None  # Original scanner output

    def has_critical(self) -> bool:
        """Check if any CRITICAL vulnerabilities found."""
        return any(
            v.severity == VulnerabilitySeverity.CRITICAL for v in self.vulnerabilities
        )

    def has_high(self) -> bool:
        """Check if any HIGH vulnerabilities found."""
        return any(
            v.severity == VulnerabilitySeverity.HIGH for v in self.vulnerabilities
        )

    def get_vulnerability_summary(self) -> Dict[str, int]:
        """Get count of vulnerabilities by severity."""
        summary = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "NEGLIGIBLE": 0,
            "UNKNOWN": 0,
        }
        for v in self.vulnerabilities:
            summary[v.severity.value] = summary.get(v.severity.value, 0) + 1
        return summary

    def get_total_issues(self) -> int:
        """Get total number of issues found."""
        return (
            len(self.vulnerabilities) + len(self.misconfigurations) + len(self.secrets)
        )

    def passes_policy(
        self, max_critical: int = 0, max_high: int = 0, allow_secrets: bool = False
    ) -> bool:
        """
        Check if scan result passes security policy.

        Args:
            max_critical: Maximum allowed CRITICAL vulnerabilities
            max_high: Maximum allowed HIGH vulnerabilities
            allow_secrets: Whether secrets are allowed

        Returns:
            True if passes policy, False otherwise
        """
        summary = self.get_vulnerability_summary()

        if summary["CRITICAL"] > max_critical:
            return False
        if summary["HIGH"] > max_high:
            return False
        if not allow_secrets and len(self.secrets) > 0:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "image": self.image,
            "image_digest": self.image_digest,
            "scanner": self.scanner.value,
            "scanner_version": self.scanner_version,
            "scan_time": self.scan_time,
            "scanned_at": self.scanned_at.isoformat(),
            "os_family": self.os_family,
            "os_version": self.os_version,
            "vulnerability_summary": self.get_vulnerability_summary(),
            "total_vulnerabilities": len(self.vulnerabilities),
            "total_misconfigurations": len(self.misconfigurations),
            "total_secrets": len(self.secrets),
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "misconfigurations": [m.to_dict() for m in self.misconfigurations],
            "secrets": [s.to_dict() for s in self.secrets],
        }


class ContainerScanRequest(BaseModel):
    """
    Request to scan a container image during agent validation.
    """

    image: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Container image reference (e.g., 'myagent:1.0', 'registry.io/agent:latest')",
    )
    image_digest: Optional[str] = Field(
        None, description="Optional image digest for verification (sha256:...)"
    )
    scanner: Optional[str] = Field(
        None,
        description="Preferred scanner (trivy, grype). Auto-detected if not specified.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "image": "myagent:1.0.0",
                "image_digest": "sha256:abc123def456...",
                "scanner": "trivy",
            }
        }


class ContainerScanResponse(BaseModel):
    """
    Response from container scanning.
    """

    success: bool = Field(..., description="Whether scan completed successfully")
    image: str = Field(..., description="Scanned image reference")
    image_digest: Optional[str] = Field(None, description="Image digest")
    scanner: str = Field(..., description="Scanner used")
    scan_time: float = Field(..., description="Scan duration in seconds")
    passes_policy: bool = Field(..., description="Whether scan passes security policy")

    vulnerability_summary: Dict[str, int] = Field(
        default_factory=dict, description="Count of vulnerabilities by severity"
    )
    total_vulnerabilities: int = Field(
        default=0, description="Total vulnerabilities found"
    )
    total_misconfigurations: int = Field(
        default=0, description="Total misconfigurations found"
    )
    total_secrets: int = Field(default=0, description="Total secrets found")

    # Details (may be truncated for large scans)
    critical_vulnerabilities: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of CRITICAL vulnerability details"
    )
    high_vulnerabilities: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of HIGH vulnerability details"
    )

    errors: List[str] = Field(
        default_factory=list, description="Errors encountered during scan"
    )

    scanned_at: datetime = Field(
        default_factory=datetime.utcnow, description="When scan was performed"
    )

    @classmethod
    def from_scan_result(
        cls, result: ScanResult, policy_passed: bool
    ) -> "ContainerScanResponse":
        """Create response from ScanResult."""
        # Get critical and high vulns for detail
        critical = [
            v.to_dict()
            for v in result.vulnerabilities
            if v.severity == VulnerabilitySeverity.CRITICAL
        ][
            :10
        ]  # Limit to 10

        high = [
            v.to_dict()
            for v in result.vulnerabilities
            if v.severity == VulnerabilitySeverity.HIGH
        ][
            :10
        ]  # Limit to 10

        return cls(
            success=True,
            image=result.image,
            image_digest=result.image_digest,
            scanner=result.scanner.value,
            scan_time=result.scan_time,
            passes_policy=policy_passed,
            vulnerability_summary=result.get_vulnerability_summary(),
            total_vulnerabilities=len(result.vulnerabilities),
            total_misconfigurations=len(result.misconfigurations),
            total_secrets=len(result.secrets),
            critical_vulnerabilities=critical,
            high_vulnerabilities=high,
            scanned_at=result.scanned_at,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "image": "myagent:1.0.0",
                "image_digest": "sha256:abc123...",
                "scanner": "trivy",
                "scan_time": 12.5,
                "passes_policy": True,
                "vulnerability_summary": {
                    "CRITICAL": 0,
                    "HIGH": 2,
                    "MEDIUM": 5,
                    "LOW": 10,
                },
                "total_vulnerabilities": 17,
                "total_misconfigurations": 3,
                "total_secrets": 0,
                "critical_vulnerabilities": [],
                "high_vulnerabilities": [
                    {
                        "id": "CVE-2024-1234",
                        "package_name": "openssl",
                        "installed_version": "1.1.1",
                        "fixed_version": "1.1.1k",
                    }
                ],
            }
        }


# =============================================================================
# Container Scan API Request/Response Models
# =============================================================================


class ContainerScanSubmitRequest(BaseModel):
    """Request to scan a container image."""

    image: str = Field(
        ..., description="Container image reference (e.g., myimage:latest)"
    )
    agent_id: str = Field(..., description="ID of the agent providing the image")
    scanner: Optional[str] = Field(
        None,
        description="Preferred scanner (trivy, grype). Auto-detects if not specified.",
    )
    severity_threshold: str = Field(
        "high", description="Minimum severity to report (critical, high, medium, low)"
    )
    fail_on_critical: bool = Field(
        True, description="Fail if critical vulnerabilities found"
    )
    fail_on_high: bool = Field(
        False, description="Fail if high-severity vulnerabilities found"
    )


class ContainerScanSubmitResponse(BaseModel):
    """Response from container scan."""

    passed: bool
    image: str
    scanner: str
    vulnerability_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    misconfiguration_count: int
    secret_count: int
    scan_time: datetime
    error: Optional[str] = None
    warnings: List[str] = []
