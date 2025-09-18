# Agent Not Available

**Type URI:** `https://arcp.0x001.tech/docs/problems/agent-not-available`  
**HTTP Status:** `404 Not Found`  
**Title:** Agent Not Available

## Description

This problem occurs when an agent is registered in the ARCP system but is not currently available for connections. The agent exists in the registry but is unreachable, offline, or not responding to health checks.

## When This Occurs

- Agent is registered but has stopped responding
- Agent's endpoint is unreachable (network issues, firewall, etc.)
- Agent has crashed or been terminated without proper deregistration
- Agent is temporarily overloaded and not accepting connections
- Agent failed health checks and is marked as unavailable

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/agent-not-available",
  "title": "Agent Not Available",
  "status": 404,
  "detail": "Agent 'data-processor-01' is registered but currently unavailable",
  "instance": "/public/connect",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_def456",
  "agent_id": "data-processor-01",
  "last_seen": "2024-01-15T09:45:00Z"
}
```

## Common Scenarios

### 1. Connection Request to Unavailable Agent
```bash
curl -X POST "http://localhost:8001/public/connect" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "offline-agent",
    "client_info": {
      "name": "test-client",
      "version": "1.0.0"
    }
  }'
```

### 2. Agent Search Including Unavailable Agents
```bash
curl "http://localhost:8001/public/search" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_ids": ["offline-agent"],
    "include_unavailable": true
  }'
```

## Resolution Steps

### 1. Check Agent Health
```bash
# Direct health check to agent
curl "http://agent-endpoint:8080/health"

# Check if agent endpoint is reachable
ping agent-hostname
telnet agent-hostname 8080
```

### 2. Review Agent Logs
```bash
# Check agent application logs
docker logs my-agent-container

# Or application-specific logs
tail -f /var/log/my-agent/app.log
```

### 3. Restart Agent Service
```bash
# Restart agent service
systemctl restart my-agent

# Or restart Docker container  
docker restart my-agent-container

# Or restart via Docker Compose
docker-compose restart my-agent
```

### 4. Check Network Connectivity
```bash
# Test network path to agent
traceroute agent-hostname

# Check firewall rules
iptables -L

# Verify port is open
nmap -p 8080 agent-hostname
```

### 5. Force Agent Re-registration
If the agent is running but marked unavailable:

```bash
# Make agent re-register (restart agent or trigger registration)
curl -X POST "http://agent-endpoint:8080/internal/reregister"
```

### 6. Manual Agent Cleanup (Admin Only)
If agent is permanently offline:

```bash
curl -X DELETE "http://localhost:8001/agents/offline-agent" \
  -H "Authorization: Bearer <admin-token>"
```

## Prevention

### Agent-Side
- Implement robust health check endpoints
- Send regular heartbeats to ARCP
- Handle graceful shutdown with deregistration
- Monitor resource usage and reject requests when overloaded
- Implement circuit breaker patterns

### ARCP-Side  
- Configure appropriate health check intervals
- Set reasonable timeout values
- Monitor agent availability trends
- Set up alerts for agent downtime

### Client-Side
- Implement retry logic with exponential backoff
- Cache agent availability status
- Have fallback agents for critical operations
- Monitor connection success rates

## Related Problems

- [Agent Not Found](./agent-not-found.md) - Agent doesn't exist in registry
- [Connection Timeout](./connection-timeout.md) - Network connection issues
- [Endpoint Unreachable](./endpoint-unreachable.md) - Network connectivity problems

## API Endpoints That Can Return This

- `POST /public/connect`
- `POST /public/search`  
- `GET /agents/{agent_id}` (when including availability status)