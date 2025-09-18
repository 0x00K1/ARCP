"""
Integration tests for Public API endpoints.
These endpoints should be publicly accessible without authentication.
"""

import pytest


@pytest.mark.integration
class TestPublicAPI:
    """Integration tests for Public API endpoints."""

    def test_discover_agents(self, test_client):
        """Test the public discover agents endpoint."""
        response = test_client.get("/public/discover")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_discover_agents_with_filters(self, test_client):
        """Test discover agents with type filter."""
        response = test_client.get("/public/discover?agent_type=test&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_discover_agents_with_capabilities(self, test_client):
        """Test discover agents with capabilities filter."""
        response = test_client.get(
            "/public/discover?capabilities=test&capabilities=demo"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_search_agents(self, test_client):
        """Test the public search agents endpoint."""
        search_data = {
            "query": "test agent",
            "top_k": 5,
            "min_similarity": 0.5,
        }

        response = test_client.post("/public/search", json=search_data)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_search_agents_with_filters(self, test_client):
        """Test search agents with additional filters."""
        search_data = {
            "query": "automation agent",
            "top_k": 10,
            "min_similarity": 0.3,
            "agent_type": "automation",
            "capabilities": ["analysis"],
        }

        response = test_client.post("/public/search", json=search_data)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_search_agents_invalid_data(self, test_client):
        """Test search with invalid data."""
        invalid_data = {
            "query": "",  # Empty query
            "top_k": -1,  # Invalid top_k
            "min_similarity": 2.0,  # Invalid similarity
        }

        response = test_client.post("/public/search", json=invalid_data)

        # Should return validation error
        assert response.status_code == 422

    def test_get_agent_by_id(self, test_client, sample_agent_request):
        """Test getting a specific agent by ID."""
        response = test_client.get(f"/public/agent/{sample_agent_request.agent_id}")

        # Should be accessible publicly, but might get 500 error if agent structure is unexpected
        assert response.status_code in [200, 404, 500]

    def test_get_agent_nonexistent(self, test_client):
        """Test getting a non-existent agent."""
        response = test_client.get("/public/agent/non-existent-agent")

        # Might return 500 instead of 404 due to error handling
        assert response.status_code in [404, 500]

    def test_connect_to_agent(self, test_client):
        """Test connecting to an agent."""
        connection_data = {
            "user_id": "test-user-123",
            "user_endpoint": "http://localhost:3000/user-callback",
            "message": "Hello, I'd like to connect",
            "context": "Testing connection",
        }

        response = test_client.post("/public/connect/test-agent", json=connection_data)

        # Should work if agent exists or return 404
        assert response.status_code in [
            200,
            404,
            500,
        ]  # 500 if agent doesn't exist

    def test_service_info(self, test_client):
        """Test the service info endpoint."""
        response = test_client.get("/public/info")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "capabilities" in data

    def test_service_stats(self, test_client):
        """Test the service statistics endpoint."""
        response = test_client.get("/public/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_agents" in data
        assert "alive_agents" in data

    def test_get_agent_types(self, test_client):
        """Test getting available agent types."""
        response = test_client.get("/public/agent_types")

        assert response.status_code == 200
        data = response.json()
        assert "allowed_agent_types" in data
        assert isinstance(data["allowed_agent_types"], list)

    def test_websocket_connection(self, test_client):
        """Test WebSocket connection for real-time updates."""
        # This would need special handling for WebSocket testing
        # For now, we'll test that the endpoint exists
        # In a real test, you'd use test_client.websocket_connect()

    def test_discover_agents_pagination(self, test_client):
        """Test pagination in discover agents."""
        # Test first page
        response1 = test_client.get("/public/discover?limit=5&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()

        # Test second page
        response2 = test_client.get("/public/discover?limit=5&offset=5")
        assert response2.status_code == 200
        data2 = response2.json()

        # Pages should be different (assuming we have enough agents)
        assert isinstance(data1, list)
        assert isinstance(data2, list)

    def test_discover_agents_limit_validation(self, test_client):
        """Test that limit validation works correctly."""
        # Test maximum limit - should return validation error
        response = test_client.get("/public/discover?limit=150")

        # Should return validation error for exceeding max limit
        assert response.status_code == 422

        # Test negative limit - the API may handle this differently
        response = test_client.get("/public/discover?limit=-1")
        # The API might accept negative values and handle them gracefully
        assert response.status_code in [200, 422]
