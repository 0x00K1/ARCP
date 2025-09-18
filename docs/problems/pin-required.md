# PIN Required

**Type URI:** `https://arcp.0x001.tech/docs/problems/pin-required`  
**HTTP Status:** `400 Bad Request`  
**Title:** PIN Required

## Description

This problem occurs when attempting to access a high-security operation that requires PIN verification, but no PIN has been verified for the current admin session.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/pin-required",
  "title": "PIN Required",
  "status": 400,
  "detail": "PIN verification required for this operation",
  "instance": "/agents/agent-id",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pin123"
}
```

## Resolution Steps

### 1. Verify PIN
```bash
curl -X POST "http://localhost:8001/auth/verify_pin" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"pin": "123456"}'
```

### 2. Then Perform Protected Operation
```bash
curl -X DELETE "http://localhost:8001/agents/agent-id" \
  -H "Authorization: Bearer <admin-token>"
```