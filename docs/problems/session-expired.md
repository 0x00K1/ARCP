# Session Expired

**Type URI:** `https://arcp.0x001.tech/docs/problems/session-expired`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Session Expired

## Description

This problem occurs when an admin user's session has exceeded the configured timeout period. Sessions automatically expire after a period of inactivity to maintain security.

## When This Occurs

- Session has been idle longer than SESSION_TIMEOUT
- Session data cleanup removed expired sessions
- System restart cleared session storage
- Clock changes affected session timing

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/session-expired",
  "title": "Session Expired", 
  "status": 401,
  "detail": "Admin session has expired after 60 minutes of inactivity",
  "instance": "/dashboard/config",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_vwx234",
  "session_timeout": 3600,
  "error_code": "SESSION_EXPIRED"
}
```

## Resolution Steps

### 1. Re-authenticate
```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: new-session-id" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### 2. Session Refresh with ARCP Client
```python
import asyncio
import time
from arcp import ARCPClient, AuthenticationError

class SessionManager:
    """Manages ARCP client session with automatic refresh"""
    
    def __init__(self, base_url: str):
        self.client = ARCPClient(base_url)
        self.admin_credentials = None
        self.last_activity = None
        self.session_timeout = 3600  # 1 hour default
    
    def set_admin_credentials(self, username: str, password: str):
        """Store admin credentials for automatic session refresh"""
        self.admin_credentials = {"username": username, "password": password}
    
    def is_session_expired(self) -> bool:
        """Check if session might be expired based on local timing"""
        if not self.last_activity:
            return True
        return time.time() - self.last_activity > self.session_timeout
    
    async def ensure_valid_session(self) -> bool:
        """Ensure we have a valid session, refresh if needed"""
        if self.is_session_expired() or not self.client._access_token:
            if not self.admin_credentials:
                raise AuthenticationError("No credentials for session refresh")
            
            try:
                await self.client.login_admin(**self.admin_credentials)
                self.last_activity = time.time()
                print("Session refreshed successfully")
                return True
            except Exception as e:
                print(f"Session refresh failed: {e}")
                raise
        
        self.last_activity = time.time()
        return True
    
    async def make_authenticated_request(self, operation_func, *args, **kwargs):
        """Make request with automatic session management"""
        await self.ensure_valid_session()
        try:
            return await operation_func(*args, **kwargs)
        except AuthenticationError as e:
            if "session" in str(e).lower() or "expired" in str(e).lower():
                # Force refresh and retry once
                self.last_activity = 0  # Force refresh
                await self.ensure_valid_session()
                return await operation_func(*args, **kwargs)
            raise

# Usage example
async def session_refresh_example():
    session_mgr = SessionManager("http://localhost:8001")
    session_mgr.set_admin_credentials("admin", "your-password")
    
    try:
        # Operations that might experience session expiry
        stats = await session_mgr.make_authenticated_request(
            session_mgr.client.get_system_stats
        )
        print("System stats retrieved successfully")
        
        # Simulate long delay that might cause session expiry
        await asyncio.sleep(1)  # In real usage this would be much longer
        
        metrics = await session_mgr.make_authenticated_request(
            session_mgr.client.get_system_metrics
        )
        print("System metrics retrieved successfully")
        
    finally:
        await session_mgr.client.close()

if __name__ == "__main__":
    asyncio.run(session_refresh_example())
```

## Related Problems

- [Session Invalid](./session-invalid.md) - Session validation issues
- [Token Invalid](./token-invalid.md) - Token expiration