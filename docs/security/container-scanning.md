# Container Security Scanning

**Version:** 2.1.0+  
**Feature Flags:** `CONTAINER_SCAN_ENABLED`, `CONTAINER_SCAN_REQUIRED`

---

## 📋 Overview

Container security scanning provides automated vulnerability detection in Docker container images before agent registration. ARCP integrates with industry-standard scanners to identify OS vulnerabilities, misconfigurations, and secrets embedded in container images.

### Why Container Scanning?

**Without Scanning:**
- ❌ Unknown vulnerabilities in base images
- ❌ Exposed secrets (API keys, passwords)
- ❌ Misconfigurations
- ❌ Compliance violations

**With Scanning:**
- ✅ Vulnerability detection in OS packages
- ✅ Secret scanning (API keys, tokens, passwords)
- ✅ Configuration validation
- ✅ Compliance checking (CIS benchmarks)
- ✅ Risk-based admission control

---

## ⚙️ Configuration

```bash
# Enable container scanning (default: false)
CONTAINER_SCAN_ENABLED=true

# Require scan for registration - strict mode (default: false)
CONTAINER_SCAN_REQUIRED=false

# Scanner to use: auto, trivy, or grype (default: auto)
CONTAINER_SCANNER=auto

# Fail on critical vulnerabilities (default: true)
CONTAINER_SCAN_FAIL_ON_CRITICAL=true

# Fail on high-severity vulnerabilities (default: false)
CONTAINER_SCAN_FAIL_ON_HIGH=false

# Fail on exposed secrets (default: true)
CONTAINER_SCAN_FAIL_ON_SECRETS=true

# Scan timeout in seconds (default: 300)
CONTAINER_SCAN_TIMEOUT=300

# Scan result cache TTL in seconds (default: 3600)
CONTAINER_SCAN_CACHE_TTL=3600

# Trivy cache directory
CONTAINER_TRIVY_CACHE_DIR=/home/arcp/.cache/trivy
```

---

## 🛠️ Supported Scanners

### Auto Mode (Recommended)

```bash
CONTAINER_SCANNER=auto
```

ARCP automatically detects and uses available scanners in order:
1. **Trivy** (preferred)
2. **Grype**

### Trivy (Recommended)

```bash
# Install Trivy
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt update && sudo apt install trivy

# Configure
CONTAINER_SCANNER=trivy
```

**Features:**
- Fast scanning
- Comprehensive vulnerability database
- Secret detection
- Misconfiguration scanning
- CIS benchmark checks

### Grype

```bash
# Install Grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh

# Configure
CONTAINER_SCANNER=grype
```

**Features:**
- Fast vulnerability scanning
- Multiple vulnerability databases
- Docker and OCI image support

---

## 🔍 Scan Types

### Vulnerability Scanning

Detects known CVEs in:
- OS packages (apt, yum, apk)
- Language-specific packages (npm, pip, gem)
- Application dependencies

**Example Findings:**
```json
{
  "vulnerabilities": [
    {
      "id": "CVE-2023-12345",
      "severity": "CRITICAL",
      "package": "openssl",
      "installed_version": "1.1.1k",
      "fixed_version": "1.1.1l",
      "description": "OpenSSL vulnerability allows remote code execution"
    }
  ]
}
```

### Secret Detection

Finds exposed secrets:
- API keys
- AWS credentials
- Private keys
- Passwords
- Tokens

**Example Findings:**
```json
{
  "secrets": [
    {
      "type": "aws-access-key-id",
      "match": "AKIA****************",
      "file": "/app/config.py",
      "line": 15
    }
  ]
}
```

### Misconfiguration Detection

Identifies security misconfigurations:
- Running as root
- Exposed ports
- Insecure environment variables
- Missing security contexts

---

## 🚀 Usage During TPR

### Phase 2: Validation

Include container image information in validation request:

```python
validation_request = {
    "agent_id": "my-agent",
    "agent_type": "security",
    "endpoint": "https://agent.example.com",
    "container_image": {
        "registry": "docker.io",
        "repository": "myorg/agent",
        "tag": "1.0.0",
        "digest": "sha256:abc123..."
    }
}
```

### Validation Response

**Success (No Critical Issues):**
```json
{
  "status": "passed",
  "container_scan": {
    "image": "myorg/agent:1.0.0",
    "scanner": "trivy",
    "scan_time": "2026-02-16T10:30:00Z",
    "vulnerabilities": {
      "critical": 0,
      "high": 1,
      "medium": 5,
      "low": 12
    },
    "secrets_found": 0,
    "misconfigurations": []
  }
}
```

**Failure (Critical Vulnerabilities):**
```json
{
  "status": "failed",
  "errors": [
    {
      "check": "container_scan",
      "severity": "critical",
      "message": "Critical vulnerabilities found in container image",
      "details": {
        "vulnerabilities": [
          {
            "id": "CVE-2023-12345",
            "severity": "CRITICAL",
            "package": "openssl",
            "description": "Remote code execution vulnerability"
          }
        ]
      }
    }
  ]
}
```

**Failure (Secrets Detected):**
```json
{
  "status": "failed",
  "errors": [
    {
      "check": "container_scan",
      "severity": "critical",
      "message": "Secrets found in container image",
      "details": {
        "secrets": [
          {
            "type": "aws-access-key",
            "file": "/app/.env",
            "line": 5
          }
        ]
      }
    }
  ]
}
```

---

## 📝 Best Practices

### Image Building

**✅ Do:**
- Use minimal base images (alpine, distroless)
- Multi-stage builds to reduce attack surface
- Regular base image updates
- Scan images in CI/CD pipeline
- Sign images for integrity

```dockerfile
# Good: Multi-stage build with minimal base
FROM python:3.11-alpine AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-alpine
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY app/ .
USER nobody
CMD ["python", "main.py"]
```

**❌ Don't:**
- Use `latest` tag
- Run as root
- Include secrets in image
- Use outdated base images
- Skip vulnerability scanning

```dockerfile
# Bad: Running as root with latest tag
FROM ubuntu:latest
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "app.py"]  # Running as root!
```

### Secret Management

**✅ Proper Secret Handling:**
```dockerfile
# Use secrets at runtime, not build time
FROM python:3.11-alpine
ENV API_KEY_FILE=/run/secrets/api_key
CMD ["python", "app.py"]
```

```bash
# Pass secrets at runtime
docker run -v /path/to/secret:/run/secrets/api_key myimage
```

**❌ Bad Secret Handling:**
```dockerfile
# NEVER do this!
FROM python:3.11
ENV API_KEY=super-secret-key-123
COPY .env /app/.env
```

### Vulnerability Management

**Priority-based remediation:**
1. **CRITICAL** - Fix immediately
2. **HIGH** - Fix within 7 days
3. **MEDIUM** - Fix within 30 days
4. **LOW** - Fix during regular updates

---

## 🔨 Manual Scanning

### Scan Local Images

```bash
# Using Trivy
trivy image myimage:latest

# With severity filtering
trivy image --severity CRITICAL,HIGH myimage:latest

# JSON output
trivy image -f json -o scan-results.json myimage:latest

# Secret scanning
trivy image --scanners secret myimage:latest
```

### Scan Remote Images

```bash
# Scan from registry
trivy image docker.io/library/nginx:latest

# Scan private registry
trivy image \
  --username $REGISTRY_USER \
  --password $REGISTRY_PASSWORD \
  myregistry.com/myimage:1.0.0
```

### Scan Filesystem

```bash
# Scan directory
trivy fs /path/to/project

# Scan IaC files
trivy config /path/to/terraform
```

---

## 🐛 Troubleshooting

### Scanner Not Found

```json
{
  "error": "No container scanner available. Install Trivy or Grype"
}
```

**Solution:**
```bash
# Install Trivy (recommended)
sudo apt install trivy

# Or use Docker image
docker run aquasec/trivy:latest image myimage:latest
```

### Scan Timeout

```json
{
  "error": "Container scan timed out after 300 seconds"
}
```

**Solution:**
- Increase `CONTAINER_SCAN_TIMEOUT`
- Check network connectivity
- Verify image is accessible
- Use faster scanner (Trivy)

### Database Update Failed

```json
{
  "warning": "Vulnerability database is outdated"
}
```

**Solution:**
```bash
# Update Trivy database
trivy image --download-db-only

# Or clear cache
rm -rf $CONTAINER_TRIVY_CACHE_DIR
```

---

## 📊 Performance Optimization

### Caching

```bash
# Enable caching (default: 3600 seconds = 1 hour)
CONTAINER_SCAN_CACHE_TTL=3600
```

**Note:** Trivy uses its own cache directory (typically `~/.cache/trivy`). Configure it using Trivy's `--cache-dir` flag or `CONTAINER_TRIVY_CACHE_DIR` environment variable if needed.

### Parallel Scanning

For multiple images:
```python
import asyncio

async def scan_images(images):
    tasks = [scan_image(img) for img in images]
    results = await asyncio.gather(*tasks)
    return results
```

---

## 📚 Related Documentation

- [Three-Phase Registration](./three-phase-registration.md)
- [SBOM Verification](./sbom.md)
- [Security Overview](./security-overview.md)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [Grype Documentation](https://github.com/anchore/grype)

---

**Last Updated:** February 16, 2026  
**Version:** 2.1.0
