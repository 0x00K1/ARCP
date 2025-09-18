# Connection Timeout

**Type URI:** `https://arcp.0x001.tech/docs/problems/connection-timeout`  
**HTTP Status:** `504 Gateway Timeout`  
**Title:** Connection Timeout

## Description

This problem occurs when ARCP cannot establish a network connection to an external service (like an agent endpoint) within the timeout period.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/connection-timeout",
  "title": "Connection Timeout",
  "status": 504, 
  "detail": "Connection to agent endpoint timed out",
  "instance": "/public/connect",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_conn123",
  "target_endpoint": "http://agent.example.com:8080",
  "timeout_seconds": 10
}
```

## Resolution Steps

### 1. Check Network Connectivity
```bash
# Test connectivity to agent
ping agent.example.com
telnet agent.example.com 8080
```

### 2. Verify Agent Status
```bash
# Direct health check
curl "http://agent.example.com:8080/health"
```

### 3. Check Firewall/Security Groups
Ensure network path allows connections on the required ports.