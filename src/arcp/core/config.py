"""
Centralized configuration management for ARCP.

This module manages all configuration values, environment variables,
and default settings for the ARCP service.
"""

import datetime
import logging
import os
import platform
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv not available, continue without it
    pass
from pathlib import Path
from typing import Any, Dict, List, Optional


class ARCPConfig:
    """Centralized configuration for ARCP."""

    def __init__(self):
        """Initialize configuration by reading environment variables with defaults."""
        self._load_config()
        self._loaded = True
        self._load_error = None

    def _load_config(self):
        """Load configuration from environment variables."""
        # Service Configuration
        self.SERVICE_NAME: str = "ARCP"
        self.SERVICE_VERSION: str = "2.0.0"
        self.SERVICE_DESCRIPTION: str = "Agent Registry & Control Protocol"

        # Server Configuration
        self.HOST: str = os.getenv("ARCP_HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("ARCP_PORT", "8001"))
        self.DEBUG: bool = os.getenv("ARCP_DEBUG", "false").lower() == "true"
        self.LOGS_DIR: str = os.getenv("ARCP_LOGS_DIR", "/app/logs")
        self.ENVIRONMENT: str = os.getenv(
            "ENVIRONMENT", "development"
        )  # development, testing, production [defaults to development for library usage]

        # Security Configuration
        self.ALLOWED_ORIGINS: Optional[str] = os.getenv(
            "ALLOWED_ORIGINS"
        )  # Comma-separated CORS origins [OPTIONAL]
        self.TRUSTED_HOSTS: Optional[str] = os.getenv(
            "TRUSTED_HOSTS"
        )  # Comma-separated trusted hosts [OPTIONAL]
        # CSP connect-src controls for allowing outbound HTTP/HTTPS from browser
        # Defaults: allow both in development, allow only HTTPS in production
        env = os.getenv("ENVIRONMENT", "development").lower()
        default_allow_http = env == "development"  # permissive in dev
        default_allow_https = True
        self.CSP_ALLOW_CONNECT_HTTP: bool = (
            os.getenv("CSP_ALLOW_CONNECT_HTTP", str(default_allow_http)).lower()
            == "true"
        )
        self.CSP_ALLOW_CONNECT_HTTPS: bool = (
            os.getenv("CSP_ALLOW_CONNECT_HTTPS", str(default_allow_https)).lower()
            == "true"
        )

        # Rate Limiting Configuration
        self.RATE_LIMIT_RPM: int = int(
            os.getenv("RATE_LIMIT_RPM", "100")
        )  # Requests per minute
        self.RATE_LIMIT_BURST: int = int(
            os.getenv("RATE_LIMIT_BURST", "20")
        )  # Burst size
        self.SESSION_TIMEOUT: int = int(
            os.getenv("SESSION_TIMEOUT", "30")
        )  # Session timeout in minutes
        self.MAX_SESSIONS: int = int(
            os.getenv("MAX_SESSIONS", "5")
        )  # Maximum concurrent sessions per user

        # Request Security Configuration
        self.MAX_JSON_SIZE: int = int(
            os.getenv("MAX_JSON_SIZE", "1048576")
        )  # 1MB max JSON payload
        self.MAX_QUERY_PARAMS: int = int(
            os.getenv("MAX_QUERY_PARAMS", "50")
        )  # Maximum query parameters
        self.MAX_HEADER_SIZE: int = int(
            os.getenv("MAX_HEADER_SIZE", "8192")
        )  # 8KB max header size

        # Security Monitoring Configuration
        self.SECURITY_LOGGING: bool = (
            os.getenv("SECURITY_LOGGING", "true").lower() == "true"
        )

        # Default deny mode: when true, requests are denied unless the client IP
        # matches one of ALLOWED_IP_RANGES. When false (default), requests are
        # allowed unless the client IP is in BLOCKED_IPS.
        self.IP_DEFAULT_DENY: bool = (
            os.getenv("IP_DEFAULT_DENY", "false").lower() == "true"
        )
        # IP Restrictions Configuration (optional)
        self.BLOCKED_IPS: Optional[str] = os.getenv(
            "BLOCKED_IPS"
        )  # Comma-separated list of blocked IPs [OPTIONAL]
        self.ALLOWED_IP_RANGES: Optional[str] = os.getenv(
            "ALLOWED_IP_RANGES"
        )  # Comma-separated list of allowed IP ranges [OPTIONAL]
        # Parsed lists for efficient checks
        self.BLOCKED_IPS_LIST: List[str] = [
            ip.strip()
            for ip in (self.BLOCKED_IPS.split(",") if self.BLOCKED_IPS else [])
            if ip.strip()
        ]
        self.ALLOWED_IP_RANGES_LIST: List[str] = [
            rng.strip()
            for rng in (
                self.ALLOWED_IP_RANGES.split(",") if self.ALLOWED_IP_RANGES else []
            )
            if rng.strip()
        ]

        # Content Filtering Configuration
        self.CONTENT_FILTERING: bool = (
            os.getenv("CONTENT_FILTERING", "true").lower() == "true"
        )

        # Data Storage Configuration
        self.DATA_DIRECTORY: str = os.getenv("ARCP_DATA_DIR", "/app/data")
        self.REDIS_DATA_DIR: str = os.getenv("REDIS_DATA_DIR", "/data")
        self.PROMETHEUS_DATA_DIR: str = os.getenv("PROMETHEUS_DATA_DIR", "/data")
        self.GRAFANA_DATA_DIR: str = os.getenv("GRAFANA_DATA_DIR", "/var/lib/grafana")

        # State Agent Configuration
        # If STATE_FILE is relative, place it under DATA_DIRECTORY
        state_file_env = os.getenv("STATE_FILE")
        if not state_file_env or state_file_env.strip() == "":
            self.STATE_FILE: str = os.path.join(
                self.DATA_DIRECTORY, "registry_state.json"
            )
        else:
            self.STATE_FILE: str = (
                state_file_env
                if os.path.isabs(state_file_env)
                else os.path.join(self.DATA_DIRECTORY, state_file_env)
            )

        # Timezone Configuration [REQUIRED]
        # Accepts TZ or TIMEZONE environment variables
        # Examples: "UTC", "Asia/Riyadh", "America/New_York", "Europe/London", "Asia/Tokyo"
        self.TIMEZONE: str = os.getenv("TZ", os.getenv("TIMEZONE", "UTC"))

        # Agent Types Configuration
        # Allowed agent types that can register
        agent_types_env = os.getenv("ALLOWED_AGENT_TYPES")

        # Parse and validate agent types
        if agent_types_env is None:
            # When used as a library, provide sensible defaults instead of failing
            # This allows developers to use ARCP client without server configuration
            agent_types_env = "security,monitoring,automation,networking,testing"

        agent_types_list = [
            agent_type.strip()
            for agent_type in agent_types_env.split(",")
            if agent_type.strip()
        ]

        # Validation: at least 1 type, max 100 types
        if len(agent_types_list) < 1:
            raise ValueError(
                "ALLOWED_AGENT_TYPES must contain at least one valid agent type"
            )
        if len(agent_types_list) > 100:
            raise ValueError(
                "ALLOWED_AGENT_TYPES cannot contain more than 100 agent types"
            )

        # Validate each agent type format
        for agent_type in agent_types_list:
            if len(agent_type) < 2:
                raise ValueError(
                    f"Agent type '{agent_type}' must be at least 2 characters"
                )
            if len(agent_type) > 50:
                raise ValueError(
                    f"Agent type '{agent_type}' cannot exceed 50 characters"
                )
            if not agent_type.replace("-", "").replace("_", "").isalnum():
                raise ValueError(
                    f"Agent type '{agent_type}' can only contain alphanumeric characters, hyphens, and underscores"
                )

        self.ALLOWED_AGENT_TYPES: List[str] = agent_types_list

        # Agent Configuration
        self.AGENT_HEARTBEAT_TIMEOUT: int = int(
            os.getenv("AGENT_HEARTBEAT_TIMEOUT", "60")
        )
        self.AGENT_CLEANUP_INTERVAL: int = int(
            os.getenv("AGENT_CLEANUP_INTERVAL", "60")
        )
        self.AGENT_REGISTRATION_TIMEOUT: int = int(
            os.getenv("AGENT_REGISTRATION_TIMEOUT", "30")
        )

        # Agent Registration Keys Configuration [OPTIONAL]
        # These are temporary test keys - in production.. agents get keys after real logic
        agent_keys_env: Optional[str] = os.getenv("AGENT_KEYS")
        self.AGENT_REGISTRATION_KEYS: Optional[List[str]] = (
            [key.strip() for key in agent_keys_env.split(",") if key.strip()]
            if agent_keys_env
            else None
        )

        # Authentication Configuration [REQUIRED for server, defaults for library usage]
        self.JWT_SECRET: Optional[str] = os.getenv("JWT_SECRET")
        self.JWT_ALGORITHM: Optional[str] = os.getenv("JWT_ALGORITHM")
        jwt_expire_env = os.getenv("JWT_EXPIRE_MINUTES")
        self.JWT_EXPIRE_MINUTES: Optional[int] = (
            int(jwt_expire_env) if jwt_expire_env else None
        )

        # Admin Authentication Configuration [REQUIRED for server, defaults for library usage]
        self.ADMIN_USERNAME: Optional[str] = os.getenv("ADMIN_USERNAME")
        self.ADMIN_PASSWORD: Optional[str] = os.getenv("ADMIN_PASSWORD")

        # Global WebSocket defaults (kept for backward compatibility)
        self.WEBSOCKET_INTERVAL: int = int(os.getenv("WEBSOCKET_INTERVAL", "30"))
        self.WEBSOCKET_TIMEOUT: int = int(os.getenv("WEBSOCKET_TIMEOUT", "30"))
        self.WEBSOCKET_PING_INTERVAL: int = int(
            os.getenv("WEBSOCKET_PING_INTERVAL", "30")
        )
        self.WEBSOCKET_MAX_CONNECTIONS: int = int(
            os.getenv("WEBSOCKET_MAX_CONNECTIONS", "100")
        )

        # Dashboard WebSocket Configuration
        self.DASHBOARD_WS_INTERVAL: int = int(os.getenv("DASHBOARD_WS_INTERVAL", "5"))
        self.DASHBOARD_WS_TIMEOUT: int = int(os.getenv("DASHBOARD_WS_TIMEOUT", "30"))
        self.DASHBOARD_WS_PING_INTERVAL: int = int(
            os.getenv("DASHBOARD_WS_PING_INTERVAL", "30")
        )
        self.DASHBOARD_WS_MAX_CONNECTIONS: int = int(
            os.getenv("DASHBOARD_WS_MAX_CONNECTIONS", "5")
        )

        # Agent WebSocket Configuration
        self.AGENT_WS_INTERVAL: int = int(os.getenv("AGENT_WS_INTERVAL", "5"))
        self.AGENT_WS_TIMEOUT: int = int(os.getenv("AGENT_WS_TIMEOUT", "30"))
        self.AGENT_WS_PING_INTERVAL: int = int(
            os.getenv("AGENT_WS_PING_INTERVAL", "30")
        )
        self.AGENT_WS_MAX_CONNECTIONS: int = int(
            os.getenv("AGENT_WS_MAX_CONNECTIONS", "100")
        )

        # Public WebSocket Configuration
        self.PUBLIC_WS_INTERVAL: int = int(os.getenv("PUBLIC_WS_INTERVAL", "30"))
        self.PUBLIC_WS_TIMEOUT: int = int(os.getenv("PUBLIC_WS_TIMEOUT", "30"))
        self.PUBLIC_WS_PING_INTERVAL: int = int(
            os.getenv("PUBLIC_WS_PING_INTERVAL", "30")
        )
        self.PUBLIC_WS_MAX_CONNECTIONS: int = int(
            os.getenv("PUBLIC_WS_MAX_CONNECTIONS", "100")
        )

        # Vector Search Configuration
        self.VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "10"))
        self.VECTOR_SEARCH_MIN_SIMILARITY: float = float(
            os.getenv("VECTOR_SEARCH_MIN_SIMILARITY", "0.5")
        )

        # Network Configuration
        # Network interface capacity for utilization calculation (Mbps)
        # Default to 1 Gbps (1000 Mbps), can be configured via environment variable
        # Common values: 10 (10 Mbps), 100 (100 Mbps), 1000 (1 Gbps), 10000 (10 Gbps)
        network_capacity_str = os.getenv("NETWORK_INTERFACE_CAPACITY_MBPS", "1000")
        try:
            self.NETWORK_INTERFACE_CAPACITY_MBPS: float = float(network_capacity_str)
        except (ValueError, TypeError):
            self.NETWORK_INTERFACE_CAPACITY_MBPS: float = 1000.0  # Default to 1 Gbps

        # Logging Configuration
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT: str = os.getenv(
            "LOG_FORMAT",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Dashboard Log Limits
        # Max number of recent dashboard logs kept in memory/Redis
        self.DASHBOARD_LOG_BUFFER_MAXLEN: int = int(
            os.getenv("DASHBOARD_LOG_BUFFER_MAXLEN", "10000")
        )
        # Max characters per single dashboard log message
        self.DASHBOARD_LOG_MESSAGE_MAXLEN: int = int(
            os.getenv("DASHBOARD_LOG_MESSAGE_MAXLEN", "2048")
        )

        # Azure OpenAI Configuration
        self.AZURE_API_KEY: Optional[str] = os.getenv("AZURE_API_KEY")
        self.AZURE_API_BASE: Optional[str] = os.getenv("AZURE_API_BASE")
        self.AZURE_API_VERSION: Optional[str] = os.getenv("AZURE_API_VERSION")
        self.AZURE_EMBEDDING_DEPLOYMENT: Optional[str] = os.getenv(
            "AZURE_EMBEDDING_DEPLOYMENT"
        )

        # Redis Configuration
        self.REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST")
        redis_port_str: Optional[str] = os.getenv("REDIS_PORT")
        self.REDIS_PORT: Optional[int] = int(redis_port_str) if redis_port_str else None
        self.REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
        redis_db_str: Optional[str] = os.getenv("REDIS_DB")
        self.REDIS_DB: Optional[int] = int(redis_db_str) if redis_db_str else None
        redis_health_check_str: Optional[str] = os.getenv("REDIS_HEALTH_CHECK_INTERVAL")
        self.REDIS_HEALTH_CHECK_INTERVAL: Optional[int] = (
            int(redis_health_check_str) if redis_health_check_str else None
        )
        self.REDIS_MAX_MEMORY: Optional[str] = os.getenv(
            "REDIS_MAX_MEMORY"
        )  # e.g., "256mb", "1gb"
        redis_exporter_port_str: Optional[str] = os.getenv("REDIS_EXPORTER_PORT")
        self.REDIS_EXPORTER_PORT: Optional[int] = (
            int(redis_exporter_port_str) if redis_exporter_port_str else None
        )

        # Prometheus Configuration
        self.PROMETHEUS_HOST: str = os.getenv("PROMETHEUS_HOST", "prometheus")
        self.PROMETHEUS_PORT: int = int(os.getenv("PROMETHEUS_PORT", "9090"))
        self.METRICS_SCRAPE_TOKEN: Optional[str] = os.getenv("METRICS_SCRAPE_TOKEN")

        # Grafana Configuration
        self.GRAFANA_HOST: str = os.getenv("GRAFANA_HOST", "grafana")
        self.GRAFANA_PORT: int = int(os.getenv("GRAFANA_PORT", "3000"))
        self.GRAFANA_PASSWORD: str = os.getenv("GRAFANA_PASSWORD", "admin")

        # OpenTelemetry Tracing Configuration
        self.TRACING_ENABLED: bool = (
            os.getenv("TRACING_ENABLED", "false").lower() == "true"
        )
        self.JAEGER_ENDPOINT: str = os.getenv(
            "JAEGER_ENDPOINT", "http://jaeger:14268/api/traces"
        )
        self.OTLP_ENDPOINT: str = os.getenv("OTLP_ENDPOINT", "http://jaeger:4317")
        self.TRACE_SERVICE_NAME: str = os.getenv("TRACE_SERVICE_NAME", "arcp")
        self.TRACE_SERVICE_VERSION: str = os.getenv(
            "TRACE_SERVICE_VERSION", self.SERVICE_VERSION
        )
        self.TRACE_ENVIRONMENT: str = os.getenv("TRACE_ENVIRONMENT", "development")
        self.TRACE_SAMPLE_RATE: float = float(os.getenv("TRACE_SAMPLE_RATE", "1.0"))
        self.JAEGER_UI_PORT: int = int(os.getenv("JAEGER_UI_PORT", "16686"))
        self.JAEGER_GRPC_PORT: int = int(os.getenv("JAEGER_GRPC_PORT", "14250"))
        self.JAEGER_THRIFT_PORT: int = int(os.getenv("JAEGER_THRIFT_PORT", "14268"))
        self.JAEGER_OTLP_GRPC_PORT: int = int(
            os.getenv("JAEGER_OTLP_GRPC_PORT", "4317")
        )
        self.JAEGER_OTLP_HTTP_PORT: int = int(
            os.getenv("JAEGER_OTLP_HTTP_PORT", "4318")
        )
        self.JAEGER_METRICS_PORT: int = int(os.getenv("JAEGER_METRICS_PORT", "14269"))

    def validate_required_config(self) -> List[str]:
        """
        Validate required configuration and return list of missing variables.

        Returns:
            List of missing required environment variables
        """
        missing = []

        # Check environment configuration [REQUIRED]
        env_from_env = os.getenv("ENVIRONMENT")
        if not env_from_env or env_from_env.strip() == "":
            missing.append("ENVIRONMENT (required) [development, testing, production]")
        elif str(self.ENVIRONMENT).lower() not in [
            "development",
            "production",
            "testing",
        ]:
            missing.append(
                "ENVIRONMENT (must be 'development', 'production', or 'testing')"
            )

        # Check timezone configuration [REQUIRED]
        tz_from_env = os.getenv("TZ") or os.getenv("TIMEZONE")
        if not tz_from_env or tz_from_env.strip() == "":
            missing.append(
                "TZ or TIMEZONE (timezone is required, e.g., 'UTC', 'Asia/Riyadh')"
            )

        # Check allowed agent types [REQUIRED]
        agent_types_from_env = os.getenv("ALLOWED_AGENT_TYPES")
        if not agent_types_from_env or agent_types_from_env.strip() == "":
            missing.append(
                "ALLOWED_AGENT_TYPES (comma-separated list of agent types, e.g., 'security,monitoring,automation')"
            )
        elif len(self.ALLOWED_AGENT_TYPES) > 100:
            missing.append(
                "ALLOWED_AGENT_TYPES (cannot contain more than 100 agent types)"
            )

        # Check JWT configuration [REQUIRED]
        if not self.JWT_SECRET or self.JWT_SECRET.strip() == "":
            missing.append("JWT_SECRET (required for authentication)")
        if not self.JWT_ALGORITHM or self.JWT_ALGORITHM.strip() == "":
            missing.append("JWT_ALGORITHM (JWT algorithm required, e.g., 'HS256')")
        if self.JWT_EXPIRE_MINUTES is None:
            missing.append(
                "JWT_EXPIRE_MINUTES (JWT expiration time in minutes required, e.g., '60')"
            )

        # Check admin credentials [REQUIRED]
        if not self.ADMIN_USERNAME or self.ADMIN_USERNAME.strip() == "":
            missing.append("ADMIN_USERNAME (required for admin authentication)")
        if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD.strip() == "":
            missing.append("ADMIN_PASSWORD (required for admin authentication)")

        return missing

    def validate_optional_config(self) -> Dict[str, List[str]]:
        """
        Validate optional configuration and return list of missing variables by category.

        Returns:
            Dictionary with categories and their missing variables
        """
        optional_missing = {
            "azure": [],
            "redis": [],
            "security": [],
            "agent": [],
        }

        # Check Azure OpenAI configuration [OPTIONAL]
        if not self.AZURE_API_KEY:
            optional_missing["azure"].append("AZURE_API_KEY")
        if not self.AZURE_API_BASE:
            optional_missing["azure"].append("AZURE_API_BASE")
        if not self.AZURE_API_VERSION:
            optional_missing["azure"].append("AZURE_API_VERSION")
        if not self.AZURE_EMBEDDING_DEPLOYMENT:
            optional_missing["azure"].append("AZURE_EMBEDDING_DEPLOYMENT")

        # Check Redis configuration [OPTIONAL]
        if not self.REDIS_HOST:
            optional_missing["redis"].append("REDIS_HOST")
        if self.REDIS_PORT is None:
            optional_missing["redis"].append("REDIS_PORT")
        if self.REDIS_PASSWORD is None:
            optional_missing["redis"].append("REDIS_PASSWORD")
        if self.REDIS_DB is None:
            optional_missing["redis"].append("REDIS_DB")
        if not self.REDIS_MAX_MEMORY:
            optional_missing["redis"].append("REDIS_MAX_MEMORY")
        if (
            self.REDIS_HEALTH_CHECK_INTERVAL is None
            or self.REDIS_HEALTH_CHECK_INTERVAL <= 0
        ):
            optional_missing["redis"].append("REDIS_HEALTH_CHECK_INTERVAL (> 0)")
        if not self.REDIS_EXPORTER_PORT:
            optional_missing["redis"].append("REDIS_EXPORTER_PORT")

        # Check Security configuration [OPTIONAL but important for production]
        if not self.ALLOWED_ORIGINS:
            optional_missing["security"].append(
                "ALLOWED_ORIGINS (important for CORS security)"
            )
        if not self.TRUSTED_HOSTS:
            optional_missing["security"].append(
                "TRUSTED_HOSTS (important for host security)"
            )

        # Check Agent Registration Keys [OPTIONAL]
        if not self.AGENT_REGISTRATION_KEYS:
            optional_missing["agent"].append("AGENT_KEYS (agent registration keys)")

        # IP filtering guidance [OPTIONAL]
        if self.IP_DEFAULT_DENY and not self.ALLOWED_IP_RANGES:
            optional_missing["security"].append(
                "ALLOWED_IP_RANGES (required when IP_DEFAULT_DENY=true)"
            )

        return optional_missing

    def validate_config_values(self) -> List[str]:
        """
        Validate configuration values for proper formats, ranges, and constraints.

        Returns:
            List of configuration validation errors
        """
        errors = []

        # Validate numeric ranges
        try:
            if not (1 <= self.PORT <= 65535):
                errors.append("ARCP_PORT (must be between 1 and 65535)")
        except (ValueError, TypeError):
            errors.append("ARCP_PORT (must be a valid integer)")

        try:
            if self.JWT_EXPIRE_MINUTES is not None and self.JWT_EXPIRE_MINUTES <= 0:
                errors.append("JWT_EXPIRE_MINUTES (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("JWT_EXPIRE_MINUTES (must be a valid positive integer)")

        try:
            if self.RATE_LIMIT_RPM < 0:
                errors.append("RATE_LIMIT_RPM (cannot be negative)")
        except (ValueError, TypeError):
            errors.append("RATE_LIMIT_RPM (must be a valid non-negative integer)")

        try:
            if self.RATE_LIMIT_BURST < 0:
                errors.append("RATE_LIMIT_BURST (cannot be negative)")
        except (ValueError, TypeError):
            errors.append("RATE_LIMIT_BURST (must be a valid non-negative integer)")

        try:
            if self.SESSION_TIMEOUT <= 0:
                errors.append("SESSION_TIMEOUT (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("SESSION_TIMEOUT (must be a valid positive integer)")

        try:
            if self.MAX_SESSIONS <= 0:
                errors.append("MAX_SESSIONS (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("MAX_SESSIONS (must be a valid positive integer)")

        try:
            if self.MAX_JSON_SIZE <= 0:
                errors.append("MAX_JSON_SIZE (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("MAX_JSON_SIZE (must be a valid positive integer)")

        try:
            if self.MAX_QUERY_PARAMS <= 0:
                errors.append("MAX_QUERY_PARAMS (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("MAX_QUERY_PARAMS (must be a valid positive integer)")

        try:
            if self.MAX_HEADER_SIZE <= 0:
                errors.append("MAX_HEADER_SIZE (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("MAX_HEADER_SIZE (must be a valid positive integer)")

        # Validate agent configuration
        try:
            if self.AGENT_HEARTBEAT_TIMEOUT <= 0:
                errors.append("AGENT_HEARTBEAT_TIMEOUT (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("AGENT_HEARTBEAT_TIMEOUT (must be a valid positive integer)")

        try:
            if self.AGENT_CLEANUP_INTERVAL <= 0:
                errors.append("AGENT_CLEANUP_INTERVAL (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("AGENT_CLEANUP_INTERVAL (must be a valid positive integer)")

        try:
            if self.AGENT_REGISTRATION_TIMEOUT <= 0:
                errors.append("AGENT_REGISTRATION_TIMEOUT (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append(
                "AGENT_REGISTRATION_TIMEOUT (must be a valid positive integer)"
            )

        # Validate WebSocket configuration
        websocket_configs = [
            ("WEBSOCKET_INTERVAL", self.WEBSOCKET_INTERVAL),
            ("WEBSOCKET_TIMEOUT", self.WEBSOCKET_TIMEOUT),
            ("WEBSOCKET_PING_INTERVAL", self.WEBSOCKET_PING_INTERVAL),
            ("WEBSOCKET_MAX_CONNECTIONS", self.WEBSOCKET_MAX_CONNECTIONS),
            ("DASHBOARD_WS_INTERVAL", self.DASHBOARD_WS_INTERVAL),
            ("DASHBOARD_WS_TIMEOUT", self.DASHBOARD_WS_TIMEOUT),
            ("DASHBOARD_WS_PING_INTERVAL", self.DASHBOARD_WS_PING_INTERVAL),
            (
                "DASHBOARD_WS_MAX_CONNECTIONS",
                self.DASHBOARD_WS_MAX_CONNECTIONS,
            ),
            ("AGENT_WS_INTERVAL", self.AGENT_WS_INTERVAL),
            ("AGENT_WS_TIMEOUT", self.AGENT_WS_TIMEOUT),
            ("AGENT_WS_PING_INTERVAL", self.AGENT_WS_PING_INTERVAL),
            ("AGENT_WS_MAX_CONNECTIONS", self.AGENT_WS_MAX_CONNECTIONS),
            ("PUBLIC_WS_INTERVAL", self.PUBLIC_WS_INTERVAL),
            ("PUBLIC_WS_TIMEOUT", self.PUBLIC_WS_TIMEOUT),
            ("PUBLIC_WS_PING_INTERVAL", self.PUBLIC_WS_PING_INTERVAL),
            ("PUBLIC_WS_MAX_CONNECTIONS", self.PUBLIC_WS_MAX_CONNECTIONS),
        ]

        for config_name, config_value in websocket_configs:
            try:
                if config_value <= 0:
                    errors.append(f"{config_name} (must be greater than 0)")
            except (ValueError, TypeError):
                errors.append(f"{config_name} (must be a valid positive integer)")

        # Validate vector search configuration
        try:
            if self.VECTOR_SEARCH_TOP_K <= 0:
                errors.append("VECTOR_SEARCH_TOP_K (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append("VECTOR_SEARCH_TOP_K (must be a valid positive integer)")

        try:
            if not (0.0 <= self.VECTOR_SEARCH_MIN_SIMILARITY <= 1.0):
                errors.append(
                    "VECTOR_SEARCH_MIN_SIMILARITY (must be between 0.0 and 1.0)"
                )
        except (ValueError, TypeError):
            errors.append(
                "VECTOR_SEARCH_MIN_SIMILARITY (must be a valid float between 0.0 and 1.0)"
            )

        # Validate network configuration
        try:
            if self.NETWORK_INTERFACE_CAPACITY_MBPS <= 0:
                errors.append(
                    "NETWORK_INTERFACE_CAPACITY_MBPS (must be greater than 0)"
                )
            elif (
                self.NETWORK_INTERFACE_CAPACITY_MBPS > 1000000
            ):  # 1 Tbps seems like a reasonable upper limit
                errors.append(
                    "NETWORK_INTERFACE_CAPACITY_MBPS (must be less than or equal to 1,000,000 Mbps)"
                )
        except (ValueError, TypeError):
            errors.append(
                "NETWORK_INTERFACE_CAPACITY_MBPS (must be a valid positive number)"
            )

        # Validate Azure OpenAI embedding deployment configuration
        if self.AZURE_EMBEDDING_DEPLOYMENT:
            valid_embedding_models = [
                "text-embedding-ada-002",
                "text-embedding-3-small",
                "text-embedding-3-large",
                "text-search-ada-doc-001",
                "text-search-ada-query-001",
                "text-similarity-ada-001",
                "text-similarity-babbage-001",
                "text-similarity-curie-001",
                "text-similarity-davinci-001",
            ]

            embedding_deployment = self.AZURE_EMBEDDING_DEPLOYMENT.lower().strip()

            # Check if the deployment name contains a known embedding model
            is_valid_embedding = any(
                valid_model in embedding_deployment
                for valid_model in valid_embedding_models
            )

            if not is_valid_embedding:
                errors.append(
                    f"AZURE_EMBEDDING_DEPLOYMENT ('{self.AZURE_EMBEDDING_DEPLOYMENT}') "
                    f"does not appear to be a valid embedding model. "
                    f"Recommended embedding models: {', '.join(valid_embedding_models[:3])}. "
                    f"Ensure your deployment is based on an embedding model, not a chat/completion model."
                )

        # Validate dashboard log limits
        try:
            if self.DASHBOARD_LOG_BUFFER_MAXLEN <= 0:
                errors.append("DASHBOARD_LOG_BUFFER_MAXLEN (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append(
                "DASHBOARD_LOG_BUFFER_MAXLEN (must be a valid positive integer)"
            )

        try:
            if self.DASHBOARD_LOG_MESSAGE_MAXLEN <= 0:
                errors.append("DASHBOARD_LOG_MESSAGE_MAXLEN (must be greater than 0)")
        except (ValueError, TypeError):
            errors.append(
                "DASHBOARD_LOG_MESSAGE_MAXLEN (must be a valid positive integer)"
            )

        # Validate optional Redis configuration
        if self.REDIS_PORT is not None:
            try:
                if not (1 <= self.REDIS_PORT <= 65535):
                    errors.append("REDIS_PORT (must be between 1 and 65535)")
            except (ValueError, TypeError):
                errors.append("REDIS_PORT (must be a valid integer)")

        if self.REDIS_DB is not None:
            try:
                if self.REDIS_DB < 0:
                    errors.append("REDIS_DB (cannot be negative)")
            except (ValueError, TypeError):
                errors.append("REDIS_DB (must be a valid non-negative integer)")

        if self.REDIS_HEALTH_CHECK_INTERVAL is not None:
            try:
                if self.REDIS_HEALTH_CHECK_INTERVAL <= 0:
                    errors.append(
                        "REDIS_HEALTH_CHECK_INTERVAL (must be greater than 0)"
                    )
            except (ValueError, TypeError):
                errors.append(
                    "REDIS_HEALTH_CHECK_INTERVAL (must be a valid positive integer)"
                )

        if self.REDIS_EXPORTER_PORT is not None:
            try:
                if not (1 <= self.REDIS_EXPORTER_PORT <= 65535):
                    errors.append("REDIS_EXPORTER_PORT (must be between 1 and 65535)")
            except (ValueError, TypeError):
                errors.append("REDIS_EXPORTER_PORT (must be a valid integer)")

        # Validate port numbers for monitoring services
        try:
            if not (1 <= self.PROMETHEUS_PORT <= 65535):
                errors.append("PROMETHEUS_PORT (must be between 1 and 65535)")
        except (ValueError, TypeError):
            errors.append("PROMETHEUS_PORT (must be a valid integer)")

        try:
            if not (1 <= self.GRAFANA_PORT <= 65535):
                errors.append("GRAFANA_PORT (must be between 1 and 65535)")
        except (ValueError, TypeError):
            errors.append("GRAFANA_PORT (must be a valid integer)")

        # Validate tracing configuration
        try:
            if not (0.0 <= self.TRACE_SAMPLE_RATE <= 1.0):
                errors.append("TRACE_SAMPLE_RATE (must be between 0.0 and 1.0)")
        except (ValueError, TypeError):
            errors.append(
                "TRACE_SAMPLE_RATE (must be a valid float between 0.0 and 1.0)"
            )

        jaeger_ports = [
            ("JAEGER_UI_PORT", self.JAEGER_UI_PORT),
            ("JAEGER_GRPC_PORT", self.JAEGER_GRPC_PORT),
            ("JAEGER_THRIFT_PORT", self.JAEGER_THRIFT_PORT),
            ("JAEGER_OTLP_GRPC_PORT", self.JAEGER_OTLP_GRPC_PORT),
            ("JAEGER_OTLP_HTTP_PORT", self.JAEGER_OTLP_HTTP_PORT),
            ("JAEGER_METRICS_PORT", self.JAEGER_METRICS_PORT),
        ]

        for port_name, port_value in jaeger_ports:
            try:
                if not (1 <= port_value <= 65535):
                    errors.append(f"{port_name} (must be between 1 and 65535)")
            except (ValueError, TypeError):
                errors.append(f"{port_name} (must be a valid integer)")

        return errors

    def validate_production_config(self) -> List[str]:
        """
        Validate production-specific configuration requirements.

        Returns:
            List of production configuration issues and recommendations
        """
        issues = []

        if self.ENVIRONMENT and self.ENVIRONMENT.lower() != "production":
            return issues  # Only validate for production environment

        # JWT Secret length for production
        if self.JWT_SECRET and len(self.JWT_SECRET) < 32:
            issues.append(
                "JWT_SECRET (should be at least 32 characters in production for security)"
            )

        # Security settings for production
        if not self.ALLOWED_ORIGINS:
            issues.append("ALLOWED_ORIGINS (critical for production CORS security)")
        if not self.TRUSTED_HOSTS:
            issues.append("TRUSTED_HOSTS (critical for production host security)")

        # CSP settings for production
        if self.CSP_ALLOW_CONNECT_HTTP:
            issues.append(
                "CSP_ALLOW_CONNECT_HTTP (should be false in production - HTTPS only)"
            )

        # Rate limiting recommendations for production
        if self.RATE_LIMIT_RPM > 500:
            issues.append(
                f"RATE_LIMIT_RPM ({self.RATE_LIMIT_RPM}) - consider lowering for production security"
            )
        if self.SESSION_TIMEOUT > 60:
            issues.append(
                f"SESSION_TIMEOUT ({self.SESSION_TIMEOUT}min) - consider shorter timeout for production"
            )
        if self.MAX_SESSIONS > 10:
            issues.append(
                f"MAX_SESSIONS ({self.MAX_SESSIONS}) - consider limiting concurrent sessions in production"
            )

        # Security logging
        if not self.SECURITY_LOGGING:
            issues.append(
                "SECURITY_LOGGING (should be enabled in production for audit trail)"
            )

        # Debug mode
        if self.DEBUG:
            issues.append("ARCP_DEBUG (should be false in production)")

        # Log level
        if self.LOG_LEVEL.upper() == "DEBUG":
            issues.append("LOG_LEVEL (DEBUG level not recommended for production)")

        # Default passwords
        if self.ADMIN_PASSWORD and self.ADMIN_PASSWORD.lower() in [
            "admin",
            "password",
            "arcp",
            "default",
        ]:
            issues.append(
                "ADMIN_PASSWORD (should not use default/common passwords in production)"
            )

        if self.GRAFANA_PASSWORD and self.GRAFANA_PASSWORD.lower() in [
            "admin",
            "password",
            "default",
        ]:
            issues.append(
                "GRAFANA_PASSWORD (should not use default passwords in production)"
            )

        if self.REDIS_PASSWORD and self.REDIS_PASSWORD.lower() in [
            "admin",
            "password",
            "default",
            "redis",
        ]:
            issues.append(
                "REDIS_PASSWORD (should not use default passwords in production)"
            )

        return issues

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration as a dictionary."""
        return {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "password": self.REDIS_PASSWORD if self.REDIS_PASSWORD else None,
            "db": self.REDIS_DB,
            "decode_responses": False,
            "health_check_interval": self.REDIS_HEALTH_CHECK_INTERVAL,
            "max_memory": self.REDIS_MAX_MEMORY,
        }

    def get_azure_config(self) -> Dict[str, Optional[str]]:
        """Get Azure OpenAI configuration as a dictionary."""
        return {
            "api_key": self.AZURE_API_KEY,
            "azure_endpoint": self.AZURE_API_BASE,
            "api_version": self.AZURE_API_VERSION,
            "deployment": self.AZURE_EMBEDDING_DEPLOYMENT,
        }

    def get_azure_embedding_info(self) -> Dict[str, Any]:
        """
        Get Azure OpenAI embedding configuration information and validation.

        Returns:
            Dictionary containing embedding configuration details and validation status
        """
        valid_embedding_models = [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-search-ada-doc-001",
            "text-search-ada-query-001",
            "text-similarity-ada-001",
            "text-similarity-babbage-001",
            "text-similarity-curie-001",
            "text-similarity-davinci-001",
        ]

        is_configured = bool(self.AZURE_EMBEDDING_DEPLOYMENT)
        is_valid = False
        recommendations = []

        if is_configured:
            embedding_deployment = self.AZURE_EMBEDDING_DEPLOYMENT.lower().strip()
            is_valid = any(
                valid_model in embedding_deployment
                for valid_model in valid_embedding_models
            )

            if not is_valid:
                recommendations.append(
                    f"[!] '{self.AZURE_EMBEDDING_DEPLOYMENT}' does not appear to be an embedding model"
                )
                recommendations.append(
                    "Ensure your deployment is based on an embedding model, not a chat/completion model"
                )
        else:
            recommendations.append(
                "! No Azure embedding deployment configured (optional)"
            )

        if not is_valid and is_configured:
            recommendations.extend(
                [
                    " Recommended embedding models:",
                    "   • text-embedding-ada-002 (Most popular, good performance)",
                    "   • text-embedding-3-small (Newer, cost-effective)",
                    "   • text-embedding-3-large (Newer, best performance)",
                    "  Set AZURE_EMBEDDING_DEPLOYMENT to your deployment name (not the model name)",
                ]
            )

        return {
            "configured": is_configured,
            "deployment_name": self.AZURE_EMBEDDING_DEPLOYMENT,
            "is_valid_embedding": is_valid,
            "valid_models": valid_embedding_models,
            "recommendations": recommendations,
            "azure_configured": bool(self.AZURE_API_KEY and self.AZURE_API_BASE),
        }

    def get_prometheus_config(self) -> Dict[str, Any]:
        """Get Prometheus configuration as a dictionary."""
        return {
            "host": self.PROMETHEUS_HOST,
            "port": self.PROMETHEUS_PORT,
            "url": f"http://{self.PROMETHEUS_HOST}:{self.PROMETHEUS_PORT}",
        }

    def get_grafana_config(self) -> Dict[str, Any]:
        """Get Grafana configuration as a dictionary."""
        return {
            "host": self.GRAFANA_HOST,
            "port": self.GRAFANA_PORT,
            "password": self.GRAFANA_PASSWORD,
            "url": f"http://{self.GRAFANA_HOST}:{self.GRAFANA_PORT}",
        }

    def ensure_data_directory(self) -> None:
        """Ensure the data directory exists."""
        Path(self.DATA_DIRECTORY).mkdir(parents=True, exist_ok=True)

    def ensure_logs_directory(self) -> None:
        """Ensure the logs directory exists.

        Attempts the configured path first. If creation fails (e.g., read-only
        filesystem), falls back to a writable location while preserving the
        original environment variable. The resolved directory is stored back in
        self.LOGS_DIR so other components can use it.
        """
        try:
            Path(self.LOGS_DIR).mkdir(parents=True, exist_ok=True)
            return
        except Exception:
            pass

        # Try data directory fallback
        try:
            fallback = Path(self.DATA_DIRECTORY) / "logs"
            fallback.mkdir(parents=True, exist_ok=True)
            self.LOGS_DIR = str(fallback)
            return
        except Exception:
            pass

        # Try user home directory fallback (cross-platform writable location)
        try:
            home_fallback = Path.home() / "arcp" / "logs"
            home_fallback.mkdir(parents=True, exist_ok=True)
            self.LOGS_DIR = str(home_fallback)
            return
        except Exception:
            pass

        # Final fallback to /tmp which is typically writable (and tmpfs in Docker compose)
        try:
            tmp_fallback = Path("/tmp/arcp/logs")
            tmp_fallback.mkdir(parents=True, exist_ok=True)
            self.LOGS_DIR = str(tmp_fallback)
        except Exception:
            # Give up silently; logging will continue to stdout
            pass

    def apply_timezone(self) -> None:
        """Apply the configured timezone setting to the system."""

        if self.TIMEZONE:
            os.environ["TZ"] = self.TIMEZONE
            try:
                time.tzset()  # Apply timezone setting (Unix-like systems)
                logging.info(f"Timezone set to: {self.TIMEZONE}")
            except (AttributeError, OSError):
                # tzset() not available on Windows or failed
                # This is expected on Windows - timezone will be handled by Python's datetime libraries
                if platform.system() == "Windows":
                    logging.debug(
                        f"Timezone {self.TIMEZONE} configured for Python datetime libraries (tzset not available on Windows)"
                    )
                else:
                    logging.warning(
                        f"Could not set system timezone to {self.TIMEZONE} - tzset not available or failed"
                    )
        else:
            logging.warning("No timezone configured - using system default")

    def get_allowed_agent_types(self) -> List[str]:
        """Get list of allowed agent types."""
        return self.ALLOWED_AGENT_TYPES.copy()

    def is_valid_agent_type(self, agent_type: str) -> bool:
        """Check if an agent type is allowed for registration."""
        return agent_type.strip().lower() in [
            t.lower() for t in self.ALLOWED_AGENT_TYPES
        ]

    def get_agent_types_info(self) -> Dict[str, Any]:
        """Get agent types configuration information."""
        return {
            "allowed_types": self.ALLOWED_AGENT_TYPES,
            "total_types": len(self.ALLOWED_AGENT_TYPES),
            "source": "ALLOWED_AGENT_TYPES environment variable",
        }

    def get_timezone_info(self) -> Dict[str, Any]:
        """Get current timezone information."""

        now = datetime.datetime.now()
        utc_now = datetime.datetime.utcnow()

        return {
            "configured_timezone": self.TIMEZONE,
            "system_timezone": time.tzname,
            "current_local_time": now.isoformat(),
            "current_utc_time": utc_now.isoformat(),
            "utc_offset": str(now - utc_now),
        }

    def validate_all_config(self) -> Dict[str, List[str]]:
        """
        Run comprehensive validation of all configuration settings.

        Returns:
            Dictionary with validation results for all categories
        """
        validation_results = {
            "required_missing": [],
            "optional_missing": {},
            "value_errors": [],
            "production_issues": [],
        }

        # Check required configuration
        validation_results["required_missing"] = self.validate_required_config()

        # Check optional configuration
        validation_results["optional_missing"] = self.validate_optional_config()

        # Check configuration value validity
        validation_results["value_errors"] = self.validate_config_values()

        # Check production-specific issues
        validation_results["production_issues"] = self.validate_production_config()

        return validation_results

    def is_loaded(self) -> bool:
        """Check if configuration has been loaded."""
        return getattr(self, "_loaded", False)

    def get_load_error(self) -> Optional[Exception]:
        """Get the error that occurred during config loading, if any."""
        return getattr(self, "_load_error", None)


# Global configuration instance - will be loaded lazily
config = ARCPConfig()


def get_config() -> ARCPConfig:
    """Get the global configuration instance. Will load config if not already loaded."""
    return config


def is_config_loaded() -> bool:
    """Check if the global configuration has been loaded."""
    return config.is_loaded()
