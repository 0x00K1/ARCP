# Request Too Large

**Type URI:** `https://arcp.0x001.tech/docs/problems/request-too-large`  
**HTTP Status:** `413 Payload Too Large`  
**Title:** Request Too Large

## Description

The request body exceeds the maximum allowed size limit.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/request-too-large",
  "title": "Request Too Large",
  "status": 413,
  "detail": "Request body size 5MB exceeds limit of 1MB",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_large123",
  "size_limit": "1MB",
  "actual_size": "5MB"
}
```

## Resolution

Reduce the size of your request data or contact administrator about limits.