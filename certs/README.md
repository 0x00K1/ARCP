# TLS Certificates Directory

This directory is where you should place your TLS/SSL certificates for ARCP to use HTTPS.

## 📁 Required Files

Place your TLS certificates in this directory:

```
certs/
├── server.crt     # Your TLS certificate
├── server.key     # Your private key
└── README.md      # This file
```

## 🎛️ Custom Certificate Names

If you want to use different filenames, update your `.env` file:

```env
ARCP_TLS_CERT_FILENAME=my-certificate.crt
ARCP_TLS_KEY_FILENAME=my-private-key.key
```

## 🔒 Security Notes

- **Never commit certificates to version control**
- Ensure certificate files have proper permissions (readable by ARCP process)
- Use strong private keys (RSA 2048+ or ECDSA P-256+)
- Keep private keys secure and never share them

## 🚀 Generating Self-Signed Certificates (For Testing)

For development/testing purposes, you can generate self-signed certificates:

```bash
# Generate private key
openssl genrsa -out server.key 2048

# Generate certificate signing request
openssl req -new -key server.key -out server.csr

# Generate self-signed certificate (valid for 365 days)
openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt

# Clean up CSR
rm server.csr
```

**Note:** Self-signed certificates should only be used for testing. Use proper CA-signed certificates in production.

## 📝 Certificate Validation

ARCP will validate that both certificate and key files exist and are readable during startup. If validation fails, ARCP will exit with an error message.

For questions or issues, refer to the main ARCP documentation.