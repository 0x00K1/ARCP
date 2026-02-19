# SBOM (Software Bill of Materials) Verification

**Version:** 2.1.0+  
**Feature Flags:** `SBOM_VERIFICATION_ENABLED`, `SBOM_REQUIRED`

---

## 📋 Overview

SBOM (Software Bill of Materials) verification provides automated security scanning of agent dependencies to identify known vulnerabilities before registration. ARCP validates SBOMs against the OSV (Open Source Vulnerabilities) database to ensure agents don't introduce security risks.

### Why SBOM Verification?

**Without SBOM:**
- ❌ Unknown dependencies
- ❌ Hidden vulnerabilities
- ❌ Supply chain risks
- ❌ No compliance tracking

**With SBOM:**
- ✅ Complete dependency inventory
- ✅ Automated vulnerability scanning
- ✅ Supply chain transparency
- ✅ Compliance evidence
- ✅ Risk-based decisions

---

## ⚙️ Configuration

```bash
# Enable SBOM verification (default: false)
SBOM_VERIFICATION_ENABLED=true

# Require SBOM for registration - strict mode (default: false)
SBOM_REQUIRED=false

# Allowed SBOM formats (comma-separated, default: cyclonedx,spdx)
SBOM_ALLOWED_FORMATS=cyclonedx,spdx

# Fail on critical vulnerabilities (default: true)
SBOM_FAIL_ON_CRITICAL=true

# Fail on high-severity vulnerabilities (default: false)
SBOM_FAIL_ON_HIGH=false

# Enable vulnerability checking (default: true)
SBOM_VULNERABILITY_CHECK=true

# Vulnerability cache TTL in seconds (default: 3600)
SBOM_VULNERABILITY_CACHE_TTL=3600

# OSV API configuration
SBOM_OSV_API_URL=https://api.osv.dev/v1
SBOM_OSV_API_TIMEOUT=30
```

---

## 📦 Supported SBOM Formats

### SPDX (Software Package Data Exchange)

```json
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "name": "my-agent-sbom",
  "documentNamespace": "https://agent.example.com/sbom/1.0.0",
  "packages": [
    {
      "name": "requests",
      "versionInfo": "2.28.0",
      "downloadLocation": "https://pypi.org/project/requests/2.28.0",
      "licenseConcluded": "Apache-2.0",
      "externalRefs": [
        {
          "referenceCategory": "PACKAGE-MANAGER",
          "referenceType": "purl",
          "referenceLocator": "pkg:pypi/requests@2.28.0"
        }
      ]
    }
  ]
}
```

### CycloneDX

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.4",
  "version": 1,
  "components": [
    {
      "type": "library",
      "name": "requests",
      "version": "2.28.0",
      "purl": "pkg:pypi/requests@2.28.0",
      "licenses": [
        {
          "license": {
            "id": "Apache-2.0"
          }
        }
      ]
    }
  ]
}
```

**Note:** CycloneDX 1.4+ is recommended for best compatibility.

---

## 🔍 Vulnerability Checking

### OSV Database Integration

ARCP queries the [OSV (Open Source Vulnerabilities)](https://osv.dev/) database for each dependency:

```python
# For each dependency
query = {
    "package": {
        "name": "requests",
        "ecosystem": "PyPI"
    },
    "version": "2.28.0"
}

response = requests.post(
    f"{SBOM_OSV_API_URL}/query",
    json=query,
    timeout=SBOM_OSV_API_TIMEOUT
)

vulnerabilities = response.json().get("vulns", [])
```

### Severity Levels

Vulnerabilities are categorized by severity:

| Severity | CVSS Score | Action |
|----------|------------|--------|
| CRITICAL | 9.0-10.0 | Fail if `SBOM_FAIL_ON_CRITICAL=true` |
| HIGH | 7.0-8.9 | Fail if `SBOM_FAIL_ON_HIGH=true` |
| MEDIUM | 4.0-6.9 | Warning only |
| LOW | 0.1-3.9 | Info only |

---

## 🚀 Usage During TPR

### Phase 2: Validation

Include SBOM in validation request:

```python
validation_request = {
    "agent_id": "my-agent",
    "agent_type": "security",
    "endpoint": "https://agent.example.com",
    "sbom": {
        "format": "cyclonedx",
        "data": {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "components": [...]
        }
    }
}
```

### Validation Response

**Success (No Critical Vulnerabilities):**
```json
{
  "status": "passed",
  "sbom_verification": {
    "dependencies_scanned": 45,
    "vulnerabilities_found": 2,
    "severity_breakdown": {
      "critical": 0,
      "high": 0,
      "medium": 1,
      "low": 1
    },
    "vulnerable_packages": [
      {
        "name": "urllib3",
        "version": "1.26.5",
        "vulnerabilities": [
          {
            "id": "PYSEC-2021-108",
            "severity": "MEDIUM",
            "summary": "urllib3 before 1.26.5 allows header injection"
          }
        ]
      }
    ]
  }
}
```

**Failure (Critical Vulnerabilities Found):**
```json
{
  "status": "failed",
  "errors": [
    {
      "check": "sbom_verification",
      "severity": "critical",
      "message": "Critical vulnerabilities found in dependencies",
      "details": {
        "package": "requests",
        "version": "2.25.0",
        "vulnerabilities": [
          {
            "id": "CVE-2023-32681",
            "severity": "CRITICAL",
            "cvss_score": 9.1,
            "summary": "Requests is vulnerable to SSRF"
          }
        ]
      }
    }
  ]
}
```

---

## 📝 Generating SBOMs

### Python (using pip)

```bash
# Install sbom generator
pip install cyclonedx-bom

# Generate CycloneDX SBOM
cyclonedx-py -o sbom.json

# Or use syft
syft packages dir:. -o cyclonedx-json > sbom.json
```

### Node.js (using npm)

```bash
# Generate CycloneDX SBOM
npx @cyclonedx/cyclonedx-npm --output-file sbom.json

# Or use syft
syft packages dir:. -o cyclonedx-json > sbom.json
```

### Docker Images

```bash
# Using syft
syft image-name:tag -o cyclonedx-json > sbom.json

# Using docker sbom (Docker Desktop)
docker sbom image-name:tag --format cyclonedx-json > sbom.json
```

---

## 🎯 Best Practices

**✅ Do:**
- Generate SBOMs from CI/CD pipeline
- Update SBOMs with every build
- Include all dependencies (direct + transitive)
- Use Package URLs (purl) for accuracy
- Scan SBOMs regularly for new vulnerabilities

**❌ Don't:**
- Manually create SBOMs (error-prone)
- Omit transitive dependencies
- Use outdated SBOM formats
- Ignore vulnerability warnings
- Cache SBOMs for too long

---

## 🐛 Troubleshooting

### SBOM Format Not Supported

```json
{
  "error": "SBOM format 'unknown' not allowed. Supported: cyclonedx, spdx"
}
```

**Solution:** Use one of the supported formats (CycloneDX or SPDX) or update `SBOM_ALLOWED_FORMATS`

### Vulnerability Check Timeout

```json
{
  "warning": "Vulnerability check timed out for some dependencies"
}
```

**Solution:** Increase `SBOM_OSV_API_TIMEOUT` or check network connectivity

### Critical Vulnerabilities Block Registration

```json
{
  "status": "failed",
  "message": "Critical vulnerabilities found, registration blocked"
}
```

**Solution:**
- Update vulnerable dependencies
- Apply security patches
- If false positive, set `SBOM_FAIL_ON_CRITICAL=false` temporarily

---

## 📚 Related Documentation

- [Three-Phase Registration](./three-phase-registration.md)
- [Container Scanning](./container-scanning.md)
- [Security Overview](./security-overview.md)
- [OSV Database](https://osv.dev/)
- [CycloneDX Specification](https://cyclonedx.org/)
- [SPDX Specification](https://spdx.dev/)

---

**Last Updated:** February 16, 2026  
**Version:** 2.1.0
