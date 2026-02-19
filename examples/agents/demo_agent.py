#!/usr/bin/env python3
"""
ARCP Demo Agent

This example demonstrates how to build an agent that properly integrates
with ARCP:
1. Uses the official ARCP client library
2. Handles the complete registration lifecycle
3. Implements proper heartbeat and metrics reporting
4. Provides a working HTTP API for the agent
5. Demonstrates graceful shutdown and cleanup
6. Supports DPoP (RFC 9449) for secure token binding
7. Supports mTLS (Mutual TLS) client certificate authentication
8. Supports dual authentication (DPoP + mTLS combined)

Usage Examples:
    # Basic mode (no authentication)
    python demo_agent.py --agent-key YOUR_KEY --deployment-mode internal

    # With DPoP only
    python demo_agent.py --agent-key YOUR_KEY --deployment-mode internal --dpop

    # With mTLS only
    python demo_agent.py --agent-key YOUR_KEY --deployment-mode internal --mtls

    # With dual authentication (DPoP + mTLS)
    python demo_agent.py --agent-key YOUR_KEY --deployment-mode internal --dpop --mtls

Arguments:
    --deployment-mode: REQUIRED - Specify 'docker' for Docker deployment (uses host.docker.internal)
                      or 'internal' for internal network deployment (uses host IP)
    --dpop/--no-dpop: Enable/disable DPoP proofs (default: disabled)
    --mtls/--no-mtls: Enable/disable mTLS client certificate authentication (default: disabled)

Requirements:
    - ARCP server running (default: https://localhost:8001)
    - Valid agent registration key
    - Available port for agent API (default: 8080)
    - cryptography library for DPoP and mTLS support (optional)
    - PyJWT for DPoP proof JWT creation (optional)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add the project root to sys.path to use local ARCP source
# This ensures we use the latest local package during development/testing
_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from arcp import AgentRequirements, ARCPClient, ARCPError  # noqa: E402

# Optional: Import DPoP support
try:
    from dpop_client import create_dpop_client

    HAS_DPOP = True
except ImportError:
    HAS_DPOP = False

# Optional: Import mTLS support
try:
    from mtls_client import DualAuthARCPClient, MTLSARCPClient
    from mtls_helper import MTLSGenerator

    HAS_MTLS = True
except ImportError:
    HAS_MTLS = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("demo-agent")


def generate_demo_sbom(agent_id: str, version: str) -> str:
    """
    Generate a minimal CycloneDX SBOM for the demo agent.

    In production, this would be generated during build time using
    tools like syft, cyclonedx-python, or sbom-tool.
    """
    import json
    import uuid

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "tools": [
                {
                    "vendor": "ARCP",
                    "name": "demo-agent-sbom-generator",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "bom-ref": agent_id,
                "name": "ARCP Demo Agent",
                "version": version,
                "description": "A demonstration agent showing proper ARCP integration",
            },
        },
        "components": [
            {
                "type": "library",
                "bom-ref": "pkg:pypi/fastapi@0.109.0",
                "name": "fastapi",
                "version": "0.109.0",
                "purl": "pkg:pypi/fastapi@0.109.0",
            },
            {
                "type": "library",
                "bom-ref": "pkg:pypi/uvicorn@0.27.0",
                "name": "uvicorn",
                "version": "0.27.0",
                "purl": "pkg:pypi/uvicorn@0.27.0",
            },
            {
                "type": "library",
                "bom-ref": "pkg:pypi/pydantic@2.6.0",
                "name": "pydantic",
                "version": "2.6.0",
                "purl": "pkg:pypi/pydantic@2.6.0",
            },
            {
                "type": "library",
                "bom-ref": "pkg:pypi/httpx@0.26.0",
                "name": "httpx",
                "version": "0.26.0",
                "purl": "pkg:pypi/httpx@0.26.0",
            },
        ],
        "dependencies": [
            {
                "ref": agent_id,
                "dependsOn": [
                    "pkg:pypi/fastapi@0.109.0",
                    "pkg:pypi/uvicorn@0.27.0",
                    "pkg:pypi/pydantic@2.6.0",
                    "pkg:pypi/httpx@0.26.0",
                ],
            }
        ],
    }
    return json.dumps(sbom, indent=2)


def generate_demo_attestation(
    agent_id: str, challenge_id: str = None, nonce: str = None
) -> dict:
    """
    Generate software attestation evidence for the demo agent.

    In production, this would include:
    - TPM-based attestation (PCR quotes)
    - Code signing verification
    - Secure boot measurements
    - Runtime integrity checks

    For the demo, we generate a software-based attestation.

    Args:
        agent_id: The agent ID for measurements
        challenge_id: Challenge ID from server (required for proper attestation)
        nonce: Nonce from the challenge (required for proper attestation)
    """
    import hashlib
    import secrets

    if nonce is None:
        nonce = secrets.token_hex(16)

    # Simulate code measurements (in production, these would be real hashes)
    code_hash = hashlib.sha256(f"demo-agent-code-{agent_id}".encode()).hexdigest()
    config_hash = hashlib.sha256(f"demo-agent-config-{agent_id}".encode()).hexdigest()

    attestation = {
        "type": "software",
        "attestation_type": "software",
        "challenge_id": challenge_id or "",
        "nonce": nonce,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # code_measurements must be Dict[str, str] (path -> hash)
        "code_measurements": {
            "demo_agent.py": code_hash,
            "config.json": config_hash,
        },
        "executable_hash": code_hash,
        "environment_hash": config_hash,
        "process_info": {
            "pid": os.getpid(),
            "executable_path": sys.executable,
            "executable_hash": code_hash,
            "command_line": " ".join(sys.argv),
            "working_directory": os.getcwd(),
            "start_time": datetime.now(timezone.utc).isoformat(),
        },
        "platform": {
            "os": "linux" if sys.platform.startswith("linux") else sys.platform,
            "python_version": sys.version.split()[0],
            "agent_version": "1.0.0",
        },
    }
    return attestation


class AgentConfig:
    """Configuration for the demo agent"""

    def __init__(self):
        # Agent identification
        self.agent_id = "demo-agent-001"
        self.agent_type = "testing"
        self.name = "ARCP Demo Agent"
        self.version = "1.0.0"
        self.owner = "ARCP Examples"

        # Network configuration
        self.host = "localhost"
        self.port = 8080
        # Endpoint will be set based on deployment mode (docker vs internal)
        self.endpoint = None
        self.deployment_mode = "internal"  # "docker" or "internal"

        # ARCP server configuration
        self.arcp_url = "http://localhost:8001"
        self.agent_key = None

        # DPoP configuration (secure token binding)
        self.dpop_enabled = False  # Enabled via --dpop flag
        self.dpop_jkt = None  # JWK Thumbprint (set during registration)

        # mTLS configuration (client certificate authentication)
        self.mtls_enabled = False  # Enabled via --mtls flag
        self.mtls_generator = None  # MTLSGenerator instance
        self.mtls_spki_hash = None  # SPKI hash for certificate binding

        # Agent capabilities and features
        self.capabilities = [
            "echo",
            "compute",
            "status",
            "demo",
            "testing",
            "examples",
        ]
        self.features = [
            "http-api",
            "json-responses",
            "health-checks",
            "metrics",
            "async-processing",
            "demo-mode",
        ]
        self.context_brief = (
            "A demonstration agent showing proper ARCP integration "
            "patterns. Provides echo services, basic computations, "
            "and status reporting."
        )

        # AI Context - detailed information for AI systems
        self.ai_context = """
ARCP Demo Agent - AI Context Guide

## Available Endpoints

### 1. Echo Service
POST /echo
Request: {"message": "string (required)", "repeat": "integer (optional, default: 1)"}
Response: {"echo": "string", "repeated": "integer", "timestamp": "ISO-8601"}
Use Case: Testing connectivity, message relay. Latency: < 100ms

### 2. Compute Operations
POST /compute
Request: {"operation": "add|multiply|fibonacci", "a": "number", "b": "number", "n": "integer"}
Response: {"operation": "string", "result": "number", "inputs": "object"}
Operations: add (a+b), multiply (a*b), fibonacci (nth number, n<=50)
Use Case: Mathematical computations. Latency: < 500ms

### 3. Status Check
GET /status
Response: {"status": "healthy|degraded|unhealthy", "uptime_seconds": "number", "version": "string", "capabilities": ["array"], "timestamp": "ISO-8601", "agent_id": "string"}
Use Case: Health monitoring. Latency: < 50ms

### 4. Health Check
GET /health
Response: {"status": "ok", "checks": {"api": "boolean", "arcp_connection": "boolean"}}
Use Case: Simple health checks. Latency: < 50ms

### 5. OpenAPI Documentation
GET /docs - Swagger UI
GET /openapi.json - OpenAPI 3.0 spec

## Orchestration Patterns

### Pattern 1: Echo Testing
1. POST /echo with {"message": "test"}
2. Verify response latency < 200ms
Use: Integration testing, connectivity verification

### Pattern 2: Sequential Computations
Chain operations by using previous result in next computation.
Example: (5 + 3) * 2
  Step 1: POST {"operation": "add", "a": 5, "b": 3} -> 8
  Step 2: POST {"operation": "multiply", "a": 8, "b": 2} -> 16

### Pattern 3: Health Monitoring
1. GET /health every 30-60 seconds
2. Alert if unhealthy for > 2 minutes
3. Use /status for detailed diagnostics

## Integration Guidelines

### Authentication
No authentication required (demo agent). Production agents use ARCP tokens.

### Error Handling
Status Codes: 200 (success), 400 (bad request), 422 (validation error), 500 (server error)
Error Format: {"detail": "string"}
Retry: Don't retry 400/422. Retry 500/503 with exponential backoff (max 3 retries)

### Performance
- Concurrent requests: Up to 50
- Request timeout: 30 seconds
- Throughput: ~100 req/sec
- Memory: ~256 MB
- No rate limiting (production: 100 req/min recommended)

### Data Constraints
- Message length (echo): 10,000 chars
- Numbers (compute): -1e10 to 1e10
- Fibonacci n: 0 to 50
- All responses are JSON with ISO-8601 UTC timestamps

## Best Practices

1. Poll /health before sending requests
2. Set 30s timeout for all requests
3. Don't request fibonacci(n) where n > 50
4. Use /echo to verify agent before real work
5. Don't exceed 50 simultaneous requests
6. Log request details for debugging

## Common Workflows

### Validate Agent
1. GET /health → check availability
2. POST /echo → verify latency < 200ms
3. Ready for work

### Mathematical Pipeline
Chain /compute operations, validate each result, handle errors at each step

### Monitoring
GET /health every 60s → GET /status if failed → log issues → alert on persistent failures

## Debugging
- Check /status for agent info and uptime
- Logs to stdout with "ARCP" prefix for registry operations
- Common issues: Connection refused (agent down), Timeout (overloaded), Validation error (check schema)
"""

        # Runtime state
        self.arcp_client = None
        self.access_token = None
        self.heartbeat_task = None
        self.metrics_task = None
        self.start_time = time.time()

    def set_endpoint_from_deployment_mode(self):
        """Set the endpoint based on deployment mode (docker vs internal)"""
        if self.deployment_mode == "docker":
            # Use host.docker.internal for Docker container access
            self.endpoint = f"http://host.docker.internal:{self.port}"
        elif self.deployment_mode == "internal":
            # Use localhost/host IP for internal network access
            self.endpoint = f"http://{self.host}:{self.port}"
        else:
            raise ValueError(
                f"Invalid deployment mode: {self.deployment_mode}. Must be 'docker' or 'internal'"
            )


# Global configuration instance
config = AgentConfig()

# FastAPI application for the agent's HTTP API
app = FastAPI(
    title="ARCP Demo Agent",
    description=("A demonstration agent showing ARCP integration patterns"),
    version=config.version,
)

# Enable CORS for web dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Pydantic models for API requests
class EchoRequest(BaseModel):
    message: str
    repeat: int = 1


class ComputeRequest(BaseModel):
    operation: str  # "add", "multiply", "fibonacci"
    a: float = 0
    b: float = 0
    n: int = 0


class TaskRequest(BaseModel):
    task_id: str
    operation: str
    parameters: Dict[str, Any] = {}


class ConnectionRequest(BaseModel):
    user_id: str
    user_endpoint: str
    display_name: str = "Unknown User"
    additional_info: Dict[str, Any] = {}


# Agent HTTP API endpoints
@app.get("/")
async def agent_root():
    """Agent information endpoint"""
    return {
        "service": config.name,
        "version": config.version,
        "status": "healthy",
        "agent_id": config.agent_id,
        "capabilities": config.capabilities,
        "features": config.features,
        "api_docs": f"{config.endpoint}/docs",
        "health": f"{config.endpoint}/health",
        "metrics": f"{config.endpoint}/metrics",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "agent_id": config.agent_id,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health endpoint with capabilities"""
    # Check ARCP connection status
    arcp_connected = (
        config.arcp_client is not None
        and config.heartbeat_task is not None
        and not config.heartbeat_task.done()
    )

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": config.version,
        "agent_id": config.agent_id,
        "components": {
            "arcp": "healthy" if arcp_connected else "disconnected",
            "http_server": "healthy",
            "background_tasks": "healthy",
        },
        "performance": {
            "uptime": int(time.time() - config.start_time),
            "memory_usage": "25%",
            "cpu_usage": "5%",
        },
        "external_services": {
            "arcp_server": "connected" if arcp_connected else "disconnected",
        },
    }


@app.get("/metrics")
async def metrics():
    """Metrics endpoint - Prometheus format"""
    uptime = time.time() - config.start_time

    # Return Prometheus text format
    prometheus_metrics = f"""# HELP agent_uptime_seconds Agent uptime in seconds
# TYPE agent_uptime_seconds gauge
agent_uptime_seconds{{agent_id="{config.agent_id}"}} {uptime:.2f}

# HELP agent_requests_total Total number of requests
# TYPE agent_requests_total counter
agent_requests_total{{agent_id="{config.agent_id}"}} {int(uptime / 10)}

# HELP agent_requests_success_total Successful requests
# TYPE agent_requests_success_total counter
agent_requests_success_total{{agent_id="{config.agent_id}"}} {int(uptime / 10 * 0.95)}

# HELP agent_requests_failed_total Failed requests
# TYPE agent_requests_failed_total counter
agent_requests_failed_total{{agent_id="{config.agent_id}"}} {int(uptime / 10 * 0.05)}

# HELP agent_response_time_milliseconds Average response time
# TYPE agent_response_time_milliseconds gauge
agent_response_time_milliseconds{{agent_id="{config.agent_id}"}} 15.5
"""

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content=prometheus_metrics, media_type="text/plain")


@app.post("/connection/notify")
async def connection_notify(request: dict):
    """Connection notification endpoint - Agent-to-Agent"""
    logger.info(f"Connection notify received: {request}")
    agent_id = request.get("agent_id", "unknown")

    return {
        "status": "notified",
        "message": f"Notification received from agent {agent_id}",
        "agent_endpoint": config.endpoint,
        "timestamp": datetime.now().isoformat(),
        "next_step": "Connection established, ready for inter-agent communication",
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for service discovery"""
    return {
        "status": "pong",
        "agent_id": config.agent_id,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status")
async def detailed_status():
    """Detailed status information"""
    return {
        "agent": {
            "id": config.agent_id,
            "name": config.name,
            "type": config.agent_type,
            "version": config.version,
            "status": "running",
        },
        "runtime": {
            "uptime": time.time() - config.start_time,
            "start_time": (datetime.fromtimestamp(config.start_time).isoformat()),
            "current_time": datetime.now().isoformat(),
        },
        "arcp": {
            "server_url": config.arcp_url,
            "connected": (
                config.arcp_client is not None
                and config.heartbeat_task is not None
                and not config.heartbeat_task.done()
            ),
            "heartbeat_active": (
                config.heartbeat_task is not None and not config.heartbeat_task.done()
            ),
            "metrics_active": (
                config.metrics_task is not None and not config.metrics_task.done()
            ),
        },
        "capabilities": config.capabilities,
        "features": config.features,
    }


@app.post("/echo")
async def echo_service(request: EchoRequest):
    """Echo service - repeats the input message"""
    start_time = time.time()

    try:
        # Simple echo with optional repetition
        if request.repeat <= 0:
            raise HTTPException(status_code=400, detail="Repeat count must be positive")
        if request.repeat > 10:
            raise HTTPException(status_code=400, detail="Maximum repeat count is 10")

        echoed_messages = [
            f"Echo {i+1}: {request.message}" for i in range(request.repeat)
        ]

        response_time = time.time() - start_time

        # Report metrics to ARCP if connected
        if config.arcp_client and config.access_token:
            try:
                await config.arcp_client.update_metrics(
                    config.agent_id,
                    {
                        "operation": "echo",
                        "response_time": response_time,
                        "success": True,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to report metrics: {e}")

        return {
            "operation": "echo",
            "input": request.message,
            "repeat_count": request.repeat,
            "outputs": echoed_messages,
            "response_time": response_time,
            "status": "success",
            "agent_id": config.agent_id,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Echo operation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Echo operation failed: {str(e)}")


@app.post("/compute")
async def compute_service(request: ComputeRequest):
    """Computation service - performs basic mathematical operations"""
    start_time = time.time()

    try:
        result = None

        if request.operation == "add":
            result = request.a + request.b
        elif request.operation == "multiply":
            result = request.a * request.b
        elif request.operation == "fibonacci":
            if request.n < 0 or request.n > 40:
                raise HTTPException(
                    status_code=400,
                    detail="Fibonacci n must be between 0 and 40",
                )
            result = fibonacci(request.n)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown operation: {request.operation}",
            )

        response_time = time.time() - start_time

        # Report metrics to ARCP
        if config.arcp_client and config.access_token:
            try:
                await config.arcp_client.update_metrics(
                    config.agent_id,
                    {
                        "operation": request.operation,
                        "response_time": response_time,
                        "success": True,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to report metrics: {e}")

        return {
            "operation": request.operation,
            "parameters": request.dict(),
            "result": result,
            "response_time": response_time,
            "status": "success",
            "agent_id": config.agent_id,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compute operation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Compute operation failed: {str(e)}"
        )


@app.post("/task")
async def execute_task(request: TaskRequest):
    """Generic task execution endpoint"""
    start_time = time.time()

    try:
        # Route to appropriate handler based on operation
        if request.operation == "echo":
            message = request.parameters.get("message", "Hello from demo agent!")
            result = f"Task {request.task_id}: Echo - {message}"
        elif request.operation == "status":
            result = {
                "agent_id": config.agent_id,
                "status": "running",
                "uptime": time.time() - config.start_time,
                "capabilities": config.capabilities,
            }
        elif request.operation == "info":
            result = {
                "name": config.name,
                "version": config.version,
                "type": config.agent_type,
                "description": config.context_brief,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown task operation: {request.operation}",
            )

        response_time = time.time() - start_time

        return {
            "task_id": request.task_id,
            "operation": request.operation,
            "result": result,
            "response_time": response_time,
            "status": "completed",
            "agent_id": config.agent_id,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Task execution failed: {str(e)}")


@app.post("/connection/request")
async def handle_connection_request(request: dict):
    """Handle connection requests from clients via ARCP"""
    start_time = time.time()

    try:
        user_id = request.get("user_id", "unknown")
        user_endpoint = request.get("user_endpoint", "")
        user_display_name = request.get("user_display_name", "Unknown User")

        logger.info(f"   Connection request from user: {user_id} ({user_display_name})")
        logger.info(f"   User endpoint: {user_endpoint}")

        response_time = time.time() - start_time

        # Report connection metrics to ARCP
        if config.arcp_client and config.access_token:
            try:
                await config.arcp_client.update_metrics(
                    config.agent_id,
                    {
                        "operation": "connection_request",
                        "user_id": user_id,
                        "response_time": response_time,
                        "success": True,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to report connection metrics: {e}")

        # Return schema matching validation requirements
        return {
            "status": "connection_request_received",
            "message": f"Connection request received from {user_display_name}",
            "requirements": {
                "api_key": "Please provide your API key",
                "supported_operations": ["echo", "compute", "task", "status"],
            },
            "agent_id": config.agent_id,
        }

    except Exception as e:
        logger.error(f"Connection request failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Connection request failed: {str(e)}"
        )


@app.post("/connection/configure")
async def connection_configure(request: dict):
    """Configure connection with client registration data"""
    user_id = request.get("user_id", "unknown")

    logger.info(f"   Configuring connection for user: {user_id}")

    # Generate registration ID
    registration_id = f"reg-{int(time.time())}-{user_id[:8]}"

    return {
        "status": "connected",
        "message": f"Connection configured successfully for user {user_id}",
        "user_id": user_id,
        "registration_id": registration_id,
        "agent_token": f"agent-token-{registration_id}",
        "capabilities_enabled": config.capabilities,
        "monitoring_started": True,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/connection/status/{user_id}")
async def connection_status(user_id: str):
    """Check connection status for a client"""
    logger.info(f"   Checking connection status for user: {user_id}")

    # For demo, return connected status
    return {
        "status": "connected",
        "user_id": user_id,
        "registration_date": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat(),
        "message": "Connection active and healthy",
    }


@app.post("/connection/disconnect")
async def connection_disconnect(request: dict):
    """Disconnect client and cleanup resources"""
    user_id = request.get("user_id", "unknown")
    reason = request.get("reason", "User requested disconnect")

    logger.info(f"   Disconnecting user: {user_id}, reason: {reason}")

    return {
        "status": "disconnected",
        "user_id": user_id,
        "message": f"User {user_id} disconnected successfully",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/agents/{agent_id}/heartbeat")
async def receive_heartbeat(agent_id: str, request: dict = None):
    """Receive heartbeat signal from ARCP"""
    logger.debug(f"   Heartbeat received for agent: {agent_id}")

    return {
        "agent_id": config.agent_id,
        "status": "alive",
        "timestamp": datetime.now().isoformat(),
        "version": config.version,
        "uptime": f"{int(time.time() - config.start_time)}s",
        "capabilities": config.capabilities,
        "features": config.features,
    }


@app.post("/agents/{agent_id}/metrics")
async def receive_metrics(agent_id: str, request: dict):
    """Receive metrics data from ARCP"""
    logger.debug(f"   Metrics received for agent: {agent_id}")

    return {
        "status": "received",
        "agent_id": config.agent_id,
        "timestamp": datetime.now().isoformat(),
        "processed": True,
    }


@app.post("/agents/report-metrics/{agent_id}")
async def report_metrics_to_arcp(agent_id: str, request: dict):
    """Report performance metrics to ARCP"""
    logger.debug(f"   Reporting metrics for agent: {agent_id}")

    return {
        "status": "reported",
        "agent_id": config.agent_id,
        "timestamp": datetime.now().isoformat(),
        "processed": True,
    }


@app.get("/search/agents")
async def search_agents(
    query: str = "test", search_type: str = "basic", max_results: int = 10
):
    """Search for other agents via ARCP"""
    logger.info(f"   Agent search query: {query}")

    # Return mock search results
    return {
        "agents": [
            {
                "agent_id": "demo-agent-002",
                "name": "Demo Agent 2",
                "type": "testing",
                "capabilities": ["echo", "test"],
            }
        ],
        "total_results": 1,
        "query": query,
        "search_type": search_type,
        "processing_time": 12.5,
    }


def fibonacci(n: int) -> int:
    """Calculate Fibonacci number (simple recursive implementation)"""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


async def register_with_arcp():
    """Register this agent with ARCP using the official client library"""
    if not config.agent_key:
        logger.error("Agent key is required for ARCP registration")
        return False

    try:
        # Create ARCP client instance (with DPoP and/or mTLS if enabled)
        if config.dpop_enabled and config.mtls_enabled and HAS_DPOP and HAS_MTLS:
            # Dual authentication: Both DPoP and mTLS
            # DualAuthARCPClient auto-generates certificates and DPoP keys
            config.arcp_client = DualAuthARCPClient(
                config.arcp_url,
                dpop_enabled=True,
                mtls_enabled=True,
                dpop_algorithm="EdDSA",
                mtls_algorithm="RSA",
                verify_ssl=False,  # For development with self-signed certs
            )
            config.dpop_jkt = config.arcp_client.get_dpop_jkt()
            config.mtls_spki_hash = config.arcp_client.get_mtls_spki()
            logger.info(
                f"Dual Auth enabled - DPoP JKT: {config.dpop_jkt[:16]}..., mTLS SPKI: {config.mtls_spki_hash[:16]}..."
            )
        elif config.mtls_enabled and HAS_MTLS:
            # mTLS only
            config.mtls_generator = MTLSGenerator(
                algorithm="RSA",
                subject_cn="ARCP Demo Agent",
                san_dns=["localhost"],
                san_ips=["127.0.0.1", "::1"],
            )
            config.arcp_client = MTLSARCPClient(
                config.arcp_url,
                mtls_generator=config.mtls_generator,
                verify_ssl=False,  # For development with self-signed certs
            )
            config.mtls_spki_hash = config.mtls_generator.get_spki_hash()
            logger.info(f"mTLS enabled - SPKI: {config.mtls_spki_hash[:16]}...")
        elif config.dpop_enabled and HAS_DPOP:
            # DPoP only
            config.arcp_client = create_dpop_client(config.arcp_url, dpop_enabled=True)
            config.dpop_jkt = config.arcp_client.get_dpop_jkt()
            logger.info(f"DPoP enabled - JKT: {config.dpop_jkt[:16]}...")
        else:
            # No authentication (basic mode)
            config.arcp_client = ARCPClient(config.arcp_url)
            if config.dpop_enabled:
                logger.warning(
                    "DPoP requested but dependencies not available (install cryptography, PyJWT)"
                )
            if config.mtls_enabled:
                logger.warning(
                    "mTLS requested but dependencies not available (install cryptography)"
                )
        await config.arcp_client.__aenter__()

        logger.info("=== Registering with ARCP ===")
        logger.info(f"Agent ID: {config.agent_id}")
        logger.info(f"Agent Type: {config.agent_type}")
        logger.info(f"Endpoint: {config.endpoint}")
        logger.info(f"ARCP Server: {config.arcp_url}")
        logger.info(
            f"DPoP: {'enabled' if (config.dpop_enabled and HAS_DPOP) else 'disabled'}"
        )
        logger.info(
            f"mTLS: {'enabled' if (config.mtls_enabled and HAS_MTLS) else 'disabled'}"
        )

        # Generate security data
        logger.info("=== Generating Security Data ===")

        # Generate SBOM
        sbom_content = generate_demo_sbom(config.agent_id, config.version)
        logger.info(f"   SBOM generated (CycloneDX 1.5, {len(sbom_content)} bytes)")

        # Request attestation challenge and generate evidence
        attestation_data = None
        try:
            challenge = await config.arcp_client.request_attestation_challenge(
                agent_id=config.agent_id, attestation_types=["software"]
            )
            if challenge:
                logger.info(
                    f"   Attestation challenge received: {challenge.get('challenge_id', 'N/A')[:16]}..."
                )
                attestation_data = generate_demo_attestation(
                    config.agent_id,
                    challenge_id=challenge.get("challenge_id"),
                    nonce=challenge.get("nonce"),
                )
                logger.info("   Attestation evidence generated (type: software)")
            else:
                logger.info("   Attestation not enabled on server, skipping")
        except Exception as e:
            logger.warning(f"   Could not request attestation challenge: {e}")
            logger.info("   Skipping attestation (no valid challenge)")
            # Don't generate attestation without a valid challenge

        # Register the agent with comprehensive configuration
        agent_info = await config.arcp_client.register_agent(
            agent_id=config.agent_id,
            name=config.name,
            agent_type=config.agent_type,
            endpoint=config.endpoint,
            capabilities=config.capabilities,
            context_brief=config.context_brief,
            version=config.version,
            owner=config.owner,
            public_key="demo-public-key-for-testing-purposes-only-at-least-32-chars",
            communication_mode="remote",
            metadata={
                "version": config.version,
                "author": config.owner,
                "description": config.context_brief,
                "tags": ["demo", "testing", "example"],
                "deployment_mode": config.deployment_mode,
                "demo_agent": True,
                "language": "python",
                "framework": "fastapi",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "example_usage": (
                    "curl -X POST {}/echo -H 'Content-Type: application/json' "
                    '-d \'{{"message": "hello"}}\''
                ).format(config.endpoint),
            },
            features=config.features,
            max_tokens=1000,
            language_support=["en"],
            rate_limit=100,
            requirements=AgentRequirements(
                system_requirements=["Python 3.11+", "FastAPI", "Uvicorn"],
                permissions=["http-server"],
                dependencies=["fastapi", "pydantic", "uvicorn", "arcp"],
                minimum_memory_mb=256,
                requires_internet=True,
                network_ports=["8080"],
            ),
            policy_tags=["demo", "example", "testing"],
            # AI Context - enables AI systems to understand and use this agent
            ai_context=config.ai_context,
            agent_key=config.agent_key,
            # Generate SBOM for vulnerability verification
            sbom=sbom_content,
            # Container image for scanning
            # Using python:3.11-slim as demo since this is a Python agent
            container_image="python:3.11-slim",
            # Demo agent runs on host, not in a container
            # Set to False since this Python process is not containerized
            is_containerized=False,
            # Attestation evidence (if challenge was obtained)
            attestation=attestation_data,
        )

        logger.info("   Successfully registered with ARCP!")
        logger.info(f"   Status: {agent_info.status}")
        logger.info(f"   Registered at: {agent_info.registered_at}")

        # Start background tasks for heartbeat and metrics
        config.heartbeat_task = await config.arcp_client.start_heartbeat_task(
            config.agent_id, interval=30.0
        )
        logger.info("   Heartbeat task started (30s interval)")

        # Start metrics reporting task
        config.metrics_task = asyncio.create_task(metrics_reporting_loop())
        logger.info("   Metrics reporting task started")

        return True

    except ARCPError as e:
        logger.error(f"   ARCP registration failed: {e}")
        return False
    except Exception as e:
        logger.error(f"   Unexpected registration error: {e}")
        return False


async def metrics_reporting_loop():
    """Background task to periodically report metrics to ARCP"""
    while True:
        try:
            if config.arcp_client:
                # Report synthetic metrics
                metrics_data = {
                    "uptime": time.time() - config.start_time,
                    # In a real agent, track actual requests
                    "total_requests": 42,
                    "success_rate": 0.95,
                    "avg_response_time": 0.15,
                    "last_active": datetime.now().isoformat(),
                    "agent_status": "healthy",
                }

                await config.arcp_client.update_metrics(config.agent_id, metrics_data)
                logger.debug("📊 Metrics reported to ARCP")

            # Report every 60 seconds
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Metrics reporting task cancelled")
            break
        except Exception as e:
            logger.warning(f"Metrics reporting failed: {e}")
            await asyncio.sleep(30)  # Retry after 30 seconds


async def cleanup():
    """Clean up resources and unregister from ARCP"""
    logger.info("Starting cleanup...")

    # Cancel background tasks
    if config.heartbeat_task and not config.heartbeat_task.done():
        config.heartbeat_task.cancel()
        logger.info("Heartbeat task cancelled")

    if config.metrics_task and not config.metrics_task.done():
        config.metrics_task.cancel()
        logger.info("Metrics task cancelled")

    # Close ARCP client
    if config.arcp_client:
        try:
            await config.arcp_client.unregister_agent(config.agent_id)
            logger.info("Unregistered from ARCP")

            await config.arcp_client.__aexit__(None, None, None)
            logger.info("ARCP client connection closed")
        except Exception as e:
            logger.warning(f"Error during ARCP cleanup: {e}")

    logger.info("Cleanup completed")


async def main():
    """Main function - sets up and runs the demo agent"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ARCP Demo Agent")
    parser.add_argument(
        "--agent-key",
        required=True,
        help="Agent registration key for ARCP",
    )
    parser.add_argument(
        "--arcp-url",
        default="https://localhost",
        help="ARCP server URL (default: https://localhost)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host for agent API (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for agent API (default: 8080)",
    )
    parser.add_argument(
        "--agent-id",
        default="demo-agent-001",
        help="Agent ID (default: demo-agent-001)",
    )
    parser.add_argument(
        "--deployment-mode",
        choices=["docker", "internal"],
        required=True,
        help="Deployment mode: 'docker' for Docker containers (uses host.docker.internal), 'internal' for internal network (uses host IP)",
    )
    parser.add_argument(
        "--dpop",
        dest="dpop_enabled",
        action="store_true",
        default=False,
        help="Enable DPoP proofs for secure token binding (requires cryptography, PyJWT)",
    )
    parser.add_argument(
        "--no-dpop",
        dest="dpop_enabled",
        action="store_false",
        help="Disable DPoP proofs (default)",
    )
    parser.add_argument(
        "--mtls",
        dest="mtls_enabled",
        action="store_true",
        default=False,
        help="Enable mTLS client certificate authentication (requires cryptography)",
    )
    parser.add_argument(
        "--no-mtls",
        dest="mtls_enabled",
        action="store_false",
        help="Disable mTLS authentication (default)",
    )

    args = parser.parse_args()

    # Update configuration
    config.agent_key = args.agent_key
    config.arcp_url = args.arcp_url
    config.host = args.host
    config.port = args.port
    config.agent_id = args.agent_id
    config.deployment_mode = args.deployment_mode
    config.dpop_enabled = args.dpop_enabled
    config.mtls_enabled = args.mtls_enabled

    # Set endpoint based on deployment mode
    config.set_endpoint_from_deployment_mode()

    logger.info("Starting ARCP Demo Agent")
    logger.info("=" * 50)
    logger.info(f"Agent ID: {config.agent_id}")
    logger.info(f"Agent Type: {config.agent_type}")
    logger.info(f"Agent Name: {config.name}")
    logger.info(f"Deployment Mode: {config.deployment_mode}")
    logger.info(f"API Endpoint: {config.endpoint}")
    logger.info(f"ARCP Server: {config.arcp_url}")
    logger.info(f"DPoP Enabled: {config.dpop_enabled} (available: {HAS_DPOP})")
    logger.info(f"mTLS Enabled: {config.mtls_enabled} (available: {HAS_MTLS})")
    logger.info("=" * 50)

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

    try:
        # Configure and start the FastAPI server FIRST
        # This is required for TPR Phase 2 - the ARCP server validates our endpoints
        # before allowing registration, so the HTTP server must be running
        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(uvicorn_config)

        logger.info(f"Starting HTTP API server on {config.endpoint}")

        # Start the server in background so we can register
        server_task = asyncio.create_task(server.serve())

        # Give the server a moment to start
        await asyncio.sleep(1.0)

        # Now register with ARCP (TPR will validate our running endpoints)
        if not await register_with_arcp():
            logger.error("Failed to register with ARCP - exiting")
            server.should_exit = True
            await server_task
            return

        logger.info("Try these commands to test the agent:")
        logger.info(f"   curl {config.endpoint}/")
        logger.info(f"   curl {config.endpoint}/health")
        logger.info(
            f"   curl -X POST {config.endpoint}/echo "
            f"-H 'Content-Type: application/json' "
            f'-d \'{{"message": "Hello ARCP!"}}\''
        )

        # Wait for shutdown signal
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for either server completion or shutdown signal
        done, pending = await asyncio.wait(
            [server_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()

        logger.info("Server stopped")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await cleanup()
        logger.info("Demo agent shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
