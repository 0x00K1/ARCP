"""
Unit tests for AgentRegistry class.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from arcp.core.exceptions import AgentNotFoundError
from arcp.core.registry import AgentRegistry
from arcp.models.agent import AgentRegistration, SearchRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRegistry:
    """Test cases for AgentRegistry class."""

    async def test_registry_singleton(self):
        """Test that AgentRegistry is a singleton."""
        # Reset singleton
        AgentRegistry._instance = None

        registry1 = AgentRegistry()
        registry2 = AgentRegistry()

        assert registry1 is registry2
        assert id(registry1) == id(registry2)

    async def test_agent_registration_success(self, registry, sample_agent_request):
        """Test successful agent registration."""
        agent_info = await registry.register_agent(sample_agent_request)

        assert agent_info.agent_id == sample_agent_request.agent_id
        assert agent_info.name == sample_agent_request.name
        assert agent_info.agent_type == sample_agent_request.agent_type
        assert agent_info.endpoint == sample_agent_request.endpoint
        assert agent_info.capabilities == sample_agent_request.capabilities
        assert agent_info.status == "alive"
        assert isinstance(agent_info.registered_at, datetime)
        assert isinstance(agent_info.last_seen, datetime)

    async def test_agent_registration_duplicate_id(
        self, registry, sample_agent_request
    ):
        """Test registration with duplicate agent ID."""
        # Register agent first time
        await registry.register_agent(sample_agent_request)

        # Mark existing agent as dead by aging last_seen far beyond heartbeat timeout
        existing = await registry.get_agent_data(sample_agent_request.agent_id)
        existing["last_seen"] = datetime.now() - timedelta(hours=1)
        await registry.store_agent_data(sample_agent_request.agent_id, existing)

        # Try to register same agent again (should pass because existing is dead)
        agent_info = await registry.register_agent(sample_agent_request)

        # Should update existing agent
        assert agent_info.agent_id == sample_agent_request.agent_id
        assert isinstance(agent_info.last_seen, datetime)

    async def test_agent_registration_invalid_endpoint(self, registry):
        """Test registration with invalid endpoint."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentRegistration(
                agent_id="test-agent",
                agent_type="testing",
                endpoint="invalid-url",  # Invalid URL
                capabilities=["test"],
            )

    async def test_agent_list_empty(self, registry):
        """Test listing agents when registry is empty."""
        agents = await registry.list_agents()
        assert agents == []

    async def test_agent_list_with_agents(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test listing agents with populated registry."""
        agents = await populated_registry.list_agents()

        assert len(agents) == len(multiple_agent_registrations)
        agent_ids = [agent.agent_id for agent in agents]
        expected_ids = [agent.agent_id for agent in multiple_agent_registrations]

        for expected_id in expected_ids:
            assert expected_id in agent_ids

    async def test_agent_list_with_type_filter(self, populated_registry):
        """Test listing agents with type filter."""
        agents = await populated_registry.list_agents(agent_type="security")

        assert len(agents) == 1  # One security agent
        for agent in agents:
            assert agent.agent_type == "security"

    async def test_agent_list_with_capabilities_filter(self, populated_registry):
        """Test listing agents with capabilities filter."""
        agents = await populated_registry.list_agents(capabilities=["alerting"])

        assert len(agents) == 1  # One agent with alerting capability
        for agent in agents:
            assert "alerting" in agent.capabilities

    async def test_agent_list_with_status_filter(self, populated_registry):
        """Test listing agents with status filter."""
        agents = await populated_registry.list_agents(status="alive")

        assert len(agents) == 3  # All agents are alive
        for agent in agents:
            assert agent.status == "alive"

    async def test_get_agent_success(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test getting specific agent by ID."""
        agent_id = multiple_agent_registrations[0].agent_id
        agent = await populated_registry.get_agent(agent_id)

        assert agent.agent_id == agent_id
        assert agent.name == multiple_agent_registrations[0].name
        assert agent.agent_type == multiple_agent_registrations[0].agent_type

    async def test_get_agent_not_found(self, registry):
        """Test getting non-existent agent."""
        with pytest.raises(AgentNotFoundError):
            await registry.get_agent("non-existent-agent")

    async def test_unregister_agent_success(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test removing agent successfully."""
        agent_id = multiple_agent_registrations[0].agent_id

        # Verify agent exists
        agent = await populated_registry.get_agent(agent_id)
        assert agent is not None

        # Remove agent
        await populated_registry.unregister_agent(agent_id)

        # Verify agent is removed
        with pytest.raises(AgentNotFoundError):
            await populated_registry.get_agent(agent_id)

    async def test_unregister_agent_not_found(self, registry):
        """Test removing non-existent agent."""
        with pytest.raises(AgentNotFoundError):
            await registry.unregister_agent("non-existent-agent")

    async def test_heartbeat_success(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test successful heartbeat update."""
        agent_id = multiple_agent_registrations[0].agent_id

        # Get original last_seen timestamp
        original_agent = await populated_registry.get_agent(agent_id)
        original_last_seen = original_agent.last_seen

        # Wait a bit to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Send heartbeat
        response = await populated_registry.heartbeat(agent_id)

        assert response.status == "success"
        assert response.agent_id == agent_id
        assert response.last_seen > original_last_seen

    async def test_heartbeat_not_found(self, registry):
        """Test heartbeat for non-existent agent."""
        with pytest.raises(AgentNotFoundError):
            await registry.heartbeat("non-existent-agent")

    async def test_update_agent_metrics(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test updating agent metrics."""
        agent_id = multiple_agent_registrations[0].agent_id

        # Update metrics
        await populated_registry.update_agent_metrics(
            agent_id,
            {
                "requests_processed": 100,
                "average_response_time": 0.5,
                "error_rate": 0.01,
            },
        )

        # Get updated metrics
        metrics = await populated_registry.get_agent_metrics(agent_id)

        assert metrics is not None
        assert metrics.requests_processed == 100
        assert metrics.average_response_time == 0.5
        assert metrics.error_rate == 0.01

    async def test_cleanup_stale_agents(
        self, populated_registry, multiple_agent_registrations
    ):
        """Test cleanup of stale agents."""
        agent_id = multiple_agent_registrations[0].agent_id

        # Manually set last_seen to old timestamp
        agent_data = await populated_registry.get_agent_data(agent_id)
        agent_data["last_seen"] = datetime.utcnow() - timedelta(hours=2)
        await populated_registry.store_agent_data(agent_id, agent_data)

        # Run cleanup
        cleanup_count = await populated_registry.cleanup_stale_agents()

        assert cleanup_count == 1

        # Verify agent is removed
        with pytest.raises(AgentNotFoundError):
            await populated_registry.get_agent(agent_id)

    async def test_vector_search_without_ai_client(self, populated_registry):
        """Test vector search without AI client."""
        populated_registry.openai_service.is_available = MagicMock(return_value=False)

        search_request = SearchRequest(query="test agent", top_k=5, min_similarity=0.5)

        results = await populated_registry.vector_search(search_request)

        # Should return empty results without AI client
        assert results == []

    @patch("arcp.core.registry.AgentRegistry.embed_text")
    async def test_vector_search_with_ai_client(
        self, mock_embed, populated_registry, vector_embeddings
    ):
        """Test vector search with AI client."""
        # Create a mock OpenAI service
        from unittest.mock import MagicMock

        mock_openai_service = MagicMock()
        mock_openai_service.is_available.return_value = True

        # Mock embedding generation (8 dimensions to match fixture embeddings)
        # Use a vector similar to security-scanner-001 to ensure high similarity
        mock_embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

        # Store embeddings for agents
        for agent_id, embedding in vector_embeddings.items():
            await populated_registry.store_embedding(agent_id, embedding)

        # Update agent timestamps to ensure they're considered alive
        from datetime import datetime

        current_time = datetime.now()  # Use offset-naive datetime to match cutoff
        all_agents = await populated_registry.get_all_agent_data()
        for agent_id, agent_data in all_agents.items():
            agent_data["last_seen"] = current_time.isoformat()
            await populated_registry.store_agent_data(agent_id, agent_data)

        # Verify embeddings were stored
        all_embeddings = await populated_registry.get_all_embeddings()
        assert (
            len(all_embeddings) > 0
        ), f"No embeddings found, expected {len(vector_embeddings)}"

        # Mock the registry's openai_service directly
        populated_registry.openai_service = mock_openai_service

        search_request = SearchRequest(query="test agent", top_k=5, min_similarity=0.5)

        results = await populated_registry.vector_search(search_request)

        assert len(results) > 0
        assert all(hasattr(result, "similarity") for result in results)
        assert all(
            result.similarity >= search_request.min_similarity for result in results
        )

    async def test_embedding_generation(self, registry):
        """Test embedding generation."""
        if not registry.openai_service.is_available():
            pytest.skip("AI client not available")

        text = "test agent for embedding"
        embedding = registry.embed_text(text)

        assert isinstance(embedding, list)
        assert len(embedding) == 5  # Mock embedding size
        assert all(isinstance(x, float) for x in embedding)

    async def test_cosine_similarity(self, registry):
        """Test cosine similarity calculation."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        vec3 = [1.0, 0.0, 0.0]

        # Orthogonal vectors should have similarity 0
        similarity_orthogonal = registry.cosine_similarity(vec1, vec2)
        assert abs(similarity_orthogonal - 0.0) < 1e-10

        # Identical vectors should have similarity 1
        similarity_identical = registry.cosine_similarity(vec1, vec3)
        assert abs(similarity_identical - 1.0) < 1e-10

    async def test_storage_operations(self, registry):
        """Test storage operations."""
        key = "test_key"
        value = {"test": "data"}

        # Store data
        await registry.storage.set("test_bucket", key, value)

        # Retrieve data
        retrieved = await registry.storage.get("test_bucket", key)
        assert retrieved == value

        # Check existence
        exists = await registry.storage.exists("test_bucket", key)
        assert exists is True

        # Delete data
        await registry.storage.delete("test_bucket", key)

        # Verify deletion
        exists = await registry.storage.exists("test_bucket", key)
        assert exists is False

    async def test_callback_registration(self, registry):
        """Test callback registration and execution."""
        callback_called = False

        async def test_callback(data):
            nonlocal callback_called
            callback_called = True

        # Register callback
        registry.on_update_callbacks.append(test_callback)

        # Trigger update (register an agent)
        request = AgentRegistration(
            agent_id="callback-test",
            name="Callback Test Agent",
            agent_type="testing",
            endpoint="http://localhost:8080",
            context_brief="Agent for testing callbacks",
            capabilities=["test"],
            owner="test-owner",
            public_key="test-key-callback-abcdefghijklmnopqrstuvwxyz123456789",
            metadata={"test": True},
            version="1.0.0",
            communication_mode="remote",
        )

        await registry.register_agent(request)

        # Wait for callback execution
        await asyncio.sleep(0.1)

        # Clean up
        registry.on_update_callbacks.remove(test_callback)

    async def test_error_handling(self, registry):
        """Test error handling in registry operations."""
        # Test with invalid agent data
        with pytest.raises(Exception):
            await registry.register_agent(None)

        # Test with invalid search request
        with pytest.raises(Exception):
            await registry.vector_search(None)

    async def test_concurrent_operations(self, registry):
        """Test concurrent registry operations."""
        # Create multiple agents concurrently
        tasks = []
        for i in range(10):
            request = AgentRegistration(
                agent_id=f"concurrent-agent-{i}",
                name=f"Concurrent Agent {i}",
                agent_type="testing",
                endpoint=f"http://localhost:808{i}",
                context_brief=f"Concurrent test agent {i}",
                capabilities=["concurrent"],
                owner="test-owner",
                public_key=f"concurrent-key-{i}-abcdefghijklmnopqrstuvwxyz123456789",
                metadata={"concurrent": True, "index": i},
                version="1.0.0",
                communication_mode="remote",
            )
            tasks.append(registry.register_agent(request))

        # Wait for all registrations
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all succeeded
        assert len(results) == 10
        assert all(not isinstance(result, Exception) for result in results)

        # Verify agents are registered
        agents = await registry.list_agents(agent_type="testing")
        # Filter for our concurrent agents specifically
        concurrent_agents = [
            agent for agent in agents if "concurrent-agent" in agent.agent_id
        ]
        assert len(concurrent_agents) == 10
