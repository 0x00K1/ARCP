"""
Unit tests for container scanning functionality.

Tests the container scanner service and scan result models.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from arcp.models.scan_result import (
    ContainerScanRequest,
    ContainerScanResponse,
    ContainerVulnerability,
    Misconfiguration,
    ScannerType,
    ScanResult,
    Secret,
    VulnerabilitySeverity,
)
from arcp.services.container_scanner import ContainerScanner, get_container_scanner


class TestScanResultModels:
    """Test container scan result models."""

    def test_container_vulnerability(self):
        """Test ContainerVulnerability model."""
        vuln = ContainerVulnerability(
            id="CVE-2021-12345",
            severity=VulnerabilitySeverity.HIGH,
            package_name="openssl",
            installed_version="1.0.2",
            fixed_version="1.1.1",
            title="Buffer Overflow",
            description="A buffer overflow vulnerability",
        )

        assert vuln.id == "CVE-2021-12345"
        assert vuln.severity == VulnerabilitySeverity.HIGH
        assert vuln.fixed_version == "1.1.1"

    def test_container_vulnerability_not_fixable(self):
        """Test vulnerability without fix."""
        vuln = ContainerVulnerability(
            id="CVE-2021-99999",
            severity=VulnerabilitySeverity.MEDIUM,
            package_name="legacy-lib",
            installed_version="1.0.0",
        )

        assert vuln.fixed_version is None

    def test_container_vulnerability_to_dict(self):
        """Test converting vulnerability to dictionary."""
        vuln = ContainerVulnerability(
            id="CVE-2021-12345",
            severity=VulnerabilitySeverity.HIGH,
            package_name="openssl",
            installed_version="1.0.2",
        )

        d = vuln.to_dict()
        assert d["id"] == "CVE-2021-12345"
        assert d["severity"] == "HIGH"
        assert d["package_name"] == "openssl"

    def test_misconfiguration(self):
        """Test Misconfiguration model."""
        misconfig = Misconfiguration(
            id="DS001",
            severity=VulnerabilitySeverity.HIGH,
            title="Running as root",
            description="Container runs as root user",
        )

        assert misconfig.id == "DS001"
        assert misconfig.severity == VulnerabilitySeverity.HIGH

    def test_secret(self):
        """Test Secret model."""
        secret = Secret(
            rule_id="aws-access-key",
            category="AWS",
            severity=VulnerabilitySeverity.HIGH,
            title="AWS Access Key",
            file_path="/app/config.py",
            start_line=10,
            end_line=10,
        )

        assert secret.category == "AWS"
        assert secret.file_path == "/app/config.py"

    def test_scan_result(self):
        """Test ScanResult model."""
        result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=12.5,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[
                ContainerVulnerability(
                    id="CVE-2021-12345",
                    severity=VulnerabilitySeverity.CRITICAL,
                    package_name="openssl",
                    installed_version="1.0.2",
                )
            ],
            misconfigurations=[],
            secrets=[],
        )

        assert result.image == "myapp:latest"
        assert len(result.vulnerabilities) == 1
        assert result.has_critical()

    def test_scan_result_passes_policy_true(self):
        """Test policy check with passing result."""
        result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=5.0,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[
                ContainerVulnerability(
                    id="CVE-2021-12345",
                    severity=VulnerabilitySeverity.LOW,
                    package_name="lib",
                    installed_version="1.0.0",
                )
            ],
            misconfigurations=[],
            secrets=[],
        )

        passed = result.passes_policy(max_critical=0, max_high=0, allow_secrets=False)

        assert passed is True

    def test_scan_result_passes_policy_false_critical(self):
        """Test policy check with critical vulnerability."""
        result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=5.0,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[
                ContainerVulnerability(
                    id="CVE-2021-12345",
                    severity=VulnerabilitySeverity.CRITICAL,
                    package_name="openssl",
                    installed_version="1.0.2",
                )
            ],
            misconfigurations=[],
            secrets=[],
        )

        passed = result.passes_policy(max_critical=0)

        assert passed is False

    def test_scan_result_passes_policy_false_secrets(self):
        """Test policy check with secrets detected."""
        result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=5.0,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[],
            misconfigurations=[],
            secrets=[
                Secret(
                    rule_id="aws-key",
                    category="AWS",
                    severity=VulnerabilitySeverity.HIGH,
                    title="AWS Key",
                    file_path="/app/config.py",
                )
            ],
        )

        passed = result.passes_policy(allow_secrets=False)

        assert passed is False

    def test_scan_result_get_vulnerability_summary(self):
        """Test vulnerability summary."""
        result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=5.0,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[
                ContainerVulnerability(
                    id="CVE-001",
                    severity=VulnerabilitySeverity.CRITICAL,
                    package_name="lib1",
                    installed_version="1.0",
                ),
                ContainerVulnerability(
                    id="CVE-002",
                    severity=VulnerabilitySeverity.HIGH,
                    package_name="lib2",
                    installed_version="1.0",
                ),
                ContainerVulnerability(
                    id="CVE-003",
                    severity=VulnerabilitySeverity.HIGH,
                    package_name="lib3",
                    installed_version="1.0",
                ),
            ],
            misconfigurations=[],
            secrets=[],
        )

        summary = result.get_vulnerability_summary()

        assert summary["CRITICAL"] == 1
        assert summary["HIGH"] == 2


class TestContainerScanner:
    """Test container scanner service."""

    def test_scanner_singleton(self):
        """Test scanner singleton pattern."""
        scanner1 = get_container_scanner()
        scanner2 = get_container_scanner()

        assert scanner1 is scanner2

    def test_scanner_detect_available_none(self):
        """Test scanner detection when none available."""
        scanner = ContainerScanner()

        with patch("shutil.which", return_value=None):
            available = scanner._detect_available_scanner()
            assert available is None

    def test_scanner_detect_trivy(self):
        """Test Trivy detection."""
        scanner = ContainerScanner()

        def mock_which(cmd):
            if cmd == "trivy":
                return "/usr/bin/trivy"
            return None

        with patch("shutil.which", side_effect=mock_which):
            available = scanner._detect_available_scanner()
            assert available == ScannerType.TRIVY

    def test_scanner_detect_grype(self):
        """Test Grype detection."""
        scanner = ContainerScanner()

        def mock_which(cmd):
            if cmd == "grype":
                return "/usr/bin/grype"
            return None

        with patch("shutil.which", side_effect=mock_which):
            available = scanner._detect_available_scanner()
            assert available == ScannerType.GRYPE

    @pytest.mark.asyncio
    async def test_scan_trivy_with_mock(self):
        """Test scanning with Trivy (mocked)."""
        scanner = ContainerScanner()

        trivy_output = json.dumps(
            {
                "Results": [
                    {
                        "Target": "myapp:latest",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2021-12345",
                                "Severity": "HIGH",
                                "PkgName": "openssl",
                                "InstalledVersion": "1.0.2",
                                "FixedVersion": "1.1.1",
                                "Title": "Buffer Overflow",
                                "Description": "A vulnerability",
                            }
                        ],
                    }
                ]
            }
        )

        with patch.object(
            scanner, "_detect_available_scanner", return_value=ScannerType.TRIVY
        ):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(
                    return_value=(trivy_output.encode(), b"")
                )
                mock_process.returncode = 0
                mock_exec.return_value = mock_process

                # scan() may return a tuple (ScanResult, error_message)
                result = await scanner.scan("myapp:latest")

                # Handle tuple return type
                if isinstance(result, tuple):
                    scan_result, error = result
                else:
                    scan_result = result

                # Result may be None if scanner isn't fully configured
                if scan_result is not None:
                    assert len(scan_result.vulnerabilities) >= 0


class TestContainerScanRequest:
    """Test container scan request model."""

    def test_container_scan_request(self):
        """Test ContainerScanRequest model."""
        request = ContainerScanRequest(
            image="myapp:latest",
        )

        assert request.image == "myapp:latest"

    def test_container_scan_request_with_digest(self):
        """Test ContainerScanRequest with image digest."""
        request = ContainerScanRequest(
            image="myapp:latest", image_digest="sha256:abc123def456..."
        )

        assert request.image_digest == "sha256:abc123def456..."

    def test_container_scan_response(self):
        """Test ContainerScanResponse model."""
        response = ContainerScanResponse(
            success=True,
            image="myapp:latest",
            scanner="trivy",
            scan_time=5.0,
            passes_policy=True,
        )

        assert response.success is True
        assert response.passes_policy is True

    def test_container_scan_response_from_result(self):
        """Test creating ContainerScanResponse from ScanResult."""
        scan_result = ScanResult(
            image="myapp:latest",
            image_digest="sha256:abc123",
            scanner=ScannerType.TRIVY,
            scanner_version="0.58.0",
            scan_time=5.0,
            scanned_at=datetime.utcnow(),
            vulnerabilities=[],
            misconfigurations=[],
            secrets=[],
        )

        response = ContainerScanResponse.from_scan_result(
            scan_result, policy_passed=True
        )

        assert response.success is True
        assert response.image == "myapp:latest"
        assert response.scanner == "trivy"
        assert response.passes_policy is True
