# Token Not DPoP Bound

**Type URI:** `https://arcp.0x001.tech/docs/problems/token-not-dpop-bound`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Token Not DPoP Bound

## Description

This problem occurs when DPoP is required but the access token does not contain a DPoP binding (missing `cnf.jkt` claim). The token was issued without DPoP proof-of-possession and cannot be used with DPoP-protected endpoints.

## When This Occurs

- Token was requested without DPoP proof during issuance
- Using legacy tokens from before DPoP was enabled
- Token issued via non-DPoP authentication flow
- Missing DPoP proof during Phase 1 (temp token request)
- Server requires DPoP but token wasn't created with binding

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/token-not-dpop-bound",
  "title": "Token Not DPoP Bound",
  "status": 401,
  "detail": "Access token does not have DPoP binding (missing cnf.jkt)",
  "instance": "/agents/validate_compliance",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_nobound_789"
}
```

## Common Scenarios

### 1. Token Requested Without DPoP
```bash
# Wrong: Request token without DPoP header
curl -X POST "http://localhost:8001/auth/agent/request_temp_token" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing",
    "agent_key": "secret-key"
  }'

# Token issued without cnf.jkt binding

# Later: Try to use with DPoP
curl -X POST "http://localhost:8001/agents/validate_compliance" \
  -H "Authorization: Bearer <unbound-token>" \
  -H "DPoP: <dpop-proof>" \
  -H "Content-Type: application/json"

# Result: token-not-dpop-bound error
```

### 2. Using Legacy Token
```python
# Token from before DPoP was enabled
legacy_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
# Token payload: {"sub": "agent-123", "role": "agent"}
# Missing: "cnf": {"jkt": "..."}

# Try to use with DPoP-required endpoint
response = requests.post(
    "http://localhost:8001/agents/validate_compliance",
    headers={
        "Authorization": f"Bearer {legacy_token}",
        "DPoP": dpop_proof  # Server checks for cnf.jkt - not found!
    }
)
```

## Resolution Steps

### 1. Request Token WITH DPoP Proof
Include DPoP proof when requesting token:

```python
from examples.agents.dpop_helper import DPoPClientHelper

# Create DPoP-enabled client
helper = DPoPClientHelper()

# Request temp token WITH DPoP
dpop_proof_for_token_request = helper.create_dpop_proof(
    method="POST",
    uri="http://localhost:8001/auth/agent/request_temp_token"
)

response = requests.post(
    "http://localhost:8001/auth/agent/request_temp_token",
    headers={
        "Content-Type": "application/json",
        "DPoP": dpop_proof_for_token_request
    },
    json={
        "agent_id": "my-agent",
        "agent_type": "processing",
        "agent_key": "secret-key"
    }
)

token_data = response.json()
temp_token = token_data["temp_token"]

# Token now contains: "cnf": {"jkt": "<thumbprint>"}
```

### 2. Use DPoP Throughout Registration Flow
```python
helper = DPoPClientHelper()

# Phase 1: Request temp token WITH DPoP
temp_token = helper.request_temp_token(
    agent_id="my-agent",
    agent_type="processing",
    agent_key="secret-key"
)

# Phase 2: Validate compliance WITH DPoP
validated_token = helper.validate_compliance(
    temp_token=temp_token,
    compliance_data={...}
)

# Phase 3: Register WITH DPoP
result = helper.register_agent(
    validated_token=validated_token,
    registration_data={...}
)
```

### 3. Verify Token Has DPoP Binding
```python
import jwt

def verify_dpop_binding(token):
    """Check if token has DPoP binding."""
    try:
        # Decode without verification (just inspect)
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Check for cnf.jkt
        if "cnf" not in payload:
            raise ValueError("Token missing 'cnf' claim - not DPoP bound")
        
        if "jkt" not in payload["cnf"]:
            raise ValueError("Token missing 'cnf.jkt' - not DPoP bound")
        
        jkt = payload["cnf"]["jkt"]
        print(f"✓ Token is DPoP-bound with jkt: {jkt[:16]}...")
        return True
        
    except jwt.DecodeError:
        raise ValueError("Invalid token format")

# Verify before using
verify_dpop_binding(temp_token)
```

### 4. Re-request Token If Needed
```bash
# If you have an unbound token, get a new one
curl -X POST "http://localhost:8001/auth/agent/request_temp_token" \
  -H "Content-Type: application/json" \
  -H "DPoP: eyJ0eXAiOiJkcG9wK2p3dCIsImFsZyI6IlJTMjU2Ii..." \
  -d '{
    "agent_id": "my-agent",
    "agent_type": "processing",
    "agent_key": "secret-key"
  }'
```

## Technical Details

### DPoP-Bound Token Structure
```json
{
  "sub": "agent-123",
  "role": "agent",
  "agent_id": "my-agent",
  "aud": "arcp:validate",
  "token_type": "temp",
  "cnf": {
    "jkt": "0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I"
  },
  "iat": 1705320600,
  "exp": 1705324200
}
```

### Non-DPoP Token (Legacy)
```json
{
  "sub": "agent-123",
  "role": "agent",
  "agent_id": "my-agent",
  "aud": "arcp:validate",
  "token_type": "temp",
  "iat": 1705320600,
  "exp": 1705324200
}
```

### Server-Side Validation
```python
# ARCP checks:
if config.DPOP_REQUIRED:
    # Extract cnf claim
    cnf = token_payload.get("cnf", {})
    expected_jkt = cnf.get("jkt")
    
    if not expected_jkt:
        # Token not DPoP-bound
        raise ProblemException(
            type_uri=ARCPProblemTypes.TOKEN_NOT_DPOP_BOUND["type"],
            title=ARCPProblemTypes.TOKEN_NOT_DPOP_BOUND["title"],
            status=401,
            detail="Token missing DPoP binding (cnf.jkt)"
        )
```

## Configuration

### Enable DPoP During Token Issuance
```bash
# In .env
DPOP_ENABLED=true
DPOP_REQUIRED=true
```

When enabled, the server will:
1. Accept DPoP proofs during token requests
2. Bind tokens to the proof's public key (add `cnf.jkt`)
3. Require DPoP proofs for protected endpoints
4. Validate that proof key matches token binding

## Migration from Non-DPoP

If upgrading from non-DPoP:

1. **Phase 1**: Enable DPoP but don't require it
   ```bash
   DPOP_ENABLED=true
   DPOP_REQUIRED=false
   ```

2. **Phase 2**: Update all clients to use DPoP
   - Use DPoPClientHelper
   - Include DPoP in token requests

3. **Phase 3**: Require DPoP
   ```bash
   DPOP_REQUIRED=true
   ```

## Related Problems

- [dpop-required](dpop-required.md) - Missing DPoP proof header
- [dpop-invalid](dpop-invalid.md) - Invalid DPoP proof
- [dpop-binding-mismatch](dpop-binding-mismatch.md) - Key mismatch
- [authentication-failed](authentication-failed.md) - General auth errors

## References

- [RFC 9449: DPoP Token Binding](https://datatracker.ietf.org/doc/html/rfc9449#section-4.2)
- [Three-Phase Registration with DPoP](../security/three-phase-registration.md)
- [DPoP Implementation Guide](../security/dpop.md)
