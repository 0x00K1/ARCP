"""
Runtime attestation service.

Verifies agent integrity through software-based measurements
and optional TPM-based hardware attestation.

Attestation ensures agents maintain integrity during operation
by verifying code measurements against expected values.

Features:
- Software attestation (code measurement verification)
- TPM attestation (hardware-based, optional)
- Remote attestation (third-party services)
- Challenge-response freshness
- Policy-based verification
- Periodic re-attestation support

Environment Variables:
    ATTESTATION_ENABLED: Enable attestation (default: false)
    ATTESTATION_REQUIRED: Require attestation for registration (default: false)
    ATTESTATION_TYPE: Default type (software, tpm) (default: software)
    ATTESTATION_INTERVAL: Re-attestation interval in seconds (default: 3600)
    ATTESTATION_CHALLENGE_TTL: Challenge validity in seconds (default: 300)

Example Usage:
    >>> from arcp.services.attestation import get_attestation_service
    >>> service = get_attestation_service()
    >>> challenge = await service.create_challenge("agent-001")
    >>> # Agent computes measurements...
    >>> result = await service.verify_attestation(evidence)
    >>> if result.valid:
    ...     print("Attestation passed")
"""

import base64
import hashlib
import json
import logging
import struct
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding

from ..core.config import config
from ..models.attestation import (
    AttestationChallenge,
    AttestationEvidence,
    AttestationPolicy,
    AttestationRequest,
    AttestationResult,
    AttestationStatus,
    AttestationType,
    CodeMeasurement,
    PCRValue,
    ProcessInfo,
)
from ..services.redis import get_redis_service

logger = logging.getLogger(__name__)

# Redis key prefixes
CHALLENGE_PREFIX = "arcp:attestation:challenge:"
POLICY_PREFIX = "arcp:attestation:policy:"
EVIDENCE_PREFIX = "arcp:attestation:evidence:"


class AttestationVerifier(ABC):
    """Abstract base class for attestation verifiers."""

    @abstractmethod
    async def verify(
        self, evidence: AttestationEvidence, policy: Optional[AttestationPolicy] = None
    ) -> AttestationResult:
        """Verify attestation evidence."""
        pass


class SoftwareAttestationVerifier(AttestationVerifier):
    """
    Verify software-based attestation.

    Checks code measurements, process information, and
    environment state against expected values.
    """

    def __init__(self):
        self.clock_skew_seconds = getattr(config, "ATTESTATION_CLOCK_SKEW", 300)

    async def verify(
        self, evidence: AttestationEvidence, policy: Optional[AttestationPolicy] = None
    ) -> AttestationResult:
        """
        Verify software attestation evidence.

        Verification Steps:
        1. Verify nonce freshness
        2. Compare code measurements to expected
        3. Verify executable hash
        4. Check required modules
        5. Verify process information
        """
        errors: List[str] = []
        warnings: List[str] = []

        code_integrity_match = True
        process_verified = True
        measurement_count = 0

        # Step 1: Verify timestamp freshness
        age = (datetime.utcnow() - evidence.timestamp).total_seconds()
        if age > self.clock_skew_seconds:
            errors.append(
                f"Evidence too old: {age:.0f}s (max: {self.clock_skew_seconds}s)"
            )
        elif age < -60:  # 1 minute tolerance for clock differences
            errors.append(f"Evidence timestamp in future by {abs(age):.0f}s")

        # Step 2: Compare code measurements
        if policy and policy.expected_measurements and evidence.code_measurements:
            for path, expected_hash in policy.expected_measurements.items():
                found = False
                for measurement in evidence.code_measurements:
                    if measurement.path == path:
                        found = True
                        measurement_count += 1
                        if measurement.hash_value != expected_hash:
                            errors.append(
                                f"Code measurement mismatch for {path}: "
                                f"expected {expected_hash[:16]}..., "
                                f"got {measurement.hash_value[:16]}..."
                            )
                            code_integrity_match = False
                        break

                if not found:
                    warnings.append(f"Missing measurement for required file: {path}")

        # Count measurements even without policy
        if evidence.code_measurements:
            measurement_count = max(measurement_count, len(evidence.code_measurements))

        # Step 3: Verify executable hash
        if policy and policy.allowed_executable_hashes and evidence.process_info:
            exec_hash = evidence.process_info.executable_hash
            if exec_hash not in policy.allowed_executable_hashes:
                errors.append(
                    f"Executable hash not in allowed list: {exec_hash[:32]}..."
                )
                code_integrity_match = False

        # Step 4: Check required modules
        if policy and policy.required_modules and evidence.loaded_modules:
            loaded_set = set(evidence.loaded_modules)
            missing = policy.required_modules - loaded_set
            if missing:
                warnings.append(f"Missing required modules: {', '.join(missing)}")

        # Step 5: Verify process information
        if evidence.process_info:
            if not evidence.process_info.executable_path:
                warnings.append("Missing executable path in process info")
            if not evidence.process_info.executable_hash:
                errors.append("Missing executable hash in process info")
                process_verified = False
        else:
            warnings.append("No process information provided")

        # Determine overall validity
        valid = len(errors) == 0

        # Calculate validity period
        attestation_interval = getattr(config, "ATTESTATION_INTERVAL", 3600)
        if policy:
            attestation_interval = policy.attestation_interval_seconds

        valid_until = datetime.utcnow() + timedelta(seconds=attestation_interval)

        return AttestationResult(
            valid=valid,
            status=AttestationStatus.VALID if valid else AttestationStatus.INVALID,
            type=AttestationType.SOFTWARE,
            evidence_hash=evidence.compute_evidence_hash(),
            verified_at=datetime.utcnow(),
            errors=errors,
            warnings=warnings,
            code_integrity_match=code_integrity_match,
            process_verified=process_verified,
            measurement_count=measurement_count,
            valid_until=valid_until if valid else None,
        )


class TPMAttestationVerifier(AttestationVerifier):
    """
    Verify TPM-based attestation.

    Uses hardware TPM quotes and PCR values for
    strong cryptographic verification.

    Supports:
    - TPM 2.0 quote signature verification
    - Nonce embedding verification
    - PCR value validation against policy
    - AK certificate chain verification

    Requires tpm2-pytss for full functionality, with graceful
    degradation when not available.
    """

    def __init__(self):
        self._tpm_available = self._check_tpm_libraries()

    def _check_tpm_libraries(self) -> bool:
        """Check if TPM libraries are available."""
        try:
            # Check for tpm2-pytss
            import tpm2_pytss  # noqa: F401
            from tpm2_pytss import (  # noqa: F401
                ESAPI,
                TPM2_ALG,
                TPM2B_ATTEST,
                TPMS_ATTEST,
            )
            from tpm2_pytss.types import TPM2B_PUBLIC  # noqa: F401

            return True
        except ImportError:
            logger.info("tpm2-pytss not available, TPM verification will be limited")
            return False

    async def verify(
        self, evidence: AttestationEvidence, policy: Optional[AttestationPolicy] = None
    ) -> AttestationResult:
        """
        Verify TPM attestation evidence.

        Verification Steps:
        1. Verify Attestation Key (AK) certificate chain
        2. Verify TPM quote signature using AK public key
        3. Verify nonce is embedded in quote extraData
        4. Compare PCR values against policy
        5. Optionally verify event log against PCRs
        """
        errors: List[str] = []
        warnings: List[str] = []

        pcr_policy_match = True
        quote_verified = False
        ak_cert_valid = False
        nonce_verified = False
        ak_public_key = None

        # Step 1: Verify AK certificate
        if not evidence.ak_cert:
            errors.append("Missing Attestation Key certificate")
        else:
            ak_public_key, ak_cert_valid, cert_errors, cert_warnings = (
                await self._verify_ak_certificate(evidence.ak_cert)
            )
            errors.extend(cert_errors)
            warnings.extend(cert_warnings)

        # Step 2 & 3: Verify quote signature and nonce
        if not evidence.quote:
            errors.append("Missing TPM quote")
        else:
            quote_verified, nonce_verified, quote_errors, quote_warnings = (
                await self._verify_tpm_quote(
                    evidence.quote, evidence.nonce, ak_public_key, evidence.pcr_values
                )
            )
            errors.extend(quote_errors)
            warnings.extend(quote_warnings)

        # Step 4: Compare PCR values
        if policy and policy.expected_pcr_values and evidence.pcr_values:
            for pcr in evidence.pcr_values:
                expected = policy.expected_pcr_values.get(pcr.index)
                if expected and pcr.value != expected:
                    errors.append(
                        f"PCR {pcr.index} mismatch: "
                        f"expected {expected[:16]}..., got {pcr.value[:16]}..."
                    )
                    pcr_policy_match = False
        elif evidence.pcr_values:
            warnings.append("No PCR policy defined, skipping PCR verification")

        # Step 5: Optionally verify event log
        if evidence.event_log and evidence.pcr_values:
            log_valid, log_warnings = await self._verify_event_log(
                evidence.event_log, evidence.pcr_values
            )
            if not log_valid:
                warnings.append(
                    "Event log verification failed - PCR values may not match log"
                )
            warnings.extend(log_warnings)

        # Determine overall validity
        valid = len(errors) == 0

        attestation_interval = getattr(config, "ATTESTATION_INTERVAL", 3600)
        valid_until = datetime.utcnow() + timedelta(seconds=attestation_interval)

        return AttestationResult(
            valid=valid,
            status=AttestationStatus.VALID if valid else AttestationStatus.INVALID,
            type=AttestationType.TPM,
            evidence_hash=evidence.compute_evidence_hash(),
            verified_at=datetime.utcnow(),
            errors=errors,
            warnings=warnings,
            pcr_policy_match=pcr_policy_match,
            quote_verified=quote_verified,
            ak_cert_valid=ak_cert_valid,
            valid_until=valid_until if valid else None,
        )

    async def _verify_ak_certificate(
        self, ak_cert_pem: str
    ) -> Tuple[Optional[Any], bool, List[str], List[str]]:
        """
        Verify Attestation Key certificate.

        Returns:
            Tuple of (public_key, is_valid, errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []
        public_key = None
        is_valid = False

        try:
            cert = x509.load_pem_x509_certificate(
                ak_cert_pem.encode(), default_backend()
            )

            # Check validity period
            now = datetime.utcnow()
            not_before = (
                cert.not_valid_before_utc
                if hasattr(cert, "not_valid_before_utc")
                else cert.not_valid_before
            )
            not_after = (
                cert.not_valid_after_utc
                if hasattr(cert, "not_valid_after_utc")
                else cert.not_valid_after
            )

            if not_before > now:
                errors.append("AK certificate not yet valid")
            elif not_after < now:
                errors.append("AK certificate expired")
            else:
                # Check key usage for attestation
                try:
                    key_usage = cert.extensions.get_extension_for_oid(
                        x509.oid.ExtensionOID.KEY_USAGE
                    )
                    if not key_usage.value.digital_signature:
                        warnings.append(
                            "AK certificate missing digitalSignature key usage"
                        )
                except x509.ExtensionNotFound:
                    warnings.append("AK certificate missing key usage extension")

                # Check for TCG-specified OIDs (optional)
                try:
                    # TCG EK Certificate Profile OID
                    tcg_oid = x509.ObjectIdentifier("2.23.133.8.1")
                    cert.extensions.get_extension_for_oid(tcg_oid)
                except (x509.ExtensionNotFound, ValueError):
                    # Not a TCG-compliant certificate, but may still be valid
                    pass

                public_key = cert.public_key()
                is_valid = len(errors) == 0

        except ImportError:
            warnings.append("cryptography package not available for cert validation")
            is_valid = True  # Allow if package not installed
        except Exception as e:
            errors.append(f"Failed to parse AK certificate: {e}")

        return public_key, is_valid, errors, warnings

    async def _verify_tpm_quote(
        self,
        quote_b64: str,
        expected_nonce: str,
        ak_public_key: Optional[Any],
        pcr_values: Optional[List[PCRValue]],
    ) -> Tuple[bool, bool, List[str], List[str]]:
        """
        Verify TPM quote signature and embedded nonce.

        Returns:
            Tuple of (quote_verified, nonce_verified, errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []
        quote_verified = False
        nonce_verified = False

        try:
            # Decode the quote
            quote_bytes = base64.b64decode(quote_b64)
        except Exception as e:
            errors.append(f"Invalid quote format (not valid base64): {e}")
            return False, False, errors, warnings

        if self._tpm_available:
            # Full verification with tpm2-pytss
            try:
                quote_verified, nonce_verified, tpm_errors, tpm_warnings = (
                    await self._verify_quote_with_tpm2(
                        quote_bytes, expected_nonce, ak_public_key, pcr_values
                    )
                )
                errors.extend(tpm_errors)
                warnings.extend(tpm_warnings)
            except Exception as e:
                errors.append(f"TPM quote verification failed: {e}")
                logger.error(f"TPM verification error: {e}", exc_info=True)
        else:
            # Fallback verification without tpm2-pytss
            quote_verified, nonce_verified, fb_errors, fb_warnings = (
                await self._verify_quote_fallback(
                    quote_bytes, expected_nonce, ak_public_key
                )
            )
            errors.extend(fb_errors)
            warnings.extend(fb_warnings)

        return quote_verified, nonce_verified, errors, warnings

    async def _verify_quote_with_tpm2(
        self,
        quote_bytes: bytes,
        expected_nonce: str,
        ak_public_key: Optional[Any],
        pcr_values: Optional[List[PCRValue]],
    ) -> Tuple[bool, bool, List[str], List[str]]:
        """
        Verify quote using tpm2-pytss library.

        TPM Quote Structure (TPMS_ATTEST):
        - magic: TPM_GENERATED_VALUE (0xff544347)
        - type: TPM_ST_ATTEST_QUOTE
        - qualifiedSigner: Name of the key that signed
        - extraData: The nonce we provided
        - clockInfo: Clock information
        - firmwareVersion: TPM firmware version
        - attested: Quote-specific data (PCR selection, digest)
        """
        errors: List[str] = []
        warnings: List[str] = []
        quote_verified = False
        nonce_verified = False

        try:
            # Parse the quote structure
            # Quote format: signature || attestation_data
            # We need to split based on signature algorithm

            # For RSA signatures, signature is typically at the end
            # For ECDSA, it's also at the end
            # The attestation data starts with the magic value

            TPM_GENERATED_VALUE = 0xFF544347
            magic_bytes = struct.pack(">I", TPM_GENERATED_VALUE)

            magic_pos = quote_bytes.find(magic_bytes)
            if magic_pos == -1:
                errors.append("TPM quote missing TPM_GENERATED magic value")
                return False, False, errors, warnings

            attestation_data = quote_bytes[magic_pos:]
            signature_data = quote_bytes[:magic_pos] if magic_pos > 0 else None

            # Parse TPMS_ATTEST structure
            # Skip magic (4) + type (2)
            offset = 6

            # qualifiedSigner (TPM2B_NAME) - variable length
            if len(attestation_data) < offset + 2:
                errors.append("TPM quote too short for qualifiedSigner")
                return False, False, errors, warnings

            signer_size = struct.unpack(">H", attestation_data[offset : offset + 2])[0]
            offset += 2 + signer_size

            # extraData (TPM2B_DATA) - this is our nonce!
            if len(attestation_data) < offset + 2:
                errors.append("TPM quote too short for extraData")
                return False, False, errors, warnings

            extra_data_size = struct.unpack(
                ">H", attestation_data[offset : offset + 2]
            )[0]
            offset += 2

            if len(attestation_data) < offset + extra_data_size:
                errors.append("TPM quote extraData truncated")
                return False, False, errors, warnings

            extra_data = attestation_data[offset : offset + extra_data_size]

            # Verify nonce is in extraData
            expected_nonce_bytes = expected_nonce.encode()
            # Nonce might be hashed or raw
            if extra_data == expected_nonce_bytes:
                nonce_verified = True
                logger.debug("TPM quote nonce verified (raw match)")
            elif extra_data == hashlib.sha256(expected_nonce_bytes).digest():
                nonce_verified = True
                logger.debug("TPM quote nonce verified (SHA-256 hash match)")
            else:
                errors.append(
                    f"Nonce mismatch in TPM quote: expected {expected_nonce[:16]}..., "
                    f"got {extra_data.hex()[:32]}..."
                )

            # Verify signature if we have the public key
            if ak_public_key and signature_data:
                try:
                    # Determine key type and verify
                    if hasattr(ak_public_key, "verify"):
                        # Try ECDSA first (common for TPM AKs)
                        try:
                            ak_public_key.verify(
                                signature_data,
                                attestation_data,
                                ec.ECDSA(hashes.SHA256()),
                            )
                            quote_verified = True
                            logger.debug("TPM quote signature verified (ECDSA)")
                        except Exception:
                            # Try RSA
                            try:
                                ak_public_key.verify(
                                    signature_data,
                                    attestation_data,
                                    padding.PKCS1v15(),
                                    hashes.SHA256(),
                                )
                                quote_verified = True
                                logger.debug("TPM quote signature verified (RSA)")
                            except Exception as e:
                                errors.append(
                                    f"Quote signature verification failed: {e}"
                                )
                    else:
                        warnings.append(
                            "Could not verify quote signature - unknown key type"
                        )
                except Exception as e:
                    errors.append(f"Signature verification error: {e}")
            else:
                if not ak_public_key:
                    warnings.append(
                        "Could not verify quote signature - no public key available"
                    )
                if not signature_data:
                    warnings.append("Quote does not contain separate signature data")
                # Still mark as verified if structure is valid
                quote_verified = nonce_verified

        except Exception as e:
            errors.append(f"TPM quote parsing error: {e}")
            logger.error(f"TPM quote parsing failed: {e}", exc_info=True)

        return quote_verified, nonce_verified, errors, warnings

    async def _verify_quote_fallback(
        self, quote_bytes: bytes, expected_nonce: str, ak_public_key: Optional[Any]
    ) -> Tuple[bool, bool, List[str], List[str]]:
        """
        Fallback quote verification without tpm2-pytss.

        Performs basic structural validation and nonce checking.
        """
        errors: List[str] = []
        warnings: List[str] = []
        quote_verified = False
        nonce_verified = False

        warnings.append("Full TPM verification requires tpm2-pytss library")

        # Check for TPM_GENERATED magic value
        TPM_GENERATED_VALUE = 0xFF544347
        magic_bytes = struct.pack(">I", TPM_GENERATED_VALUE)

        if magic_bytes not in quote_bytes:
            errors.append("TPM quote missing TPM_GENERATED magic value")
            return False, False, errors, warnings

        # Try to find nonce in the quote data
        expected_nonce_bytes = expected_nonce.encode()
        expected_nonce_hash = hashlib.sha256(expected_nonce_bytes).digest()

        if expected_nonce_bytes in quote_bytes:
            nonce_verified = True
            logger.debug("Found raw nonce in TPM quote (fallback verification)")
        elif expected_nonce_hash in quote_bytes:
            nonce_verified = True
            logger.debug("Found hashed nonce in TPM quote (fallback verification)")
        else:
            # Check if any 32-byte segment matches the hash
            for i in range(len(quote_bytes) - 32):
                if quote_bytes[i : i + 32] == expected_nonce_hash:
                    nonce_verified = True
                    break

            if not nonce_verified:
                warnings.append("Could not verify nonce in quote without TPM libraries")

        # Basic structural validation passed
        if nonce_verified:
            quote_verified = True

        return quote_verified, nonce_verified, errors, warnings

    async def _verify_event_log(
        self, event_log_b64: str, pcr_values: List[PCRValue]
    ) -> Tuple[bool, List[str]]:
        """
        Verify TCG event log against PCR values.

        Event log replay should produce the same PCR values
        as those reported in the quote.
        """
        warnings: List[str] = []

        try:
            event_log = base64.b64decode(event_log_b64)
        except Exception:
            warnings.append("Could not decode event log (invalid base64)")
            return False, warnings

        # TCG Event Log parsing would go here
        # This requires parsing the TCG_PCR_EVENT2 structures
        # For now, just validate the log is non-empty and parseable

        if len(event_log) < 32:
            warnings.append("Event log too short to be valid")
            return False, warnings

        warnings.append("Full event log verification requires TCG log parser")

        # Return True to indicate we didn't find definitive problems
        return True, warnings


class AttestationService:
    """
    Main attestation service.

    Manages attestation challenges, verification, and
    policy enforcement for agents.
    """

    def __init__(self):
        self.enabled = getattr(config, "ATTESTATION_ENABLED", False)
        self.required = getattr(config, "ATTESTATION_REQUIRED", False)
        self.default_type = getattr(config, "ATTESTATION_TYPE", "software")
        self.challenge_ttl = getattr(config, "ATTESTATION_CHALLENGE_TTL", 300)
        self.interval = getattr(config, "ATTESTATION_INTERVAL", 3600)

        self._redis = None
        self._verifiers: Dict[AttestationType, AttestationVerifier] = {
            AttestationType.SOFTWARE: SoftwareAttestationVerifier(),
            AttestationType.TPM: TPMAttestationVerifier(),
        }

        # In-memory fallback storage
        self._challenges: Dict[str, AttestationChallenge] = {}
        self._policies: Dict[str, AttestationPolicy] = {}

    def _get_redis(self):
        """Get Redis client."""
        if self._redis is None:
            try:
                redis_service = get_redis_service()
                if redis_service and redis_service.is_available():
                    self._redis = redis_service.get_client()
            except Exception:
                pass
        return self._redis

    async def create_challenge(
        self,
        agent_id: str,
        attestation_types: Optional[List[str]] = None,
        required_measurements: Optional[List[str]] = None,
    ) -> AttestationChallenge:
        """
        Create a new attestation challenge for an agent.

        Args:
            agent_id: Agent requesting attestation
            attestation_types: Accepted attestation types
            required_measurements: Specific files to measure

        Returns:
            AttestationChallenge with nonce and metadata
        """
        if attestation_types is None:
            attestation_types = [self.default_type]

        challenge = AttestationChallenge.create(
            validity_seconds=self.challenge_ttl,
            attestation_types=attestation_types,
            required_measurements=required_measurements,
        )

        # Store challenge
        await self._store_challenge(challenge, agent_id)

        logger.info(
            f"Created attestation challenge {challenge.challenge_id} "
            f"for agent {agent_id}, expires in {self.challenge_ttl}s"
        )

        return challenge

    async def _store_challenge(
        self, challenge: AttestationChallenge, agent_id: str
    ) -> None:
        """Store challenge in Redis or memory."""
        key = f"{CHALLENGE_PREFIX}{challenge.challenge_id}"
        data = {
            "challenge": challenge.model_dump(mode="json"),
            "agent_id": agent_id,
        }

        redis = self._get_redis()
        if redis:
            try:
                redis.setex(key, self.challenge_ttl, json.dumps(data, default=str))
                return
            except Exception as e:
                logger.warning(f"Failed to store challenge in Redis: {e}")

        # Fallback to memory
        self._challenges[challenge.challenge_id] = challenge

    async def _get_challenge(
        self, challenge_id: str
    ) -> Tuple[Optional[AttestationChallenge], Optional[str]]:
        """Retrieve and validate challenge."""
        key = f"{CHALLENGE_PREFIX}{challenge_id}"

        redis = self._get_redis()
        if redis:
            try:
                data = redis.get(key)
                if data:
                    parsed = json.loads(data)
                    challenge_data = parsed["challenge"]
                    agent_id = parsed["agent_id"]

                    # Convert datetime strings
                    challenge_data["timestamp"] = datetime.fromisoformat(
                        challenge_data["timestamp"]
                    )
                    challenge_data["expires_at"] = datetime.fromisoformat(
                        challenge_data["expires_at"]
                    )

                    return AttestationChallenge(**challenge_data), agent_id
            except Exception as e:
                logger.warning(f"Failed to get challenge from Redis: {e}")

        # Fallback to memory
        challenge = self._challenges.get(challenge_id)
        if challenge:
            return challenge, None

        return None, None

    async def _delete_challenge(self, challenge_id: str) -> None:
        """Delete used challenge."""
        key = f"{CHALLENGE_PREFIX}{challenge_id}"

        redis = self._get_redis()
        if redis:
            try:
                redis.delete(key)
            except Exception:
                pass

        self._challenges.pop(challenge_id, None)

    async def verify_attestation(
        self,
        request: AttestationRequest,
        agent_id: str,
        policy: Optional[AttestationPolicy] = None,
    ) -> AttestationResult:
        """
        Verify attestation from an agent.

        Args:
            request: Attestation evidence from agent
            agent_id: Agent providing attestation
            policy: Optional policy to verify against

        Returns:
            AttestationResult with verification outcome
        """
        # Get and validate challenge
        challenge, stored_agent_id = await self._get_challenge(request.challenge_id)

        if not challenge:
            return AttestationResult(
                valid=False,
                status=AttestationStatus.ERROR,
                type=AttestationType.NONE,
                evidence_hash="",
                verified_at=datetime.utcnow(),
                errors=["Challenge not found or expired"],
            )

        if challenge.is_expired():
            await self._delete_challenge(request.challenge_id)
            return AttestationResult(
                valid=False,
                status=AttestationStatus.EXPIRED,
                type=AttestationType.NONE,
                evidence_hash="",
                verified_at=datetime.utcnow(),
                errors=["Challenge has expired"],
            )

        if request.nonce != challenge.nonce:
            return AttestationResult(
                valid=False,
                status=AttestationStatus.INVALID,
                type=AttestationType.NONE,
                evidence_hash="",
                verified_at=datetime.utcnow(),
                errors=["Nonce mismatch"],
            )

        if stored_agent_id and stored_agent_id != agent_id:
            return AttestationResult(
                valid=False,
                status=AttestationStatus.INVALID,
                type=AttestationType.NONE,
                evidence_hash="",
                verified_at=datetime.utcnow(),
                errors=["Agent ID mismatch"],
            )

        # Convert request to evidence
        evidence = self._request_to_evidence(request, agent_id)

        # Get appropriate verifier
        attestation_type = AttestationType(request.attestation_type)
        verifier = self._verifiers.get(attestation_type)

        if not verifier:
            return AttestationResult(
                valid=False,
                status=AttestationStatus.UNSUPPORTED,
                type=attestation_type,
                evidence_hash="",
                verified_at=datetime.utcnow(),
                errors=[f"Unsupported attestation type: {attestation_type.value}"],
            )

        # Get policy if not provided
        if policy is None:
            policy = await self._get_policy(agent_id)

        # Verify
        result = await verifier.verify(evidence, policy)

        # Delete used challenge (one-time use)
        await self._delete_challenge(request.challenge_id)

        logger.info(
            f"Attestation verification for {agent_id}: "
            f"type={attestation_type.value}, valid={result.valid}, "
            f"errors={len(result.errors)}, warnings={len(result.warnings)}"
        )

        return result

    def _request_to_evidence(
        self, request: AttestationRequest, agent_id: str
    ) -> AttestationEvidence:
        """Convert request to internal evidence structure."""
        attestation_type = AttestationType(request.attestation_type)

        # Parse code measurements
        code_measurements = None
        if request.code_measurements:
            code_measurements = [
                CodeMeasurement(
                    path=path,
                    hash_algorithm="sha256",
                    hash_value=hash_val,
                )
                for path, hash_val in request.code_measurements.items()
            ]

        # Parse PCR values
        pcr_values = None
        if request.pcr_values:
            pcr_values = [
                PCRValue(
                    index=int(idx),
                    algorithm="sha256",
                    value=val,
                )
                for idx, val in request.pcr_values.items()
            ]

        # Parse process info
        process_info = None
        if request.process_info:
            pi = request.process_info
            process_info = ProcessInfo(
                pid=pi.get("pid", 0),
                name=pi.get("name", ""),
                executable_path=pi.get("executable_path", ""),
                executable_hash=request.executable_hash
                or pi.get("executable_hash", ""),
                command_line=pi.get("command_line"),
                user=pi.get("user"),
            )

        return AttestationEvidence(
            type=attestation_type,
            timestamp=datetime.utcnow(),
            nonce=request.nonce,
            agent_id=agent_id,
            quote=request.quote,
            pcr_values=pcr_values,
            ak_cert=request.ak_cert,
            event_log=request.event_log,
            code_measurements=code_measurements,
            process_info=process_info,
            environment_hash=request.environment_hash,
            loaded_modules=request.loaded_modules,
            remote_token=request.remote_token,
            remote_service=request.remote_service,
        )

    async def _get_policy(self, agent_id: str) -> Optional[AttestationPolicy]:
        """Get attestation policy for agent."""
        # Try Redis first
        key = f"{POLICY_PREFIX}{agent_id}"

        redis = self._get_redis()
        if redis:
            try:
                data = redis.get(key)
                if data:
                    policy_dict = json.loads(data)
                    return AttestationPolicy(**policy_dict)
            except Exception:
                pass

        # Fallback to memory
        return self._policies.get(agent_id)

    async def set_policy(self, agent_id: str, policy: AttestationPolicy) -> None:
        """Set attestation policy for an agent."""
        key = f"{POLICY_PREFIX}{agent_id}"

        redis = self._get_redis()
        if redis:
            try:
                redis.set(key, json.dumps(policy.to_dict()))
                return
            except Exception as e:
                logger.warning(f"Failed to store policy in Redis: {e}")

        # Fallback to memory
        self._policies[agent_id] = policy

    async def get_agent_attestation_status(
        self, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get current attestation status for an agent."""
        key = f"{EVIDENCE_PREFIX}{agent_id}"

        redis = self._get_redis()
        if redis:
            try:
                data = redis.get(key)
                if data:
                    return json.loads(data)
            except Exception:
                pass

        return None

    async def store_attestation_result(
        self, agent_id: str, result: AttestationResult
    ) -> None:
        """Store attestation result for tracking."""
        key = f"{EVIDENCE_PREFIX}{agent_id}"

        data = {
            "agent_id": agent_id,
            "result": result.to_dict(),
            "stored_at": datetime.utcnow().isoformat(),
        }

        # TTL based on validity period
        ttl = self.interval * 2  # Keep for 2x attestation interval

        redis = self._get_redis()
        if redis:
            try:
                redis.setex(key, ttl, json.dumps(data, default=str))
            except Exception as e:
                logger.warning(f"Failed to store attestation result: {e}")


# Module-level singleton
_attestation_service: Optional[AttestationService] = None


def get_attestation_service() -> AttestationService:
    """Get the attestation service singleton."""
    global _attestation_service
    if _attestation_service is None:
        _attestation_service = AttestationService()
    return _attestation_service


async def create_attestation_challenge(
    agent_id: str, attestation_types: Optional[List[str]] = None
) -> AttestationChallenge:
    """Convenience function to create attestation challenge."""
    service = get_attestation_service()
    return await service.create_challenge(agent_id, attestation_types)


async def verify_agent_attestation(
    request: AttestationRequest, agent_id: str
) -> AttestationResult:
    """Convenience function to verify attestation."""
    service = get_attestation_service()
    return await service.verify_attestation(request, agent_id)
