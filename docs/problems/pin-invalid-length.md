# PIN Invalid Length

**Type URI:** `https://arcp.0x001.tech/docs/problems/pin-invalid-length`  
**HTTP Status:** `400 Bad Request`  
**Title:** Invalid PIN Length

## Description

The PIN does not meet the required length constraints.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/pin-invalid-length",
  "title": "Invalid PIN Length",
  "status": 400,
  "detail": "PIN must be exactly 6 digits",
  "instance": "/auth/set_pin",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pin_length123",
  "required_length": 6,
  "provided_length": 4
}
```

## Resolution

Provide a PIN with the correct length (typically 6 digits).