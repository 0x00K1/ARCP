"""
Unit tests for agent data models.

Tests the Pydantic models for agent registration, info, metrics, and search.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.arcp.models.agent import (
    AgentInfo,
    AgentMetrics,
    AgentRegistration,
    AgentRequirements,
    OptionalConfigField,
    RequiredConfigField,
    SearchRequest,
    SearchResponse,
)


@pytest.mark.unit
class TestAgentRegistration:
    """Test AgentRegistration model validation and serialization."""

    def test_minimal_agent_registration(self):
        """Test agent registration with minimal required fields."""
        registration = AgentRegistration(
            name="Test Agent",
            agent_id="test-agent-001",
            agent_type="testing",
            endpoint="https://test.example.com/api",
            context_brief="A test agent",
            capabilities=["test"],
            owner="Test Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD6F9H2J4L6M8O0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6 test-minimal-key",
            version="1.0.0",
            communication_mode="remote",
            metadata={"test": True, "validation": True},
        )

        assert registration.name == "Test Agent"
        assert registration.agent_id == "test-agent-001"
        assert registration.agent_type == "testing"
        assert registration.capabilities == ["test"]
        assert registration.communication_mode == "remote"

    def test_comprehensive_agent_registration(self):
        """Test agent registration with all optional fields."""
        requirements = AgentRequirements(
            system_requirements=["linux", "docker"],
            permissions=["network", "file_read"],
            dependencies=["python>=3.8"],
            minimum_memory_mb=512,
            minimum_disk_space_mb=1024,
            requires_internet=True,
            network_ports=["8080"],
            required_fields=[
                RequiredConfigField(
                    name="api_key",
                    label="API Key",
                    type="text",
                    description="Required API key",
                )
            ],
            optional_fields=[
                OptionalConfigField(
                    name="timeout",
                    label="Timeout",
                    type="number",
                    default_value=30,
                )
            ],
        )

        registration = AgentRegistration(
            name="Comprehensive Agent",
            agent_id="comp-agent-001",
            agent_type="automation",
            endpoint="https://comprehensive.example.com/api",
            context_brief="A comprehensive test agent with all features",
            capabilities=["analysis", "generation", "translation"],
            owner="Test Organization",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 comprehensive-test-key",
            metadata={"priority": "high", "region": "us-east-1"},
            version="2.1.0",
            communication_mode="hybrid",
            features=["streaming", "batch_processing"],
            max_tokens=8192,
            language_support=["en", "es", "fr"],
            rate_limit=1000,
            requirements=requirements,
            policy_tags=["production", "approved"],
        )

        assert registration.features == ["streaming", "batch_processing"]
        assert registration.max_tokens == 8192
        assert registration.language_support == ["en", "es", "fr"]
        assert registration.rate_limit == 1000
        assert registration.requirements is not None
        assert registration.policy_tags == ["production", "approved"]

    def test_agent_id_validation(self):
        """Test agent ID validation rules."""
        valid_ids = [
            "agent-001",
            "test_agent_123",
            "analytics-engine-v2",
            "a" * 50,  # Max length
        ]

        for agent_id in valid_ids:
            registration = AgentRegistration(
                name="Test Agent",
                agent_id=agent_id,
                agent_type="testing",
                endpoint="https://test.example.com/api",
                context_brief="Test agent for validation purposes and testing",
                capabilities=["test"],
                owner="Test",
                public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
                metadata={"test": True, "validation": True},
                version="1.0.0",
                communication_mode="remote",
            )
            assert registration.agent_id == agent_id

    def test_invalid_agent_registration(self):
        """Test validation errors for invalid agent registrations."""
        # Missing required field
        with pytest.raises(ValidationError):
            AgentRegistration(
                name="Test Agent",
                # Missing agent_id
                agent_type="testing",
                endpoint="https://test.example.com/api",
                context_brief="Test",
                capabilities=["test"],
                owner="Test",
                public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
                version="1.0.0",
                communication_mode="remote",
            )

        # Invalid endpoint URL
        with pytest.raises(ValidationError):
            AgentRegistration(
                name="Test Agent",
                agent_id="test-agent",
                agent_type="testing",
                endpoint="not-a-url",
                context_brief="Test",
                capabilities=["test"],
                owner="Test",
                public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
                version="1.0.0",
                communication_mode="remote",
            )

        # Empty capabilities
        with pytest.raises(ValidationError):
            AgentRegistration(
                name="Test Agent",
                agent_id="test-agent",
                agent_type="testing",
                endpoint="https://test.example.com/api",
                context_brief="Test",
                capabilities=[],  # Empty list should fail
                owner="Test",
                public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
                version="1.0.0",
                communication_mode="remote",
            )


@pytest.mark.unit
class TestAgentInfo:
    """Test AgentInfo model validation and serialization."""

    def test_agent_info_creation(self):
        """Test AgentInfo model creation."""
        now = datetime.now(timezone.utc)

        agent_info = AgentInfo(
            agent_id="test-agent-001",
            name="Test Agent",
            agent_type="testing",
            endpoint="https://test.example.com/api",
            capabilities=["test", "demo"],
            context_brief="A test agent for unit testing",
            version="1.0.0",
            owner="Test Suite",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD6F9H2J4L6M8O0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6 test-minimal-key",
            metadata={"test": True},
            communication_mode="remote",
            status="alive",
            last_seen=now,
            registered_at=now,
        )

        assert agent_info.agent_id == "test-agent-001"
        assert agent_info.status == "alive"
        assert agent_info.last_seen == now
        assert agent_info.registered_at == now

    def test_agent_info_with_metrics(self):
        """Test AgentInfo with metrics."""
        now = datetime.now(timezone.utc)

        metrics = AgentMetrics(
            agent_id="test-agent-001",
            success_rate=0.95,
            avg_response_time=1.2,
            total_requests=100,
            reputation_score=4.5,
            requests_processed=100,
            average_response_time=1.2,
            error_rate=0.05,
        )

        agent_info = AgentInfo(
            agent_id="test-agent-001",
            name="Test Agent",
            agent_type="testing",
            endpoint="https://test.example.com/api",
            capabilities=["test"],
            context_brief="Test agent for metrics validation and testing",
            version="1.0.0",
            owner="Test",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
            metadata={"test": True, "metrics": True},
            communication_mode="remote",
            status="alive",
            last_seen=now,
            registered_at=now,
            metrics=metrics,
        )

        assert agent_info.metrics is not None
        assert agent_info.metrics.success_rate == 0.95
        assert agent_info.metrics.total_requests == 100


@pytest.mark.unit
class TestAgentMetrics:
    """Test AgentMetrics model validation."""

    def test_agent_metrics_creation(self):
        """Test AgentMetrics model creation."""
        metrics = AgentMetrics(
            agent_id="test-agent-001",
            success_rate=0.98,
            avg_response_time=0.8,
            total_requests=500,
            reputation_score=4.9,
            requests_processed=500,
            average_response_time=0.8,
            error_rate=0.02,
        )

        assert metrics.agent_id == "test-agent-001"
        assert metrics.success_rate == 0.98
        assert metrics.avg_response_time == 0.8
        assert metrics.total_requests == 500
        assert metrics.error_rate == 0.02

    def test_metrics_validation_ranges(self):
        """Test that metrics values are within valid ranges."""
        # Valid metrics
        metrics = AgentMetrics(
            agent_id="test-agent",
            success_rate=0.95,  # Should be 0-1
            avg_response_time=2.5,  # Should be positive
            total_requests=100,  # Should be non-negative
            reputation_score=4.2,  # Should be 0-5
            requests_processed=100,
            average_response_time=2.5,
            error_rate=0.05,  # Should be 0-1
        )
        assert metrics.success_rate == 0.95
        assert metrics.reputation_score == 4.2


@pytest.mark.unit
class TestSearchRequest:
    """Test SearchRequest model validation."""

    def test_basic_search_request(self):
        """Test basic search request."""
        search = SearchRequest(query="test query", top_k=10)

        assert search.query == "test query"
        assert search.top_k == 10
        assert search.min_similarity == 0.5  # Default value

    def test_advanced_search_request(self):
        """Test search request with all options."""
        search = SearchRequest(
            query="advanced security scanning",
            top_k=20,
            min_similarity=0.7,
            agent_type="security",
            capabilities=["vulnerability_scan", "penetration_test"],
            weighted=True,
        )

        assert search.query == "advanced security scanning"
        assert search.top_k == 20
        assert search.min_similarity == 0.7
        assert search.agent_type == "security"
        assert search.capabilities == [
            "vulnerability_scan",
            "penetration_test",
        ]
        assert search.weighted is True

    def test_search_request_validation(self):
        """Test search request validation."""
        # Empty query should fail
        with pytest.raises(ValidationError):
            SearchRequest(query="", top_k=10)

        # Negative top_k should fail
        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_k=-1)

        # top_k too large should fail
        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_k=1000)


@pytest.mark.unit
class TestSearchResponse:
    """Test SearchResponse model."""

    def test_search_response_creation(self):
        """Test search response creation."""
        response = SearchResponse(
            id="agent-001",
            name="Test Agent",
            url="https://test.example.com/api",
            capabilities=["test", "demo"],
            version="1.0.0",
            owner="Test Owner",
            similarity=0.85,
        )

        assert response.id == "agent-001"
        assert response.name == "Test Agent"
        assert response.url == "https://test.example.com/api"
        assert response.capabilities == ["test", "demo"]
        assert response.version == "1.0.0"
        assert response.similarity == 0.85


@pytest.mark.unit
class TestAgentRequirements:
    """Test AgentRequirements model."""

    def test_basic_requirements(self):
        """Test basic requirements."""
        requirements = AgentRequirements(
            system_requirements=["linux"],
            permissions=["network"],
            dependencies=["python>=3.8"],
            minimum_memory_mb=256,
            minimum_disk_space_mb=512,
            requires_internet=True,
            network_ports=["8080"],
        )

        assert requirements.system_requirements == ["linux"]
        assert requirements.minimum_memory_mb == 256
        assert requirements.requires_internet is True

    def test_config_fields(self):
        """Test required and optional config fields."""
        required_field = RequiredConfigField(
            name="api_key",
            label="API Key",
            type="text",
            description="Secret API key for authentication",
        )

        optional_field = OptionalConfigField(
            name="timeout",
            label="Request Timeout",
            type="number",
            default_value=30,
            options=None,
        )

        requirements = AgentRequirements(
            system_requirements=[],
            permissions=[],
            dependencies=[],
            minimum_memory_mb=128,
            minimum_disk_space_mb=256,
            requires_internet=False,
            network_ports=[],
            required_fields=[required_field],
            optional_fields=[optional_field],
        )

        assert len(requirements.required_fields) == 1
        assert len(requirements.optional_fields) == 1
        assert requirements.required_fields[0].name == "api_key"
        assert requirements.optional_fields[0].default_value == 30


@pytest.mark.unit
class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_agent_registration_json_roundtrip(self):
        """Test AgentRegistration JSON serialization roundtrip."""
        original = AgentRegistration(
            name="JSON Test Agent",
            agent_id="json-test-001",
            agent_type="testing",
            endpoint="https://json-test.example.com/api",
            context_brief="Agent for JSON serialization testing",
            capabilities=["json_processing", "serialization"],
            owner="JSON Test Suite",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD9I2K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G6 json-test-key",
            metadata={
                "json_test": True,
                "version": 1,
                "test": True,
                "validation": True,
            },
            version="1.0.0",
            communication_mode="remote",
        )

        # Convert to JSON and back
        json_data = original.dict()
        reconstructed = AgentRegistration(**json_data)

        assert reconstructed.name == original.name
        assert reconstructed.agent_id == original.agent_id
        assert reconstructed.capabilities == original.capabilities
        assert reconstructed.metadata == original.metadata

    def test_agent_info_json_roundtrip(self):
        """Test AgentInfo JSON serialization roundtrip."""
        now = datetime.now(timezone.utc)

        original = AgentInfo(
            agent_id="json-info-001",
            name="JSON Info Agent",
            agent_type="testing",
            endpoint="https://json-info.example.com/api",
            capabilities=["info_processing"],
            context_brief="Agent info JSON test",
            version="1.0.0",
            owner="Test",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 validation-key",
            metadata={"test": True},
            communication_mode="remote",
            status="alive",
            last_seen=now,
            registered_at=now,
        )

        # Convert to JSON and back
        json_data = original.dict()
        reconstructed = AgentInfo(**json_data)

        assert reconstructed.agent_id == original.agent_id
        assert reconstructed.status == original.status
        assert reconstructed.last_seen == original.last_seen
