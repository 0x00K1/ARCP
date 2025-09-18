"""
Agent-related test fixtures and sample data for ARCP tests.

Provides reusable agent registrations, agent info objects, and related test data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from src.arcp.models.agent import (
    AgentInfo,
    AgentMetrics,
    AgentRegistration,
    AgentRequirements,
    OptionalConfigField,
    RequiredConfigField,
)


@pytest.fixture
def sample_agent_registration() -> AgentRegistration:
    """Sample agent registration for testing."""
    return AgentRegistration(
        name="Test Security Agent",
        agent_id="test-security-001",
        agent_type="security",
        endpoint="https://test-agent.example.com/api",
        context_brief="Specialized security analysis agent for vulnerability assessment and threat detection",
        capabilities=[
            "vulnerability_scan",
            "threat_analysis",
            "security_audit",
            "penetration_testing",
        ],
        owner="ARCP Test Suite",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC5M8P2K4R7S9U1X3Y6Z8A0C2E4G6I8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0Q2S4U6W8Y0A2C4E6G8I0K2M4O6Q8S0U2W4Y6A8C0E2G4I6K8M0O2Q4S6U8W0Y2A4C6E8G0I2K4M6O8Q0S2U4W6Y8A0C2E4G6I8K0M2 sample-registration-key",
        metadata={
            "description": "A test security agent for comprehensive testing",
            "tags": ["security", "testing", "automation"],
            "supported_formats": ["json", "xml", "yaml"],
            "api_version": "v2.1",
        },
        version="2.1.0",
        communication_mode="remote",
        features=["real_time_scanning", "batch_processing", "custom_rules"],
        max_tokens=4096,
        language_support=["python", "javascript", "go", "rust"],
        rate_limit=100,
        requirements=AgentRequirements(
            system_requirements=["linux", "docker"],
            permissions=["network", "file_read"],
            dependencies=["python>=3.8", "docker>=20.10"],
            minimum_memory_mb=512,
            minimum_disk_space_mb=1024,
            requires_internet=True,
            network_ports=["8080", "8443"],
            required_fields=[
                RequiredConfigField(
                    name="api_key",
                    label="API Key",
                    type="text",
                    description="Required API key for security scanning",
                )
            ],
            optional_fields=[
                OptionalConfigField(
                    name="scan_depth",
                    label="Scan Depth",
                    type="select",
                    options=["shallow", "medium", "deep"],
                    default_value="medium",
                )
            ],
        ),
        policy_tags=["security", "scanning", "approved"],
    )


@pytest.fixture
def sample_agent_info() -> AgentInfo:
    """Sample agent info for testing."""
    now = datetime.now(timezone.utc)
    return AgentInfo(
        agent_id="test-security-001",
        name="Test Security Agent",
        agent_type="security",
        endpoint="https://test-agent.example.com/api",
        capabilities=["vulnerability_scan", "threat_analysis"],
        context_brief="Specialized security analysis agent",
        version="2.1.0",
        owner="ARCP Test Suite",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC8YwA3O2L4nQ0rS6tV9xF3zJ5pL7sB4eG8hK2nO3qS4rV5xY6zC7dF8gK9jM0nP1qT2sW3xZ4aC5dG6hK7jM8nP9qS0rV1xY2zC3dF4gK5jM6nP7qS8rV9xY0zC1dF2gK3jM4nP5qS6rV7xY8zC9dF0gK1jM2nP3qS4rV5xY6 test-monitoring-key",
        metadata={
            "description": "Test agent",
            "tags": ["security", "testing"],
        },
        communication_mode="remote",
        status="alive",
        last_seen=now,
        registered_at=now,
        similarity=0.85,
        metrics=AgentMetrics(
            agent_id="test-security-001",
            success_rate=0.95,
            avg_response_time=1.2,
            total_requests=150,
            reputation_score=4.8,
            requests_processed=150,
            average_response_time=1.2,
            error_rate=0.05,
        ),
    )


@pytest.fixture
def multiple_agent_registrations() -> List[AgentRegistration]:
    """Multiple agent registrations for testing list operations."""
    return [
        AgentRegistration(
            name="Security Scanner",
            agent_id="security-scanner-001",
            agent_type="security",
            endpoint="https://security.example.com/api",
            context_brief="Automated security scanning and vulnerability assessment",
            capabilities=["vulnerability_scan", "port_scan", "ssl_check"],
            owner="Security Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3K5N1P7qS9tU2W5X8Z0A2C4E6G8I0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0 security-scanner-key",
            metadata={"priority": "high", "region": "us-east-1"},
            version="1.5.0",
            communication_mode="remote",
        ),
        AgentRegistration(
            name="Data Analyzer",
            agent_id="data-analyzer-002",
            agent_type="automation",
            endpoint="https://analytics.example.com/api",
            context_brief="Advanced data analysis and pattern recognition",
            capabilities=[
                "data_analysis",
                "pattern_recognition",
                "ml_inference",
            ],
            owner="Data Science Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD4L6O2Q8rT0uV3X6Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5H7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 analytics-data-key",
            metadata={"priority": "medium", "region": "eu-west-1"},
            version="3.2.1",
            communication_mode="hybrid",
        ),
        AgentRegistration(
            name="System Monitor",
            agent_id="system-monitor-003",
            agent_type="monitoring",
            endpoint="https://monitor.example.com/api",
            context_brief="Real-time system monitoring and alerting",
            capabilities=["system_monitoring", "alerting", "log_analysis"],
            owner="DevOps Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD5M7P3R9sU1vW4Y7Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6 system-monitor-key",
            metadata={"priority": "critical", "region": "ap-south-1"},
            version="2.0.0",
            communication_mode="local",
        ),
    ]


@pytest.fixture
def agent_metrics_samples() -> List[AgentMetrics]:
    """Sample agent metrics for testing."""
    return [
        AgentMetrics(
            agent_id="test-agent-001",
            success_rate=0.98,
            avg_response_time=0.8,
            total_requests=500,
            reputation_score=4.9,
            requests_processed=500,
            average_response_time=0.8,
            error_rate=0.02,
        ),
        AgentMetrics(
            agent_id="test-agent-002",
            success_rate=0.92,
            avg_response_time=1.5,
            total_requests=300,
            reputation_score=4.3,
            requests_processed=300,
            average_response_time=1.5,
            error_rate=0.08,
        ),
        AgentMetrics(
            agent_id="test-agent-003",
            success_rate=0.85,
            avg_response_time=2.1,
            total_requests=150,
            reputation_score=3.8,
            requests_processed=150,
            average_response_time=2.1,
            error_rate=0.15,
        ),
    ]


@pytest.fixture
def vector_embeddings() -> Dict[str, List[float]]:
    """Sample vector embeddings for testing search functionality."""
    return {
        "security-scanner-001": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        "data-analyzer-002": [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
        "system-monitor-003": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    }


@pytest.fixture
def agent_connection_request_data() -> Dict[str, Any]:
    """Sample agent connection request data."""
    return {
        "user_id": "external-user-123",
        "user_endpoint": "https://external-app.example.com/callback",
        "display_name": "External Application User",
        "additional_info": {
            "app_name": "Security Dashboard",
            "app_version": "1.0.0",
            "contact_email": "user@example.com",
        },
    }


@pytest.fixture
def search_request_data() -> Dict[str, Any]:
    """Sample search request data for vector search testing."""
    return {
        "query": "security vulnerability scanning agent",
        "top_k": 5,
        "min_similarity": 0.7,
        "capabilities": ["vulnerability_scan"],
        "weighted": True,
        "agent_type": "security",
    }


def create_test_agent(
    agent_id: str = "test-agent",
    agent_type: str = "generic",
    capabilities: List[str] = None,
    status: str = "alive",
) -> AgentInfo:
    """Create a test agent with customizable properties."""
    if capabilities is None:
        capabilities = ["test_capability"]

    now = datetime.now(timezone.utc)
    return AgentInfo(
        agent_id=agent_id,
        name=f"Test {agent_type.title()} Agent",
        agent_type=agent_type,
        endpoint=f"https://{agent_id}.example.com/api",
        capabilities=capabilities,
        context_brief=f"Test agent for {agent_type} operations",
        version="1.0.0",
        owner="Test Suite",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD0A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8W9X0Y1Z2A3B4C5D6E7F8G9H0I1J2K3L4M5N6O7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F4 test-creation-key",
        metadata={"test": True},
        communication_mode="remote",
        status=status,
        last_seen=now,
        registered_at=now,
    )


def create_test_agent_registration(
    agent_id: str = "test-agent",
    agent_type: str = "generic",
    capabilities: List[str] = None,
) -> AgentRegistration:
    """Create a test agent registration with customizable properties."""
    if capabilities is None:
        capabilities = ["test_capability"]

    return AgentRegistration(
        name=f"Test {agent_type.title()} Agent",
        agent_id=agent_id,
        agent_type=agent_type,
        endpoint=f"https://{agent_id}.example.com/api",
        context_brief=f"Test agent for {agent_type} operations",
        capabilities=capabilities,
        owner="Test Suite",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8W9X0Y1Z2A3B4C5D6E7F8G9H0I1J2K3L4M5N6O7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F5 test-fixture-key",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )


@pytest.fixture
def sample_agents_data(multiple_agent_registrations) -> List[Dict[str, Any]]:
    """Convert agent registrations to dictionary format for tests."""
    return [
        {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "agent_type": agent.agent_type,
            "endpoint": agent.endpoint,
            "capabilities": agent.capabilities,
            "owner": agent.owner,
            "version": agent.version,
            "public_key": agent.public_key,
            "metadata": agent.metadata,
            "communication_mode": agent.communication_mode,
        }
        for agent in multiple_agent_registrations
    ]
