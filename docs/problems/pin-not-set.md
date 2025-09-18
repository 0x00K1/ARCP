# PIN Not Set

**Type URI:** `https://arcp.0x001.tech/docs/problems/pin-not-set`  
**HTTP Status:** `400 Bad Request`  
**Title:** PIN Not Set

## Description

Attempting to verify a PIN when no PIN has been set for the admin session.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/pin-not-set",
  "title": "PIN Not Set",
  "status": 400,
  "detail": "No PIN has been set for this session",
  "instance": "/auth/verify_pin",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pin_not_set123"
}
```

## Resolution

Set a PIN first using `/auth/set_pin` endpoint before attempting verification.