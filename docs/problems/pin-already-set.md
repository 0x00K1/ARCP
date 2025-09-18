# PIN Already Set

**Type URI:** `https://arcp.0x001.tech/docs/problems/pin-already-set`  
**HTTP Status:** `400 Bad Request`  
**Title:** PIN Already Set

## Description

Attempting to set a PIN when one is already configured for the admin session.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/pin-already-set",
  "title": "PIN Already Set",
  "status": 400,
  "detail": "PIN is already set for this session",
  "instance": "/auth/set_pin",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pin_set123"
}
```

## Resolution

Use existing PIN or reset session to set a new one.