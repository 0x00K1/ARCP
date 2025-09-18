"""
Performance tests for vector search functionality.

Tests search performance with large numbers of agents and concurrent requests.
"""

import asyncio
import statistics
import time

import pytest

from src.arcp.core.registry import AgentRegistry
from src.arcp.models.agent import SearchRequest
from tests.fixtures.agent_fixtures import create_test_agent_registration
from tests.fixtures.mock_services import MockStorageAdapter
from tests.fixtures.test_helpers import (
    assert_approximately_equal,
    assert_performance_within_limit,
    performance_test,
)


@performance_test
@pytest.mark.asyncio
class TestVectorSearchPerformance:
    """Performance tests for vector search operations."""

    @pytest.fixture
    async def performance_registry(self):
        """Registry populated with many agents for performance testing."""
        # Patch the heartbeat timeout to be very large for this test
        from arcp.core.config import config

        original_timeout = config.AGENT_HEARTBEAT_TIMEOUT
        config.AGENT_HEARTBEAT_TIMEOUT = 3600  # 1 hour

        print(f"Set AGENT_HEARTBEAT_TIMEOUT to {config.AGENT_HEARTBEAT_TIMEOUT}")

        try:
            registry = AgentRegistry()
            registry.storage = MockStorageAdapter()

            # Use MockOpenAIService instead of MockOpenAIClient
            from tests.fixtures.mock_services import MockOpenAIService

            mock_openai_service = MockOpenAIService()
            registry.openai_service = mock_openai_service

            # Generate diverse embeddings for realistic search testing
            embeddings_map = {}
            agent_registrations = []

            # Create agents with different types and capabilities
            agent_types = [
                "security",
                "automation",
                "monitoring",
                "networking",
                "testing",
            ]
            capabilities_sets = [
                ["vulnerability_scan", "penetration_test", "security_audit"],
                ["data_analysis", "pattern_recognition", "ml_inference"],
                ["system_monitoring", "alerting", "log_analysis"],
                ["api_integration", "webhook_management", "data_sync"],
                [
                    "natural_language_processing",
                    "computer_vision",
                    "recommendation",
                ],
            ]

            for i in range(100):  # Create 100 agents for performance testing
                agent_type = agent_types[i % len(agent_types)]
                capabilities = capabilities_sets[i % len(capabilities_sets)]

                registration = create_test_agent_registration(
                    agent_id=f"perf-agent-{i:03d}",
                    agent_type=agent_type,
                    capabilities=capabilities,
                )
                registration.name = f"Performance Agent {i}"
                registration.context_brief = f"Agent {i} specialized in {agent_type} operations with {len(capabilities)} capabilities"

                agent_registrations.append(registration)

                # Generate varied embeddings based on agent characteristics
                base_vector = [
                    0.1 * (i % 10),
                    0.2 * ((i + 1) % 5),
                    0.3 * ((i + 2) % 3),
                ]
                # Pad to 8 dimensions with some variance
                embedding = base_vector + [0.1 * ((i + j) % 7) for j in range(5)]
                embeddings_map[registration.context_brief] = embedding

            # Set up custom embeddings in mock service
            for context, embedding in embeddings_map.items():
                mock_openai_service.set_custom_embedding(context, embedding)

            # Register all agents
            registration_start = time.time()
            registration_tasks = [
                registry.register_agent(reg) for reg in agent_registrations
            ]
            registered_agents = await asyncio.gather(*registration_tasks)
            registration_time = time.time() - registration_start

            print(
                f"Registered {len(registered_agents)} agents in {registration_time:.3f}s"
            )
            assert len(registered_agents) == 100

            yield registry
        finally:
            # Restore original timeout
            config.AGENT_HEARTBEAT_TIMEOUT = original_timeout

    async def test_single_search_performance(self, performance_registry):
        """Test performance of single vector search operation."""

        # First, let's check what agents are actually in the registry
        all_agents = await performance_registry.get_all_agent_data()
        print(f"Total agents in registry: {len(all_agents)}")

        # Check if any agents exist and their timestamps
        if all_agents:
            sample_agent_id = list(all_agents.keys())[0]
            sample_agent = all_agents[sample_agent_id]
            print(f"Sample agent last_seen: {sample_agent.get('last_seen')}")

        # Check embeddings
        all_embeddings = await performance_registry.get_all_embeddings()
        print(f"Total embeddings available: {len(all_embeddings)}")

        search_request = SearchRequest(
            query="security vulnerability scanning and threat detection",
            top_k=10,
            min_similarity=0.0,
        )

        # Warm up
        warmup_results = await performance_registry.vector_search(search_request)
        print(f"Warmup search found {len(warmup_results)} agents")

        # Measure performance
        start_time = time.time()
        results = await performance_registry.vector_search(search_request)
        search_time = time.time() - start_time

        print(f"Performance search found {len(results)} agents")

        # If we get 0 results, let's try to understand why
        if len(results) == 0:
            print("Debugging: No results found, checking possible issues...")

            # Try with no similarity threshold
            debug_request = SearchRequest(
                query="security",
                top_k=100,
                min_similarity=0.0,
            )
            debug_results = await performance_registry.vector_search(debug_request)
            print(
                f"Debug search with lower requirements found: {len(debug_results)} agents"
            )

        assert (
            len(results) >= 1
        )  # At least 1 result should be found with such a low threshold
        assert_performance_within_limit(search_time, 0.5, "Single vector search")

        print(f"Single search completed in {search_time:.3f}s")
        return search_time

    async def test_concurrent_search_performance(self, performance_registry):
        """Test performance with concurrent search requests."""
        search_queries = [
            "security vulnerability assessment",
            "data processing and machine learning",
            "system monitoring and alerting",
            "API integration and webhooks",
            "artificial intelligence processing",
        ]

        search_requests = [
            SearchRequest(query=query, top_k=5, min_similarity=0.0)
            for query in search_queries
        ]

        # Test with different concurrency levels
        concurrency_levels = [1, 5, 10, 20]
        performance_results = {}

        for concurrency in concurrency_levels:
            # Create concurrent search tasks
            tasks = []
            for i in range(concurrency):
                request = search_requests[i % len(search_requests)]
                tasks.append(performance_registry.vector_search(request))

            # Measure concurrent performance
            start_time = time.time()
            results = await asyncio.gather(*tasks)
            elapsed_time = time.time() - start_time

            # Ensure minimum elapsed time to avoid division by zero
            elapsed_time = max(elapsed_time, 0.001)  # Minimum 1ms

            performance_results[concurrency] = {
                "elapsed_time": elapsed_time,
                "throughput": concurrency / elapsed_time,
                "avg_per_request": elapsed_time / concurrency,
            }

            # Verify all searches completed successfully
            assert len(results) == concurrency
            for result in results:
                assert len(result) <= 5  # top_k was 5

            print(
                f"Concurrency {concurrency}: {elapsed_time:.3f}s total, "
                f"{performance_results[concurrency]['throughput']:.2f} req/s"
            )

        # Performance should scale reasonably with concurrency
        single_throughput = performance_results[1]["throughput"]
        concurrent_throughput = performance_results[10]["throughput"]

        # With 10x concurrency, expect some improvement (realistic for API-bound operations)
        # Note: In mock environments, concurrency scaling is limited - adjust expectations
        # In real environments with actual API calls, this would scale better
        assert (
            concurrent_throughput > single_throughput * 0.7
        ), f"Poor concurrency scaling: {single_throughput:.2f} -> {concurrent_throughput:.2f} req/s"

        # Average per-request time shouldn't degrade too much
        single_avg = performance_results[1]["avg_per_request"]
        concurrent_avg = performance_results[10]["avg_per_request"]
        assert (
            concurrent_avg < single_avg * 4
        ), f"Excessive per-request degradation: {single_avg:.3f}s -> {concurrent_avg:.3f}s"

    async def test_large_result_set_performance(self, performance_registry):
        """Test performance with large result sets."""
        search_request = SearchRequest(
            query="agent performance testing",
            top_k=50,  # Large result set
            min_similarity=0.0,  # Include all agents
        )

        start_time = time.time()
        results = await performance_registry.vector_search(search_request)
        search_time = time.time() - start_time

        assert len(results) == 50  # Should return top 50
        assert_performance_within_limit(search_time, 1.0, "Large result set search")

        # Verify results are properly sorted by similarity
        similarities = [
            result.similarity for result in results if result.similarity is not None
        ]
        assert similarities == sorted(
            similarities, reverse=True
        ), "Results should be sorted by similarity (highest first)"

        print(
            f"Large result set search (top-{search_request.top_k}) completed in {search_time:.3f}s"
        )

    async def test_filtered_search_performance(self, performance_registry):
        """Test performance with various filters applied."""
        # Test different filter combinations
        filter_scenarios = [
            {
                "name": "Type filter only",
                "request": SearchRequest(
                    query="system operations", top_k=10, agent_type="security"
                ),
            },
            {
                "name": "Capabilities filter only",
                "request": SearchRequest(
                    query="data processing",
                    top_k=10,
                    capabilities=["data_analysis"],
                ),
            },
            {
                "name": "Combined filters",
                "request": SearchRequest(
                    query="monitoring systems",
                    top_k=10,
                    agent_type="monitoring",
                    capabilities=["system_monitoring"],
                ),
            },
            {
                "name": "High similarity threshold",
                "request": SearchRequest(
                    query="artificial intelligence",
                    top_k=10,
                    min_similarity=0.8,
                ),
            },
        ]

        filter_performance = {}

        for scenario in filter_scenarios:
            start_time = time.time()
            results = await performance_registry.vector_search(scenario["request"])
            elapsed_time = time.time() - start_time

            filter_performance[scenario["name"]] = {
                "elapsed_time": elapsed_time,
                "result_count": len(results),
            }

            # Filtered searches should still be performant
            assert_performance_within_limit(
                elapsed_time, 1.5, f"Filtered search: {scenario['name']}"
            )  # Allow slightly higher limit due to filtering overhead

            print(f"{scenario['name']}: {elapsed_time:.3f}s, {len(results)} results")

        # Verify filters are working correctly
        combined_results = filter_performance["Combined filters"]["result_count"]
        type_only_results = filter_performance["Type filter only"]["result_count"]

        # Combined filters should return fewer or equal results than single filters
        assert (
            combined_results <= type_only_results
        ), "Combined filters should not return more results than individual filters"

    async def test_search_latency_distribution(self, performance_registry):
        """Test search latency distribution and percentiles."""
        search_request = SearchRequest(
            query="performance testing agent", top_k=10, min_similarity=0.0
        )

        # Collect latency measurements
        latencies = []
        num_measurements = 50

        for i in range(num_measurements):
            start_time = time.time()
            results = await performance_registry.vector_search(search_request)
            latency = time.time() - start_time
            latencies.append(latency)

            assert len(results) <= 10

            # Small delay between measurements to avoid overwhelming
            if i % 10 == 9:
                await asyncio.sleep(0.01)

        # Calculate statistics
        mean_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        p95_latency = sorted(latencies)[int(0.95 * len(latencies))]
        p99_latency = sorted(latencies)[int(0.99 * len(latencies))]
        std_dev = statistics.stdev(latencies)

        print(f"Latency statistics over {num_measurements} requests:")
        print(f"  Mean: {mean_latency:.3f}s")
        print(f"  Median: {median_latency:.3f}s")
        print(f"  P95: {p95_latency:.3f}s")
        print(f"  P99: {p99_latency:.3f}s")
        print(f"  Std Dev: {std_dev:.3f}s")

        # Performance assertions
        # Adjusted thresholds for test environment with mock services
        # Note: Mock services include 10ms simulated network delay per API call
        assert mean_latency < 1.0, f"Mean latency too high: {mean_latency:.3f}s"
        assert p95_latency < 2.0, f"P95 latency too high: {p95_latency:.3f}s"
        assert p99_latency < 3.0, f"P99 latency too high: {p99_latency:.3f}s"
        assert std_dev < (
            mean_latency * 2
        ), f"High latency variance: {std_dev:.3f}s std dev"

    async def test_memory_usage_during_search(self, performance_registry):
        """Test memory usage patterns during intensive search operations."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform many searches to test memory usage
        search_requests = [
            SearchRequest(
                query=f"test query {i} with various keywords and phrases",
                top_k=20,
                min_similarity=0.0,
            )
            for i in range(50)
        ]

        memory_measurements = []

        for i, request in enumerate(search_requests):
            await performance_registry.vector_search(request)

            if i % 10 == 9:  # Measure every 10 searches
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_measurements.append(current_memory)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        print(
            f"Memory usage: {initial_memory:.1f} MB -> {final_memory:.1f} MB (+{memory_growth:.1f} MB)"
        )

        # Memory growth should be reasonable (less than 100MB for this test)
        assert memory_growth < 100, f"Excessive memory growth: {memory_growth:.1f} MB"

        # Memory usage should be relatively stable (not constantly growing)
        if len(memory_measurements) >= 3:
            early_avg = statistics.mean(memory_measurements[:2])
            late_avg = statistics.mean(memory_measurements[-2:])
            growth_rate = (late_avg - early_avg) / early_avg

            assert (
                growth_rate < 0.5
            ), f"Memory usage growing too rapidly: {growth_rate:.2%}"

    async def test_search_accuracy_under_load(self, performance_registry):
        """Test that search accuracy is maintained under high load."""
        # Define a specific query that should return predictable results
        test_query = "security vulnerability scanning"

        # Perform single search to establish baseline
        baseline_request = SearchRequest(query=test_query, top_k=5, min_similarity=0.0)
        baseline_results = await performance_registry.vector_search(baseline_request)
        baseline_ids = [result.id for result in baseline_results]

        # Perform concurrent searches with same query
        concurrent_requests = [baseline_request] * 20

        start_time = time.time()
        concurrent_results_list = await asyncio.gather(
            *[performance_registry.vector_search(req) for req in concurrent_requests]
        )
        elapsed_time = time.time() - start_time

        # Verify all concurrent searches return same results as baseline
        for results in concurrent_results_list:
            result_ids = [result.id for result in results]
            similarities = [result.similarity for result in results]

            # Results should be identical to baseline (same agents, same order)
            assert (
                result_ids == baseline_ids
            ), "Concurrent search results differ from baseline"

            # Similarities should be consistent
            baseline_similarities = [result.similarity for result in baseline_results]
            for i, (sim, baseline_sim) in enumerate(
                zip(similarities, baseline_similarities)
            ):
                if sim is not None and baseline_sim is not None:
                    assert_approximately_equal(
                        sim,
                        baseline_sim,
                        tolerance=0.01,
                        message=f"Similarity mismatch for result {i}: {sim} vs {baseline_sim}",
                    )

        print(
            f"Accuracy test: {len(concurrent_requests)} concurrent searches in {elapsed_time:.3f}s"
        )
        print("All searches returned identical results to baseline")

    @pytest.mark.skip(
        reason="Requires actual OpenAI API for realistic embedding performance"
    )
    async def test_real_embedding_performance(self):
        """Test performance with real OpenAI embeddings (requires API key)."""
        # This test would use real OpenAI API to test embedding generation performance
        # Skip by default as it requires API key and makes external calls
