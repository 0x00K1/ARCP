# Session Invalid

**Type URI:** `https://arcp.0x001.tech/docs/problems/session-invalid`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Session Validation Failed

## Description

This problem occurs when session validation fails due to missing session data, fingerprint mismatch, or session inconsistencies. Sessions are used for admin users to bind tokens to specific browser sessions.

## When This Occurs

- Session fingerprint doesn't match stored fingerprint
- Session data is missing or corrupted
- Multiple concurrent sessions with same credentials
- Session storage system is unavailable
- Client fingerprint header changed mid-session

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/session-invalid",
  "title": "Session Validation Failed",
  "status": 401,
  "detail": "Session fingerprint mismatch - please re-authenticate",
  "instance": "/agents",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_stu901",
  "session_id": "sess_abc123",
  "error_code": "SESSION_INVALID"
}
```

## Resolution Steps

### 1. Re-authenticate with Proper Headers
```bash
# Login with consistent client fingerprint
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: my-browser-session-123" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### 2. Use Same Fingerprint for Subsequent Requests
```bash
# Use the same fingerprint from login
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer <token>" \
  -H "X-Client-Fingerprint: my-browser-session-123"
```

### 3. Using ARCP Client with Session Management
```python
import asyncio
from arcp import ARCPClient, AuthenticationError

async def session_management_example():
    """Example of proper session handling with ARCP client"""
    
    # The ARCP client handles session fingerprints automatically
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Admin login - client handles fingerprint generation
            result = await client.login_admin("admin", "your-password")
            print("Login successful - session established")
            
            # Subsequent operations use the same session
            agents = await client.list_agents()
            print(f"Retrieved {len(agents)} agents in same session")
            
            # Session is maintained across operations
            stats = await client.get_system_stats()
            print("System stats retrieved successfully")
            
        except AuthenticationError as e:
            if "session" in str(e).lower() or "fingerprint" in str(e).lower():
                print(f"Session invalid: {e}")
                print("The client will automatically handle session recreation")
            else:
                print(f"Authentication error: {e}")
        
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(session_management_example())
```

## Related Problems

- [Session Expired](./session-expired.md) - Session timeout issues
- [Authentication Failed](./authentication-failed.md) - Auth problems
- [Required Header Missing](./required-header-missing.md) - Missing fingerprint header