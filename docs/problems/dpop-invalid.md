# Invalid DPoP Proof

**Type URI:** `https://arcp.0x001.tech/docs/problems/dpop-invalid`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Invalid DPoP Proof

## Description

This problem occurs when a DPoP proof is provided but fails validation. The proof may have an invalid signature, expired timestamp, incorrect HTTP method/URI binding, or malformed structure.

## When This Occurs

- DPoP proof JWT has invalid signature
- Proof timestamp is too old or in the future
- HTTP method (htm) doesn't match the request method
- HTTP URI (htu) doesn't match the request URI
- Missing required claims (jti, htm, htu, iat)
- Malformed JWK in proof header
- Replay attack detected (jti reused)

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/dpop-invalid",
  "title": "Invalid DPoP Proof",
  "status": 401,
  "detail": "DPoP proof signature validation failed",
  "instance": "/agents/validate_compliance",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_xyz789"
}
```

## Common Scenarios

### 1. Signature Verification Failed
```bash
# DPoP proof signed with wrong key
curl -X POST "http://localhost:8001/agents/validate_compliance" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "DPoP: eyJ0eXAiOiJkcG9wK2p3dCIsImFsZyI6IlJTMjU2Ii..." \
  -H "Content-Type: application/json"
```

### 2. HTTP Method Mismatch
```bash
# DPoP created for POST but used in GET
curl "http://localhost:8001/agents/some-resource" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "DPoP: eyJ0eXAiOiJkcG9wK2p3dCIsImFsZyI6IlJTMjU2Ii..."
```

### 3. Expired Timestamp
```bash
# DPoP proof created more than 60 seconds ago
curl -X POST "http://localhost:8001/agents/validate_compliance" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "DPoP: eyJ0eXAiOiJkcG9wK2p3dCIsImFsZyI6IlJTMjU2Ii..."
```

## Resolution Steps

### 1. Verify DPoP Proof Creation
Ensure correct proof generation:

```python
import jwt
import time
import uuid

def create_dpop_proof(private_key, method, uri, access_token=None):
    """Create a valid DPoP proof."""
    
    # Get public key JWK
    public_key = private_key.public_key()
    jwk = get_jwk_from_public_key(public_key)
    
    # Create claims
    claims = {
        "jti": str(uuid.uuid4()),
        "htm": method,  # MUST match request method
        "htu": uri,     # MUST match request URI
        "iat": int(time.time())  # Current timestamp
    }
    
    # Add access token hash if present
    if access_token:
        import hashlib
        import base64
        hash_bytes = hashlib.sha256(access_token.encode()).digest()
        claims["ath"] = base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")
    
    # Sign with private key
    proof = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"typ": "dpop+jwt", "jwk": jwk}
    )
    
    return proof
```

### 2. Check HTTP Method and URI
```python
# Correct usage
method = "POST"
uri = "http://localhost:8001/agents/validate_compliance"

dpop_proof = create_dpop_proof(private_key, method, uri, access_token)

response = requests.post(
    uri,  # Same URI
    headers={
        "Authorization": f"Bearer {access_token}",
        "DPoP": dpop_proof
    },
    json=data
)
```

### 3. Generate Fresh Proof for Each Request
```python
# DON'T reuse DPoP proofs
# DO create new proof for each request

for request in requests_to_make:
    # Create fresh proof
    dpop_proof = create_dpop_proof(
        private_key,
        request.method,
        request.uri,
        access_token
    )
    
    # Make request
    response = request.execute(dpop_proof)
```

### 4. Verify Key Consistency
```python
# Use the SAME private key that was used to bind the token
# Don't generate new keys for each proof

# Store key securely
private_key = load_private_key("path/to/key.pem")

# Use this key for all proofs
dpop_proof = create_dpop_proof(private_key, method, uri)
```

## Validation Rules

ARCP validates the following:

1. **JWT Structure**
   - Valid JWT format
   - Header contains `typ: "dpop+jwt"`
   - Header contains valid JWK

2. **Signature**
   - Signature verifies with public key from JWK
   - Algorithm is RS256 or ES256

3. **Claims**
   - `jti`: Present and unique (not replayed)
   - `htm`: Matches request HTTP method
   - `htu`: Matches request URI (scheme + host + path)
   - `iat`: Within acceptable time window (±60 seconds)
   - `ath`: If present, matches hash of access token

4. **Timestamp**
   - Not more than 60 seconds old
   - Not in the future

## Technical Details

### DPoP Proof Lifetime
```python
# Default: 60 seconds
DPOP_PROOF_MAX_AGE = 60

# Proof is valid if:
# current_time - 60 <= iat <= current_time
```

### URI Matching
```python
# Full URI comparison (case-sensitive)
# Includes: scheme, host, port, path
# Excludes: query parameters, fragment

Expected: "http://localhost:8001/agents/validate_compliance"
Valid:    "http://localhost:8001/agents/validate_compliance"
Invalid:  "http://localhost:8001/agents/validate_compliance?foo=bar"
Invalid:  "https://localhost:8001/agents/validate_compliance"
```

## Common Mistakes

1. **Using Wrong Key**: Proof signed with different key than token binding
2. **Reusing Proofs**: Same jti used multiple times
3. **URI Mismatch**: Including query parameters or wrong scheme
4. **Time Skew**: Server and client clocks out of sync
5. **Method Mismatch**: Proof for GET used in POST request

## Related Problems

- [dpop-required](dpop-required.md) - Missing DPoP proof header
- [dpop-binding-mismatch](dpop-binding-mismatch.md) - Key mismatch with token
- [authentication-failed](authentication-failed.md) - General authentication errors

## References

- [RFC 9449: OAuth 2.0 DPoP](https://datatracker.ietf.org/doc/html/rfc9449)
- [DPoP Implementation Guide](../security/dpop.md)
