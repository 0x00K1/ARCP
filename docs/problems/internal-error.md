# Internal Error

**Type URI:** `https://arcp.0x001.tech/docs/problems/internal-error`  
**HTTP Status:** `500 Internal Server Error`  
**Title:** Internal Server Error

## Description

This problem occurs when an unexpected error happens within the ARCP system that prevents the request from being processed successfully.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred while processing the request",
  "instance": "/agents/register", 
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_err123",
  "error_code": "INTERNAL_ERROR"
}
```

## When This Occurs

- Database connection failures
- Unexpected exceptions in business logic
- System resource exhaustion
- Configuration errors
- Third-party service failures

## Resolution Steps

### 1. Check System Status
```bash
# Check ARCP health
curl "http://localhost:8001/health"

# Check system resources
docker stats arcp
```

### 2. Review Logs
```bash
# Check application logs
docker logs arcp

# Check system logs  
journalctl -u arcp
```

### 3. Retry Request
Internal errors are often transient:

```bash
# Wait a moment and retry
sleep 5
curl -X POST "http://localhost:8001/agents/register" \
  -H "Authorization: Bearer <token>" \
  # ... request data
```

### 4. Contact Support
If the error persists, contact system administrators with:
- Request ID from the error response
- Timestamp of the error
- Full error response
- Steps to reproduce