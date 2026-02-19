# DPoP Key Mismatch

**Type URI:** `https://arcp.0x001.tech/docs/problems/dpop-binding-mismatch`  
**HTTP Status:** `401 Unauthorized`  
**Title:** DPoP Key Mismatch

## Description

This problem occurs when the cryptographic key used in the DPoP proof does not match the key bound to the access token. The access token contains a `cnf.jkt` (confirmation/JWK thumbprint) claim that must match the thumbprint of the public key in the DPoP proof.

## When This Occurs

- DPoP proof uses a different key than the one bound to the token
- Token's `cnf.jkt` claim doesn't match the proof's JWK thumbprint
- Key rotation without obtaining a new token
- Using wrong private key for proof generation

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/dpop-binding-mismatch",
  "title": "DPoP Key Mismatch",
  "status": 401,
  "detail": "DPoP proof key does not match token binding",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_mismatch_456"
}
```

## Common Scenarios

### 1. Key Rotation Without New Token
```python
# Got token with key1
token = get_token_with_dpop(private_key_1)

# Later, rotated to key2 but still using old token
dpop_proof = create_proof(private_key_2, method, uri)  # Wrong key!

response = requests.post(
    uri,
    headers={
        "Authorization": f"Bearer {token}",  # Bound to key1
        "DPoP": dpop_proof  # Created with key2
    }
)
# Result: dpop-binding-mismatch error
```

### 2. Using Wrong Key from Multiple Keys
```python
# Agent has multiple keys
key_for_service_a = load_key("service_a.pem")
key_for_service_b = load_key("service_b.pem")

# Got token with service_a key
token = get_token_with_dpop(key_for_service_a)

# Accidentally used service_b key for proof
dpop_proof = create_proof(key_for_service_b, method, uri)  # Wrong!

response = requests.post(
    uri,
    headers={
        "Authorization": f"Bearer {token}",
        "DPoP": dpop_proof
    }
)
```

## Resolution Steps

### 1. Use Consistent Key
Ensure the same key is used for token binding and proofs:

```python
# Store and reuse the same key
class DPoPSession:
    def __init__(self):
        # Generate or load key ONCE
        self.private_key = self._load_or_generate_key()
        self.token = None
        self.jkt = self._calculate_jkt()
    
    def get_token(self):
        """Get DPoP-bound token."""
        if not self.token or self._is_token_expired():
            self.token = self._request_token_with_dpop(self.private_key)
        return self.token
    
    def make_request(self, method, uri, **kwargs):
        """Make request with consistent DPoP."""
        token = self.get_token()
        
        # Use SAME key for proof
        dpop_proof = create_dpop_proof(
            self.private_key,  # Same key!
            method,
            uri,
            token
        )
        
        return requests.request(
            method,
            uri,
            headers={
                "Authorization": f"Bearer {token}",
                "DPoP": dpop_proof
            },
            **kwargs
        )
```

### 2. Verify JKT Matching
Check that JWK thumbprints match:

```python
import hashlib
import base64
import json

def calculate_jkt(public_key):
    """Calculate JWK thumbprint."""
    # Convert public key to JWK
    jwk = public_key_to_jwk(public_key)
    
    # Create canonical JSON (sorted keys)
    canonical = json.dumps(jwk, sort_keys=True, separators=(',', ':'))
    
    # SHA-256 hash
    hash_bytes = hashlib.sha256(canonical.encode()).digest()
    
    # Base64url encode
    jkt = base64.urlsafe_b64encode(hash_bytes).decode().rstrip('=')
    
    return jkt

# Verify match
token_jkt = jwt.decode(token, verify=False)["cnf"]["jkt"]
proof_jkt = calculate_jkt(private_key.public_key())

assert token_jkt == proof_jkt, "Key mismatch!"
```

### 3. Request New Token After Key Change
```python
# If you need to rotate keys
old_private_key = load_key("old_key.pem")
new_private_key = generate_new_key()

# Get new token with new key
new_token = request_token_with_dpop(new_private_key)

# Use new key for all subsequent proofs
dpop_proof = create_proof(new_private_key, method, uri, new_token)
```

### 4. Use DPoP Helper
The helper manages key consistency:

```python
from examples.agents.dpop_helper import DPoPClientHelper

# Helper automatically maintains key consistency
helper = DPoPClientHelper()

# Get token (uses helper's key)
token = helper.get_dpop_bound_token()

# Make requests (uses same key)
response = helper.post(
    "http://localhost:8001/agents/register",
    json=registration_data
)
```

## Technical Details

### Token Binding Structure
The access token contains:
```json
{
  "sub": "agent-123",
  "role": "agent",
  "cnf": {
    "jkt": "0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I"
  }
}
```

### JKT Calculation
```python
# JKT = Base64url(SHA256(canonical_jwk))
jwk = {
    "kty": "RSA",
    "e": "AQAB",
    "n": "xjlC..."  # Modulus
}

# Sort keys, create canonical JSON
canonical = '{"e":"AQAB","kty":"RSA","n":"xjlC..."}'

# Hash and encode
jkt = base64url(sha256(canonical))
```

### Validation Process
```python
# ARCP validates:
1. Extract jkt from token's cnf claim
2. Extract public key from DPoP proof's JWK header
3. Calculate JKT from proof's public key
4. Compare: token_jkt == proof_jkt
```

## Key Management Best Practices

1. **Single Key Per Agent**: Use one key pair per agent instance
2. **Secure Storage**: Store private key securely (encrypted, secure vault)
3. **Key Lifecycle**: Plan for key rotation (requires new token)
4. **Consistent Usage**: Always use same key for token and proofs
5. **Key Identification**: Track which key is bound to which token

## Related Problems

- [dpop-required](dpop-required.md) - Missing DPoP proof
- [dpop-invalid](dpop-invalid.md) - Invalid DPoP proof structure
- [token-not-dpop-bound](token-not-dpop-bound.md) - Token without DPoP binding
- [authentication-failed](authentication-failed.md) - General authentication issues

## References

- [RFC 9449 Section 4.2: DPoP Access Token Binding](https://datatracker.ietf.org/doc/html/rfc9449#section-4.2)
- [RFC 7638: JWK Thumbprint](https://datatracker.ietf.org/doc/html/rfc7638)
- [DPoP Implementation Guide](../security/dpop.md)
