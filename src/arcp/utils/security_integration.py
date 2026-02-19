"""
Advanced security validation integration.

Integrates SBOM verification, container scanning, and attestation
checks into the Three-Phase Registration (TPR) validation flow.

This module provides functions to perform security checks during
Phase 2 (Compliance Validation) and update the SecurityBinding
with hashes from verified security artifacts.

Usage:
    In core/validation.py, call these functions after fast checks:

    >>> from ..utils.security_integration import perform_security_validation
    >>> await perform_security_validation(request, result)

Features:
    - SBOM verification and vulnerability scanning
    - Container image scanning (Trivy/Grype)
    - Runtime attestation verification
    - Security binding updates with verified hashes
"""

import logging
from typing import List, Optional, Tuple

from ..core.config import config
from ..models.attestation import AttestationRequest
from ..models.validation import SecurityBinding, ValidationRequest, ValidationResult
from ..services.attestation import get_attestation_service
from ..services.container_scanner import get_container_scanner
from ..utils.sbom import verify_sbom

logger = logging.getLogger(__name__)


async def verify_sbom_if_provided(
    request: ValidationRequest, result: ValidationResult
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Verify SBOM if provided in validation request.

    Args:
        request: ValidationRequest with optional SBOM data
        result: ValidationResult to update with findings

    Returns:
        Tuple of (passed, sbom_hash, warnings)
    """
    warnings = []

    # Check if SBOM is provided
    sbom_content = getattr(request, "sbom", None)
    if not sbom_content:
        if config.SBOM_REQUIRED:
            result.errors.append(
                {
                    "type": "sbom_required",
                    "message": "SBOM is required but not provided",
                }
            )
            return False, None, warnings
        else:
            logger.debug(f"No SBOM provided for {request.agent_id}")
            return True, None, warnings

    # Parse and verify SBOM
    try:
        verification = await verify_sbom(
            sbom_content, check_vulnerabilities=config.SBOM_VULNERABILITY_CHECK
        )

        if not verification.valid:
            for error in verification.errors:
                result.errors.append(
                    {"type": "sbom_verification_failed", "message": error}
                )
            return False, None, getattr(verification, "warnings", [])

        # Check vulnerability thresholds
        if verification.vulnerabilities_found > 0:
            if config.SBOM_FAIL_ON_CRITICAL and verification.critical_vulns > 0:
                result.errors.append(
                    {
                        "type": "sbom_critical_vulnerabilities",
                        "message": f"SBOM contains {verification.critical_vulns} critical vulnerabilities",
                    }
                )
                return False, verification.sbom_hash, verification.warnings

            if config.SBOM_FAIL_ON_HIGH and verification.high_vulns > 0:
                result.errors.append(
                    {
                        "type": "sbom_high_vulnerabilities",
                        "message": f"SBOM contains {verification.high_vulns} high-severity vulnerabilities",
                    }
                )
                return False, verification.sbom_hash, verification.warnings

            # Add vulnerability warning
            warnings.append(
                f"SBOM contains {verification.vulnerabilities_found} vulnerabilities "
                f"(critical: {verification.critical_vulns}, high: {verification.high_vulns})"
            )

        logger.info(
            f"SBOM verification passed for {request.agent_id}: "
            f"format={verification.format}, deps={verification.dependency_count}"
        )

        return True, verification.sbom_hash, warnings + verification.warnings

    except Exception as e:
        logger.error(f"SBOM verification error for {request.agent_id}: {e}")
        result.errors.append({"type": "sbom_verification_error", "message": str(e)})
        return False, None, warnings


async def scan_container_if_applicable(
    request: ValidationRequest, result: ValidationResult
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Scan container image if this is a containerized agent.

    Args:
        request: ValidationRequest with optional container info
        result: ValidationResult to update with findings

    Returns:
        Tuple of (passed, scan_hash, warnings)
    """
    warnings = []

    # Check if container image is provided
    container_image = getattr(request, "container_image", None)
    if not container_image:
        if config.CONTAINER_SCAN_REQUIRED:
            # SECURITY: Container scanning is required for ALL agents when enabled
            # Don't trust agent's self-reported is_containerized flag
            result.errors.append(
                {
                    "type": "container_scan_required",
                    "message": "Container image is required when CONTAINER_SCAN_REQUIRED=true. "
                    "Provide container_image in validation request.",
                }
            )
            logger.warning(
                f"Container scan required but no image provided for {request.agent_id}"
            )
            return False, None, warnings

        logger.debug(f"No container image for {request.agent_id}")
        return True, None, warnings

    try:
        scanner = get_container_scanner()

        if not scanner.is_available():
            warnings.append("Container scanner not available, skipping scan")
            logger.warning(f"Container scanner not available for {request.agent_id}")
            return True, None, warnings

        # Extract client_ip from request if available
        client_ip = getattr(request, "client_ip", None)

        # Perform scan (returns tuple: result, error)
        # Pass agent context for audit logging
        scan_result, scan_error = await scanner.scan(
            container_image, agent_id=request.agent_id, client_ip=client_ip
        )

        if scan_result is None or scan_error:
            error_msg = scan_error or "Container scan failed - check scanner logs"
            result.errors.append(
                {"type": "container_scan_failed", "message": error_msg}
            )
            return False, None, warnings

        # Check vulnerability thresholds
        critical = sum(
            1
            for v in scan_result.vulnerabilities
            if v.severity.value.lower() == "critical"
        )
        high = sum(
            1 for v in scan_result.vulnerabilities if v.severity.value.lower() == "high"
        )

        if config.CONTAINER_SCAN_FAIL_ON_CRITICAL and critical > 0:
            result.errors.append(
                {
                    "type": "container_critical_vulnerabilities",
                    "message": f"Container has {critical} critical vulnerabilities",
                }
            )
            return False, scan_result.image_digest, warnings

        if config.CONTAINER_SCAN_FAIL_ON_HIGH and high > 0:
            result.errors.append(
                {
                    "type": "container_high_vulnerabilities",
                    "message": f"Container has {high} high-severity vulnerabilities",
                }
            )
            return False, scan_result.image_digest, warnings

        # Check for secrets
        if config.CONTAINER_SCAN_FAIL_ON_SECRETS and scan_result.secrets:
            result.errors.append(
                {
                    "type": "container_secrets_detected",
                    "message": f"Container has {len(scan_result.secrets)} exposed secrets",
                }
            )
            return False, scan_result.image_digest, warnings

        # Add warning if vulnerabilities found but below threshold
        vuln_count = len(scan_result.vulnerabilities)
        if vuln_count > 0:
            warnings.append(
                f"Container has {vuln_count} vulnerabilities "
                f"(critical: {critical}, high: {high})"
            )

        logger.info(
            f"Container scan passed for {request.agent_id}: "
            f"image={container_image}, vulns={vuln_count}"
        )

        return True, scan_result.image_digest, warnings

    except Exception as e:
        logger.error(f"Container scan error for {request.agent_id}: {e}")
        result.errors.append({"type": "container_scan_error", "message": str(e)})
        return False, None, warnings


async def verify_attestation_if_provided(
    request: ValidationRequest, result: ValidationResult
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Verify attestation if provided in validation request.

    Args:
        request: ValidationRequest with optional attestation data
        result: ValidationResult to update with findings

    Returns:
        Tuple of (passed, evidence_hash, warnings)
    """
    warnings = []

    # Check if attestation is provided
    attestation_data = getattr(request, "attestation", None)
    if not attestation_data:
        if config.ATTESTATION_REQUIRED:
            result.errors.append(
                {
                    "type": "attestation_required",
                    "message": "Attestation is required but not provided",
                }
            )
            return False, None, warnings
        else:
            logger.debug(f"No attestation for {request.agent_id}")
            return True, None, warnings

    try:
        service = get_attestation_service()

        # Convert attestation data to request
        attestation_request = AttestationRequest(
            challenge_id=attestation_data.get("challenge_id", ""),
            nonce=attestation_data.get("nonce", ""),
            attestation_type=attestation_data.get("type", "software"),
            code_measurements=attestation_data.get("code_measurements"),
            executable_hash=attestation_data.get("executable_hash"),
            process_info=attestation_data.get("process_info"),
            environment_hash=attestation_data.get("environment_hash"),
            loaded_modules=attestation_data.get("loaded_modules"),
            quote=attestation_data.get("quote"),
            pcr_values=attestation_data.get("pcr_values"),
            ak_cert=attestation_data.get("ak_cert"),
            event_log=attestation_data.get("event_log"),
        )

        # Verify attestation
        attestation_result = await service.verify_attestation(
            request=attestation_request, agent_id=request.agent_id
        )

        if not attestation_result.valid:
            for error in attestation_result.errors:
                result.errors.append({"type": "attestation_failed", "message": error})
            return False, attestation_result.evidence_hash, attestation_result.warnings

        # Add any warnings
        warnings.extend(attestation_result.warnings)

        logger.info(
            f"Attestation verified for {request.agent_id}: "
            f"type={attestation_result.type.value}, "
            f"valid_until={attestation_result.valid_until}"
        )

        return True, attestation_result.evidence_hash, warnings

    except Exception as e:
        logger.error(f"Attestation verification error for {request.agent_id}: {e}")
        result.errors.append({"type": "attestation_error", "message": str(e)})
        return False, None, warnings


async def perform_security_validation(
    request: ValidationRequest, result: ValidationResult
) -> None:
    """
    Perform all advanced security validations.

    Runs SBOM verification, container scanning, and attestation
    checks based on configuration and provided data.

    Updates the ValidationResult with any errors, warnings,
    and security findings.

    This should be called in the validation worker after fast checks
    and before capability verification:

    ```python
    # In validation_worker():
    await perform_fast_checks(request, result)

    if len(result.errors) == 0:
        # Advanced security validation
        await perform_security_validation(request, result)

        if len(result.errors) == 0:
            await perform_endpoint_validation(request, result)
    ```

    Args:
        request: ValidationRequest from agent
        result: ValidationResult to update
    """
    # Skip if none of the features are enabled
    if not (
        config.SBOM_VERIFICATION_ENABLED
        or config.CONTAINER_SCAN_ENABLED
        or config.ATTESTATION_ENABLED
    ):
        logger.debug("Advanced security validation disabled")
        return

    logger.info(f"Performing advanced security validation for {request.agent_id}")

    security_hashes = {}
    all_warnings = []

    # SBOM Verification
    if config.SBOM_VERIFICATION_ENABLED:
        passed, sbom_hash, warnings = await verify_sbom_if_provided(request, result)
        all_warnings.extend(warnings)
        if sbom_hash:
            security_hashes["sbom_hash"] = sbom_hash
        if not passed and not config.SBOM_REQUIRED:
            # Log warning but continue if SBOM not required
            logger.warning(
                f"SBOM verification failed for {request.agent_id} (not required)"
            )

    # Container Scanning
    if config.CONTAINER_SCAN_ENABLED:
        passed, scan_hash, warnings = await scan_container_if_applicable(
            request, result
        )
        all_warnings.extend(warnings)
        if scan_hash:
            security_hashes["container_scan_hash"] = scan_hash
        if not passed and not config.CONTAINER_SCAN_REQUIRED:
            logger.warning(
                f"Container scan failed for {request.agent_id} (not required)"
            )

    # Attestation
    if config.ATTESTATION_ENABLED:
        passed, evidence_hash, warnings = await verify_attestation_if_provided(
            request, result
        )
        all_warnings.extend(warnings)
        if evidence_hash:
            security_hashes["attestation_hash"] = evidence_hash
        if not passed and not config.ATTESTATION_REQUIRED:
            logger.warning(f"Attestation failed for {request.agent_id} (not required)")

    # Add all warnings to result
    for warning in all_warnings:
        result.warnings.append({"type": "security_warning", "message": warning})

    # Store security hashes for later binding
    if security_hashes:
        setattr(request, "_security_hashes", security_hashes)
        logger.info(
            f"Security validation complete for {request.agent_id}: "
            f"hashes={list(security_hashes.keys())}"
        )


def update_security_binding_with_hashes(
    binding: SecurityBinding, request: ValidationRequest
) -> SecurityBinding:
    """
    Update security binding with verified security hashes.

    Adds SBOM hash, container scan hash, and attestation hash
    to the security binding if they were computed during validation.

    Call this after create_security_binding():

    ```python
    binding = create_security_binding(request, result, dpop_jkt, mtls_spki)
    binding = update_security_binding_with_hashes(binding, request)
    ```

    Args:
        binding: SecurityBinding to update
        request: ValidationRequest with security hashes

    Returns:
        Updated SecurityBinding
    """
    security_hashes = getattr(request, "_security_hashes", {})

    if "sbom_hash" in security_hashes:
        binding.sbom_hash = security_hashes["sbom_hash"]

    if "container_scan_hash" in security_hashes:
        binding.container_scan_hash = security_hashes["container_scan_hash"]

    if "attestation_hash" in security_hashes:
        binding.attestation_hash = security_hashes["attestation_hash"]

    return binding
