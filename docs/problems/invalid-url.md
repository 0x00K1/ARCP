# Invalid URL Format

**Type URI:** `https://arcp.0x001.tech/docs/problems/invalid-url`  
**HTTP Status:** `400 Bad Request`  
**Title:** Invalid URL Format

## Description

The provided URL does not have a valid format.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/invalid-url",
  "title": "Invalid URL Format",
  "status": 400,
  "detail": "Invalid URL format - must be http:// or https://",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_url123",
  "invalid_url": "ftp://example.com",
  "expected_schemes": ["http", "https"]
}
```

## Resolution

Use a valid HTTP or HTTPS URL format.