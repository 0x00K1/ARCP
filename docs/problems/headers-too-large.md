# Request Headers Too Large

**Type URI:** `https://arcp.0x001.tech/docs/problems/headers-too-large`  
**HTTP Status:** `413 Payload Too Large`  
**Title:** Request Headers Too Large

## Description

The HTTP request headers exceed the maximum allowed size limit.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/headers-too-large",
  "title": "Request Headers Too Large",
  "status": 413,
  "detail": "Request headers size exceeds maximum allowed limit",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_headers_large123"
}
```

## Resolution

Reduce the size of HTTP headers, remove unnecessary headers, or contact administrator about limits.