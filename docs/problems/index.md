# ARCP Problem Details Reference

This directory contains documentation for all problem types that can be returned by the ARCP API. These problems follow the [RFC 9457 Problem Details for HTTP APIs](https://datatracker.ietf.org/doc/rfc9457/) standard.

## Problem Types by Category

### 🤖 Agent Problems
- [Agent Not Found](./agent-not-found.md) - Requested agent does not exist
- [Agent Not Available](./agent-not-available.md) - Agent exists but is not reachable
- [Duplicate Agent](./duplicate-agent.md) - Agent ID already exists during registration
- [Agent Registration Failed](./agent-registration-failed.md) - Agent registration process failed

### 🔐 Authentication Problems  
- [Authentication Failed](./authentication-failed.md) - Login credentials are invalid
- [Token Invalid/Expired](./token-invalid.md) - JWT token is invalid or expired
- [Session Invalid](./session-invalid.md) - Session validation failed
- [Session Expired](./session-expired.md) - Session has timed out

### 🛡️ Authorization Problems
- [Insufficient Permissions](./insufficient-permissions.md) - User lacks required permissions
- [Forbidden](./forbidden.md) - Access to resource is forbidden

### 🔢 PIN Problems
- [PIN Required](./pin-required.md) - PIN verification is required
- [PIN Already Set](./pin-already-set.md) - PIN has already been configured
- [PIN Not Set](./pin-not-set.md) - PIN must be set before use
- [PIN Incorrect](./pin-incorrect.md) - Provided PIN is wrong
- [PIN Invalid Length](./pin-invalid-length.md) - PIN does not meet length requirements

### ⚙️ Configuration Problems
- [Configuration Error](./configuration-error.md) - Service configuration issue

### 🔧 Service Problems
- [Vector Search Unavailable](./vector-search-unavailable.md) - Search service is down
- [Operation Timeout](./operation-timeout.md) - Operation exceeded time limit
- [Connection Timeout](./connection-timeout.md) - Network connection timed out
- [Endpoint Unreachable](./endpoint-unreachable.md) - Target endpoint cannot be reached

### ✅ Validation Problems
- [Validation Failed](./validation-failed.md) - Request data validation failed
- [Invalid Input](./invalid-input.md) - Input data format is incorrect
- [Required Header Missing](./required-header-missing.md) - Required HTTP header is missing
- [Invalid URL](./invalid-url.md) - URL format is invalid

### 🚦 Rate Limiting Problems
- [Rate Limit Exceeded](./rate-limit-exceeded.md) - Too many requests from client

### 📦 Request Size Problems
- [Request Too Large](./request-too-large.md) - Request body exceeds size limit
- [Headers Too Large](./headers-too-large.md) - Request headers exceed size limit

### 🔧 Generic Problems
- [Internal Error](./internal-error.md) - Internal server error occurred
- [Request Error](./request-error.md) - General request processing error
- [Not Found](./not-found.md) - Requested resource was not found

## Problem Details Format

All ARCP problems follow this structure:

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/{problem-type}",
  "title": "Human Readable Title",
  "status": 400,
  "detail": "Specific details about this occurrence",
  "instance": "/request/path",
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "req_12345"
}
```

## Using Problem Details

### In Client Applications with ARCP

When using the ARCP client, errors are automatically handled and converted to appropriate exceptions:

```python
import asyncio
from arcp import ARCPClient, ARCPError, AuthenticationError, RegistrationError

async def error_handling_example():
    async with ARCPClient("https://arcp.example.com") as client:
        try:
            # This might fail if agent doesn't exist
            agent = await client.get_agent("missing-agent")
            
        except ARCPError as e:
            # ARCP client automatically parses problem details
            print(f"ARCP Error: {e}")
            
            # You can check for specific error types
            if "not found" in str(e).lower():
                print("Agent not found - handle missing agent scenario")
            elif "authentication" in str(e).lower():
                print("Authentication required - handle login")
        
        try:
            # Agent registration example
            agent_info = await client.register_agent(
                agent_id="my-agent",
                name="My Agent",
                # ... other required parameters
            )
            
        except AuthenticationError:
            print("Authentication failed - check credentials")
        except RegistrationError as e:
            print(f"Registration failed: {e}")
        except ARCPError as e:
            print(f"General ARCP error: {e}")

if __name__ == "__main__":
    asyncio.run(error_handling_example())
```

### For Troubleshooting

1. **Check the exception type** - ARCP client maps problems to specific exceptions
2. **Read the exception message** - Contains the problem detail information  
3. **Note the timestamp** - Helps correlate with server logs
4. **Use the request_id** - Reference when contacting support

## Base URI

All ARCP problem types use the base URI:
```
https://arcp.0x001.tech/docs/problems/
```

This documentation is accessible at that base URL for programmatic problem resolution.