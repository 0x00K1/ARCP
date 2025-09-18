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

Usage:
    python demo_agent.py --agent-key YOUR_AGENT_KEY --deployment-mode [docker|internal]

Arguments:
    --deployment-mode: REQUIRED - Specify 'docker' for Docker deployment (uses host.docker.internal)
                      or 'internal' for internal network deployment (uses host IP)

Requirements:
    - ARCP server running (default: http://localhost:8001)
    - Valid agent registration key
    - Available port for agent API (default: 8080)
"""

import argparse
import asyncio
import logging
import signal
import time
from datetime import datetime
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from arcp import AgentRequirements, ARCPClient, ARCPError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("demo-agent")


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
        "agent_id": config.agent_id,
        "name": config.name,
        "type": config.agent_type,
        "version": config.version,
        "status": "running",
        "capabilities": config.capabilities,
        "features": config.features,
        "description": config.context_brief,
        "endpoint": config.endpoint,
        "uptime": time.time() - config.start_time,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    # Check ARCP connection status more comprehensively
    arcp_connected = (
        config.arcp_client is not None
        and config.heartbeat_task is not None
        and not config.heartbeat_task.done()
    )

    return {
        "status": "healthy",
        "agent_id": config.agent_id,
        "uptime": time.time() - config.start_time,
        "arcp_connected": arcp_connected,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for ARCP dashboard monitoring"""
    return {
        "status": "pong",
        "agent_id": config.agent_id,
        "timestamp": datetime.now().isoformat(),
        "response_time": f"{time.time() * 1000:.2f}ms",
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
async def handle_connection_request(request: ConnectionRequest):
    """Handle connection requests from ARCP clients"""
    start_time = time.time()

    try:
        logger.info(
            f"   Connection request from user: {request.user_id} "
            f"({request.display_name})"
        )
        logger.info(f"   User endpoint: {request.user_endpoint}")
        logger.info(f"   Additional info: {request.additional_info}")

        # In a real agent, you would:
        # 1. Validate the connection request
        # 2. Check user permissions/authorization
        # 3. Establish a connection session
        # 4. Return connection details or reject

        # For the demo, we'll accept all connections
        connection_id = f"conn-{int(time.time())}-{request.user_id[:8]}"

        response_time = time.time() - start_time

        # Report connection metrics to ARCP
        if config.arcp_client and config.access_token:
            try:
                await config.arcp_client.update_metrics(
                    config.agent_id,
                    {
                        "operation": "connection_request",
                        "user_id": request.user_id,
                        "response_time": response_time,
                        "success": True,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to report connection metrics: {e}")

        return {
            "status": "connection_accepted",
            "message": (f"Connection accepted for user {request.display_name}"),
            "next_steps": (
                f"Use connection_id '{connection_id}' for subsequent "
                f"requests. Available endpoints: {config.endpoint}/echo, "
                f"{config.endpoint}/compute. Send POST requests with JSON "
                "payloads."
            ),
            "agent_info": {
                "name": config.name,
                "agent_id": config.agent_id,
                "version": config.version,
                "capabilities": config.capabilities,
                "supported_operations": ["echo", "compute", "task", "status"],
                "connection_id": connection_id,
                "created_at": datetime.now().isoformat(),
                "expires_at": None,
            },
            "request_id": connection_id,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Connection request failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Connection request failed: {str(e)}"
        )


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
        # Create ARCP client instance
        config.arcp_client = ARCPClient(config.arcp_url)
        await config.arcp_client.__aenter__()

        logger.info("=== Registering with ARCP ===")
        logger.info(f"Agent ID: {config.agent_id}")
        logger.info(f"Agent Type: {config.agent_type}")
        logger.info(f"Endpoint: {config.endpoint}")
        logger.info(f"ARCP Server: {config.arcp_url}")

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
                "created_at": datetime.now().isoformat(),
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
            agent_key=config.agent_key,
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
        default="http://localhost:8001",
        help="ARCP server URL (default: http://localhost:8001)",
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

    args = parser.parse_args()

    # Update configuration
    config.agent_key = args.agent_key
    config.arcp_url = args.arcp_url
    config.host = args.host
    config.port = args.port
    config.agent_id = args.agent_id
    config.deployment_mode = args.deployment_mode

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
        # Register with ARCP
        if not await register_with_arcp():
            logger.error("Failed to register with ARCP - exiting")
            return

        # Configure and start the FastAPI server
        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(uvicorn_config)

        logger.info(f"Starting HTTP API server on {config.endpoint}")
        logger.info("Try these commands to test the agent:")
        logger.info(f"   curl {config.endpoint}/")
        logger.info(f"   curl {config.endpoint}/health")
        logger.info(
            f"   curl -X POST {config.endpoint}/echo "
            f"-H 'Content-Type: application/json' "
            f'-d \'{{"message": "Hello ARCP!"}}\''
        )

        # Run server until shutdown signal
        server_task = asyncio.create_task(server.serve())
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
