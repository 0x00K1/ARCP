# Token Invalid/Expired

**Type URI:** `https://arcp.0x001.tech/docs/problems/token-invalid`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Invalid or Expired Token

## Description

This problem occurs when a JWT token is malformed, expired, or otherwise invalid. The token cannot be verified and authenticated requests fail.

## When This Occurs

- JWT token has expired
- Token signature verification fails
- Token format is malformed or corrupted
- Token was issued by a different system
- Token payload is missing required claims
- System clock skew causing premature expiration

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/token-invalid",
  "title": "Invalid or Expired Token",
  "status": 401,
  "detail": "JWT token has expired at 2024-01-15T09:30:00Z",
  "instance": "/agents",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_pqr678",
  "token_issued_at": "2024-01-15T08:30:00Z",
  "token_expired_at": "2024-01-15T09:30:00Z",
  "error_code": "TOKEN_EXPIRED"
}
```

## Common Scenarios

### 1. Expired Token
```bash
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZ2VudC0wMDEiLCJleHAiOjE3MDUzOTk4MDB9.signature"
```

### 2. Malformed Token
```bash
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer invalid.token.format"
```

### 3. Token Validation
```bash
curl -X POST "http://localhost:8001/auth/validate" \
  -H "Content-Type: application/json" \
  -d '{"token": "expired-or-invalid-token"}'
```

## Token Error Types

### Expired Token
```json
{
  "detail": "JWT token has expired at 2024-01-15T09:30:00Z",
  "error_code": "TOKEN_EXPIRED",
  "token_expired_at": "2024-01-15T09:30:00Z"
}
```

### Invalid Signature
```json
{
  "detail": "JWT token signature verification failed",
  "error_code": "INVALID_SIGNATURE"
}
```

### Malformed Token
```json
{
  "detail": "JWT token format is invalid",
  "error_code": "MALFORMED_TOKEN"
}
```

### Missing Claims
```json
{
  "detail": "JWT token is missing required claims",
  "error_code": "MISSING_CLAIMS",
  "missing_claims": ["agent_id", "scopes"]
}
```

## Resolution Steps

### 1. Request New Token (Agent)
```bash
curl -X POST "http://localhost:8001/auth/temp-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing",
    "agent_key": "valid-agent-key"
  }'
```

### 2. Request New Token (Admin)
```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: unique-session-id" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### 3. Validate Current Token
```bash
curl -X POST "http://localhost:8001/auth/validate" \
  -H "Content-Type: application/json" \
  -d '{"token": "your-current-token"}'
```

### 4. Check Token Expiration
Use the ARCP client to validate tokens:

```python
import asyncio
from arcp import ARCPClient, AuthenticationError

async def check_token_validity(token: str = None):
    """Check if current or provided token is valid"""
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Validate the current token or a specific token
            validation_result = await client.validate_token(token)
            print(f"Token is valid: {validation_result}")
            return True
            
        except AuthenticationError as e:
            print(f"Token validation failed: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during validation: {e}")
            return False

# Example usage
if __name__ == "__main__":
    # Check current client token
    result = asyncio.run(check_token_validity())
    
    # Or check a specific token
    # result = asyncio.run(check_token_validity("your-token-here"))
```

### 5. Refresh Token Logic
Use the ARCP client's built-in token management:

```python
import asyncio
from arcp import ARCPClient, AuthenticationError

class TokenManagedClient:
    """Wrapper for ARCP client with automatic token refresh"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = ARCPClient(base_url)
        self._agent_credentials = None
        self._admin_credentials = None
    
    def set_agent_credentials(self, agent_id: str, agent_type: str, agent_key: str):
        """Store agent credentials for automatic token refresh"""
        self._agent_credentials = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "agent_key": agent_key
        }
    
    def set_admin_credentials(self, username: str, password: str):
        """Store admin credentials for automatic token refresh"""
        self._admin_credentials = {
            "username": username,
            "password": password
        }
    
    async def ensure_valid_token(self):
        """Ensure we have a valid token, refresh if needed"""
        try:
            # Try to validate current token
            await self.client.validate_token()
            return True
            
        except AuthenticationError:
            # Token is invalid, try to refresh
            if self._agent_credentials:
                await self.client.request_temp_token(**self._agent_credentials)
            elif self._admin_credentials:
                await self.client.login_admin(**self._admin_credentials)
            else:
                raise AuthenticationError("No credentials available for token refresh")
            
            return True
    
    async def safe_request(self, operation_func, *args, **kwargs):
        """Perform operation with automatic token refresh"""
        try:
            return await operation_func(*args, **kwargs)
        except AuthenticationError:
            await self.ensure_valid_token()
            return await operation_func(*args, **kwargs)

# Example usage
async def example_with_auto_refresh():
    client = TokenManagedClient("http://localhost:8001")
    client.set_agent_credentials("my-agent", "processing", "agent-key")
    
    # This will automatically refresh token if needed
    await client.ensure_valid_token()
    
    # Use the client normally
    agents = await client.safe_request(client.client.list_agents)
    print(f"Found {len(agents)} agents")
```

## Client Implementation

### Using the ARCP Client with Error Handling
```python
import asyncio
from arcp import ARCPClient, AuthenticationError, ARCPError

async def robust_client_operations():
    """Example of using ARCP client with proper error handling"""
    async with ARCPClient("http://localhost:8001") as client:
        
        # Agent authentication example
        try:
            temp_token = await client.request_temp_token(
                agent_id="my-agent",
                agent_type="processing",
                agent_key="your-agent-key"
            )
            print("Agent authenticated successfully")
            
            # Perform operations that might fail due to token issues
            agents = await client.list_agents()
            print(f"Retrieved {len(agents)} agents")
            
            # Register or update agent
            agent_info = await client.register_agent(
                agent_id="my-agent",
                name="My Processing Agent", 
                agent_type="processing",
                endpoint="http://localhost:8080",
                capabilities=["data-processing"],
                context_brief="Processes incoming data",
                version="1.0.0",
                owner="system@example.com",
                public_key="your-public-key",
                communication_mode="remote",
                agent_key="your-agent-key"
            )
            print(f"Agent registration completed: {agent_info.agent_id}")
            
        except AuthenticationError as e:
            print(f"Authentication failed: {e}")
            # Handle auth errors - maybe retry with fresh credentials
            
        except ARCPError as e:
            print(f"ARCP operation failed: {e}")
            # Handle other ARCP-specific errors
            
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(robust_client_operations())
```

### Token Validation (JavaScript)
```javascript
class TokenManager {
  constructor() {
    this.token = localStorage.getItem('arcp_token');
  }
  
  isTokenExpired(token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const now = Math.floor(Date.now() / 1000);
      return payload.exp < now;
    } catch {
      return true;
    }
  }
  
  async getValidToken() {
    if (!this.token || this.isTokenExpired(this.token)) {
      await this.refreshToken();
    }
    return this.token;
  }
  
  async refreshToken() {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: this.username,
        password: this.password
      })
    });
    
    if (response.ok) {
      const data = await response.json();
      this.token = data.access_token;
      localStorage.setItem('arcp_token', this.token);
    }
  }
}
```

## Best Practices

### 1. Proactive Token Refresh
Refresh tokens before they expire:

```python
# Refresh 5 minutes before expiration
REFRESH_BUFFER = 300

def should_refresh_token(token):
    payload = jwt.decode(token, options={"verify_signature": False})
    exp_time = payload.get('exp', 0)
    return time.time() + REFRESH_BUFFER >= exp_time
```

### 2. Handle Token Refresh Failures
```python
def robust_api_call(client, method, endpoint, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client._make_request(method, endpoint)
            if response.status_code != 401:
                return response
            
            # Token issue - try to refresh
            if not client.refresh_token():
                break
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)  # Exponential backoff
    
    raise Exception("Failed to complete API call after token refresh attempts")
```

### 3. Secure Token Storage
```python
import keyring
from cryptography.fernet import Fernet

class SecureTokenStorage:
    def __init__(self, service_name):
        self.service_name = service_name
        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)
    
    def store_token(self, token):
        encrypted_token = self.cipher.encrypt(token.encode())
        keyring.set_password(self.service_name, "token", encrypted_token.decode())
    
    def get_token(self):
        encrypted_token = keyring.get_password(self.service_name, "token")
        if encrypted_token:
            return self.cipher.decrypt(encrypted_token.encode()).decode()
        return None
```

## Related Problems

- [Authentication Failed](./authentication-failed.md) - General auth issues
- [Session Expired](./session-expired.md) - Session-level expiration
- [Session Invalid](./session-invalid.md) - Session validation problems

## API Endpoints That Can Return This

- Any authenticated endpoint when token is invalid
- `POST /auth/validate`
- `GET /agents`
- `POST /agents/register`
- `GET /dashboard/*` endpoints