# Forbidden

**Type URI:** `https://arcp.0x001.tech/docs/problems/forbidden`  
**HTTP Status:** `403 Forbidden`  
**Title:** Forbidden

## Description

Generic forbidden access error when access to a resource is explicitly denied.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access to this resource is forbidden",
  "instance": "/dashboard/config",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_forbidden123"
}
```

## Resolution

Check authentication and permissions. Use appropriate credentials for the resource.