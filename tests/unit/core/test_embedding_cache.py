"""Test embedding cache optimization during agent registration and re-registration."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from arcp.core.registry import AgentRegistry
from arcp.models.agent import AgentRegistration


@pytest.mark.unit
@pytest.mark.asyncio
class TestEmbeddingCache:
    """Test embedding cache functionality to avoid unnecessary OpenAI API calls."""

    async def test_embedding_not_regenerated_on_reregistration_with_same_info(self):
        """
        Test that embedding is NOT regenerated when an agent re-registers
        with the exact same information.

        This test verifies the fix for the issue where agents would call OpenAI
        API unnecessarily on re-registration even when their info hasn't changed.
        """
        # Reset singleton to get a clean registry
        AgentRegistry._instance = None
        registry = AgentRegistry()

        # Setup mock OpenAI service
        mock_openai_service = MagicMock()
        mock_openai_service.is_available.return_value = True
        registry.openai_service = mock_openai_service

        # Clear any existing data for this agent ID
        test_agent_id = "embedding-cache-test-001"
        await registry.storage.hdel("agent:data", test_agent_id)
        await registry.storage.hdel("agent:embeddings", test_agent_id)
        await registry.storage.hdel("agent:info_hashes", test_agent_id)
        await registry.storage.hdel("agent:metrics", test_agent_id)

        # Create agent registration data
        agent_key = "test-embedding-cache-key"
        agent_key_hash = hashlib.sha256(agent_key.encode()).hexdigest()

        agent_registration = AgentRegistration(
            name="Test Agent Embedding Cache",
            agent_id="embedding-cache-test-001",
            agent_type="testing",
            endpoint="https://test-embedding.example.com/api",
            context_brief="A test agent for embedding cache validation",
            capabilities=["test", "cache"],
            owner="Test Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 embedding-cache-test",
            metadata={"test": True, "cache": "enabled"},
            version="1.0.0",
            communication_mode="remote",
        )

        try:
            # Mock the embed_text method to track calls
            embedding_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
            with patch.object(
                registry, "embed_text", return_value=embedding_vector
            ) as mock_embed:

                # STEP 1: Register agent for the first time
                result1 = await registry.register_agent(
                    agent_registration, agent_key_hash=agent_key_hash
                )
                assert result1.agent_id == "embedding-cache-test-001"

                # Verify embed_text was called once during initial registration
                assert (
                    mock_embed.call_count == 1
                ), "Embedding should be generated on first registration"
                first_call_count = mock_embed.call_count

                # Verify the hash was stored
                stored_hash1 = await registry.storage.hget(
                    "agent:info_hashes", "embedding-cache-test-001"
                )
                assert (
                    stored_hash1 is not None
                ), "Info hash should be stored after registration"

                # STEP 2: Unregister the agent
                success = await registry.unregister_agent("embedding-cache-test-001")
                assert success, "Agent should be unregistered successfully"

                # CRITICAL: Verify the info_hash is PRESERVED after unregistration
                stored_hash2 = await registry.storage.hget(
                    "agent:info_hashes", "embedding-cache-test-001"
                )
                assert (
                    stored_hash2 is not None
                ), "Info hash should be PRESERVED after unregistration"
                assert stored_hash1 == stored_hash2, "Info hash should remain unchanged"

                # STEP 3: Re-register the SAME agent with IDENTICAL information
                result2 = await registry.register_agent(
                    agent_registration, agent_key_hash=agent_key_hash
                )
                assert result2.agent_id == "embedding-cache-test-001"

                # CRITICAL: Verify embed_text was NOT called again (embedding was cached)
                assert mock_embed.call_count == first_call_count, (
                    f"Embedding should NOT be regenerated on re-registration with same info. "
                    f"Expected {first_call_count} calls, got {mock_embed.call_count}"
                )

                # Verify the hash is still the same
                stored_hash3 = await registry.storage.hget(
                    "agent:info_hashes", "embedding-cache-test-001"
                )
                assert stored_hash3 == stored_hash1, "Info hash should remain the same"

        finally:
            # Clean up
            try:
                await registry.unregister_agent("embedding-cache-test-001")
            except Exception:
                pass

    async def test_embedding_regenerated_on_reregistration_with_changed_info(self):
        """
        Test that embedding IS regenerated when an agent re-registers
        with DIFFERENT information.
        """
        # Reset singleton to get a clean registry
        AgentRegistry._instance = None
        registry = AgentRegistry()

        # Setup mock OpenAI service
        mock_openai_service = MagicMock()
        mock_openai_service.is_available.return_value = True
        registry.openai_service = mock_openai_service

        # Clear any existing data for this agent ID
        test_agent_id = "embedding-change-test-001"
        await registry.storage.hdel("agent:data", test_agent_id)
        await registry.storage.hdel("agent:embeddings", test_agent_id)
        await registry.storage.hdel("agent:info_hashes", test_agent_id)
        await registry.storage.hdel("agent:metrics", test_agent_id)

        # Create agent registration data
        agent_key = "test-embedding-change-key"
        agent_key_hash = hashlib.sha256(agent_key.encode()).hexdigest()

        agent_registration_v1 = AgentRegistration(
            name="Test Agent Version 1",
            agent_id="embedding-change-test-001",
            agent_type="testing",
            endpoint="https://test-embedding-v1.example.com/api",
            context_brief="Version 1 of test agent",
            capabilities=["test", "v1"],
            owner="Test Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 embedding-change-test",
            metadata={"test": True, "version": 1},
            version="1.0.0",
            communication_mode="remote",
        )

        agent_registration_v2 = AgentRegistration(
            name="Test Agent Version 2",  # CHANGED
            agent_id="embedding-change-test-001",
            agent_type="testing",
            endpoint="https://test-embedding-v2.example.com/api",
            context_brief="Version 2 of test agent with new capabilities",  # CHANGED
            capabilities=["test", "v2", "enhanced"],  # CHANGED
            owner="Test Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 embedding-change-test",
            metadata={"test": True, "version": 2},  # CHANGED
            version="2.0.0",
            communication_mode="remote",
        )

        try:
            # Mock the embed_text method to track calls
            embedding_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
            with patch.object(
                registry, "embed_text", return_value=embedding_vector
            ) as mock_embed:

                # STEP 1: Register agent version 1
                result1 = await registry.register_agent(
                    agent_registration_v1, agent_key_hash=agent_key_hash
                )
                assert result1.agent_id == "embedding-change-test-001"

                # Verify embed_text was called once
                assert mock_embed.call_count == 1
                first_call_count = mock_embed.call_count

                # Get the first hash
                stored_hash1 = await registry.storage.hget(
                    "agent:info_hashes", "embedding-change-test-001"
                )
                assert stored_hash1 is not None

                # STEP 2: Unregister the agent
                success = await registry.unregister_agent("embedding-change-test-001")
                assert success

                # STEP 3: Re-register with DIFFERENT information (version 2)
                result2 = await registry.register_agent(
                    agent_registration_v2, agent_key_hash=agent_key_hash
                )
                assert result2.agent_id == "embedding-change-test-001"

                # CRITICAL: Verify embed_text WAS called again (info changed)
                assert mock_embed.call_count == first_call_count + 1, (
                    f"Embedding SHOULD be regenerated when agent info changes. "
                    f"Expected {first_call_count + 1} calls, got {mock_embed.call_count}"
                )

                # Verify the hash is different
                stored_hash2 = await registry.storage.hget(
                    "agent:info_hashes", "embedding-change-test-001"
                )
                assert (
                    stored_hash2 != stored_hash1
                ), "Info hash should change when agent info changes"

        finally:
            # Clean up
            try:
                await registry.unregister_agent("embedding-change-test-001")
            except Exception:
                pass

    async def test_info_hash_preserved_across_unregister(self):
        """
        Test that info_hash is preserved when an agent is unregistered,
        enabling embedding cache reuse on re-registration.
        """
        # Reset singleton to get a clean registry
        AgentRegistry._instance = None
        registry = AgentRegistry()

        # Clear any existing data for this agent ID
        test_agent_id = "hash-preserve-test-001"
        await registry.storage.hdel("agent:data", test_agent_id)
        await registry.storage.hdel("agent:embeddings", test_agent_id)
        await registry.storage.hdel("agent:info_hashes", test_agent_id)
        await registry.storage.hdel("agent:metrics", test_agent_id)

        # Setup mock OpenAI service to enable embedding generation
        from unittest.mock import MagicMock, patch

        mock_openai_service = MagicMock()
        mock_openai_service.is_available.return_value = True
        registry.openai_service = mock_openai_service

        agent_registration = AgentRegistration(
            name="Test Hash Preservation",
            agent_id="hash-preserve-test-001",
            agent_type="testing",
            endpoint="https://test-hash.example.com/api",
            context_brief="Testing hash preservation",
            capabilities=["test"],
            owner="Test Owner",
            public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD7G0I3K5M7O9Q1S3U5W7Y9A1C3E5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5G7I9K1M3O5Q7S9U1W3Y5A7C9E1G3I5K7M9O1Q3S5U7W9Y1A3C5E7G9I1K3M5O7Q9S1U3W5Y7A9C1E3G5 hash-test",
            metadata={"test": True},
            version="1.0.0",
            communication_mode="remote",
        )

        try:
            # Mock embed_text to return a test embedding
            embedding_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
            with patch.object(registry, "embed_text", return_value=embedding_vector):
                # Register agent (with embedding)
                await registry.register_agent(agent_registration)

            # Get the stored hash and embedding
            hash_before_unregister = await registry.storage.hget(
                "agent:info_hashes", "hash-preserve-test-001"
            )
            assert (
                hash_before_unregister is not None
            ), "Hash should exist after registration"

            embedding_before = await registry.get_embedding("hash-preserve-test-001")
            assert (
                embedding_before is not None
            ), "Embedding should exist after registration"

            # Unregister agent
            await registry.unregister_agent("hash-preserve-test-001")

            # Verify hash is STILL there
            hash_after_unregister = await registry.storage.hget(
                "agent:info_hashes", "hash-preserve-test-001"
            )
            assert (
                hash_after_unregister is not None
            ), "Hash should be preserved after unregistration to enable cache reuse"
            assert (
                hash_after_unregister == hash_before_unregister
            ), "Hash value should remain unchanged after unregistration"

            # Verify embedding is ALSO preserved (for complete cache reuse)
            embedding_after = await registry.get_embedding("hash-preserve-test-001")
            assert (
                embedding_after is not None
            ), "Embedding should be preserved on unregister for cache reuse"
            assert (
                embedding_after == embedding_before
            ), "Embedding should remain unchanged"

            # Verify agent data WAS deleted (only cache data preserved)
            agent_data = await registry.get_agent_data("hash-preserve-test-001")
            assert agent_data is None, "Agent data should be deleted on unregister"

        finally:
            # Clean up
            try:
                await registry.unregister_agent("hash-preserve-test-001")
                # Also clean up the hash for this test
                await registry.storage.hdel(
                    "agent:info_hashes", "hash-preserve-test-001"
                )
            except Exception:
                pass


@pytest.mark.unit
@pytest.mark.asyncio
class TestEmbeddingHashGeneration:
    """Test the hash generation logic for embedding cache."""

    async def test_hash_generation_includes_relevant_fields(self):
        """Test that hash is generated from embedding-relevant fields only."""
        # Reset singleton to get a clean registry
        AgentRegistry._instance = None
        registry = AgentRegistry()

        agent_data = {
            "agent_id": "test-001",
            "name": "Test Agent",
            "context_brief": "Brief description",
            "capabilities": ["cap1", "cap2"],
            "agent_type": "testing",
            "features": ["feat1"],
            "metadata": {"key": "value"},
            # These should NOT affect the hash:
            "endpoint": "https://example.com",
            "version": "1.0.0",
            "owner": "Test Owner",
            "public_key": "key123",
            "last_seen": "2024-01-01",
        }

        hash1 = registry._get_agent_info_hash(agent_data)
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256 produces 64-char hex string

        # Change irrelevant field - hash should NOT change
        agent_data["endpoint"] = "https://different.com"
        hash2 = registry._get_agent_info_hash(agent_data)
        assert hash2 == hash1, "Hash should not change when non-embedding fields change"

        # Change relevant field - hash SHOULD change
        agent_data["name"] = "Different Name"
        hash3 = registry._get_agent_info_hash(agent_data)
        assert (
            hash3 != hash1
        ), "Hash should change when embedding-relevant fields change"

    async def test_hash_excludes_timestamp_fields(self):
        """Test that timestamp fields in metadata don't affect the hash."""
        # Reset singleton to get a clean registry
        AgentRegistry._instance = None
        registry = AgentRegistry()

        base_agent_data = {
            "agent_id": "test-001",
            "name": "Test Agent",
            "context_brief": "Brief description",
            "capabilities": ["cap1", "cap2"],
            "agent_type": "testing",
            "features": ["feat1"],
            "metadata": {
                "description": "Test description",
                "tags": ["demo", "test"],
            },
        }

        # Same data with timestamp fields added
        agent_data_with_timestamps = {
            **base_agent_data,
            "metadata": {
                **base_agent_data["metadata"],
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T11:00:00",
                "timestamp": "2024-01-01T12:00:00",
                "registered_at": "2024-01-01T13:00:00",
                "last_seen": "2024-01-01T14:00:00",
            },
        }

        # Different timestamp values
        agent_data_different_timestamps = {
            **base_agent_data,
            "metadata": {
                **base_agent_data["metadata"],
                "created_at": "2025-02-02T20:00:00",
                "updated_at": "2025-02-02T21:00:00",
                "timestamp": "2025-02-02T22:00:00",
                "registered_at": "2025-02-02T23:00:00",
                "last_seen": "2025-02-03T00:00:00",
            },
        }

        # All three should produce the same hash
        hash1 = registry._get_agent_info_hash(base_agent_data)
        hash2 = registry._get_agent_info_hash(agent_data_with_timestamps)
        hash3 = registry._get_agent_info_hash(agent_data_different_timestamps)

        assert hash1 == hash2, "Hash should be same with timestamp fields added"
        assert hash2 == hash3, "Hash should be same with different timestamp values"
        assert hash1 == hash3, "Hash should only depend on non-timestamp metadata"
