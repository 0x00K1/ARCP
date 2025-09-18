# Required Header Missing

**Type URI:** `https://arcp.0x001.tech/docs/problems/required-header-missing`  
**HTTP Status:** `400 Bad Request`  
**Title:** Required Header Missing

## Description

This problem occurs when a required HTTP header is missing from the request.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/required-header-missing",
  "title": "Required Header Missing",
  "status": 400,
  "detail": "Required header 'X-Client-Fingerprint' is missing",
  "instance": "/auth/login",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_header123",
  "missing_header": "X-Client-Fingerprint"
}
```

## Common Missing Headers

### X-Client-Fingerprint
Required for admin login to bind sessions:

```bash
# Missing header (fails)
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "pass"}'

# With required header (works)
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: unique-session-id" \
  -d '{"username": "admin", "password": "pass"}'
```

### Authorization Header
Required for protected endpoints:

```bash
# Missing auth header (fails)
curl "http://localhost:8001/agents"

# With auth header (works)
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer <token>"
```

## Resolution Steps

### 1. Add Missing Header
Include the required header in your request.

### 2. Check API Documentation
Review endpoint documentation for required headers.

### 3. Using ARCP Client (Headers Managed Automatically)
```python
import asyncio
from arcp import ARCPClient, AuthenticationError

async def header_management_example():
    """ARCP client automatically manages required headers"""
    
    # The client handles all required headers automatically
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Client automatically adds X-Client-Fingerprint and other headers
            await client.login_admin("admin", "your-password")
            print("Login successful - headers handled automatically")
            
            # All subsequent requests include proper headers
            agents = await client.list_agents()
            print(f"Retrieved {len(agents)} agents")
            
        except AuthenticationError as e:
            if "header" in str(e).lower():
                print(f"Header issue: {e}")
                print("This should not happen with the ARCP client as headers are automatic")
            else:
                print(f"Authentication error: {e}")

if __name__ == "__main__":
    asyncio.run(header_management_example())
```