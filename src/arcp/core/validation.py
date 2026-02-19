"""
Validation worker for Three-Phase Registration (TPR) Phase 2.

This module handles asynchronous validation of agents during the
compliance validation phase, performing security and endpoint checks
before issuing validated tokens.
"""

import asyncio
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import uuid4

import httpx

from ..core.config import config
from ..models.validation import SecurityBinding, ValidationRequest, ValidationResult
from ..services.redis import get_redis_service
from ..utils.endpoint_validator import validate_agent_endpoints
from ..utils.security_integration import (
    scan_container_if_applicable,
    verify_attestation_if_provided,
    verify_sbom_if_provided,
)

logger = logging.getLogger(__name__)

# Redis queue key for distributed validation processing
VALIDATION_QUEUE_KEY = "arcp:validation:queue"


# ========== Validation Queue ==========
# Hybrid Redis + asyncio.Queue fallback
#
# When Redis is available:
#   - Uses Redis LIST (LPUSH for enqueue, BRPOP for dequeue)
#   - Supports multi-process and distributed deployments
#   - Persistent across server restarts
#   - Queue key: VALIDATION_QUEUE_KEY = "arcp:validation:queue"
#
# When Redis is unavailable:
#   - Falls back to in-memory asyncio.Queue
#   - Single-process only
#   - Lost on restart
#   - Bound to specific event loop for test compatibility
#
# Migration path: Deploy hybrid code → Enable Redis → Scale to multi-instance

_validation_queue_lock = threading.Lock()
_validation_queue: Optional[asyncio.Queue] = None
_validation_queue_loop: Optional[asyncio.AbstractEventLoop] = None


def get_validation_queue() -> asyncio.Queue:
    """
    Get or create validation queue for current event loop.

    This ensures the queue is bound to the correct event loop,
    preventing RuntimeError in tests and multi-loop scenarios.

    Thread-safety: Uses a lock to prevent race conditions when
    creating the queue from multiple threads (though async code
    should typically run in a single thread).

    Note:
        For distributed deployments, replace this with a Redis-based
        queue or a task queue like Celery.
    """
    global _validation_queue, _validation_queue_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create one
        current_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(current_loop)

    # Use lock to ensure thread-safe queue creation
    with _validation_queue_lock:
        # Create new queue if not exists or bound to different loop
        if _validation_queue is None or _validation_queue_loop != current_loop:
            _validation_queue = asyncio.Queue(maxsize=config.VALIDATION_QUEUE_MAX_SIZE)
            _validation_queue_loop = current_loop
            logger.debug(f"Created validation queue for event loop {id(current_loop)}")

    return _validation_queue


# Hybrid Redis + in-memory fallback storage
#
# When Redis is available:
#   - Stores validation results in Redis with TTL expiration
#   - Key pattern: val:result:{validation_id}
#   - TTL: config.TPR_TOKEN_TTL_VALIDATED + 60s buffer
#   - Supports multi-instance deployments
#
# When Redis is unavailable:
#   - Falls back to in-memory dictionary
#   - Single-process only, lost on restart
#
# Storage functions:
#   - store_validation_result_internal(): Write to Redis/fallback
#   - get_validation_result(): Read from Redis/fallback
validation_results: Dict[str, ValidationResult] = {}

# In-memory storage for validation context (security bindings from HTTP request)
# This stores dpop_jkt and mtls_spki extracted during validate_compliance
# which are needed later when generating the token in the polling endpoint.
#
# Why separate from validation_results?
# - validation_results: Written by the async worker (validation outcome)
# - validation_contexts: Written by the HTTP handler (request-time security info)
#
# The worker doesn't have access to HTTP headers, so we capture them here.
validation_contexts: Dict[str, Dict] = {}


async def store_validation_context(validation_id: str, context: Dict) -> None:
    """
    Store security context from HTTP request for later token generation.

    This captures dpop_jkt and mtls_spki from the HTTP headers during
    validate_compliance, so they can be embedded in the token when
    the polling endpoint generates it.

    Stores in Redis or falls back to in-memory dictionary.

    Args:
        validation_id: Validation identifier
        context: Dictionary containing dpop_jkt, mtls_spki (security bindings)
    """
    # Only store security-relevant fields (agent_id is in validation_results)
    security_context = {
        "dpop_jkt": context.get("dpop_jkt"),
        "mtls_spki": context.get("mtls_spki"),
        "created_at": datetime.utcnow().isoformat(),
    }

    redis_service = get_redis_service()

    # Try Redis first
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                key = f"val:context:{validation_id}"
                ttl = config.TOKEN_TTL_VALIDATED + 60  # Extra buffer
                client.setex(key, ttl, json.dumps(security_context))
                logger.debug(f"Stored context in Redis for {validation_id}")
                return
        except Exception as e:
            logger.warning(f"Failed to store context in Redis: {e}")

    # Fallback to in-memory
    validation_contexts[validation_id] = security_context

    bindings = [k for k, v in security_context.items() if v and k != "created_at"]
    logger.debug(f"Stored security context for {validation_id}: {bindings or 'none'}")


async def get_validation_context(validation_id: str) -> Optional[Dict]:
    """
    Retrieve context information for a validation request.

    Retrieves from Redis or falls back to in-memory dictionary.

    Args:
        validation_id: Validation identifier

    Returns:
        Context dictionary if found, None otherwise
    """
    redis_service = get_redis_service()

    # Try Redis first
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                key = f"val:context:{validation_id}"
                data = client.get(key)
                if data:
                    return json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to get context from Redis: {e}")

    # Fallback to in-memory
    return validation_contexts.get(validation_id)


async def clear_validation_context(validation_id: str) -> None:
    """
    Clear context information after validation is consumed.

    Clears from both Redis and in-memory fallback.

    Args:
        validation_id: Validation identifier
    """
    redis_service = get_redis_service()

    # Clear from Redis
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                key = f"val:context:{validation_id}"
                client.delete(key)
        except Exception as e:
            logger.warning(f"Failed to clear context from Redis: {e}")

    # Always clear from fallback
    validation_contexts.pop(validation_id, None)
    logger.debug(f"Cleared validation context for {validation_id}")


async def store_validation_result_internal(
    validation_id: str, result: ValidationResult
) -> None:
    """
    Store validation result in Redis with TTL or fallback to in-memory.

    Args:
        validation_id: Validation identifier
        result: ValidationResult to store
    """
    redis_service = get_redis_service()

    # Try Redis first
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                key = f"val:result:{validation_id}"
                ttl = config.TOKEN_TTL_VALIDATED + 60  # Extra buffer
                client.setex(key, ttl, result.model_dump_json())
                logger.debug(f"Stored result in Redis for {validation_id}")
                return
        except Exception as e:
            logger.warning(f"Failed to store in Redis, using fallback: {e}")

    # Fallback to in-memory
    validation_results[validation_id] = result


async def get_validation_result_from_storage(
    validation_id: str,
) -> Optional[ValidationResult]:
    """
    Get validation result from Redis or fallback to in-memory.

    Args:
        validation_id: Validation identifier

    Returns:
        ValidationResult if found, None otherwise
    """
    redis_service = get_redis_service()

    # Try Redis first
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                key = f"val:result:{validation_id}"
                data = client.get(key)
                if data:
                    return ValidationResult.model_validate_json(data)
        except Exception as e:
            logger.warning(f"Failed to get from Redis: {e}")

    # Fallback to in-memory
    return validation_results.get(validation_id)


# ========== Queue Operations ==========


async def enqueue_validation(request: ValidationRequest) -> str:
    """
    Enqueue a validation request for async processing.

    Uses Redis LIST (LPUSH) for distributed queue, or falls back to asyncio.Queue.

    Args:
        request: ValidationRequest containing agent details

    Returns:
        validation_id: Unique identifier for this validation

    Raises:
        asyncio.QueueFull: If validation queue is at capacity
    """
    validation_id = f"val_{uuid4().hex[:16]}"

    # Create pending result
    result = ValidationResult(
        validation_id=validation_id,
        agent_id=request.agent_id,
        status="pending",
        binding=None,
        errors=[],
        warnings=[],
        endpoint_checks={},
        duration_ms=0,
        current_step=None,
    )

    redis_service = get_redis_service()

    # Try Redis queue first
    if redis_service and redis_service.is_available():
        try:
            client = redis_service.get_client()
            if client:
                # Store result
                await store_validation_result_internal(validation_id, result)

                # Enqueue to Redis LIST
                queue_item = {
                    "validation_id": validation_id,
                    "request": request.model_dump(),
                }
                queue_length = client.lpush(
                    VALIDATION_QUEUE_KEY, json.dumps(queue_item)
                )
                logger.info(
                    f"Validation {validation_id} enqueued (Redis) for "
                    f"agent {request.agent_id} (queue depth: {queue_length})"
                )
                return validation_id
        except Exception as e:
            logger.warning(f"Redis queue failed, using fallback: {e}")

    # Fallback to in-memory queue
    validation_results[validation_id] = result
    try:
        queue = get_validation_queue()
        queue.put_nowait((validation_id, request))
        logger.info(
            f"Validation {validation_id} enqueued (fallback) for "
            f"agent {request.agent_id} (queue depth: {queue.qsize()})"
        )
    except asyncio.QueueFull:
        validation_results.pop(validation_id, None)
        logger.error(
            f"Validation queue full (max: {config.VALIDATION_QUEUE_MAX_SIZE}), "
            f"rejecting validation for agent {request.agent_id}"
        )
        raise

    return validation_id


async def get_validation_result(validation_id: str) -> Optional[ValidationResult]:
    """
    Get validation result by ID.

    Retrieves from Redis with fallback to in-memory dictionary.

    Args:
        validation_id: Validation identifier

    Returns:
        ValidationResult if found, None otherwise
    """
    return await get_validation_result_from_storage(validation_id)


# ========== Validation Stages ==========


async def perform_fast_checks(
    request: ValidationRequest, result: ValidationResult
) -> None:
    """
    Perform fast validation checks (< 1 second).

    Checks:
    - Agent ID format validation
    - Quick health probe
    - Identity match verification

    Args:
        request: ValidationRequest
        result: ValidationResult to update with findings
    """
    # 1. Identity match (agent_id format)
    if not request.agent_id or len(request.agent_id) < 3:
        result.errors.append(
            {
                "type": "invalid_agent_id",
                "message": "agent_id must be at least 3 characters",
                "field": "agent_id",
            }
        )
        return

    # 2. Quick health probe
    try:
        async with httpx.AsyncClient(timeout=config.VALIDATION_TIMEOUT_FAST) as client:
            health_url = f"{request.endpoint.rstrip('/')}/health"
            health_resp = await client.get(health_url)

            if health_resp.status_code != 200:
                result.errors.append(
                    {
                        "type": "health_check_failed",
                        "message": f"Health endpoint returned {health_resp.status_code}",
                        "details": {"status_code": health_resp.status_code},
                    }
                )
            else:
                try:
                    health_data = health_resp.json()

                    # Verify agent_id match
                    if health_data.get("agent_id") != request.agent_id:
                        result.errors.append(
                            {
                                "type": "identity_mismatch",
                                "message": (
                                    f"Agent ID mismatch: expected '{request.agent_id}', "
                                    f"got '{health_data.get('agent_id')}'"
                                ),
                                "field": "agent_id",
                            }
                        )

                    # Verify healthy status
                    if health_data.get("status") != "healthy":
                        result.warnings.append(
                            {
                                "type": "unhealthy_status",
                                "message": f"Agent reports status: {health_data.get('status')}",
                            }
                        )

                except Exception as e:
                    result.errors.append(
                        {
                            "type": "invalid_health_response",
                            "message": f"Health endpoint returned invalid JSON: {str(e)}",
                        }
                    )

    except httpx.TimeoutException:
        result.errors.append(
            {
                "type": "endpoint_timeout",
                "message": f"Health endpoint timed out after {config.VALIDATION_TIMEOUT_FAST}s",
            }
        )
    except Exception as e:
        result.errors.append(
            {
                "type": "endpoint_unreachable",
                "message": f"Cannot reach health endpoint: {str(e)}",
            }
        )


async def perform_endpoint_validation(
    request: ValidationRequest, result: ValidationResult
) -> None:
    """
    Perform full endpoint contract validation.

    Uses the endpoint_validator module to check all required
    endpoints against their schemas.

    Args:
        request: ValidationRequest
        result: ValidationResult to update with findings
    """
    if not config.ENDPOINT_VALIDATION_ENABLED:
        logger.info(f"Endpoint validation disabled, skipping for {request.agent_id}")
        return

    try:
        # Determine validation mode for logging
        validation_mode = getattr(config, "ENDPOINT_VALIDATION_MODE", "static").upper()
        logger.info(
            f"Performing {validation_mode} endpoint validation for agent {request.agent_id}"
        )

        validator_result = await validate_agent_endpoints(
            agent_id=request.agent_id,
            agent_endpoint=request.endpoint,
            declared_capabilities=request.capabilities,
            communication_mode=request.communication_mode,
        )

        # Add endpoint check results
        result.endpoint_checks = validator_result.get_summary()

        # Add errors from validator
        if not validator_result.is_valid():
            for error in validator_result.errors:
                result.errors.append(error.to_dict())

        # Add warnings
        for warning in validator_result.warnings:
            result.warnings.append(warning.to_dict())

        logger.info(
            f"Endpoint validation for {request.agent_id}: "
            f"{len(validator_result.checks)} checks, "
            f"{len(validator_result.errors)} errors, "
            f"{len(validator_result.warnings)} warnings"
        )

    except Exception as e:
        logger.error(f"Endpoint validation error for {request.agent_id}: {e}")
        result.errors.append(
            {
                "type": "endpoint_validation_error",
                "message": f"Endpoint validation failed: {str(e)}",
            }
        )


async def verify_capabilities(
    request: ValidationRequest, result: ValidationResult
) -> None:
    """
    Verify declared capabilities.

    Ensures agent declares at least one capability and that
    capabilities match what's reported by endpoints.

    Args:
        request: ValidationRequest
        result: ValidationResult to update with findings
    """
    # Capability verification is now handled by endpoint validator
    # Just ensure capabilities are non-empty
    if not request.capabilities or len(request.capabilities) == 0:
        result.warnings.append(
            {"type": "no_capabilities", "message": "Agent declares no capabilities"}
        )


def create_security_binding(
    request: ValidationRequest,
    result: ValidationResult,
    dpop_jkt: Optional[str] = None,
    mtls_spki: Optional[str] = None,
) -> SecurityBinding:
    """
    Create security binding for validated token.

    Generates hashes of agent code and endpoint configuration to
    tie the validated token to specific agent characteristics.

    Includes DPoP JWK thumbprint when dpop_jkt is provided.
    Includes mTLS SPKI hash when mtls_spki is provided.

    Args:
        request: ValidationRequest
        result: ValidationResult with validation findings
        dpop_jkt: Optional DPoP JWK thumbprint (RFC 9449)
        mtls_spki: Optional mTLS client certificate SPKI hash

    Returns:
        SecurityBinding with code and endpoint hashes
    """
    # Hash the endpoint configuration
    endpoint_config = json.dumps(
        {
            "endpoint": request.endpoint,
            "capabilities": sorted(request.capabilities),
            "communication_mode": request.communication_mode,
        },
        sort_keys=True,
    )
    endpoint_hash = f"sha256:{hashlib.sha256(endpoint_config.encode()).hexdigest()}"

    # Currently we use a simple hash based on agent_id + version
    #   - Quick and deterministic
    #   - Suitable for development and testing
    #   - Does NOT verify actual agent code integrity
    #
    # TODO:
    #   We'll implement one of the following approaches for strong security:
    #
    #   1. SBOM (Software Bill of Materials) Integration:
    #      - Agent provides SBOM in SPDX or CycloneDX format during registration
    #      - Hash the SBOM document to create code_hash
    #      - Verify SBOM signature using agent's public key
    #      - Track dependencies and vulnerability scanning results
    #      - Tools: syft, grype, trivy, OWASP DependencyCheck
    #
    #   2. Container Image Attestation:
    #      - For containerized agents, use image digest (sha256:...)
    #      - Verify image signature using Sigstore/cosign
    #      - Check image provenance and build attestations
    #      - Implement admission control policies
    #      - Tools: cosign, in-toto, SLSA framework
    #
    #   3. Binary/Artifact Signing:
    #      - Agent provides signed binary or artifact hash
    #      - Verify signature against trusted public key registry
    #      - Use platform-specific signing (e.g., .NET Authenticode, JAR signing)
    #      - Tools: sigstore, minisign, GPG
    #
    #   4. TPM/Hardware-based Attestation:
    #      - Use TPM to generate and seal code measurements
    #      - Remote attestation using TPM quote
    #      - Measured boot and runtime integrity monitoring
    #      - Tools: go-attestation, keylime
    #
    #   Additional Security Controls:
    #   - Implement code_hash allowlist/denylist
    #   - Monitor for code_hash changes during agent lifecycle
    #   - Trigger re-validation on code updates
    #   - Integrate with vulnerability databases
    #   - Enforce code signing policies per agent type
    #   - Audit all code_hash verification events
    #
    code_str = f"{request.agent_id}:{request.version or 'unknown'}"
    code_hash = f"sha256:{hashlib.sha256(code_str.encode()).hexdigest()}"

    binding = SecurityBinding(
        code_hash=code_hash,
        endpoint_hash=endpoint_hash,
        jkt=dpop_jkt,
        mtls_spki=mtls_spki,
        validation_timestamp=datetime.utcnow(),
    )

    binding_info = (
        f"code_hash={code_hash[:20]}..., endpoint_hash={endpoint_hash[:20]}..."
    )
    if dpop_jkt:
        binding_info += f", dpop_jkt={dpop_jkt[:16]}..."
    if mtls_spki:
        binding_info += f", mtls_spki={mtls_spki[:16]}..."

    logger.debug(f"Security binding created for {request.agent_id}: {binding_info}")

    return binding


async def store_validation_result(validation_id: str, result: ValidationResult) -> None:
    """
    Store validation result in Redis with TTL.

    The validation result is stored for later consumption during
    the registration phase. It includes the security binding and
    is marked as single-use.

    Args:
        validation_id: Validation identifier
        result: ValidationResult to store
    """
    # Store in-memory first
    validation_results[validation_id] = result

    redis_service = get_redis_service()

    if not redis_service or not redis_service.is_available():
        logger.warning(
            f"Redis not available, validation result {validation_id} "
            "stored in-memory only (not persistent)"
        )
        return

    client = redis_service.get_client()
    if not client:
        return

    try:
        # Store as JSON with 5 minute TTL (matches validated token TTL)
        ttl = config.TOKEN_TTL_VALIDATED

        data = {
            "validation_id": validation_id,
            "agent_id": result.agent_id,
            "status": result.status,
            "binding": result.binding.model_dump() if result.binding else None,
            "endpoint_checks": result.endpoint_checks,
            "exp": int((datetime.utcnow() + timedelta(seconds=ttl)).timestamp()),
            "used": False,  # Mark as unused
            "created_at": datetime.utcnow().isoformat(),
        }

        key = f"val:{validation_id}"
        client.setex(key, ttl, json.dumps(data, default=str))

        logger.info(
            f"Stored validation result {validation_id} in Redis with {ttl}s TTL"
        )

    except Exception as e:
        logger.error(f"Failed to store validation result in Redis: {e}")


# ========== Validation Worker ==========


async def validation_worker():
    """
    Background worker that processes validation requests from the queue.

    Dequeues from Redis LIST (BRPOP) or falls back to asyncio.Queue.

    Performs the following stages:
    1. Fast checks (< 1s): identity, quick health
    2. Endpoint validation: full contract validation
    3. Capability verification
    4. Security binding creation
    5. Result storage in Redis

    Runs continuously, processing items from the validation queue.
    """
    logger.info("Validation worker started")
    redis_service = get_redis_service()

    while True:
        try:
            validation_id = None
            request = None

            # Try Redis queue first
            if redis_service and redis_service.is_available():
                try:
                    client = redis_service.get_client()
                    if client:
                        # Use non-blocking RPOP instead of BRPOP to avoid blocking executor threads
                        loop = asyncio.get_running_loop()
                        result_item = await loop.run_in_executor(
                            None, lambda: client.rpop(VALIDATION_QUEUE_KEY)
                        )
                        if result_item:
                            queue_item = json.loads(result_item)
                            validation_id = queue_item["validation_id"]
                            request_dict = queue_item["request"]
                            request = ValidationRequest(**request_dict)
                            logger.info(
                                f"Processing validation {validation_id} (Redis) "
                                f"for agent {request.agent_id}"
                            )
                except Exception as e:
                    logger.warning(f"Redis dequeue failed: {e}")
                    await asyncio.sleep(1)
                    continue

            # Fallback to in-memory queue
            if validation_id is None:
                try:
                    queue = get_validation_queue()
                    validation_id, request = await asyncio.wait_for(
                        queue.get(), timeout=1.0
                    )
                    logger.info(
                        f"Processing validation {validation_id} (fallback) "
                        f"for agent {request.agent_id}"
                    )
                except asyncio.TimeoutError:
                    continue  # No items, continue loop

            if validation_id and request:
                start_time = datetime.utcnow()
                result = await get_validation_result(validation_id)

                if not result:
                    logger.error(f"Validation result not found for {validation_id}")
                    continue

                try:
                    # Stage 1: Fast checks (< 1s)
                    result.current_step = "Performing fast checks..."
                    await store_validation_result_internal(validation_id, result)
                    await perform_fast_checks(request, result)

                    # If fast checks failed critically, skip full validation
                    if len(result.errors) > 0:
                        logger.warning(
                            f"Validation {validation_id} failed fast checks, "
                            f"skipping full validation"
                        )
                    else:
                        # Stage 2: Advanced security validation (with granular progress updates)
                        security_hashes = {}
                        all_warnings = []

                        # SBOM Verification
                        if config.SBOM_VERIFICATION_ENABLED:
                            result.current_step = (
                                "Verifying SBOM and checking vulnerabilities..."
                            )
                            await store_validation_result_internal(
                                validation_id, result
                            )
                            logger.info(f"[{validation_id}] {result.current_step}")

                            passed, sbom_hash, warnings = await verify_sbom_if_provided(
                                request, result
                            )
                            all_warnings.extend(warnings)
                            if sbom_hash:
                                security_hashes["sbom_hash"] = sbom_hash
                            if not passed and not config.SBOM_REQUIRED:
                                logger.warning(
                                    f"SBOM verification failed for {request.agent_id} (not required)"
                                )

                        # Container Scanning (the long operation - 15-20 seconds)
                        if config.CONTAINER_SCAN_ENABLED:
                            result.current_step = "Scanning container image with Trivy (this may take 15-20s)..."
                            await store_validation_result_internal(
                                validation_id, result
                            )
                            logger.info(f"[{validation_id}] {result.current_step}")

                            passed, scan_hash, warnings = (
                                await scan_container_if_applicable(request, result)
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
                            result.current_step = "Verifying attestation evidence..."
                            await store_validation_result_internal(
                                validation_id, result
                            )
                            logger.info(f"[{validation_id}] {result.current_step}")

                            passed, evidence_hash, warnings = (
                                await verify_attestation_if_provided(request, result)
                            )
                            all_warnings.extend(warnings)
                            if evidence_hash:
                                security_hashes["attestation_hash"] = evidence_hash
                            if not passed and not config.ATTESTATION_REQUIRED:
                                logger.warning(
                                    f"Attestation failed for {request.agent_id} (not required)"
                                )

                        # Add all warnings to result
                        for warning in all_warnings:
                            result.warnings.append(
                                {"type": "security_warning", "message": warning}
                            )

                        # Store security hashes for later binding
                        if security_hashes:
                            setattr(request, "_security_hashes", security_hashes)
                            logger.info(
                                f"Security validation complete for {request.agent_id}: "
                                f"hashes={list(security_hashes.keys())}"
                            )

                        # Stage 3: Endpoint validation
                        if config.ENDPOINT_VALIDATION_ENABLED:
                            result.current_step = "Checking agent endpoints..."
                            await store_validation_result_internal(
                                validation_id, result
                            )
                            logger.info(f"[{validation_id}] {result.current_step}")
                            await perform_endpoint_validation(request, result)

                        # Stage 4: Capability verification
                        result.current_step = "Verifying capabilities..."
                        await store_validation_result_internal(validation_id, result)
                        logger.info(f"[{validation_id}] {result.current_step}")
                        await verify_capabilities(request, result)

                    # Determine final status
                    if len(result.errors) == 0:
                        # Stage 5: Security binding (only if validation passed)
                        result.current_step = "Creating security binding..."
                        await store_validation_result_internal(validation_id, result)
                        logger.info(f"[{validation_id}] {result.current_step}")
                        # Include DPoP/mTLS bindings if provided
                        binding = create_security_binding(
                            request,
                            result,
                            dpop_jkt=getattr(request, "dpop_jkt", None),
                            mtls_spki=getattr(request, "mtls_spki", None),
                        )
                        result.binding = binding
                        result.status = "passed"
                    else:
                        result.status = "failed"

                    # Clear step when complete
                    result.current_step = None

                    # Calculate duration
                    result.duration_ms = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )

                    # Stage 5: Store in Redis with TTL
                    await store_validation_result_internal(validation_id, result)

                    logger.info(
                        f"Validation {validation_id} completed: {result.status} "
                        f"(duration: {result.duration_ms}ms, "
                        f"errors: {len(result.errors)}, "
                        f"warnings: {len(result.warnings)})"
                    )

                except Exception as e:
                    logger.error(
                        f"Validation {validation_id} failed with exception: {e}",
                        exc_info=True,
                    )
                    result.status = "failed"
                    result.errors.append({"type": "internal_error", "message": str(e)})
                    result.duration_ms = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )
                    await store_validation_result_internal(validation_id, result)

        except Exception as e:
            logger.error(f"Validation worker error: {e}", exc_info=True)
            await asyncio.sleep(1)  # Brief pause before retrying


# ========== Worker Management ==========

_worker_tasks = []


def start_validation_worker():
    """
    Start validation worker tasks.

    Spawns multiple worker tasks based on configuration
    (VALIDATION_WORKER_COUNT) to process validations in parallel.

    Call this during application startup.
    """
    if not config.FEATURE_THREE_PHASE:
        logger.info("Three-phase registration disabled, validation worker not started")
        return

    worker_count = config.VALIDATION_WORKER_COUNT
    logger.info(f"Starting {worker_count} validation worker(s)")

    for i in range(worker_count):
        task = asyncio.create_task(validation_worker())
        _worker_tasks.append(task)
        logger.info(f"Validation worker {i+1}/{worker_count} started")


def stop_validation_workers():
    """
    Stop all validation worker tasks.

    Call this during application shutdown to gracefully
    terminate worker tasks.
    """
    logger.info(f"Stopping {len(_worker_tasks)} validation worker(s)")

    for task in _worker_tasks:
        task.cancel()

    _worker_tasks.clear()
    logger.info("Validation workers stopped")
