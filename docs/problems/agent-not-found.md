# Agent Not Found

**Type URI:** `https://arcp.0x001.tech/docs/problems/agent-not-found`  
**HTTP Status:** `404 Not Found`  
**Title:** Agent Not Found

## Description

This problem occurs when a requested agent cannot be found in the ARCP registry. The agent either was never registered, has been unregistered, or the agent ID is incorrect.

## When This Occurs

- Requesting details for an agent that doesn't exist
- Attempting to connect to an unregistered agent
- Using an incorrect or typo'd agent ID
- Agent was recently unregistered but client cache is stale

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/agent-not-found",
  "title": "Agent Not Found", 
  "status": 404,
  "detail": "Agent 'my-missing-agent' not found in registry",
  "instance": "/agents/my-missing-agent",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_abc123",
  "agent_id": "my-missing-agent"
}
```

## Common Scenarios

### 1. Agent Lookup
```bash
curl "http://localhost:8001/agents/nonexistent-agent"
```

### 2. Agent Connection Request  
```bash
curl -X POST "http://localhost:8001/public/connect" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "missing-agent", "client_info": {"name": "test"}}'
```

### 3. Agent Search
```bash
curl "http://localhost:8001/public/search" \
  -H "Content-Type: application/json" \
  -d '{"agent_ids": ["missing-agent"]}'
```

## Resolution Steps

### 1. Verify Agent ID
- Check for typos in the agent ID
- Ensure case sensitivity is correct
- Confirm the agent ID format matches your records

### 2. Check Agent Registration
```bash
# List all registered agents
curl "http://localhost:8001/public/discover"
```

### 3. Re-register Agent (if needed)
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "my-agent",
    "name": "My Agent", 
    "agent_type": "processing",
    "endpoint": "http://localhost:8080",
    "capabilities": ["data-processing"],
    "context_brief": "Data processing agent"
  }'
```

### 4. Check Agent Status
If the agent should exist, check if it's properly running and registered:

```bash
# Check agent heartbeat
curl "http://your-agent-endpoint:8080/health"

# Check ARCP server logs for registration issues
docker logs arcp
```

## Prevention

- Implement proper error handling for agent lookups
- Cache agent lists with appropriate TTL
- Use the public discovery endpoint to get current agent list
- Monitor agent registration status
- Implement agent health monitoring

## Related Problems

- [Agent Not Available](./agent-not-available.md) - Agent exists but is unreachable
- [Agent Registration Failed](./agent-registration-failed.md) - Agent registration issues
- [Not Found](./not-found.md) - Generic resource not found

## API Endpoints That Can Return This

- `GET /agents/{agent_id}` 
- `POST /public/connect`
- `POST /public/search`
- `GET /agents/{agent_id}/metrics`
- `POST /agents/{agent_id}/metrics`