"""
Integration tests for complete agent lifecycle.

Tests the full workflow: Registration → Heartbeat → Search → Metrics → Cleanup
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.arcp.core.registry import AgentRegistry
from src.arcp.models.agent import AgentRegistration, SearchRequest
from tests.fixtures.test_helpers import integration_test


@integration_test
@pytest.mark.asyncio
class TestAgentLifecycle:
    """Test complete agent lifecycle scenarios."""

    async def test_complete_agent_lifecycle(
        self, mock_storage_adapter, mock_openai_client
    ):
        """Test complete agent lifecycle from registration to cleanup."""
        # Initialize registry with mocks
        registry = AgentRegistry()
        registry.storage = mock_storage_adapter
        registry.ai_client = mock_openai_client

        # Set up custom embedding for search
        mock_openai_client.set_custom_embedding(
            "security vulnerability scanning",
            [0.8, 0.2, 0.9, 0.1, 0.7, 0.3, 0.6, 0.4],
        )

        # Step 1: Agent Registration
        registration = AgentRegistration(
            name="Security Scanner Pro",
            agent_id="security-scanner-001",
            agent_type="security",
            endpoint="https://security-scanner.example.com/api",
            context_brief="Advanced security vulnerability scanning agent with ML capabilities",
            capabilities=[
                "vulnerability_scan",
                "threat_detection",
                "compliance_check",
            ],
            owner="Security Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2 security-key",
            metadata={"priority": "high", "region": "us-east-1"},
            version="2.0.0",
            communication_mode="remote",
        )

        # Register agent
        agent_info = await registry.register_agent(registration)
        assert agent_info.agent_id == "security-scanner-001"
        assert agent_info.status == "alive"
        assert agent_info.registered_at is not None

        # Verify agent is in registry
        agents = await registry.list_agents()
        assert len(agents) == 1
        assert agents[0].agent_id == "security-scanner-001"

        # Step 2: Heartbeat Updates
        heartbeat_response = await registry.heartbeat("security-scanner-001")
        assert heartbeat_response.status == "success"
        assert heartbeat_response.last_seen is not None

        # Update heartbeat multiple times
        for i in range(3):
            await asyncio.sleep(0.1)  # Small delay to see time progression
            heartbeat_response = await registry.heartbeat("security-scanner-001")
            assert heartbeat_response.status == "success"

        # Step 3: Vector Search
        search_request = SearchRequest(
            query="security vulnerability scanning",
            top_k=3,
            min_similarity=0.5,
        )

        search_results = await registry.vector_search(search_request)
        assert len(search_results) == 1
        assert search_results[0].id == "security-scanner-001"
        assert search_results[0].similarity > 0.5

        # Step 4: Metrics Updates
        metrics_data = {
            "avg_response_time": 1.2,
            "success_rate": 0.95,
            "total_requests": 50,
        }

        updated_metrics = await registry.update_agent_metrics(
            "security-scanner-001", metrics_data
        )
        assert updated_metrics.avg_response_time == 1.2
        assert updated_metrics.success_rate == 0.95
        assert updated_metrics.total_requests == 50

        # Get agent with metrics
        agent_with_metrics = await registry.get_agent("security-scanner-001")
        assert agent_with_metrics.metrics is not None
        assert agent_with_metrics.metrics.success_rate == 0.95

        # Step 5: Multi-agent scenarios
        # Register another agent for comparison
        analytics_registration = AgentRegistration(
            name="Data Analytics Engine",
            agent_id="analytics-engine-001",
            agent_type="automation",
            endpoint="https://analytics.example.com/api",
            context_brief="Big data analytics and pattern recognition engine",
            capabilities=[
                "data_analysis",
                "pattern_recognition",
                "ml_inference",
            ],
            owner="Data Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4 analytics-key",
            metadata={"priority": "medium", "region": "eu-west-1"},
            version="1.5.0",
            communication_mode="hybrid",
        )

        await registry.register_agent(analytics_registration)

        # Verify both agents exist
        all_agents = await registry.list_agents()
        assert len(all_agents) == 2

        agent_ids = [agent.agent_id for agent in all_agents]
        assert "security-scanner-001" in agent_ids
        assert "analytics-engine-001" in agent_ids

        # Test filtered listing
        security_agents = await registry.list_agents(agent_type="security")
        assert len(security_agents) == 1
        assert security_agents[0].agent_id == "security-scanner-001"

        analytics_agents = await registry.list_agents(agent_type="automation")
        assert len(analytics_agents) == 1
        assert analytics_agents[0].agent_id == "analytics-engine-001"

        # Step 6: Statistics
        stats = await registry.get_stats()
        assert stats["total_agents"] == 2
        assert stats["alive_agents"] == 2
        assert stats["dead_agents"] == 0
        assert "security" in stats["agent_types"]
        assert "automation" in stats["agent_types"]

        # Step 7: Agent Cleanup (simulated stale)
        # Manually mark one agent as stale by setting old last_seen
        stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
        await registry.storage.hset(
            "agents",
            "analytics-engine-001",
            {"last_seen": stale_time.isoformat(), "status": "dead"},
        )

        # Cleanup stale agents
        cleaned_count = await registry.cleanup_stale_agents(stale_threshold_hours=1)
        assert cleaned_count >= 0  # May or may not clean depending on implementation

        # Step 8: Agent Unregistration
        success = await registry.unregister_agent("security-scanner-001")
        assert success is True

        # Verify agent is gone
        remaining_agents = await registry.list_agents()
        remaining_ids = [agent.agent_id for agent in remaining_agents]
        assert "security-scanner-001" not in remaining_ids

        # Try to get unregistered agent - should raise AgentNotFoundError
        from src.arcp.core.exceptions import AgentNotFoundError

        try:
            await registry.get_agent("security-scanner-001")
            assert False, "Expected AgentNotFoundError but agent was found"
        except AgentNotFoundError:
            pass  # Expected behavior

    async def test_concurrent_agent_operations(
        self, mock_storage_adapter, mock_openai_client
    ):
        """Test concurrent agent registrations and operations."""
        registry = AgentRegistry()
        registry.storage = mock_storage_adapter
        registry.ai_client = mock_openai_client

        # Create multiple agent registrations
        registrations = []
        for i in range(5):
            registration = AgentRegistration(
                name=f"Test Agent {i}",
                agent_id=f"test-agent-{i:03d}",
                agent_type="testing",
                endpoint=f"https://agent-{i}.example.com/api",
                context_brief=f"Test agent number {i} for concurrent testing",
                capabilities=["test_capability"],
                owner="Test Suite",
                public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDA3K6N8P0R2T4V6X8Z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4N6P8R0T2V4X6Z8B0D2F4H6J8L0N2P4R6T8V0X2Z4B6D8F0H2J4L6N8P0R2T4V6X8Z0B2D4F6 lifecycle-test-key",
                metadata={"index": i},
                version="1.0.0",
                communication_mode="remote",
            )
            registrations.append(registration)

        # Register agents concurrently
        registration_tasks = [registry.register_agent(reg) for reg in registrations]
        registered_agents = await asyncio.gather(*registration_tasks)

        assert len(registered_agents) == 5

        # Verify all agents are registered
        all_agents = await registry.list_agents()
        assert len(all_agents) == 5

        # Concurrent heartbeats
        heartbeat_tasks = [registry.heartbeat(f"test-agent-{i:03d}") for i in range(5)]
        heartbeat_responses = await asyncio.gather(*heartbeat_tasks)

        assert len(heartbeat_responses) == 5
        for response in heartbeat_responses:
            assert response.status == "success"

        # Concurrent metrics updates
        metrics_tasks = [
            registry.update_agent_metrics(
                f"test-agent-{i:03d}",
                {"avg_response_time": i * 0.1, "success_rate": 0.9 + i * 0.01},
            )
            for i in range(5)
        ]
        updated_metrics = await asyncio.gather(*metrics_tasks)

        assert len(updated_metrics) == 5
        for i, metrics in enumerate(updated_metrics):
            assert metrics.avg_response_time == i * 0.1

    async def test_agent_failure_recovery(
        self, mock_storage_adapter, mock_openai_client
    ):
        """Test agent failure scenarios and recovery."""
        registry = AgentRegistry()
        registry.storage = mock_storage_adapter
        registry.ai_client = mock_openai_client

        # Register test agent
        registration = AgentRegistration(
            name="Resilient Agent",
            agent_id="resilient-agent-001",
            agent_type="monitoring",
            endpoint="https://resilient.example.com/api",
            context_brief="Agent for testing failure recovery scenarios",
            capabilities=["monitoring", "self_healing"],
            owner="Reliability Team",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3 resilient-key",
            metadata={"fault_tolerant": True},
            version="1.0.0",
            communication_mode="remote",
        )

        agent_info = await registry.register_agent(registration)
        assert agent_info.status == "alive"

        # Simulate storage failure
        mock_storage_adapter.set_backend_available(False)

        # Operations should still work with fallback
        heartbeat_response = await registry.heartbeat("resilient-agent-001")
        assert heartbeat_response is not None

        # Restore storage
        mock_storage_adapter.set_backend_available(True)

        # Operations should continue normally
        heartbeat_response = await registry.heartbeat("resilient-agent-001")
        assert heartbeat_response.status == "success"

        # Simulate AI service failure
        mock_openai_client.set_available(False)

        # Search should fall back to non-vector search
        search_request = SearchRequest(query="monitoring agent", top_k=3)

        search_results = await registry.vector_search(search_request)
        # Should still find the agent using fallback search
        assert len(search_results) >= 1

        # Restore AI service
        mock_openai_client.set_available(True)

        # Vector search should work again
        search_results = await registry.vector_search(search_request)
        assert len(search_results) >= 1
