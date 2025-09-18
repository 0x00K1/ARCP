# Operation Timeout

**Type URI:** `https://arcp.0x001.tech/docs/problems/operation-timeout`  
**HTTP Status:** `504 Gateway Timeout`  
**Title:** Operation Timeout

## Description

This problem occurs when an operation takes longer than the configured timeout period to complete.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/operation-timeout",
  "title": "Operation Timeout", 
  "status": 504,
  "detail": "Agent connection timed out after 30 seconds",
  "instance": "/public/connect",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_timeout123",
  "operation": "agent_connection",
  "timeout_seconds": 30
}
```

## Resolution Steps

### 1. Retry Operation
```bash
# Retry the same request
curl -X POST "http://localhost:8001/public/connect" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "slow-agent",
    "client_info": {"name": "test"}
  }'
```

### 2. Check Agent Health
```bash
curl "http://agent-endpoint:8080/health"
```

### 3. Increase Timeout (if possible)
Some operations may allow timeout configuration via query parameters or headers.