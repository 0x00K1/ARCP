<div align="center">

# ARCP - Agent Registry & Control Protocol

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security](https://img.shields.io/badge/security+-brightgreen.svg)](#security)
[![PyPI version](https://badge.fury.io/py/arcp-py.svg)](https://badge.fury.io/py/arcp-py)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

**A sophisticated agent orchestration protocol that provides centralized service discovery, registration, communication, and control for distributed agent systems.**

</div>

## ✨ Features

<div align="center">

| 🔧 **Centralized Management** | 🔍 **Service Discovery** | 🤝 **Agent Communication** |
|:---:|:---:|:---:|
| *Register & control agents* | *Automatic endpoint resolution* | *Secure agent collaboration* |

| 🛡️ **Security** | 📊 **Dashboard** | 🐳 **Production** |
|:---:|:---:|:---:|
| *Built-in authentication* | *Metrics & Alerts & Logs* | *Docker & monitoring stack* |

| ⚙️ **Extensible** | 👨‍💻 **Developers** | 📚 **Docs** |
|:---:|:---:|:---:|
| *Custom use cases* | *Python client, API* | *Guides & references* |

</div>


## 🚀 Quick Start

### Running the Server

#### 🐍 pip Installation
```bash
# Install ARCP
pip install arcp-py

# Set up configuration
curl -o .env https://raw.githubusercontent.com/0x00K1/ARCP/main/.env.example
# Edit .env file with your configuration

# Start the server
python -m arcp
```

#### 🐳 Docker Deployment (Recommended)
For a complete production setup with monitoring, use Docker:

```bash
# Clone ARCP
git clone https://github.com/0x00K1/ARCP.git
cd ARCP

# Set up configuration
cp .env.example .env
cp .env.example deployment/docker/.env
# Edit .env file with your configuration

# Start full stack (ARCP + Redis + Monitoring)
cd deployment/docker
docker-compose up -d --build
```

> 💡 **Need help?** Check out our detailed [Installation Guide](https://arcp.0x001.tech/docs/getting-started/installation).


### 🛠️ Agent Development

Build agents that integrate seamlessly with ARCP:

```python
from arcp import ARCPClient, AgentRequirements

async def register_with_arcp():
    """Register this agent with ARCP"""
    # Create ARCP client
    arcp_client = ARCPClient("http://localhost:8001")
    
    try:
        # Register the agent
        agent = await arcp_client.register_agent(
            agent_id="my-agent-001",
            name="My Demo Agent",
            agent_type="automation",
            endpoint="http://localhost:8080",
            capabilities=["processing", "automation"],
            context_brief="A demo agent showcasing ARCP integration",
            version="1.0.0",
            owner="Developer",
            public_key="your-public-key-min-32-chars-long",
            communication_mode="remote",
            metadata={
                "framework": "fastapi",
                "language": "python",
                "created_at": "2025-09-20T03:00:00.000000",
            },
            features=["http-api", "json-responses"],
            max_tokens=1000,
            language_support=["en"],
            rate_limit=100,
            requirements=AgentRequirements(
                system_requirements=["Python 3.11+", "FastAPI"],
                permissions=["http-server"],
                dependencies=["fastapi", "arcp"],
                minimum_memory_mb=256,
                requires_internet=True,
                network_ports=["8080"]
            ),
            policy_tags=["utility", "demo"],
            agent_key="test-agent-001"
        )
        
        print(f"✅ Agent registered: {agent.name}")
        print(f"📊 Status: {agent.status}")
        
    finally:
        await arcp_client.close()

# Run the registration
import asyncio
asyncio.run(register_with_arcp())
```

> 🎯 **Want to dive deeper?** Explore our comprehensive [Agent Development Guide](https://arcp.0x001.tech/docs/user-guide/agent-development).


## 📚 Documentation

<div align="center">

### Everything you need to get started, develop agents, and operate ARCP

**📖 [Complete Documentation](https://arcp.0x001.tech/docs)**

</div>


## 📄 License

<div>

This project is licensed under the **Apache License 2.0** - see the [LICENSE](https://arcp.0x001.tech/docs/LICENSE) file for details.

</div>