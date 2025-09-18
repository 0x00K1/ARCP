# Insufficient Permissions

**Type URI:** `https://arcp.0x001.tech/docs/problems/insufficient-permissions`  
**HTTP Status:** `403 Forbidden`  
**Title:** Insufficient Permissions

## Description

This problem occurs when an authenticated user or agent lacks the required permissions to access a specific resource or perform an operation. Authentication succeeded, but authorization failed.

## When This Occurs

- Agent trying to access admin endpoints
- User without admin role accessing protected resources
- Missing required scopes in JWT token
- Permission level too low for operation
- PIN verification required but not provided

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/insufficient-permissions",
  "title": "Insufficient Permissions",
  "status": 403,
  "detail": "Admin role required for this operation",
  "instance": "/agents",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_yza567",
  "required_role": "admin",
  "current_role": "agent",
  "required_scopes": ["admin", "agent_management"],
  "current_scopes": ["agent"]
}
```

## Permission Levels

ARCP uses a hierarchical permission system:

1. **PUBLIC** - No authentication required
2. **AGENT** - Authenticated agents (inherits PUBLIC)  
3. **ADMIN** - Authenticated admins (inherits PUBLIC + AGENT)
4. **ADMIN_PIN** - Admin with PIN verification (inherits all above)

## Common Scenarios

### 1. Agent Accessing Admin Endpoint
```bash
# This will fail with insufficient permissions
curl "http://localhost:8001/agents" \
  -H "Authorization: Bearer <agent-token>"
```

### 2. Admin Without PIN Accessing Protected Resource
```bash
# Some admin endpoints require PIN verification
curl -X DELETE "http://localhost:8001/agents/agent-id" \
  -H "Authorization: Bearer <admin-token-without-pin>"
```

## Resolution Steps

### 1. Use Appropriate Authentication Level

For admin operations, use admin credentials:
```bash
# Login as admin
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: session-id" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### 2. Verify PIN for High-Security Operations
```bash
# Set PIN first (if not already set)
curl -X POST "http://localhost:8001/auth/set_pin" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"pin": "123456"}'

# Verify PIN before protected operations
curl -X POST "http://localhost:8001/auth/verify_pin" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"pin": "123456"}'
```

### 3. Check Token Permissions with ARCP Client
```python
import asyncio
from arcp import ARCPClient, AuthenticationError

async def check_user_permissions():
    """Check current user's permissions using the ARCP client"""
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Validate current token to see permissions
            validation_result = await client.validate_token()
            print(f"Token validation: {validation_result}")
            
            # Try to access admin endpoints to check permissions
            try:
                system_stats = await client.get_system_stats()
                print("Admin permissions confirmed - can access system stats")
                
            except AuthenticationError as e:
                if "403" in str(e) or "forbidden" in str(e).lower():
                    print("Insufficient permissions for admin operations")
                else:
                    print(f"Authentication error: {e}")
                    
        except Exception as e:
            print(f"Permission check failed: {e}")

# Example usage
if __name__ == "__main__":
    asyncio.run(check_user_permissions())
```

## API Endpoint Permission Requirements

### PUBLIC Endpoints (No Auth Required)
- `GET /health`
- `GET /public/discover`
- `POST /public/connect`
- `POST /public/search`

### AGENT Endpoints (Agent Token Required)
- `POST /agents/register`
- `GET /agents` (list agents)
- `WebSocket /agents/ws`

### ADMIN Endpoints (Admin Token Required)
- `GET /dashboard/config`
- `POST /dashboard/config`
- `GET /agents/{id}/metrics`
- `POST /agents/{id}/metrics`

### ADMIN_PIN Endpoints (Admin + PIN Required)
- `DELETE /agents/{id}`
- `GET /health/detailed`
- Admin configuration changes

## Client Implementation

### Python Permission-Aware Operations
```python
import asyncio
from arcp import ARCPClient, AuthenticationError, ARCPError

async def permission_aware_operations():
    """Example of handling different permission levels with ARCP client"""
    
    async with ARCPClient("http://localhost:8001") as client:
        
        # PUBLIC operations - no authentication needed
        print("=== PUBLIC Operations ===")
        try:
            # Public agent discovery
            agents = await client.discover_agents()
            print(f"Found {len(agents)} agents via public discovery")
            
            # Public search
            search_results = await client.search_agents("data processing")
            print(f"Search returned {len(search_results)} results")
            
        except Exception as e:
            print(f"Public operation failed: {e}")
        
        # AGENT operations - require agent token
        print("\n=== AGENT Operations ===")
        try:
            # First authenticate as agent
            await client.request_temp_token(
                agent_id="test-agent",
                agent_type="processing",
                agent_key="your-agent-key"
            )
            
            # Now can access agent endpoints
            agent_list = await client.list_agents()
            print(f"Agent list access successful: {len(agent_list)} agents")
            
        except AuthenticationError as e:
            print(f"Agent authentication failed: {e}")
        except ARCPError as e:
            print(f"Agent operation failed: {e}")
        
        # ADMIN operations - require admin authentication
        print("\n=== ADMIN Operations ===")
        try:
            # Authenticate as admin
            await client.login_admin("admin", "your-admin-password")
            
            # Access admin-only endpoints
            system_stats = await client.get_system_stats()
            print(f"System stats access successful")
            
            system_metrics = await client.get_system_metrics()
            print(f"System metrics retrieved: {len(system_metrics)} characters")
            
        except AuthenticationError as e:
            if "403" in str(e):
                print(f"Insufficient admin permissions: {e}")
            else:
                print(f"Admin authentication failed: {e}")
        except ARCPError as e:
            print(f"Admin operation failed: {e}")

if __name__ == "__main__":
    asyncio.run(permission_aware_operations())
```

### Error Handling Best Practices
```python
import asyncio
from arcp import ARCPClient, AuthenticationError, ARCPError

async def handle_permission_errors():
    """Best practices for handling permission-related errors"""
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Attempt operation that may require elevated permissions
            metrics = await client.get_system_metrics()
            
        except AuthenticationError as e:
            if "403" in str(e) or "forbidden" in str(e).lower():
                print("Access denied: Insufficient permissions")
                print("This operation requires admin privileges")
            elif "401" in str(e):
                print("Authentication required: Please login first")
            else:
                print(f"Authentication error: {e}")
        
        except ARCPError as e:
            print(f"Operation failed: {e}")
```

### Auto-Escalation Pattern
```python
async def with_admin_privileges(operation):
    """Decorator to ensure admin privileges for operations"""
    async def wrapper(self, *args, **kwargs):
        if not self.is_admin():
            await self.login_admin()
        
        try:
            return await operation(self, *args, **kwargs)
        except PermissionError as e:
            if "pin" in str(e).lower():
                await self.verify_pin()
                return await operation(self, *args, **kwargs)
            raise
    
    return wrapper

class ARCPAdminClient:
    @with_admin_privileges
    async def delete_agent(self, agent_id):
        # This will auto-escalate to admin and PIN if needed
        return await self._delete(f"/agents/{agent_id}")
```

## Related Problems

- [Authentication Failed](./authentication-failed.md) - Auth issues
- [Forbidden](./forbidden.md) - Access denied
- [PIN Required](./pin-required.md) - PIN verification needed

## API Endpoints That Can Return This

- Admin endpoints accessed by agents
- PIN-protected endpoints without PIN verification
- Endpoints requiring specific scopes