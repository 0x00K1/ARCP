"""Integration test for agent key validation end-to-end flow."""

import hashlib

import pytest

from src.arcp.core.registry import AgentRegistry
from src.arcp.models.agent import AgentRegistration
from tests.fixtures.test_helpers import integration_test


@integration_test
@pytest.mark.asyncio
class TestAgentKeyIntegration:
    """Test agent key validation in complete integration scenario."""

    async def test_agent_key_validation_integration(
        self, mock_storage_adapter, mock_openai_client
    ):
        """Test agent key validation prevents duplicate registrations."""
        # Initialize registry with mocks
        registry = AgentRegistry()
        registry.storage = mock_storage_adapter
        registry.ai_client = mock_openai_client

        # Test data
        agent_key_hash = hashlib.sha256("test-agent-key".encode()).hexdigest()

        # Step 1: Register first agent with agent key
        registration1 = AgentRegistration(
            name="Demo Agent 1",
            agent_id="demo-agent-001",
            agent_type="testing",
            endpoint="https://demo1.example.com/api",
            context_brief="First demo agent for testing",
            capabilities=["test"],
            owner="Test Owner 1",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2 test-key-1",
            metadata={"test": True},
            version="1.0.0",
            communication_mode="remote",
        )

        agent_info1 = await registry.register_agent(
            registration1, agent_key_hash=agent_key_hash
        )
        assert agent_info1 is not None
        assert agent_info1.agent_id == "demo-agent-001"

        # Verify agent key mapping was stored
        stored_agent_id = await registry.get_agent_by_key(agent_key_hash)
        assert stored_agent_id == "demo-agent-001"

        # Step 2: Try to register different agent with same key - should fail
        registration2 = AgentRegistration(
            name="Demo Agent 2",
            agent_id="demo-agent-002",  # Different agent ID
            agent_type="testing",
            endpoint="https://demo2.example.com/api",
            context_brief="Second demo agent for testing",
            capabilities=["test"],
            owner="Test Owner 2",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2 test-key-2",
            metadata={"test": True},
            version="1.0.0",
            communication_mode="remote",
        )

        # This should raise an exception due to key already in use
        with pytest.raises(Exception) as exc_info:
            await registry.register_agent(registration2, agent_key_hash=agent_key_hash)

        assert "Agent key is already in use" in str(exc_info.value)
        assert "demo-agent-001" in str(exc_info.value)

        # Step 3: Re-register same agent with same key - should succeed
        # First unregister, then register again (as agent is alive)
        await registry.unregister_agent("demo-agent-001")
        agent_info3 = await registry.register_agent(
            registration1, agent_key_hash=agent_key_hash
        )
        assert agent_info3 is not None
        assert agent_info3.agent_id == "demo-agent-001"

        # Step 4: Unregister agent and verify key mapping cleanup
        await registry.unregister_agent("demo-agent-001")

        # Verify key mapping was cleaned up
        stored_agent_id_after_cleanup = await registry.get_agent_by_key(agent_key_hash)
        assert stored_agent_id_after_cleanup is None

        # Step 5: Now register second agent with same key - should succeed
        agent_info4 = await registry.register_agent(
            registration2, agent_key_hash=agent_key_hash
        )
        assert agent_info4 is not None
        assert agent_info4.agent_id == "demo-agent-002"

    async def test_backward_compatibility_without_agent_key(
        self, mock_storage_adapter, mock_openai_client
    ):
        """Test that agents can still register without agent keys (backward compatibility)."""
        # Initialize registry with mocks
        registry = AgentRegistry()
        registry.storage = mock_storage_adapter
        registry.ai_client = mock_openai_client

        # Register agent without agent key
        registration = AgentRegistration(
            name="Legacy Agent",
            agent_id="legacy-agent-001",
            agent_type="automation",  # Use a valid agent type
            endpoint="https://legacy.example.com/api",
            context_brief="Legacy agent without key validation",
            capabilities=["legacy"],
            owner="Legacy Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2 legacy-key",
            metadata={"legacy": True},
            version="1.0.0",
            communication_mode="remote",
        )

        # Should succeed without agent_key_hash parameter
        agent_info = await registry.register_agent(registration)
        assert agent_info is not None
        assert agent_info.agent_id == "legacy-agent-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    print("Integration test completed successfully!")
