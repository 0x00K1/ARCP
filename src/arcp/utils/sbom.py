"""
SBOM (Software Bill of Materials) parsing and verification.

Parses SBOM documents in CycloneDX and SPDX formats,
extracting dependency information for vulnerability checking
and security binding.

Supported Formats:
- CycloneDX 1.4+ (JSON)
- SPDX 2.2+ (JSON)

Features:
- Automatic format detection
- Dependency extraction with package URL (purl) parsing
- Signature verification (optional)
- Hash computation for security binding

Example Usage:
    >>> from arcp.utils.sbom import SBOMParser, verify_sbom
    >>> parser = SBOMParser()
    >>> sbom_data, error = parser.parse(sbom_json_string)
    >>> if error:
    ...     print(f"Parse error: {error}")
    >>> else:
    ...     print(f"Found {sbom_data.get_dependency_count()} dependencies")

    # Full verification with vulnerability check
    >>> result = await verify_sbom(sbom_json_string)
    >>> if result.valid:
    ...     print("SBOM verified successfully")
"""

import base64
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import jwt

from ..core.config import config
from ..models.sbom import (
    Dependency,
    SBOMData,
    SBOMFormat,
    SBOMVerificationResult,
    SeverityLevel,
    VulnerabilityInfo,
)
from ..services.vulnerability import check_dependencies_for_vulnerabilities

logger = logging.getLogger(__name__)


class SBOMParser:
    """
    Parse and validate SBOM documents.

    Supports CycloneDX and SPDX formats, automatically detecting
    the format based on document structure.
    """

    # Minimum spec versions we support
    MIN_CYCLONEDX_VERSION = "1.4"
    MIN_SPDX_VERSION = "SPDX-2.2"

    def detect_format(self, sbom_data: Dict[str, Any]) -> SBOMFormat:
        """
        Detect SBOM format from document content.

        Args:
            sbom_data: Parsed JSON dictionary

        Returns:
            Detected SBOMFormat
        """
        # Check for CycloneDX
        if sbom_data.get("bomFormat") == "CycloneDX":
            return SBOMFormat.CYCLONEDX

        # Check for SPDX
        if "spdxVersion" in sbom_data:
            return SBOMFormat.SPDX

        # Check for CycloneDX alternative indicators
        if "specVersion" in sbom_data and "components" in sbom_data:
            return SBOMFormat.CYCLONEDX

        return SBOMFormat.UNKNOWN

    def parse(self, sbom_json: str) -> Tuple[Optional[SBOMData], Optional[str]]:
        """
        Parse SBOM JSON string.

        Args:
            sbom_json: Raw SBOM JSON string

        Returns:
            Tuple of (SBOMData, error_message)
        """
        try:
            data = json.loads(sbom_json)
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON: {e}"

        format_type = self.detect_format(data)

        if format_type == SBOMFormat.UNKNOWN:
            return None, "Unknown SBOM format. Supported: CycloneDX, SPDX"

        # Compute hash of raw SBOM
        raw_hash = f"sha256:{hashlib.sha256(sbom_json.encode()).hexdigest()}"

        try:
            if format_type == SBOMFormat.CYCLONEDX:
                return self._parse_cyclonedx(data, raw_hash)
            else:
                return self._parse_spdx(data, raw_hash)
        except Exception as e:
            logger.error(f"SBOM parse error: {e}", exc_info=True)
            return None, f"Parse error: {e}"

    def _parse_cyclonedx(
        self, data: Dict[str, Any], raw_hash: str
    ) -> Tuple[SBOMData, None]:
        """
        Parse CycloneDX format SBOM.

        CycloneDX Structure:
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "metadata": {
                "component": {"name": "...", "version": "..."},
                "timestamp": "...",
                "tools": [...]
            },
            "components": [
                {
                    "type": "library",
                    "name": "...",
                    "version": "...",
                    "purl": "pkg:pypi/...",
                    "licenses": [...]
                }
            ]
        }
        """
        spec_version = data.get("specVersion", "1.4")

        # Validate version
        warnings = []
        if spec_version < self.MIN_CYCLONEDX_VERSION:
            warnings.append(
                f"CycloneDX version {spec_version} is older than recommended {self.MIN_CYCLONEDX_VERSION}"
            )

        # Extract metadata
        metadata = data.get("metadata", {})
        main_component = metadata.get("component", {})

        component_name = main_component.get("name")
        component_version = main_component.get("version")

        # Parse timestamp
        created_at = None
        timestamp_str = metadata.get("timestamp")
        if timestamp_str:
            try:
                # Handle ISO format with Z or +00:00
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1] + "+00:00"
                created_at = datetime.fromisoformat(timestamp_str)
            except ValueError:
                pass

        # Extract tool info
        creator_tool = None
        tools = metadata.get("tools", [])
        if tools and isinstance(tools, list) and len(tools) > 0:
            tool = tools[0]
            if isinstance(tool, dict):
                creator_tool = f"{tool.get('vendor', '')}/{tool.get('name', '')}".strip(
                    "/"
                )

        # Parse components
        components = data.get("components", [])
        dependencies = []

        for comp in components:
            if not isinstance(comp, dict):
                continue

            name = comp.get("name")
            version = comp.get("version", "unknown")

            if not name:
                continue

            dep = Dependency(
                name=name,
                version=version,
                purl=comp.get("purl"),
                license=self._extract_license_cyclonedx(comp),
                ecosystem=self._extract_ecosystem_from_type(comp.get("type")),
                sha256=self._extract_hash_cyclonedx(comp),
            )
            dependencies.append(dep)

        # Extract signature if present
        signature = None
        sig_data = data.get("signature")
        if sig_data and isinstance(sig_data, dict):
            signature = sig_data.get("value")

        return (
            SBOMData(
                format=SBOMFormat.CYCLONEDX,
                version=spec_version,
                dependencies=dependencies,
                raw_hash=raw_hash,
                component_name=component_name,
                component_version=component_version,
                created_at=created_at,
                creator_tool=creator_tool,
                signature=signature,
            ),
            None,
        )

    def _parse_spdx(self, data: Dict[str, Any], raw_hash: str) -> Tuple[SBOMData, None]:
        """
        Parse SPDX format SBOM.

        SPDX Structure:
        {
            "spdxVersion": "SPDX-2.3",
            "name": "...",
            "packages": [
                {
                    "name": "...",
                    "versionInfo": "...",
                    "externalRefs": [
                        {"referenceType": "purl", "referenceLocator": "pkg:..."}
                    ],
                    "licenseDeclared": "MIT"
                }
            ],
            "creationInfo": {
                "created": "...",
                "creators": [...]
            }
        }
        """
        spdx_version = data.get("spdxVersion", "SPDX-2.2")

        # Extract creation info
        creation_info = data.get("creationInfo", {})
        created_at = None
        created_str = creation_info.get("created")
        if created_str:
            try:
                if created_str.endswith("Z"):
                    created_str = created_str[:-1] + "+00:00"
                created_at = datetime.fromisoformat(created_str)
            except ValueError:
                pass

        # Extract creator tool
        creator_tool = None
        creators = creation_info.get("creators", [])
        for creator in creators:
            if isinstance(creator, str) and creator.startswith("Tool:"):
                creator_tool = creator[5:].strip()
                break

        # Main component (from document name or first package)
        component_name = data.get("name")
        component_version = None

        # Parse packages
        packages = data.get("packages", [])
        dependencies = []

        for pkg in packages:
            if not isinstance(pkg, dict):
                continue

            name = pkg.get("name")
            version = pkg.get("versionInfo", "unknown")

            if not name:
                continue

            # Skip root package (usually the main component)
            spdx_id = pkg.get("SPDXID", "")
            if spdx_id == "SPDXRef-DOCUMENT":
                component_name = name
                component_version = version
                continue

            dep = Dependency(
                name=name,
                version=version,
                purl=self._extract_purl_spdx(pkg),
                license=pkg.get("licenseDeclared"),
                sha256=self._extract_hash_spdx(pkg),
            )
            dependencies.append(dep)

        return (
            SBOMData(
                format=SBOMFormat.SPDX,
                version=spdx_version,
                dependencies=dependencies,
                raw_hash=raw_hash,
                component_name=component_name,
                component_version=component_version,
                created_at=created_at,
                creator_tool=creator_tool,
            ),
            None,
        )

    def _extract_license_cyclonedx(self, component: Dict[str, Any]) -> Optional[str]:
        """Extract license from CycloneDX component."""
        licenses = component.get("licenses", [])
        if not licenses:
            return None

        if isinstance(licenses, list) and len(licenses) > 0:
            license_entry = licenses[0]
            if isinstance(license_entry, dict):
                # Check for license ID
                license_obj = license_entry.get("license", {})
                if isinstance(license_obj, dict):
                    return license_obj.get("id") or license_obj.get("name")
                # Check for expression
                if "expression" in license_entry:
                    return license_entry["expression"]

        return None

    def _extract_hash_cyclonedx(self, component: Dict[str, Any]) -> Optional[str]:
        """Extract SHA256 hash from CycloneDX component."""
        hashes = component.get("hashes", [])
        for h in hashes:
            if isinstance(h, dict) and h.get("alg") == "SHA-256":
                return h.get("content")
        return None

    def _extract_purl_spdx(self, package: Dict[str, Any]) -> Optional[str]:
        """Extract package URL from SPDX package."""
        refs = package.get("externalRefs", [])
        for ref in refs:
            if isinstance(ref, dict):
                ref_type = ref.get("referenceType") or ref.get("referenceCategory")
                if ref_type in ("purl", "PACKAGE-MANAGER"):
                    return ref.get("referenceLocator")
        return None

    def _extract_hash_spdx(self, package: Dict[str, Any]) -> Optional[str]:
        """Extract SHA256 hash from SPDX package."""
        checksums = package.get("checksums", [])
        for cs in checksums:
            if isinstance(cs, dict) and cs.get("algorithm") == "SHA256":
                return cs.get("checksumValue")
        return None

    def _extract_ecosystem_from_type(self, comp_type: Optional[str]) -> Optional[str]:
        """Map CycloneDX component type to ecosystem."""
        # CycloneDX types don't directly map to ecosystems
        # The ecosystem is better extracted from purl
        return None


async def verify_sbom(
    sbom_json: str, check_vulnerabilities: bool = True
) -> SBOMVerificationResult:
    """
    Verify SBOM and optionally check for vulnerabilities.

    Args:
        sbom_json: Raw SBOM JSON string
        check_vulnerabilities: Whether to check dependency vulnerabilities

    Returns:
        SBOMVerificationResult with verification outcome
    """
    parser = SBOMParser()
    errors: List[str] = []
    warnings: List[str] = []
    vulnerabilities: List[VulnerabilityInfo] = []

    # Parse SBOM
    sbom_data, parse_error = parser.parse(sbom_json)

    if parse_error:
        return SBOMVerificationResult(
            valid=False,
            sbom_hash="",
            format="unknown",
            dependency_count=0,
            errors=[parse_error],
        )

    logger.info(
        f"Parsed SBOM: format={sbom_data.format.value}, "
        f"dependencies={sbom_data.get_dependency_count()}"
    )

    # Check for vulnerabilities if enabled
    if check_vulnerabilities and getattr(config, "SBOM_VULN_CHECK_ENABLED", True):
        try:
            vulnerabilities = await check_dependencies_for_vulnerabilities(
                sbom_data.dependencies
            )
        except ImportError:
            warnings.append("Vulnerability checking service not available")
        except Exception as e:
            logger.error(f"Vulnerability check failed: {e}")
            warnings.append(f"Vulnerability check failed: {str(e)}")

    # Count vulnerabilities by severity
    critical_count = sum(
        1 for v in vulnerabilities if v.severity == SeverityLevel.CRITICAL
    )
    high_count = sum(1 for v in vulnerabilities if v.severity == SeverityLevel.HIGH)

    # Determine if valid based on config
    block_critical = getattr(config, "SBOM_BLOCK_CRITICAL", True)
    block_high = getattr(config, "SBOM_BLOCK_HIGH", False)

    is_valid = True
    if block_critical and critical_count > 0:
        is_valid = False
        errors.append(f"Found {critical_count} CRITICAL vulnerabilities")
    if block_high and high_count > 0:
        is_valid = False
        errors.append(f"Found {high_count} HIGH vulnerabilities")

    return SBOMVerificationResult(
        valid=is_valid,
        sbom_hash=sbom_data.raw_hash,
        format=sbom_data.format.value,
        dependency_count=sbom_data.get_dependency_count(),
        vulnerabilities_found=len(vulnerabilities),
        critical_vulns=critical_count,
        high_vulns=high_count,
        vulnerabilities=[v.to_dict() for v in vulnerabilities],
        errors=errors,
        warnings=warnings,
    )


def validate_sbom_signature(
    sbom_json: str, signature: str, public_key: str
) -> Tuple[bool, Optional[str]]:
    """
    Verify SBOM signature using JWS.

    Args:
        sbom_json: Raw SBOM content
        signature: JWS signature
        public_key: PEM or JWK public key

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # The signature should be a detached JWS
        # Reconstruct the full JWS with payload
        parts = signature.split(".")
        if len(parts) != 3:
            return False, "Invalid JWS format"

        header, _, sig = parts

        # Base64url encode the payload
        payload_b64 = base64.urlsafe_b64encode(sbom_json.encode()).rstrip(b"=").decode()

        full_jws = f"{header}.{payload_b64}.{sig}"

        # Verify
        jwt.decode(full_jws, public_key, algorithms=["ES256", "EdDSA", "RS256"])
        return True, None

    except jwt.InvalidSignatureError:
        return False, "Signature verification failed"
    except Exception as e:
        return False, f"Signature verification error: {str(e)}"


# Convenience function
def get_sbom_parser() -> SBOMParser:
    """Get SBOM parser instance."""
    return SBOMParser()
