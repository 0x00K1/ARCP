# Client Certificate Required

**Type URI:** `https://arcp.0x001.tech/docs/problems/mtls-required`  
**HTTP Status:** `401 Unauthorized`  
**Title:** Client Certificate Required

## Description

This problem occurs when mutual TLS (mTLS) client certificate authentication is required but no valid client certificate was provided. mTLS ensures that both the server and client authenticate each other using X.509 certificates, providing strong cryptographic proof of identity.

## When This Occurs

- mTLS is enabled (`MTLS_ENABLED=true`) and required for remote clients (`MTLS_REQUIRED_REMOTE=true`)
- Request is from a remote client (not localhost) without a client certificate
- Client certificate is invalid, expired, or not trusted
- Certificate chain validation failed
- Accessing mTLS-protected endpoints without proper certificate setup

## Example Response

```json
{
  "type": "https://arcp.0x001.tech/docs/problems/mtls-required",
  "title": "Client Certificate Required",
  "status": 401,
  "detail": "mTLS client certificate is required for remote agents",
  "instance": "/agents/validate_compliance",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req_mtls_123"
}
```

## Common Scenarios

### 1. Remote Client Without Certificate
```bash
# Wrong: Remote request without client cert
curl -X POST "https://arcp.example.com/agents/validate_compliance" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"compliance_data": {...}}'

# Result: mtls-required error
```

### 2. Invalid or Expired Certificate
```bash
# Certificate expired or not trusted
curl --cert expired-client.crt --key client.key \
  -X POST "https://arcp.example.com/agents/register" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

### 3. Missing Certificate in Production
```python
# Works locally (localhost exempt)
response = requests.post(
    "http://localhost:8001/agents/register",
    headers={"Authorization": f"Bearer {token}"},
    json=registration_data
)

# Fails in production without cert
response = requests.post(
    "https://arcp.example.com/agents/register",
    headers={"Authorization": f"Bearer {token}"},
    json=registration_data
)
# Result: mtls-required error
```

## Resolution Steps

### 1. Generate Client Certificate
Create a client certificate signed by your CA:

```bash
# Generate private key
openssl genrsa -out client.key 2048

# Create certificate signing request
openssl req -new -key client.key -out client.csr \
  -subj "/CN=my-agent-client/O=MyOrg"

# Sign with CA (or self-sign for testing)
openssl x509 -req -in client.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days 365 -sha256
```

### 2. Configure Client to Use Certificate
With curl:
```bash
curl --cert client.crt --key client.key \
  --cacert ca.crt \
  -X POST "https://arcp.example.com/agents/validate_compliance" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"compliance_data": {...}}'
```

With Python requests:
```python
import requests

response = requests.post(
    "https://arcp.example.com/agents/validate_compliance",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    cert=("client.crt", "client.key"),
    verify="ca.crt",  # or True for system CA
    json=compliance_data
)
```

### 3. Use mTLS Helper
```python
from examples.agents.mtls_helper import MTLSClientHelper

# Initialize with certificates
helper = MTLSClientHelper(
    cert_file="client.crt",
    key_file="client.key",
    ca_file="ca.crt"
)

# Make request with mTLS
response = helper.post(
    "https://arcp.example.com/agents/validate_compliance",
    headers={"Authorization": f"Bearer {token}"},
    json=compliance_data
)
```

### 4. Verify Certificate Configuration
```bash
# Test certificate with OpenSSL
openssl s_client -connect arcp.example.com:443 \
  -cert client.crt -key client.key \
  -CAfile ca.crt

# Check certificate details
openssl x509 -in client.crt -text -noout

# Verify certificate chain
openssl verify -CAfile ca.crt client.crt
```

## Technical Details

### Certificate Requirements
- **Format**: X.509 certificate in PEM format
- **Key Size**: Minimum 2048-bit RSA or 256-bit EC
- **Signature**: SHA-256 or stronger
- **Validity**: Not expired, not yet valid
- **Chain**: Must chain to trusted CA

### SPKI Hash Calculation
ARCP uses Subject Public Key Info (SPKI) hash for certificate binding:

```python
import hashlib
import base64
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

def calculate_spki_hash(cert_pem):
    """Calculate SPKI hash for certificate."""
    cert = x509.load_pem_x509_certificate(
        cert_pem.encode(),
        default_backend()
    )
    
    # Get public key
    public_key = cert.public_key()
    
    # Serialize to DER
    spki_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # SHA-256 hash
    hash_bytes = hashlib.sha256(spki_der).digest()
    
    # Base64url encode
    spki_hash = base64.urlsafe_b64encode(hash_bytes).decode().rstrip('=')
    
    return spki_hash
```

### Token Binding with mTLS
During validation, ARCP can bind the token to the certificate:

```json
{
  "sub": "agent-123",
  "role": "agent",
  "cnf": {
    "x5t#S256": "bwcK0esc3ACC3DB2Y5_lESsXE8o9ltc05O89jdN-dg2"
  }
}
```

### Server-Side Validation
```python
# ARCP validates:
1. Certificate present in request
2. Certificate is valid (not expired)
3. Certificate chains to trusted CA
4. SPKI hash matches token binding (if present)
```

## Configuration

### Server Configuration
```bash
# In .env
MTLS_ENABLED=true
MTLS_REQUIRED_REMOTE=true  # Only for remote (non-localhost) clients
MTLS_CA_CERT_PATH=/path/to/ca.crt
```

### Nginx/Reverse Proxy Setup
```nginx
server {
    listen 443 ssl;
    server_name arcp.example.com;
    
    # Server certificate
    ssl_certificate /path/to/server.crt;
    ssl_certificate_key /path/to/server.key;
    
    # Client certificate verification
    ssl_client_certificate /path/to/ca.crt;
    ssl_verify_client optional;  # or 'on' for strict
    ssl_verify_depth 2;
    
    location / {
        proxy_pass http://localhost:8001;
        
        # Forward certificate to app
        proxy_set_header X-SSL-Client-Cert $ssl_client_cert;
        proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
        proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;
    }
}
```

## Localhost Exemption

Local development is exempt from mTLS:
```python
# Localhost requests don't require mTLS
# Even when MTLS_REQUIRED_REMOTE=true

# OK without cert:
curl http://localhost:8001/agents/register

# OK without cert:
curl http://127.0.0.1:8001/agents/register

# Requires cert (remote):
curl https://arcp.example.com/agents/register
```

## Testing mTLS

### Generate Test Certificates
```bash
cd certs/

# Generate CA
./generate_test_ca.sh

# Generate client cert
./generate_client_cert.sh my-agent-client
```

### Test with curl
```bash
# Test mTLS connection
curl -v --cert client.crt --key client.key \
  --cacert ca.crt \
  https://arcp.example.com/agents/discover
```

## Common Issues

1. **Certificate Expired**: Check validity dates
2. **Wrong CA**: Client cert not signed by trusted CA
3. **Missing Intermediate Certs**: Incomplete certificate chain
4. **Permission Issues**: Certificate files not readable
5. **Format Issues**: Certificate not in PEM format

## Related Problems

- [mtls-binding-mismatch](mtls-binding-mismatch.md) - Certificate doesn't match token binding
- [authentication-failed](authentication-failed.md) - General authentication errors
- [dpop-required](dpop-required.md) - DPoP proof required (can be combined with mTLS)

## References

- [RFC 8705: OAuth 2.0 mTLS](https://datatracker.ietf.org/doc/html/rfc8705)
- [ARCP mTLS Implementation](../security/mtls.md)
- [mTLS Implementation Guide](../security/mtls.md)
- [NGINX Deployment with mTLS](../deployment/nginx.md)
