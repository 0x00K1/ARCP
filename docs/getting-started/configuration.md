# Configuration Guide

ARCP is highly configurable through environment variables. This guide covers all configuration options, from basic setup to advanced security and performance tuning.

## 🔧 Configuration Methods

### Environment Variables (Recommended)

ARCP reads configuration from environment variables. You can set them in several ways:

```bash
# Direct export
export JWT_SECRET=your-secret-key
export ADMIN_USERNAME=ARCP

# Using .env file
echo "JWT_SECRET=your-secret-key" >> .env
echo "ADMIN_USERNAME=ARCP" >> .env

# Docker environment
docker run -e JWT_SECRET=your-secret-key -e ADMIN_USERNAME=ARCP arcp
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  arcp:
    environment:
      JWT_SECRET: your-secret-key
      ADMIN_USERNAME: admin
      # ... other variables
    prometheus:
        env_file:
            - .env
        environment:
            METRICS_SCRAPE_TOKEN: ${METRICS_SCRAPE_TOKEN}
```

#### Docker Deployment Notes (Production)

When running with `ENVIRONMENT=production` via Docker Compose:

1. Include all internal service hostnames and the overlay subnet in `TRUSTED_HOSTS` so inter‑container requests (health checks, metrics, tracing, Redis, etc.) are accepted.
2. Ensure your `.env` is available to the compose file (copy it next to `docker-compose.yml` or pass it explicitly with `--env-file`).

Internal services defined in the provided compose file:

```
arcp, redis, redis-exporter, prometheus, grafana, jaeger
```

Network subnet (from compose `arcp_network`):

```
172.20.0.0/16
```

Recommended production `TRUSTED_HOSTS` example (add your public domains first):

```bash
TRUSTED_HOSTS=yourdomain.com,api.yourdomain.com,arcp,redis,redis-exporter,prometheus,grafana,jaeger,172.20.0.0/16
```

Example `.env` fragment for production Docker:

```bash
ENVIRONMENT=production
ARCP_PORT=8001
ARCP_HOST=0.0.0.0
TRUSTED_HOSTS=yourdomain.com,api.yourdomain.com,arcp,redis,redis-exporter,prometheus,grafana,jaeger,172.20.0.0/16
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
```

MANDATORY for Docker Compose runs:

Place your `.env` file in `deployment/docker/` (the same directory as `docker-compose.yml`). Docker Compose will auto‑load it when you run from that folder. This is the default and simplest method.

```bash
# From repo root
copy .env deployment/docker/.env   # Windows (PowerShell)
# or
cp .env deployment/docker/.env     # Linux / macOS

cd deployment/docker
docker compose up -d
```

Alternative (advanced): If you intentionally keep the master `.env` at the repo root, you MUST explicitly pass it:

```bash
cd deployment/docker
docker compose --env-file ../../.env up -d
```

This ensures all docker services share the same configuration while allowing required internal communication.

## 📋 Required Configuration

These environment variables are **required** for ARCP to start:

### Core Settings

```bash
# Environment (development, testing, production)
ENVIRONMENT=development

# Timezone (UTC, Asia/Riyadh, America/New_York, Europe/London, etc.)
# Accepts either TZ or TIMEZONE environment variables
TZ=UTC

# Agent Types (comma-separated)
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,testing

# JWT Configuration
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=3000

# Admin Authentication
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP
```

### Example Minimal Configuration

```bash
# .env file
ENVIRONMENT=development
TZ=UTC
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,testing
JWT_SECRET=my-super-secret-jwt-key-that-is-at-least-32-characters-long
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=3000
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP
```

## 🌐 Server Configuration

### Network Settings

```bash
# Server binding
ARCP_HOST=0.0.0.0          # Host to bind to (0.0.0.0 for all interfaces)
ARCP_PORT=8001             # Port to listen on
ARCP_DEBUG=false           # Enable debug mode (true/false)

# Logging
LOG_LEVEL=INFO             # DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
ARCP_LOGS_DIR=/app/logs    # Log directory
```

### Data Storage

```bash
# Data directories
ARCP_DATA_DIR=/app/data                   # Main data directory
STATE_FILE=registry_state.json            # Agent registry state file
REDIS_DATA_DIR=/data                      # Redis data directory
PROMETHEUS_DATA_DIR=/data                 # Prometheus data directory
GRAFANA_DATA_DIR=/var/lib/grafana         # Grafana data directory
```

## 🔐 Security Configuration

### Authentication & Authorization

```bash
# JWT Settings
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters
JWT_ALGORITHM=HS256                       # HS256, HS384, HS512
JWT_EXPIRE_MINUTES=3000                   # Token expiration in minutes

# Admin Credentials [Change in production!]
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP

# Agent Registration Keys
AGENT_KEYS=test-agent-001,test-agent-002,test-agent-003
```

### Network Security

```bash
# CORS Configuration
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:8001
TRUSTED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Content Security Policy
CSP_ALLOW_CONNECT_HTTP=true              # Allow HTTP connections (dev only)
CSP_ALLOW_CONNECT_HTTPS=true             # Allow HTTPS connections

# IP Filtering
IP_DEFAULT_DENY=false                        # Default deny mode
BLOCKED_IPS=192.168.1.100,10.0.0.50          # Blocked IP addresses
ALLOWED_IP_RANGES=192.168.1.0/24,10.0.0.0/8  # Allowed IP ranges
```

### Rate Limiting

```bash
# Rate Limiting
RATE_LIMIT_RPM=100                       # Requests per minute
RATE_LIMIT_BURST=20                      # Burst size
SESSION_TIMEOUT=30                       # Session timeout in minutes
MAX_SESSIONS=5                           # Maximum concurrent sessions per user

# Request Security
MAX_JSON_SIZE=1048576                    # Max JSON payload size (1MB)
MAX_QUERY_PARAMS=50                      # Maximum query parameters
MAX_HEADER_SIZE=8192                     # Max header size (8KB)
```

### Security Monitoring

```bash
# Security Features
SECURITY_LOGGING=true                    # Enable security event logging
CONTENT_FILTERING=true                   # Enable content filtering
```

## 🤖 Agent Configuration

### Agent Management

```bash
# Agent Lifecycle
AGENT_HEARTBEAT_TIMEOUT=60               # Heartbeat timeout in seconds
AGENT_CLEANUP_INTERVAL=60                # Cleanup interval in seconds
AGENT_REGISTRATION_TIMEOUT=30            # Registration timeout in seconds

# Agent Types
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,testing

# Agent Type Validation Rules:
# - Must contain at least 1 type, maximum 100 types
# - Each type: 2-50 characters long
# - Only alphanumeric characters, hyphens (-), and underscores (_) allowed
# - Comma-separated list (no spaces around commas recommended)
```

### Vector Search (Optional)

```bash
# Vector Search Settings
VECTOR_SEARCH_TOP_K=10                   # Number of results to return
VECTOR_SEARCH_MIN_SIMILARITY=0.5         # Minimum similarity threshold (0.0-1.0)
```

## 🌐 WebSocket Configuration

### Connection Settings

```bash
# Global WebSocket Settings (fallbacks)
WEBSOCKET_INTERVAL=30                    # Update interval in seconds
WEBSOCKET_TIMEOUT=30                     # Connection timeout in seconds
WEBSOCKET_PING_INTERVAL=30               # Ping interval in seconds
WEBSOCKET_MAX_CONNECTIONS=100            # Maximum connections

# Dashboard WebSocket
DASHBOARD_WS_INTERVAL=5                  # Dashboard update interval
DASHBOARD_WS_TIMEOUT=30                  # Dashboard timeout
DASHBOARD_WS_PING_INTERVAL=30            # Dashboard ping interval
DASHBOARD_WS_MAX_CONNECTIONS=5           # Dashboard max connections

# Agent WebSocket
AGENT_WS_INTERVAL=5                      # Agent update interval
AGENT_WS_TIMEOUT=30                      # Agent timeout
AGENT_WS_PING_INTERVAL=30                # Agent ping interval
AGENT_WS_MAX_CONNECTIONS=100             # Agent max connections

# Public WebSocket
PUBLIC_WS_INTERVAL=30                    # Public update interval
PUBLIC_WS_TIMEOUT=30                     # Public timeout
PUBLIC_WS_PING_INTERVAL=30               # Public ping interval
PUBLIC_WS_MAX_CONNECTIONS=100            # Public max connections
```

## 🗄️ Storage Configuration

### Redis Settings

```bash
# Redis Connection
REDIS_HOST=redis                         # Redis hostname
REDIS_PORT=6379                          # Redis port
REDIS_PASSWORD=admin                     # Redis password
REDIS_DB=0                               # Redis database number
REDIS_HEALTH_CHECK_INTERVAL=30           # Health check interval
REDIS_MAX_MEMORY=256mb                   # Maximum memory usage
REDIS_EXPORTER_PORT=9121                 # Redis exporter port
```

## 🤖 AI Integration

### Azure OpenAI Configuration

```bash
# Azure OpenAI Settings
AZURE_API_KEY=your-azure-openai-api-key
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_API_VERSION=your-api-version
# IMPORTANT: This MUST be an EMBEDDING model deployment, not a chat/completion model
# Recommended embedding models:
#   - text-embedding-ada-002    (Most common, good performance)
#   - text-embedding-3-small    (Newer, smaller model)
#   - text-embedding-3-large    (Newer, larger model)
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
```

**Note**: Azure OpenAI is optional but enables semantic search capabilities. Without it, ARCP falls back to simple text matching.

## 📊 Monitoring Configuration

### Prometheus

```bash
# Prometheus Settings
PROMETHEUS_HOST=prometheus               # Prometheus hostname
PROMETHEUS_PORT=9090                     # Prometheus port
METRICS_SCRAPE_TOKEN=random-token        # ARCP metrics scrape token
```

### Grafana

```bash
# Grafana Settings
GRAFANA_HOST=grafana                     # Grafana hostname
GRAFANA_PORT=3000                        # Grafana port
GRAFANA_PASSWORD=admin                   # Grafana admin password
```

### Jaeger Tracing

```bash
# Tracing Settings
TRACING_ENABLED=false                    # Enable distributed tracing
JAEGER_ENDPOINT=http://jaeger:14268/api/traces
OTLP_ENDPOINT=http://jaeger:4317
TRACE_SERVICE_NAME=arcp
TRACE_SERVICE_VERSION=2.0.0
TRACE_ENVIRONMENT=development
TRACE_SAMPLE_RATE=1.0

# Jaeger Ports
JAEGER_UI_PORT=16686
JAEGER_GRPC_PORT=14250
JAEGER_THRIFT_PORT=14268
JAEGER_OTLP_GRPC_PORT=4317
JAEGER_OTLP_HTTP_PORT=4318
JAEGER_METRICS_PORT=14269
```

## 🌐 Network Configuration

### Network Interface

```bash
# Network Settings
NETWORK_INTERFACE_CAPACITY_MBPS=1000     # Network capacity in Mbps
```

## 📝 Logging Configuration

### Dashboard Logs

```bash
# Dashboard Log Settings
DASHBOARD_LOG_BUFFER_MAXLEN=10000        # Max log buffer length
DASHBOARD_LOG_MESSAGE_MAXLEN=2048        # Max log message length
```

## 🏭 Environment-Specific Configurations

### Development Environment

```bash
ENVIRONMENT=development
ARCP_DEBUG=true
LOG_LEVEL=DEBUG
CSP_ALLOW_CONNECT_HTTP=true
RATE_LIMIT_RPM=1000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:8001
TRUSTED_HOSTS=localhost,127.0.0.1,0.0.0.0
```

### Testing Environment

```bash
ENVIRONMENT=testing
ARCP_DEBUG=true
LOG_LEVEL=DEBUG
JWT_EXPIRE_MINUTES=60
RATE_LIMIT_RPM=10000
ALLOWED_ORIGINS=*
TRUSTED_HOSTS=*
```

### Production Environment

```bash
ENVIRONMENT=production
ARCP_DEBUG=false
LOG_LEVEL=INFO
CSP_ALLOW_CONNECT_HTTP=false
CSP_ALLOW_CONNECT_HTTPS=true
RATE_LIMIT_RPM=100
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
TRUSTED_HOSTS=yourdomain.com,api.yourdomain.com
SECURITY_LOGGING=true
CONTENT_FILTERING=true
IP_DEFAULT_DENY=false
```

## 🔧 Configuration Validation

ARCP validates configuration on startup. You can check your configuration:

### Using Docker

```bash
# Check configuration
docker-compose -f deployment/docker/docker-compose.yml config

# Validate and start
docker-compose -f deployment/docker/docker-compose.yml up -d
```

### Using Python

```python
from arcp.core.config import config

# Validate configuration
missing = config.validate_required_config()
if missing:
    print("Missing required configuration:")
    for item in missing:
        print(f"  - {item}")

# Check optional configuration
optional = config.validate_optional_config()
for category, items in optional.items():
    if items:
        print(f"Optional {category} configuration missing:")
        for item in items:
            print(f"  - {item}")
```

## 🚀 Configuration Examples

### Minimal Production Setup

```bash
# .env
ENVIRONMENT=production
TZ=UTC
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters-long
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking
AGENT_KEYS=prod-agent-001,prod-agent-002,prod-agent-003
ALLOWED_ORIGINS=https://yourdomain.com
TRUSTED_HOSTS=yourdomain.com
CSP_ALLOW_CONNECT_HTTP=false
CSP_ALLOW_CONNECT_HTTPS=true
SECURITY_LOGGING=true
CONTENT_FILTERING=true
```

### Development with AI Features

```bash
# .env
ENVIRONMENT=development
TZ=UTC
JWT_SECRET=dev-jwt-secret-key-for-development-only
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=3000
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,testing
AGENT_KEYS=test-agent-001,test-agent-002,test-agent-003
ARCP_DEBUG=true
LOG_LEVEL=DEBUG
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:8001
TRUSTED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSP_ALLOW_CONNECT_HTTP=true
CSP_ALLOW_CONNECT_HTTPS=true

# Azure OpenAI for semantic search
AZURE_API_KEY=your-azure-openai-key
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_API_VERSION=2024-02-01
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-ada-002

# Monitoring
TRACING_ENABLED=true
```

### High-Performance Setup

```bash
# .env
ENVIRONMENT=production
TZ=UTC
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters-long
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
ADMIN_USERNAME=ARCP
ADMIN_PASSWORD=ARCP
ALLOWED_AGENT_TYPES=security,monitoring,automation,networking
AGENT_KEYS=prod-agent-001,prod-agent-002,prod-agent-003

# Performance tuning
RATE_LIMIT_RPM=1000
RATE_LIMIT_BURST=100
WEBSOCKET_MAX_CONNECTIONS=500
AGENT_WS_MAX_CONNECTIONS=500
PUBLIC_WS_MAX_CONNECTIONS=500
VECTOR_SEARCH_TOP_K=20
VECTOR_SEARCH_MIN_SIMILARITY=0.3

# Redis optimization
REDIS_MAX_MEMORY=1gb
REDIS_HEALTH_CHECK_INTERVAL=10

# Network optimization
NETWORK_INTERFACE_CAPACITY_MBPS=10000
```

## 🔍 Configuration Troubleshooting

### Common Issues

#### Missing Required Configuration

```bash
# Error: Missing required configuration
# Solution: Set all required environment variables
export ENVIRONMENT=development
export JWT_SECRET=your-secret-key
export JWT_ALGORITHM=HS256
export JWT_EXPIRE_MINUTES=3600
export ADMIN_USERNAME=ARCP
export ADMIN_PASSWORD=ARCP
export ALLOWED_AGENT_TYPES=testing
```

#### Invalid JWT Secret

```bash
# Error: JWT secret too short
# Solution: Use a longer secret (minimum 32 characters)
export JWT_SECRET=your-super-secret-jwt-key-that-is-at-least-32-characters-long
```

#### Invalid Agent Types

```bash
# Error: Invalid agent type format
# Solution: Use valid format (alphanumeric, hyphens, underscores)
export ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,testing
```

#### Port Conflicts

```bash
# Error: Port already in use
# Solution: Use a different port
export ARCP_PORT=8002
```

### Configuration Validation Script

Create a configuration validation script:

```python
# validate_config.py
import os
from arcp.core.config import config

def validate_config():
    print("Validating ARCP configuration...")
    
    # Check required configuration
    missing = config.validate_required_config()
    if missing:
        print("Missing required configuration:")
        for item in missing:
            print(f"   - {item}")
        return False
    
    # Check optional configuration
    optional = config.validate_optional_config()
    warnings = 0
    for category, items in optional.items():
        if items:
            warnings += len(items)
            print(f"Optional {category} configuration missing:")
            for item in items:
                print(f"   - {item}")
    
    # Check configuration values
    errors = config.validate_config_values()
    if errors:
        print("Configuration value errors:")
        for error in errors:
            print(f"   - {error}")
        return False
    
    if warnings > 0:
        print(f"{warnings} optional configuration items missing")
    else:
        print("All configuration is valid")
    
    return True

if __name__ == "__main__":
    if validate_config():
        print("Configuration is ready!")
    else:
        print("Please fix configuration errors before starting ARCP")
```

## 📚 Next Steps

After configuring ARCP:

1. **[Quick Start Guide](quickstart.md)** - Test your configuration
2. **[Monitoring Setup](../deployment/monitoring.md)** - Set up monitoring

## 🆘 Getting Help

If you need help with configuration:

- Review the [GitHub Issues](https://github.com/0x00K1/ARCP/issues)
- Join our [Discussions](https://github.com/0x00K1/ARCP/discussions)