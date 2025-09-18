"""Agent-related data models"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from pydantic import field_validator as validator

from ..core.config import config, is_config_loaded


class AgentTypeValidation:
    """Centralized agent type validation using configuration."""

    @staticmethod
    def get_allowed_types() -> List[str]:
        """Get allowed agent types from configuration."""
        if not is_config_loaded():
            # When used as a library, provide sensible defaults
            return ["security", "monitoring", "automation", "networking", "testing"]
        return config.get_allowed_agent_types()

    @staticmethod
    def is_valid_type(agent_type: str) -> bool:
        """Check if agent type is allowed."""
        if not is_config_loaded():
            # When used as a library, allow basic validation without strict enforcement
            return bool(
                agent_type and agent_type.strip() and len(agent_type.strip()) >= 2
            )
        return config.is_valid_agent_type(agent_type)

    @staticmethod
    def validate_agent_type(agent_type: str) -> str:
        """Validate and normalize agent type."""
        if not agent_type or not agent_type.strip():
            raise ValueError("agent_type cannot be empty")

        agent_type = agent_type.strip()

        # Length validation
        if len(agent_type) < 2:
            raise ValueError("agent_type must be at least 2 characters")
        if len(agent_type) > 50:
            raise ValueError("agent_type too long (max 50 characters)")

        # Format validation (alphanumeric, underscore, hyphen only)
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_type):
            raise ValueError(
                "agent_type contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )

        # Check against allowed types from configuration (only if config is loaded)
        if is_config_loaded() and not AgentTypeValidation.is_valid_type(agent_type):
            allowed_types = AgentTypeValidation.get_allowed_types()
            raise ValueError(
                f'agent_type "{agent_type}" is not allowed. Allowed types: {", ".join(allowed_types)}'
            )

        return agent_type


class RequiredConfigField(BaseModel):
    """Represents a required configuration field for an agent"""

    name: str = Field(..., description="Field name/identifier")
    label: str = Field(..., description="Display label for the field")
    type: str = Field(
        ...,
        description="Field type: text, select, multiselect, boolean, number, textarea, array",
    )
    description: Optional[str] = Field(None, description="Field description/help text")
    default_value: Optional[Union[str, int, bool, List[str]]] = Field(
        None, description="Default value"
    )
    options: Optional[List[str]] = Field(
        None, description="Options for select/multiselect types"
    )
    validation: Optional[str] = Field(None, description="Regex pattern for validation")
    placeholder: Optional[str] = Field(None, description="Placeholder text")

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        v = v.strip()
        if len(v) < 1:
            raise ValueError("name must be at least 1 character")
        if len(v) > 100:
            raise ValueError("name too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "name contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v

    @validator("label")
    def validate_label(cls, v):
        if not v or not v.strip():
            raise ValueError("label cannot be empty")
        v = v.strip()
        if len(v) < 1:
            raise ValueError("label must be at least 1 character")
        if len(v) > 200:
            raise ValueError("label too long (max 200 characters)")
        return v

    @validator("type")
    def validate_type(cls, v):
        if not v or not v.strip():
            raise ValueError("type cannot be empty")
        v = v.strip()
        allowed_types = {
            "text",
            "select",
            "multiselect",
            "boolean",
            "number",
            "textarea",
            "array",
        }
        if v not in allowed_types:
            raise ValueError(f'type must be one of: {", ".join(allowed_types)}')
        return v

    @validator("description")
    def validate_description(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 1000:
                raise ValueError("description too long (max 1000 characters)")
        return v

    @validator("options")
    def validate_options(cls, v):
        if v is not None:
            if len(v) > 50:
                raise ValueError("too many options (max 50)")
            validated_options = []
            for option in v:
                if not isinstance(option, str):
                    raise ValueError("option must be a string")
                option = option.strip()
                if option and len(option) <= 200:
                    validated_options.append(option)
            return validated_options if validated_options else None
        return v

    @validator("validation")
    def validate_validation_pattern(cls, v):
        if v is not None:
            v = v.strip()
            if v:
                try:
                    re.compile(v)
                except re.error as e:
                    raise ValueError(f"invalid regex pattern: {e}")
                if len(v) > 500:
                    raise ValueError("validation pattern too long (max 500 characters)")
        return v

    @validator("placeholder")
    def validate_placeholder(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 300:
                raise ValueError("placeholder too long (max 300 characters)")
        return v


class OptionalConfigField(BaseModel):
    """Represents an optional configuration field for an agent"""

    name: str = Field(..., description="Field name/identifier")
    label: str = Field(..., description="Display label for the field")
    type: str = Field(
        ...,
        description="Field type: text, select, multiselect, boolean, number, textarea, array",
    )
    description: Optional[str] = Field(None, description="Field description/help text")
    default_value: Optional[Union[str, int, bool, List[str]]] = Field(
        None, description="Default value"
    )
    options: Optional[List[str]] = Field(
        None, description="Options for select/multiselect types"
    )
    validation: Optional[str] = Field(None, description="Regex pattern for validation")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    category: Optional[str] = Field(
        None, description="Grouping category for UI organization"
    )

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        v = v.strip()
        if len(v) < 1:
            raise ValueError("name must be at least 1 character")
        if len(v) > 100:
            raise ValueError("name too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "name contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v

    @validator("label")
    def validate_label(cls, v):
        if not v or not v.strip():
            raise ValueError("label cannot be empty")
        v = v.strip()
        if len(v) < 1:
            raise ValueError("label must be at least 1 character")
        if len(v) > 200:
            raise ValueError("label too long (max 200 characters)")
        return v

    @validator("type")
    def validate_type(cls, v):
        if not v or not v.strip():
            raise ValueError("type cannot be empty")
        v = v.strip()
        allowed_types = {
            "text",
            "select",
            "multiselect",
            "boolean",
            "number",
            "textarea",
            "array",
        }
        if v not in allowed_types:
            raise ValueError(f'type must be one of: {", ".join(allowed_types)}')
        return v

    @validator("description")
    def validate_description(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 1000:
                raise ValueError("description too long (max 1000 characters)")
        return v

    @validator("options")
    def validate_options(cls, v):
        if v is not None:
            if len(v) > 50:
                raise ValueError("too many options (max 50)")
            validated_options = []
            for option in v:
                if not isinstance(option, str):
                    raise ValueError("option must be a string")
                option = option.strip()
                if option and len(option) <= 200:
                    validated_options.append(option)
            return validated_options if validated_options else None
        return v

    @validator("validation")
    def validate_validation_pattern(cls, v):
        if v is not None:
            v = v.strip()
            if v:
                try:
                    re.compile(v)
                except re.error as e:
                    raise ValueError(f"invalid regex pattern: {e}")
                if len(v) > 500:
                    raise ValueError("validation pattern too long (max 500 characters)")
        return v

    @validator("placeholder")
    def validate_placeholder(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 300:
                raise ValueError("placeholder too long (max 300 characters)")
        return v

    @validator("category")
    def validate_category(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 100:
                raise ValueError("category too long (max 100 characters)")
        return v


class AgentRequirements(BaseModel):
    """Agent requirements with required/optional field distinction"""

    system_requirements: Optional[List[str]] = Field(
        default_factory=list, description="System requirements"
    )
    permissions: Optional[List[str]] = Field(
        default_factory=list, description="Required permissions"
    )
    dependencies: Optional[List[str]] = Field(
        default_factory=list, description="Software dependencies"
    )
    minimum_system_version: Optional[str] = Field(
        None, description="Minimum system version"
    )
    minimum_memory_mb: Optional[int] = Field(None, description="Minimum memory in MB")
    minimum_disk_space_mb: Optional[int] = Field(
        None, description="Minimum disk space in MB"
    )
    requires_internet: bool = Field(
        default=True, description="Requires internet connection"
    )
    network_ports: Optional[List[str]] = Field(
        default_factory=list, description="Required network ports"
    )

    # Configuration fields
    required_fields: Optional[List[RequiredConfigField]] = Field(
        default_factory=list, description="Required configuration fields"
    )
    optional_fields: Optional[List[OptionalConfigField]] = Field(
        default_factory=list, description="Optional configuration fields"
    )
    user_configuration: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="User-provided configuration values"
    )
    schema_version: str = Field(
        default="1.0", description="Configuration schema version"
    )

    @validator("system_requirements")
    def validate_system_requirements(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError("too many system requirements (max 50)")
        validated_reqs = []
        for req in v or []:
            if isinstance(req, str):
                req = req.strip()
                if req and len(req) <= 200:
                    validated_reqs.append(req)
        return validated_reqs

    @validator("permissions")
    def validate_permissions(cls, v):
        if v is not None and len(v) > 30:
            raise ValueError("too many permissions (max 30)")
        validated_perms = []
        for perm in v or []:
            if isinstance(perm, str):
                perm = perm.strip()
                if perm and len(perm) <= 100:
                    validated_perms.append(perm)
        return validated_perms

    @validator("dependencies")
    def validate_dependencies(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("too many dependencies (max 100)")
        validated_deps = []
        for dep in v or []:
            if isinstance(dep, str):
                dep = dep.strip()
                if dep and len(dep) <= 200:
                    validated_deps.append(dep)
        return validated_deps

    @validator("minimum_system_version")
    def validate_minimum_system_version(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 50:
                raise ValueError("minimum_system_version too long (max 50 characters)")
            # Basic version pattern validation
            if not re.match(r"^[0-9]+(\.[0-9]+)*([a-zA-Z0-9\-+]*)?$", v):
                raise ValueError(
                    "minimum_system_version must be a valid version format"
                )
        return v

    @validator("minimum_memory_mb")
    def validate_minimum_memory_mb(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError("minimum_memory_mb must be positive")
            if v > 1024 * 1024:  # 1TB limit
                raise ValueError("minimum_memory_mb too large (max 1TB)")
        return v

    @validator("minimum_disk_space_mb")
    def validate_minimum_disk_space_mb(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError("minimum_disk_space_mb must be positive")
            if v > 10 * 1024 * 1024:  # 10TB limit
                raise ValueError("minimum_disk_space_mb too large (max 10TB)")
        return v

    @validator("network_ports")
    def validate_network_ports(cls, v):
        if v is not None and len(v) > 20:
            raise ValueError("too many network ports (max 20)")
        validated_ports = []
        for port in v or []:
            if isinstance(port, str):
                port = port.strip()
                if port:
                    # Validate port format (number or range)
                    if re.match(r"^\d+(-\d+)?$", port):
                        port_nums = port.split("-")
                        for p in port_nums:
                            port_num = int(p)
                            if port_num < 1 or port_num > 65535:
                                raise ValueError(
                                    f"invalid port number: {p} (must be 1-65535)"
                                )
                        validated_ports.append(port)
                    else:
                        raise ValueError(
                            f"invalid port format: {port} (use number or range like 8080 or 8000-8999)"
                        )
        return validated_ports

    @validator("required_fields")
    def validate_required_fields(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError("too many required fields (max 50)")
        return v

    @validator("optional_fields")
    def validate_optional_fields(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("too many optional fields (max 100)")
        return v

    @validator("user_configuration")
    def validate_user_configuration(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("too many configuration entries (max 100)")
        return v

    @validator("schema_version")
    def validate_schema_version(cls, v):
        if not v or not v.strip():
            raise ValueError("schema_version cannot be empty")
        v = v.strip()
        if not re.match(r"^\d+\.\d+$", v):
            raise ValueError("schema_version must follow format X.Y (e.g., 1.0)")
        return v


class AgentRegistration(BaseModel):
    """Universal agent registration model"""

    # REQUIRED fields
    name: str = Field(..., description="Name of the Agent")
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    endpoint: str = Field(..., description="Agent HTTP endpoint URL")
    context_brief: str = Field(
        ..., description="Description of agent's domain expertise"
    )
    capabilities: List[str] = Field(..., description="List of specific capabilities")
    owner: str = Field(..., description="Entity that owns this agent")
    public_key: str = Field(..., description="Public key for agent authentication")
    metadata: Dict[str, Any] = Field(
        ..., description="Additional agent metadata for enhanced search"
    )
    version: str = Field(..., description="Version of the agent")
    communication_mode: str = Field(
        ..., description="Communication mode: 'remote', 'local', or 'hybrid'"
    )

    # OPTIONAL fields
    features: Optional[List[str]] = Field(
        None, description="List of high-level agent features"
    )
    max_tokens: Optional[int] = Field(
        None, description="Maximum tokens the agent can process"
    )
    language_support: Optional[List[str]] = Field(
        None, description="Supported languages"
    )
    rate_limit: Optional[int] = Field(None, description="Max requests per minute")
    requirements: Optional[Union[AgentRequirements, Dict[str, Any], str]] = Field(
        None, description="Agent requirements schema"
    )
    policy_tags: Optional[List[str]] = Field(None, description="Policy tags")

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        if len(v) > 32:
            raise ValueError("name too long (max 32 characters)")
        return v

    @validator("agent_id")
    def validate_agent_id(cls, v):
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        v = v.strip()
        if len(v) < 3:
            raise ValueError("agent_id must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        # Validate agent_id format (alphanumeric, underscore, hyphen only - NO SPACES)
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed - no spaces)"
            )
        return v

    @validator("agent_type")
    def validate_agent_type(cls, v):
        return AgentTypeValidation.validate_agent_type(v)

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if not v or not v.strip():
            raise ValueError("endpoint cannot be empty")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                "endpoint must be a valid URL starting with http:// or https://"
            )
        if len(v) > 2048:
            raise ValueError("endpoint URL too long (max 2048 characters)")
        # Basic URL validation
        url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(url_pattern, v):
            raise ValueError("endpoint must be a valid URL")
        return v

    @validator("context_brief")
    def validate_context_brief(cls, v):
        if not v or not v.strip():
            raise ValueError("context_brief cannot be empty")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("context_brief must be at least 10 characters")
        if len(v) > 1000:
            raise ValueError("context_brief too long (max 1000 characters)")
        return v

    @validator("capabilities")
    def validate_capabilities(cls, v):
        if not v:
            raise ValueError(
                "capabilities cannot be empty - must specify at least one capability"
            )
        if len(v) > 50:
            raise ValueError("too many capabilities (max 50)")
        validated_caps = []
        for cap in v:
            if not isinstance(cap, str):
                raise ValueError("capability must be a string")
            cap = cap.strip()
            if not cap:
                continue
            if len(cap) < 2:
                raise ValueError("capability must be at least 2 characters")
            if len(cap) > 100:
                raise ValueError("capability too long (max 100 characters)")
            if not re.match(r"^[a-zA-Z0-9_\-\s]+$", cap):
                raise ValueError("capability contains invalid characters")
            validated_caps.append(cap)
        if not validated_caps:
            raise ValueError("must have at least one valid capability")
        return validated_caps

    @validator("owner")
    def validate_owner(cls, v):
        if not v or not v.strip():
            raise ValueError("owner cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("owner must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("owner too long (max 50 characters)")
        return v

    @validator("public_key")
    def validate_public_key(cls, v):
        if not v or not v.strip():
            raise ValueError("public_key cannot be empty")
        v = v.strip()
        if len(v) < 32:
            raise ValueError("public_key must be at least 32 characters")
        if len(v) > 1024:
            raise ValueError("public_key too long (max 1024 characters)")
        # Basic validation for common key formats (PEM, SSH, etc.)
        # Allow base64, hex, or PEM format keys
        if not re.match(r"^[a-zA-Z0-9+/=\-_\s\n\r]+$", v):
            raise ValueError("public_key contains invalid characters")
        return v

    @validator("metadata")
    def validate_metadata(cls, v):
        if not v:
            raise ValueError(
                "metadata cannot be empty - required for enhanced search capabilities"
            )
        if not isinstance(v, dict):
            raise ValueError("metadata must be a dictionary")
        if len(v) == 0:
            raise ValueError("metadata must contain at least one key-value pair")
        if len(v) > 50:
            raise ValueError("too many metadata fields (max 50)")

        # Validate metadata keys and values
        for key, value in v.items():
            if not isinstance(key, str):
                raise ValueError("metadata keys must be strings")
            if len(key) > 100:
                raise ValueError(f"metadata key too long: {key} (max 100 characters)")
            if not isinstance(value, (str, int, float, bool, list)):
                raise ValueError(
                    f"metadata value for {key} must be string, number, boolean, or list"
                )
            if isinstance(value, str) and len(value) > 1000:
                raise ValueError(
                    f"metadata value for {key} too long (max 1000 characters)"
                )
        return v

    @validator("version")
    def validate_version(cls, v):
        if not v or not v.strip():
            raise ValueError("version cannot be empty")
        v = v.strip()
        # Basic semantic version validation
        if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$", v):
            raise ValueError("version must follow semantic versioning (e.g., 1.0.0)")
        return v

    @validator("communication_mode")
    def validate_communication_mode(cls, v):
        allowed = {"remote", "local", "hybrid"}
        v = v.strip().lower()
        if v not in allowed:
            raise ValueError(
                f"Invalid communication_mode '{v}'. Must be one of: {', '.join(allowed)}"
            )
        return v

    @validator("features")
    def validate_features(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("too many features (max 100)")
        validated_features = []
        for feature in v or []:
            if not isinstance(feature, str):
                raise ValueError("feature must be a string")
            feature = feature.strip()
            if feature and len(feature) <= 100:
                validated_features.append(feature)
        return validated_features

    @validator("max_tokens")
    def validate_max_tokens(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError("max_tokens must be positive")
            if v > 1000000:
                raise ValueError("max_tokens too large (max 1,000,000)")
        return v

    @validator("language_support")
    def validate_language_support(cls, v):
        if v is None:
            return None  # Allow None for optional field
        if len(v) > 20:
            raise ValueError("too many languages (max 20)")
        validated_langs = []
        for lang in v:
            if isinstance(lang, str) and len(lang) >= 2 and len(lang) <= 5:
                validated_langs.append(lang.lower())
        return validated_langs if validated_langs else None

    @validator("rate_limit")
    def validate_rate_limit(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError("rate_limit must be positive")
            if v > 10000:
                raise ValueError("rate_limit too large (max 10,000 requests/minute)")
        return v

    @validator("requirements")
    def validate_requirements(cls, v):
        if v is None:
            return None

        # If already an AgentRequirements object, return as-is
        if isinstance(v, AgentRequirements):
            return v

        # Convert dict to AgentRequirements
        if isinstance(v, dict):
            if len(v) > 100:
                raise ValueError("too many requirement fields (max 100)")
            try:
                return AgentRequirements(**v)
            except Exception as e:
                raise ValueError(
                    f"Failed to convert requirements dict to AgentRequirements: {e}"
                )

        # Convert JSON string to AgentRequirements
        if isinstance(v, str):
            # Handle empty or whitespace-only strings
            if not v.strip():
                return None
            try:
                requirements_dict = json.loads(v)
                return AgentRequirements(**requirements_dict)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                raise ValueError(f"Failed to parse requirements string as JSON: {e}")

        # Invalid type
        raise ValueError(
            f"requirements must be None, dict, JSON string, or AgentRequirements object, got {type(v)}"
        )
        return v

    @validator("policy_tags")
    def validate_policy_tags(cls, v):
        if v is not None and len(v) > 20:
            raise ValueError("too many policy tags (max 20)")
        validated_tags = []
        for tag in v or []:
            if isinstance(tag, str):
                tag = tag.strip()
                if tag and len(tag) <= 50:
                    validated_tags.append(tag)
        return validated_tags


class RegistrationResponse(BaseModel):
    """Response model for agent registration"""

    status: str = Field(..., description="Registration status")
    message: str = Field(..., description="Human-readable message")
    agent_id: str = Field(..., description="Registered agent ID")
    access_token: str = Field(..., description="JWT access token for the agent")

    @validator("status")
    def validate_status(cls, v):
        if not v or not v.strip():
            raise ValueError("status cannot be empty")
        v = v.strip()
        allowed_statuses = {"success", "error", "warning"}
        if v not in allowed_statuses:
            raise ValueError(f'status must be one of: {", ".join(allowed_statuses)}')
        return v

    @validator("message")
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        v = v.strip()
        if len(v) > 500:
            raise ValueError("message too long (max 500 characters)")
        return v


class AgentMetrics(BaseModel):
    """Agent performance metrics with validation"""

    agent_id: str
    success_rate: float = 0.0
    avg_response_time: float = 0.0
    total_requests: int = 0
    last_active: datetime = Field(default_factory=datetime.now)
    reputation_score: float = 0.0
    requests_processed: int = 0
    average_response_time: float = 0.0
    error_rate: float = 0.0

    @validator("agent_id")
    def validate_agent_id(cls, v):
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        v = v.strip()
        if len(v) < 3:
            raise ValueError("agent_id must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed - no spaces)"
            )
        return v

    @validator("success_rate")
    def validate_success_rate(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError("success_rate must be between 0.0 and 1.0")
        return v

    @validator("avg_response_time")
    def validate_avg_response_time(cls, v):
        if v < 0.0:
            raise ValueError("avg_response_time must be non-negative")
        if v > 3600.0:  # Max 1 hour response time
            raise ValueError("avg_response_time too large (max 3600 seconds)")
        return v

    @validator("total_requests")
    def validate_total_requests(cls, v):
        if v < 0:
            raise ValueError("total_requests must be non-negative")
        return v

    @validator("reputation_score")
    def validate_reputation_score(cls, v):
        if v < 0.0 or v > 10.0:
            raise ValueError("reputation_score must be between 0.0 and 10.0")
        return v

    @validator("requests_processed")
    def validate_requests_processed(cls, v):
        if v < 0:
            raise ValueError("requests_processed must be non-negative")
        return v

    @validator("average_response_time")
    def validate_average_response_time(cls, v):
        if v < 0.0:
            raise ValueError("average_response_time must be non-negative")
        if v > 3600.0:  # Max 1 hour response time
            raise ValueError("average_response_time too large (max 3600 seconds)")
        return v

    @validator("error_rate")
    def validate_error_rate(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError("error_rate must be between 0.0 and 1.0")
        return v


class AgentInfo(BaseModel):
    """Agent information"""

    # Core fields from AgentRegistration
    agent_id: str
    name: str
    agent_type: str
    endpoint: str
    capabilities: List[str]
    context_brief: str
    version: str
    owner: str
    public_key: str
    metadata: Dict[str, Any]
    communication_mode: str

    # Optional fields from AgentRegistration
    features: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    language_support: Optional[List[str]] = None
    rate_limit: Optional[int] = None
    requirements: Optional[Union[AgentRequirements, Dict[str, Any], str]] = None
    policy_tags: Optional[List[str]] = None

    # System/operational fields
    status: str  # "alive", "dead"
    last_seen: datetime
    registered_at: datetime
    similarity: Optional[float] = None  # For search results
    metrics: Optional[AgentMetrics] = None

    @validator("agent_id")
    def validate_agent_id(cls, v):
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        v = v.strip()
        if len(v) < 3:
            raise ValueError("agent_id must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "agent_id contains invalid characters (only alphanumeric, underscore, hyphen allowed - no spaces)"
            )
        return v

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        if len(v) > 32:
            raise ValueError("name too long (max 32 characters)")
        return v

    @validator("agent_type")
    def validate_agent_type(cls, v):
        return AgentTypeValidation.validate_agent_type(v)

    @validator("endpoint")
    def validate_endpoint(cls, v):
        if not v or not v.strip():
            raise ValueError("endpoint cannot be empty")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                "endpoint must be a valid URL starting with http:// or https://"
            )
        if len(v) > 2048:
            raise ValueError("endpoint URL too long (max 2048 characters)")
        url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(url_pattern, v):
            raise ValueError("endpoint must be a valid URL")
        return v

    @validator("capabilities")
    def validate_capabilities(cls, v):
        if not v:
            raise ValueError(
                "capabilities cannot be empty - must specify at least one capability"
            )
        if len(v) > 50:
            raise ValueError("too many capabilities (max 50)")
        validated_caps = []
        for cap in v:
            if not isinstance(cap, str):
                raise ValueError("capability must be a string")
            cap = cap.strip()
            if not cap:
                continue
            if len(cap) < 2:
                raise ValueError("capability must be at least 2 characters")
            if len(cap) > 100:
                raise ValueError("capability too long (max 100 characters)")
            if not re.match(r"^[a-zA-Z0-9_\-\s]+$", cap):
                raise ValueError("capability contains invalid characters")
            validated_caps.append(cap)
        if not validated_caps:
            raise ValueError("must have at least one valid capability")
        return validated_caps

    @validator("context_brief")
    def validate_context_brief(cls, v):
        if not v or not v.strip():
            raise ValueError("context_brief cannot be empty")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("context_brief must be at least 10 characters")
        if len(v) > 1000:
            raise ValueError("context_brief too long (max 1000 characters)")
        return v

    @validator("version")
    def validate_version(cls, v):
        if not v or not v.strip():
            raise ValueError("version cannot be empty")
        v = v.strip()
        if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$", v):
            raise ValueError("version must follow semantic versioning (e.g., 1.0.0)")
        return v

    @validator("owner")
    def validate_owner(cls, v):
        if not v or not v.strip():
            raise ValueError("owner cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("owner must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("owner too long (max 50 characters)")
        return v

    @validator("public_key")
    def validate_public_key(cls, v):
        if not v or not v.strip():
            raise ValueError("public_key cannot be empty")
        v = v.strip()
        if len(v) < 32:
            raise ValueError("public_key must be at least 32 characters")
        if len(v) > 1024:
            raise ValueError("public_key too long (max 1024 characters)")
        if not re.match(r"^[a-zA-Z0-9+/=\-_\s\n\r]+$", v):
            raise ValueError("public_key contains invalid characters")
        return v

    @validator("metadata")
    def validate_metadata(cls, v):
        if not v:
            raise ValueError(
                "metadata cannot be empty - required for enhanced search capabilities"
            )
        if not isinstance(v, dict):
            raise ValueError("metadata must be a dictionary")
        if len(v) == 0:
            raise ValueError("metadata must contain at least one key-value pair")
        if len(v) > 50:
            raise ValueError("too many metadata fields (max 50)")
        for key, value in v.items():
            if not isinstance(key, str):
                raise ValueError("metadata keys must be strings")
            if len(key) > 100:
                raise ValueError(f"metadata key too long: {key} (max 100 characters)")
            if not isinstance(value, (str, int, float, bool, list)):
                raise ValueError(
                    f"metadata value for {key} must be string, number, boolean, or list"
                )
            if isinstance(value, str) and len(value) > 1000:
                raise ValueError(
                    f"metadata value for {key} too long (max 1000 characters)"
                )
        return v

    @validator("status")
    def validate_status(cls, v):
        if v not in ["alive", "dead"]:
            raise ValueError('status must be either "alive" or "dead"')
        return v

    @validator("requirements")
    def validate_requirements(cls, v):
        if v is None:
            return None

        # If already an AgentRequirements object, return as-is
        if isinstance(v, AgentRequirements):
            return v

        # Convert dict to AgentRequirements
        if isinstance(v, dict):
            if len(v) > 100:
                raise ValueError("too many requirement fields (max 100)")
            try:
                return AgentRequirements(**v)
            except Exception as e:
                raise ValueError(
                    f"Failed to convert requirements dict to AgentRequirements: {e}"
                )

        # Convert JSON string to AgentRequirements
        if isinstance(v, str):
            # Handle empty or whitespace-only strings
            if not v.strip():
                return None
            try:
                requirements_dict = json.loads(v)
                return AgentRequirements(**requirements_dict)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                raise ValueError(f"Failed to parse requirements string as JSON: {e}")

        # Invalid type
        raise ValueError(
            f"requirements must be None, dict, JSON string, or AgentRequirements object, got {type(v)}"
        )

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class HeartbeatResponse(BaseModel):
    agent_id: str
    status: str
    last_seen: datetime
    metrics: Optional[AgentMetrics] = None

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


class TokenData(BaseModel):
    """JWT token data"""

    agent_id: Optional[str] = None
    role: Optional[str] = None
    scopes: Optional[List[str]] = None


class SearchRequest(BaseModel):
    """Vector search request"""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(
        default_factory=lambda: int(getattr(config, "VECTOR_SEARCH_TOP_K", 3)),
        description="Number of results to return",
    )
    min_similarity: float = Field(
        default_factory=lambda: float(
            getattr(config, "VECTOR_SEARCH_MIN_SIMILARITY", 0.5)
        ),
        description="Minimum similarity threshold",
    )
    capabilities: Optional[List[str]] = Field(
        None, description="Filter by capabilities"
    )
    weighted: bool = Field(
        default=False, description="Weight results by reputation/metrics"
    )
    agent_type: Optional[str] = Field(None, description="Filter by agent type")

    @validator("query")
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError("query cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("query must be at least 2 characters")
        if len(v) > 1000:
            raise ValueError("query too long (max 1000 characters)")
        return v

    @validator("top_k")
    def validate_top_k(cls, v):
        if v <= 0:
            raise ValueError("top_k must be a positive integer")
        if v > 100:
            raise ValueError("top_k too large (max 100 results)")
        return v

    @validator("min_similarity")
    def validate_min_similarity(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError("min_similarity must be between 0.0 and 1.0")
        return v

    @validator("capabilities")
    def validate_capabilities(cls, v):
        if v is not None:
            if len(v) == 0:
                raise ValueError(
                    "capabilities filter cannot be empty - either provide capabilities or set to None"
                )
            if len(v) > 20:
                raise ValueError("too many capability filters (max 20)")
            validated_caps = []
            for cap in v:
                if not isinstance(cap, str):
                    raise ValueError("capability filter must be a string")
                cap = cap.strip()
                if not cap:
                    continue
                if len(cap) < 2:
                    raise ValueError("capability filter must be at least 2 characters")
                if len(cap) > 100:
                    raise ValueError("capability filter too long (max 100 characters)")
                if not re.match(r"^[a-zA-Z0-9_\-\s]+$", cap):
                    raise ValueError("capability filter contains invalid characters")
                validated_caps.append(cap)
            if not validated_caps:
                raise ValueError("must have at least one valid capability filter")
            return validated_caps
        return v

    @validator("weighted")
    def validate_weighted(cls, v):
        if not isinstance(v, bool):
            raise ValueError("weighted must be a boolean value (True or False)")
        return v

    @validator("agent_type")
    def validate_agent_type(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError(
                    "agent_type filter cannot be empty - either provide valid type or set to None"
                )
            v = v.strip()
            if len(v) < 2:
                raise ValueError("agent_type filter must be at least 2 characters")
            if len(v) > 50:
                raise ValueError("agent_type filter too long (max 50 characters)")
            if not re.match(r"^[a-zA-Z0-9_-]+$", v):
                raise ValueError(
                    "agent_type filter contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
                )
            return v
        return v


class SearchResponse(BaseModel):
    """Search response format"""

    id: str
    name: str
    url: str
    capabilities: List[str]
    version: str
    owner: Optional[str]
    similarity: Optional[float] = None
    metrics: Optional[AgentMetrics] = None

    @validator("id")
    def validate_id(cls, v):
        if not v or not v.strip():
            raise ValueError("id cannot be empty")
        v = v.strip()
        if len(v) < 3:
            raise ValueError("id must be at least 3 characters")
        if len(v) > 100:
            raise ValueError("id too long (max 100 characters)")
        return v

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        if len(v) > 32:
            raise ValueError("name too long (max 32 characters)")
        return v

    @validator("url")
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError("url cannot be empty")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                "url must be a valid URL starting with http:// or https://"
            )
        if len(v) > 2048:
            raise ValueError("url too long (max 2048 characters)")
        url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(url_pattern, v):
            raise ValueError("url must be a valid URL")
        return v

    @validator("capabilities")
    def validate_capabilities(cls, v):
        if not v:
            raise ValueError(
                "capabilities cannot be empty - must specify at least one capability"
            )
        if len(v) > 50:
            raise ValueError("too many capabilities (max 50)")
        validated_caps = []
        for cap in v:
            if not isinstance(cap, str):
                raise ValueError("capability must be a string")
            cap = cap.strip()
            if not cap:
                continue
            if len(cap) < 2:
                raise ValueError("capability must be at least 2 characters")
            if len(cap) > 100:
                raise ValueError("capability too long (max 100 characters)")
            if not re.match(r"^[a-zA-Z0-9_\-\s]+$", cap):
                raise ValueError("capability contains invalid characters")
            validated_caps.append(cap)
        if not validated_caps:
            raise ValueError("must have at least one valid capability")
        return validated_caps

    @validator("version")
    def validate_version(cls, v):
        if not v or not v.strip():
            raise ValueError("version cannot be empty")
        v = v.strip()
        if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$", v):
            raise ValueError("version must follow semantic versioning (e.g., 1.0.0)")
        return v

    @validator("similarity")
    def validate_similarity(cls, v):
        if v is not None:
            if v < 0.0 or v > 1.0:
                raise ValueError("similarity must be between 0.0 and 1.0")
        return v


class AgentConnectionRequest(BaseModel):
    """Request model for user-agent connections in public API."""

    user_id: str
    user_endpoint: str
    display_name: Optional[str] = "Anonymous User"
    additional_info: Optional[Dict[str, Any]] = {}

    @validator("user_id")
    def validate_user_id(cls, v):
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise ValueError("user_id must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("user_id too long (max 100 characters)")
        # Allow alphanumeric, underscore, hyphen, and at symbol for user IDs
        if not re.match(r"^[a-zA-Z0-9_@.-]+$", v):
            raise ValueError(
                "user_id contains invalid characters (only alphanumeric, underscore, hyphen, at symbol, dot allowed)"
            )
        return v

    @validator("user_endpoint")
    def validate_user_endpoint(cls, v):
        if not v or not v.strip():
            raise ValueError("user_endpoint cannot be empty")
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                "user_endpoint must be a valid URL starting with http:// or https://"
            )
        if len(v) > 2048:
            raise ValueError("user_endpoint URL too long (max 2048 characters)")
        # Basic URL validation
        url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(url_pattern, v):
            raise ValueError("user_endpoint must be a valid URL")
        return v

    @validator("display_name")
    def validate_display_name(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return "Anonymous User"  # Reset to default if empty
            if len(v) > 200:
                raise ValueError("display_name too long (max 200 characters)")
            # Allow most characters for display names but prevent control characters
            if not re.match(r"^[^\x00-\x1f\x7f]+$", v):
                raise ValueError("display_name contains invalid control characters")
        return v

    @validator("additional_info")
    def validate_additional_info(cls, v):
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError("additional_info must be a dictionary")
            if len(v) > 50:
                raise ValueError("too many additional_info fields (max 50)")
            # Validate keys and values
            for key, value in v.items():
                if not isinstance(key, str):
                    raise ValueError("additional_info keys must be strings")
                if len(key) > 100:
                    raise ValueError(
                        f"additional_info key too long: {key} (max 100 characters)"
                    )
                if not isinstance(value, (str, int, float, bool, list, dict)):
                    raise ValueError(
                        f"additional_info value for {key} must be string, number, boolean, list, or dict"
                    )
                if isinstance(value, str) and len(value) > 1000:
                    raise ValueError(
                        f"additional_info value for {key} too long (max 1000 characters)"
                    )
        return v


class AgentConnectionResponse(BaseModel):
    """Response model for user-agent connection requests."""

    status: str
    message: str
    next_steps: str
    agent_info: Dict[str, Any]
    request_id: str
    timestamp: str

    @validator("status")
    def validate_status(cls, v):
        if not v or not v.strip():
            raise ValueError("status cannot be empty")
        v = v.strip()
        allowed_statuses = {
            "connection_requested",
            "connection_accepted",
            "connection_rejected",
            "connection_pending",
            "connection_timeout",
            "connection_error",
        }
        if v not in allowed_statuses:
            raise ValueError(f"status must be one of: {', '.join(allowed_statuses)}")
        return v

    @validator("message")
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        v = v.strip()
        if len(v) < 5:
            raise ValueError("message must be at least 5 characters")
        if len(v) > 500:
            raise ValueError("message too long (max 500 characters)")
        return v

    @validator("next_steps")
    def validate_next_steps(cls, v):
        if not v or not v.strip():
            raise ValueError("next_steps cannot be empty")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("next_steps must be at least 10 characters")
        if len(v) > 1000:
            raise ValueError("next_steps too long (max 1000 characters)")
        return v

    @validator("agent_info")
    def validate_agent_info(cls, v):
        if not v:
            raise ValueError("agent_info cannot be empty")
        if not isinstance(v, dict):
            raise ValueError("agent_info must be a dictionary")
        if len(v) == 0:
            raise ValueError("agent_info must contain at least one field")
        if len(v) > 50:
            raise ValueError("too many agent_info fields (max 50)")

        # Validate required fields in agent_info
        required_fields = ["name"]
        for field in required_fields:
            if field not in v:
                raise ValueError(f"agent_info must contain required field: {field}")

        # Validate keys and values
        for key, value in v.items():
            if not isinstance(key, str):
                raise ValueError("agent_info keys must be strings")
            if len(key) > 100:
                raise ValueError(f"agent_info key too long: {key} (max 100 characters)")
            if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                raise ValueError(
                    f"agent_info value for {key} must be string, number, boolean, list, dict, or null"
                )
            if isinstance(value, str) and len(value) > 2000:
                raise ValueError(
                    f"agent_info value for {key} too long (max 2000 characters)"
                )
        return v

    @validator("request_id")
    def validate_request_id(cls, v):
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty")
        v = v.strip()
        if len(v) < 5:
            raise ValueError("request_id must be at least 5 characters")
        if len(v) > 100:
            raise ValueError("request_id too long (max 100 characters)")
        # Allow alphanumeric, underscore, hyphen for request IDs
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "request_id contains invalid characters (only alphanumeric, underscore, hyphen allowed)"
            )
        return v

    @validator("timestamp")
    def validate_timestamp(cls, v):
        if not v or not v.strip():
            raise ValueError("timestamp cannot be empty")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("timestamp must be at least 10 characters")
        if len(v) > 50:
            raise ValueError("timestamp too long (max 50 characters)")
        # Basic ISO 8601 timestamp validation
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", v):
            raise ValueError(
                "timestamp must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"
            )
        return v
