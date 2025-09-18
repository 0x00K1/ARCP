# Agent Registration Failed

**Type URI:** `https://arcp.0x001.tech/docs/problems/agent-registration-failed`  
**HTTP Status:** `400 Bad Request`  
**Title:** Agent Registration Failed

## Description

This problem occurs when an agent registration request fails due to validation errors, authentication issues, or system constraints. The registration process could not be completed successfully.

## When This Occurs

- Invalid or malformed registration data
- Authentication token is invalid or expired
- Agent type is not allowed in the system
- Required fields are missing or invalid
- Endpoint URL format is incorrect
- Agent key validation fails
- System configuration prevents registration

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/agent-registration-failed",
  "title": "Agent Registration Failed",
  "status": 400,
  "detail": "Agent registration failed: Invalid endpoint URL format",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_jkl012",
  "agent_id": "malformed-agent",
  "validation_errors": [
    {
      "field": "endpoint",
      "error": "Invalid URL format"
    },
    {
      "field": "capabilities",
      "error": "At least one capability is required"
    }
  ]
}
```

## Common Scenarios

### 1. Invalid Registration Data
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "",
    "agent_type": "invalid-type",
    "endpoint": "not-a-url",
    "capabilities": []
  }'
```

### 2. Missing Authentication
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing"
  }'
```

### 3. Invalid Agent Type
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "disallowed-type"
  }'
```

## Resolution Steps

### 1. Validate Registration Data
Ensure all required fields are present and properly formatted:

```json
{
  "agent_id": "my-agent-001",
  "name": "My Processing Agent",
  "agent_type": "processing",
  "endpoint": "http://localhost:8080",
  "capabilities": ["data-processing"],
  "context_brief": "Processes data",
  "owner": "user@example.com",
  "public_key": "valid-key-string",
  "metadata": {
    "version": "1.0.0"  
  },
  "version": "1.0.0",
  "communication_mode": "remote"
}
```

### 2. Check Authentication
Ensure you have a valid agent token:

```bash
# First get a temporary token
curl -X POST "http://localhost:8001/auth/temp-token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-001",
    "agent_type": "processing",
    "agent_key": "your-agent-key"
  }'

# Use the token for registration
curl -X POST "http://localhost:8001/agents/register" \
  -H "Authorization: Bearer <temp-token>" \
  # ... registration data
```

### 3. Verify Agent Type is Allowed
Check system configuration for allowed agent types:

```bash
# Check public discovery for allowed types
curl "http://localhost:8001/public/discover"

# Or check with admin access
curl "http://localhost:8001/dashboard/config" \
  -H "Authorization: Bearer <admin-token>"
```

### 4. Validate Endpoint Accessibility
Ensure your agent endpoint is reachable:

```bash
# Test agent endpoint
curl "http://your-agent-endpoint:8080/health"

# Check network connectivity
ping your-agent-host
telnet your-agent-host 8080
```

### 5. Check Agent Key Configuration
Verify your agent key is properly configured:

```bash
# Check if your key is in the allowed keys list
# (This requires admin access or checking server configuration)
```

## Common Validation Errors

### Required Field Errors
```json
{
  "validation_errors": [
    {
      "field": "agent_id",
      "error": "Agent ID is required and cannot be empty"
    },
    {
      "field": "name", 
      "error": "Agent name is required"
    },
    {
      "field": "endpoint",
      "error": "Agent endpoint URL is required"
    }
  ]
}
```

### Format Validation Errors
```json
{
  "validation_errors": [
    {
      "field": "endpoint",
      "error": "Invalid URL format - must be http:// or https://"
    },
    {
      "field": "agent_id",
      "error": "Agent ID can only contain alphanumeric characters and dashes"
    },
    {
      "field": "capabilities",
      "error": "At least one capability must be specified"
    }
  ]
}
```

### Authentication Errors
```json
{
  "detail": "Agent registration failed: Authentication required",
  "error_code": "AUTH_REQUIRED"
}
```

## Prevention

### 1. Use Registration Schema Validation
```python
import asyncio
from arcp import ARCPClient, RegistrationError, AgentRequirements
from typing import List

async def validate_and_register_agent(
    agent_id: str,
    name: str, 
    agent_type: str,
    endpoint: str,
    capabilities: List[str],
    agent_key: str
):
    """Validate and register an agent with proper error handling"""
    
    # Basic validation
    if not agent_id or len(agent_id.strip()) == 0:
        raise ValueError('Agent ID cannot be empty')
    
    if not endpoint.startswith(('http://', 'https://')):
        raise ValueError('Endpoint must be a valid HTTP URL')
    
    if not capabilities:
        raise ValueError('At least one capability is required')
    
    async with ARCPClient("http://localhost:8001") as client:
        try:
            agent_info = await client.register_agent(
                agent_id=agent_id.strip(),
                name=name,
                agent_type=agent_type,
                endpoint=endpoint,
                capabilities=capabilities,
                context_brief=f"{name} - {agent_type} agent",
                version="1.0.0",
                owner="system@example.com",
                public_key="your-public-key",
                communication_mode="remote",
                agent_key=agent_key
            )
            return agent_info
            
        except RegistrationError as e:
            print(f"Registration validation failed: {e}")
            raise
```

### 2. Test Registration Locally
```python
import asyncio
from arcp import ARCPClient, RegistrationError, AgentRequirements

async def test_registration():
    async with ARCPClient("http://localhost:8001") as client:
        try:
            # Register agent with all required fields
            agent_info = await client.register_agent(
                agent_id="test-agent",
                name="Test Agent",
                agent_type="processing", 
                endpoint="http://localhost:8080",
                capabilities=["data-processing", "testing"],
                context_brief="Test agent for data processing",
                version="1.0.0",
                owner="test@example.com",
                public_key="your-public-key-here",
                communication_mode="remote",
                metadata={"version": "1.0.0"},
                agent_key="your-agent-registration-key"
            )
            print(f"Registration successful: {agent_info}")
            
        except RegistrationError as e:
            print(f"Registration failed: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_registration())
```

### 3. Environment-Specific Configuration
```yaml
# config.yaml
agent:
  id: "${AGENT_ID}"
  name: "${AGENT_NAME}"  
  type: "${AGENT_TYPE:-processing}"
  endpoint: "http://${HOST:-localhost}:${PORT:-8080}"
  capabilities: 
    - "${CAPABILITY_1:-processing}"
```

## Related Problems

- [Duplicate Agent](./duplicate-agent.md) - Agent ID already exists
- [Authentication Failed](./authentication-failed.md) - Auth token issues
- [Validation Failed](./validation-failed.md) - Data validation errors
- [Token Invalid](./token-invalid.md) - Token problems

## API Endpoints That Can Return This

- `POST /agents/register`