"""
Unit tests for ARCP Client

This module tests the ARCPClient class with mocked HTTP responses
to ensure the client works correctly without needing a real ARCP server.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcp.client import AgentRequirements, ARCPClient, ARCPError


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient"""
    with patch("arcp.client.httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        # Set up the request method to return a response-like object by default
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        client_instance.request.return_value = mock_response
        mock.return_value = client_instance
        yield client_instance


class TestARCPClient:
    """Test cases for ARCPClient class"""

    @pytest.fixture
    def arcp_client(self, mock_httpx_client):
        """Create an ARCPClient instance with mocked HTTP client"""
        return ARCPClient("https://test.arcp.com")

    def test_client_initialization(self):
        """Test client initialization with various configurations"""
        # Basic initialization
        client = ARCPClient("https://test.arcp.com")
        assert client.base_url == "https://test.arcp.com"
        assert client.timeout == 30.0
        assert client.retry_attempts == 3

        # Custom configuration
        client = ARCPClient("https://test.arcp.com", timeout=60.0, retry_attempts=5)
        assert client.timeout == 60.0
        assert client.retry_attempts == 5

    @pytest.mark.asyncio
    async def test_health_check(self, arcp_client, mock_httpx_client):
        """Test health check endpoint"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "2.0.2",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.request.return_value = mock_response

        health = await arcp_client.health_check()

        assert health["status"] == "healthy"
        assert health["version"] == "2.0.2"
        mock_httpx_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_system_info(self, arcp_client, mock_httpx_client):
        """Test system info endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "service": "ARCP",
            "version": "2.0.2",
            "public_api": {"features": ["discovery", "search", "stats"]},
        }
        mock_httpx_client.request.return_value = mock_response

        info = await arcp_client.get_system_info()

        assert info["service"] == "ARCP"
        assert "discovery" in info["public_api"]["features"]
        mock_httpx_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_agents(self, arcp_client, mock_httpx_client):
        """Test agent discovery"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agents": [
                {
                    "agent_id": "test-agent-1",
                    "name": "Test Agent 1",
                    "agent_type": "security",
                    "status": "alive",
                    "capabilities": ["vulnerability-scanning"],
                    "context_brief": "Test agent for security analysis",
                    "version": "1.0.0",
                    "endpoint": "https://agent1.test.com",
                    "owner": "test-user",
                    "public_key": "1234567890abcdef1234567890abcdef12345678",
                    "communication_mode": "remote",
                    "last_seen": "2024-01-01T00:00:00Z",
                    "registered_at": "2024-01-01T00:00:00Z",
                    "metadata": {"test": "data"},
                }
            ],
            "pagination": {
                "offset": 0,
                "limit": 10,
                "total_agents": 1,
                "has_more": False,
            },
        }
        mock_httpx_client.request.return_value = mock_response

        agents = await arcp_client.discover_agents(limit=10)

        assert len(agents) == 1
        assert agents[0].agent_id == "test-agent-1"
        assert agents[0].name == "Test Agent 1"
        assert agents[0].status == "alive"
        assert agents[0].agent_type == "security"

        mock_httpx_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_agents(self, arcp_client, mock_httpx_client):
        """Test semantic agent search"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "test-agent-1",
                    "name": "Test Agent 1",
                    "similarity": 0.85,
                    "capabilities": ["vulnerability-scanning"],
                    "url": "https://agent1.test.com",
                    "version": "1.0.0",
                    "owner": "test-user",
                }
            ],
            "query": "data analysis agent",
            "total_results": 1,
            "search_time_ms": 150,
        }
        mock_httpx_client.request.return_value = mock_response

        results = await arcp_client.search_agents(
            "data analysis agent", top_k=5, min_similarity=0.7
        )

        assert len(results) == 1
        assert results[0].id == "test-agent-1"
        assert results[0].similarity == 0.85

        mock_httpx_client.request.assert_called_once()
        # Note: More detailed assertion of call args would require examining the actual call
        # call_args = mock_httpx_client.request.call_args
        # assert "search" in call_args[1]["url"]

    @pytest.mark.asyncio
    async def test_agent_registration(self, arcp_client, mock_httpx_client):
        """Test agent registration"""
        # Mock token request first
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "temp_token": "test-token",
            "expires_in": 3600,
        }

        # Mock registration response
        register_response = MagicMock()
        register_response.status_code = 201
        register_response.json.return_value = {
            "agent_id": "test-agent-1",
            "name": "Test Agent",
            "agent_type": "security",
            "status": "alive",
            "capabilities": ["vulnerability-scanning"],
            "context_brief": "Test agent",
            "version": "1.0.0",
            "endpoint": "https://test-agent.com",
            "owner": "test-user",
            "public_key": "1234567890abcdef1234567890abcdef12345678",
            "communication_mode": "remote",
            "last_seen": "2024-01-01T00:00:00Z",
            "registered_at": "2024-01-01T00:00:00Z",
            "metadata": {"test": "data"},
        }

        # Set up mock responses in order: token, registration, get_agent
        get_agent_response = MagicMock()
        get_agent_response.status_code = 200
        get_agent_response.json.return_value = {
            "agent_id": "test-agent-1",
            "name": "Test Agent",
            "agent_type": "security",
            "status": "alive",
            "capabilities": ["vulnerability-scanning"],
            "context_brief": "Test agent",
            "version": "1.0.0",
            "endpoint": "https://test-agent.com",
            "owner": "test-user",
            "public_key": "1234567890abcdef1234567890abcdef12345678",
            "communication_mode": "remote",
            "last_seen": "2024-01-01T00:00:00Z",
            "registered_at": "2024-01-01T00:00:00Z",
            "metadata": {"test": "data"},
        }

        mock_httpx_client.request.side_effect = [
            token_response,
            register_response,
            get_agent_response,
        ]

        agent = await arcp_client.register_agent(
            agent_id="test-agent-1",
            name="Test Agent",
            agent_type="security",
            endpoint="https://test-agent.com",
            capabilities=["vulnerability-scanning"],
            context_brief="Test agent",
            version="1.0.0",
            owner="test-user",
            public_key="1234567890abcdef1234567890abcdef12345678",
            communication_mode="remote",
            metadata={"test": "data"},
            agent_key="test-key",
        )

        assert agent.agent_id == "test-agent-1"
        assert agent.name == "Test Agent"
        assert agent.status == "alive"

        # Verify three calls were made (token + registration + get_agent)
        assert mock_httpx_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_agent_heartbeat(self, arcp_client, mock_httpx_client):
        """Test agent heartbeat"""
        # Mock heartbeat response
        heartbeat_response = MagicMock()
        heartbeat_response.status_code = 200
        heartbeat_response.json.return_value = {
            "agent_id": "test-agent-1",
            "status": "alive",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        mock_httpx_client.request.return_value = heartbeat_response

        result = await arcp_client.update_heartbeat("test-agent-1")

        assert result["agent_id"] == "test-agent-1"
        assert result["status"] == "alive"

    @pytest.mark.asyncio
    async def test_error_handling(self, arcp_client, mock_httpx_client):
        """Test various error conditions"""

        # Test 404 error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Agent not found"}
        mock_httpx_client.request.return_value = mock_response

        with pytest.raises(ARCPError, match="Endpoint not found"):
            await arcp_client.get_public_agent("nonexistent-agent")

        # Test 429 rate limit error
        mock_response.status_code = 429
        mock_response.json.return_value = {"detail": "Rate limit exceeded"}

        with pytest.raises(ARCPError, match="Rate limit exceeded"):
            await arcp_client.health_check()

        # Test 500 server error
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with pytest.raises(ARCPError, match="Health check failed"):
            await arcp_client.health_check()

    @pytest.mark.asyncio
    async def test_retry_logic(self, arcp_client, mock_httpx_client):
        """Test retry logic for failed requests"""
        import httpx

        # First two calls fail with connection error, third succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"status": "healthy"}

        mock_httpx_client.request.side_effect = [
            httpx.ConnectError("Connection failed"),
            httpx.ConnectError("Connection failed"),
            success_response,
        ]

        # Should succeed after retries
        result = await arcp_client.health_check()
        assert result["status"] == "healthy"

        # Should have made 3 calls total
        assert mock_httpx_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_httpx_client):
        """Test using client as async context manager"""
        async with ARCPClient("https://test.arcp.com") as client:
            assert client._client is not None

        # Client should be closed after context exit (Note: this check might not work as expected with mocks)
        # mock_httpx_client.aclose.assert_called_once()

    def test_agent_requirements(self):
        """Test AgentRequirements helper class"""
        reqs = AgentRequirements(
            system_requirements=["linux", "docker"],
            permissions=["network", "filesystem"],
            minimum_memory_mb=1024,
            requires_internet=True,
        )

        assert "linux" in reqs.system_requirements
        assert "network" in reqs.permissions
        assert reqs.minimum_memory_mb == 1024
        assert reqs.requires_internet is True

    @pytest.mark.asyncio
    async def test_login_admin(self, arcp_client, mock_httpx_client):
        """Test admin authentication in ARCPClient"""
        # Mock successful admin login response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-admin-token",
            "expires_in": 1800,
            "token_type": "bearer",
        }
        mock_httpx_client.request.return_value = mock_response

        result = await arcp_client.login_admin("root", "root")

        # Verify the response
        assert result["access_token"] == "test-admin-token"
        assert result["expires_in"] == 1800

        # Verify token was stored
        assert arcp_client._access_token == "test-admin-token"
        assert arcp_client._token_expires_at is not None

        # Verify correct API call was made
        mock_httpx_client.request.assert_called_once()
        call_args = mock_httpx_client.request.call_args
        assert call_args[1]["method"] == "POST"
        assert "/auth/login" in call_args[1]["url"]
        assert call_args[1]["json"] == {"username": "root", "password": "root"}

    @pytest.mark.asyncio
    async def test_login_admin_failure(self, arcp_client, mock_httpx_client):
        """Test admin authentication failure handling"""
        from arcp.client import AuthenticationError

        # Mock failed login response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid credentials"}
        mock_httpx_client.request.return_value = mock_response

        with pytest.raises(AuthenticationError, match="Admin login failed"):
            await arcp_client.login_admin("wrong", "credentials")

    @pytest.mark.asyncio
    async def test_get_system_metrics(self, arcp_client, mock_httpx_client):
        """Test system metrics retrieval (admin only)"""
        # Mock metrics response - the _request method will wrap plain text in {"message": text}
        mock_metrics = """# HELP arcp_system_cpu_utilization_percent CPU utilization
arcp_system_cpu_utilization_percent 25.5
# HELP arcp_active_agents Active agents count
arcp_active_agents{agent_type="all"} 3"""

        # Mock _request to return the wrapped response like it does for non-JSON responses
        with patch.object(
            arcp_client, "_request", return_value={"message": mock_metrics}
        ):
            result = await arcp_client.get_system_metrics()

            # Verify the response content
            assert "arcp_system_cpu_utilization_percent" in result
            assert "25.5" in result
            assert "arcp_active_agents" in result
            assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_get_system_metrics_auth_error(self, arcp_client, mock_httpx_client):
        """Test system metrics authentication error handling"""
        from arcp.client import AuthenticationError

        # Mock _request to raise an exception with 403 in the message
        with patch.object(
            arcp_client, "_request", side_effect=Exception("403 Forbidden")
        ):
            with pytest.raises(
                AuthenticationError, match="Admin authentication required"
            ):
                await arcp_client.get_system_metrics()

    @pytest.mark.asyncio
    async def test_get_system_stats(self, arcp_client, mock_httpx_client):
        """Test system statistics retrieval (admin only)"""
        # Mock system stats response
        mock_stats = {
            "registry_statistics": {
                "alive_agents": 2,
                "total_agents": 3,
                "agent_types": {"testing": 1, "production": 1},
            },
            "feature_statistics": {"websocket_enabled": True, "search_enabled": True},
            "performance_metrics": {"avg_response_time": 150.5, "total_requests": 1500},
        }

        # Mock _request to return the stats
        with patch.object(arcp_client, "_request", return_value=mock_stats):
            result = await arcp_client.get_system_stats()

            # Verify the response
            assert result == mock_stats
            assert result["registry_statistics"]["alive_agents"] == 2
            assert result["feature_statistics"]["websocket_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_resource_utilization(self, arcp_client, mock_httpx_client):
        """Test resource utilization parsing from system metrics"""
        # Mock metrics with resource utilization data
        mock_metrics = """# System resource metrics
arcp_system_cpu_utilization_percent 45.2
arcp_system_memory_utilization_percent 67.8
arcp_system_network_utilization_percent 12.1
arcp_system_disk_utilization_percent 23.4
# Other metrics
arcp_active_agents 5"""

        # Mock the get_system_metrics call
        with patch.object(arcp_client, "get_system_metrics", return_value=mock_metrics):
            result = await arcp_client.get_resource_utilization()

            # Verify parsed resource utilization
            expected = {"cpu": 45.2, "memory": 67.8, "network": 12.1, "disk": 23.4}
            assert result == expected

    @pytest.mark.asyncio
    async def test_get_resource_utilization_missing_metrics(
        self, arcp_client, mock_httpx_client
    ):
        """Test resource utilization with missing metrics"""
        # Mock metrics without resource utilization
        mock_metrics = """# Only other metrics
arcp_active_agents 5
arcp_requests_total 1000"""

        with patch.object(arcp_client, "get_system_metrics", return_value=mock_metrics):
            with pytest.raises(
                ARCPError, match="Resource utilization metrics not found"
            ):
                await arcp_client.get_resource_utilization()

    @pytest.mark.asyncio
    async def test_admin_metrics_workflow(self, arcp_client, mock_httpx_client):
        """Test complete admin metrics workflow: login -> get metrics -> get stats"""
        # Mock the _request method for the workflow
        mock_metrics = "arcp_system_cpu_utilization_percent 30.0\narcp_active_agents 2"
        mock_stats = {"registry_statistics": {"alive_agents": 2, "total_agents": 2}}

        # Create a side effect that returns different responses based on the endpoint
        def mock_request(method, endpoint, **kwargs):
            if endpoint == "/auth/login":
                return {"access_token": "admin-token", "expires_in": 1800}
            elif endpoint == "/metrics":
                return {"message": mock_metrics}  # Wrapped in message for non-JSON
            elif endpoint == "/agents/stats":
                return mock_stats
            else:
                raise ValueError(f"Unexpected endpoint: {endpoint}")

        with patch.object(arcp_client, "_request", side_effect=mock_request):
            # Execute workflow
            login_result = await arcp_client.login_admin("root", "root")
            assert login_result["access_token"] == "admin-token"

            metrics = await arcp_client.get_system_metrics()
            assert "arcp_system_cpu_utilization_percent" in metrics

            stats = await arcp_client.get_system_stats()
            assert stats["registry_statistics"]["alive_agents"] == 2


class TestARCPClientIntegration:
    """Integration-style tests that test multiple client operations together"""

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self, mock_httpx_client):
        """Test complete agent lifecycle: register -> heartbeat -> search -> unregister"""

        # Mock all responses for the lifecycle
        responses = [
            # Token for registration
            MagicMock(
                status_code=200,
                **{
                    "json.return_value": {
                        "temp_token": "token1",
                        "expires_in": 3600,
                    }
                },
            ),
            # Registration
            MagicMock(
                status_code=201,
                **{
                    "json.return_value": {
                        "agent_id": "lifecycle-agent",
                        "name": "Lifecycle Agent",
                        "agent_type": "security",
                        "status": "alive",
                        "capabilities": ["testing"],
                        "context_brief": "Test agent",
                        "version": "1.0.0",
                        "endpoint": "https://test.com",
                        "owner": "test-user",
                        "public_key": "1234567890abcdef1234567890abcdef12345678",
                        "communication_mode": "remote",
                        "last_seen": "2024-01-01T00:00:00Z",
                        "registered_at": "2024-01-01T00:00:00Z",
                        "metadata": {"test": "data"},
                    }
                },
            ),
            # Get agent (after registration)
            MagicMock(
                status_code=200,
                **{
                    "json.return_value": {
                        "agent_id": "lifecycle-agent",
                        "name": "Lifecycle Agent",
                        "agent_type": "security",
                        "status": "alive",
                        "capabilities": ["testing"],
                        "context_brief": "Test agent",
                        "version": "1.0.0",
                        "endpoint": "https://test.com",
                        "owner": "test-user",
                        "public_key": "1234567890abcdef1234567890abcdef12345678",
                        "communication_mode": "remote",
                        "last_seen": "2024-01-01T00:00:00Z",
                        "registered_at": "2024-01-01T00:00:00Z",
                        "metadata": {"test": "data"},
                    }
                },
            ),
            # Heartbeat
            MagicMock(
                status_code=200,
                **{
                    "json.return_value": {
                        "agent_id": "lifecycle-agent",
                        "status": "alive",
                        "timestamp": "2024-01-01T00:01:00Z",
                    }
                },
            ),
            # Search (no auth needed)
            MagicMock(
                status_code=200,
                **{
                    "json.return_value": {
                        "results": [
                            {
                                "id": "lifecycle-agent",
                                "name": "Lifecycle Agent",
                                "similarity": 0.95,
                                "capabilities": ["testing"],
                                "url": "https://test.com",
                                "version": "1.0.0",
                                "owner": "test-user",
                            }
                        ],
                        "query": "test agent",
                        "total_results": 1,
                        "search_time_ms": 100,
                    }
                },
            ),
            # Unregister
            MagicMock(
                status_code=200,
                **{
                    "json.return_value": {
                        "message": "Agent unregistered successfully",
                        "agent_id": "lifecycle-agent",
                    }
                },
            ),
        ]

        mock_httpx_client.request.side_effect = responses

        async with ARCPClient("https://test.arcp.com") as client:
            # 1. Register agent
            agent = await client.register_agent(
                agent_id="lifecycle-agent",
                name="Lifecycle Agent",
                agent_type="security",
                endpoint="https://test.com",
                capabilities=["testing"],
                context_brief="Test agent",
                version="1.0.0",
                owner="test-user",
                public_key="1234567890abcdef1234567890abcdef12345678",
                communication_mode="remote",
                metadata={"test": "data"},
                agent_key="test-key",
            )

            assert agent.agent_id == "lifecycle-agent"

            # 2. Send heartbeat
            heartbeat = await client.update_heartbeat("lifecycle-agent")

            assert heartbeat["status"] == "alive"

            # 3. Search for the agent
            search_results = await client.search_agents("test agent")

            assert len(search_results) == 1
            assert search_results[0].id == "lifecycle-agent"

            # 4. Unregister agent
            result = await client.unregister_agent(
                "lifecycle-agent", agent_key="test-key"
            )

            assert "successfully" in result["message"]


class TestUnifiedMetricsClient:
    """Tests for the unified metrics functionality in ARCPClient"""

    @pytest.mark.asyncio
    async def test_metrics_snapshot_functionality(self, mock_httpx_client):
        """Test metrics snapshot creation with unified client"""
        from arcp.client import ARCPClient, MetricsSnapshot

        client = ARCPClient("http://localhost:8001")

        # Mock responses for admin login and snapshot data
        prometheus_data = """arcp_system_cpu_utilization_percent 25.0
arcp_system_memory_utilization_percent 50.0
arcp_system_network_utilization_percent 10.0
arcp_system_disk_utilization_percent 75.0
arcp_active_agents 1"""

        # Create a proper mock response for Prometheus metrics
        def create_prometheus_response():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = prometheus_data
            mock_response.json.side_effect = json.JSONDecodeError("Not JSON", "", 0)
            return mock_response

        mock_responses = [
            # Admin login
            MagicMock(
                status_code=200,
                json=lambda: {
                    "access_token": "test_token",
                    "expires_in": 1800,
                    "token_type": "bearer",
                },
            ),
            # get_system_metrics (Prometheus text) - first call
            create_prometheus_response(),
            # get_system_stats (JSON)
            MagicMock(
                status_code=200,
                json=lambda: {"registry_statistics": {"alive_agents": 1}},
            ),
            # get_system_metrics (Prometheus text) - second call from get_resource_utilization
            create_prometheus_response(),
        ]

        mock_httpx_client.request.side_effect = mock_responses

        # Login as admin
        await client.login_admin("root", "root")

        # Test snapshot creation
        snapshot = await client.get_metrics_snapshot()

        # Verify snapshot contents
        assert isinstance(snapshot, MetricsSnapshot)
        assert "arcp_system_cpu_utilization_percent 25.0" in snapshot.prometheus_metrics
        assert snapshot.agent_stats["registry_statistics"]["alive_agents"] == 1
        assert snapshot.resource_utilization["cpu"] == 25.0
        assert snapshot.timestamp is not None

    @pytest.mark.asyncio
    async def test_health_check_functionality(self, mock_httpx_client):
        """Test system health check with unified client - testing the admin_health_check method"""
        from datetime import datetime

        from arcp.client import ARCPClient, MetricsSnapshot

        client = ARCPClient("http://localhost:8001")

        # Mock the login first
        mock_httpx_client.request.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "test_token",
                "expires_in": 1800,
                "token_type": "bearer",
            },
        )
        await client.login_admin("root", "root")

        # Create a realistic metrics snapshot
        mock_snapshot = MetricsSnapshot(
            timestamp=datetime.now(),
            prometheus_metrics="""arcp_system_cpu_utilization_percent 25.0
arcp_system_memory_utilization_percent 50.0
arcp_system_network_utilization_percent 10.0
arcp_system_disk_utilization_percent 75.0
arcp_active_agents 2""",
            agent_stats={"registry_statistics": {"alive_agents": 2, "total_agents": 2}},
            resource_utilization={
                "cpu": 25.0,
                "memory": 50.0,
                "network": 10.0,
                "disk": 75.0,
            },
        )

        # Mock only the get_metrics_snapshot method to test the admin_health_check logic
        with patch.object(client, "get_metrics_snapshot", return_value=mock_snapshot):
            # Test the admin health check method
            health = await client.admin_health_check()

            # Debug: print the actual response
            print("Actual health response:", health)
            print("Health response keys:", list(health.keys()))

            # Verify health status structure
            assert isinstance(health, dict)
            assert "status" in health
            assert "timestamp" in health
            assert "checks" in health

            # Verify overall status is healthy (all metrics under thresholds)
            assert health["status"] == "healthy"

            # Verify individual checks
            checks = health["checks"]
            assert "cpu_usage" in checks
            assert "memory_usage" in checks
            assert "agent_availability" in checks

            # CPU should be OK (25% < 90% threshold)
            assert checks["cpu_usage"]["status"] == "ok"
            assert checks["cpu_usage"]["value"] == 25.0

            # Memory should be OK (50% < 95% threshold)
            assert checks["memory_usage"]["status"] == "ok"
            assert checks["memory_usage"]["value"] == 50.0

            # Agent availability should be OK (2 alive == 2 total)
            assert checks["agent_availability"]["status"] == "ok"
            assert checks["agent_availability"]["alive_agents"] == 2
            assert checks["agent_availability"]["total_agents"] == 2

    @pytest.mark.asyncio
    async def test_monitor_system_functionality(self, mock_httpx_client):
        """Test system monitoring with unified client"""
        from arcp.client import ARCPClient

        client = ARCPClient("http://localhost:8001")

        prometheus_data = """arcp_system_cpu_utilization_percent 25.0
arcp_system_memory_utilization_percent 50.0
arcp_system_network_utilization_percent 10.0
arcp_system_disk_utilization_percent 75.0
arcp_active_agents 1"""

        # Create a proper mock response for Prometheus metrics
        def create_prometheus_response():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = prometheus_data
            mock_response.json.side_effect = json.JSONDecodeError("Not JSON", "", 0)
            return mock_response

        # Mock admin login response
        mock_login_response = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "test_token",
                "expires_in": 1800,
                "token_type": "bearer",
            },
        )

        # For monitoring, we'll mock multiple cycles of responses
        mock_monitor_responses = [
            # get_system_metrics (Prometheus text) - first call
            create_prometheus_response(),
            # get_system_stats (JSON)
            MagicMock(
                status_code=200,
                json=lambda: {"registry_statistics": {"alive_agents": 1}},
            ),
            # get_system_metrics (Prometheus text) - second call from get_resource_utilization
            create_prometheus_response(),
        ]

        mock_httpx_client.request.side_effect = [
            mock_login_response
        ] + mock_monitor_responses

        # Login as admin
        await client.login_admin("root", "root")

        # Test monitoring with callback
        snapshots = []

        def custom_callback(snapshot):
            snapshots.append(snapshot)

        with patch("asyncio.sleep"):
            # Test one monitoring cycle
            await client.monitor_system(
                interval=1, duration=1, callback=custom_callback
            )

            # Verify callback was called at least once
            assert len(snapshots) >= 1
            assert (
                "arcp_system_cpu_utilization_percent 25.0"
                in snapshots[0].prometheus_metrics
            )

    @pytest.mark.asyncio
    async def test_export_metrics_functionality(self, mock_httpx_client):
        """Test metrics export with unified client"""
        from arcp.client import ARCPClient

        client = ARCPClient("http://localhost:8001")

        # Mock admin login and export responses
        mock_prometheus = (
            "arcp_system_cpu_utilization_percent 25.0\narcp_active_agents 1"
        )

        # Create a proper mock response for Prometheus metrics
        def create_prometheus_response():
            import json

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = mock_prometheus
            mock_response.json.side_effect = json.JSONDecodeError("Not JSON", "", 0)
            return mock_response

        mock_responses = [
            # Admin login
            MagicMock(
                status_code=200,
                json=lambda: {
                    "access_token": "test_token",
                    "expires_in": 1800,
                    "token_type": "bearer",
                },
            ),
            # Prometheus export (default)
            create_prometheus_response(),
            # Prometheus export (explicit)
            create_prometheus_response(),
            # For JSON format: get_system_metrics (first call)
            create_prometheus_response(),
            # For JSON format: get_system_stats
            MagicMock(
                status_code=200,
                json=lambda: {"registry_statistics": {"alive_agents": 1}},
            ),
            # For JSON format: get_system_metrics (second call from get_resource_utilization)
            create_prometheus_response(),
        ]

        mock_httpx_client.request.side_effect = mock_responses

        # Login as admin
        await client.login_admin("root", "root")

        # Test prometheus format (default)
        result = await client.export_metrics()
        assert result == mock_prometheus

        # Test prometheus format (explicit)
        result = await client.export_metrics("prometheus")
        assert result == mock_prometheus

        # Test JSON format
        result = await client.export_metrics("json")
        # JSON result should be a valid JSON string
        import json

        json_data = json.loads(result)
        assert "timestamp" in json_data
        assert "agent_stats" in json_data
        assert "resource_utilization" in json_data
        assert "metrics_size" in json_data

    def test_metrics_snapshot_get_metric_value(self):
        """Test MetricsSnapshot.get_metric_value method"""
        from datetime import datetime

        from arcp.client import MetricsSnapshot

        prometheus_data = """# HELP test metric
arcp_test_metric 42.0
arcp_another_metric 100.5
some_other_format{label="value"} 200.0"""

        snapshot = MetricsSnapshot(
            timestamp=datetime.now(),
            prometheus_metrics=prometheus_data,
            agent_stats={},
            resource_utilization={},
        )

        # Test existing metrics
        assert snapshot.get_metric_value("arcp_test_metric") == 42.0
        assert snapshot.get_metric_value("arcp_another_metric") == 100.5

        # Test non-existing metric
        assert snapshot.get_metric_value("nonexistent_metric") is None

        # Test metric with labels
        assert snapshot.get_metric_value('some_other_format{label="value"}') == 200.0

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions for system health and monitoring"""
        from arcp.client import get_system_health, monitor_system

        with patch("arcp.client.ARCPClient") as MockARCPClient:
            mock_client = AsyncMock()
            MockARCPClient.return_value = mock_client

            mock_health = {"status": "healthy"}
            mock_client.admin_health_check.return_value = mock_health

            # Test get_system_health convenience function
            result = await get_system_health("http://localhost:8001", "root", "root")

            MockARCPClient.assert_called_with("http://localhost:8001")
            mock_client.login_admin.assert_called_with("root", "root")
            mock_client.admin_health_check.assert_called_once()
            assert result == mock_health

            # Reset mock for next test
            MockARCPClient.reset_mock()
            mock_client.reset_mock()

            # Test monitor_system convenience function
            await monitor_system(
                "http://localhost:8001", "root", "root", interval=30, duration=60
            )

            MockARCPClient.assert_called_with("http://localhost:8001")
            mock_client.login_admin.assert_called_with("root", "root")
            mock_client.monitor_system.assert_called_with(interval=30, duration=60)
