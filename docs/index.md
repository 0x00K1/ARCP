# ARCP - Agent Registry & Control Protocol

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security](https://img.shields.io/badge/security+-brightgreen.svg)](#security)
[![PyPI version](https://badge.fury.io/py/arcp-py.svg)](https://badge.fury.io/py/arcp-py)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

**ARCP** (Agent Registry & Control Protocol) is a sophisticated agent orchestration platform that provides centralized service discovery, registration, and control for distributed agent systems. Built with FastAPI and designed for production environments, ARCP enables seamless communication between AI agents, microservices, and distributed applications.

## 🚀 Key Features

### 🔍 **Intelligent Agent Discovery**
- **Semantic Search**: Vector-based agent discovery using Azure OpenAI embeddings
- **Real-time Updates**: WebSocket-based live agent registry updates
- **Advanced Filtering**: Search by capabilities, agent types, and performance metrics

### 🛡️ **Enterprise Security**
- **JWT Authentication**: Secure token-based authentication system
- **Role-based Access Control**: Admin, agent, and public access levels
- **IP Filtering**: Configurable IP allow/deny lists
- **Rate Limiting**: Built-in protection against abuse

### 📊 **Production Monitoring**
- **Comprehensive Metrics**: Agent performance tracking and reputation scoring
- **Health Monitoring**: Built-in health checks and status reporting
- **Observability**: Prometheus metrics, Grafana dashboards, and Jaeger tracing
- **Real-time Dashboard**: Web-based management interface

### 🔧 **Developer Experience**
- **Python Client Library**: Easy-to-use async client with full feature support
- **RESTful API**: Well-documented REST API with OpenAPI/Swagger
- **Docker Ready**: Complete Docker Compose stack with monitoring
- **Extensive Examples**: Working examples for agents and clients

## 🏗️ Architecture

```mermaid
graph TB
    subgraph "ARCP Ecosystem"
        ARCP[ARCP Server]
        Redis[(Redis Cache)]
        Prometheus[Prometheus]
        Grafana[Grafana]
        Jaeger[Jaeger Tracing]
    end
    
    subgraph "Agents"
        Agent1[Security Agent]
        Agent2[Monitoring Agent]
        Agent3[Custom Agent]
    end
    
    subgraph "Clients"
        Client1[Web Dashboard]
        Client2[Python Client]
        Client3[External App]
    end
    
    ARCP --> Redis
    ARCP --> Prometheus
    Prometheus --> Grafana
    ARCP --> Jaeger
    
    Agent1 --> ARCP
    Agent2 --> ARCP
    Agent3 --> ARCP
    
    Client1 --> ARCP
    Client2 --> ARCP
    Client3 --> ARCP
```

## 🚀 Quick Start

### 1. Start ARCP Server with Docker

```bash
# Clone the repository
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Create environment file
cp .env.example .env
# Also copy to deployment/docker directory for Docker Compose
cp .env.example deployment/docker/.env
# Edit .env files with your configuration (see Configuration section below)

# Start the complete stack
docker-compose -f deployment/docker/docker-compose.yml up -d
```

### 2. Access the Services

- **ARCP Server**: http://localhost:8001
- **Web Dashboard**: http://localhost:8001/dashboard (built-in)
- **API Documentation**: http://localhost:8001/docs
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Jaeger**: http://localhost:16686

### 3. Create Your First Agent

```python
import asyncio
from arcp import ARCPClient

async def main():
    # Connect to ARCP server
    client = ARCPClient("http://localhost:8001")
    
    # Register an agent
    agent = await client.register_agent(
        agent_id="my-first-agent",
        name="My First Agent",
        agent_type="testing",
        endpoint="https://my-agent.example.com",
        context_brief="A simple test agent for learning ARCP",
        capabilities=["testing", "demo"],
        owner="tester",
        public_key="my-super-secure-public-key-that-is-at-least-32-chars-long",
        metadata={
            "author": "ARCP User",
            "description": "A simple test agent for learning ARCP",
            "tags": ["demo", "testing", "learning"]
        },
        version="1.0.0",
        communication_mode="remote",
        agent_key="test-agent-001",
    )
    
    print(f"Agent registered: {agent.name}")
    
    # Search for agents
    results = await client.search_agents("find test agents")
    for result in results:
        print(f"Found: {result.name} (similarity: {result.similarity})")

asyncio.run(main())
```

## 📚 Documentation Structure

### Getting Started
- **[Installation](getting-started/installation.md)** - Complete installation guide
- **[Quick Start](getting-started/quickstart.md)** - Get up and running in minutes
- **[Configuration](getting-started/configuration.md)** - Environment variables and settings

### User Guide
- **[Agent Development](user-guide/agent-development.md)** - Building agents that integrate with ARCP
- **[Client Library](user-guide/client-library.md)** - Using the Python client library

### API Reference
- **[REST API](api-reference/rest-api.md)** - Complete API documentation
- **[WebSocket API](api-reference/websocket-api.md)** - Real-time WebSocket API

### Deployment
- **[Monitoring](deployment/monitoring.md)** - Observability and monitoring

### Security
- **[Security Overview](security/security-overview.md)** - Security architecture and practices

## 🎯 Use Cases

### **AI Agent Orchestration**
- Coordinate multiple AI agents for complex tasks
- Load balancing and failover for agent services
- Performance monitoring and optimization

### **Microservices Registry**
- Service discovery for distributed applications
- Health monitoring and automatic failover
- Centralized configuration management

### **IoT Device Management**
- Register and monitor IoT devices
- Real-time status updates and alerts
- Device capability discovery

### **API Gateway**
- Route requests to appropriate services
- Authentication and authorization
- Rate limiting and monitoring

## 🔧 Technology Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: Redis for caching and session storage
- **AI**: Azure OpenAI for semantic search
- **Monitoring**: Prometheus + Grafana
- **Tracing**: Jaeger for distributed tracing
- **Containerization**: Docker + Docker Compose
- **Documentation**: MkDocs with Material theme

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Install dependencies
poetry install

# Run tests
pytest

# Start development server
python -m arcp
```

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE.md) file for details.

## 🆘 Support

- **Documentation**: [https://arcp.0x001.tech/docs](https://arcp.0x001.tech/docs)
- **Issues**: [GitHub Issues](https://github.com/0x00K1/ARCP/issues)
- **Discussions**: [GitHub Discussions](https://github.com/0x00K1/ARCP/discussions)

---

**Ready to get started?** Check out our [Quick Start Guide](getting-started/quickstart.md) to have ARCP running in minutes!