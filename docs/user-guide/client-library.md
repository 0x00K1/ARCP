# Client Library Guide

The ARCP Python client library provides a comprehensive interface for interacting with ARCP servers. This guide covers all client features with practical examples.

## 🚀 Installation

```bash
# Install from PyPI
pip install arcp-py

# Or install from source
git clone https://github.com/0x00K1/ARCP.git
cd ARCP
pip install -e .
```

## 🔧 Basic Usage

### Simple Client Setup

```python
import asyncio
from arcp import ARCPClient

async def main():
    # Create client instance
    client = ARCPClient("http://localhost:8001")
    
    # Use async context manager for automatic cleanup
    async with client:
        # Check server health
        health = await client.health_check()
        print(f"Server status: {health['status']}")
        
        # Discover agents
        agents = await client.discover_agents()
        print(f"Found {len(agents)} agents")

asyncio.run(main())
```

### Client Configuration

```python
from arcp import ARCPClient

# Configure client with custom settings
client = ARCPClient(
    base_url="http://localhost:8001",
    timeout=30.0,           # Request timeout
    retry_attempts=3,       # Number of retries
    retry_delay=1.0,        # Initial retry delay
    max_retry_delay=60.0,   # Maximum retry delay
    user_agent="MyApp/1.0"  # Custom user agent
)
```

## 🔐 Authentication

### Admin Authentication

```python
async def admin_example():
    client = ARCPClient("http://localhost:8001")
    
    try:
        # Login as admin (credentials may vary by deployment)
        await client.login_admin("ARCP", "ARCP")
        
        # Now you can access admin endpoints
        stats = await client.get_public_stats()
        print(f"System stats: {stats}")
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("Check your admin credentials and server configuration")

asyncio.run(admin_example())
```

### Agent Authentication

```python
async def agent_example():
    client = ARCPClient("http://localhost:8001")
    
    # Request temporary token for agent registration
    temp_token = await client.request_temp_token(
        agent_id="my-agent",
        agent_type="testing",
        agent_key="test-agent-001"
    )
    
    print(f"Temporary token: {temp_token}")
    
    # Use the token for agent operations
    # (Token is automatically used in subsequent requests)

asyncio.run(agent_example())
```

### Token Validation

```python
async def validate_token_example():
    client = ARCPClient("http://localhost:8001")
    
    # Validate a token
    result = await client.validate_token("your-jwt-token")
    print(f"Token valid: {result}")
    
    # Check if client is authenticated
    if client.is_authenticated():
        print("Client is authenticated")
    else:
        print("Client is not authenticated")

asyncio.run(validate_token_example())
```

## 🤖 Agent Management

### Register an Agent

```python
from arcp import AgentRequirements

async def register_agent_example():
    client = ARCPClient("http://localhost:8001")
    
    # Register a new agent
    agent = await client.register_agent(
        agent_id="my-testing-agent",
        name="My Testing Agent",
        agent_type="testing",
        endpoint="https://my-agent.example.com",
        capabilities=["data-processing", "file-conversion", "text-analysis"],
        context_brief="A testing agent for data processing and file conversion",
        version="1.0.0",
        owner="My Organization",
        public_key="my-agent-public-key-that-is-long-enough-32-chars",
        communication_mode="remote",
        metadata={
            "framework": "fastapi",
            "language": "python",
            "deployment": "docker",
            "created_at": "2025-01-XX"
        },
        features=["http-api", "json-responses", "async-processing"],
        max_tokens=2000,
        language_support=["en", "es", "fr"],
        rate_limit=100,
        requirements=AgentRequirements(
            system_requirements=["Python 3.11+", "FastAPI"],
            permissions=["http-server", "file-access"],
            dependencies=["fastapi", "pydantic", "uvicorn"],
            minimum_memory_mb=512,
            requires_internet=True,
            network_ports=["8080"]
        ),
        policy_tags=["testing", "data-processing"],
        agent_key="test-agent-001"
    )
    
    print(f"Agent registered: {agent.name}")
    print(f"Status: {agent.status}")
    print(f"Registered at: {agent.registered_at}")

asyncio.run(register_agent_example())
```

### Get Agent Information

```python
async def get_agent_example():
    client = ARCPClient("http://localhost:8001")
    
    # Get specific agent
    agent = await client.get_agent("my-testing-agent", include_metrics=True)
    print(f"Agent: {agent.name}")
    print(f"Status: {agent.status}")
    print(f"Capabilities: {agent.capabilities}")
    print(f"Metrics: {agent.metrics}")
    
    # List all agents
    agents = await client.list_agents(
        agent_type="testing",
        status="alive",
        include_metrics=True
    )
    
    print(f"Found {len(agents)} testing agents:")
    for agent in agents:
        print(f"  • {agent.name} - {agent.status}")

asyncio.run(get_agent_example())
```

### Update Agent Heartbeat

```python
async def heartbeat_example():
    client = ARCPClient("http://localhost:8001")
    
    # Update heartbeat
    response = await client.update_heartbeat("my-testing-agent")
    print(f"Heartbeat updated: {response}")
    
    # Start automatic heartbeat task
    heartbeat_task = await client.start_heartbeat_task(
        "my-testing-agent",
        interval=30.0  # Update every 30 seconds
    )
    
    # Keep running for 2 minutes
    await asyncio.sleep(120)
    
    # Stop heartbeat task
    heartbeat_task.cancel()
    print("Heartbeat task stopped")

asyncio.run(heartbeat_example())
```

### Update Agent Metrics

```python
async def metrics_example():
    client = ARCPClient("http://localhost:8001")
    
    # Update metrics
    metrics = await client.update_metrics("my-testing-agent", {
        "total_requests": 150,
        "success_rate": 0.98,
        "avg_response_time": 0.25,
        "last_active": "2025-01-XX...",
        "custom_metric": "value"
    })
    
    print(f"Metrics updated: {metrics}")
    
    # Get current metrics
    current_metrics = await client.get_metrics("my-testing-agent")
    print(f"Current metrics: {current_metrics}")

asyncio.run(metrics_example())
```

### Unregister Agent

```python
async def unregister_example():
    client = ARCPClient("http://localhost:8001")
    
    # Unregister agent
    response = await client.unregister_agent("my-testing-agent")
    print(f"Unregistration response: {response}")

asyncio.run(unregister_example())
```

## 🔍 Agent Discovery and Search

### Basic Discovery

```python
async def discovery_example():
    client = ARCPClient("http://localhost:8001")
    
    # Discover all agents
    agents = await client.discover_agents(limit=50)
    print(f"Found {len(agents)} agents")
    
    # Filter by agent type
    testing_agents = await client.discover_agents(
        agent_type="testing",
        limit=10
    )
    print(f"Found {len(testing_agents)} testing agents")
    
    # Filter by capabilities
    data_agents = await client.discover_agents(
        capabilities=["data-processing"],
        limit=10
    )
    print(f"Found {len(data_agents)} data processing agents")

asyncio.run(discovery_example())
```

### Semantic Search

```python
async def search_example():
    client = ARCPClient("http://localhost:8001")
    
    # Basic search
    results = await client.search_agents(
        query="find agents that can process text files",
        top_k=5,
        min_similarity=0.5
    )
    
    print(f"Search results: {len(results)}")
    for result in results:
        print(f"  • {result.name} (similarity: {result.similarity:.3f})")
        print(f"    Capabilities: {', '.join(result.capabilities)}")
    
    # Advanced search with filters
    results = await client.search_agents(
        query="data analysis and visualization",
        top_k=10,
        min_similarity=0.3,
        capabilities=["data-analysis", "visualization"],
        agent_type="testing",
        weighted=True,  # Use reputation scores
        public_api=True  # Use public API (no authentication required)
    )
    
    print(f"Advanced search results: {len(results)}")
    for result in results:
        print(f"  • {result.name} (similarity: {result.similarity:.3f})")
        if result.metrics:
            print(f"    Reputation: {result.metrics.reputation_score:.2f}")

asyncio.run(search_example())
```

### Get Public Agent Information

```python
async def public_agent_example():
    client = ARCPClient("http://localhost:8001")
    
    # Get public agent info (no authentication required)
    agent = await client.get_public_agent("my-testing-agent")
    print(f"Public agent info: {agent.name}")
    print(f"Endpoint: {agent.endpoint}")
    print(f"Capabilities: {agent.capabilities}")

asyncio.run(public_agent_example())
```

## 🔌 Agent Communication

### Request Agent Connection

```python
async def connection_example():
    client = ARCPClient("http://localhost:8001")
    
    # Request connection to an agent
    response = await client.request_agent_connection(
        agent_id="my-testing-agent",
        user_id="user-123",
        user_endpoint="https://my-app.example.com/callback",
        display_name="My Application",
        additional_info={
            "purpose": "data processing",
            "priority": "high",
            "expected_duration": "30 minutes"
        }
    )
    
    print(f"Connection response: {response}")
    print(f"Status: {response.get('status')}")
    print(f"Next steps: {response.get('next_steps')}")

asyncio.run(connection_example())
```

## 📊 System Information

### Health Check

```python
async def health_example():
    client = ARCPClient("http://localhost:8001")
    
    # Check server health
    health = await client.health_check()
    print(f"Server health: {health}")
    
    # Get system information
    info = await client.get_system_info()
    print(f"System info: {info}")
    
    # Get public statistics
    stats = await client.get_public_stats()
    print(f"Public stats: {stats}")
    
    # Get allowed agent types
    agent_types = await client.get_allowed_agent_types()
    print(f"Allowed agent types: {agent_types}")

asyncio.run(health_example())
```

## 🔌 WebSocket Communication

### Public WebSocket

```python
async def public_websocket_example():
    client = ARCPClient("http://localhost:8001")
    
    print("Connecting to public WebSocket...")
    
    message_count = 0
    async for message in client.websocket_public():
        message_count += 1
        print(f"Message {message_count}: {message.get('type', 'unknown')}")
        
        # Process different message types
        if message.get('type') == 'stats_update':
            data = message.get('data', {})
            print(f"  System stats: {data.get('total_agents', 0)} agents")
        elif message.get('type') == 'agents_update':
            data = message.get('data', {})
            print(f"  Agents update: {data.get('total_count', 0)} agents")
        
        # Stop after 10 messages
        if message_count >= 10:
            break
    
    print(f"Received {message_count} messages")

asyncio.run(public_websocket_example())
```

### Agent WebSocket

```python
async def agent_websocket_example():
    client = ARCPClient("http://localhost:8001")
    
    # First authenticate
    await client.login_admin("ARCP", "ARCP")
    
    print("Connecting to agent WebSocket...")
    
    message_count = 0
    async for message in client.websocket_agent():
        message_count += 1
        print(f"Agent message {message_count}: {message}")
        
        # Stop after 5 messages
        if message_count >= 5:
            break
    
    print(f"Received {message_count} agent messages")

asyncio.run(agent_websocket_example())
```

## 🛠️ Advanced Usage Patterns

### Agent Pool Management

```python
class AgentPool:
    def __init__(self, client: ARCPClient, capability: str):
        self.client = client
        self.capability = capability
        self.agents = []
        self.current_index = 0
    
    async def refresh_agents(self):
        """Refresh the list of available agents"""
        results = await self.client.search_agents(
            query=f"agents with {self.capability} capability",
            capabilities=[self.capability],
            weighted=True,
            top_k=10
        )
        
        self.agents = results
        print(f"Refreshed agent pool: {len(self.agents)} agents")
    
    async def get_next_agent(self):
        """Get the next available agent (round-robin)"""
        if not self.agents:
            await self.refresh_agents()
        
        if not self.agents:
            raise Exception(f"No agents available for capability: {self.capability}")
        
        # Round-robin selection
        agent = self.agents[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.agents)
        return agent
    
    async def execute_with_failover(self, request: dict):
        """Execute request with automatic failover"""
        max_retries = len(self.agents)
        
        for attempt in range(max_retries):
            try:
                agent = await self.get_next_agent()
                result = await self.execute_on_agent(agent, request)
                return result
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                
                # Remove failed agent from pool
                if agent in self.agents:
                    self.agents.remove(agent)
                
                if attempt == max_retries - 1:
                    raise Exception(f"All agents failed for capability: {self.capability}")
    
    async def execute_on_agent(self, agent, request: dict):
        """Execute request on specific agent"""
        import httpx
        
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{agent.url}/api/process",
                json=request,
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Agent request failed: {response.status_code}")

# Usage
async def agent_pool_example():
    client = ARCPClient("http://localhost:8001")
    
    # Create agent pool for data processing
    pool = AgentPool(client, "data-processing")
    
    # Execute request with failover
    result = await pool.execute_with_failover({
        "data": "sample data",
        "operation": "process"
    })
    
    print(f"Result: {result}")

asyncio.run(agent_pool_example())
```

### Agent Monitoring

```python
class AgentMonitor:
    def __init__(self, client: ARCPClient):
        self.client = client
        self.agents = {}
        self.monitoring = False
    
    async def start_monitoring(self):
        """Start monitoring agent status"""
        self.monitoring = True
        
        # Start WebSocket monitoring
        async for message in self.client.websocket_public():
            if not self.monitoring:
                break
            
            if message.get('type') == 'agents_update':
                await self.update_agent_status(message.get('data', {}))
    
    async def update_agent_status(self, data: dict):
        """Update agent status from WebSocket message"""
        # This would parse the WebSocket message and update internal state
        print(f"Agent status update: {data}")
    
    async def get_agent_health(self, agent_id: str):
        """Get detailed health information for an agent"""
        try:
            agent = await self.client.get_agent(agent_id, include_metrics=True)
            
            health_info = {
                "agent_id": agent.agent_id,
                "status": agent.status,
                "last_seen": agent.last_seen,
                "metrics": agent.metrics,
                "capabilities": agent.capabilities,
                "endpoint": agent.endpoint
            }
            
            return health_info
        except Exception as e:
            return {"error": str(e)}
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False

# Usage
async def monitoring_example():
    client = ARCPClient("http://localhost:8001")
    monitor = AgentMonitor(client)
    
    # Start monitoring in background
    monitoring_task = asyncio.create_task(monitor.start_monitoring())
    
    # Get health for specific agent
    health = await monitor.get_agent_health("my-testing-agent")
    print(f"Agent health: {health}")
    
    # Stop monitoring after 30 seconds
    await asyncio.sleep(30)
    monitor.stop_monitoring()
    monitoring_task.cancel()

asyncio.run(monitoring_example())
```

### Batch Operations

```python
async def batch_operations_example():
    client = ARCPClient("http://localhost:8001")
    
    # Batch register multiple agents
    agents_to_register = [
        {
            "agent_id": "agent-1",
            "name": "Agent 1",
            "agent_type": "testing",
            "endpoint": "http://agent1.example.com",
            "capabilities": ["processing"],
            "context_brief": "Agent 1 for processing",
            "agent_key": "test-agent-001"
        },
        {
            "agent_id": "agent-2",
            "name": "Agent 2",
            "agent_type": "testing",
            "endpoint": "http://agent2.example.com",
            "capabilities": ["analysis"],
            "context_brief": "Agent 2 for analysis",
            "agent_key": "test-agent-002"
        }
    ]
    
    # Register agents concurrently
    tasks = []
    for agent_data in agents_to_register:
        task = client.register_agent(**agent_data)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Agent {i+1} registration failed: {result}")
        else:
            print(f"Agent {i+1} registered: {result.name}")
    
    # Batch update heartbeats
    agent_ids = ["agent-1", "agent-2"]
    heartbeat_tasks = [
        client.update_heartbeat(agent_id) 
        for agent_id in agent_ids
    ]
    
    heartbeat_results = await asyncio.gather(*heartbeat_tasks, return_exceptions=True)
    
    for i, result in enumerate(heartbeat_results):
        if isinstance(result, Exception):
            print(f"Heartbeat {i+1} failed: {result}")
        else:
            print(f"Heartbeat {i+1} updated: {result}")

asyncio.run(batch_operations_example())
```

## 🧪 Testing

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, patch
from arcp import ARCPClient

@pytest.mark.asyncio
async def test_client_creation():
    """Test client creation"""
    client = ARCPClient("http://localhost:8001")
    assert client.base_url == "http://localhost:8001"
    assert client.timeout == 30.0

@pytest.mark.asyncio
async def test_health_check():
    """Test health check"""
    client = ARCPClient("http://localhost:8001")
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_client.return_value.__aenter__.return_value.request.return_value = mock_response
        
        health = await client.health_check()
        assert health["status"] == "healthy"

@pytest.mark.asyncio
async def test_agent_discovery():
    """Test agent discovery"""
    client = ARCPClient("http://localhost:8001")
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "agent_id": "test-agent",
                "name": "Test Agent",
                "status": "alive"
            }
        ]
        mock_client.return_value.__aenter__.return_value.request.return_value = mock_response
        
        agents = await client.discover_agents()
        assert len(agents) == 1
        assert agents[0].agent_id == "test-agent"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_agent_lifecycle():
    """Test complete agent lifecycle"""
    client = ARCPClient("http://localhost:8001")
    
    try:
        # Register agent
        agent = await client.register_agent(
            agent_id="test-lifecycle-agent",
            name="Test Lifecycle Agent",
            agent_type="testing",
            endpoint="http://localhost:8080",
            capabilities=["test"],
            context_brief="Test agent for lifecycle testing",
            agent_key="test-agent-001"
        )
        
        assert agent.agent_id == "test-lifecycle-agent"
        assert agent.status == "alive"
        
        # Update heartbeat
        heartbeat = await client.update_heartbeat("test-lifecycle-agent")
        assert heartbeat["status"] == "success"
        
        # Update metrics
        metrics = await client.update_metrics("test-lifecycle-agent", {
            "total_requests": 10,
            "success_rate": 1.0
        })
        assert metrics["status"] == "success"
        
        # Get agent
        retrieved_agent = await client.get_agent("test-lifecycle-agent")
        assert retrieved_agent.agent_id == "test-lifecycle-agent"
        
        # Search for agent
        search_results = await client.search_agents("test lifecycle")
        assert len(search_results) > 0
        assert any(r.id == "test-lifecycle-agent" for r in search_results)
        
    finally:
        # Cleanup
        await client.unregister_agent("test-lifecycle-agent")
```

## 🚀 Performance Optimization

### Connection Pooling

```python
import httpx
from arcp import ARCPClient

class OptimizedARCPClient(ARCPClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connection_pool = None
    
    async def _ensure_client(self):
        """Ensure HTTP client with connection pooling"""
        if self._client is None:
            # Create client with connection pooling
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            )
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=limits,
                headers={
                    "User-Agent": self.user_agent,
                    "X-Client-Fingerprint": self._client_fingerprint,
                },
            )
```

### Caching

```python
import asyncio
import time
from typing import Dict, Any, Optional
from arcp import ARCPClient

class CachedARCPClient(ARCPClient):
    def __init__(self, *args, cache_ttl: int = 300, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
    
    def _get_cache_key(self, method: str, **kwargs) -> str:
        """Generate cache key"""
        return f"{method}:{hash(str(sorted(kwargs.items())))}"
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cache entry is valid"""
        return time.time() - timestamp < self.cache_ttl
    
    async def discover_agents(self, *args, **kwargs):
        """Cached agent discovery"""
        cache_key = self._get_cache_key("discover_agents", **kwargs)
        
        if cache_key in self._cache:
            value, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                return value
        
        # Fetch from server
        result = await super().discover_agents(*args, **kwargs)
        
        # Cache result
        self._cache[cache_key] = (result, time.time())
        
        return result
    
    async def search_agents(self, *args, **kwargs):
        """Cached agent search"""
        cache_key = self._get_cache_key("search_agents", **kwargs)
        
        if cache_key in self._cache:
            value, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                return value
        
        # Fetch from server
        result = await super().search_agents(*args, **kwargs)
        
        # Cache result
        self._cache[cache_key] = (result, time.time())
        
        return result
```

## 🆘 Troubleshooting

### Common Issues

#### Rate Limiting
If you encounter rate limiting errors:
```python
import asyncio
from arcp import ARCPClient

async def robust_auth_example():
    client = ARCPClient("http://localhost:8001")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await client.login_admin("ARCP", "ARCP")
            break
        except Exception as e:
            if "rate limit" in str(e).lower() and attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Rate limited, waiting {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                raise e
```

#### Connection Errors

```python
# Handle connection errors gracefully
async def robust_client_example():
    client = ARCPClient("http://localhost:8001")
    
    try:
        health = await client.health_check()
        print(f"Server health: {health}")
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Check if ARCP server is running on http://localhost:8001")
```

#### Authentication Errors

```python
# Handle authentication errors
async def auth_error_example():
    client = ARCPClient("http://localhost:8001")
    
    try:
        await client.login_admin("wrong-username", "wrong-password")
    except Exception as e:
        print(f"Authentication failed: {e}")
        print("Check admin credentials in ARCP configuration")
```

#### Timeout Errors

```python
# Handle timeout errors
async def timeout_example():
    client = ARCPClient(
        "http://localhost:8001",
        timeout=5.0,  # Short timeout for testing
        retry_attempts=2
    )
    
    try:
        agents = await client.discover_agents()
        print(f"Found {len(agents)} agents")
    except Exception as e:
        print(f"Request failed: {e}")
        print("Consider increasing timeout or checking network connectivity")
```

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Create client with debug info
client = ARCPClient("http://localhost:8001")

# All requests will now show detailed debug information
```

## 📚 Next Steps

Now that you understand the client library:

1. **[API Reference](../api-reference/rest-api.md)** - Complete API documentation
2. **[Agent Development Guide](agent-development.md)** - Build agents that use the client
3. **[WebSocket API Reference](../api-reference/websocket-api.md)** - Real-time communication

## 💡 Tips and Best Practices

1. **Use async context managers** - Automatic cleanup and resource management
2. **Handle errors gracefully** - Always catch and handle exceptions
3. **Implement retry logic** - Use the built-in retry mechanisms with exponential backoff
4. **Monitor performance** - Track response times and success rates
5. **Use connection pooling** - For high-throughput applications
6. **Implement caching** - Reduce server load for frequently accessed data
7. **Test thoroughly** - Unit and integration tests are essential
8. **Log appropriately** - Use proper logging levels and formats
9. **Monitor resource usage** - Watch memory and connection usage
10. **Keep clients updated** - Use the latest version for bug fixes and features
11. **Handle rate limiting** - Implement proper delays and backoff strategies
12. **Validate agent types** - Use only supported agent types you wrote in the environment, DEFAULT (security, monitoring, automation, networking, testing)
13. **Use proper public keys** - Ensure public keys are at least 32 characters long

Ready to explore real-time communication? Check out the [WebSocket API Reference](../api-reference/websocket-api.md)!