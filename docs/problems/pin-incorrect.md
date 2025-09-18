# PIN Incorrect

**Type URI:** `https://arcp.0x001.tech/docs/problems/pin-incorrect`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Incorrect PIN

## Description

The provided PIN does not match the PIN set for the admin session.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/pin-incorrect",
  "title": "Incorrect PIN",
  "status": 401,
  "detail": "The provided PIN is incorrect",
  "instance": "/auth/verify_pin",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pin_wrong123"
}
```

## Resolution

Provide the correct PIN that was set for this session.