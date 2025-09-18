"""Test agent key uniqueness validation."""

import hashlib

import pytest

from arcp.core.exceptions import AgentRegistrationError
from arcp.core.registry import AgentRegistry
from arcp.models.agent import AgentRegistration


@pytest.mark.asyncio
async def test_agent_key_uniqueness():
    """Test that agent keys can only register one agent."""
    registry = AgentRegistry()

    # Test data
    agent_key = "test-agent-001"
    agent_key_hash = hashlib.sha256(agent_key.encode()).hexdigest()

    # Agent registration data
    agent1_registration = AgentRegistration(
        name="Test Agent 1",
        agent_id="demo-agent-001",
        agent_type="testing",
        endpoint="https://test1.example.com/api",
        context_brief="A test agent for validation",
        capabilities=["test"],
        owner="Test Owner 1",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 test-key-1",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )

    agent2_registration = AgentRegistration(
        name="Test Agent 2",
        agent_id="demo-agent-002",
        agent_type="testing",
        endpoint="https://test2.example.com/api",
        context_brief="Another test agent for validation",
        capabilities=["test"],
        owner="Test Owner 2",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD8H1J4L6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6H8 test-key-2",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )

    try:
        # Test 1: Register first agent with key - should succeed
        result1 = await registry.register_agent(
            agent1_registration, agent_key_hash=agent_key_hash
        )
        assert result1.agent_id == "demo-agent-001"

        # Test 2: Try to register second agent with same key - should fail
        with pytest.raises(AgentRegistrationError) as exc_info:
            await registry.register_agent(
                agent2_registration, agent_key_hash=agent_key_hash
            )

        assert "Agent key is already in use" in str(exc_info.value)
        assert "demo-agent-001" in str(exc_info.value)

        # Test 3: Verify key mapping exists
        mapped_agent = await registry.get_agent_by_key(agent_key_hash)
        assert mapped_agent == "demo-agent-001"

    finally:
        # Clean up
        try:
            await registry.unregister_agent("demo-agent-001")
        except Exception:
            pass
        try:
            await registry.unregister_agent("demo-agent-002")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_agent_key_reregistration():
    """Test that the same agent can re-register with the same key."""
    registry = AgentRegistry()

    # Test data
    agent_key = "test-agent-reregister"
    agent_key_hash = hashlib.sha256(agent_key.encode()).hexdigest()

    agent_registration = AgentRegistration(
        name="Test Agent Reregister",
        agent_id="demo-agent-reregister",
        agent_type="testing",
        endpoint="https://test-reregister.example.com/api",
        context_brief="A test agent for re-registration",
        capabilities=["test"],
        owner="Test Owner",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 test-reregister-key",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )

    try:
        # Register agent
        result1 = await registry.register_agent(
            agent_registration, agent_key_hash=agent_key_hash
        )
        assert result1.agent_id == "demo-agent-reregister"

        # Unregister agent
        success = await registry.unregister_agent("demo-agent-reregister")
        assert success

        # Verify key mapping is removed
        mapped_agent = await registry.get_agent_by_key(agent_key_hash)
        assert mapped_agent is None

        # Re-register same agent with same key - should succeed
        result2 = await registry.register_agent(
            agent_registration, agent_key_hash=agent_key_hash
        )
        assert result2.agent_id == "demo-agent-reregister"

        # Verify key mapping is restored
        mapped_agent = await registry.get_agent_by_key(agent_key_hash)
        assert mapped_agent == "demo-agent-reregister"

    finally:
        # Clean up
        try:
            await registry.unregister_agent("demo-agent-reregister")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_agent_key_cleanup_on_unregister():
    """Test that agent key mappings are cleaned up when agent is unregistered."""
    registry = AgentRegistry()

    # Test data
    agent_key = "test-agent-cleanup"
    agent_key_hash = hashlib.sha256(agent_key.encode()).hexdigest()

    agent_registration = AgentRegistration(
        name="Test Agent Cleanup",
        agent_id="demo-agent-cleanup",
        agent_type="testing",
        endpoint="https://test-cleanup.example.com/api",
        context_brief="A test agent for cleanup validation",
        capabilities=["test"],
        owner="Test Owner",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 test-cleanup-key",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )

    try:
        # Register agent
        result = await registry.register_agent(
            agent_registration, agent_key_hash=agent_key_hash
        )
        assert result.agent_id == "demo-agent-cleanup"

        # Verify key mapping exists
        mapped_agent = await registry.get_agent_by_key(agent_key_hash)
        assert mapped_agent == "demo-agent-cleanup"

        # Unregister agent
        success = await registry.unregister_agent("demo-agent-cleanup")
        assert success

        # Verify key mapping is removed
        mapped_agent = await registry.get_agent_by_key(agent_key_hash)
        assert mapped_agent is None

    finally:
        # Clean up
        try:
            await registry.unregister_agent("demo-agent-cleanup")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_agent_registration_without_key():
    """Test that agent registration works without agent key (backward compatibility)."""
    registry = AgentRegistry()

    agent_registration = AgentRegistration(
        name="Test Agent No Key",
        agent_id="demo-agent-no-key",
        agent_type="testing",
        endpoint="https://test-no-key.example.com/api",
        context_brief="A test agent without key validation",
        capabilities=["test"],
        owner="Test Owner",
        public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 test-no-key",
        metadata={"test": True},
        version="1.0.0",
        communication_mode="remote",
    )

    try:
        # Register agent without key hash - should succeed
        result = await registry.register_agent(agent_registration, agent_key_hash=None)
        assert result.agent_id == "demo-agent-no-key"

    finally:
        # Clean up
        try:
            await registry.unregister_agent("demo-agent-no-key")
        except Exception:
            pass
