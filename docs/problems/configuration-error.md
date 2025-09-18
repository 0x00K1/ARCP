# Configuration Error

**Type URI:** `https://arcp.0x001.tech/docs/problems/configuration-error`  
**HTTP Status:** `500 Internal Server Error`  
**Title:** Service Configuration Error

## Description

A configuration issue prevents the service from operating correctly.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/configuration-error",
  "title": "Service Configuration Error",
  "status": 500,
  "detail": "Admin authentication not properly configured",
  "instance": "/auth/login",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_config123"
}
```

## Common Issues

- Missing environment variables
- Invalid configuration values
- Database connection settings
- Missing required services

## Resolution

Contact system administrator to review service configuration.