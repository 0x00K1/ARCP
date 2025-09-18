# Endpoint Unreachable

**Type URI:** `https://arcp.0x001.tech/docs/problems/endpoint-unreachable`  
**HTTP Status:** `502 Bad Gateway`  
**Title:** Endpoint Unreachable

## Description

This problem occurs when ARCP cannot reach a target endpoint (typically an agent endpoint) due to network connectivity issues.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/endpoint-unreachable",
  "title": "Endpoint Unreachable",
  "status": 502,
  "detail": "Cannot connect to agent endpoint http://agent.example.com:8080",
  "instance": "/public/connect",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_unreachable123",
  "target_endpoint": "http://agent.example.com:8080",
  "error_details": "Connection refused"
}
```

## Common Causes

- Agent is offline or crashed
- Network connectivity issues
- Firewall blocking connections
- Incorrect endpoint URL
- DNS resolution problems

## Resolution Steps

### 1. Test Direct Connectivity
```bash
# Test if endpoint is reachable
ping agent.example.com
telnet agent.example.com 8080

# Check DNS resolution
nslookup agent.example.com

# Test HTTP connectivity
curl "http://agent.example.com:8080/health"
```

### 2. Verify Agent Status
```bash
# Check if agent process is running
ps aux | grep agent-process

# Check Docker container status
docker ps | grep agent

# Check service status
systemctl status my-agent-service
```

### 3. Check Network Configuration
```bash
# Check firewall rules
iptables -L
ufw status

# Check network routes
ip route show

# Test from ARCP server
docker exec arcp curl http://agent.example.com:8080/health
```

### 4. Update Endpoint Configuration
If the agent's endpoint has changed:

```bash
# Update agent registration with new endpoint
curl -X POST "http://localhost:8001/agents/register" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "my-agent",
    "endpoint": "http://new-address:8080",
    ...
  }'
```