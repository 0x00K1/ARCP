# Installation

This guide covers all the different ways to install and run ARCP, from Docker (recommended) to manual installation.

## 🐳 Docker Installation (Recommended)

The easiest way to get started with ARCP is using Docker Compose, which includes the complete stack with monitoring.

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

### Quick Start

```bash
# Clone the repository
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Create environment configuration
cp .env.example .env
# Also copy to deployment/docker directory for Docker Compose
cp .env.example deployment/docker/.env
# Edit .env files with your configuration (see Configuration section below)

# Start the complete stack
docker-compose -f deployment/docker/docker-compose.yml up -d

# Check status
docker-compose -f deployment/docker/docker-compose.yml ps
```

### Services Included

The Docker Compose setup includes:

- **ARCP Server** (port 8001) - Main application
- **Redis** (port 6379) - Caching and session storage
- **Prometheus** (port 9090) - Metrics collection
- **Grafana** (port 3000) - Monitoring dashboards
- **Jaeger** (port 16686) - Distributed tracing
- **Redis Exporter** (port 9121) - Redis metrics

### Access Points

- **ARCP Dashboard**: http://localhost:8001/dashboard
- **API Documentation**: http://localhost:8001/docs
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Jaeger**: http://localhost:16686

## 🐍 Python Installation

For development or custom deployments, you can install ARCP directly with Python.

### Prerequisites

- Python 3.11 or higher
- pip or Poetry
- Redis server (optional but recommended)

### Using Poetry

```bash
# Clone the repository
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Create environment configuration
cp .env.example .env
# Edit .env files with your configuration (see Configuration section below)

# Run ARCP
python -m arcp
```

### Using pip

```bash
# Install from PyPI
pip install arcp-py

# Or install from source
git clone https://github.com/0x00K1/ARCP.git
cd ARCP
pip install -e .

# Create environment configuration
cp .env.example .env
# Edit .env files with your configuration (see Configuration section below)

python -m arcp
```

## 🔧 Manual Installation

For advanced users who want full control over the installation.

### System Requirements

- **OS**: Linux, macOS, or Windows
- **Python**: 3.11 or higher
- **Memory**: 2GB minimum, 4GB recommended
- **Storage**: 5GB minimum
- **Network**: Ports 8001 (ARCP), 6379 (Redis), 3000 (Grafana), 9090 (Prometheus)

### Step 1: Install Dependencies

#### Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install Python and development tools
sudo apt install python3.11 python3.11-venv python3.11-dev python3-pip

# Install Redis
sudo apt install redis-server

# Install system dependencies
sudo apt install curl wget git build-essential
```

#### CentOS/RHEL

```bash
# Install Python 3.11
sudo dnf install python3.11 python3.11-pip python3.11-devel

# Install Redis
sudo dnf install redis

# Install system dependencies
sudo dnf install curl wget git gcc
```

#### macOS

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python and Redis
brew install python@3.11 redis

# Install system dependencies
brew install curl wget git
```

### Step 2: Install ARCP

```bash
# Clone the repository
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install ARCP
pip install -e .
```

### Step 3: Configure Redis

```bash
# Start Redis service
sudo systemctl start redis-server  # Linux
brew services start redis          # macOS

# Test Redis connection
redis-cli ping
# Should return: PONG
```

### Step 4: Set Environment Variables

Create a `.env` file or set environment variables:

```bash
# Required Configuration
export ENVIRONMENT=development
export TZ=UTC
export ALLOWED_AGENT_TYPES=security,monitoring,automation,networking,test
export JWT_SECRET=your-super-secret-jwt-key-here
export JWT_ALGORITHM=HS256
export JWT_EXPIRE_MINUTES=3000
export ADMIN_USERNAME=ARCP
export ADMIN_PASSWORD=ARCP
export AGENT_KEYS=test-agent-001,test-agent-002,test-agent-003

# Optional: Redis Configuration
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=""

# Optional: Azure OpenAI for semantic search
export AZURE_API_KEY=your-azure-openai-key
export AZURE_API_BASE=https://your-resource.openai.azure.com/
export AZURE_API_VERSION=2024-02-01
export AZURE_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
```

### Step 5: Run ARCP

```bash
# Start ARCP server
python -m arcp

# Or with uvicorn directly
uvicorn arcp.__main__:app --host 0.0.0.0 --port 8001 --reload
```

## 🔍 Verification

After installation, verify that ARCP is running correctly:

### 1. Health Check

```bash
# Check if ARCP is responding
curl http://localhost:8001/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-01-XX..."
  "version": "2.0.3",
  ...
}
```

### 2. API Documentation

Visit http://localhost:8001/docs to see the interactive API documentation.

### 3. Dashboard

Visit http://localhost:8001/dashboard to access the web dashboard.

### 4. Test Agent Registration

```python
import asyncio
from arcp import ARCPClient

async def test_connection():
    client = ARCPClient("http://localhost:8001")
    
    # Test basic connectivity
    health = await client.health_check()
    print(f"Health: {health}")
    
    # Test agent discovery
    agents = await client.discover_agents()
    print(f"Found {len(agents)} agents")

asyncio.run(test_connection())
```

## 🐛 Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Check what's using port 8001
lsof -i :8001  # macOS/Linux
netstat -ano | findstr :8001  # Windows

# Kill the process or use a different port
export ARCP_PORT=8002
```

#### Redis Connection Failed

```bash
# Check if Redis is running
redis-cli ping

# Start Redis if not running
sudo systemctl start redis-server  # Linux
brew services start redis          # macOS

# Check Redis configuration
redis-cli config get bind
redis-cli config get port
```

#### Permission Denied

```bash
# Make sure you have proper permissions
sudo chown -R $USER:$USER /path/to/ARCP

# Or run with proper user permissions
sudo -u arcp python -m arcp
```

#### Missing Dependencies

```bash
# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Or with Poetry
poetry install --sync
```

### Logs and Debugging

#### Enable Debug Mode

```bash
export ARCP_DEBUG=true
export LOG_LEVEL=DEBUG
python -m arcp
```

#### Check Logs

```bash
# Docker logs
docker-compose -f deployment/docker/docker-compose.yml logs arcp

# Application logs
tail -f /app/logs/arcp.log
```

## 🔄 Updates

### Docker Update

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose -f deployment/docker/docker-compose.yml down
docker-compose -f deployment/docker/docker-compose.yml build --no-cache
docker-compose -f deployment/docker/docker-compose.yml up -d
```

### Python Update

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install --upgrade -r requirements.txt

# Restart ARCP
python -m arcp
```

## 📋 Next Steps

After successful installation:

1. **[Quick Start Guide](quickstart.md)** - Learn the basics
2. **[Configuration Guide](configuration.md)** - Customize your setup
3. **[Agent Development](../user-guide/agent-development.md)** - Build your first agent
4. **[Client Library](../user-guide/client-library.md)** - Use the Python client

## 🆘 Getting Help

If you encounter issues during installation:

- Review the [GitHub Issues](https://github.com/0x00K1/ARCP/issues)
- Join our [Discussions](https://github.com/0x00K1/ARCP/discussions)