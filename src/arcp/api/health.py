"""Health check endpoint"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends

from ..core.dependencies import get_registry
from ..core.registry import AgentRegistry
from ..services import get_openai_service
from ..services.metrics import get_metrics_service
from ..utils.api_protection import RequireAdmin, RequirePublic

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check(
    registry: AgentRegistry = Depends(get_registry), _: dict = RequirePublic
):
    """Comprehensive health check endpoint"""
    try:
        # Get registry statistics
        stats = await registry.get_stats()
        metrics_service = get_metrics_service()

        # Use storage adapter backend status for Redis availability
        storage = registry.storage
        redis_connected = await storage.is_backend_available()
        redis_status = "connected" if redis_connected else "error"

        # Check Azure OpenAI status
        openai_service = get_openai_service()
        ai_status = "available" if openai_service.is_available() else "unavailable"

        # Update service health metric
        service_health = "healthy"
        if redis_status == "error" or ai_status == "unavailable":
            service_health = "degraded"

        metrics_service.update_service_health(service_health)

        # Update active agents count
        metrics_service.update_active_agents_count(stats["alive_agents"])

        # Trigger resource utilization update
        try:
            await metrics_service.get_resource_utilization()
        except Exception as e:
            logger.debug(f"Failed to update resource metrics: {e}")

        return {
            "status": service_health,
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "uptime": "operational",
            "service": "ARCP Registry",
            "features": {
                "vector_search": ai_status == "available",
                "redis_storage": redis_status == "connected",
                "metrics_tracking": True,
                "jwt_authentication": True,
                "websocket_broadcasts": True,
            },
            "storage": {
                "redis": redis_status,
                "backup_storage": "available",  # In-memory backup is always available
            },
            "ai_services": {
                "azure_openai": ai_status,
                "embeddings": ai_status == "available",
            },
            "agents": {
                "total_registered": stats["total_agents"],
                "alive_agents": stats["alive_agents"],
                "dead_agents": stats["dead_agents"],
                "agent_types": stats["agent_types"],
                "embeddings_stored": stats["embeddings_available"],
            },
            "performance": {
                "redis_connected": redis_status == "connected",
                "ai_client_available": stats["ai_client_available"],
            },
        }

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "degraded",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "error": str(e),
            "message": "Health check encountered errors but service is still operational",
        }


@router.get("/health/detailed")
async def detailed_health_check(
    registry: AgentRegistry = Depends(get_registry), _: dict = RequireAdmin
):
    """Detailed health check endpoint with comprehensive system status"""
    try:
        # Get registry statistics
        stats = await registry.get_stats()

        # Determine storage backend availability via adapter
        storage = registry.storage
        redis_status = (
            "connected" if await storage.is_backend_available() else "disconnected"
        )

        # Check Azure OpenAI status
        openai_service = get_openai_service()
        ai_status = "available" if openai_service.is_available() else "unavailable"

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "service": "ARCP Registry",
            "uptime": "operational",
            "components": {
                "registry": {
                    "status": "healthy",
                    "agents_total": stats["total_agents"],
                    "agents_alive": stats["alive_agents"],
                },
                "storage": {"status": redis_status, "redis": redis_status},
                "ai_services": {
                    "status": ("healthy" if ai_status == "available" else "degraded"),
                    "azure_openai": ai_status,
                },
            },
            "detailed": {
                "database": {"status": "operational", "type": "memory+redis"},
                "storage": {
                    "redis": redis_status,
                    "backup_storage": "available",  # In-memory backup is always available
                },
                "ai_services": {
                    "azure_openai": ai_status,
                    "embeddings": ai_status == "available",
                    "vector_search": ai_status == "available",
                },
                "features": {
                    "agent_registration": True,
                    "heartbeat_monitoring": True,
                    "metrics_collection": True,
                    "websocket_broadcasts": True,
                    "jwt_authentication": True,
                },
                "agents": {
                    "total_registered": stats["total_agents"],
                    "alive_agents": stats["alive_agents"],
                    "dead_agents": stats["dead_agents"],
                    "agent_types": stats["agent_types"],
                    "embeddings_stored": stats["embeddings_available"],
                },
                "performance": {
                    "redis_connected": await storage.is_backend_available(),
                    "ai_client_available": stats["ai_client_available"],
                },
            },
        }

    except Exception as e:
        return {
            "status": "degraded",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "error": str(e),
            "message": "Detailed health check encountered errors but service is still operational",
            "detailed": {"error_details": str(e)},
        }


@router.get("/health/config")
async def health_config(
    registry: AgentRegistry = Depends(get_registry),  # kept for symmetry/future
    _: dict = RequireAdmin,
):
    """Report configuration presence and optional settings status.

    Returns a summary of required and optional configuration based on the
    centralized config validation helpers.
    """
    try:
        # Local import to avoid circulars
        from ..core.config import config  # type: ignore

        # Required config details
        required_missing = config.validate_required_config()

        # Optional config details
        optional_missing = config.validate_optional_config()

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "required_config": required_missing,
            "optional_config": optional_missing,
        }
    except Exception as e:
        logger.error(f"Config health error: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "error": str(e),
        }


@router.get("/health/redis")
async def health_redis(
    registry: AgentRegistry = Depends(get_registry), _: dict = RequireAdmin
):
    """Report Redis backend availability via storage adapter."""
    try:
        storage = registry.storage
        available = await storage.is_backend_available()
        return {
            "status": "healthy" if available else "unavailable",
            "redis": "connected" if available else "disconnected",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
        }
    except Exception as e:
        logger.error(f"Redis health error: {e}")
        return {
            "status": "error",
            "redis": "unknown",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "error": str(e),
        }


@router.get("/health/azure")
async def health_azure(
    _: dict = RequireAdmin,
):
    """Report Azure OpenAI availability and configuration status."""
    try:
        service = get_openai_service()
        status = service.get_status()
        return {
            "status": status.get("status", "unknown"),
            "details": status,
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
        }
    except Exception as e:
        logger.error(f"Azure health error: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "error": str(e),
        }
