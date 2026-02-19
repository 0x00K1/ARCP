"""
Unit tests for SBOM verification functionality.

Tests the SBOM parser, verification, and vulnerability checking.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcp.models.sbom import (
    Dependency,
    SBOMData,
    SBOMFormat,
    SBOMRequest,
    SBOMVerificationResult,
    SeverityLevel,
    VulnerabilityInfo,
)
from arcp.utils.sbom import SBOMParser, verify_sbom


class TestSBOMModels:
    """Test SBOM data models."""

    def test_dependency_creation(self):
        """Test creating a Dependency."""
        dep = Dependency(
            name="requests",
            version="2.28.0",
            purl="pkg:pypi/requests@2.28.0",
            ecosystem="pypi",
        )
        assert dep.name == "requests"
        assert dep.version == "2.28.0"
        assert dep.ecosystem == "pypi"
        assert dep.purl == "pkg:pypi/requests@2.28.0"

    def test_dependency_get_ecosystem_from_purl(self):
        """Test extracting ecosystem from purl."""
        dep = Dependency(
            name="requests", version="2.28.0", purl="pkg:pypi/requests@2.28.0"
        )
        assert dep.get_ecosystem_from_purl() == "pypi"

    def test_dependency_from_dict(self):
        """Test creating Dependency from dictionary."""
        data = {
            "name": "flask",
            "version": "2.0.1",
            "purl": "pkg:pypi/flask@2.0.1",
            "ecosystem": "pypi",
        }
        dep = Dependency.from_dict(data)
        assert dep.name == "flask"
        assert dep.version == "2.0.1"

    def test_dependency_to_dict(self):
        """Test converting Dependency to dictionary."""
        dep = Dependency(name="requests", version="2.28.0")
        d = dep.to_dict()
        assert d["name"] == "requests"
        assert d["version"] == "2.28.0"

    def test_sbom_data_compute_hash(self):
        """Test SBOM hash computation."""
        sbom = SBOMData(
            format=SBOMFormat.CYCLONEDX,
            version="1.4",
            raw_hash="sha256:test123",
            dependencies=[
                Dependency(name="requests", version="2.28.0", ecosystem="pypi")
            ],
        )
        hash1 = sbom.compute_hash()
        assert hash1.startswith("sha256:")

        # Same data should produce same hash
        hash2 = sbom.compute_hash()
        assert hash1 == hash2

    def test_sbom_data_get_dependency_count(self):
        """Test getting dependency count."""
        sbom = SBOMData(
            format=SBOMFormat.CYCLONEDX,
            version="1.4",
            raw_hash="sha256:test123",
            dependencies=[
                Dependency(name="requests", version="2.28.0"),
                Dependency(name="flask", version="2.0.1"),
            ],
        )
        assert sbom.get_dependency_count() == 2

    def test_sbom_request_validation(self):
        """Test SBOM request validation."""
        # Create valid SBOM content (at least 100 chars)
        sbom_content = json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.4",
                "version": 1,
                "components": [
                    {"type": "library", "name": "requests", "version": "2.28.0"}
                ],
            }
        )

        request = SBOMRequest(sbom_content=sbom_content)
        assert request.sbom_content == sbom_content
        assert request.signature is None

    def test_sbom_verification_result(self):
        """Test verification result model."""
        result = SBOMVerificationResult(
            valid=True,
            format="cyclonedx",
            dependency_count=5,
            sbom_hash="sha256:abc123",
        )
        assert result.valid
        assert result.vulnerabilities_found == 0
        assert result.critical_vulns == 0

    def test_sbom_verification_has_blocking_vulnerabilities(self):
        """Test blocking vulnerability check."""
        result = SBOMVerificationResult(
            valid=True,
            format="cyclonedx",
            sbom_hash="sha256:abc123",
            critical_vulns=1,
            high_vulns=2,
        )
        assert result.has_blocking_vulnerabilities(block_on_critical=True) is True
        assert (
            result.has_blocking_vulnerabilities(
                block_on_critical=False, block_on_high=True
            )
            is True
        )


class TestSBOMParser:
    """Test SBOM parsing."""

    def test_parse_cyclonedx(self):
        """Test parsing CycloneDX format."""
        sbom_json = json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.4",
                "version": 1,
                "components": [
                    {
                        "type": "library",
                        "name": "requests",
                        "version": "2.28.0",
                        "purl": "pkg:pypi/requests@2.28.0",
                    },
                    {
                        "type": "library",
                        "name": "flask",
                        "version": "2.0.1",
                        "purl": "pkg:pypi/flask@2.0.1",
                    },
                ],
            }
        )

        parser = SBOMParser()
        result, error = parser.parse(sbom_json)

        assert error is None
        assert result is not None
        assert result.format == SBOMFormat.CYCLONEDX
        assert result.version == "1.4"
        assert len(result.dependencies) == 2

    def test_parse_spdx(self):
        """Test parsing SPDX format."""
        sbom_json = json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "test-sbom",
                "packages": [
                    {
                        "name": "requests",
                        "versionInfo": "2.28.0",
                        "downloadLocation": "https://pypi.org/project/requests/",
                        "externalRefs": [
                            {
                                "referenceType": "purl",
                                "referenceLocator": "pkg:pypi/requests@2.28.0",
                            }
                        ],
                    }
                ],
            }
        )

        parser = SBOMParser()
        result, error = parser.parse(sbom_json)

        assert error is None
        assert result is not None
        assert result.format == SBOMFormat.SPDX
        assert len(result.dependencies) == 1

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        parser = SBOMParser()
        result, error = parser.parse("not valid json")

        assert result is None
        assert error is not None
        assert "Invalid JSON" in error

    def test_parse_unknown_format(self):
        """Test parsing unknown SBOM format."""
        parser = SBOMParser()
        result, error = parser.parse('{"unknown": "format"}')

        assert result is None
        assert error is not None
        assert "Unknown SBOM format" in error

    def test_detect_format_cyclonedx(self):
        """Test format detection for CycloneDX."""
        parser = SBOMParser()

        data1 = {"bomFormat": "CycloneDX"}
        assert parser.detect_format(data1) == SBOMFormat.CYCLONEDX

        data2 = {"specVersion": "1.4", "components": []}
        assert parser.detect_format(data2) == SBOMFormat.CYCLONEDX

    def test_detect_format_spdx(self):
        """Test format detection for SPDX."""
        parser = SBOMParser()

        data = {"spdxVersion": "SPDX-2.3"}
        assert parser.detect_format(data) == SBOMFormat.SPDX


class TestSBOMVerification:
    """Test SBOM verification."""

    @pytest.mark.asyncio
    async def test_verify_sbom_basic(self):
        """Test basic SBOM verification."""
        sbom_content = json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.4",
                "components": [
                    {
                        "type": "library",
                        "name": "requests",
                        "version": "2.28.0",
                        "purl": "pkg:pypi/requests@2.28.0",
                    }
                ],
            }
        )

        result = await verify_sbom(sbom_content, check_vulnerabilities=False)

        assert result.valid
        assert result.format == "cyclonedx"
        assert result.dependency_count == 1
        assert result.sbom_hash.startswith("sha256:")

    @pytest.mark.asyncio
    async def test_verify_sbom_invalid(self):
        """Test verification of invalid SBOM."""
        result = await verify_sbom("invalid json", check_vulnerabilities=False)

        assert not result.valid
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_verify_sbom_with_vulnerabilities_disabled(self):
        """Test SBOM verification with vulnerability check disabled."""
        sbom_content = json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.4",
                "components": [
                    {
                        "type": "library",
                        "name": "flask",
                        "version": "0.12.0",
                        "purl": "pkg:pypi/flask@0.12.0",
                    }
                ],
            }
        )

        result = await verify_sbom(sbom_content, check_vulnerabilities=False)

        assert result.valid
        assert result.vulnerabilities_found == 0


class TestVulnerabilityInfo:
    """Test VulnerabilityInfo model."""

    def test_vulnerability_info_creation(self):
        """Test creating VulnerabilityInfo."""
        vuln = VulnerabilityInfo(
            id="CVE-2024-1234",
            severity=SeverityLevel.HIGH,
            package_name="requests",
            installed_version="2.25.0",
            fixed_version="2.31.0",
            title="Security Issue",
        )

        assert vuln.id == "CVE-2024-1234"
        assert vuln.severity == SeverityLevel.HIGH
        assert vuln.fixed_version == "2.31.0"

    def test_vulnerability_info_to_dict(self):
        """Test converting VulnerabilityInfo to dictionary."""
        vuln = VulnerabilityInfo(
            id="CVE-2024-1234",
            severity=SeverityLevel.CRITICAL,
            package_name="openssl",
            installed_version="1.0.0",
        )

        d = vuln.to_dict()
        assert d["id"] == "CVE-2024-1234"
        assert d["severity"] == "CRITICAL"
        assert d["package_name"] == "openssl"


class TestVulnerabilityService:
    """Test vulnerability checking service."""

    @pytest.mark.asyncio
    async def test_check_package(self):
        """Test checking a single package for vulnerabilities."""
        from arcp.services.vulnerability import VulnerabilityChecker

        # Mock httpx client
        with patch("arcp.services.vulnerability.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"vulns": []}

            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            checker = VulnerabilityChecker()
            vulns = await checker.check_package("requests", "2.28.0", "pypi")

            assert vulns == []
