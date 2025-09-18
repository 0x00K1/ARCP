# Request Processing Error

**Type URI:** `https://arcp.0x001.tech/docs/problems/request-error`  
**HTTP Status:** `400 Bad Request`  
**Title:** Request Processing Error

## Description

A general error occurred while processing the request that doesn't fit other specific problem types.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/request-error",
  "title": "Request Processing Error",
  "status": 400,
  "detail": "Unable to process request due to data format issues",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_error123"
}
```

## Resolution

Review request format and data according to API documentation.