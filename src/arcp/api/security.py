"""
Security API endpoints.

Provides REST endpoints for:
- SBOM verification
- Container scanning
- Runtime attestation

These endpoints support the Three-Phase Registration (TPR) system
by enabling security verification during agent registration.

API Endpoints:
    POST /security/sbom/verify - Verify SBOM
    POST /security/container/scan - Scan container image
    GET /security/attestation/challenge - Get attestation challenge
    POST /security/attestation/verify - Verify attestation

All endpoints require authentication via DPoP or mTLS.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from ..core.config import config
from ..models.attestation import (
    AttestationChallengeRequest,
    AttestationChallengeResponse,
    AttestationRequest,
    AttestationVerifyRequest,
    AttestationVerifyResponse,
)
from ..models.sbom import SBOMVerifyRequest, SBOMVerifyResponse
from ..models.scan_result import ContainerScanSubmitRequest, ContainerScanSubmitResponse
from ..services.attestation import get_attestation_service
from ..services.container_scanner import get_container_scanner
from ..services.vulnerability import get_vulnerability_checker
from ..utils.api_protection import RequireAgent, RequirePublic
from ..utils.sbom import SBOMParser, verify_sbom
from ..utils.security_enforcement import RequireSecureAgent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["security"])


# =============================================================================
# SBOM Verification Endpoints
# =============================================================================


@router.post(
    "/sbom/verify", response_model=SBOMVerifyResponse, dependencies=[RequireSecureAgent]
)
async def verify_sbom_endpoint(
    request: SBOMVerifyRequest,
) -> SBOMVerifyResponse:
    """
    Verify an SBOM (Software Bill of Materials).

    Parses the SBOM, validates its structure, optionally verifies
    its signature, and checks dependencies for known vulnerabilities.

    Supports:
    - CycloneDX 1.4+ (JSON)
    - SPDX 2.2+ (JSON)

    Returns verification status including vulnerability counts
    and a hash of the SBOM for security binding.
    """
    # Check if SBOM verification is enabled
    sbom_enabled = getattr(config, "SBOM_VERIFICATION_ENABLED", True)
    if not sbom_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="SBOM verification is not enabled",
        )

    try:
        # Parse SBOM
        parser = SBOMParser()
        sbom_data = parser.parse(request.sbom_content)

        if sbom_data is None:
            return SBOMVerifyResponse(
                valid=False,
                format="unknown",
                component_count=0,
                dependency_count=0,
                vulnerability_count=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                hash="",
                timestamp=datetime.utcnow(),
                error="Failed to parse SBOM: Unknown or unsupported format",
            )

        # Verify SBOM (including vulnerability check if requested)
        result = await verify_sbom(
            request.sbom_content,
            signature=request.signature,
            check_vulnerabilities=request.verify_vulnerabilities,
        )

        # Count vulnerabilities by severity
        critical = high = medium = low = 0
        for dep in sbom_data.dependencies:
            for vuln in dep.vulnerabilities:
                sev = vuln.severity.lower() if vuln.severity else "unknown"
                if sev == "critical":
                    critical += 1
                elif sev == "high":
                    high += 1
                elif sev == "medium":
                    medium += 1
                elif sev == "low":
                    low += 1

        # Determine overall validity
        valid = result.is_valid
        if request.fail_on_critical and critical > 0:
            valid = False
        if request.fail_on_high and high > 0:
            valid = False

        logger.info(
            f"SBOM verification for agent {request.agent_id}: "
            f"format={sbom_data.format.value}, valid={valid}, "
            f"deps={len(sbom_data.dependencies)}, vulns={critical+high+medium+low}"
        )

        return SBOMVerifyResponse(
            valid=valid,
            format=sbom_data.format.value,
            component_count=len(sbom_data.components),
            dependency_count=len(sbom_data.dependencies),
            vulnerability_count=critical + high + medium + low,
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            hash=result.sbom_hash,
            timestamp=datetime.utcnow(),
            warnings=result.warnings,
        )

    except Exception as e:
        logger.error(f"SBOM verification failed: {e}")
        return SBOMVerifyResponse(
            valid=False,
            format="unknown",
            component_count=0,
            dependency_count=0,
            vulnerability_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            hash="",
            timestamp=datetime.utcnow(),
            error=str(e),
        )


# =============================================================================
# Container Scanning Endpoints
# =============================================================================


@router.post(
    "/container/scan",
    response_model=ContainerScanSubmitResponse,
    dependencies=[RequireSecureAgent],
)
async def scan_container_endpoint(
    request: ContainerScanSubmitRequest,
    http_request: Request,
) -> ContainerScanSubmitResponse:
    """
    Scan a container image for vulnerabilities and misconfigurations.

    Uses Trivy or Grype (auto-detected if not specified) to scan
    the container image and report security issues.

    Returns vulnerability counts and pass/fail status based on
    configured thresholds.
    """
    # Extract client IP for audit logging
    client_ip = None
    if hasattr(http_request, "client") and http_request.client:
        client_ip = http_request.client.host

    # Check if container scanning is enabled
    scan_enabled = getattr(config, "CONTAINER_SCAN_ENABLED", True)
    if not scan_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Container scanning is not enabled",
        )

    try:
        scanner = get_container_scanner()

        # Check scanner availability
        if not scanner.is_available():
            return ContainerScanSubmitResponse(
                passed=False,
                image=request.image,
                scanner="none",
                vulnerability_count=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                misconfiguration_count=0,
                secret_count=0,
                scan_time=datetime.utcnow(),
                error="No container scanner available. Install Trivy or Grype.",
                warnings=[],
            )

        # Perform scan
        result, error = await scanner.scan(request.image, client_ip=client_ip)

        if result is None or error:
            return ContainerScanSubmitResponse(
                passed=False,
                image=request.image,
                scanner=(
                    scanner.scanner_type.value if scanner.scanner_type else "unknown"
                ),
                vulnerability_count=0,
                critical_count=0,
                high_count=0,
                medium_count=0,
                low_count=0,
                misconfiguration_count=0,
                secret_count=0,
                scan_time=datetime.utcnow(),
                error="Scan failed - check scanner logs",
                warnings=[],
            )

        # Count vulnerabilities by severity
        critical = high = medium = low = 0
        for vuln in result.vulnerabilities:
            sev = vuln.severity.value.lower()
            if sev == "critical":
                critical += 1
            elif sev == "high":
                high += 1
            elif sev == "medium":
                medium += 1
            elif sev == "low":
                low += 1

        # Determine pass/fail
        passed = True
        warnings = []

        if request.fail_on_critical and critical > 0:
            passed = False
            warnings.append(f"Found {critical} critical vulnerabilities")
        if request.fail_on_high and high > 0:
            passed = False
            warnings.append(f"Found {high} high-severity vulnerabilities")
        if result.secrets:
            passed = False
            warnings.append(f"Found {len(result.secrets)} exposed secrets")

        logger.info(
            f"Container scan for agent {request.agent_id}: "
            f"image={request.image}, passed={passed}, "
            f"vulns={len(result.vulnerabilities)}, "
            f"misconfigs={len(result.misconfigurations)}"
        )

        return ContainerScanSubmitResponse(
            passed=passed,
            image=request.image,
            scanner=result.scanner_type.value,
            vulnerability_count=len(result.vulnerabilities),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            misconfiguration_count=len(result.misconfigurations),
            secret_count=len(result.secrets),
            scan_time=result.scan_time,
            warnings=warnings,
        )

    except Exception as e:
        logger.error(f"Container scan failed: {e}")
        return ContainerScanSubmitResponse(
            passed=False,
            image=request.image,
            scanner="error",
            vulnerability_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            misconfiguration_count=0,
            secret_count=0,
            scan_time=datetime.utcnow(),
            error=str(e),
        )


# =============================================================================
# Attestation Endpoints
# =============================================================================


@router.post(
    "/attestation/challenge",
    response_model=AttestationChallengeResponse,
    dependencies=[RequirePublic],
)
async def create_attestation_challenge(
    request: AttestationChallengeRequest,
) -> AttestationChallengeResponse:
    """
    Request an attestation challenge.

    Returns a challenge with a cryptographic nonce that the agent
    must include in its attestation evidence. The challenge has
    a limited validity period (default: 5 minutes).

    This endpoint is PUBLIC because challenges are not sensitive data.
    Challenges are cryptographic nonces that prevent replay attacks.
    Anyone can request a challenge, but it's useless without:
    1. Valid attestation evidence (TPM quote or software measurements)
    2. Authentication token to submit the evidence

    The agent should:
    1. Request a challenge (no auth required)
    2. Compute measurements including the nonce
    3. Submit evidence to /attestation/verify (requires temp token)
    """
    # Check if attestation is enabled
    attestation_enabled = getattr(config, "ATTESTATION_ENABLED", True)
    if not attestation_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Attestation is not enabled",
        )

    try:
        service = get_attestation_service()

        challenge = await service.create_challenge(
            agent_id=request.agent_id,
            attestation_types=request.attestation_types,
            required_measurements=request.required_measurements,
        )

        logger.info(
            f"Created attestation challenge for agent {request.agent_id}: "
            f"challenge_id={challenge.challenge_id}"
        )

        return AttestationChallengeResponse(
            challenge_id=challenge.challenge_id,
            nonce=challenge.nonce,
            timestamp=challenge.timestamp,
            expires_at=challenge.expires_at,
            attestation_types=challenge.attestation_types,
            required_measurements=challenge.required_measurements,
        )

    except Exception as e:
        logger.error(f"Failed to create attestation challenge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create challenge: {str(e)}",
        )


@router.post(
    "/attestation/verify",
    response_model=AttestationVerifyResponse,
    dependencies=[RequireAgent],
)
async def verify_attestation(
    request: AttestationVerifyRequest,
) -> AttestationVerifyResponse:
    """
    Verify attestation evidence from an agent.

    Accepts software attestation (code measurements) or TPM
    attestation (hardware-backed quote) and verifies against
    the challenge nonce and optional policy.

    This endpoint accepts temporary tokens (from Phase 1) because
    attestation verification happens during the registration process.

    Software Attestation:
    - Verifies code measurement hashes
    - Checks process information
    - Validates environment state

    TPM Attestation:
    - Verifies TPM quote signature
    - Checks PCR values against policy
    - Validates Attestation Key certificate

    Returns verification result with validity period.
    """
    attestation_enabled = getattr(config, "ATTESTATION_ENABLED", True)
    if not attestation_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Attestation is not enabled",
        )

    try:
        service = get_attestation_service()

        # Convert to internal request model
        internal_request = AttestationRequest(
            challenge_id=request.challenge_id,
            nonce=request.nonce,
            attestation_type=request.attestation_type,
            code_measurements=request.code_measurements,
            executable_hash=request.executable_hash,
            process_info=request.process_info,
            environment_hash=request.environment_hash,
            loaded_modules=request.loaded_modules,
            quote=request.quote,
            pcr_values=request.pcr_values,
            ak_cert=request.ak_cert,
            event_log=request.event_log,
        )

        result = await service.verify_attestation(
            request=internal_request, agent_id=request.agent_id
        )

        # Store result for tracking
        await service.store_attestation_result(request.agent_id, result)

        logger.info(
            f"Attestation verification for agent {request.agent_id}: "
            f"type={result.type.value}, valid={result.valid}, "
            f"status={result.status.value}"
        )

        return AttestationVerifyResponse(
            valid=result.valid,
            status=result.status.value,
            type=result.type.value,
            evidence_hash=result.evidence_hash,
            verified_at=result.verified_at,
            valid_until=result.valid_until,
            errors=result.errors,
            warnings=result.warnings,
            code_integrity_match=result.code_integrity_match,
            process_verified=result.process_verified,
            pcr_policy_match=result.pcr_policy_match,
            quote_verified=result.quote_verified,
        )

    except Exception as e:
        logger.error(f"Attestation verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}",
        )


@router.get("/attestation/status/{agent_id}", dependencies=[RequireAgent])
async def get_attestation_status(
    agent_id: str,
) -> Dict[str, Any]:
    """
    Get current attestation status for an agent.

    Returns the most recent attestation result including
    validity period and any warnings.
    """
    attestation_enabled = getattr(config, "ATTESTATION_ENABLED", True)
    if not attestation_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Attestation is not enabled",
        )

    service = get_attestation_service()
    status_data = await service.get_agent_attestation_status(agent_id)

    if status_data is None:
        return {
            "agent_id": agent_id,
            "attested": False,
            "message": "No attestation record found",
        }

    return {"agent_id": agent_id, "attested": True, **status_data}


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def security_health() -> Dict[str, Any]:
    """
    Check health of security services.

    Returns availability status of:
    - SBOM verification
    - Vulnerability checker
    - Container scanner
    - Attestation service
    """
    health = {"status": "healthy", "services": {}}

    # SBOM verification
    sbom_enabled = getattr(config, "SBOM_VERIFICATION_ENABLED", True)
    health["services"]["sbom"] = {"enabled": sbom_enabled, "available": sbom_enabled}

    # Vulnerability checker
    try:
        get_vulnerability_checker()  # Verify service is available
        osv_url = getattr(config, "OSV_API_URL", "https://api.osv.dev/v1")
        health["services"]["vulnerability"] = {
            "enabled": True,
            "available": True,
            "osv_api": osv_url,
        }
    except Exception as e:
        health["services"]["vulnerability"] = {
            "enabled": True,
            "available": False,
            "error": str(e),
        }

    # Container scanner
    try:
        scanner = get_container_scanner()
        health["services"]["container_scanner"] = {
            "enabled": getattr(config, "CONTAINER_SCAN_ENABLED", True),
            "available": scanner.is_available(),
            "scanner_type": (
                scanner.scanner_type.value if scanner.scanner_type else None
            ),
        }
    except Exception as e:
        health["services"]["container_scanner"] = {
            "enabled": getattr(config, "CONTAINER_SCAN_ENABLED", True),
            "available": False,
            "error": str(e),
        }

    # Attestation
    attestation_enabled = getattr(config, "ATTESTATION_ENABLED", True)
    health["services"]["attestation"] = {
        "enabled": attestation_enabled,
        "available": attestation_enabled,
        "types": ["software", "tpm"],
    }

    # Overall status
    all_available = all(s.get("available", False) for s in health["services"].values())
    if not all_available:
        health["status"] = "degraded"

    return health
