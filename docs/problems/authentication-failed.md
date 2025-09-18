# Authentication Failed

**Type URI:** `https://arcp.0x001.tech/docs/problems/authentication-failed`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Authentication Failed

## Description

This problem occurs when authentication credentials are invalid, missing, or expired. The system cannot verify the identity of the user or agent making the request.

## When This Occurs

- Invalid username/password combination for admin login
- Missing or malformed Authorization header
- Expired JWT tokens
- Invalid agent keys during token request
- Direct agent login attempts (not allowed)
- Missing required client fingerprint header

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/authentication-failed",
  "title": "Authentication Failed",
  "status": 401,
  "detail": "Invalid admin credentials",
  "instance": "/auth/login",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_mno345",
  "error_code": "INVALID_CREDENTIALS"
}
```

## Common Scenarios

### 1. Admin Login with Wrong Credentials
```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: unique-session-id" \
  -d '{
    "username": "admin",
    "password": "wrong-password"
  }'
```

### 2. Missing Authorization Header
```bash
curl "http://localhost:8001/agents" \
  -H "Content-Type: application/json"
```

### 3. Invalid Agent Key for Token Request
```bash
curl -X POST "http://localhost:8001/auth/agent/request_temp_token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing",
    "agent_key": "invalid-key"
  }'
```

### 4. Missing Client Fingerprint
```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "correct-password"
  }'
```

## Resolution Steps

### 1. Verify Credentials
For admin login, check your credentials:

```bash
# Correct admin login
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: $(uuidgen)" \
  -d '{
    "username": "admin",
    "password": "your-admin-password"
  }'
```

### 2. Check Authorization Header Format
Ensure proper Bearer token format:

```bash
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

### 3. Request New Token
If token is expired:

```bash
# For agents: request temp token first
curl -X POST "http://localhost:8001/auth/temp-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing", 
    "agent_key": "valid-agent-key"
  }'

# For admins: login to get new token
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: unique-session-id" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### 4. Verify Agent Key Configuration
Check that your agent key is in the allowed list:

```bash
# Check server configuration (requires admin access)
curl "http://localhost:8001/dashboard/config" \
  -H "Authorization: Bearer <admin-token>"
```

### 5. Include Required Headers
For admin operations, include client fingerprint:

```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: $(date +%s)-$(hostname)" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

## Error Details by Scenario

### Invalid Admin Credentials
```json
{
  "detail": "Invalid admin credentials",
  "error_code": "INVALID_CREDENTIALS"
}
```

### Missing Authorization Header
```json
{
  "detail": "Authentication required - missing or invalid Authorization header",
  "error_code": "AUTH_REQUIRED"
}
```

### Invalid Agent Key
```json
{
  "detail": "Authentication failed: Invalid agent key for agent 'my-agent'",
  "error_code": "INVALID_AGENT_KEY"
}
```

### Direct Agent Login Blocked
```json
{
  "detail": "Direct agent login not allowed. Use agent registration flow with valid agent key",
  "error_code": "AGENT_LOGIN_BLOCKED"
}
```

### Missing Client Fingerprint
```json
{
  "detail": "X-Client-Fingerprint header is required for session binding",
  "error_code": "FINGERPRINT_REQUIRED"
}
```

## Client Implementation

### Python Client Example
```python
import asyncio
from arcp import ARCPClient, AuthenticationError

async def main():
    # Create client instance
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Admin login example
            result = await client.login_admin("admin", "your-password")
            print(f"Admin login successful: {result}")
            
            # Agent temp token request example
            temp_token = await client.request_temp_token(
                agent_id="my-agent",
                agent_type="processing", 
                agent_key="your-agent-key"
            )
            print(f"Temporary token acquired: {temp_token}")
            
        except AuthenticationError as e:
            print(f"Authentication failed: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

# Run the async example
if __name__ == "__main__":
    asyncio.run(main())
```

### JavaScript Client Example
```javascript
class ARCPClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.token = null;
    this.sessionId = crypto.randomUUID();
  }
  
  async loginAdmin(username, password) {
    try {
      const response = await fetch(`${this.baseUrl}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Client-Fingerprint': this.sessionId
        },
        body: JSON.stringify({ username, password })
      });
      
      if (response.ok) {
        const data = await response.json();
        this.token = data.access_token;
        return true;
      } else {
        const error = await response.json();
        console.error('Login failed:', error);
        return false;
      }
    } catch (error) {
      console.error('Login error:', error);
      return false;
    }
  }
}
```

## Security Considerations

1. **Use HTTPS in production** - Never send credentials over HTTP
2. **Generate unique session fingerprints** - Helps prevent session hijacking  
3. **Monitor failed attempts** - Implement rate limiting for login attempts
4. **Rotate agent keys regularly** - Use strong, unique keys for each agent
5. **Set appropriate token expiration** - Balance security with usability

## Prevention

- Store credentials securely (environment variables, secrets management)
- Implement proper token refresh logic
- Use unique client fingerprints for sessions
- Monitor authentication metrics and failures
- Implement retry logic with exponential backoff
- Validate tokens before use

## Related Problems

- [Token Invalid](./token-invalid.md) - Token-specific issues
- [Session Invalid](./session-invalid.md) - Session validation problems
- [Required Header Missing](./required-header-missing.md) - Missing headers
- [Rate Limit Exceeded](./rate-limit-exceeded.md) - Too many auth attempts

## API Endpoints That Can Return This

- `POST /auth/login`
- `POST /auth/agent/request_temp_token`
- `GET /agents` (and other protected endpoints)
- `POST /agents/register`
- Any endpoint requiring authentication