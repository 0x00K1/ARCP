# Not Found

**Type URI:** `https://arcp.0x001.tech/docs/problems/not-found`  
**HTTP Status:** `404 Not Found`  
**Title:** Resource Not Found

## Description

This problem occurs when a requested resource cannot be found. This is a generic "not found" error for resources other than agents.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/not-found",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "The requested resource '/invalid/endpoint' was not found",
  "instance": "/invalid/endpoint",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_404_123"
}
```

## Common Scenarios

### 1. Invalid Endpoint Path
```bash
curl "http://localhost:8001/nonexistent/endpoint"
```

### 2. Resource ID Not Found
```bash
curl "http://localhost:8001/tokens/invalid-token-id"
```

## Resolution Steps

### 1. Verify URL Path
Check the API documentation for correct endpoint paths.

### 2. Check Resource ID
Ensure the resource identifier is correct and exists.

### 3. Review Available Endpoints
```bash
# Check API documentation or available endpoints
curl "http://localhost:8001/health"
```