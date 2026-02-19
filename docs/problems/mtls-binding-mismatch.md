# Certificate Mismatch

**Type URI:** `https://arcp.0x001.tech/docs/problems/mtls-binding-mismatch`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Certificate Mismatch

## Description

This problem occurs when the client certificate presented in the request does not match the certificate bound to the access token. The token contains a `cnf.x5t#S256` (confirmation/certificate thumbprint) claim that must match the SPKI hash of the presented certificate.

## When This Occurs

- Client certificate's SPKI hash doesn't match token's `cnf.x5t#S256`
- Using different certificate than the one used during token issuance
- Certificate rotation without obtaining a new token
- Token bound to one certificate, request uses another

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/mtls-binding-mismatch",
  "title": "Certificate Mismatch",
  "status": 401,
  "detail": "Client certificate does not match token binding",
  "instance": "/agents/register",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_cert_mismatch_789"
}
```

## Common Scenarios

### 1. Certificate Rotation Without New Token
```python
# Got token with cert1
with open("client1.crt") as f:
    cert1 = f.read()

token = request_token_with_mtls(cert="client1.crt", key="client1.key")

# Later, rotated to cert2 but still using old token
response = requests.post(
    "https://arcp.example.com/agents/register",
    headers={"Authorization": f"Bearer {token}"},  # Bound to cert1
    cert=("client2.crt", "client2.key"),  # Using cert2
    json=registration_data
)
# Result: mtls-binding-mismatch error
```

### 2. Using Wrong Certificate from Multiple Certificates
```python
# Agent has certificates for different purposes
cert_production = "prod-client.crt"
cert_staging = "staging-client.crt"

# Got token with production cert
token = request_token_with_mtls(cert=cert_production, key="prod-client.key")

# Accidentally used staging cert for request
response = requests.post(
    url,
    headers={"Authorization": f"Bearer {token}"},
    cert=(cert_staging, "staging-client.key"),  # Wrong cert!
    json=data
)
```

### 3. Mismatched Certificate in Load Balanced Environment
```python
# Load balancer terminates TLS with one cert
# App receives different cert in X-SSL-Client-Cert header
# Token was bound to client's original cert
# Result: mismatch
```

## Resolution Steps

### 1. Use Consistent Certificate
Ensure the same certificate is used for token binding and requests:

```python
class MTLSSession:
    def __init__(self, cert_file, key_file, ca_file):
        """Maintain consistent mTLS session."""
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        self.token = None
        self.spki_hash = self._calculate_spki_hash()
    
    def _calculate_spki_hash(self):
        """Calculate SPKI hash of certificate."""
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        import hashlib
        import base64
        
        with open(self.cert_file, 'rb') as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())
        
        spki = cert.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        hash_bytes = hashlib.sha256(spki).digest()
        return base64.urlsafe_b64encode(hash_bytes).decode().rstrip('=')
    
    def get_token(self):
        """Get mTLS-bound token."""
        if not self.token or self._is_token_expired():
            # Request token with mTLS
            response = requests.post(
                "https://arcp.example.com/auth/agent/request_temp_token",
                cert=(self.cert_file, self.key_file),
                verify=self.ca_file,
                json={
                    "agent_id": "my-agent",
                    "agent_type": "processing",
                    "agent_key": "secret-key"
                }
            )
            self.token = response.json()["temp_token"]
        return self.token
    
    def make_request(self, method, url, **kwargs):
        """Make request with consistent mTLS."""
        token = self.get_token()
        
        # Use SAME certificate
        return requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {token}",
                **kwargs.pop("headers", {})
            },
            cert=(self.cert_file, self.key_file),  # Same cert!
            verify=self.ca_file,
            **kwargs
        )
```

### 2. Verify SPKI Hash Matching
```python
import hashlib
import base64
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import jwt

def calculate_cert_spki_hash(cert_file):
    """Calculate SPKI hash of certificate."""
    with open(cert_file, 'rb') as f:
        cert = x509.load_pem_x509_certificate(f.read(), default_backend())
    
    # Get public key SPKI
    spki = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # SHA-256 hash
    hash_bytes = hashlib.sha256(spki).digest()
    
    # Base64url encode
    return base64.urlsafe_b64encode(hash_bytes).decode().rstrip('=')

# Verify match
token_payload = jwt.decode(token, options={"verify_signature": False})
token_spki = token_payload["cnf"]["x5t#S256"]
cert_spki = calculate_cert_spki_hash("client.crt")

assert token_spki == cert_spki, f"Certificate mismatch!\nToken: {token_spki}\nCert: {cert_spki}"
```

### 3. Request New Token After Certificate Change
```python
# If you need to rotate certificates
old_cert = ("old-client.crt", "old-client.key")
new_cert = ("new-client.crt", "new-client.key")

# Get new token with new certificate
response = requests.post(
    "https://arcp.example.com/auth/agent/request_temp_token",
    cert=new_cert,
    verify="ca.crt",
    json={
        "agent_id": "my-agent",
        "agent_type": "processing",
        "agent_key": "secret-key"
    }
)

new_token = response.json()["temp_token"]

# Use new certificate with new token
response = requests.post(
    "https://arcp.example.com/agents/register",
    headers={"Authorization": f"Bearer {new_token}"},
    cert=new_cert,
    verify="ca.crt",
    json=registration_data
)
```

### 4. Use mTLS Helper
```python
from examples.agents.mtls_helper import MTLSClientHelper

# Helper automatically maintains certificate consistency
helper = MTLSClientHelper(
    cert_file="client.crt",
    key_file="client.key",
    ca_file="ca.crt"
)

# Get token (uses helper's cert)
token = helper.request_temp_token(
    agent_id="my-agent",
    agent_type="processing",
    agent_key="secret-key"
)

# Make requests (uses same cert)
response = helper.post(
    "https://arcp.example.com/agents/register",
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
  "agent_id": "my-agent",
  "cnf": {
    "x5t#S256": "bwcK0esc3ACC3DB2Y5_lESsXE8o9ltc05O89jdN-dg2"
  }
}
```

### SPKI Hash Calculation
```python
# SPKI Hash = Base64url(SHA256(SubjectPublicKeyInfo))
cert → public_key → SPKI (DER) → SHA-256 → Base64url → hash
```

### Validation Process
```python
# ARCP validates:
1. Extract x5t#S256 from token's cnf claim
2. Extract client certificate from request
3. Calculate SPKI hash from certificate
4. Compare: token_spki == cert_spki
```

## Certificate Management

### Best Practices
1. **Single Certificate Per Agent**: One cert per agent instance
2. **Secure Storage**: Store private key securely
3. **Certificate Lifecycle**: Plan for rotation
4. **Consistent Usage**: Always use same cert for token and requests
5. **Monitoring**: Track certificate expiration

### Certificate Rotation
```python
# Safe certificate rotation process:

# 1. Generate new certificate
new_cert, new_key = generate_new_certificate()

# 2. Request new token with new certificate
new_token = request_token_with_mtls(new_cert, new_key)

# 3. Switch to new certificate and token
session.update(cert=new_cert, key=new_key, token=new_token)

# 4. Revoke old certificate (optional)
revoke_certificate(old_cert)
```

## Debugging

### Check Token Binding
```python
import jwt

# Decode token to see binding
payload = jwt.decode(token, options={"verify_signature": False})
print("Token SPKI:", payload.get("cnf", {}).get("x5t#S256"))
```

### Check Certificate SPKI
```bash
# Calculate SPKI hash manually
openssl x509 -in client.crt -pubkey -noout | \
  openssl pkey -pubin -outform DER | \
  openssl dgst -sha256 -binary | \
  base64 | tr '+/' '-_' | tr -d '='
```

### Compare Both
```python
def debug_mtls_binding(token, cert_file):
    """Debug mTLS binding mismatch."""
    # Token SPKI
    token_payload = jwt.decode(token, options={"verify_signature": False})
    token_spki = token_payload.get("cnf", {}).get("x5t#S256")
    
    # Certificate SPKI
    cert_spki = calculate_cert_spki_hash(cert_file)
    
    print(f"Token SPKI:  {token_spki}")
    print(f"Cert SPKI:   {cert_spki}")
    print(f"Match:       {token_spki == cert_spki}")
    
    if token_spki != cert_spki:
        print("\n⚠️  Mismatch detected!")
        print("Token is bound to a different certificate.")
        print("You need to request a new token with the current certificate.")
```

## Configuration

### Enable mTLS Binding
```bash
# In .env
MTLS_ENABLED=true
MTLS_REQUIRED_REMOTE=true
```

When enabled, ARCP will:
1. Accept client certificates during token requests
2. Bind tokens to certificate SPKI hash (add `cnf.x5t#S256`)
3. Require matching certificate for protected endpoints
4. Validate SPKI hash matches token binding

## Related Problems

- [mtls-required](mtls-required.md) - Missing client certificate
- [dpop-binding-mismatch](dpop-binding-mismatch.md) - DPoP key mismatch (can combine both)
- [authentication-failed](authentication-failed.md) - General authentication errors
- [token-invalid](token-invalid.md) - Token validation issues

## References

- [RFC 8705: OAuth 2.0 mTLS](https://datatracker.ietf.org/doc/html/rfc8705)
- [RFC 8705 Section 3.1: Certificate Thumbprint](https://datatracker.ietf.org/doc/html/rfc8705#section-3.1)
- [ARCP mTLS Implementation](../security/mtls.md)
- [mTLS Implementation Guide](../security/mtls.md)
