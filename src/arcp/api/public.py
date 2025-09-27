"""Public API endpoints for external developers.

ARCP Public API for External Developers
Developer Use Case: Agent Discovery & Connection

For external developers building applications that need to:
- Display agent cards with full info
- Allow users to search for agents
- Enable users to connect with agents

These endpoints are intentionally PUBLIC to enable:
- Agent marketplace platforms
- Discovery interfaces
- Third-party integrations
- External developer adoption
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ..core.config import config
from ..core.dependencies import get_registry
from ..core.exceptions import (
    ARCPProblemTypes,
    agent_not_available_problem,
    agent_not_found_problem,
    create_problem_response,
    endpoint_unreachable_problem,
    handle_exception_with_problem_details,
    invalid_input_problem,
    timeout_problem,
)
from ..core.registry import AgentRegistry
from ..models.agent import (
    AgentConnectionRequest,
    AgentConnectionResponse,
    AgentInfo,
    SearchRequest,
    SearchResponse,
)
from ..utils.api_protection import RequirePublic

router = APIRouter()
logger = logging.getLogger(__name__)

# Store Public WebSocket connections
public_active_connections: List[WebSocket] = []


async def broadcast_public_agents_update(registry: AgentRegistry):
    """Broadcast public agent updates to all connected public WebSocket clients"""
    logger.info(
        f"Broadcasting to {len(public_active_connections)} public WebSocket connections"
    )
    if not public_active_connections:
        logger.debug("No active public WebSocket connections to broadcast to")
        return

    try:
        agents = await asyncio.wait_for(
            registry.list_agents(),
            timeout=float(
                getattr(
                    config,
                    "PUBLIC_WS_TIMEOUT",
                    getattr(config, "WEBSOCKET_TIMEOUT", 5),
                )
            ),
        )

        # Filter to only alive agents for public
        public_agents = [
            agent.dict(exclude_none=True) for agent in agents if agent.status == "alive"
        ]

        # Wrap in proper message format for consistency
        broadcast_message = {
            "type": "agents_update",
            "timestamp": time.time(),
            "data": {
                "agents": public_agents,
                "total_count": len(public_agents),
            },
        }
        agents_json = json.dumps(broadcast_message, default=str)
        logger.info(
            f"Broadcasting {len(public_agents)} public agents to WebSocket clients"
        )

        disconnected = []
        broadcast_tasks = []

        for connection in public_active_connections:
            task = asyncio.create_task(
                send_to_public_connection(connection, agents_json)
            )
            broadcast_tasks.append((task, connection))

        # Wait for all broadcasts to complete with timeout
        for task, connection in broadcast_tasks:
            try:
                await asyncio.wait_for(
                    task,
                    timeout=float(
                        getattr(
                            config,
                            "PUBLIC_WS_TIMEOUT",
                            getattr(config, "WEBSOCKET_TIMEOUT", 30),
                        )
                    ),
                )
                logger.debug("Successfully sent data to public WebSocket connection")
            except (Exception, asyncio.TimeoutError) as e:
                logger.warning(f"Failed to send to public WebSocket connection: {e}")
                disconnected.append(connection)

        # Remove disconnected connections
        for conn in disconnected:
            if conn in public_active_connections:
                public_active_connections.remove(conn)
                logger.info(
                    f"Removed disconnected public WebSocket connection. Remaining: {len(public_active_connections)}"
                )

    except asyncio.TimeoutError:
        logger.error("Timeout while fetching agents for public broadcast")
    except Exception as e:
        logger.error(f"Error during public broadcast: {e}")


async def send_to_public_connection(connection: WebSocket, message: str):
    """Send message to a specific public WebSocket connection"""
    try:
        await connection.send_text(message)
    except Exception as e:
        logger.warning(f"Failed to send to specific public connection: {e}")
        raise


async def on_public_agent_update(registry: AgentRegistry):
    """Callback for public agent updates"""
    logger.debug("Public agent update callback triggered")
    try:
        await asyncio.wait_for(broadcast_public_agents_update(registry), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Timeout during public agent update broadcast")
    except Exception as e:
        logger.error(f"Error in public agent update callback: {e}")


# Register the callback at module level to ensure it's always available
def register_public_callback():
    """Register the public callback if not already registered"""
    if on_public_agent_update not in AgentRegistry.on_update_callbacks:
        AgentRegistry.on_update_callbacks.append(on_public_agent_update)
        logger.info("Public WebSocket callback registered with AgentRegistry")


# Register callback immediately when module loads
register_public_callback()


# ================================
# PUBLIC DISCOVERY ENDPOINTS
# ================================


@router.get("/discover", response_model=List[AgentInfo])
async def discover_agents(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    capabilities: Optional[List[str]] = Query(
        None, description="Filter by capabilities"
    ),
    limit: int = Query(50, le=100, description="Maximum number of agents to return"),
    offset: int = Query(0, description="Number of agents to skip"),
    registry: AgentRegistry = Depends(get_registry),
    _: dict = RequirePublic,
):
    """
    PUBLIC: Discover agents for external applications

    Perfect for building agent marketplace cards and discovery interfaces.
    Returns sanitized agent information suitable for public consumption.

    - **agent_type**: Filter by specific agent type (e.g., "security", "analysis")
    - **capabilities**: Filter by required capabilities
    - **limit**: Maximum agents to return (max 100)
    - **offset**: Pagination offset

    **Returns**: List of public agent information
    """
    try:
        logger.info(
            f"Public agent discovery request: type={agent_type}, capabilities={capabilities}, limit={limit}, offset={offset}"
        )

        # Get agents from registry with filters
        agents = await registry.list_agents()

        # Apply filters
        filtered_agents = []
        for agent in agents:
            # Only show alive agents publicly
            if agent.status != "alive":
                continue

            # Apply agent_type filter
            if agent_type and agent.agent_type != agent_type:
                continue

            # Apply capabilities filter
            if capabilities:
                agent_capabilities = agent.capabilities or []
                if not all(cap in agent_capabilities for cap in capabilities):
                    continue

            filtered_agents.append(agent)

        # Apply pagination
        paginated_agents = filtered_agents[offset : offset + limit]

        # Return full agent information
        public_agents = []
        for agent in paginated_agents:
            public_agent = AgentInfo(
                agent_id=agent.agent_id,
                name=agent.name,
                agent_type=agent.agent_type,
                endpoint=agent.endpoint,
                capabilities=agent.capabilities,
                context_brief=getattr(agent, "context_brief", ""),
                version=agent.version,
                owner=getattr(agent, "owner", ""),
                public_key=getattr(agent, "public_key", ""),
                metadata=getattr(agent, "metadata", {}),
                communication_mode=getattr(agent, "communication_mode", "remote"),
                features=getattr(agent, "features", None),
                max_tokens=getattr(agent, "max_tokens", None),
                language_support=getattr(agent, "language_support", None),
                rate_limit=getattr(agent, "rate_limit", None),
                requirements=getattr(agent, "requirements", None),
                policy_tags=getattr(agent, "policy_tags", None),
                status=agent.status,
                last_seen=agent.last_seen,
                registered_at=agent.registered_at,
                similarity=getattr(agent, "similarity", None),
                metrics=agent.metrics if hasattr(agent, "metrics") else None,
            )
            public_agents.append(public_agent)

        logger.info(
            f"Public discovery returned {len(public_agents)} agents (filtered from {len(filtered_agents)} total)"
        )
        return public_agents

    except Exception as e:
        return handle_exception_with_problem_details(
            logger, "Public agent discovery", e
        )


@router.post("/search", response_model=List[SearchResponse])
async def search_agents(
    request: SearchRequest,
    registry: AgentRegistry = Depends(get_registry),
    _: dict = RequirePublic,
):
    """
    PUBLIC: Search agents using semantic vector search

    Enables powerful agent discovery for external applications using AI-powered search.
    Uses semantic similarity to find agents matching the search query.

    - **request**: SearchRequest with query, filters, and limits

    **Returns**: List of matching agents with similarity scores
    """
    try:
        logger.info(
            f"Public agent search request: query='{request.query}', type={request.agent_type}, capabilities={request.capabilities}, top_k={request.top_k}"
        )

        # Perform vector search using the SearchRequest model
        results = await registry.vector_search(request)

        # Results are already SearchResponse instances from the registry; return directly
        logger.info(
            f"Public search returned {len(results)} results for query: '{request.query}'"
        )
        return results

    except Exception as e:
        return handle_exception_with_problem_details(logger, "Public agent search", e)


@router.get("/agent/{agent_id}", response_model=AgentInfo)
async def get_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
    _: dict = RequirePublic,
):
    """
    PUBLIC: Get detailed agent information for public display

    Returns comprehensive agent details suitable for agent cards and profiles.
    Perfect for displaying detailed agent information before connection.

    - **agent_id**: Unique identifier of the agent

    **Returns**: Detailed agent information (sensitive data removed)
    """
    try:
        logger.info(f"Public agent details request: agent_id={agent_id}")

        agent = await registry.get_agent(agent_id)
        if not agent:
            logger.warning(f"Agent not found for public request: {agent_id}")
            return agent_not_found_problem(agent_id)

        # Only show active agents publicly
        if agent.status != "alive":
            logger.warning(
                f"Inactive agent requested publicly: {agent_id} (status: {agent.status})"
            )
            return agent_not_available_problem(agent_id)

        # Keep all agent information
        public_agent = AgentInfo(
            agent_id=agent.agent_id,
            name=agent.name,
            agent_type=agent.agent_type,
            endpoint=agent.endpoint,
            capabilities=agent.capabilities,
            context_brief=getattr(agent, "context_brief", ""),
            version=agent.version,
            owner=getattr(agent, "owner", ""),
            public_key=getattr(agent, "public_key", ""),
            metadata=getattr(agent, "metadata", {}),
            communication_mode=getattr(agent, "communication_mode", "remote"),
            features=getattr(agent, "features", None),
            max_tokens=getattr(agent, "max_tokens", None),
            language_support=getattr(agent, "language_support", None),
            rate_limit=getattr(agent, "rate_limit", None),
            requirements=getattr(agent, "requirements", None),
            policy_tags=getattr(agent, "policy_tags", None),
            status=agent.status,
            last_seen=agent.last_seen,
            registered_at=agent.registered_at,
            similarity=getattr(agent, "similarity", None),
            metrics=agent.metrics if hasattr(agent, "metrics") else None,
        )

        logger.info(f"Public agent details returned for: {agent_id} ({agent.name})")
        return public_agent

    except Exception as e:
        logger.error(f"Error getting public agent {agent_id}: {e}")
        return handle_exception_with_problem_details(
            logger, "Get public agent information", e, agent_id=agent_id
        )


# ================================
# PUBLIC CONNECTION ENDPOINTS
# ================================


@router.post("/connect/{agent_id}", response_model=AgentConnectionResponse)
async def request_agent_connection(
    agent_id: str,
    user_info: AgentConnectionRequest,
    registry: AgentRegistry = Depends(get_registry),
    _: dict = RequirePublic,
):
    """
    PUBLIC: Request connection to an agent for external users

    Allows external applications to facilitate user-agent connections.
    The agent will receive the connection request and can respond directly to the user.

    - **agent_id**: ID of the agent to connect to
    - **user_info**: User connection details including endpoint and display name

    **Returns**: AgentConnectionResponse with connection status and next steps
    """
    try:
        logger.info(
            f"Public connection request: User {user_info.user_id} ({user_info.display_name}) wants to connect to agent {agent_id}"
        )

        # Validate agent exists and is active
        agent = await registry.get_agent(agent_id)
        if not agent or agent.status != "alive":
            logger.warning(f"Connection request to unavailable agent: {agent_id}")
            return agent_not_available_problem(agent_id)

        # Validate required user info
        if not user_info.user_id or not user_info.user_endpoint:
            return invalid_input_problem(
                "user info",
                "user_id and user_endpoint are required",
                agent_id=agent_id,
            )

        # Validate endpoint format
        if not user_info.user_endpoint.startswith(("http://", "https://")):
            return invalid_input_problem(
                "user_endpoint",
                "user_endpoint must be a valid HTTP/HTTPS URL",
                agent_id=agent_id,
            )

        logger.info(
            f"Forwarding connection request to agent {agent_id} at {agent.endpoint}"
        )

        # Forward connection request to agent
        async with httpx.AsyncClient() as client:
            try:
                connection_payload = {
                    "user_id": user_info.user_id,
                    "user_endpoint": user_info.user_endpoint,
                    "user_display_name": user_info.display_name,
                    "connection_type": "external_app",
                    "user_info": user_info.additional_info,
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),  # Dynamic timestamp
                    "request_source": "arcp_public_api",
                }

                response = await client.post(
                    f"{agent.endpoint}/connection/request",
                    json=connection_payload,
                    timeout=10.0,
                    headers={"User-Agent": "ARCP-Public-API/1.0"},
                )

                if response.status_code == 200:
                    logger.info(
                        f"Connection request successfully forwarded to agent {agent_id}"
                    )
                    # Serialize requirements for agent_info
                    requirements_dict = (
                        agent.requirements.model_dump() if agent.requirements else None
                    )

                    return AgentConnectionResponse(
                        status="connection_requested",
                        message=f"Connection request sent to {agent.name}",
                        next_steps="Agent will contact you directly with connection details",
                        agent_info={
                            "name": agent.name,
                            "agent_type": agent.agent_type,
                            "capabilities": agent.capabilities,
                            "requirements": requirements_dict,
                        },
                        request_id=f"pub_{agent_id}_{user_info.user_id}"[
                            :50
                        ],  # Truncated request ID
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                else:
                    logger.warning(
                        f"Agent {agent_id} returned status {response.status_code} for connection request"
                    )
                    return create_problem_response(
                        problem_type=ARCPProblemTypes.ENDPOINT_UNREACHABLE,
                        detail="Agent connection service unavailable",
                        agent_id=agent_id,
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException:
                logger.error(f"Timeout connecting to agent {agent_id}")
                return timeout_problem("Agent connection")
            except httpx.ConnectError:
                logger.error(f"Failed to connect to agent {agent_id} endpoint")
                return endpoint_unreachable_problem(agent.endpoint)
            except Exception as e:
                logger.error(f"Error connecting to agent {agent_id}: {e}")
                return create_problem_response(
                    problem_type=ARCPProblemTypes.ENDPOINT_UNREACHABLE,
                    detail="Failed to connect to agent",
                    agent_id=agent_id,
                )

    except Exception as e:
        logger.error(f"Error in public connection request: {e}")
        return handle_exception_with_problem_details(
            logger, "Public connection request", e, agent_id=agent_id
        )


# ================================
# PUBLIC WEBSOCKET ENDPOINT
# ================================


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    registry: AgentRegistry = Depends(get_registry),
    # Note: WebSocket auth handled manually below
):
    """PUBLIC: WebSocket endpoint for real-time public agent updates"""
    connection_id = (
        f"{websocket.client.host}:{websocket.client.port}"
        if websocket.client
        else "unknown"
    )
    logger.info(f"Public WebSocket connection attempt from {connection_id}")

    try:
        try:
            # Enforce WebSocket connection cap (public-specific)
            max_conns = int(
                getattr(
                    config,
                    "PUBLIC_WS_MAX_CONNECTIONS",
                    getattr(config, "WEBSOCKET_MAX_CONNECTIONS", 100),
                )
            )
            if max_conns > 0 and len(public_active_connections) >= max_conns:
                await websocket.close(
                    code=1013, reason="Public WebSocket capacity reached"
                )
                return
        except Exception:
            pass

        # Accept the WebSocket connection
        await asyncio.wait_for(
            websocket.accept(),
            timeout=float(
                getattr(
                    config,
                    "PUBLIC_WS_TIMEOUT",
                    getattr(config, "WEBSOCKET_TIMEOUT", 5),
                )
            ),
        )
        logger.info(f"Public WebSocket connection accepted for {connection_id}")

        # Add to active connections immediately after accepting
        public_active_connections.append(websocket)
        logger.info(
            f"New public WebSocket connection established. Total connections: {len(public_active_connections)}"
        )

        # Ensure callback is registered
        register_public_callback()

        # Send welcome message
        await websocket.send_text(
            json.dumps(
                {
                    "type": "welcome",
                    "message": "Connected to ARCP Public API WebSocket",
                    "features": [
                        "agent_updates",
                        "public_stats",
                        "discovery_events",
                        "paginated_discovery",
                    ],
                    "commands": {
                        "ping": "Send ping to check connection",
                        "get_discovery": "Get agent discovery data with pagination",
                    },
                    "pagination": {
                        "default_page_size": 30,
                        "max_page_size": 100,
                        "usage": "Send {type: 'get_discovery', page: 1, page_size: 30, agent_type: 'optional'}",
                    },
                }
            )
        )

        # Note: Initial agents data is sent only when requested via 'get_discovery' command
        # This allows for better control of message flow and testing

        # Keep connection alive and send periodic updates
        last_update = (
            time.time()
        )  # Initialize to current time to prevent immediate stats update
        # Use dedicated public WS interval from config (seconds)
        update_interval = getattr(
            config,
            "PUBLIC_WS_INTERVAL",
            getattr(config, "WEBSOCKET_INTERVAL", 30),
        )

        while True:
            try:
                # Send periodic agent discovery updates
                current_time = time.time()
                if current_time - last_update >= update_interval:

                    # Get current public stats
                    stats = await registry.get_stats()
                    total_agents = stats.get("total_agents", 0)
                    alive_agents = stats.get("alive_agents", 0)
                    dead_agents = stats.get("dead_agents", 0)
                    agent_types = stats.get("agent_types", {})

                    # Send public statistics update
                    update_message = {
                        "type": "stats_update",
                        "timestamp": time.time(),
                        "data": {
                            "total_agents": total_agents,
                            "alive_agents": alive_agents,
                            "dead_agents": dead_agents,
                            "agent_types_count": len(agent_types),
                            "available_types": (
                                list(agent_types.keys()) if agent_types else []
                            ),
                            "system_status": "operational",
                        },
                    }

                    await websocket.send_text(json.dumps(update_message))
                    logger.debug(
                        f"Sent public stats update to {connection_id}: {alive_agents} agents"
                    )
                    last_update = current_time

                # Check for incoming messages (ping/pong, requests)
                try:
                    # Non-blocking receive with short timeout
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=float(
                            max(
                                1.0,
                                getattr(
                                    config,
                                    "PUBLIC_WS_PING_INTERVAL",
                                    getattr(config, "WEBSOCKET_PING_INTERVAL", 30),
                                ),
                            )
                        ),
                    )

                    # Handle both plain text and JSON format messages (like agent WebSocket)
                    plain = message.strip().lower()
                    if plain == "ping":
                        # Plain text ping - respond with plain text pong (like agent WebSocket)
                        await websocket.send_text("pong")
                        logger.debug(
                            f"Responded to plain text ping from {connection_id}"
                        )
                        continue
                    if plain == "pong":
                        # Plain text pong from client - treat as keepalive, no action needed
                        logger.debug(f"Received plain text pong from {connection_id}")
                        continue

                    # Try to parse as JSON for structured messages
                    try:
                        data = json.loads(message)
                        message_type = data.get("type")

                        if message_type == "ping":
                            # JSON format ping - respond with JSON format pong
                            await websocket.send_text(
                                json.dumps({"type": "pong", "timestamp": time.time()})
                            )
                            logger.debug(f"Responded to JSON ping from {connection_id}")

                        elif message_type == "pong":
                            # JSON format pong from client - treat as keepalive, no action needed
                            logger.debug(f"Received JSON pong from {connection_id}")

                        elif message_type == "get_discovery":
                            # Send current agent discovery data with pagination support
                            try:
                                # Get pagination parameters from message
                                page = data.get("page", 1)  # Default to page 1
                                page_size = data.get(
                                    "page_size", 30
                                )  # Default to 30 agents per page
                                agent_type_filter = data.get(
                                    "agent_type"
                                )  # Optional filter

                                # Validate pagination parameters
                                page = max(1, int(page))  # Ensure page >= 1
                                page_size = min(
                                    100, max(1, int(page_size))
                                )  # Limit page_size between 1-100

                                agents = await registry.list_agents()
                                public_agents = []

                                # Filter and prepare agents
                                for agent in agents:
                                    if agent.status == "alive":
                                        # Apply agent type filter if provided
                                        if (
                                            agent_type_filter
                                            and agent.agent_type != agent_type_filter
                                        ):
                                            continue

                                        public_agents.append(
                                            agent.dict(exclude_none=True)
                                        )

                                # Calculate pagination
                                total_agents = len(public_agents)
                                total_pages = (
                                    total_agents + page_size - 1
                                ) // page_size  # Ceiling division
                                start_index = (page - 1) * page_size
                                end_index = start_index + page_size
                                paginated_agents = public_agents[start_index:end_index]

                                discovery_message = {
                                    "type": "discovery_data",
                                    "timestamp": time.time(),
                                    "data": {
                                        "agents": paginated_agents,
                                        "pagination": {
                                            "current_page": page,
                                            "page_size": page_size,
                                            "total_agents": total_agents,
                                            "total_pages": total_pages,
                                            "has_next": page < total_pages,
                                            "has_previous": page > 1,
                                            "next_page": (
                                                page + 1 if page < total_pages else None
                                            ),
                                            "previous_page": (
                                                page - 1 if page > 1 else None
                                            ),
                                        },
                                        "filters": {"agent_type": agent_type_filter},
                                    },
                                }

                                await websocket.send_text(
                                    json.dumps(discovery_message, default=str)
                                )
                                logger.info(
                                    f"Sent discovery data to {connection_id}: page {page}/{total_pages}, {len(paginated_agents)} agents"
                                )

                            except Exception as e:
                                logger.error(f"Error getting discovery data: {e}")
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "type": "error",
                                            "message": "Failed to get discovery data",
                                        }
                                    )
                                )
                        else:
                            # Unknown message type
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "message": f"Unknown message type: {message_type}",
                                    }
                                )
                            )

                    except json.JSONDecodeError:
                        logger.warning(
                            f"Public WebSocket received invalid JSON from {connection_id}"
                        )
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "message": "Invalid JSON format",
                                }
                            )
                        )
                        continue

                except asyncio.TimeoutError:
                    # Send a ping to check if connection is still alive (like agent WebSocket)
                    try:
                        await websocket.send_text("ping")
                        logger.debug(f"Sent ping to {connection_id}")
                    except Exception:
                        logger.info(
                            f"Public connection {connection_id} appears dead, breaking loop"
                        )
                        break

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except WebSocketDisconnect:
                logger.info(f"Public WebSocket client {connection_id} disconnected")
                break
            except Exception as e:
                logger.error(f"Error in public WebSocket loop for {connection_id}: {e}")
                break

    except asyncio.TimeoutError:
        logger.warning(f"Public WebSocket connection timeout for {connection_id}")
        try:
            await websocket.close(code=1000, reason="Connection timeout")
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info(
            f"Public WebSocket client {connection_id} disconnected during setup"
        )
    except Exception as e:
        logger.error(f"Public WebSocket error for {connection_id}: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        # Cleanup: Remove from active connections
        if websocket in public_active_connections:
            public_active_connections.remove(websocket)
        logger.info(
            f"Public WebSocket connection closed for {connection_id}. Remaining connections: {len(public_active_connections)}"
        )


# ================================
# PUBLIC SYSTEM INFORMATION
# ================================


@router.get("/info")
async def get_public_system_info(_: dict = RequirePublic):
    """
    PUBLIC: Get basic system information for external developers

    Provides general information about the ARCP system for integration purposes.
    No sensitive information is exposed.

    **Returns**: Basic system information and API capabilities
    """
    try:
        return {
            "service": "ARCP (Agent Registry & Control Protocol)",
            "version": "2.0.3",
            "public_api": {
                "available": True,
                "endpoints": {
                    "discover": "/public/discover - Discover available agents",
                    "search": "/public/search - Search agents with semantic queries",
                    "agent_details": "/public/agent/{agent_id} - Get detailed agent information",
                    "connect": "/public/connect/{agent_id} - Request connection to an agent",
                },
                "features": [
                    "Agent discovery and browsing",
                    "Semantic agent search",
                    "Public agent profiles",
                    "User-agent connection facilitation",
                ],
            },
            "capabilities": {
                "vector_search": True,
                "real_time_updates": True,
                "agent_filtering": True,
                "pagination": True,
                "websocket_pagination": True,
            },
            "limits": {
                "discover_max_limit": 100,
                "search_max_limit": 50,
                "rate_limiting": "Applied per IP address",
            },
            "documentation": "https://arcp.0x001.tech/docs",
            "support": "https://github.com/0x00K1/ARCP/support",
        }

    except Exception as e:
        logger.error(f"Error getting public system info: {e}")
        return handle_exception_with_problem_details(
            logger, "Get public system information", e
        )


@router.get("/stats")
async def get_public_stats(
    registry: AgentRegistry = Depends(get_registry), _: dict = RequirePublic
):
    """
    PUBLIC: Get basic public statistics about the agent ecosystem

    Provides aggregate statistics for external developers and platforms.
    Individual agent details are not exposed.

    **Returns**: Public ecosystem statistics
    """
    try:
        # Get basic registry stats
        stats = await registry.get_stats()

        # Return only public-safe statistics
        public_stats = {
            "alive_agents": stats.get("alive_agents", 0),
            "total_agents": stats.get("total_agents", 0),
            "agent_types": len(stats.get("agent_types", {})),
            "system_status": "operational",
            "last_updated": datetime.now(timezone.utc).isoformat(),  # Dynamic timestamp
            "features": {
                "semantic_search": True,
                "real_time_discovery": True,
                "connection_facilitation": True,
            },
        }

        # Add agent type breakdown (without specific counts for privacy)
        agent_types = stats.get("agent_types", {})
        if agent_types:
            public_stats["available_types"] = list(agent_types.keys())

        logger.info(
            f"Public stats requested: {stats.get('alive_agents', 0)} agents available"
        )
        return public_stats

    except Exception as e:
        logger.error(f"Error getting public stats: {e}")
        return handle_exception_with_problem_details(logger, "Get public statistics", e)


@router.get("/agent_types")
async def get_allowed_agent_types(_: dict = RequirePublic):
    """PUBLIC: Return allowed agent types from server configuration."""
    try:
        types = config.get_allowed_agent_types()
        return {"allowed_agent_types": types}
    except Exception as e:
        logger.error(f"Error getting allowed agent types: {e}")
        return handle_exception_with_problem_details(
            logger, "Get allowed agent types", e
        )
