"""Agent registration and discovery endpoints with vector search and metrics"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

from ..core.config import config
from ..core.dependencies import get_registry
from ..core.exceptions import (
    AgentNotFoundError,
    AgentRegistrationError,
    ARCPProblemTypes,
    agent_not_found_problem,
    create_problem_response,
    handle_exception_with_problem_details,
    invalid_input_problem,
    timeout_problem,
)
from ..core.registry import AgentRegistry
from ..models.agent import (
    AgentInfo,
    AgentRegistration,
    HeartbeatResponse,
    RegistrationResponse,
    SearchRequest,
    SearchResponse,
)
from ..services.metrics import get_metrics_service
from ..utils.api_protection import PermissionLevel, RequireAdmin, RequireAgent
from ..utils.sessions import get_token_payload

router = APIRouter()

# Store WebSocket connections
active_connections: List[WebSocket] = []

# Configure logging
logger = logging.getLogger(__name__)


async def broadcast_agents_update(registry: AgentRegistry):
    """Broadcast agent updates to all connected clients"""
    logger.info(f"Broadcasting to {len(active_connections)} WebSocket connections")
    if not active_connections:
        logger.debug("No active WebSocket connections to broadcast to")
        return

    try:
        agents = await asyncio.wait_for(
            registry.list_agents(),
            timeout=float(getattr(config, "WEBSOCKET_TIMEOUT", 5)),
        )
        agents_json = json.dumps(
            [agent.dict(exclude_none=True) for agent in agents], default=str
        )
        logger.info(f"Broadcasting {len(agents)} agents to WebSocket clients")

        disconnected = []
        broadcast_tasks = []

        for connection in active_connections:
            task = asyncio.create_task(send_to_connection(connection, agents_json))
            broadcast_tasks.append((task, connection))

        # Wait for all broadcasts to complete with timeout
        for task, connection in broadcast_tasks:
            try:
                await asyncio.wait_for(
                    task,
                    timeout=float(getattr(config, "WEBSOCKET_TIMEOUT", 2)),
                )
                logger.debug("Successfully sent data to WebSocket connection")
            except (Exception, asyncio.TimeoutError) as e:
                logger.warning(f"Failed to send to WebSocket connection: {e}")
                disconnected.append(connection)

        # Remove disconnected connections
        for conn in disconnected:
            if conn in active_connections:
                active_connections.remove(conn)
                logger.info(
                    f"Removed disconnected WebSocket connection. Remaining: {len(active_connections)}"
                )

    except asyncio.TimeoutError:
        logger.error("Timeout while fetching agents for broadcast")
    except Exception as e:
        logger.error(f"Error during broadcast: {e}")


async def send_to_connection(connection: WebSocket, message: str):
    """Send message to a specific WebSocket connection"""
    try:
        await connection.send_text(message)
    except Exception as e:
        logger.warning(f"Failed to send to specific connection: {e}")
        raise


async def on_agent_update(registry: AgentRegistry):
    """Callback for agent updates"""
    logger.debug("Agent update callback triggered")
    try:
        await asyncio.wait_for(broadcast_agents_update(registry), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Timeout during agent update broadcast")
    except Exception as e:
        logger.error(f"Error in agent update callback: {e}")


# Register the callback at module level to ensure it's always available
def register_callback():
    """Register the callback if not already registered"""
    if on_agent_update not in AgentRegistry.on_update_callbacks:
        AgentRegistry.on_update_callbacks.append(on_agent_update)
        logger.info("WebSocket callback registered with AgentRegistry")


# Register callback immediately when module loads
register_callback()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    registry: AgentRegistry = Depends(get_registry),
    # Note: WebSocket auth handled manually below
):
    """AGENT: WebSocket endpoint for real-time agent updates - requires agent authentication"""
    connection_id = (
        f"{websocket.client.host}:{websocket.client.port}"
        if websocket.client
        else "unknown"
    )
    logger.info(f"WebSocket connection attempt from {connection_id}")

    try:
        # Enforce WebSocket connection cap (agent-specific)
        if len(active_connections) >= int(
            getattr(
                config,
                "AGENT_WS_MAX_CONNECTIONS",
                getattr(config, "WEBSOCKET_MAX_CONNECTIONS", 100),
            )
        ):
            await websocket.close(code=1013, reason="WebSocket capacity reached")
            return
        # Accept the WebSocket connection
        await asyncio.wait_for(
            websocket.accept(),
            timeout=float(
                getattr(
                    config,
                    "AGENT_WS_TIMEOUT",
                    getattr(config, "WEBSOCKET_TIMEOUT", 5),
                )
            ),
        )
        logger.info(f"WebSocket connection accepted for {connection_id}")

        # AGENT AUTHENTICATION: Require token for WebSocket access
        try:
            # Request authentication token from client
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "auth_required",
                        "message": "Send your authentication token",
                    }
                )
            )

            # Wait for auth message with timeout
            auth_message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=float(
                    getattr(
                        config,
                        "AGENT_WS_TIMEOUT",
                        getattr(config, "WEBSOCKET_TIMEOUT", 10),
                    )
                ),
            )
            auth_data = json.loads(auth_message)

            token = auth_data.get("token")
            if not token:
                await websocket.send_text(
                    json.dumps({"type": "auth_error", "message": "Token required"})
                )
                await websocket.close(code=1008, reason="Authentication required")
                return

            # Verify token using registry
            payload = get_token_payload(token)
            if not payload:
                await websocket.send_text(
                    json.dumps({"type": "auth_error", "message": "Invalid token"})
                )
                await websocket.close(code=1008, reason="Invalid token")
                return

            user_role = payload.get("role", "agent")
            user_id = payload.get("sub")

            # Check if user has AGENT permission or higher
            if not PermissionLevel.can_access(user_role, PermissionLevel.AGENT):
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "auth_error",
                            "message": "Insufficient permissions",
                        }
                    )
                )
                await websocket.close(code=1008, reason="Insufficient permissions")
                return

            logger.info(
                f"WebSocket authenticated for user {user_id} with role {user_role}"
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "auth_success",
                        "message": "Authentication successful",
                    }
                )
            )

        except asyncio.TimeoutError:
            logger.warning(f"WebSocket authentication timeout for {connection_id}")
            await websocket.close(code=1008, reason="Authentication timeout")
            return
        except json.JSONDecodeError:
            logger.warning(
                f"WebSocket received invalid JSON for auth from {connection_id}"
            )
            await websocket.send_text(
                json.dumps({"type": "auth_error", "message": "Invalid JSON"})
            )
            await websocket.close(code=1008, reason="Invalid JSON")
            return
        except Exception as e:
            logger.error(f"WebSocket authentication error for {connection_id}: {e}")
            await websocket.send_text(
                json.dumps({"type": "auth_error", "message": "Authentication failed"})
            )
            await websocket.close(code=1008, reason="Authentication failed")
            return

        # Add to active connections immediately after accepting
        active_connections.append(websocket)
        logger.info(
            f"New WebSocket connection established. Total connections: {len(active_connections)}"
        )

        # Ensure callback is registered
        register_callback()

        # Send initial agents list with proper error handling and timeout
        try:
            logger.debug(f"Fetching initial agents list for {connection_id}")
            agents = await asyncio.wait_for(
                registry.list_agents(),
                timeout=float(
                    getattr(
                        config,
                        "AGENT_WS_TIMEOUT",
                        getattr(config, "WEBSOCKET_TIMEOUT", 10),
                    )
                ),
            )

            logger.debug(f"Serializing {len(agents)} agents for {connection_id}")
            agents_json = json.dumps(
                [agent.dict(exclude_none=True) for agent in agents],
                default=str,
            )

            logger.debug(f"Sending initial agents data to {connection_id}")
            await asyncio.wait_for(
                websocket.send_text(agents_json),
                timeout=float(
                    getattr(
                        config,
                        "AGENT_WS_TIMEOUT",
                        getattr(config, "WEBSOCKET_TIMEOUT", 5),
                    )
                ),
            )

            logger.info(
                f"Sent initial {len(agents)} agents to WebSocket client {connection_id}"
            )

        except asyncio.TimeoutError:
            logger.error(f"Timeout sending initial agents to {connection_id}")
            raise
        except Exception as e:
            logger.error(f"Failed to send initial agents to {connection_id}: {e}")
            raise

        # Keep connection alive and handle messages
        logger.debug(f"Starting message loop for {connection_id}")
        while True:
            try:
                # Wait for ping/pong or other messages with timeout
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=float(
                        getattr(
                            config,
                            "AGENT_WS_PING_INTERVAL",
                            getattr(config, "WEBSOCKET_PING_INTERVAL", 30),
                        )
                    ),
                )
                logger.debug(
                    f"Received message from {connection_id}: {message[:100]}..."
                )

                # Echo back pong for ping messages
                if message.strip().lower() == "ping":
                    await websocket.send_text("pong")
                    logger.debug(f"Responded to ping from agent {connection_id}")
                    continue

                # Handle pong responses (client responded to our ping)
                if message.strip().lower() == "pong":
                    logger.debug(
                        f"Received pong from agent {connection_id} (keepalive)"
                    )
                    continue

            except asyncio.TimeoutError:
                # Send a ping to check if connection is still alive
                try:
                    await websocket.send_text("ping")
                    logger.debug(f"Sent ping to {connection_id}")
                except Exception:
                    logger.info(
                        f"Connection {connection_id} appears dead, breaking loop"
                    )
                    break
            except WebSocketDisconnect:
                logger.info(f"WebSocket client {connection_id} disconnected normally")
                break
            except Exception as e:
                logger.warning(f"Error in message loop for {connection_id}: {e}")
                break

            try:
                await asyncio.sleep(
                    float(
                        getattr(
                            config,
                            "AGENT_WS_INTERVAL",
                            getattr(config, "WEBSOCKET_INTERVAL", 30),
                        )
                    )
                )
            except Exception:
                pass

    except asyncio.TimeoutError:
        logger.error(f"WebSocket connection timeout for {connection_id}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {connection_id} disconnected during setup")
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
    finally:
        # Cleanup: Remove from active connections
        if websocket in active_connections:
            active_connections.remove(websocket)
        logger.info(
            f"WebSocket connection closed for {connection_id}. Remaining connections: {len(active_connections)}"
        )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    dependencies=[RequireAgent],
)
async def register_agent(
    request: AgentRegistration,
    registry: AgentRegistry = Depends(get_registry),
    current_user: Dict[str, Any] = RequireAgent,
):
    """Universal agent registration with comprehensive validation and features"""
    start_time = time.time()
    metrics_service = get_metrics_service()

    try:
        # Verify the agent trying to register matches the authenticated user
        user_agent_id = current_user.get("agent_id")
        request_agent_id = request.agent_id

        # Security check: agent can only register itself (unless admin or using temp token)
        is_temp_token = current_user.get("temp_registration", False)
        if (
            not current_user.get("is_admin")
            and not is_temp_token
            and user_agent_id != request_agent_id
        ):
            logger.warning(
                f"Agent {user_agent_id} attempted to register different agent {request_agent_id}"
            )
            metrics_service.record_agent_registration(
                agent_type=getattr(request, "agent_type", "unknown"),
                status="unauthorized",
            )
            return create_problem_response(
                problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                detail="Agents can only register themselves",
                agent_id=user_agent_id,
                request_agent_id=request_agent_id,
            )

        # Debug: Log the incoming request
        logger.info(
            f"Processing agent registration for: {request.name} (ID: {request.agent_id})"
        )

        # Extract agent key hash from temporary token for validation (if present)
        agent_key_hash = None
        if is_temp_token and current_user.get("agent_key_hash"):
            agent_key_hash = current_user.get("agent_key_hash")

        # Register agent (this includes embedding generation and validation)
        await registry.register_agent(request, agent_key_hash=agent_key_hash)

        # Generate access token with proper role
        access_token = registry.create_access_token(
            data={
                "sub": request.agent_id,
                "agent_id": request.agent_id,
                "role": "agent",
                "scopes": [],
            }
        )

        # Record successful registration
        metrics_service.record_agent_registration(
            agent_type=getattr(request, "agent_type", "unknown"), status="success"
        )

        # Update active agents count
        try:
            agents = await registry.get_all_agents()
            active_count = len(
                [agent for agent in agents if agent.get("status") != "inactive"]
            )
            metrics_service.update_active_agents_count(active_count)
        except Exception as e:
            logger.debug(f"Failed to update active agents count: {e}")

        # Return comprehensive response with proper model
        logger.info(
            f"Agent {request.name} registered successfully with {len(request.capabilities)} capabilities"
        )
        return RegistrationResponse(
            status="success",
            message=f"Agent '{request.name}' registered successfully",
            agent_id=request.agent_id,
            access_token=access_token,
        )

    except AgentRegistrationError as e:
        agent_id = getattr(request, "agent_id", "unknown")
        metrics_service.record_agent_registration(
            agent_type=getattr(request, "agent_type", "unknown"), status="error"
        )
        return handle_exception_with_problem_details(
            logger, "Agent registration", e, agent_id=agent_id
        )
    except ValueError as e:
        agent_id = getattr(request, "agent_id", "unknown")
        metrics_service.record_agent_registration(
            agent_type=getattr(request, "agent_type", "unknown"),
            status="validation_error",
        )
        return handle_exception_with_problem_details(
            logger, "Agent registration", e, agent_id=agent_id
        )
    except Exception as e:
        agent_id = getattr(request, "agent_id", "unknown")
        metrics_service.record_agent_registration(
            agent_type=getattr(request, "agent_type", "unknown"), status="error"
        )
        return handle_exception_with_problem_details(
            logger, "Agent registration", e, agent_id=agent_id
        )
    finally:
        # Record request duration
        duration = time.time() - start_time
        metrics_service.record_http_request(
            method="POST",
            endpoint="/agents/register",
            status_code=200,  # This will be overridden by actual response status
            duration=duration,
        )


@router.post(
    "/search", response_model=List[SearchResponse], dependencies=[RequireAgent]
)
async def search_p_agents(
    request: SearchRequest, registry: AgentRegistry = Depends(get_registry)
):
    """Semantic search with vector embeddings"""
    start_time = time.time()
    metrics_service = get_metrics_service()

    try:
        results = await registry.vector_search(request)
        search_time = time.time() - start_time

        logger.info(
            f"Vector search for '{request.query}' returned {len(results)} results in {search_time:.3f}s"
        )

        # Record successful vector search
        metrics_service.record_vector_search("success")
        metrics_service.record_http_request(
            method="POST",
            endpoint="/agents/search",
            status_code=200,
            duration=search_time,
        )

        return results

    except Exception as e:
        search_time = time.time() - start_time
        metrics_service.record_vector_search("error")
        metrics_service.record_http_request(
            method="POST",
            endpoint="/agents/search",
            status_code=500,
            duration=search_time,
        )
        return handle_exception_with_problem_details(logger, "Vector search", e)


@router.get("/search", response_model=List[SearchResponse], dependencies=[RequireAgent])
async def search_g_agents(
    query: str = Query(..., description="Search query text"),
    top_k: int = Query(3, ge=1, le=100),
    min_similarity: float = Query(0.5, ge=0.0, le=1.0),
    capabilities: Optional[List[str]] = Query(None),
    weighted: bool = Query(False),
    agent_type: Optional[str] = Query(None),
    registry: AgentRegistry = Depends(get_registry),
):
    """GET variant that builds SearchRequest from query parameters"""
    request = SearchRequest(
        query=query,
        top_k=top_k,
        min_similarity=min_similarity,
        capabilities=capabilities,
        weighted=weighted,
        agent_type=agent_type,
    )
    return await search_p_agents(request, registry)


@router.post(
    "/{agent_id}/heartbeat",
    response_model=HeartbeatResponse,
    dependencies=[RequireAgent],
)
async def agent_heartbeat(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
    current_user: Dict[str, Any] = RequireAgent,
):
    """Update agent heartbeat timestamp - agents can only update their own heartbeat"""
    try:
        user_agent_id = current_user.get("agent_id")

        # Security check: agent can only update its own heartbeat (unless admin)
        if not current_user.get("is_admin") and user_agent_id != agent_id:
            logger.warning(
                f"Agent {user_agent_id} attempted to update heartbeat for different agent {agent_id}"
            )
            return create_problem_response(
                problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                detail="Agents can only update their own heartbeat",
                agent_id=user_agent_id,
                target_agent_id=agent_id,
            )

        result = await registry.heartbeat(agent_id)
        return result
    except AgentNotFoundError:
        return create_problem_response(
            problem_type=ARCPProblemTypes.AGENT_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
            agent_id=agent_id,
        )
    except Exception as e:
        logger.error(f"Error updating heartbeat for {agent_id}: {e}")
        return create_problem_response(
            problem_type=ARCPProblemTypes.INTERNAL_ERROR,
            detail=f"Failed to update heartbeat for agent {agent_id}",
            agent_id=agent_id,
        )


@router.post("/{agent_id}/metrics", dependencies=[RequireAgent])
async def update_agent_metrics(
    agent_id: str,
    metrics_data: Dict[str, Any],
    registry: AgentRegistry = Depends(get_registry),
    current_user: Dict[str, Any] = RequireAgent,
):
    """Update agent metrics"""
    try:
        user_agent_id = current_user.get("agent_id")

        # Security check: agent can only update its own metrics (unless admin)
        if not current_user.get("is_admin") and user_agent_id != agent_id:
            logger.warning(
                f"Agent {user_agent_id} attempted to update metrics for different agent {agent_id}"
            )
            return create_problem_response(
                problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                detail="Agents can only update their own metrics",
                agent_id=user_agent_id,
                target_agent_id=agent_id,
            )

        metrics = await registry.update_agent_metrics(agent_id, metrics_data)
        return {
            "status": "success",
            "message": "Metrics updated successfully",
            "metrics": (metrics.dict() if hasattr(metrics, "dict") else str(metrics)),
        }
    except AgentNotFoundError:
        return agent_not_found_problem(agent_id)
    except Exception as e:
        logger.error(f"Error updating metrics for {agent_id}: {e}")
        return handle_exception_with_problem_details(
            logger, "Update agent metrics", e, agent_id=agent_id
        )


@router.get("/{agent_id}/metrics", dependencies=[RequireAgent])
async def get_agent_metrics(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
    current_user: Dict[str, Any] = RequireAgent,
):
    """Get agent metrics"""
    try:
        user_agent_id = current_user.get("agent_id")

        # Security check: agent can only view its own metrics (unless admin)
        if not current_user.get("is_admin") and user_agent_id != agent_id:
            logger.warning(
                f"Agent {user_agent_id} attempted to view metrics for different agent {agent_id}"
            )
            return create_problem_response(
                problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                detail="Agents can only view their own metrics",
                agent_id=user_agent_id,
                target_agent_id=agent_id,
            )

        metrics = await registry.get_agent_metrics(agent_id)
        if not metrics:
            return Response(
                content=json.dumps(
                    {
                        "status": "error",
                        "message": f"No metrics found for agent {agent_id}",
                    }
                ),
                status_code=404,
                media_type="application/json",
            )

        # Return metrics fields directly (not nested)
        metrics_dict = metrics.dict() if hasattr(metrics, "dict") else {}
        return metrics_dict
    except AgentNotFoundError:
        return Response(
            content=json.dumps(
                {"status": "error", "message": f"Agent {agent_id} not found"}
            ),
            status_code=404,
            media_type="application/json",
        )
    except Exception as e:
        logger.error(f"Error getting metrics for {agent_id}: {e}")
        return Response(
            content=json.dumps({"status": "error", "message": str(e)}),
            status_code=500,
            media_type="application/json",
        )


async def _report_agent_metrics_impl(
    agent_id: str,
    response_time: float,
    success: bool,
    token: str,
    registry: AgentRegistry,
):
    """Common implementation for reporting agent metrics"""
    try:
        # Extract token from Authorization header
        if token.startswith("Bearer "):
            token = token[7:]

        # Verify JWT token properly
        if not token or len(token) < 10:
            logger.warning(f"Invalid token format for agent {agent_id}")
            return create_problem_response(
                problem_type=ARCPProblemTypes.TOKEN_VALIDATION_ERROR,
                detail="Invalid token format",
                agent_id=agent_id,
            )

        # Validate the JWT token
        try:
            token_data = registry.verify_token(token)
            if not token_data:
                return create_problem_response(
                    problem_type=ARCPProblemTypes.TOKEN_VALIDATION_ERROR,
                    detail="Invalid or expired token",
                    agent_id=agent_id,
                )
        except Exception as e:
            logger.warning(f"Token validation failed for agent {agent_id}: {e}")
            return create_problem_response(
                problem_type=ARCPProblemTypes.TOKEN_VALIDATION_ERROR,
                detail="Token validation failed",
                agent_id=agent_id,
            )

        # Update metrics with validated token
        try:
            metrics = await registry.update_agent_metrics(
                agent_id, response_time, success
            )

            return {
                "status": "success",
                "message": "Metrics updated successfully",
                "current_metrics": {
                    "success_rate": round(metrics.success_rate, 3),
                    "avg_response_time": round(metrics.avg_response_time, 3),
                    "total_requests": metrics.total_requests,
                    "reputation_score": round(metrics.reputation_score, 3),
                    "last_active": metrics.last_active,
                },
            }
        except Exception as metrics_error:
            logger.warning(f"Metrics update failed for {agent_id}: {metrics_error}")
            # Return success anyway to avoid blocking agents
            return {
                "status": "accepted",
                "message": "Metrics received but could not be processed",
                "agent_id": agent_id,
            }

    except Exception as e:
        logger.error(f"Error processing metrics for {agent_id}: {e}")
        # Return success to avoid blocking agents
        return {
            "status": "accepted",
            "message": "Metrics received",
            "agent_id": agent_id,
        }


@router.post("/report-metrics/{agent_id}")
async def report_agent_metrics(
    agent_id: str,
    response_time: float = Query(..., description="Response time in seconds"),
    success: bool = Query(True, description="Whether the operation was successful"),
    token: str = Header(..., alias="Authorization"),
    registry: AgentRegistry = Depends(get_registry),
):
    """Report agent performance metrics for reputation tracking"""
    return await _report_agent_metrics_impl(
        agent_id, response_time, success, token, registry
    )


@router.post("/{agent_id}/metrics/compat")
async def report_agent_metrics_compat(
    agent_id: str,
    response_time: float = Query(..., description="Response time in seconds"),
    success: bool = Query(True, description="Whether the operation was successful"),
    token: str = Header(..., alias="Authorization"),
    registry: AgentRegistry = Depends(get_registry),
):
    """Compatibility endpoint for agent metrics reporting (matches VulnIntel expectations)"""
    return await _report_agent_metrics_impl(
        agent_id, response_time, success, token, registry
    )


@router.get("", response_model=List[AgentInfo], dependencies=[RequireAgent])
async def list_agents(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    status: Optional[str] = Query(
        None, description="Filter by status: 'alive' or 'dead'"
    ),
    capabilities: Optional[List[str]] = Query(
        None, description="Filter by capabilities"
    ),
    include_metrics: bool = Query(False, description="Include performance metrics"),
    registry: AgentRegistry = Depends(get_registry),
):
    """Agent listing with filtering and metrics - requires authentication"""
    try:
        agents = await registry.list_agents(
            agent_type=agent_type, capabilities=capabilities, status=status
        )

        # Filter out metrics if not requested
        if not include_metrics:
            for agent in agents:
                agent.metrics = None

        return agents

    except Exception as e:
        return handle_exception_with_problem_details(logger, "List agents", e)


@router.get("/stats", response_model=dict, dependencies=[RequireAdmin])
async def get_registry_stats(registry: AgentRegistry = Depends(get_registry)):
    """Registry statistics"""
    try:
        stats = await registry.get_stats()
        return {
            "registry_statistics": stats,
            "features": {
                "vector_search_enabled": stats["ai_client_available"],
                "redis_storage_enabled": stats["redis_connected"],
                "metrics_tracking_enabled": True,
                "websocket_broadcasts_enabled": True,
            },
            "performance": {
                "active_websocket_connections": len(active_connections),
                "vector_embeddings_stored": stats["embeddings_available"],
            },
        }

    except Exception as e:
        return handle_exception_with_problem_details(logger, "Get registry stats", e)


@router.get("/{agent_id}", response_model=AgentInfo, dependencies=[RequireAgent])
async def get_agent(
    agent_id: str,
    include_metrics: bool = Query(True, description="Include performance metrics"),
    registry: AgentRegistry = Depends(get_registry),
):
    """Get specific agent information with metrics"""
    try:
        agent = await registry.get_agent(agent_id)
        if not agent:
            return agent_not_found_problem(agent_id)

        if not include_metrics:
            agent.metrics = None

        return agent

    except AgentNotFoundError:
        return Response(
            content=json.dumps({"status": "error", "message": "Agent not found"}),
            status_code=404,
            media_type="application/json",
        )
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}")
        return handle_exception_with_problem_details(
            logger, "Get agent", e, agent_id=agent_id
        )


@router.delete("/{agent_id}", dependencies=[RequireAgent])
async def unregister_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
    current_user: Dict[str, Any] = RequireAgent,
):
    """Agent deregistration with authentication - agents can only unregister themselves unless admin"""
    try:
        user_agent_id = current_user.get("agent_id")

        # Allow admins to unregister any agent
        if current_user.get("is_admin"):
            action_by = f"admin ({current_user.get('sub', 'unknown')})"
        else:
            # Security check: agent can only unregister itself (unless admin)
            if user_agent_id != agent_id:
                logger.warning(
                    f"Agent {user_agent_id} attempted to unregister different agent {agent_id}"
                )
                return create_problem_response(
                    problem_type=ARCPProblemTypes.INSUFFICIENT_PERMISSIONS,
                    detail="Agents can only unregister themselves",
                    agent_id=user_agent_id,
                    target_agent_id=agent_id,
                )
            action_by = "agent (self)"

        # Unregister agent
        success = await registry.unregister_agent(agent_id)
        if not success:
            return agent_not_found_problem(agent_id)

        logger.info(f"Agent {agent_id} unregistered by {action_by}")

        return {
            "status": "success",
            "message": f"Agent {agent_id} unregistered successfully",
            "unregistered_by": action_by,
        }

    except Exception as e:
        logger.error(f"Error unregistering agent {agent_id}: {e}")
        return handle_exception_with_problem_details(
            logger, "Unregister agent", e, agent_id=agent_id
        )


@router.post("/{agent_id}/connection/notify", dependencies=[RequireAgent])
async def notify_agent_connection(
    agent_id: str,
    request: dict,
    registry: AgentRegistry = Depends(get_registry),
):
    """
    Notify agent about agent connection request.
    ARCP only facilitates initial contact - all further communication is direct.
    """
    try:
        # Get agent info
        agent = await registry.get_agent(agent_id)
        if not agent:
            return agent_not_found_problem(agent_id)

        # Extract requester info (avoid shadowing path param)
        requester_agent_id = request.get("agent_id")
        requester_agent_endpoint = request.get("agent_endpoint")

        if not requester_agent_id or not requester_agent_endpoint:
            return invalid_input_problem(
                "connection request",
                "Missing agent_id or agent_endpoint",
                agent_id=agent_id,
            )

        logger.info(
            f"Notifying agent {agent_id} about connection from agent {requester_agent_id}"
        )

        # Forward notification to agent
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{agent.endpoint}/connection/notify",
                    json={
                        "agent_id": requester_agent_id,
                        "agent_endpoint": requester_agent_endpoint,
                        "agent_info": request.get("agent_info", {}),
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(f"Successfully notified agent {agent_id}")
                    return {
                        "status": "notified",
                        "message": "Agent notified successfully",
                        "agent_endpoint": agent.endpoint,
                        "next_step": "Agent will contact agent directly with requirements",
                    }
                elif response.status_code == 404:
                    logger.warning(
                        f"Agent {agent_id} returned 404 (connection/notify not found)"
                    )
                    return create_problem_response(
                        problem_type=ARCPProblemTypes.NOT_FOUND,
                        detail="Agent connection endpoint not found",
                        agent_id=agent_id,
                    )
                else:
                    logger.error(
                        f"Agent {agent_id} returned status {response.status_code}"
                    )
                    return create_problem_response(
                        problem_type=ARCPProblemTypes.ENDPOINT_UNREACHABLE,
                        detail=f"Agent returned error: {response.status_code}",
                        agent_id=agent_id,
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException:
                logger.error(f"Timeout notifying agent {agent_id}")
                return timeout_problem("Agent notification", agent_id=agent_id)
            except Exception as e:
                logger.error(f"Error notifying agent {agent_id}: {e}")
                return create_problem_response(
                    problem_type=ARCPProblemTypes.ENDPOINT_UNREACHABLE,
                    detail="Agent returned an unexpected error while processing the connection request",
                    agent_id=agent_id,
                )

    except Exception as e:
        logger.error(f"Error in connection notification: {e}")
        return handle_exception_with_problem_details(
            logger, "Agent connection notification", e, agent_id=agent_id
        )
