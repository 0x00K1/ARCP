"""Dashboard WebSocket API for ARCP real-time monitoring.

All dashboard data now flows through WebSocket connections.
Provides real-time monitoring metrics, health status, agent status, alerts, and logs.
"""

import asyncio
import json
import logging
import time
import uuid as _uuid
import zoneinfo
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from ..core.config import config
from ..core.dependencies import get_registry
from ..core.registry import AgentRegistry
from ..core.storage_adapter import StorageAdapter
from ..models.dashboard import DashboardFrame, DashboardLogRequest
from ..services import get_metrics_service, get_openai_service
from ..utils.api_protection import RequireAdmin
from ..utils.sessions import get_token_payload

router = APIRouter()
logger = logging.getLogger(__name__)

# WebSocket connection management
dashboard_connections: Set[WebSocket] = set()
connection_lock = asyncio.Lock()

# Track paused connections for selective data broadcasting
paused_connections: Set[WebSocket] = set()
paused_lock = asyncio.Lock()

# Background task for broadcasting
broadcast_task: Optional[asyncio.Task] = None

try:
    LOG_BUFFER_MAXLEN = int(getattr(config, "DASHBOARD_LOG_BUFFER_MAXLEN", 10000))
    LOG_MESSAGE_MAXLEN = int(getattr(config, "DASHBOARD_LOG_MESSAGE_MAXLEN", 2048))
except Exception:
    LOG_BUFFER_MAXLEN = 10000
    LOG_MESSAGE_MAXLEN = 2048

log_buffer: deque = deque(maxlen=LOG_BUFFER_MAXLEN)  # Server cap: last N entries only
log_buffer_lock = asyncio.Lock()
alert_buffer: deque = deque(maxlen=LOG_BUFFER_MAXLEN)
alert_buffer_lock = asyncio.Lock()

# Persistent storage buckets (Redis with in-memory fallback)
LOGS_BUCKET = "dashboard:logs"
ALERTS_BUCKET = "dashboard:alerts"
SETTINGS_BUCKET = "dashboard:settings"
storage_adapter = StorageAdapter()
# Register a tiny internal fallback map for adapter, although we primarily
# rely on the module-level deque for fast in-process reads
storage_adapter.register_bucket(LOGS_BUCKET, {})
storage_adapter.register_bucket(ALERTS_BUCKET, {})
storage_adapter.register_bucket(SETTINGS_BUCKET, {})


async def _store_log_persistently(entry: Dict[str, Any]) -> None:
    """Persist a log entry to Redis (via StorageAdapter) and enforce caps.

    Keys are time-ordered using milliseconds epoch as prefix, so trimming
    can be done by sorting keys lexicographically.
    """
    try:
        epoch_ms = int(time.time() * 1000)
        # Use a short random suffix to avoid collisions at same ms
        key = f"{epoch_ms}:{_uuid.uuid4().hex[:6]}"
        await storage_adapter.hset(LOGS_BUCKET, key, entry)

        # Trim if we exceeded maxlen; operate at most 2x work (cheap for small caps)
        try:
            keys: List[str] = await storage_adapter.hkeys(LOGS_BUCKET)
            if len(keys) > LOG_BUFFER_MAXLEN:
                # Sort ascending by time (oldest first)
                keys_sorted = sorted(
                    keys,
                    key=lambda k: (
                        int(k.split(":", 1)[0])
                        if ":" in k and k.split(":", 1)[0].isdigit()
                        else 0
                    ),
                )
                to_delete = len(keys_sorted) - LOG_BUFFER_MAXLEN
                for k in keys_sorted[:to_delete]:
                    await storage_adapter.hdel(LOGS_BUCKET, k)
        except Exception:
            # Non-fatal if trimming fails
            pass
    except Exception:
        # Swallow persistence errors; in-memory buffer remains the source of truth
        logger.debug("Failed to persist dashboard log entry", exc_info=True)


async def _load_recent_logs_from_storage(limit: int) -> List[Dict[str, Any]]:
    """Load most-recent logs from storage, newest-first, up to limit."""
    try:
        keys: List[str] = await storage_adapter.hkeys(LOGS_BUCKET)
        if not keys:
            return []
        # Sort descending (newest first)
        keys_sorted = sorted(
            keys,
            key=lambda k: (
                int(k.split(":", 1)[0])
                if ":" in k and k.split(":", 1)[0].isdigit()
                else 0
            ),
            reverse=True,
        )
        selected = keys_sorted[: max(0, limit)]
        results: List[Dict[str, Any]] = []
        for k in selected:
            try:
                v = await storage_adapter.hget(LOGS_BUCKET, k)
                if isinstance(v, dict):
                    results.append(v)
                else:
                    # Attempt JSON parse if returned as string
                    try:
                        results.append(json.loads(v))
                    except Exception:
                        pass
            except Exception:
                continue
        return results
    except Exception:
        return []


async def broadcast_to_dashboard(frame: DashboardFrame):
    """Broadcast a frame to all connected dashboard clients, respecting pause state."""
    if not dashboard_connections:
        return

    frame_json = frame.json()
    disconnected = set()

    async with connection_lock:
        async with paused_lock:
            for ws in dashboard_connections.copy():
                try:
                    # Check if this connection is paused and skip non-agent data
                    if ws in paused_connections and frame.type not in [
                        "agents",
                        "logs",
                    ]:
                        continue  # Skip monitoring, health, and alerts for paused connections

                    if ws.client_state == WebSocketState.CONNECTED:
                        # Set a timeout for sending to prevent blocking
                        await asyncio.wait_for(
                            ws.send_text(frame_json),
                            timeout=float(getattr(config, "WEBSOCKET_TIMEOUT", 10)),
                        )
                    else:
                        disconnected.add(ws)
                except (
                    WebSocketDisconnect,
                    ConnectionError,
                    asyncio.TimeoutError,
                ):
                    disconnected.add(ws)
                except Exception as e:
                    logger.warning(f"Error broadcasting to WebSocket client: {e}")
                    disconnected.add(ws)

        # Remove disconnected clients
        for ws in disconnected:
            dashboard_connections.discard(ws)
            paused_connections.discard(ws)  # Also remove from paused set
            logger.debug(
                f"Removed disconnected WebSocket client, {len(dashboard_connections)} remaining"
            )


async def dashboard_producer(registry: AgentRegistry):
    """Background task that produces dashboard frames at regular intervals."""
    logger.info("Dashboard WebSocket producer started")

    # Add initial system log
    await add_log_entry(
        "INFO",
        "Dashboard producer task started - real-time monitoring active",
        "system",
    )

    while True:
        try:
            # Use configured timezone for consistency, with Windows-safe fallback
            try:
                if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                    tz = zoneinfo.ZoneInfo(config.TIMEZONE)
                else:
                    tz = timezone.utc
            except Exception:
                tz = (
                    timezone.utc
                )  # Fallback to UTC if timezone is invalid or not supported on platform
            current_time = datetime.now(tz).isoformat()

            # Generate monitoring frame
            monitoring_data = await get_monitoring_data(registry)
            monitoring_frame = DashboardFrame(
                type="monitoring", timestamp=current_time, data=monitoring_data
            )
            await broadcast_to_dashboard(monitoring_frame)

            # Generate health frame
            health_data = await get_health_data(registry)
            health_frame = DashboardFrame(
                type="health", timestamp=current_time, data=health_data
            )
            await broadcast_to_dashboard(health_frame)

            # Generate agents frame
            agents_data = await get_agents_data(registry)
            agents_frame = DashboardFrame(
                type="agents", timestamp=current_time, data=agents_data
            )
            await broadcast_to_dashboard(agents_frame)

            # Generate logs frame
            logs_data = await get_logs_data(registry)
            if logs_data:
                logs_frame = DashboardFrame(
                    type="logs", timestamp=current_time, data=logs_data
                )
                await broadcast_to_dashboard(logs_frame)

            # Check for alerts
            alert_data = await check_for_alerts(registry, monitoring_data, health_data)
            if alert_data:
                # Persist individual alerts
                for a in alert_data.get("alerts", []):
                    await add_alert_entry(a)
                alert_frame = DashboardFrame(
                    type="alert", timestamp=current_time, data=alert_data
                )
                await broadcast_to_dashboard(alert_frame)

            # Wait for next interval
            await asyncio.sleep(
                getattr(
                    config,
                    "DASHBOARD_WS_INTERVAL",
                    getattr(config, "WEBSOCKET_INTERVAL", 10),
                )
            )

        except asyncio.CancelledError:
            logger.info("Dashboard producer task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in dashboard producer: {e}")
            await asyncio.sleep(5)  # Wait before retrying


async def get_resource_utilization() -> Dict[str, float]:
    """Get system resource utilization metrics."""
    metrics_service = get_metrics_service()
    return await metrics_service.get_resource_utilization()


async def get_monitoring_data(registry: AgentRegistry) -> Dict[str, Any]:
    """Get monitoring metrics for dashboard."""
    try:
        agents = await registry.list_agents()

        if not agents:
            return {
                "total_requests": 0,
                "avg_response_time": 0,
                "error_rate": 0,
                "agent_metrics": [],
                "agent_count": 0,
                "resource_utilization": await get_resource_utilization(),
            }

        # Collect metrics for all agents
        metrics = []
        for agent in agents:
            if agent:
                try:
                    agent_metrics = await registry.get_agent_metrics(agent.agent_id)
                    if agent_metrics:
                        # Validate that we have meaningful metrics, not just defaults
                        metrics_dict = (
                            agent_metrics.dict()
                            if hasattr(agent_metrics, "dict")
                            else vars(agent_metrics)
                        )

                        # Only include metrics (not all zeros)
                        has_data = (
                            metrics_dict.get("total_requests", 0) > 0
                            or metrics_dict.get("requests_processed", 0) > 0
                            or metrics_dict.get("avg_response_time", 0) > 0
                            or metrics_dict.get("average_response_time", 0) > 0
                            or metrics_dict.get("error_rate", 0) > 0
                        )

                        if has_data:
                            metrics.append(agent_metrics)
                        else:
                            # Agent exists but has no activity yet - include with zero values
                            # (agent is registered but inactive)
                            metrics.append(agent_metrics)

                except Exception as e:
                    logger.warning(
                        f"Failed to get metrics for agent {agent.agent_id}: {e}"
                    )
                    continue

        # Calculate aggregated metrics
        total_requests = (
            sum(getattr(m, "total_requests", 0) for m in metrics) if metrics else 0
        )
        avg_response_time = (
            sum(getattr(m, "avg_response_time", 0) for m in metrics) / len(metrics)
            if metrics
            else 0
        )
        error_rate = (
            sum(getattr(m, "error_rate", 0) for m in metrics) / len(metrics)
            if metrics
            else 0
        )

        return {
            "total_requests": total_requests,
            "avg_response_time": round(avg_response_time, 2),
            "error_rate": round(error_rate, 3),
            "agent_metrics": [
                m.dict() if hasattr(m, "dict") else vars(m) for m in metrics
            ],
            "agent_count": len(agents),
            "resource_utilization": await get_resource_utilization(),
        }

    except Exception as e:
        logger.error(f"Error getting monitoring data: {e}")
        return {
            "total_requests": 0,
            "avg_response_time": 0,
            "error_rate": 0,
            "agent_metrics": [],
            "agent_count": 0,
            "resource_utilization": {
                "cpu": 0.0,
                "memory": 0.0,
                "network": 0.0,
                "storage": 0.0,
            },
        }


async def get_health_data(registry: AgentRegistry) -> Dict[str, Any]:
    """Get health status for dashboard."""
    try:
        health_data = {"status": "healthy", "components": {}}

        # Check storage health
        try:
            registry_stats = await registry.get_stats()
            redis_connected = registry_stats.get("redis_connected", False)

            health_data["components"]["storage"] = {
                "redis": "connected" if redis_connected else "error",
                "status": "healthy" if redis_connected else "degraded",
            }
        except Exception as e:
            logger.warning(f"Storage health check failed: {e}")
            health_data["components"]["storage"] = {
                "redis": "error",
                "status": "degraded",
            }

        # Check AI services
        try:
            openai_service = get_openai_service()
            openai_status = openai_service.get_status()

            if openai_status["status"] == "available":
                health_data["components"]["ai_services"] = {
                    "azure_openai": "available",
                    "status": "healthy",
                }
            elif openai_status["status"] == "not_configured":
                health_data["components"]["ai_services"] = {
                    "azure_openai": "not_configured",
                    "status": "not_configured",
                }
            else:
                health_data["components"]["ai_services"] = {
                    "azure_openai": openai_status["status"],
                    "status": "degraded",
                }
        except Exception as e:
            logger.warning(f"AI services health check failed: {e}")
            health_data["components"]["ai_services"] = {
                "azure_openai": "error",
                "status": "degraded",
            }

        # Check agent connectivity
        try:
            stats = await registry.get_stats()
            total_agents = stats.get("total_agents", 0)
            active_agents = stats.get("alive_agents", 0)

            if total_agents > 0:
                connectivity_ratio = active_agents / total_agents

                # Logic: consider both ratio and absolute numbers
                if total_agents == 1:
                    # Special case: single agent system
                    agent_status = "healthy" if active_agents == 1 else "degraded"
                elif total_agents <= 3:
                    # Small agent pool (2-3 agents): be more lenient
                    if active_agents >= total_agents:
                        agent_status = "healthy"
                    elif active_agents >= max(
                        1, total_agents - 1
                    ):  # Allow 1 agent down
                        agent_status = "degraded"
                    else:
                        agent_status = "critical"
                else:
                    # Larger agent pool (4+ agents): use percentage-based logic
                    if connectivity_ratio >= 0.75:  # Relaxed from 0.8 to 0.75
                        agent_status = "healthy"
                    elif connectivity_ratio >= 0.4:  # Relaxed from 0.5 to 0.4
                        agent_status = "degraded"
                    else:
                        agent_status = "critical"

                # Additional check: if we have at least 1 agent working, don't go to critical
                # unless we have a very large pool and most are down
                if (
                    agent_status == "critical"
                    and active_agents > 0
                    and total_agents < 10
                ):
                    agent_status = "degraded"

            else:
                agent_status = "no_agents"

            health_data["components"]["agents"] = {
                "total": total_agents,
                "active": active_agents,
                "status": agent_status,
                "connectivity_ratio": (
                    round(connectivity_ratio, 3) if total_agents > 0 else 0
                ),
            }
        except Exception as e:
            logger.warning(f"Agent connectivity check failed: {e}")
            health_data["components"]["agents"] = {"status": "error"}

        # Determine overall health with improved logic
        component_statuses = [
            comp.get("status", "unknown") for comp in health_data["components"].values()
        ]

        # Health determination logic
        critical_components = [
            status for status in component_statuses if status in ["error", "critical"]
        ]
        degraded_components = [
            status for status in component_statuses if status == "degraded"
        ]
        # healthy_components = [status for status in component_statuses if status == "healthy"]

        # Core system health (storage) has higher priority
        storage_status = (
            health_data["components"].get("storage", {}).get("status", "unknown")
        )
        agent_status = (
            health_data["components"].get("agents", {}).get("status", "unknown")
        )
        ai_status = (
            health_data["components"].get("ai_services", {}).get("status", "unknown")
        )

        # Critical conditions: core storage issues or complete agent failure
        if storage_status in ["error", "critical"]:
            health_data["status"] = "unhealthy"
            health_data["reason"] = "Storage system failure"
        elif (
            agent_status == "critical"
            and health_data["components"].get("agents", {}).get("active", 0) == 0
        ):
            health_data["status"] = "unhealthy"
            health_data["reason"] = "No active agents available"
        elif len(critical_components) >= 2:  # Multiple critical failures
            health_data["status"] = "unhealthy"
            health_data["reason"] = "Multiple critical component failures"
        # Degraded conditions: some issues but system can still function
        elif storage_status == "degraded" or agent_status in [
            "degraded",
            "critical",
        ]:
            # Only mark as degraded if core functionality is impacted
            if agent_status == "critical" or storage_status == "degraded":
                health_data["status"] = "degraded"
                if agent_status == "critical":
                    health_data["reason"] = "Significant agent connectivity issues"
                else:
                    health_data["reason"] = "Storage system degraded"
            else:
                # Agent degraded but not critical - system can still function well
                health_data["status"] = "healthy"
                health_data["reason"] = "System operational with minor issues"
        elif ai_status == "degraded" and len(degraded_components) == 1:
            # AI is degraded
            health_data["status"] = "healthy"
            health_data["reason"] = "Core system healthy, AI services have minor issues"
        elif len(degraded_components) >= 2:
            health_data["status"] = "degraded"
            health_data["reason"] = "Multiple components experiencing issues"
        else:
            health_data["status"] = "healthy"
            health_data["reason"] = "All systems operational"

        return health_data

    except Exception as e:
        logger.error(f"Error getting health data: {e}")
        return {"status": "error", "components": {}}


async def get_agents_data(registry: AgentRegistry) -> Dict[str, Any]:
    """Get agent data for dashboard WebSocket."""
    try:
        # Fetch all agents similar to the agents.py WebSocket
        agents = await registry.list_agents()

        if not agents:
            return {
                "agents": [],
                "total_count": 0,
                "active_count": 0,
                "agent_types": {},
                "status_summary": {},
            }

        # Convert agents to dict format for JSON serialization
        agents_data = []
        agent_types = {}
        status_summary = {"alive": 0, "dead": 0}

        for agent in agents:
            try:
                # Convert agent to dictionary, similar to agents.py WebSocket
                agent_dict = agent.dict(exclude_none=True)

                # Add metrics if available
                try:
                    metrics = await registry.get_agent_metrics(agent.agent_id)
                    if metrics:
                        # Ensure metrics can be JSON serialized
                        if hasattr(metrics, "dict"):
                            agent_dict["metrics"] = metrics.dict()
                        elif hasattr(metrics, "__dict__"):
                            # Convert to dict and filter out internal attributes
                            metrics_dict = {
                                k: v
                                for k, v in vars(metrics).items()
                                if not k.startswith("_")
                            }
                            agent_dict["metrics"] = metrics_dict
                        else:
                            agent_dict["metrics"] = str(metrics)
                except Exception as metrics_error:
                    logger.debug(
                        f"No metrics available for agent {agent.agent_id}: {metrics_error}"
                    )
                    agent_dict["metrics"] = None

                agents_data.append(agent_dict)

                # Count agent types
                agent_type = agent.agent_type or "unknown"
                agent_types[agent_type] = agent_types.get(agent_type, 0) + 1

                # Count status - use the agent's existing status field
                # The agent object should already have the correct status
                agent_status = getattr(agent, "status", "dead")
                if agent_status not in status_summary:
                    status_summary[agent_status] = 0
                status_summary[agent_status] += 1

            except Exception as agent_error:
                logger.warning(
                    f"Error processing agent {agent.agent_id}: {agent_error}"
                )
                continue

        return {
            "agents": agents_data,
            "total_count": len(agents),
            "active_count": status_summary.get("alive", 0),  # Use .get() for safety
            "agent_types": agent_types,
            "status_summary": status_summary,
        }

    except Exception as e:
        logger.error(f"Error getting agents data: {e}")
        return {
            "agents": [],
            "total_count": 0,
            "active_count": 0,
            "agent_types": {},
            "status_summary": {},
        }


async def get_logs_data(registry: AgentRegistry) -> Optional[Dict[str, Any]]:
    """Get recent log entries for dashboard."""
    try:
        # Read from in-memory deque first for speed
        async with log_buffer_lock:
            logs_mem = list(reversed(log_buffer))

        # Determine cap for return using buffer size only
        max_return = LOG_BUFFER_MAXLEN

        logs_list = logs_mem[:max_return]

        # If in-memory is empty (process restart) try to hydrate from storage
        if not logs_list:
            hydrated = await _load_recent_logs_from_storage(max_return)
            logs_list = hydrated
            # Warm the in-memory buffer so subsequent refreshes keep logs
            if hydrated:
                async with log_buffer_lock:
                    for entry in reversed(hydrated):  # push oldest first
                        if len(log_buffer) >= LOG_BUFFER_MAXLEN:
                            break
                        log_buffer.append(entry)

        # If still nothing, return None so caller can skip
        if not logs_list:
            return None

        # Use configured timezone for consistency, with Windows-safe fallback
        try:
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
                timestamp = datetime.now(tz).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
        except Exception:
            # Fallback to UTC if timezone is invalid or not supported on platform
            timestamp = datetime.now(timezone.utc).isoformat()

        return {
            "logs": logs_list,
            "count": len(logs_list),
            "last_updated": timestamp,
        }

    except Exception as e:
        logger.error(f"Error getting logs data: {e}")
        return None


async def add_log_entry(level: str, message: str, source: str = "system", **kwargs):
    """Add a log entry to the dashboard log buffer."""
    try:
        # Enforce server-side message size cap to prevent abuse
        if not isinstance(message, str):
            try:
                message = str(message)
            except Exception:
                message = "<non-string message>"
        if len(message) > LOG_MESSAGE_MAXLEN:
            message = message[: LOG_MESSAGE_MAXLEN - 3] + "..."
        # Use configured timezone for log timestamps
        try:
            # Check if timezone is configured and valid
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
                timestamp = datetime.now(tz).isoformat()
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
        except Exception:
            # Fallback to UTC if timezone is invalid or not supported on platform
            timestamp = datetime.now(timezone.utc).isoformat()

        log_entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message,
            "source": source,
            **kwargs,
        }

        async with log_buffer_lock:
            log_buffer.append(log_entry)
            # deque(maxlen=...) enforces max size; no further action needed
        # Persist outside the lock to avoid blocking readers
        await _store_log_persistently(log_entry)

    except Exception as e:
        logger.warning(f"Failed to add log entry to dashboard buffer: {e}")


async def handle_pause_monitoring(websocket: WebSocket):
    """Handle pause monitoring request from client."""
    async with paused_lock:
        paused_connections.add(websocket)
        logger.info(
            f"Dashboard monitoring paused. {len(paused_connections)} paused connections"
        )
        await add_log_entry("WARN", "Dashboard monitoring paused", "dashboard")


async def handle_resume_monitoring(websocket: WebSocket):
    """Handle resume monitoring request from client."""
    async with paused_lock:
        paused_connections.discard(websocket)
        logger.info(
            f"Dashboard monitoring resumed. {len(paused_connections)} paused connections"
        )
        await add_log_entry("INFO", "Dashboard monitoring resumed", "dashboard")

    # Send current data immediately when resuming
    try:
        # Use configured timezone for consistency
        try:
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
            else:
                tz = timezone.utc
        except Exception:
            tz = timezone.utc

        current_time = datetime.now(tz).isoformat()
        registry = get_registry()

        # Send current monitoring data
        monitoring_data = await get_monitoring_data(registry)
        monitoring_frame = DashboardFrame(
            type="monitoring", timestamp=current_time, data=monitoring_data
        )
        await websocket.send_text(monitoring_frame.json())

        # Send current health data
        health_data = await get_health_data(registry)
        health_frame = DashboardFrame(
            type="health", timestamp=current_time, data=health_data
        )
        await websocket.send_text(health_frame.json())

        logger.info("Sent current monitoring and health data to resumed client")

    except Exception as e:
        logger.error(f"Error sending data to resumed client: {e}")


async def handle_refresh_request(websocket: WebSocket):
    """Handle manual refresh request from client - send fresh data immediately."""
    try:
        # Use configured timezone for consistency
        try:
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
            else:
                tz = timezone.utc
        except Exception:
            tz = timezone.utc

        current_time = datetime.now(tz).isoformat()
        registry = get_registry()

        logger.info("Processing manual refresh request - sending fresh data")
        await add_log_entry("INFO", "Manual refresh requested", "dashboard")

        # Send fresh monitoring data
        monitoring_data = await get_monitoring_data(registry)
        monitoring_frame = DashboardFrame(
            type="monitoring", timestamp=current_time, data=monitoring_data
        )
        await websocket.send_text(monitoring_frame.json())

        # Send fresh health data
        health_data = await get_health_data(registry)
        health_frame = DashboardFrame(
            type="health", timestamp=current_time, data=health_data
        )
        await websocket.send_text(health_frame.json())

        # Send fresh agents data
        agents_data = await get_agents_data(registry)
        agents_frame = DashboardFrame(
            type="agents", timestamp=current_time, data=agents_data
        )
        await websocket.send_text(agents_frame.json())

        # Send fresh logs data
        logs_data = await get_logs_data(registry)
        if logs_data:
            logs_frame = DashboardFrame(
                type="logs", timestamp=current_time, data=logs_data
            )
            await websocket.send_text(logs_frame.json())

        # Check for fresh alerts
        alert_data = await check_for_alerts(registry, monitoring_data, health_data)
        if alert_data:
            alert_frame = DashboardFrame(
                type="alert", timestamp=current_time, data=alert_data
            )
            await websocket.send_text(alert_frame.json())

        # Send acknowledgment
        ack_frame = DashboardFrame(
            type="refresh_ack",
            timestamp=current_time,
            data={"status": "completed", "message": "Fresh data sent"},
        )
        await websocket.send_text(ack_frame.json())

        logger.info("Manual refresh completed - sent all fresh data to client")

    except Exception as e:
        logger.error(f"Error processing refresh request: {e}")
        # Send error acknowledgment
        try:
            error_frame = DashboardFrame(
                type="refresh_ack",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "status": "error",
                    "message": f"Refresh failed: {str(e)}",
                },
            )
            await websocket.send_text(error_frame.json())
        except Exception:
            pass


async def handle_agents_request(websocket: WebSocket):
    """Handle immediate agents data request."""
    try:
        # Use configured timezone for consistency
        try:
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
            else:
                tz = timezone.utc
        except Exception:
            tz = timezone.utc

        current_time = datetime.now(tz).isoformat()
        registry = get_registry()

        logger.info("Processing immediate agents data request.")

        # Send fresh agents data
        agents_data = await get_agents_data(registry)
        agents_frame = DashboardFrame(
            type="agents", timestamp=current_time, data=agents_data
        )
        await websocket.send_text(agents_frame.json())
        logger.info(f"Sent {agents_data.get('total_count', 0)} agents to client.")

        # Send acknowledgment
        ack_frame = DashboardFrame(
            type="agents_ack",
            timestamp=current_time,
            data={"status": "completed", "message": "Agents data sent"},
        )
        await websocket.send_text(ack_frame.json())
        logger.info("Sent agents data acknowledgment to client.")

    except Exception as e:
        logger.error(f"Error processing immediate agents data request: {e}")
        # Send error acknowledgment
        try:
            error_frame = DashboardFrame(
                type="agents_ack",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "status": "error",
                    "message": f"Failed to send agents data: {str(e)}",
                },
            )
            await websocket.send_text(error_frame.json())
        except Exception:
            pass


async def handle_dashboard_log(msg_data: Dict[str, Any]):
    """Handle dashboard log messages from frontend."""
    try:
        # Extract and validate log data using Pydantic model
        log_data = msg_data.get("data", {})
        try:
            req = DashboardLogRequest(**log_data)
        except Exception as validation_error:
            logger.warning(f"Invalid dashboard log payload: {validation_error}")
            return

        frontend_ts = req.timestamp

        # Add the frontend log to our backend log buffer
        await add_log_entry(
            req.level, req.message, "dashboard", frontend_timestamp=frontend_ts
        )

        logger.debug(
            f"Received dashboard log from frontend: [{req.level}] {req.message}"
        )

        # Immediately broadcast updated logs to all connected dashboard clients
        # so the sender and other viewers see the new entry without waiting
        try:
            # Use configured timezone for consistency
            try:
                if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                    tz = zoneinfo.ZoneInfo(config.TIMEZONE)
                else:
                    tz = timezone.utc
            except Exception:
                tz = timezone.utc

            current_time = datetime.now(tz).isoformat()
            registry = get_registry()
            logs_data = await get_logs_data(registry)
            if logs_data:
                logs_frame = DashboardFrame(
                    type="logs", timestamp=current_time, data=logs_data
                )
                await broadcast_to_dashboard(logs_frame)
        except Exception as broadcast_error:
            logger.warning(
                f"Failed to broadcast updated logs after dashboard_log: {broadcast_error}"
            )

    except Exception as e:
        logger.warning(f"Error processing dashboard log message: {e}")


async def handle_dashboard_alert(msg_data: Dict[str, Any]):
    """Handle dashboard alert messages from frontend (persist only)."""
    try:
        data = msg_data.get("data") or {}
        # Accept either a single alert or a list
        alerts: List[Dict[str, Any]] = []
        if isinstance(data, dict) and ("message" in data or "title" in data):
            alerts = [data]
        elif isinstance(data, dict) and isinstance(data.get("alerts"), list):
            alerts = data.get("alerts")  # type: ignore

        for a in alerts:
            try:
                await add_alert_entry(a)
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Error processing dashboard alert message: {e}")


async def handle_clear_logs(websocket: WebSocket):
    """Handle clear logs request from frontend."""
    try:
        # Clear the backend log buffer
        async with log_buffer_lock:
            log_buffer.clear()
            logger.info("Dashboard log buffer cleared by frontend request")

        # Add a log entry to indicate logs were cleared
        await add_log_entry("WARN", "Dashboard logs cleared", "dashboard")

        # Send acknowledgment back to the client
        ack_frame = DashboardFrame(
            type="clear_logs_ack",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "status": "completed",
                "message": "Backend logs cleared successfully",
            },
        )
        await websocket.send_text(ack_frame.json())

        logger.info("Sent clear logs acknowledgment to frontend")

    except Exception as e:
        logger.error(f"Error processing clear logs request: {e}")
        # Send error acknowledgment
        try:
            error_frame = DashboardFrame(
                type="clear_logs_ack",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "status": "error",
                    "message": f"Failed to clear backend logs: {str(e)}",
                },
            )
            await websocket.send_text(error_frame.json())
        except Exception:
            pass


async def handle_clear_alerts(websocket: WebSocket):
    """Handle clear alerts request from frontend."""
    try:
        # Clear the backend alerts buffer
        async with alert_buffer_lock:
            alert_buffer.clear()
            logger.info("Dashboard alerts buffer cleared by frontend request")

        # Clear persisted alerts in storage
        try:
            keys: List[str] = await storage_adapter.hkeys(ALERTS_BUCKET)
            if keys:
                for k in keys:
                    try:
                        await storage_adapter.hdel(ALERTS_BUCKET, k)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Failed to clear persisted alerts: {e}")

        # Add a log entry to indicate alerts were cleared
        await add_log_entry("WARN", "Dashboard alerts cleared", "dashboard")

        # Send acknowledgment back to the client
        ack_frame = DashboardFrame(
            type="clear_alerts_ack",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "status": "completed",
                "message": "Backend alerts cleared successfully",
            },
        )
        await websocket.send_text(ack_frame.json())

        logger.info("Sent clear alerts acknowledgment to frontend")

    except Exception as e:
        logger.error(f"Error processing clear alerts request: {e}")
        # Send error acknowledgment
        try:
            error_frame = DashboardFrame(
                type="clear_alerts_ack",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "status": "error",
                    "message": f"Failed to clear backend alerts: {str(e)}",
                },
            )
            await websocket.send_text(error_frame.json())
        except Exception:
            pass


async def check_for_alerts(
    registry: AgentRegistry,
    monitoring_data: Dict[str, Any],
    health_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Check for alert conditions and return alert data if any."""
    alerts = []

    # Alert deduplication - prevent spam of same alerts
    if not hasattr(check_for_alerts, "_recent_alerts"):
        check_for_alerts._recent_alerts = {}

    def should_send_alert(alert_key: str, alert_severity: str) -> bool:
        """Determine if an alert should be sent based on deduplication rules."""
        current_time = time.time()

        # Critical alerts: resend every 5 minutes (300 seconds)
        # Warning alerts: resend every 15 minutes (900 seconds)
        # Info alerts: send only once per hour (3600 seconds)
        cooldown_periods = {
            "critical": 300,  # 5 minutes
            "warning": 900,  # 15 minutes
            "info": 3600,  # 1 hour
        }

        cooldown = cooldown_periods.get(alert_severity, 900)  # Default 15 min

        # Check if we've sent this alert recently
        if alert_key in check_for_alerts._recent_alerts:
            last_sent = check_for_alerts._recent_alerts[alert_key]
            if current_time - last_sent < cooldown:
                return False

        # Update the last sent time
        check_for_alerts._recent_alerts[alert_key] = current_time

        # Clean up old entries (older than 1 hour)
        keys_to_remove = [
            key
            for key, timestamp in check_for_alerts._recent_alerts.items()
            if current_time - timestamp > 3600
        ]
        for key in keys_to_remove:
            del check_for_alerts._recent_alerts[key]

        return True

    # Get component statuses for context
    agent_status = health_data.get("components", {}).get("agents", {})
    storage_status = health_data.get("components", {}).get("storage", {})
    ai_status = health_data.get("components", {}).get("ai_services", {})

    # Check monitoring thresholds
    avg_response_time = monitoring_data.get("avg_response_time", 0)
    error_rate = monitoring_data.get("error_rate", 0)
    agent_count = monitoring_data.get("agent_count", 0)

    # Performance alerts - only if we have agents to measure
    if agent_count > 0:
        if avg_response_time > 2000:  # 2 seconds - critical
            alert_key = f"performance_critical_{int(avg_response_time/500)*500}"  # Group by 500ms ranges
            if should_send_alert(alert_key, "critical"):
                alerts.append(
                    {
                        "severity": "critical",
                        "message": f"Very high response time: {avg_response_time:.0f}ms (threshold: 2000ms)",
                        "type": "performance",
                        "details": {
                            "response_time": avg_response_time,
                            "threshold": 2000,
                        },
                    }
                )
                # Log critical performance issue
                await add_log_entry(
                    "CRIT",
                    f"Performance alert: Average response time {avg_response_time:.0f}ms exceeds 2000ms threshold",
                    "monitoring",
                )
        elif avg_response_time > 1500:  # 1.5 seconds - warning before critical
            alert_key = f"performance_warning_{int(avg_response_time/200)*200}"  # Group by 200ms ranges
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High response time: {avg_response_time:.0f}ms (approaching critical threshold: 2000ms)",
                        "type": "performance",
                        "details": {
                            "response_time": avg_response_time,
                            "threshold": 1500,
                        },
                    }
                )
        elif avg_response_time > 1000:  # 1 second - info/early warning
            alert_key = f"performance_info_{int(avg_response_time/100)*100}"  # Group by 100ms ranges
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated response time: {avg_response_time:.0f}ms (monitor closely)",
                        "type": "performance",
                        "details": {
                            "response_time": avg_response_time,
                            "threshold": 1000,
                        },
                    }
                )

    # Error rate alerts - only if we have meaningful traffic
    total_requests = monitoring_data.get("total_requests", 0)
    if total_requests > 10:  # Only alert on error rate if we have some traffic
        if error_rate > 0.2:  # 20% - critical
            alert_key = (
                f"error_rate_critical_{int(error_rate*100/5)*5}"  # Group by 5% ranges
            )
            if should_send_alert(alert_key, "critical"):
                alerts.append(
                    {
                        "severity": "critical",
                        "message": f"Very high error rate: {error_rate*100:.1f}% (threshold: 20%)",
                        "type": "error_rate",
                        "details": {
                            "error_rate": error_rate,
                            "threshold": 0.2,
                        },
                    }
                )
        elif error_rate > 0.15:  # 15% - warning before critical
            alert_key = (
                f"error_rate_warning_{int(error_rate*100/2)*2}"  # Group by 2% ranges
            )
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High error rate: {error_rate*100:.1f}% (approaching critical threshold: 20%)",
                        "type": "error_rate",
                        "details": {
                            "error_rate": error_rate,
                            "threshold": 0.15,
                        },
                    }
                )
        elif error_rate > 0.1:  # 10% - info/early warning
            alert_key = f"error_rate_info_{int(error_rate*100)}"  # Group by 1% ranges
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated error rate: {error_rate*100:.1f}% (monitor closely)",
                        "type": "error_rate",
                        "details": {
                            "error_rate": error_rate,
                            "threshold": 0.1,
                        },
                    }
                )
        elif error_rate > 0.05:  # 5% - very early warning
            alert_key = f"error_rate_baseline_{int(error_rate*100)}"
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Minor error rate increase: {error_rate*100:.1f}% (baseline monitoring)",
                        "type": "error_rate",
                        "details": {
                            "error_rate": error_rate,
                            "threshold": 0.05,
                        },
                    }
                )

    # Agent connectivity alerts with context and warning levels
    if agent_status:
        total_agents = agent_status.get("total", 0)
        active_agents = agent_status.get("active", 0)
        connectivity_ratio = agent_status.get("connectivity_ratio", 0)
        status = agent_status.get("status", "unknown")

        if status == "critical":
            if active_agents == 0:
                alert_key = "agent_connectivity_no_agents"
                if should_send_alert(alert_key, "critical"):
                    alerts.append(
                        {
                            "severity": "critical",
                            "message": f"No agents are active (0/{total_agents})",
                            "type": "agent_connectivity",
                            "details": {
                                "total_agents": total_agents,
                                "active_agents": active_agents,
                            },
                        }
                    )
                    # Log critical agent connectivity issue
                    await add_log_entry(
                        "CRIT",
                        f"Alert: No agents are active (0/{total_agents} registered agents)",
                        "agents",
                    )
            else:
                alert_key = f"agent_connectivity_critical_{int(connectivity_ratio*100/10)*10}"  # Group by 10% ranges
                if should_send_alert(alert_key, "critical"):
                    alerts.append(
                        {
                            "severity": "critical",
                            "message": f"Critical agent connectivity: {active_agents}/{total_agents} agents active ({connectivity_ratio*100:.1f}%)",
                            "type": "agent_connectivity",
                            "details": {
                                "total_agents": total_agents,
                                "active_agents": active_agents,
                                "ratio": connectivity_ratio,
                            },
                        }
                    )
        elif (
            status == "degraded" and total_agents > 1
        ):  # Don't alert for single agent going down
            # Add different warning levels based on severity of degradation
            if connectivity_ratio < 0.5:  # Less than 50% - warning approaching critical
                alert_key = (
                    f"agent_connectivity_warning_{int(connectivity_ratio*100/10)*10}"
                )
                if should_send_alert(alert_key, "warning"):
                    alerts.append(
                        {
                            "severity": "warning",
                            "message": f"Significant agent connectivity issues: {active_agents}/{total_agents} agents active ({connectivity_ratio*100:.1f}%) - approaching critical",
                            "type": "agent_connectivity",
                            "details": {
                                "total_agents": total_agents,
                                "active_agents": active_agents,
                                "ratio": connectivity_ratio,
                            },
                        }
                    )
            else:  # 50-75% - info level early warning
                alert_key = (
                    f"agent_connectivity_info_{int(connectivity_ratio*100/10)*10}"
                )
                if should_send_alert(alert_key, "info"):
                    alerts.append(
                        {
                            "severity": "info",
                            "message": f"Reduced agent capacity: {active_agents}/{total_agents} agents active ({connectivity_ratio*100:.1f}%)",
                            "type": "agent_connectivity",
                            "details": {
                                "total_agents": total_agents,
                                "active_agents": active_agents,
                                "ratio": connectivity_ratio,
                            },
                        }
                    )
        elif status == "no_agents":
            alert_key = "agent_connectivity_no_agents_registered"
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": "No agents registered in the system",
                        "type": "agent_connectivity",
                        "details": {"total_agents": 0, "active_agents": 0},
                    }
                )
        # Add early warning for healthy but not perfect connectivity
        elif (
            status == "healthy" and total_agents > 3 and connectivity_ratio < 0.9
        ):  # Less than 90% but still healthy
            alert_key = f"agent_connectivity_notice_{int(connectivity_ratio*100/5)*5}"  # Group by 5% ranges
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Minor agent connectivity notice: {active_agents}/{total_agents} agents active ({connectivity_ratio*100:.1f}%) - system healthy",
                        "type": "agent_connectivity",
                        "details": {
                            "total_agents": total_agents,
                            "active_agents": active_agents,
                            "ratio": connectivity_ratio,
                        },
                    }
                )

    # Storage alerts - critical for system operation
    storage_redis_status = storage_status.get("redis")
    storage_overall_status = storage_status.get("status")

    if storage_redis_status == "error":
        alert_key = "storage_redis_error"
        if should_send_alert(alert_key, "critical"):
            alerts.append(
                {
                    "severity": "critical",
                    "message": "Redis storage connection failed - system functionality impacted",
                    "type": "storage",
                    "details": {"component": "redis", "status": "error"},
                }
            )
            # Log critical storage failure
            await add_log_entry(
                "CRIT",
                "Storage alert: Redis connection failed - system functionality impacted",
                "storage",
            )
    elif storage_overall_status == "degraded":
        alert_key = "storage_redis_degraded"
        if should_send_alert(alert_key, "warning"):
            alerts.append(
                {
                    "severity": "warning",
                    "message": "Redis storage connection degraded - monitoring required",
                    "type": "storage",
                    "details": {"component": "redis", "status": "degraded"},
                }
            )
    elif storage_redis_status == "connected" and storage_overall_status == "healthy":
        pass

    # AI services alerts - only if there are actual errors, not configuration issues
    if ai_status.get("status") == "degraded":
        alert_key = "ai_services_degraded"
        if should_send_alert(alert_key, "info"):
            alerts.append(
                {
                    "severity": "info",  # Reduced severity - AI is often optional
                    "message": "AI services experiencing issues",
                    "type": "ai_services",
                    "details": {
                        "azure_openai": ai_status.get("azure_openai", "unknown")
                    },
                }
            )

    # System-wide health alerts - only for truly critical situations
    overall_status = health_data.get("status")
    overall_reason = health_data.get("reason", "")

    if overall_status == "unhealthy":
        alert_key = (
            f"system_health_unhealthy_{hash(overall_reason) % 1000}"  # Group by reason
        )
        if should_send_alert(alert_key, "critical"):
            alerts.append(
                {
                    "severity": "critical",
                    "message": f"System health critical: {overall_reason}",
                    "type": "system_health",
                    "details": {
                        "status": overall_status,
                        "reason": overall_reason,
                    },
                }
            )
    # Don't create alerts for "degraded" system status - component-specific alerts are sufficient

    # Resource utilization alerts
    resource_utilization = monitoring_data.get("resource_utilization", {})
    if resource_utilization:
        cpu = resource_utilization.get("cpu", 0)
        memory = resource_utilization.get("memory", 0)
        network = resource_utilization.get("network", 0)
        storage = resource_utilization.get("storage", 0)

        # CPU utilization alerts
        if cpu > 90:  # Critical - very high CPU
            alert_key = f"cpu_critical_{int(cpu/5)*5}"  # Group by 5% ranges
            if should_send_alert(alert_key, "critical"):
                alerts.append(
                    {
                        "severity": "critical",
                        "message": f"Critical CPU usage: {cpu}% (threshold: 90%)",
                        "type": "resource_cpu",
                        "details": {"cpu_percent": cpu, "threshold": 90},
                    }
                )
                await add_log_entry(
                    "CRIT",
                    f"Resource alert: CPU usage {cpu}% exceeds 90% threshold",
                    "monitoring",
                )
        elif cpu > 80:  # Warning - high CPU
            alert_key = f"cpu_warning_{int(cpu/5)*5}"
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High CPU usage: {cpu}% (approaching critical threshold: 90%)",
                        "type": "resource_cpu",
                        "details": {"cpu_percent": cpu, "threshold": 80},
                    }
                )
        elif cpu > 70:  # Info - elevated CPU
            alert_key = f"cpu_info_{int(cpu/5)*5}"
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated CPU usage: {cpu}% (monitor closely)",
                        "type": "resource_cpu",
                        "details": {"cpu_percent": cpu, "threshold": 70},
                    }
                )

        # Memory utilization alerts
        if memory > 95:  # Critical - very high memory
            alert_key = f"memory_critical_{int(memory/5)*5}"
            if should_send_alert(alert_key, "critical"):
                alerts.append(
                    {
                        "severity": "critical",
                        "message": f"Critical memory usage: {memory}% (threshold: 95%)",
                        "type": "resource_memory",
                        "details": {"memory_percent": memory, "threshold": 95},
                    }
                )
                await add_log_entry(
                    "CRIT",
                    f"Resource alert: Memory usage {memory}% exceeds 95% threshold",
                    "monitoring",
                )
        elif memory > 85:  # Warning - high memory
            alert_key = f"memory_warning_{int(memory/5)*5}"
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High memory usage: {memory}% (approaching critical threshold: 95%)",
                        "type": "resource_memory",
                        "details": {"memory_percent": memory, "threshold": 85},
                    }
                )
        elif memory > 75:  # Info - elevated memory
            alert_key = f"memory_info_{int(memory/5)*5}"
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated memory usage: {memory}% (monitor closely)",
                        "type": "resource_memory",
                        "details": {"memory_percent": memory, "threshold": 75},
                    }
                )

        # Storage utilization alerts
        if storage > 95:  # Critical - very high storage
            alert_key = f"storage_critical_{int(storage/5)*5}"
            if should_send_alert(alert_key, "critical"):
                alerts.append(
                    {
                        "severity": "critical",
                        "message": f"Critical disk usage: {storage}% (threshold: 95%)",
                        "type": "resource_storage",
                        "details": {
                            "storage_percent": storage,
                            "threshold": 95,
                        },
                    }
                )
                await add_log_entry(
                    "CRIT",
                    f"Resource alert: Disk usage {storage}% exceeds 95% threshold",
                    "monitoring",
                )
        elif storage > 85:  # Warning - high storage
            alert_key = f"storage_warning_{int(storage/5)*5}"
            if should_send_alert(alert_key, "warning"):
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High disk usage: {storage}% (approaching critical threshold: 95%)",
                        "type": "resource_storage",
                        "details": {
                            "storage_percent": storage,
                            "threshold": 85,
                        },
                    }
                )
        elif storage > 80:  # Info - elevated storage
            alert_key = f"storage_info_{int(storage/5)*5}"
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated disk usage: {storage}% (monitor closely)",
                        "type": "resource_storage",
                        "details": {
                            "storage_percent": storage,
                            "threshold": 80,
                        },
                    }
                )

        # Network utilization alerts (only if network monitoring is meaningful)
        if network > 80:  # Critical - very high network
            alert_key = f"network_critical_{int(network/10)*10}"  # Group by 10% ranges
            if should_send_alert(
                alert_key, "warning"
            ):  # Network alerts are usually warnings, not critical
                alerts.append(
                    {
                        "severity": "warning",
                        "message": f"High network usage: {network:.1f}% (monitor for bottlenecks)",
                        "type": "resource_network",
                        "details": {
                            "network_percent": network,
                            "threshold": 80,
                        },
                    }
                )
        elif network > 60:  # Info - elevated network
            alert_key = f"network_info_{int(network/10)*10}"
            if should_send_alert(alert_key, "info"):
                alerts.append(
                    {
                        "severity": "info",
                        "message": f"Elevated network usage: {network:.1f}% (monitor traffic patterns)",
                        "type": "resource_network",
                        "details": {
                            "network_percent": network,
                            "threshold": 60,
                        },
                    }
                )

    return {"alerts": alerts} if alerts else None


async def _store_alert_persistently(entry: Dict[str, Any]) -> None:
    try:
        epoch_ms = int(time.time() * 1000)
        key = f"{epoch_ms}:{_uuid.uuid4().hex[:6]}"
        await storage_adapter.hset(ALERTS_BUCKET, key, entry)
        try:
            keys: List[str] = await storage_adapter.hkeys(ALERTS_BUCKET)
            if len(keys) > LOG_BUFFER_MAXLEN:
                keys_sorted = sorted(
                    keys,
                    key=lambda k: (
                        int(k.split(":", 1)[0])
                        if ":" in k and k.split(":", 1)[0].isdigit()
                        else 0
                    ),
                )
                to_delete = len(keys_sorted) - LOG_BUFFER_MAXLEN
                for k in keys_sorted[:to_delete]:
                    await storage_adapter.hdel(ALERTS_BUCKET, k)
        except Exception:
            pass
    except Exception:
        logger.debug("Failed to persist dashboard alert entry", exc_info=True)


async def _load_recent_alerts_from_storage(limit: int) -> List[Dict[str, Any]]:
    try:
        keys: List[str] = await storage_adapter.hkeys(ALERTS_BUCKET)
        if not keys:
            return []
        keys_sorted = sorted(
            keys,
            key=lambda k: (
                int(k.split(":", 1)[0])
                if ":" in k and k.split(":", 1)[0].isdigit()
                else 0
            ),
            reverse=True,
        )
        selected = keys_sorted[: max(0, limit)]
        results: List[Dict[str, Any]] = []
        for k in selected:
            try:
                v = await storage_adapter.hget(ALERTS_BUCKET, k)
                if isinstance(v, dict):
                    results.append(v)
                else:
                    try:
                        results.append(json.loads(v))
                    except Exception:
                        pass
            except Exception:
                continue
        return results
    except Exception:
        return []


async def add_alert_entry(alert: Dict[str, Any]) -> None:
    """Normalize and store a single alert entry in memory and Redis."""
    try:
        # Normalize basic fields
        entry = {
            "id": alert.get("id"),
            "title": alert.get("title")
            or (str(alert.get("type", "")).replace("_", " ").capitalize() or "Alert"),
            "message": alert.get("message") or "",
            "severity": (alert.get("severity") or alert.get("type") or "info").lower(),
            "type": (alert.get("type") or "general").lower(),
            "timestamp": alert.get("timestamp")
            or datetime.now(timezone.utc).isoformat(),
        }
        async with alert_buffer_lock:
            alert_buffer.append(entry)
        await _store_alert_persistently(entry)
    except Exception as e:
        logger.debug(f"Failed to add alert entry: {e}")


@router.websocket("/ws")
async def dashboard_socket(websocket: WebSocket):
    """WebSocket endpoint for dashboard real-time data."""

    # Enforce WebSocket connection cap (dashboard-specific)
    if len(dashboard_connections) >= int(
        getattr(
            config,
            "DASHBOARD_WS_MAX_CONNECTIONS",
            getattr(config, "WEBSOCKET_MAX_CONNECTIONS", 5),
        )
    ):
        await websocket.close(code=1013, reason="WebSocket capacity reached")
        return
    # Accept connection first
    await asyncio.wait_for(
        websocket.accept(),
        timeout=float(
            getattr(
                config,
                "DASHBOARD_WS_TIMEOUT",
                getattr(config, "WEBSOCKET_TIMEOUT", 10),
            )
        ),
    )
    logger.info("Dashboard WebSocket connection established")

    try:
        # Read the first client message for authentication
        first = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=float(
                getattr(
                    config,
                    "DASHBOARD_WS_TIMEOUT",
                    getattr(config, "WEBSOCKET_TIMEOUT", 10),
                )
            ),
        )
        msg = json.loads(first)

        if msg.get("type") != "auth":
            await websocket.close(code=4001, reason="Auth frame required")
            return

        token = msg.get("token")

        logger.info(f"WebSocket auth - token present: {bool(token)}")

        if not token:
            logger.warning("WebSocket connection rejected: No authentication token")
            await websocket.close(code=4001, reason="Authentication token required")
            return

        # Verify JWT + admin role using existing get_token_payload(token)
        payload = get_token_payload(token)
        logger.info(f"WebSocket auth - payload: {payload}")

        if not payload:
            logger.warning("WebSocket connection rejected: Invalid token payload")
            await websocket.close(code=4001, reason="Invalid token")
            return

        if payload.get("role") != "admin":
            logger.warning(
                f"WebSocket connection rejected: Role '{payload.get('role')}' is not admin"
            )
            await websocket.close(code=4003, reason="Admin role required")
            return

        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Note: PIN validation is handled at session/API level, not WebSocket level
        # JWT token validation is sufficient for WebSocket authentication

        # Add connection to active set
        async with connection_lock:
            dashboard_connections.add(websocket)
            logger.info(
                f"Added dashboard WebSocket connection, {len(dashboard_connections)} total connections"
            )

            # Add log entry for new connection
            await add_log_entry(
                "INFO",
                f"New dashboard connection established ({len(dashboard_connections)} total)",
                "dashboard",
            )

        # Note: broadcast task is now started globally in FastAPI lifespan

        # Send immediate frames
        # Use configured timezone for consistency, with Windows-safe fallback
        try:
            if hasattr(config, "TIMEZONE") and config.TIMEZONE:
                tz = zoneinfo.ZoneInfo(config.TIMEZONE)
            else:
                tz = timezone.utc
        except Exception:
            tz = (
                timezone.utc
            )  # Fallback to UTC if timezone is invalid or not supported on platform
        current_time = datetime.now(tz).isoformat()
        registry = get_registry()

        # Send initial monitoring data
        logger.info("Sending initial monitoring data...")
        try:
            monitoring_data = await get_monitoring_data(registry)
            logger.info(f"Got monitoring data: {len(str(monitoring_data))} chars")
            monitoring_frame = DashboardFrame(
                type="monitoring", timestamp=current_time, data=monitoring_data
            )
            await websocket.send_text(monitoring_frame.json())
            logger.info("Sent monitoring frame successfully")
        except Exception as e:
            logger.error(f"Error sending monitoring data: {e}")
            raise

        # Send initial health data
        logger.info("Sending initial health data...")
        try:
            health_data = await get_health_data(registry)
            logger.info(f"Got health data: {len(str(health_data))} chars")
            health_frame = DashboardFrame(
                type="health", timestamp=current_time, data=health_data
            )
            await websocket.send_text(health_frame.json())
            logger.info("Sent health frame successfully")
        except Exception as e:
            logger.error(f"Error sending health data: {e}")
            raise

        # Send initial agents data
        logger.info("Sending initial agents data...")
        try:
            agents_data = await get_agents_data(registry)
            logger.info(f"Got agents data: {agents_data.get('total_count', 0)} agents")
            agents_frame = DashboardFrame(
                type="agents", timestamp=current_time, data=agents_data
            )
            await websocket.send_text(agents_frame.json())
            logger.info("Sent agents frame successfully")
        except Exception as e:
            logger.error(f"Error sending agents data: {e}")
            raise

        # Send initial logs data
        logger.info("Sending initial logs data...")
        try:
            # Add some initial log entries if buffer is empty
            async with log_buffer_lock:
                if len(log_buffer) == 0:
                    await add_log_entry(
                        "INFO",
                        "Dashboard WebSocket connection established",
                        "dashboard",
                    )
                    await add_log_entry(
                        "INFO",
                        f"ARCP system initialized with {len(dashboard_connections)} dashboard connections",
                        "system",
                    )
                    await add_log_entry(
                        "INFO",
                        "Real-time monitoring and alerting system started",
                        "monitoring",
                    )

            logs_data = await get_logs_data(registry)
            if logs_data:
                logs_frame = DashboardFrame(
                    type="logs", timestamp=current_time, data=logs_data
                )
                await websocket.send_text(logs_frame.json())
                logger.info(f"Sent logs data: {logs_data.get('count', 0)} log entries")
        except Exception as e:
            logger.error(f"Error sending logs data: {e}")
            # Don't raise - logs are not critical for dashboard functionality

        # Send initial recent alerts from storage (hydration)
        try:
            recent_alerts = await _load_recent_alerts_from_storage(LOG_BUFFER_MAXLEN)
            if recent_alerts:
                # Warm in-memory buffer for future use
                async with alert_buffer_lock:
                    for entry in reversed(recent_alerts):
                        if len(alert_buffer) >= LOG_BUFFER_MAXLEN:
                            break
                        alert_buffer.append(entry)
                alerts_frame = DashboardFrame(
                    type="alert",
                    timestamp=current_time,
                    data={"alerts": recent_alerts},
                )
                await websocket.send_text(alerts_frame.json())
                logger.info(f"Sent initial alerts: {len(recent_alerts)}")
        except Exception as e:
            logger.warning(f"Error sending initial alerts: {e}")

        # Keep connection alive and handle messages from client
        # Determine a receive timeout that is more tolerant than the ping interval
        try:
            ping_interval_s = float(
                getattr(
                    config,
                    "DASHBOARD_WS_PING_INTERVAL",
                    getattr(config, "WEBSOCKET_PING_INTERVAL", 30),
                )
            )
            recv_timeout_s = max(60.0, ping_interval_s * 2.0)
        except Exception:
            ping_interval_s = 30.0

        while True:
            try:
                # Wait for messages from client (e.g., ping, pause, resume, etc...)
                message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=recv_timeout_s
                )

                # Handle ping/pong messages (plain text)
                if message == "ping":
                    await websocket.send_text("pong")
                    logger.debug("Responded to ping from dashboard client")
                    continue

                if message == "pong":
                    # Client responded to our ping - connection is alive
                    logger.debug("Received pong from dashboard client (keepalive)")
                    continue

                # Handle JSON messages
                try:
                    msg_data = json.loads(message)
                    msg_type = msg_data.get("type")

                    if msg_type == "pause_monitoring":
                        await handle_pause_monitoring(websocket)
                        # Send acknowledgment
                        ack_frame = DashboardFrame(
                            type="pause_ack",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            data={"status": "paused"},
                        )
                        await websocket.send_text(ack_frame.json())

                    elif msg_type == "resume_monitoring":
                        await handle_resume_monitoring(websocket)
                        # Send acknowledgment
                        ack_frame = DashboardFrame(
                            type="resume_ack",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            data={"status": "resumed"},
                        )
                        await websocket.send_text(ack_frame.json())

                    elif msg_type == "refresh_request":
                        await handle_refresh_request(websocket)

                    elif msg_type == "agents_request":
                        await handle_agents_request(websocket)

                    elif msg_type == "dashboard_log":
                        # Handle dashboard log messages from frontend
                        await handle_dashboard_log(msg_data)

                    elif msg_type == "dashboard_alert":
                        # Handle dashboard alert messages from frontend
                        await handle_dashboard_alert(msg_data)

                    elif msg_type == "clear_logs":
                        # Handle clear logs request from frontend
                        await handle_clear_logs(websocket)

                    elif msg_type == "clear_alerts":
                        # Handle clear alerts request from frontend
                        await handle_clear_alerts(websocket)

                    else:
                        logger.warning(f"Unknown message type received: {msg_type}")

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message received: {message}")

            except asyncio.TimeoutError:
                # No message received within timeout; proactively ping client to keep-alive
                try:
                    await websocket.send_text("ping")
                    logger.debug("Sent keepalive ping to dashboard client")
                except WebSocketDisconnect:
                    logger.debug("Dashboard client disconnected during keepalive ping")
                    break
                except Exception as ping_err:
                    logger.info(f"WebSocket keepalive ping failed: {ping_err}")
                    break
                # Continue waiting for next message without closing the connection
                continue
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"Error in WebSocket message handling: {e}")
                break

    except WebSocketDisconnect:
        logger.info("Dashboard WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
        try:
            await websocket.close(code=4000, reason="Internal server error")
        except Exception:
            pass
    finally:
        # Remove connection from active set and paused set
        async with connection_lock:
            async with paused_lock:
                dashboard_connections.discard(websocket)
                paused_connections.discard(websocket)
                logger.info(
                    f"Removed dashboard WebSocket connection, {len(dashboard_connections)} remaining"
                )

                # Add log entry for disconnection
                await add_log_entry(
                    "INFO",
                    f"Dashboard connection disconnected ({len(dashboard_connections)} remaining)",
                    "dashboard",
                )


@router.get("/config")
async def get_config(
    _: dict = RequireAdmin,
    tz: Optional[str] = Query(None, description="Override timezone for preview only"),
):
    """Get server timezone configuration for consistent timestamp formatting."""
    # Note: `tz` is for client preview only; it doesn't mutate server config
    return {
        "timezone": tz or config.TIMEZONE,
        # Convert seconds to ms for clients
        "ws_ping_interval_ms": int(
            getattr(
                config,
                "DASHBOARD_WS_PING_INTERVAL",
                getattr(config, "WEBSOCKET_PING_INTERVAL", 30),
            )
            * 1000
        ),
        "log_buffer_maxlen": LOG_BUFFER_MAXLEN,
        "log_message_maxlen": LOG_MESSAGE_MAXLEN,
        "ui": await storage_adapter.hget(SETTINGS_BUCKET, "ui") or {},
    }


@router.post("/config")
async def update_config(
    payload: Dict[str, Any],
    _: dict = RequireAdmin,
):
    """Persist admin dashboard UI settings server-side.

    Expected payload example:
      { "ui": { "enableAutoRefresh": true, "refreshInterval": 60, "maxLogEntries": 500 } }
    """
    try:
        ui = payload.get("ui", {})
        if not isinstance(ui, dict):
            return {"status": "error", "message": "Invalid payload"}
        # Optionally clamp values server-side to safe ranges
        try:
            if "maxLogEntries" in ui:
                m = int(ui["maxLogEntries"])  # type: ignore
                ui["maxLogEntries"] = max(10, min(m, LOG_BUFFER_MAXLEN))
        except Exception:
            ui.pop("maxLogEntries", None)
        await storage_adapter.hset(SETTINGS_BUCKET, "ui", ui)
        return {"status": "ok", "ui": ui}
    except Exception as e:
        logger.warning(f"Failed to persist dashboard settings: {e}")
        return {"status": "error", "message": "Persistence failed"}
