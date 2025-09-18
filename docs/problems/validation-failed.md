# Validation Failed

**Type URI:** `https://arcp.0x001.tech/docs/problems/validation-failed`  
**HTTP Status:** `422 Unprocessable Entity`  
**Title:** Request Validation Failed

## Description

This problem occurs when request data fails validation checks. The request format is correct but the data doesn't meet the required constraints.

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/validation-failed",
  "title": "Request Validation Failed",
  "status": 422,
  "detail": "Input validation failed: 2 validation errors",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_val456",
  "validation_errors": [
    {
      "field": "agent_id",
      "message": "Agent ID cannot be empty",
      "invalid_value": ""
    },
    {
      "field": "endpoint", 
      "message": "Invalid URL format",
      "invalid_value": "not-a-url"
    }
  ]
}
```

## Common Validation Errors

### Agent Registration
```json
{
  "validation_errors": [
    {
      "field": "agent_id",
      "message": "String should have at least 1 character",
      "invalid_value": ""
    },
    {
      "field": "capabilities",
      "message": "List should have at least 1 item",
      "invalid_value": []
    },
    {
      "field": "endpoint",
      "message": "Invalid URL scheme - must be http or https",
      "invalid_value": "ftp://example.com"
    }
  ]
}
```

## Resolution Steps

### 1. Fix Validation Errors
```bash
# Before (invalid)
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "agent_id": "",
    "endpoint": "invalid-url",
    "capabilities": []
  }'

# After (valid)
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "agent_id": "my-agent-001",
    "name": "My Agent",
    "agent_type": "processing", 
    "endpoint": "http://localhost:8080",
    "capabilities": ["data-processing"],
    "context_brief": "Data processing agent"
  }'
```

### 2. Validate Before Sending with ARCP Client
```python
import asyncio
from typing import List
from arcp import ARCPClient, RegistrationError, ValidationError

async def validate_and_register_agent(
    agent_id: str,
    name: str,
    agent_type: str,
    endpoint: str,
    capabilities: List[str],
    context_brief: str,
    agent_key: str
):
    """Validate input and register agent using ARCP client"""
    
    # Client-side validation
    if not agent_id or not agent_id.strip():
        raise ValueError('Agent ID cannot be empty')
    
    if not endpoint.startswith(('http://', 'https://')):
        raise ValueError('Endpoint must be a valid HTTP/HTTPS URL')
    
    if not capabilities:
        raise ValueError('At least one capability is required')
    
    if not context_brief.strip():
        raise ValueError('Context brief cannot be empty')
    
    # Use ARCP client for registration
    async with ARCPClient("http://localhost:8001") as client:
        try:
            agent_info = await client.register_agent(
                agent_id=agent_id.strip(),
                name=name,
                agent_type=agent_type,
                endpoint=endpoint,
                capabilities=capabilities,
                context_brief=context_brief.strip(),
                version="1.0.0",
                owner="system@example.com",
                public_key="your-public-key",
                communication_mode="remote",
                agent_key=agent_key
            )
            
            print(f"Agent registered successfully: {agent_info.agent_id}")
            return agent_info
            
        except RegistrationError as e:
            print(f"Registration failed due to validation: {e}")
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

# Usage example
async def example_usage():
    try:
        await validate_and_register_agent(
            agent_id="data-processor-001",
            name="Data Processing Agent",
            agent_type="processing",
            endpoint="http://localhost:8080",
            capabilities=["data-processing", "file-analysis"],
            context_brief="Processes various data formats and generates reports",
            agent_key="your-agent-key"
        )
    except (ValueError, RegistrationError) as e:
        print(f"Validation error: {e}")

if __name__ == "__main__":
    asyncio.run(example_usage())
```
try:
    registration_data = AgentRegistration(
        agent_id="my-agent",
        name="My Agent",
        agent_type="processing",
        endpoint="http://localhost:8080", 
        capabilities=["processing"],
        context_brief="Processing agent"
    )
    # Send to ARCP
except ValidationError as e:
    print(f"Validation errors: {e}")
```