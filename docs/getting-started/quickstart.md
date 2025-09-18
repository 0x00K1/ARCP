# Quick Start Guide

Get ARCP up and running in minutes with this step-by-step guide. We'll start the server, register an agent, and perform some basic operations.

## 🚀 Prerequisites

- Docker and Docker Compose installed
- Basic familiarity with command line
- 5 minutes of your time

## Step 1: Start ARCP Server

### Create Environment Configuration

```bash
# Clone the repository
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Create environment file with required settings
cp .env.example .env
# Also copy to deployment/docker directory for Docker Compose
cp .env.example deployment/docker/.env
# Edit .env files with your configuration (see Configuration section below)
```

### Start the Complete Stack

```bash
# Start all services (ARCP, Redis, Prometheus, Grafana, Jaeger)
docker-compose -f deployment/docker/docker-compose.yml up -d

# Check that all services are running
docker-compose -f deployment/docker/docker-compose.yml ps
```

You should see output like:
```
NAME                IMAGE                    COMMAND                  SERVICE             CREATED             STATUS                    PORTS
arcp                arcp-arcp              "/bin/sh -c 'sh -c \"…"    arcp                2 minutes ago       Up 2 minutes (healthy)   0.0.0.0:8001->8001/tcp
arcp-grafana        grafana/grafana:latest   "sh /entrypoint.sh"      grafana             2 minutes ago       Up 2 minutes (healthy)   0.0.0.0:3000->3000/tcp
arcp-prometheus     prom/prometheus:latest   "/bin/prometheus..."     prometheus          2 minutes ago       Up 2 minutes (healthy)   0.0.0.0:9090->9090/tcp
arcp-redis          redis:7-alpine           "docker-entrypoint..."   redis               2 minutes ago       Up 2 minutes (healthy)   0.0.0.0:6379->6379/tcp
...
```

## Step 2: Verify Installation

### Check ARCP Health

```bash
# Test the health endpoint
curl http://localhost:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-09-06T00:23:56.920083",
  "version": "2.0.0",
  "uptime": "operational",
  "service": "ARCP Registry",
  "features": {
    ...
  },
  "storage": {
    "redis": "connected",
    "backup_storage": "available"
  },
  "ai_services": {
    "azure_openai": "available",
    "embeddings": true
  },
  ...
}
```

### Access the Web Dashboard

Open your browser and go to: **http://localhost:8001/dashboard**

You should see the ARCP dashboard with:
- System status
- Agent registry (empty initially)
- Real-time statistics

### View API Documentation

Visit: **http://localhost:8001/docs**

This shows the interactive Swagger/OpenAPI documentation where you can test all endpoints.

## Step 3: Register Your First Agent

### Using the Python Client

Create a simple Python script to register an agent:

```python
# save as register_agent.py
import asyncio
from arcp import ARCPClient

async def main():
    # Connect to ARCP server
    client = ARCPClient("http://localhost:8001")
    
    try:
        print("Registering agent with ARCP...")
        
        # Register an agent
        agent = await client.register_agent(
            agent_id="my-first-agent",
            name="My First Agent",
            agent_type="testing",
            endpoint="https://my-agent.example.com",
            capabilities=["testing", "demo", "hello-world"],
            context_brief="A simple test agent for learning ARCP",
            version="1.0.0",
            owner="Quick Start User",
            communication_mode="remote",
            agent_key="test-agent-001",  # From your ARCP configuration
            public_key="my-super-secure-public-key-that-is-at-least-32-chars-long",
            metadata={
                "version": "1.0.0",
                "author": "Quick Start User",
                "description": "A simple test agent for learning ARCP",
                "tags": ["demo", "testing", "learning"]
            }
        )
        
        print(f"Agent registered successfully!")
        print(f"   Name: {agent.name}")
        print(f"   ID: {agent.agent_id}")
        print(f"   Status: {agent.status}")
        print(f"   Registered at: {agent.registered_at}")
        
        # Search for our agent
        print("\nSearching for agents...")
        results = await client.search_agents("find test agents")
        
        print(f"Found {len(results)} agents:")
        for result in results:
            print(f"  • {result.name} (similarity: {result.similarity:.3f})")
            print(f"    Capabilities: {', '.join(result.capabilities)}")
        
        # List all agents
        print("\nAll registered agents:")
        agents = await client.discover_agents()
        for agent in agents:
            print(f"  • {agent.name} ({agent.agent_type}) - {agent.status}")
            
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Run the script:

```bash
# Install the ARCP client library
pip install arcp-py

# Run the registration script
python register_agent.py
```

Expected output:
```
Registering agent with ARCP...
Agent registered successfully!
   Name: My First Agent
   ID: my-first-agent
   Status: alive
   Registered at: 2025-09-06 00:33:07.721933

Searching for agents...
Found 1 agents:
  • My First Agent (similarity: 0.805)
    Capabilities: testing, demo, hello-world

All registered agents:
  • My First Agent (testing) - alive
```

## Step 4: Explore the Dashboard

### View Your Agent

1. Go to **http://localhost:8001/dashboard**
2. You should now see your agent in the registry (Offline). For serving an online agent, refer to the **[Agent Development Guide](../user-guide/agent-development.md)**.
3. Click on the agent to see detailed information

### Monitor with Grafana

1. Go to **http://localhost:3000**
2. Navigate to the ARCP dashboard
3. View system metrics

## Step 5: Test Agent Operations

### Update Agent Heartbeat

```python
# save as test_heartbeat.py
import asyncio
from arcp import ARCPClient

async def main():
    client = ARCPClient("http://localhost:8001")
    
    try:
        print("Testing heartbeat functionality...")
        
        # Request fresh authentication token
        token = await client.request_temp_token(
            agent_id="my-first-agent",
            agent_type="testing",
            agent_key="test-agent-001"
        )
        
        # Update heartbeat to keep agent alive
        response = await client.update_heartbeat("my-first-agent")
        print(f"Heartbeat updated: {response}")
        
        # Get agent details
        agent = await client.get_agent("my-first-agent")
        print(f"Agent status: {agent.status}")
        print(f"Last seen: {agent.last_seen}")
        
    except Exception as e:
        print(f"Error: {e}")
        
    finally:
        await client.close()

asyncio.run(main())
```

### Report Agent Metrics

```python
# save as test_metrics.py
import asyncio
import datetime
from arcp import ARCPClient

async def main():
    client = ARCPClient("http://localhost:8001")

    try:
        print("Testing metrics functionality...")

        # Request fresh authentication token
        token = await client.request_temp_token(
            agent_id="my-first-agent",
            agent_type="testing",
            agent_key="test-agent-001"
        )
        
        # Report performance metrics
        metrics_data = {
            "total_requests": 100,
            "success_rate": 0.95,
            "avg_response_time": 0.15,
            "last_active": datetime.datetime.now().isoformat()
        }

        response = await client.update_metrics("my-first-agent", metrics_data)
        print(f"Metrics updated: {response}")

        # Get current metrics
        current_metrics = await client.get_metrics("my-first-agent")
        print(f"Current metrics: {current_metrics}")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await client.close()

asyncio.run(main())
```

## Step 6: Test Real-time Updates

### WebSocket Monitoring

```python
# save as test_websocket.py
import asyncio
from arcp import ARCPClient

async def main():
    client = ARCPClient("http://localhost:8001")
    
    print("Connecting to WebSocket for real-time updates...")
    print("   (This will run for 30 seconds, then exit)")
    
    message_count = 0
    async for message in client.websocket_public():
        message_count += 1
        print(f"Message {message_count}: {message.get('type', 'unknown')}")
        
        # Stop after 30 seconds or 10 messages
        if message_count >= 10:
            break
    
    print(f"Received {message_count} real-time updates")

asyncio.run(main())
```

## Step 7: Clean Up

### Stop the Services

```bash
# Stop all services
docker-compose -f deployment/docker/docker-compose.yml down

# Remove volumes (optional - this will delete all data)
docker-compose -f deployment/docker/docker-compose.yml down -v
```

## 🎉 Congratulations!

You've successfully:

- ✅ Started ARCP with the complete monitoring stack
- ✅ Registered your first agent
- ✅ Performed agent discovery and search
- ✅ Updated agent heartbeat and metrics
- ✅ Tested real-time WebSocket updates
- ✅ Explored the web dashboard and monitoring

## 🚀 Next Steps

Now that you have ARCP running, explore these topics:

### **Agent Development**
- **[Agent Development Guide](../user-guide/agent-development.md)** - Build a real agent that integrates with ARCP
- **[Client Library Guide](../user-guide/client-library.md)** - Master the Python client library

### **Production Setup**
- **[Configuration Guide](configuration.md)** - Customize ARCP for your needs
- **[Monitoring Setup](../deployment/monitoring.md)** - Advanced monitoring

### **Advanced Features**
- **[API Reference](../api-reference/rest-api.md)** - Complete API documentation
- **[WebSocket API Reference](../api-reference/websocket-api.md)** - Real-time communication

## 🆘 Troubleshooting

If you encountered any issues:

1. **Check service status**: `docker-compose -f deployment/docker/docker-compose.yml ps`
2. **View logs**: `docker-compose -f deployment/docker/docker-compose.yml logs arcp`
3. **Verify health**: `curl http://localhost:8001/health`

## 💡 Tips

- **Keep the dashboard open** in a browser tab to see real-time updates
- **Use the API docs** at http://localhost:8001/docs to explore endpoints
- **Check Grafana** at http://localhost:3000 for detailed metrics
- **Monitor logs** with `docker-compose logs -f arcp` for debugging

Ready to build something amazing with ARCP? Explore the [API Reference](../api-reference/rest-api.md) to get started!