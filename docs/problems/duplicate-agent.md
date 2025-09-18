# Duplicate Agent

**Type URI:** `https://arcp.0x001.tech/docs/problems/duplicate-agent`  
**HTTP Status:** `409 Conflict`  
**Title:** Duplicate Agent

## Description

This problem occurs when attempting to register an agent with an ID that is already in use by another registered agent. Each agent in the ARCP system must have a unique agent ID.

## When This Occurs

- Registering an agent with an existing agent ID
- Multiple instances of the same agent trying to register simultaneously  
- Agent restart without proper deregistration of previous instance
- Configuration error with duplicate agent IDs
- Race condition during bulk agent registration

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/duplicate-agent",
  "title": "Duplicate Agent",
  "status": 409,
  "detail": "Agent with ID 'data-processor-01' is already registered",
  "instance": "/agents/register", 
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_ghi789",
  "agent_id": "data-processor-01",
  "existing_agent_endpoint": "http://10.0.1.50:8080",
  "registration_timestamp": "2024-01-15T08:15:00Z"
}
```

## Common Scenarios

### 1. Agent Registration Conflict
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "existing-agent",
    "name": "My Agent",
    "agent_type": "processing",
    "endpoint": "http://localhost:8080",
    "capabilities": ["data-processing"],
    "context_brief": "Data processing agent"
  }'
```

### 2. Agent Restart Without Cleanup
When an agent restarts and tries to re-register without the previous instance being properly deregistered.

## Resolution Steps

### 1. Check Existing Agent Status
```bash
# Check if agent is still active
curl "http://localhost:8001/agents/duplicate-agent-id"

# Check agent endpoint directly
curl "http://existing-agent-endpoint:8080/health"
```

### 2. Use Different Agent ID
If you're registering a new agent:

```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "data-processor-02",  # Use unique ID
    "name": "My Agent Instance 2",
    "agent_type": "processing", 
    "endpoint": "http://localhost:8081",
    "capabilities": ["data-processing"],
    "context_brief": "Data processing agent instance 2"
  }'
```

### 3. Deregister Existing Agent (If Appropriate)
If the existing agent is no longer valid:

```bash
# Admin deregistration
curl -X DELETE "http://localhost:8001/agents/duplicate-agent-id" \
  -H "Authorization: Bearer <admin-token>"
```

### 4. Force Re-registration (For Same Agent)
If this is the same agent restarting:

```bash
# First deregister the old instance
curl -X DELETE "http://localhost:8001/agents/my-agent-id" \
  -H "Authorization: Bearer <admin-token>"

# Then register the new instance
curl -X POST "http://localhost:8001/agents/register" \
  -H "Authorization: Bearer <agent-token>" \
  # ... registration data
```

### 5. Check Agent Configuration
Review your agent configuration to ensure unique IDs:

```yaml
# agent-config.yaml
agent:
  id: "unique-agent-${HOSTNAME}-${RANDOM_SUFFIX}"
  name: "Processing Agent"
  type: "data-processor"
```

## Prevention Strategies

### 1. Use Dynamic Agent IDs
Generate unique agent IDs:

```python
import asyncio
import uuid
import socket
import time
import os
from arcp import ARCPClient

async def generate_unique_agent_id():
    """Generate unique agent ID using various methods"""
    
    # Method 1: UUID-based
    uuid_id = f"agent-{uuid.uuid4().hex[:8]}"
    
    # Method 2: Hostname + timestamp
    hostname_id = f"agent-{socket.gethostname()}-{int(time.time())}"
    
    # Method 3: Environment-based (useful in containers)
    env_id = f"agent-{os.environ.get('POD_NAME', socket.gethostname())}-{uuid.uuid4().hex[:4]}"
    
    # Choose one method or combine them
    return uuid_id  # Most recommended for uniqueness
```

### 2. Implement Graceful Shutdown
Ensure agents deregister on shutdown:

```python
import asyncio
import atexit
import signal
import logging
from arcp import ARCPClient, ARCPError

logger = logging.getLogger(__name__)

class GracefulAgent:
    def __init__(self, base_url: str, agent_id: str):
        self.client = ARCPClient(base_url)
        self.agent_id = agent_id
        self._registered = False
    
    async def register(self, **agent_data):
        """Register the agent"""
        try:
            await self.client.register_agent(
                agent_id=self.agent_id,
                **agent_data
            )
            self._registered = True
            logger.info(f"Agent {self.agent_id} registered successfully")
        except Exception as e:
            logger.error(f"Failed to register agent: {e}")
            raise
    
    async def cleanup(self):
        """Deregister agent on shutdown"""
        if self._registered:
            try:
                # Note: Implement deregister method in the client
                # await self.client.deregister_agent(self.agent_id)
                logger.info(f"Agent {self.agent_id} deregistered")
            except ARCPError as e:
                logger.error(f"Failed to deregister: {e}")
            finally:
                await self.client.close()

# Global agent instance for cleanup
_agent_instance = None

def cleanup_handler():
    """Cleanup handler for graceful shutdown"""
    if _agent_instance:
        asyncio.run(_agent_instance.cleanup())

# Register cleanup handlers
atexit.register(cleanup_handler)
signal.signal(signal.SIGTERM, lambda s, f: cleanup_handler())
signal.signal(signal.SIGINT, lambda s, f: cleanup_handler())
```

### 3. Health Check Before Registration
Check if agent ID is available:

```python
import asyncio
from arcp import ARCPClient, ARCPError

async def safe_register_agent(agent_id: str, agent_data: dict):
    """Safely register agent after checking for duplicates"""
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # First, try to get the agent to see if it exists
            existing_agent = await client.get_agent(agent_id)
            
            if existing_agent:
                print(f"Warning: Agent {agent_id} already exists")
                
                # Check if the existing agent is still alive
                try:
                    # You could implement a health check here
                    # For now, we'll assume we want to use a different ID
                    import uuid
                    new_agent_id = f"{agent_id}-{uuid.uuid4().hex[:4]}"
                    print(f"Using alternative ID: {new_agent_id}")
                    agent_data['agent_id'] = new_agent_id
                    agent_id = new_agent_id
                except Exception:
                    pass
                    
        except ARCPError as e:
            # If agent is not found, that's good - we can proceed
            if "not found" in str(e).lower():
                print(f"Agent ID {agent_id} is available")
            else:
                raise
        
        # Proceed with registration
        try:
            result = await client.register_agent(**agent_data)
            print(f"Agent {agent_id} registered successfully")
            return result
            
        except Exception as e:
            print(f"Registration failed: {e}")
            raise
```

### 4. Container/Docker Considerations

```yaml
# docker-compose.yml
version: '3.8'
services:
  agent:
    image: your-agent-image:latest
    container_name: agent
    environment:
      HOSTNAME: "${HOSTNAME}"
      AGENT_ID: "agent-${HOSTNAME}"
```

## Best Practices

1. **Use meaningful but unique IDs**: `data-processor-${instance}-${timestamp}`
2. **Implement proper shutdown sequences**: Always deregister on exit
3. **Monitor for duplicate registrations**: Alert on registration conflicts  
4. **Use health checks**: Verify existing agents are still alive
5. **Document agent ID conventions**: Establish naming patterns

## Related Problems

- [Agent Registration Failed](./agent-registration-failed.md) - General registration issues
- [Agent Not Found](./agent-not-found.md) - Agent doesn't exist  
- [Configuration Error](./configuration-error.md) - Configuration problems

## API Endpoints That Can Return This

- `POST /agents/register`