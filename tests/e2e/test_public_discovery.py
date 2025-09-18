"""
End-to-end tests for public agent discovery workflow.

Tests the complete external developer experience:
Discovery → Search → Connection → Real-time Updates
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.arcp.__main__ import app
from tests.fixtures.test_helpers import (
    ResponseValidator,
    integration_test,
    wait_for_condition,
)


@integration_test
@pytest.mark.asyncio
class TestPublicDiscoveryE2E:
    """End-to-end tests for public agent discovery and connection."""

    @pytest.fixture
    def test_client(self):
        """FastAPI test client."""
        return TestClient(app)

    @pytest.fixture
    async def populated_registry(self, test_client):
        """Populate registry with test agents for discovery."""
        # Create temp registration token to bypass admin session requirements
        from tests.fixtures.auth_fixtures import create_temp_registration_token

        # Generate unique test run ID to avoid conflicts
        test_run_id = str(uuid.uuid4())[:8]

        # Register multiple test agents with unique IDs
        test_agents = [
            {
                "name": "Security Vulnerability Scanner",
                "agent_id": f"security-scanner-{test_run_id}",
                "agent_type": "security",
                "endpoint": "https://security-scanner.example.com/api",
                "context_brief": "Advanced security vulnerability assessment and penetration testing agent with AI-powered threat detection",
                "capabilities": [
                    "vulnerability_scan",
                    "penetration_test",
                    "threat_analysis",
                    "compliance_audit",
                ],
                "owner": "CyberSec Corp",
                "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2 security-key",
                "metadata": {
                    "priority": "high",
                    "certification": "ISO27001",
                    "region": "us-east-1",
                },
                "version": "3.1.0",
                "communication_mode": "remote",
            },
            {
                "name": "Financial Data Analyzer",
                "agent_id": f"fintech-analyzer-{test_run_id}",
                "agent_type": "automation",
                "endpoint": "https://fintech-analytics.example.com/api",
                "context_brief": "Specialized financial market analysis agent with real-time trading insights and risk assessment capabilities",
                "capabilities": [
                    "market_analysis",
                    "risk_assessment",
                    "trading_signals",
                    "portfolio_optimization",
                ],
                "owner": "FinTech Innovations",
                "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4F5G6H7I8J9K0L1M2N3O4P5Q6R7S8T9U0V1W2X3Y4Z5A6B7C8D9E0F1G2H3I4J5K6L7M8N9O0P1Q2R3S4T5U6V7W8X9Y0Z1A2B3C4D5E6F7G8H9I0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A8B9C0D1E2F3G4H5I6J7K8L9M0N1O2P3Q4R5S6T7U8V9W0X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R1S2T3U4V5W6X7Y8Z9A0B1C2D3E4 fintech-key",
                "metadata": {
                    "priority": "critical",
                    "compliance": "SOX",
                    "region": "us-east-1",
                },
                "version": "2.5.1",
                "communication_mode": "hybrid",
            },
            {
                "name": "Infrastructure Monitor",
                "agent_id": f"infra-monitor-{test_run_id}",
                "agent_type": "monitoring",
                "endpoint": "https://infra-monitor.example.com/api",
                "context_brief": "Comprehensive infrastructure monitoring agent with predictive maintenance and anomaly detection",
                "capabilities": [
                    "system_monitoring",
                    "anomaly_detection",
                    "predictive_maintenance",
                    "alerting",
                ],
                "owner": "DevOps Solutions",
                "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD4C5D6E7F8G9H0I1J2K3L4M5N6O7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F4G5H6I7J8K9L0M1N2O3P4Q5R6S7T8U9V0W1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M7N8O9P0Q1R2S3T4U5V6W7X8Y9Z0A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8W9X0Y1Z2A3B4C5D6E7F8G9H0I1J2K3L4M5N6O7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F4G5H6I7J8K9L0M1N2O3P4Q5R6S7T8U9V0W1X2Y3Z4A5B6C7D8E9F0G1H2I3J4K5L6M7N8O9P0Q1R2S3T4U5V6W7X8Y9Z0A1B2C3D4E5F6 monitor-key",
                "metadata": {
                    "priority": "medium",
                    "scope": "global",
                    "region": "eu-west-1",
                },
                "version": "1.8.3",
                "communication_mode": "local",
            },
        ]

        # Register agents via API using temp tokens for each agent
        for agent_data in test_agents:
            # Create a temp token for this specific agent
            temp_token = create_temp_registration_token(
                agent_data["agent_id"], agent_data["agent_type"]
            )
            temp_headers = {"Authorization": f"Bearer {temp_token}"}

            response = test_client.post(
                "/agents/register", json=agent_data, headers=temp_headers
            )
            ResponseValidator.assert_success_response(response, 200)

        # Wait for agents to be fully registered
        await wait_for_condition(
            lambda: len(test_client.get("/public/discover").json()) >= 3,
            timeout=5.0,
            error_message="Agents not registered in time",
        )

        return test_agents

    def test_public_agent_discovery(self, test_client, populated_registry):
        """Test public agent discovery endpoint."""
        # Test basic discovery
        response = test_client.get("/public/discover")
        ResponseValidator.assert_success_response(response)

        agents = response.json()
        assert len(agents) >= 3, f"Expected at least 3 agents, got {len(agents)}"

        # Verify agent data structure
        for agent in agents:
            assert "agent_id" in agent
            assert "name" in agent
            assert "agent_type" in agent
            assert "capabilities" in agent
            assert "endpoint" in agent
            assert "status" in agent
            assert agent["status"] == "alive"  # Only alive agents should be returned

        # Test filtering by agent type
        response = test_client.get("/public/discover?agent_type=security")
        ResponseValidator.assert_success_response(response)

        security_agents = response.json()
        assert len(security_agents) >= 1
        for agent in security_agents:
            assert agent["agent_type"] == "security"

        # Test filtering by capabilities
        response = test_client.get("/public/discover?capabilities=market_analysis")
        ResponseValidator.assert_success_response(response)

        market_agents = response.json()
        assert len(market_agents) >= 1
        for agent in market_agents:
            assert "market_analysis" in agent["capabilities"]

        # Test pagination
        response = test_client.get("/public/discover?limit=2&offset=0")
        ResponseValidator.assert_success_response(response)

        first_page = response.json()
        assert len(first_page) <= 2

        response = test_client.get("/public/discover?limit=2&offset=2")
        ResponseValidator.assert_success_response(response)

        second_page = response.json()
        # Should not overlap with first page
        first_page_ids = {agent["agent_id"] for agent in first_page}
        second_page_ids = {agent["agent_id"] for agent in second_page}
        assert not first_page_ids.intersection(second_page_ids)

    def test_public_semantic_search(self, test_client, populated_registry):
        """Test public semantic search functionality."""
        search_request = {
            "query": "security vulnerability assessment and penetration testing",
            "top_k": 3,
            "min_similarity": 0.3,
        }

        response = test_client.post("/public/search", json=search_request)
        ResponseValidator.assert_success_response(response)

        results = response.json()
        assert len(results) >= 1

        # Verify search results structure
        for result in results:
            assert "id" in result
            assert "name" in result
            assert "url" in result
            assert "capabilities" in result
            assert "similarity" in result
            assert result["similarity"] >= search_request["min_similarity"]

        # Results should be sorted by similarity (highest first)
        similarities = [result["similarity"] for result in results]
        assert similarities == sorted(similarities, reverse=True)

        # Test search with filters
        filtered_search = {
            "query": "financial market analysis",
            "top_k": 5,
            "agent_type": "automation",
            "capabilities": ["market_analysis"],
        }

        response = test_client.post("/public/search", json=filtered_search)
        ResponseValidator.assert_success_response(response)

        results = response.json()
        for result in results:
            # Should match filters
            agent_response = test_client.get(f"/public/agent/{result['id']}")
            agent_data = agent_response.json()
            assert agent_data["agent_type"] == "automation"
            assert "market_analysis" in agent_data["capabilities"]

    def test_public_agent_details(self, test_client, populated_registry):
        """Test getting detailed agent information."""
        # First discover an agent
        response = test_client.get("/public/discover?limit=1")
        agents = response.json()
        assert len(agents) >= 1

        agent_id = agents[0]["agent_id"]

        # Get detailed agent information
        response = test_client.get(f"/public/agent/{agent_id}")
        ResponseValidator.assert_success_response(response)

        agent_details = response.json()

        # Verify comprehensive agent information
        required_fields = [
            "agent_id",
            "name",
            "agent_type",
            "endpoint",
            "capabilities",
            "context_brief",
            "version",
            "owner",
            "communication_mode",
            "status",
            "last_seen",
            "registered_at",
        ]

        for field in required_fields:
            assert field in agent_details, f"Missing required field: {field}"

        assert agent_details["agent_id"] == agent_id
        assert agent_details["status"] == "alive"

        # Test non-existent agent
        response = test_client.get("/public/agent/non-existent-agent")
        ResponseValidator.assert_not_found_error(response)

    def test_public_agent_connection_request(self, test_client, populated_registry):
        """Test requesting connection to an agent."""
        # Discover an agent to connect to
        response = test_client.get("/public/discover?agent_type=security&limit=1")
        agents = response.json()
        assert len(agents) >= 1

        target_agent_id = agents[0]["agent_id"]

        # Create connection request
        connection_request = {
            "user_id": "external-developer-123",
            "user_endpoint": "https://my-security-app.example.com/webhook",
            "display_name": "Security Dashboard Pro",
            "additional_info": {
                "app_name": "Security Dashboard Pro",
                "app_version": "2.1.0",
                "contact_email": "dev@security-app.example.com",
                "use_case": "Automated security scanning integration",
            },
        }

        # Note: In real E2E test, this would make actual HTTP request to agent
        # For testing, we expect it to attempt the connection and handle the response
        response = test_client.post(
            f"/public/connect/{target_agent_id}", json=connection_request
        )

        # The actual response depends on whether the agent endpoint is reachable
        # In test environment, it should return an appropriate error or success
        assert response.status_code in [
            200,
            502,
            504,
        ]  # Success or connection error

        if response.status_code == 200:
            connection_response = response.json()
            assert "status" in connection_response
            assert "message" in connection_response
            assert "next_steps" in connection_response
            assert connection_response["status"] == "connection_requested"

        # Test invalid connection request
        invalid_request = {
            "user_id": "",  # Invalid empty user_id
            "user_endpoint": "invalid-url",  # Invalid URL format
        }

        response = test_client.post(
            f"/public/connect/{target_agent_id}", json=invalid_request
        )
        ResponseValidator.assert_error_response(response, 422)

    @pytest.mark.asyncio
    async def test_public_websocket_real_time_updates(self, test_client):
        """Test public WebSocket for real-time agent discovery updates."""
        # Note: This would require a WebSocket test client
        # For now, we'll test the basic WebSocket endpoint availability

        with test_client.websocket_connect("/public/ws") as websocket:
            # WebSocket should accept connection
            assert websocket is not None

            # Should receive welcome message
            welcome_data = websocket.receive_json()
            assert welcome_data["type"] == "welcome"
            assert "features" in welcome_data
            assert "agent_updates" in welcome_data["features"]

            # Send ping
            websocket.send_json({"type": "ping"})
            pong_data = websocket.receive_json()
            assert pong_data["type"] == "pong"

            # Request discovery data with pagination
            discovery_request = {
                "type": "get_discovery",
                "page": 1,
                "page_size": 10,
                "agent_type": "security",
            }
            websocket.send_json(discovery_request)

            discovery_data = websocket.receive_json()
            assert discovery_data["type"] == "discovery_data"
            assert "data" in discovery_data
            assert "pagination" in discovery_data["data"]

            pagination = discovery_data["data"]["pagination"]
            assert "current_page" in pagination
            assert "total_agents" in pagination
            assert "has_next" in pagination
            assert "has_previous" in pagination

    def test_public_system_info(self, test_client):
        """Test public system information endpoint."""
        response = test_client.get("/public/info")
        ResponseValidator.assert_success_response(response)

        system_info = response.json()

        required_fields = [
            "service",
            "version",
            "public_api",
            "capabilities",
            "limits",
        ]
        for field in required_fields:
            assert field in system_info, f"Missing required field: {field}"

        assert system_info["service"] == "ARCP (Agent Registry & Control Protocol)"
        assert system_info["version"] == "2.0.0"

        # Check API capabilities
        public_api = system_info["public_api"]
        assert public_api["available"] is True
        assert "endpoints" in public_api
        assert "features" in public_api

        # Check limits
        limits = system_info["limits"]
        assert "discover_max_limit" in limits
        assert "search_max_limit" in limits

    def test_public_statistics(self, test_client, populated_registry):
        """Test public statistics endpoint."""
        response = test_client.get("/public/stats")
        ResponseValidator.assert_success_response(response)

        stats = response.json()

        required_fields = [
            "alive_agents",
            "total_agents",
            "agent_types",
            "system_status",
        ]
        for field in required_fields:
            assert field in stats, f"Missing required field: {field}"

        assert stats["alive_agents"] >= 3  # From populated registry
        assert stats["total_agents"] >= 3
        assert stats["agent_types"] >= 3  # security, automation, monitoring
        assert stats["system_status"] == "operational"

        # Should include available agent types
        if "available_types" in stats:
            available_types = stats["available_types"]
            assert isinstance(available_types, list)
            assert len(available_types) >= 3

    def test_complete_external_developer_workflow(
        self, test_client, populated_registry
    ):
        """Test complete workflow for external developer using public API."""
        # Step 1: Get system info to understand capabilities
        response = test_client.get("/public/info")
        system_info = response.json()
        assert system_info["public_api"]["available"] is True

        # Step 2: Get general statistics
        response = test_client.get("/public/stats")
        stats = response.json()
        assert stats["alive_agents"] > 0

        # Step 3: Discover available agents
        response = test_client.get("/public/discover?limit=10")
        agents = response.json()
        assert len(agents) >= 3

        # Step 4: Filter by specific needs (e.g., security agents)
        response = test_client.get("/public/discover?agent_type=security")
        security_agents = response.json()
        assert len(security_agents) >= 1

        # Step 5: Search with semantic query
        search_request = {
            "query": "vulnerability scanning and security assessment",
            "top_k": 5,
            "min_similarity": 0.3,
        }

        response = test_client.post("/public/search", json=search_request)
        search_results = response.json()
        assert len(search_results) >= 1

        # Step 6: Get detailed info for best match
        best_match = search_results[0]
        response = test_client.get(f"/public/agent/{best_match['id']}")
        agent_details = response.json()

        assert agent_details["agent_id"] == best_match["id"]
        assert "capabilities" in agent_details
        assert (
            "requirements" in agent_details or agent_details.get("requirements") is None
        )

        # Step 7: Attempt connection
        connection_request = {
            "user_id": "security-platform-001",
            "user_endpoint": "https://security-platform.example.com/agent-webhook",
            "display_name": "Security Platform Integration",
            "additional_info": {
                "integration_type": "REST API",
                "expected_volume": "high",
                "use_case": "Automated vulnerability scanning",
            },
        }

        response = test_client.post(
            f"/public/connect/{agent_details['agent_id']}",
            json=connection_request,
        )

        # Accept various responses based on agent availability
        assert response.status_code in [200, 502, 504]

        # Workflow completed successfully - external developer
        # now has all information needed to integrate with ARCP agents
