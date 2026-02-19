"""
Container scanning service for agent validation.

Integrates with Trivy or Grype to scan container images
for vulnerabilities, misconfigurations, and secrets.

This service runs during the validation phase to ensure
agent container images meet security requirements before
registration.

Features:
- Trivy and Grype integration
- Vulnerability scanning
- Misconfiguration detection
- Secret scanning
- Policy-based blocking
- Scan result caching

Environment Variables:
    CONTAINER_SCAN_ENABLED: Enable container scanning (default: false)
    CONTAINER_SCANNER: Preferred scanner (trivy, grype) (default: trivy)
    CONTAINER_SCAN_TIMEOUT: Scan timeout in seconds (default: 300)
    CONTAINER_SCAN_CACHE_TTL: Cache TTL in seconds (default: 3600)
    CONTAINER_MAX_CRITICAL: Max CRITICAL vulns allowed (default: 0)
    CONTAINER_MAX_HIGH: Max HIGH vulns allowed (default: 5)

Example Usage:
    >>> from arcp.services.container_scanner import scan_container_image
    >>> result = await scan_container_image("myagent:1.0")
    >>> if result.passes_policy():
    ...     print("Image is secure")
    >>> else:
    ...     print(f"Found {len(result.vulnerabilities)} vulnerabilities")
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import config
from ..models.scan_result import (
    ContainerVulnerability,
    Misconfiguration,
    ScannerType,
    ScanResult,
    Secret,
    VulnerabilitySeverity,
)
from ..services.redis import get_redis_service
from ..utils.security_audit import SecurityEventType, log_security_event

logger = logging.getLogger(__name__)

# Cache key prefix for scan results
SCAN_CACHE_PREFIX = "arcp:container:scan:"


class ContainerScanner:
    """
    Scan container images for vulnerabilities.

    Supports Trivy and Grype scanners, automatically detecting
    which is available on the system.
    """

    def __init__(self):
        self.enabled = getattr(config, "CONTAINER_SCAN_ENABLED", False)
        self.preferred_scanner = getattr(config, "CONTAINER_SCANNER", "trivy")
        self.timeout = getattr(config, "CONTAINER_SCAN_TIMEOUT", 300)
        self.cache_ttl = getattr(config, "CONTAINER_SCAN_CACHE_TTL", 3600)

        # Policy settings
        self.max_critical = getattr(config, "CONTAINER_MAX_CRITICAL", 0)
        self.max_high = getattr(config, "CONTAINER_MAX_HIGH", 5)
        self.allow_secrets = getattr(config, "CONTAINER_ALLOW_SECRETS", False)

        self._redis = None
        self._available_scanner: Optional[ScannerType] = None

    @property
    def scanner_type(self) -> Optional[ScannerType]:
        """Get the detected scanner type."""
        return self._detect_available_scanner()

    def is_available(self) -> bool:
        """Check if a container scanner is available on the system."""
        return self._detect_available_scanner() is not None

    def _get_redis(self):
        """Get Redis client for caching."""
        if self._redis is None:
            try:
                redis_service = get_redis_service()
                if redis_service and redis_service.is_available():
                    self._redis = redis_service.get_client()
            except Exception:
                pass
        return self._redis

    def _detect_available_scanner(self) -> Optional[ScannerType]:
        """Detect which scanner is available on the system."""
        if self._available_scanner is not None:
            return self._available_scanner

        # Check preferred scanner first
        if self.preferred_scanner.lower() == "trivy":
            trivy_path = shutil.which("trivy")
            if trivy_path:
                logger.info(f"Container scanner detected: Trivy at {trivy_path}")
                self._available_scanner = ScannerType.TRIVY
                return self._available_scanner
            grype_path = shutil.which("grype")
            if grype_path:
                logger.info(f"Container scanner detected: Grype at {grype_path}")
                self._available_scanner = ScannerType.GRYPE
                return self._available_scanner
        else:
            grype_path = shutil.which("grype")
            if grype_path:
                logger.info(f"Container scanner detected: Grype at {grype_path}")
                self._available_scanner = ScannerType.GRYPE
                return self._available_scanner
            trivy_path = shutil.which("trivy")
            if trivy_path:
                logger.info(f"Container scanner detected: Trivy at {trivy_path}")
                self._available_scanner = ScannerType.TRIVY
                return self._available_scanner

        logger.warning(
            "No container scanner found. Install Trivy or Grype for container scanning. "
            f"Searched PATH: {os.environ.get('PATH', 'NOT SET')[:200]}..."
        )
        return None

    def _get_cache_key(self, image: str, digest: Optional[str] = None) -> str:
        """Generate cache key for an image scan."""
        key_data = f"{image}:{digest or 'latest'}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{SCAN_CACHE_PREFIX}{key_hash}"

    async def _get_cached(self, cache_key: str) -> Optional[ScanResult]:
        """Get cached scan result."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            data = redis.get(cache_key)
            if data:
                result_dict = json.loads(data)
                return self._dict_to_scan_result(result_dict)
        except Exception as e:
            logger.debug(f"Cache get error: {e}")

        return None

    async def _set_cached(self, cache_key: str, result: ScanResult) -> None:
        """Cache scan result."""
        redis = self._get_redis()
        if not redis:
            return

        try:
            # Don't cache raw_output to save space
            result_dict = result.to_dict()
            result_dict.pop("raw_output", None)
            redis.setex(cache_key, self.cache_ttl, json.dumps(result_dict, default=str))
        except Exception as e:
            logger.debug(f"Cache set error: {e}")

    async def scan(
        self,
        image: str,
        digest: Optional[str] = None,
        force_rescan: bool = False,
        agent_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Tuple[Optional[ScanResult], Optional[str]]:
        """
        Scan a container image for vulnerabilities.

        Args:
            image: Image reference (e.g., "myagent:1.0", "registry.io/agent:latest")
            digest: Optional image digest for verification
            force_rescan: Skip cache and force fresh scan
            agent_id: Optional agent ID for audit logging
            client_ip: Optional client IP for audit logging

        Returns:
            Tuple of (ScanResult, error_message)
        """
        if not self.enabled:
            return None, "Container scanning is disabled"

        # Check cache first
        if not force_rescan:
            cache_key = self._get_cache_key(image, digest)
            cached = await self._get_cached(cache_key)
            if cached:
                logger.info(f"Using cached scan result for {image}")
                return cached, None

        # Detect available scanner
        scanner = self._detect_available_scanner()
        if not scanner:
            return None, "No container scanner available. Install Trivy or Grype."

        logger.info(f"Scanning image {image} with {scanner.value}")

        try:
            if scanner == ScannerType.TRIVY:
                result, error = await self._scan_trivy(image, digest)
            else:
                result, error = await self._scan_grype(image, digest)

            if error:
                return None, error

            # Log successful scan
            if result:
                await log_security_event(
                    event_type=SecurityEventType.CONTAINER_SCAN_SUCCESS,
                    message=f"Container scan completed for {image}",
                    agent_id=agent_id,
                    client_ip=client_ip,
                    details={
                        "image": image,
                        "scanner": scanner.value,
                        "vulnerabilities_count": len(result.vulnerabilities),
                        "critical_count": len(
                            [
                                v
                                for v in result.vulnerabilities
                                if v.severity == VulnerabilitySeverity.CRITICAL
                            ]
                        ),
                        "high_count": len(
                            [
                                v
                                for v in result.vulnerabilities
                                if v.severity == VulnerabilitySeverity.HIGH
                            ]
                        ),
                        "secrets_count": len(result.secrets) if result.secrets else 0,
                        "passes_policy": result.passes_policy(
                            self.max_critical, self.max_high
                        ),
                    },
                )

                # Log vulnerability detection if any critical/high found
                critical_vulns = [
                    v
                    for v in result.vulnerabilities
                    if v.severity == VulnerabilitySeverity.CRITICAL
                ]
                high_vulns = [
                    v
                    for v in result.vulnerabilities
                    if v.severity == VulnerabilitySeverity.HIGH
                ]

                if critical_vulns or high_vulns:
                    await log_security_event(
                        event_type=SecurityEventType.CONTAINER_VULNERABILITY_DETECTED,
                        message=f"Found {len(critical_vulns)} critical and {len(high_vulns)} high vulnerabilities in {image}",
                        agent_id=agent_id,
                        client_ip=client_ip,
                        details={
                            "image": image,
                            "critical_count": len(critical_vulns),
                            "high_count": len(high_vulns),
                            "critical_ids": [
                                v.id for v in critical_vulns[:5]
                            ],  # First 5
                            "high_ids": [v.id for v in high_vulns[:5]],  # First 5
                        },
                    )

                # Log secret detection if any found
                if result.secrets:
                    await log_security_event(
                        event_type=SecurityEventType.CONTAINER_SECRET_DETECTED,
                        message=f"Found {len(result.secrets)} secrets in {image}",
                        agent_id=agent_id,
                        client_ip=client_ip,
                        details={
                            "image": image,
                            "secrets_count": len(result.secrets),
                            "secret_types": list(
                                set(s.rule_id for s in result.secrets)
                            ),
                        },
                    )

            # Cache the result
            cache_key = self._get_cache_key(image, digest)
            await self._set_cached(cache_key, result)

            return result, None

        except Exception as e:
            logger.error(f"Container scan error: {e}", exc_info=True)

            # Log scan failure
            await log_security_event(
                event_type=SecurityEventType.CONTAINER_SCAN_FAILURE,
                message=f"Container scan failed for {image}: {str(e)}",
                agent_id=agent_id,
                client_ip=client_ip,
                details={
                    "image": image,
                    "scanner": scanner.value if scanner else "none",
                    "error": str(e),
                },
            )

            return None, f"Scan error: {str(e)}"

    async def _scan_trivy(
        self, image: str, digest: Optional[str] = None
    ) -> Tuple[Optional[ScanResult], Optional[str]]:
        """
        Run Trivy scanner.

        Trivy output format:
        {
            "Results": [
                {
                    "Target": "alpine (alpine 3.18.4)",
                    "Class": "os-pkgs",
                    "Type": "alpine",
                    "Vulnerabilities": [...]
                }
            ],
            "Metadata": {
                "ImageID": "sha256:...",
                "OS": {"Family": "alpine", "Name": "3.18.4"}
            }
        }
        """
        start_time = time.time()

        # Build command
        cmd = [
            "trivy",
            "image",
            "--format",
            "json",
            "--severity",
            "CRITICAL,HIGH,MEDIUM,LOW",
            "--no-progress",
            "--timeout",
            f"{self.timeout}s",
        ]

        # Add secret scanning
        cmd.extend(["--scanners", "vuln,secret,misconfig"])

        # Add image reference
        image_ref = image
        if digest:
            image_ref = f"{image}@{digest}"
        cmd.append(image_ref)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )

            if process.returncode != 0:
                # Trivy returns non-zero for some warnings, check if we got output
                if not stdout:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    return None, f"Trivy error: {error_msg}"

            # Parse JSON output
            output_str = stdout.decode()
            result_json = json.loads(output_str)

            # Parse result
            scan_time = time.time() - start_time
            result = self._parse_trivy_result(
                result_json, image, digest, scan_time, output_str
            )

            return result, None

        except asyncio.TimeoutError:
            return None, f"Scan timeout after {self.timeout}s"
        except json.JSONDecodeError as e:
            return None, f"Invalid Trivy output: {e}"
        except FileNotFoundError:
            return None, "Trivy not found in PATH"

    async def _scan_grype(
        self, image: str, digest: Optional[str] = None
    ) -> Tuple[Optional[ScanResult], Optional[str]]:
        """
        Run Grype scanner.

        Grype output format:
        {
            "matches": [
                {
                    "vulnerability": {"id": "CVE-...", "severity": "High"},
                    "artifact": {"name": "pkg", "version": "1.0"}
                }
            ],
            "source": {"type": "image", "target": {...}}
        }
        """
        start_time = time.time()

        # Build command
        cmd = [
            "grype",
            "--output",
            "json",
        ]

        # Add image reference
        image_ref = image
        if digest:
            image_ref = f"{image}@{digest}"
        cmd.append(image_ref)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )

            if process.returncode != 0:
                if not stdout:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    return None, f"Grype error: {error_msg}"

            # Parse JSON output
            output_str = stdout.decode()
            result_json = json.loads(output_str)

            # Parse result
            scan_time = time.time() - start_time
            result = self._parse_grype_result(
                result_json, image, digest, scan_time, output_str
            )

            return result, None

        except asyncio.TimeoutError:
            return None, f"Scan timeout after {self.timeout}s"
        except json.JSONDecodeError as e:
            return None, f"Invalid Grype output: {e}"
        except FileNotFoundError:
            return None, "Grype not found in PATH"

    def _parse_trivy_result(
        self,
        result: Dict[str, Any],
        image: str,
        digest: Optional[str],
        scan_time: float,
        raw_output: str,
    ) -> ScanResult:
        """Parse Trivy JSON output."""
        vulnerabilities = []
        misconfigurations = []
        secrets = []

        # Extract OS info
        metadata = result.get("Metadata", {})
        os_info = metadata.get("OS", {})
        os_family = os_info.get("Family")
        os_version = os_info.get("Name")
        image_digest = metadata.get("ImageID")

        # Parse results
        results = result.get("Results", [])
        for target_result in results:
            target = target_result.get("Target", "")

            # Parse vulnerabilities
            vulns = target_result.get("Vulnerabilities", [])
            for vuln in vulns:
                if not isinstance(vuln, dict):
                    continue

                vulnerabilities.append(
                    ContainerVulnerability(
                        id=vuln.get("VulnerabilityID", ""),
                        severity=self._parse_severity(vuln.get("Severity", "UNKNOWN")),
                        package_name=vuln.get("PkgName", ""),
                        installed_version=vuln.get("InstalledVersion", ""),
                        fixed_version=vuln.get("FixedVersion"),
                        title=vuln.get("Title"),
                        description=(
                            vuln.get("Description", "")[:500]
                            if vuln.get("Description")
                            else None
                        ),
                        layer=(
                            vuln.get("Layer", {}).get("DiffID")
                            if isinstance(vuln.get("Layer"), dict)
                            else None
                        ),
                        target=target,
                    )
                )

            # Parse misconfigurations
            misconfigs = target_result.get("Misconfigurations", [])
            for mc in misconfigs:
                if not isinstance(mc, dict):
                    continue

                misconfigurations.append(
                    Misconfiguration(
                        id=mc.get("ID", ""),
                        severity=self._parse_severity(mc.get("Severity", "UNKNOWN")),
                        title=mc.get("Title", ""),
                        description=(
                            mc.get("Description", "")[:500]
                            if mc.get("Description")
                            else ""
                        ),
                        resolution=mc.get("Resolution"),
                        file_path=mc.get("Target"),
                        category=mc.get("Type"),
                    )
                )

            # Parse secrets
            found_secrets = target_result.get("Secrets", [])
            for sec in found_secrets:
                if not isinstance(sec, dict):
                    continue

                secrets.append(
                    Secret(
                        rule_id=sec.get("RuleID", ""),
                        category=sec.get("Category", ""),
                        severity=self._parse_severity(sec.get("Severity", "HIGH")),
                        title=sec.get("Title", ""),
                        file_path=sec.get("Target", ""),
                        start_line=sec.get("StartLine"),
                        end_line=sec.get("EndLine"),
                    )
                )

        return ScanResult(
            image=image,
            image_digest=digest or image_digest,
            scanner=ScannerType.TRIVY,
            scanner_version=None,  # Could extract from output
            scan_time=scan_time,
            scanned_at=datetime.utcnow(),
            vulnerabilities=vulnerabilities,
            misconfigurations=misconfigurations,
            secrets=secrets,
            os_family=os_family,
            os_version=os_version,
            raw_output=raw_output if len(raw_output) < 100000 else None,
        )

    def _parse_grype_result(
        self,
        result: Dict[str, Any],
        image: str,
        digest: Optional[str],
        scan_time: float,
        raw_output: str,
    ) -> ScanResult:
        """Parse Grype JSON output."""
        vulnerabilities = []

        # Extract image info
        source = result.get("source", {})
        target_info = source.get("target", {})
        image_digest = target_info.get("manifestDigest")

        # Parse distro info
        distro = result.get("distro", {})
        os_family = distro.get("id")
        os_version = distro.get("version")

        # Parse matches (vulnerabilities)
        matches = result.get("matches", [])
        for match in matches:
            if not isinstance(match, dict):
                continue

            vuln = match.get("vulnerability", {})
            artifact = match.get("artifact", {})

            vulnerabilities.append(
                ContainerVulnerability(
                    id=vuln.get("id", ""),
                    severity=self._parse_severity(vuln.get("severity", "UNKNOWN")),
                    package_name=artifact.get("name", ""),
                    installed_version=artifact.get("version", ""),
                    fixed_version=self._get_grype_fix(vuln),
                    title=(
                        vuln.get("description", "")[:200]
                        if vuln.get("description")
                        else None
                    ),
                    description=(
                        vuln.get("description", "")[:500]
                        if vuln.get("description")
                        else None
                    ),
                    target=artifact.get("type"),
                )
            )

        return ScanResult(
            image=image,
            image_digest=digest or image_digest,
            scanner=ScannerType.GRYPE,
            scanner_version=None,
            scan_time=scan_time,
            scanned_at=datetime.utcnow(),
            vulnerabilities=vulnerabilities,
            misconfigurations=[],  # Grype doesn't do misconfiguration scanning
            secrets=[],  # Grype doesn't do secret scanning
            os_family=os_family,
            os_version=os_version,
            raw_output=raw_output if len(raw_output) < 100000 else None,
        )

    def _get_grype_fix(self, vuln: Dict[str, Any]) -> Optional[str]:
        """Extract fixed version from Grype vulnerability."""
        fix = vuln.get("fix", {})
        if isinstance(fix, dict):
            versions = fix.get("versions", [])
            if versions:
                return versions[0]
        return None

    def _parse_severity(self, severity_str: str) -> VulnerabilitySeverity:
        """Parse severity string to enum."""
        mapping = {
            "CRITICAL": VulnerabilitySeverity.CRITICAL,
            "HIGH": VulnerabilitySeverity.HIGH,
            "MEDIUM": VulnerabilitySeverity.MEDIUM,
            "MODERATE": VulnerabilitySeverity.MEDIUM,
            "LOW": VulnerabilitySeverity.LOW,
            "NEGLIGIBLE": VulnerabilitySeverity.NEGLIGIBLE,
        }
        return mapping.get(severity_str.upper(), VulnerabilitySeverity.UNKNOWN)

    def _dict_to_scan_result(self, data: Dict[str, Any]) -> ScanResult:
        """Convert cached dictionary to ScanResult."""
        return ScanResult(
            image=data.get("image", ""),
            image_digest=data.get("image_digest"),
            scanner=ScannerType(data.get("scanner", "trivy")),
            scanner_version=data.get("scanner_version"),
            scan_time=data.get("scan_time", 0),
            scanned_at=datetime.fromisoformat(
                data.get("scanned_at", datetime.utcnow().isoformat())
            ),
            vulnerabilities=[
                ContainerVulnerability.from_dict(v)
                for v in data.get("vulnerabilities", [])
            ],
            misconfigurations=[],  # Simplified for cache
            secrets=[],
            os_family=data.get("os_family"),
            os_version=data.get("os_version"),
        )

    def check_policy(self, result: ScanResult) -> Tuple[bool, List[str]]:
        """
        Check if scan result passes security policy.

        Returns:
            Tuple of (passes, list of policy violations)
        """
        violations = []

        summary = result.get_vulnerability_summary()

        if summary["CRITICAL"] > self.max_critical:
            violations.append(
                f"Found {summary['CRITICAL']} CRITICAL vulnerabilities "
                f"(max allowed: {self.max_critical})"
            )

        if summary["HIGH"] > self.max_high:
            violations.append(
                f"Found {summary['HIGH']} HIGH vulnerabilities "
                f"(max allowed: {self.max_high})"
            )

        if not self.allow_secrets and len(result.secrets) > 0:
            violations.append(f"Found {len(result.secrets)} secrets in image")

        return len(violations) == 0, violations


# Module-level singleton
_container_scanner: Optional[ContainerScanner] = None


def get_container_scanner() -> ContainerScanner:
    """Get the container scanner singleton."""
    global _container_scanner
    if _container_scanner is None:
        _container_scanner = ContainerScanner()
    return _container_scanner


async def scan_container_image(
    image: str,
    digest: Optional[str] = None,
    force_rescan: bool = False,
    agent_id: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> Tuple[Optional[ScanResult], Optional[str]]:
    """
    Convenience function to scan a container image.

    Args:
        image: Image reference
        digest: Optional image digest
        force_rescan: Skip cache and force fresh scan
        agent_id: Optional agent ID for audit logging
        client_ip: Optional client IP for audit logging

    Returns:
        Tuple of (ScanResult, error_message)
    """
    scanner = get_container_scanner()
    return await scanner.scan(image, digest, force_rescan, agent_id, client_ip)


def is_scanning_available() -> bool:
    """Check if container scanning is available."""
    scanner = get_container_scanner()
    return scanner._detect_available_scanner() is not None
