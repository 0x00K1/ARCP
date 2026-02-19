"""
Endpoint Contract Validator for TPR Phase 2.

This module validates that agent endpoints conform to the ARCP contract
specification, ensuring they provide required endpoints with correct schemas.

Supports two validation modes:
- STATIC: Uses predefined endpoint contracts for 14 standard endpoints
- DYNAMIC: Uses admin-configured custom endpoints from a YAML file

Standard Static Endpoints (v1.0.0):
1. GET /                              - Service information and agent capabilities
2. GET /ping                          - Quick ping for service discovery
3. GET /health                        - Basic health check
4. GET /health/detailed               - Comprehensive health check
5. GET /metrics                       - Prometheus-compatible metrics
6. POST /agents/{agent_id}/heartbeat  - Receive heartbeat from ARCP
7. POST /agents/{agent_id}/metrics    - Receive metrics from ARCP
8. POST /agents/report-metrics/{agent_id} - Report metrics to ARCP
9. POST /connection/request           - Handle connection request from client
10. POST /connection/configure        - Configure connection with client
11. GET /connection/status/{user_id}  - Check connection status
12. POST /connection/disconnect       - Disconnect client
13. POST /connection/notify           - Handle agent-to-agent notification
14. GET /search/agents                - Search for other agents via ARCP
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
import yaml
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from ..core.config import config

logger = logging.getLogger(__name__)


# ========== Dynamic Schema Definition ==========


class DynamicEndpointSchema(BaseModel):
    """Schema definition for dynamic endpoint validation"""

    path: str = Field(..., description="Endpoint path (e.g., '/health')")
    method: Literal["GET", "POST", "PUT", "DELETE"] = Field(default="GET")
    timeout: int = Field(default=5, ge=1, le=60, description="Timeout in seconds")
    required: bool = Field(
        default=True, description="If false, failures become warnings"
    )
    expected_status: List[int] = Field(
        default=[200], description="Expected HTTP status codes"
    )
    request_body: Optional[Dict[str, Any]] = Field(
        None, description="Request body for POST/PUT (for testing)"
    )
    response_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for response validation"
    )
    required_fields: Optional[List[str]] = Field(
        None, description="Required fields in response"
    )
    field_validations: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Field-specific validations: {field: {type, enum, pattern, min, max}}",
    )
    description: Optional[str] = Field(None, description="Human-readable description")


# ========== Static Endpoint Definitions ==========

STATIC_ENDPOINTS: List[DynamicEndpointSchema] = [
    # Root service information
    DynamicEndpointSchema(
        path="/",
        method="GET",
        timeout=10,
        required=True,
        expected_status=[200],
        required_fields=[
            "service",
            "version",
            "status",
            "agent_id",
            "capabilities",
            "features",
        ],
        field_validations={
            "service": {"type": "string"},
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "status": {
                "type": "string",
                "enum": ["starting", "healthy", "degraded", "unhealthy"],
            },
            "agent_id": {"type": "string"},
            "capabilities": {"type": "array"},
            "features": {"type": "array"},
            "api_docs": {"type": "string", "required": False},
            "health": {"type": "string", "required": False},
            "metrics": {"type": "string", "required": False},
        },
        description="Service information and agent capabilities",
    ),
    # Ping endpoint
    DynamicEndpointSchema(
        path="/ping",
        method="GET",
        timeout=5,
        required=True,
        expected_status=[200],
        required_fields=["status", "agent_id", "timestamp"],
        field_validations={
            "status": {"type": "string", "pattern": r"pong"},
            "agent_id": {"type": "string"},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
            "response_time": {"type": "string", "required": False},
        },
        description="Quick ping for service discovery and availability check",
    ),
    # Simple health check
    DynamicEndpointSchema(
        path="/health",
        method="GET",
        timeout=5,
        required=True,
        expected_status=[200],
        required_fields=["status", "agent_id", "timestamp"],
        field_validations={
            "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
            "agent_id": {"type": "string"},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
        },
        description="Basic health check for load balancers and monitoring",
    ),
    # Detailed health check
    DynamicEndpointSchema(
        path="/health/detailed",
        method="GET",
        timeout=10,
        required=True,
        expected_status=[200],
        required_fields=["status", "timestamp", "version", "agent_id", "components"],
        field_validations={
            "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "agent_id": {"type": "string"},
            "components": {"type": "object"},
            "performance": {"type": "object", "required": False},
            "external_services": {"type": "object", "required": False},
            "recommendations": {"type": "array", "required": False},
        },
        description="Comprehensive health check with component status and metrics",
    ),
    # Prometheus metrics
    DynamicEndpointSchema(
        path="/metrics",
        method="GET",
        timeout=10,
        required=True,
        expected_status=[200],
        description="Prometheus-compatible metrics endpoint",
    ),
    # Heartbeat from ARCP
    DynamicEndpointSchema(
        path="/agents/{agent_id}/heartbeat",
        method="POST",
        timeout=10,
        required=True,
        expected_status=[200],
        required_fields=["agent_id", "status", "timestamp", "version"],
        field_validations={
            "agent_id": {"type": "string"},
            "status": {"type": "string", "enum": ["alive", "active", "ready"]},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
            "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
            "uptime": {"type": "string", "required": False},
            "capabilities": {"type": "array", "required": False},
            "features": {"type": "array", "required": False},
        },
        description="Receive heartbeat signal from ARCP",
    ),
    # Metrics from ARCP
    DynamicEndpointSchema(
        path="/agents/{agent_id}/metrics",
        method="POST",
        timeout=10,
        required=False,
        expected_status=[200],
        request_body={"metrics_data": {}},
        required_fields=["status", "agent_id", "timestamp", "processed"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["received", "processed", "acknowledged"],
            },
            "agent_id": {"type": "string"},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
            "processed": {"type": "boolean"},
        },
        description="Receive metrics data from ARCP",
    ),
    # Report metrics to ARCP
    DynamicEndpointSchema(
        path="/agents/report-metrics/{agent_id}",
        method="POST",
        timeout=10,
        required=True,
        expected_status=[200],
        request_body={
            "metrics_data": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 1.0,
                "avg_response_time": 0.5,
                "reputation_score": 8.0,
            }
        },
        required_fields=["status", "agent_id", "timestamp", "processed"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["reported", "received", "acknowledged"],
            },
            "agent_id": {"type": "string"},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
            },
            "processed": {"type": "boolean"},
        },
        description="Report performance metrics to ARCP",
    ),
    # Connection request (from ARCP → Agent)
    DynamicEndpointSchema(
        path="/connection/request",
        method="POST",
        timeout=15,
        required=True,
        expected_status=[200],
        request_body={
            "user_id": "validation-test-user",
            "user_endpoint": "https://validation.arcp.test",
            "user_display_name": "Validation Test Client",
            "connection_type": "external_app",
            "timestamp": "2026-02-12T00:00:00Z",
            "request_source": "validation",
            "user_info": {"test": True, "validation": True},
        },
        required_fields=["status", "message"],
        field_validations={
            "status": {
                "type": "string",
                "enum": [
                    "connection_request_received",
                    "requirements_needed",
                    "accepted",
                    "rejected",
                ],
            },
            "message": {"type": "string"},
            "requirements": {"type": "object", "required": False},
            "agent_id": {"type": "string", "required": False},
        },
        description="Handle connection request from client via ARCP",
    ),
    # Connection configuration (from Client → Agent)
    DynamicEndpointSchema(
        path="/connection/configure",
        method="POST",
        timeout=20,
        required=True,
        expected_status=[200],
        request_body={
            "user_id": "validation-test-user",
            "user_endpoint": "https://validation.arcp.test",
            "registration": {"test": True},
        },
        required_fields=["status", "message", "user_id", "registration_id"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["connected", "pending", "rejected", "error"],
            },
            "message": {"type": "string"},
            "user_id": {"type": "string"},
            "registration_id": {"type": "string"},
            "agent_token": {"type": "string", "required": False},
            "capabilities_enabled": {"type": "array", "required": False},
            "monitoring_started": {"type": "boolean", "required": False},
            "recommended_actions": {"type": "array", "required": False},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                "required": False,
            },
        },
        description="Configure connection with client registration data",
    ),
    # Connection status check
    DynamicEndpointSchema(
        path="/connection/status/{user_id}",
        method="GET",
        timeout=10,
        required=True,
        expected_status=[200],
        required_fields=["status", "user_id"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["connected", "not_connected", "pending", "suspended"],
            },
            "user_id": {"type": "string"},
            "registration_date": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                "required": False,
            },
            "last_activity": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                "required": False,
            },
            "message": {"type": "string", "required": False},
        },
        description="Check connection status for a client",
    ),
    # Disconnect client
    DynamicEndpointSchema(
        path="/connection/disconnect",
        method="POST",
        timeout=10,
        required=True,
        expected_status=[200],
        request_body={
            "user_id": "validation-test-user",
            "reason": "validation-test",
        },
        required_fields=["status"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["disconnected", "not_found", "error"],
            },
            "user_id": {"type": "string", "required": False},
            "message": {"type": "string", "required": False},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                "required": False,
            },
        },
        description="Disconnect client and cleanup resources",
    ),
    # Connection notify (Agent-to-Agent via ARCP)
    DynamicEndpointSchema(
        path="/connection/notify",
        method="POST",
        timeout=15,
        required=True,
        expected_status=[200],
        request_body={
            "agent_id": "validation-test-agent",
            "agent_endpoint": "https://validation.arcp.test",
            "agent_info": {"test": True, "validation": True},
        },
        required_fields=["status", "message"],
        field_validations={
            "status": {
                "type": "string",
                "enum": ["notified", "accepted", "rejected", "not_found"],
            },
            "message": {"type": "string"},
            "agent_endpoint": {"type": "string", "required": False},
            "timestamp": {
                "type": "string",
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                "required": False,
            },
            "next_step": {"type": "string", "required": False},
        },
        description="Handle agent-to-agent connection notification via ARCP",
    ),
    # Agent search (via ARCP)
    DynamicEndpointSchema(
        path="/search/agents",
        method="GET",
        timeout=15,
        required=False,
        expected_status=[200],
        required_fields=["agents", "total_results", "query"],
        field_validations={
            "agents": {"type": "array"},
            "total_results": {"type": "integer", "min": 0},
            "query": {"type": "string"},
            "search_type": {"type": "string", "required": False},
            "processing_time": {"type": "number", "required": False},
        },
        description="Search for other agents via ARCP",
    ),
]


# ========== Validation Result Models ==========


class ValidationError(BaseModel):
    """An error encountered during endpoint validation"""

    endpoint: str
    type: str
    message: str
    details: Optional[Dict] = None

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


class ValidationWarning(BaseModel):
    """A warning encountered during endpoint validation"""

    endpoint: str
    type: str
    message: str

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


class EndpointCheckResult(BaseModel):
    """Result of a single endpoint check"""

    endpoint: str
    method: str = "GET"
    status: Literal["passed", "failed", "warning", "skipped"]
    response_time_ms: Optional[int] = None
    error: Optional[str] = None
    details: Optional[Dict] = None


class EndpointValidationResult:
    """
    Container for endpoint validation results.

    Tracks overall validation status, individual endpoint checks,
    errors, and warnings.
    """

    def __init__(self, agent_id: str, mode: str = "static"):
        self.agent_id = agent_id
        self.mode = mode
        self.checks: Dict[str, EndpointCheckResult] = {}
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationWarning] = []
        self.started_at: datetime = datetime.utcnow()
        self.completed_at: Optional[datetime] = None

    def add_check(self, result: EndpointCheckResult):
        """Add an endpoint check result"""
        key = f"{result.method}:{result.endpoint}"
        self.checks[key] = result

    def add_error(self, error: ValidationError):
        """Add a validation error"""
        self.errors.append(error)

    def add_warning(self, warning: ValidationWarning):
        """Add a validation warning"""
        self.warnings.append(warning)

    def complete(self):
        """Mark validation as complete"""
        self.completed_at = datetime.utcnow()

    def is_valid(self) -> bool:
        """Check if validation passed (no critical errors)"""
        return len(self.errors) == 0

    def duration_ms(self) -> int:
        """Get total validation duration in milliseconds"""
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return int((datetime.utcnow() - self.started_at).total_seconds() * 1000)

    def get_summary(self) -> dict:
        """Get summary of validation results"""
        return {
            "agent_id": self.agent_id,
            "mode": self.mode,
            "valid": self.is_valid(),
            "duration_ms": self.duration_ms(),
            "checks": {
                name: {
                    "status": check.status,
                    "method": check.method,
                    "response_time_ms": check.response_time_ms,
                    "error": check.error,
                }
                for name, check in self.checks.items()
            },
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


# ========== Field Validation Helpers ==========


def validate_field(
    field_name: str, value: Any, rules: Dict[str, Any], parent_path: str = ""
) -> List[str]:
    """
    Validate a single field against rules.

    Returns list of error messages (empty if valid).
    """
    errors = []
    full_path = f"{parent_path}.{field_name}" if parent_path else field_name

    # Check if field is required
    is_required = rules.get("required", True)
    if value is None:
        if is_required:
            errors.append(f"Required field '{full_path}' is missing")
        return errors

    # Type validation
    expected_type = rules.get("type")
    if expected_type:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        python_type = type_map.get(expected_type)
        if python_type and not isinstance(value, python_type):
            errors.append(
                f"Field '{full_path}' expected {expected_type}, got {type(value).__name__}"
            )
            return errors  # Stop further validation on type mismatch

    # Enum validation
    if "enum" in rules and value not in rules["enum"]:
        errors.append(
            f"Field '{full_path}' value '{value}' not in allowed values: {rules['enum']}"
        )

    # Pattern validation (for strings)
    if "pattern" in rules and isinstance(value, str):
        if not re.match(rules["pattern"], value):
            errors.append(
                f"Field '{full_path}' value '{value}' doesn't match pattern: {rules['pattern']}"
            )

    # Min/max validation (for numbers)
    if isinstance(value, (int, float)):
        if "min" in rules and value < rules["min"]:
            errors.append(
                f"Field '{full_path}' value {value} is below minimum {rules['min']}"
            )
        if "max" in rules and value > rules["max"]:
            errors.append(
                f"Field '{full_path}' value {value} exceeds maximum {rules['max']}"
            )

    # Array item validation
    if isinstance(value, list) and "items" in rules:
        for i, item in enumerate(value):
            item_errors = validate_field(f"[{i}]", item, rules["items"], full_path)
            errors.extend(item_errors)

    return errors


def validate_response_schema(
    data: Dict[str, Any],
    required_fields: Optional[List[str]],
    field_validations: Optional[Dict[str, Dict[str, Any]]],
) -> List[str]:
    """
    Validate response data against schema rules.

    Returns list of error messages.
    """
    errors = []

    # Check required fields
    if required_fields:
        for field in required_fields:
            if field not in data:
                errors.append(f"Required field '{field}' is missing")

    # Validate field-specific rules
    if field_validations:
        for field_name, rules in field_validations.items():
            value = data.get(field_name)
            field_errors = validate_field(field_name, value, rules)
            errors.extend(field_errors)

    return errors


# ========== Endpoint Validator ==========


class EndpointValidator:
    """
    Validates agent endpoints against ARCP contract specifications.

    Supports two modes:
    - STATIC: Uses predefined endpoint contracts
    - DYNAMIC: Uses admin-configured custom endpoints
    """

    def __init__(
        self,
        agent_id: str,
        agent_endpoint: str,
        declared_capabilities: List[str],
        mode: Optional[str] = None,
    ):
        """
        Initialize endpoint validator.

        Args:
            agent_id: Agent identifier
            agent_endpoint: Base URL for agent (e.g., "https://agent.example.com")
            declared_capabilities: Capabilities declared during registration
            mode: Validation mode ("static" or "dynamic"), defaults to config
        """
        self.agent_id = agent_id
        self.agent_endpoint = agent_endpoint.rstrip("/")
        self.declared_capabilities = declared_capabilities
        self.mode = mode or getattr(config, "ENDPOINT_VALIDATION_MODE", "static")
        self.result = EndpointValidationResult(agent_id, self.mode)

        # Load endpoint definitions based on mode
        if self.mode == "static":
            logger.info(
                f"Using STATIC endpoint validation for agent {agent_id} "
                f"(14 predefined ARCP v1.0.0 contracts)"
            )
            self.endpoints = STATIC_ENDPOINTS
        else:
            logger.info(
                f"Using DYNAMIC endpoint validation for agent {agent_id} "
                f"(custom contracts from config file)"
            )
            self.endpoints = self._load_dynamic_endpoints()

    def _load_dynamic_endpoints(self) -> List[DynamicEndpointSchema]:
        """
        Load dynamic endpoint definitions from a configuration file.

        Supports YAML (.yaml, .yml) and JSON (.json) formats.
        The file must follow the endpoint contracts schema (v1.0).

        Returns:
            List of endpoint definitions, or STATIC_ENDPOINTS if loading fails
        """
        try:
            # Get contracts file path from config
            contracts_file = getattr(config, "ENDPOINT_CONTRACTS_FILE", None)

            if not contracts_file:
                logger.warning(
                    "Dynamic mode enabled but ARCP_TPR_ENDPOINT_CONTRACTS_FILE not set, "
                    "falling back to static endpoints"
                )
                return STATIC_ENDPOINTS

            # Resolve path
            file_path = Path(contracts_file)
            if not file_path.is_absolute():
                # Try relative to config directory or current directory
                config_dir = Path(__file__).parent.parent.parent.parent / "config"
                if (config_dir / contracts_file).exists():
                    file_path = config_dir / contracts_file
                elif not file_path.exists():
                    logger.error(f"Endpoint contracts file not found: {contracts_file}")
                    return STATIC_ENDPOINTS

            if not file_path.exists():
                logger.error(f"Endpoint contracts file not found: {file_path}")
                return STATIC_ENDPOINTS

            # Load file based on extension
            file_content = self._load_contracts_file(file_path)
            if file_content is None:
                return STATIC_ENDPOINTS

            # Validate file structure
            endpoints = self._parse_contracts_file(file_content, str(file_path))
            if not endpoints:
                logger.warning(
                    "No valid endpoints in contracts file, falling back to static"
                )
                return STATIC_ENDPOINTS

            logger.info(
                f"Loaded {len(endpoints)} dynamic endpoint definitions from {file_path}"
            )
            return endpoints

        except Exception as e:
            logger.error(f"Error loading dynamic endpoints: {e}")
            return STATIC_ENDPOINTS

    def _load_contracts_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load endpoint contracts from a YAML file.

        Args:
            file_path: Path to the contracts file (.yaml or .yml)

        Returns:
            Parsed file content as dict, or None if loading fails
        """
        suffix = file_path.suffix.lower()

        if suffix not in (".yaml", ".yml"):
            logger.error(
                f"Endpoint contracts file must be YAML format (.yaml or .yml), "
                f"got: {suffix}"
            )
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML contracts file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read contracts file {file_path}: {e}")
            return None

    def _parse_contracts_file(
        self, content: Dict[str, Any], file_path: str
    ) -> List[DynamicEndpointSchema]:
        """
        Parse and validate endpoint contracts file content.

        Args:
            content: Parsed file content
            file_path: Path to file (for error messages)

        Returns:
            List of validated endpoint definitions
        """
        # Validate version
        version = content.get("version")
        if version != "1.0":
            logger.error(
                f"Unsupported contracts file version: {version}. "
                f"Expected '1.0'. File: {file_path}"
            )
            return []

        # Get endpoints
        endpoints_data = content.get("endpoints", [])
        if not endpoints_data:
            logger.error(f"No endpoints defined in contracts file: {file_path}")
            return []

        # Parse each endpoint
        endpoints = []
        for i, ep_data in enumerate(endpoints_data):
            try:
                # Convert field_validations from YAML format if needed
                if "field_validations" in ep_data:
                    ep_data["field_validations"] = self._normalize_field_validations(
                        ep_data["field_validations"]
                    )

                endpoint = DynamicEndpointSchema(**ep_data)
                endpoints.append(endpoint)
                logger.debug(f"Loaded endpoint: {endpoint.method} {endpoint.path}")
            except PydanticValidationError as e:
                logger.error(f"Invalid endpoint definition #{i+1} in {file_path}: {e}")
            except Exception as e:
                logger.error(f"Error parsing endpoint #{i+1} in {file_path}: {e}")

        return endpoints

    def _normalize_field_validations(
        self, field_validations: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Normalize field validations from YAML format to expected dict format.

        YAML allows more readable formats that need to be converted.
        """
        normalized = {}
        for field_name, rules in field_validations.items():
            if isinstance(rules, dict):
                normalized[field_name] = rules
            elif isinstance(rules, str):
                # Simple type definition like "status: string"
                normalized[field_name] = {"type": rules}
            else:
                normalized[field_name] = {"type": str(rules)}
        return normalized

    async def validate_endpoint(
        self, endpoint_def: DynamicEndpointSchema
    ) -> EndpointCheckResult:
        """
        Validate a single endpoint against its definition.

        Args:
            endpoint_def: Endpoint definition with validation rules

        Returns:
            EndpointCheckResult with validation status
        """
        start_time = datetime.utcnow()
        path = endpoint_def.path
        method = endpoint_def.method

        # Replace path parameters with validation test values
        url_path = path
        if "{agent_id}" in url_path:
            url_path = url_path.replace("{agent_id}", self.agent_id)
        if "{user_id}" in url_path:
            url_path = url_path.replace("{user_id}", "validation-test-user")

        url = f"{self.agent_endpoint}{url_path}"

        try:
            async with httpx.AsyncClient(timeout=endpoint_def.timeout) as client:
                # Make request based on method
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url, json=endpoint_def.request_body or {})
                elif method == "PUT":
                    resp = await client.put(url, json=endpoint_def.request_body or {})
                elif method == "DELETE":
                    resp = await client.delete(url)
                else:
                    resp = await client.get(url)

                response_time_ms = int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                )

                # Check HTTP status
                if resp.status_code not in endpoint_def.expected_status:
                    error_msg = f"Expected HTTP {endpoint_def.expected_status}, got {resp.status_code}"
                    if endpoint_def.required:
                        self.result.add_error(
                            ValidationError(
                                endpoint=path,
                                type="http_status_error",
                                message=error_msg,
                                details={"status_code": resp.status_code},
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="failed",
                            response_time_ms=response_time_ms,
                            error=f"HTTP {resp.status_code}",
                        )
                    else:
                        self.result.add_warning(
                            ValidationWarning(
                                endpoint=path,
                                type="http_status_warning",
                                message=f"{error_msg} (non-fatal)",
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="warning",
                            response_time_ms=response_time_ms,
                            error=f"HTTP {resp.status_code}",
                        )

                # Try to parse JSON response
                try:
                    # Special handling for /metrics - accept Prometheus format
                    content_type = resp.headers.get("content-type", "")
                    if path == "/metrics" and (
                        "text/plain" in content_type or "text" in content_type
                    ):
                        # Prometheus format - just check non-empty
                        if len(resp.text.strip()) > 0:
                            return EndpointCheckResult(
                                endpoint=path,
                                method=method,
                                status="passed",
                                response_time_ms=response_time_ms,
                                details={"format": "prometheus"},
                            )
                        else:
                            self.result.add_warning(
                                ValidationWarning(
                                    endpoint=path,
                                    type="empty_response",
                                    message="Metrics endpoint returned empty response",
                                )
                            )
                            return EndpointCheckResult(
                                endpoint=path,
                                method=method,
                                status="warning",
                                response_time_ms=response_time_ms,
                                error="Empty response",
                            )

                    data = resp.json()
                except Exception:
                    if endpoint_def.required:
                        self.result.add_error(
                            ValidationError(
                                endpoint=path,
                                type="invalid_json",
                                message="Response is not valid JSON",
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="failed",
                            response_time_ms=response_time_ms,
                            error="Invalid JSON",
                        )
                    else:
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="warning",
                            response_time_ms=response_time_ms,
                            error="Invalid JSON (non-fatal)",
                        )

                # Validate response schema
                schema_errors = validate_response_schema(
                    data,
                    endpoint_def.required_fields,
                    endpoint_def.field_validations,
                )

                if schema_errors:
                    if endpoint_def.required:
                        self.result.add_error(
                            ValidationError(
                                endpoint=path,
                                type="schema_validation_error",
                                message="; ".join(schema_errors),
                                details={"errors": schema_errors},
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="failed",
                            response_time_ms=response_time_ms,
                            error=f"{len(schema_errors)} schema errors",
                            details={"errors": schema_errors},
                        )
                    else:
                        self.result.add_warning(
                            ValidationWarning(
                                endpoint=path,
                                type="schema_validation_warning",
                                message=f"Schema warnings: {'; '.join(schema_errors)}",
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="warning",
                            response_time_ms=response_time_ms,
                            error=f"{len(schema_errors)} schema warnings",
                        )

                # Special validations for static mode
                if self.mode == "static":
                    # Validate agent_id matches
                    if "agent_id" in data and data["agent_id"] != self.agent_id:
                        self.result.add_error(
                            ValidationError(
                                endpoint=path,
                                type="identity_mismatch",
                                message=f"agent_id mismatch: expected '{self.agent_id}', got '{data['agent_id']}'",
                            )
                        )
                        return EndpointCheckResult(
                            endpoint=path,
                            method=method,
                            status="failed",
                            response_time_ms=response_time_ms,
                            error="Identity mismatch",
                        )

                    # Validate health status for /health endpoint
                    if path == "/health" and data.get("status") != "healthy":
                        self.result.add_warning(
                            ValidationWarning(
                                endpoint=path,
                                type="unhealthy_status",
                                message=f"Agent status is '{data.get('status')}', not 'healthy'",
                            )
                        )

                    # Validate capabilities for /health/detailed
                    if path == "/health/detailed" and "capabilities" in data:
                        reported_caps = set(data["capabilities"])
                        declared_caps = set(self.declared_capabilities)
                        if not reported_caps.issubset(
                            declared_caps
                        ) and not declared_caps.issubset(reported_caps):
                            self.result.add_warning(
                                ValidationWarning(
                                    endpoint=path,
                                    type="capability_mismatch",
                                    message=f"Capabilities mismatch: reported={list(reported_caps)}, declared={list(declared_caps)}",
                                )
                            )

                # Success
                return EndpointCheckResult(
                    endpoint=path,
                    method=method,
                    status="passed",
                    response_time_ms=response_time_ms,
                )

        except httpx.TimeoutException:
            error_msg = f"Endpoint timed out after {endpoint_def.timeout} seconds"
            if endpoint_def.required:
                self.result.add_error(
                    ValidationError(endpoint=path, type="timeout", message=error_msg)
                )
                return EndpointCheckResult(
                    endpoint=path, method=method, status="failed", error="Timeout"
                )
            else:
                self.result.add_warning(
                    ValidationWarning(
                        endpoint=path,
                        type="timeout",
                        message=f"{error_msg} (non-fatal)",
                    )
                )
                return EndpointCheckResult(
                    endpoint=path, method=method, status="warning", error="Timeout"
                )

        except Exception as e:
            error_msg = f"Failed to connect: {str(e)}"
            if endpoint_def.required:
                self.result.add_error(
                    ValidationError(
                        endpoint=path, type="connection_error", message=error_msg
                    )
                )
                return EndpointCheckResult(
                    endpoint=path, method=method, status="failed", error=str(e)
                )
            else:
                self.result.add_warning(
                    ValidationWarning(
                        endpoint=path,
                        type="connection_error",
                        message=f"{error_msg} (non-fatal)",
                    )
                )
                return EndpointCheckResult(
                    endpoint=path, method=method, status="warning", error=str(e)
                )


# ========== Main Validation Function ==========


async def validate_agent_endpoints(
    agent_id: str,
    agent_endpoint: str,
    declared_capabilities: List[str],
    communication_mode: str = "remote",
    mode: Optional[str] = None,
) -> EndpointValidationResult:
    """
    Validate agent endpoints against ARCP contract specifications.

    Supports two validation modes:
    - STATIC: Uses 14 predefined endpoint contracts (v1.0.0 standard)
    - DYNAMIC: Uses admin-configured custom endpoints from YAML file

    The mode is determined by:
    1. Explicit `mode` parameter (if provided)
    2. ARCP_TPR_ENDPOINT_VALIDATION_MODE config setting
    3. Defaults to "static"

    Args:
        agent_id: Agent identifier
        agent_endpoint: Base URL for agent (e.g., "https://agent.example.com")
        declared_capabilities: Capabilities declared during registration
        communication_mode: Communication mode (remote/local/hybrid)
        mode: Override validation mode ("static" or "dynamic")

    Returns:
        EndpointValidationResult with validation status, errors, and warnings
    """
    validation_mode = mode or getattr(config, "ENDPOINT_VALIDATION_MODE", "static")
    mode_upper = validation_mode.upper()

    validator = EndpointValidator(
        agent_id, agent_endpoint, declared_capabilities, mode=validation_mode
    )

    logger.info(
        f"Starting {mode_upper} endpoint validation for agent {agent_id} at {agent_endpoint}"
    )

    # Run all validations in parallel
    results = await asyncio.gather(
        *[validator.validate_endpoint(ep) for ep in validator.endpoints],
        return_exceptions=True,
    )

    # Process results
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Validation exception for {agent_id}: {result}")
            validator.result.add_error(
                ValidationError(
                    endpoint=validator.endpoints[i].path,
                    type="validation_exception",
                    message=str(result),
                )
            )
        elif isinstance(result, EndpointCheckResult):
            validator.result.add_check(result)

    validator.result.complete()

    passed = len([c for c in validator.result.checks.values() if c.status == "passed"])
    logger.info(
        f"{mode_upper} validation for {agent_id} complete: "
        f"{passed}/{len(validator.endpoints)} passed, "
        f"{len(validator.result.errors)} errors, "
        f"{len(validator.result.warnings)} warnings "
        f"({validator.result.duration_ms()}ms)"
    )

    return validator.result
