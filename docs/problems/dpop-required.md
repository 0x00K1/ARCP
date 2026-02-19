# DPoP Proof Required

**Type URI:** `https://arcp.0x001.tech/docs/problems/dpop-required`  
**HTTP Status:** `401 Unauthorized`  
**Title:** DPoP Proof Required

## Description

This problem occurs when a DPoP (Demonstration of Proof-of-Possession) proof is required for the endpoint but was not provided in the request. DPoP is a security mechanism that binds access tokens to specific cryptographic keys, preventing token theft and replay attacks.

## When This Occurs

- DPoP is enabled (`DPOP_REQUIRED=true`) but no `DPoP` header was sent
- Attempting to access DPoP-protected endpoints without proof
- Missing DPoP header during agent registration or validation

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/dpop-required",
  "title": "DPoP Proof Required",
  "status": 401,
  "detail": "This endpoint requires a DPoP proof header",
  "instance": "/agents/validate_compliance",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_abc123"
}
```

## Common Scenarios

### 1. Missing DPoP Header During Registration
```bash
curl -X POST "http://localhost:8001/agents/validate_compliance" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "Content-Type: application/json" \
  -d '{"compliance_data": {...}}'
```

### 2. Accessing Protected Endpoint Without DPoP
```bash
curl "http://localhost:8001/agents/protected-resource" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

## Resolution Steps

### 1. Generate DPoP Proof
Create a DPoP proof JWT with your private key:

```python
import jwt
import hashlib
import base64
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# Generate key pair (do this once and store)
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

# Calculate JKT (thumbprint)
# ... (see dpop_helper.py for full implementation)

# Create DPoP proof
dpop_proof = jwt.encode(
    {
        "jti": unique_id,
        "htm": "POST",
        "htu": "http://localhost:8001/agents/validate_compliance",
        "iat": int(time.time())
    },
    private_key,
    algorithm="RS256",
    headers={"typ": "dpop+jwt", "jwk": jwk_public}
)
```

### 2. Include DPoP Header in Request
```bash
curl -X POST "http://localhost:8001/agents/validate_compliance" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "DPoP: eyJ0eXAiOiJkcG9wK2p3dCIsImFsZyI6IlJTMjU2Ii..." \
  -H "Content-Type: application/json" \
  -d '{"compliance_data": {...}}'
```

### 3. Use DPoP Client Helper
Use the provided client helper:

```python
from examples.agents.dpop_helper import DPoPClientHelper

# Initialize helper with your key
helper = DPoPClientHelper()

# Make request with DPoP
response = helper.post(
    "http://localhost:8001/agents/validate_compliance",
    headers={"Authorization": f"Bearer {token}"},
    json={"compliance_data": {...}}
)
```

## Technical Details

### DPoP Proof Structure
A valid DPoP proof is a JWT with:

**Headers:**
- `typ`: "dpop+jwt"
- `alg`: Signing algorithm (e.g., "RS256")
- `jwk`: Public key in JWK format

**Claims:**
- `jti`: Unique identifier for the proof
- `htm`: HTTP method (e.g., "POST")
- `htu`: Full HTTP URI of the request
- `iat`: Issued at timestamp
- `ath` (optional): Hash of access token

### Configuration

Check if DPoP is required:
```bash
# In .env file
DPOP_ENABLED=true
DPOP_REQUIRED=true
```

## Related Problems

- [dpop-invalid](dpop-invalid.md) - Invalid DPoP proof format or signature
- [dpop-binding-mismatch](dpop-binding-mismatch.md) - DPoP key doesn't match token binding
- [token-not-dpop-bound](token-not-dpop-bound.md) - Token missing DPoP binding
- [authentication-failed](authentication-failed.md) - General authentication failures

## References

- [RFC 9449: OAuth 2.0 Demonstrating Proof-of-Possession](https://datatracker.ietf.org/doc/html/rfc9449)
- [ARCP Security Documentation](../security/security-overview.md)
- [DPoP Implementation Guide](../security/dpop.md)
