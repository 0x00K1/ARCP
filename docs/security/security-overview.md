# ARCP Security Overview

This document provides a detailed overview of the security architecture, features, and best practices implemented in ARCP to protect against modern threats and ensure secure operations.

---

## 🛡️ Security Architecture Overview

ARCP implements a multi-layered security architecture designed to protect against various threat vectors while maintaining operational efficiency. The security framework is built around the principle of **Defense in Depth** with multiple independent layers of protection.

### Core Security Principles

- **Zero Trust Architecture**: Never trust, always verify
- **Principle of Least Privilege**: Minimal access rights by default
- **Defense in Depth**: Multiple security layers
- **Secure by Default**: Security-first configuration
- **Comprehensive Monitoring**: Full audit trail and real-time threat detection

---

## 🔐 Authentication & Authorization System

### Multi-Tier Authentication Model

ARCP implements a hierarchical authentication system with four distinct privilege levels:

| **Level** | **Access** | **Description** |
|-----------|------------|-----------------|
| `PUBLIC` | Read-only system info | No authentication required |
| `AGENT` | Agent operations | Token-based authentication |
| `ADMIN` | Administrative functions | JWT + session binding |
| `ADMIN_PIN` | Critical operations | Admin + PIN verification |

### JWT Token Security

**Implementation Features:**
- **Algorithm**: Configurable (HS256/HS384/HS512) with algorithm confusion protection
- **Expiration**: Configurable token lifetime (default: 1 hour)
- **Validation**: Comprehensive token validation with tamper detection
- **Rotation**: Automatic token refresh capabilities

**Security Measures:**
```python
# Token validation includes:
- Signature verification
- Expiration checking
- Algorithm validation (prevents algorithm confusion attacks)
- Payload integrity verification
- Blacklist checking for revoked tokens
```

### Session Management

**Admin Session Security:**
- **Client Fingerprinting**: Unique browser/client identification
- **Session Binding**: Tokens bound to specific client sessions
- **PIN Protection**: Additional PIN layer for critical operations
- **Session Timeout**: Configurable session expiration
- **Concurrent Session Limits**: Maximum active sessions per user

**Session Validation:**
```javascript
// Client-side session validation
- Token validity checking every 5 minutes
- Automatic logout on token expiration
- Session fingerprint verification
- Real-time session status monitoring
```

---

## 🚨 Rate Limiting & Brute Force Protection

### Advanced Rate Limiting System

ARCP implements a sophisticated rate limiting system with multiple protection mechanisms:

**Rate Limiting Tiers:**
- **Login Endpoints**: 5 attempts per 15 minutes
- **PIN Operations**: 3 attempts per 10 minutes  
- **General API**: 100 requests per minute (configurable)

**Protection Features:**
- **Progressive Delays**: Exponential backoff for failed attempts
- **Temporary Lockouts**: Automatic account lockouts after repeated failures
- **Anti-Bypass Protection**: IP header spoofing detection
- **Distributed Storage**: Redis-backed attempt tracking

**Lockout Algorithm:**
```python
# Progressive lockout duration calculation
base_duration = 5 minutes
lockout_duration = base_duration * (2 ^ (lockout_count - 1))
max_lockout = 1 hour
```

### Client-Side Rate Limiting

**JavaScript Security Manager:**
- Real-time attempt tracking
- Progressive delay enforcement
- Local storage persistence
- User experience optimization

---

## 🔍 Input Validation & Sanitization

### Comprehensive Input Security

**Validation Layers:**
1. **Pydantic Models**: Type and format validation
2. **Custom Validators**: Business logic validation  
3. **Security Sanitizers**: XSS and injection prevention
4. **Length Limits**: Buffer overflow protection

**Security Sanitization:**
```python
# Dangerous pattern detection and filtering
DANGEROUS_PATTERNS = [
    r"<[^>]*>",           # HTML tags
    r"javascript:",       # JavaScript URLs
    r"on\w+\s*=",        # Event handlers
    r"expression\s*\(",   # CSS expressions
    r"\.\./",            # Path traversal
    # ... and more
]
```

**Input Validation Examples:**
- **Agent IDs**: Alphanumeric, underscore, hyphen only
- **Usernames**: 3-50 characters, specific character set
- **Passwords**: 1-200 characters, full Unicode support
- **PINs**: 4-32 characters, numeric or alphanumeric

---

## 🌐 Network Security

### HTTP Security Headers

ARCP implements comprehensive security headers following OWASP recommendations:

```http
# Security Headers Applied
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'...
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()...
```

### Content Security Policy (CSP)

**Configurable CSP Settings:**
- **Development**: Permissive for local development
- **Production**: Strict policy with minimal trusted sources
- **WebSocket Support**: Secure WebSocket connections
- **External Resources**: Controlled CDN access for dependencies

### IP Filtering & Access Control

**IP-Based Security:**
- **Allowlist Mode**: Only specified IP ranges allowed
- **Blocklist Mode**: Specific IPs denied access
- **CIDR Support**: Network range specifications
- **Header Validation**: X-Forwarded-For protection

---

## 🔒 WebSocket Security

### Multi-Tier WebSocket Authentication

ARCP provides three types of WebSocket connections with different security levels:

| **Type** | **Endpoint** | **Authentication** | **Use Case** |
|----------|--------------|-------------------|--------------|
| Public | `/public/ws` | None | System status monitoring |
| Agent | `/agents/ws` | Agent Token | Agent communications |
| Dashboard | `/dashboard/ws` | Admin JWT + Fingerprint | Real-time dashboard |

### WebSocket Security Features

**Authentication Flow:**
```javascript
// Dashboard WebSocket authentication
ws.onopen = function() {
    ws.send(JSON.stringify({
        type: 'auth',
        token: jwt_token,
        fingerprint: client_fingerprint
    }));
};
```

**Security Measures:**
- **Token Validation**: JWT verification for each connection
- **Ping/Pong Monitoring**: Connection health verification
- **Rate Limiting**: Message frequency limits
- **Connection Limits**: Maximum concurrent connections
- **Automatic Reconnection**: Secure reconnection handling

---

## 🛡️ Content Filtering & XSS Protection

### Response Sanitization

**Security Sanitizer Features:**
- **HTML Entity Encoding**: Prevents script injection
- **Dangerous String Filtering**: Removes malicious patterns
- **Length Limits**: Prevents buffer overflow
- **Error Message Sanitization**: Prevents information disclosure

**Content Risk Detection:**
```python
# JSON response content scanning
ContentRiskDetector.scan_json_for_risk(payload)
# Flags potentially dangerous content without modifying response
```

### Error Handling Security

**RFC 9457 Problem Details:**
- Standardized error responses
- Information leakage prevention
- Sanitized error messages
- Structured error format

---

## 📊 Security Monitoring & Logging

### Comprehensive Audit Trail

**Security Event Types:**
- Authentication attempts (success/failure)
- Authorization failures
- Rate limit violations
- Suspicious activity detection
- Session management events
- Token validation failures

**Logging Levels:**
- **INFO**: Successful operations
- **WARNING**: Suspicious activities
- **ERROR**: Security violations
- **CRITICAL**: System compromises

### Real-Time Security Monitoring

**Dashboard Security Features:**
- Live security event monitoring
- Failed authentication tracking
- Rate limit status display
- Session health monitoring
- Alert generation and notification

**Client-Side Security Manager:**
```javascript
// Security event tracking and logging
SecurityManager.logSecurityEvent('failed_login', 'Invalid credentials', {
    username: sanitized_username,
    ip_address: client_ip,
    timestamp: new Date().toISOString()
});
```

---

## 🔧 Security Configuration

### Environment-Based Security

**Development vs Production:**
```bash
# Development (Permissive)
ENVIRONMENT=development
CSP_ALLOW_CONNECT_HTTP=true
RATE_LIMIT_RPM=100
LOG_LEVEL=DEBUG

# Production (Strict)
ENVIRONMENT=production
CSP_ALLOW_CONNECT_HTTP=false
RATE_LIMIT_RPM=60
SECURITY_LOGGING=true
IP_DEFAULT_DENY=true
```

### Security Configuration Options

**Authentication Settings:**
```bash
# JWT Configuration
JWT_SECRET=your-256-bit-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Admin Credentials
ADMIN_USERNAME=secure_admin_user
ADMIN_PASSWORD=complex_password_here

# Agent Registration Keys
AGENT_KEYS=key1,key2,key3
```

**Rate Limiting:**
```bash
# Rate Limit Configuration
RATE_LIMIT_RPM=100          # Requests per minute
RATE_LIMIT_BURST=20         # Burst allowance
SESSION_TIMEOUT=30          # Minutes
MAX_SESSIONS=5              # Concurrent sessions
```

**Network Security:**
```bash
# CORS and Origins
ALLOWED_ORIGINS=https://dashboard.example.com,https://monitor.example.com
TRUSTED_HOSTS=dashboard.example.com,api.example.com

# IP Filtering
IP_DEFAULT_DENY=false
BLOCKED_IPS=192.168.1.10,10.0.0.5
ALLOWED_IP_RANGES=10.0.0.0/8,192.168.0.0/16
```

---

## 🔍 Security Testing & Validation

### Penetration Testing Suite

ARCP includes a comprehensive security testing framework:

**Automated Security Tests:**
- Authentication bypass attempts
- JWT token manipulation attacks  
- Rate limiting bypass techniques
- Input validation and injection testing
- Session fixation and hijacking tests
- XSS and CSRF protection validation

**Security Test Categories:**
```python
# Included security tests
1. Authentication Bypass Tests
2. JWT Token Manipulation  
3. Rate Limiting Bypass
4. Session Hijacking Attempts
5. Input Validation & Injection
6. Authorization Boundary Tests
7. WebSocket Security Tests
8. Advanced Attack Vectors
```

### Security Validation Tools

**Built-in Security Scanner:**
```bash
# Run comprehensive security tests
python tests/security/security_pentest.py --target http://localhost:8001 --verbose

# Save results to a report file
python tests/security/security_pentest.py --target http://localhost:8001 --output security_report.txt
```

---

## Metrics Security Best Practices

To enhance security, ensure that metrics scraping is done via a secure token and restrict access to the `/metrics` endpoint to admin users only.

## 🔧 Advanced Security Configuration

### High-Security Environment Setup

**Maximum Security Configuration:**
```bash
# Ultra-secure production setup
ENVIRONMENT=production

# Strong authentication
JWT_SECRET=<256-bit-random-key-here>
JWT_ALGORITHM=HS384
JWT_EXPIRE_MINUTES=30

# Restrictive rate limiting
RATE_LIMIT_RPM=30
RATE_LIMIT_BURST=10
MAX_SESSIONS=3

# Strict network security
IP_DEFAULT_DENY=true
ALLOWED_IP_RANGES=<your-office-network>/24
CSP_ALLOW_CONNECT_HTTP=false
CSP_ALLOW_CONNECT_HTTPS=true

# Enhanced monitoring
SECURITY_LOGGING=true
LOG_LEVEL=INFO
CONTENT_FILTERING=true
```

### Security Headers Customization

**Custom Security Headers:**
```python
# Additional security headers for high-security environments
CUSTOM_SECURITY_HEADERS = {
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-Robots-Tag": "noindex, nofollow, nosnippet, noarchive",
    "X-Download-Options": "noopen",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin"
}
```

### Multi-Factor Authentication Integration

**MFA Implementation Considerations:**
- TOTP (Time-based One-Time Password) support
- Hardware token integration (YubiKey, etc.)
- SMS/Email verification backup
- Recovery code generation and management
- MFA enforcement for admin accounts

---

## Threat Detection & Response

### Automated Threat Detection

**Security Alert Triggers:**
- Multiple failed login attempts (>3 in 5 minutes)
- JWT token manipulation attempts
- Rate limiting violations
- Unusual access patterns
- Session hijacking indicators
- Input validation failures
- WebSocket connection anomalies

**Real-time Security Monitoring:**
```javascript
// Dashboard security monitoring
- Live authentication failure tracking
- Rate limit status visualization  
- Session health monitoring
- Alert generation with severity levels
- Automated response actions
```

### Security Metrics & KPIs

**Key Security Indicators:**
- Authentication success/failure rates
- Average session duration
- Rate limiting effectiveness
- Token validation failure rates
- Security event frequency by type
- Response time to security incidents
- Security patch deployment time

---

### Security Notifications

Monitor the following for security updates:
- GitHub Security Advisories
- Release notes for security fixes
- Dependency security updates
- CVE notifications for used libraries

### Security Resources

- [OWASP Security Guidelines](https://owasp.org/)
- [RFC 9457 Problem Details](https://tools.ietf.org/rfc/rfc9457.txt)
- [JWT Security Best Practices](https://tools.ietf.org/rfc/rfc8725.txt)
- [WebSocket Security](https://datatracker.ietf.org/doc/html/rfc6455)

---

*This security overview provides a comprehensive understanding of ARCP's security architecture. For implementation details, refer to the individual component documentation and configuration guides.*

**Last Updated:** September 2025  
**Version:** ARCP 2.0.2