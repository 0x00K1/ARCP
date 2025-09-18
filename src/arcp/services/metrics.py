"""
Metrics service for ARCP.

This module provides a centralized interface for metrics collection and reporting,
including Prometheus metrics, agent performance metrics, and system monitoring.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Enum,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"

    # Mock classes for when prometheus_client is not available
    class Counter:
        def __init__(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Histogram:
        def __init__(self, *args, **kwargs):
            pass

        def time(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def observe(self, *args):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Gauge:
        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args):
            pass

        def inc(self, *args):
            pass

        def dec(self, *args):
            pass

        def labels(self, *args, **kwargs):
            return self

    class Info:
        def __init__(self, *args, **kwargs):
            pass

        def info(self, *args):
            pass

    class Enum:
        def __init__(self, *args, **kwargs):
            pass

        def state(self, *args):
            pass


try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from ..core.config import config
from .redis import get_redis_service

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for metrics collection and reporting."""

    def __init__(self):
        """Initialize the metrics service."""
        self._prometheus_available = PROMETHEUS_AVAILABLE
        self._psutil_available = PSUTIL_AVAILABLE
        self._redis_service = get_redis_service()

        # Redis keys for metrics caching
        self._cpu_cache_key = "arcp:metrics:cpu_baseline"
        self._memory_cache_key = "arcp:metrics:memory_baseline"
        self._network_cache_key = "arcp:metrics:network_baseline"
        self._disk_cache_key = "arcp:metrics:disk_baseline"

        # Network interface capacity for utilization calculation (Mbps)
        # Default to 1 Gbps, can be configured via environment
        self._interface_capacity_mbps = float(
            getattr(config, "NETWORK_INTERFACE_CAPACITY_MBPS", 1000)
        )

        # Cache TTL for metrics (seconds)
        self._metrics_cache_ttl = 300  # 5 minutes

        # In-memory fallback cache when Redis is unavailable
        self._memory_cache = {
            "cpu": None,
            "memory": None,
            "network": None,
            "disk": None,
        }

        # Initialize custom ARCP metrics
        self._init_custom_metrics()

        if not self._prometheus_available:
            logger.warning(
                "prometheus-client not available - Prometheus metrics unavailable"
            )

        if not self._psutil_available:
            logger.warning("psutil not available - system resource metrics unavailable")

    def _init_custom_metrics(self):
        """Initialize custom ARCP Prometheus metrics."""
        if not self._prometheus_available:
            # Create mock metrics if prometheus_client not available
            # Use the local mock classes
            mock_counter = type(
                "Counter",
                (),
                {
                    "__init__": lambda s, *a, **k: None,
                    "inc": lambda s, *a, **k: None,
                    "labels": lambda s, *a, **k: s,
                },
            )()
            mock_histogram = type(
                "Histogram",
                (),
                {
                    "__init__": lambda s, *a, **k: None,
                    "time": lambda s: s,
                    "__enter__": lambda s: s,
                    "__exit__": lambda s, *a: None,
                    "observe": lambda s, *a: None,
                    "labels": lambda s, *a, **k: s,
                },
            )()
            mock_gauge = type(
                "Gauge",
                (),
                {
                    "__init__": lambda s, *a, **k: None,
                    "set": lambda s, *a: None,
                    "inc": lambda s, *a: None,
                    "dec": lambda s, *a: None,
                    "labels": lambda s, *a, **k: s,
                },
            )()
            mock_info = type(
                "Info",
                (),
                {"__init__": lambda s, *a, **k: None, "info": lambda s, *a: None},
            )()
            mock_enum = type(
                "Enum",
                (),
                {"__init__": lambda s, *a, **k: None, "state": lambda s, *a: None},
            )()

            self.agent_registrations = mock_counter
            self.agent_unregistrations = mock_counter
            self.agent_heartbeats = mock_counter
            self.active_agents = mock_gauge
            self.request_duration = mock_histogram
            self.request_count = mock_counter
            self.redis_operations = mock_counter
            self.websocket_connections = mock_gauge
            self.vector_search_operations = mock_counter
            self.auth_attempts = mock_counter
            self.system_cpu_utilization = mock_gauge
            self.system_memory_utilization = mock_gauge
            self.system_disk_utilization = mock_gauge
            self.system_network_utilization = mock_gauge
            self.service_info = mock_info
            self.service_health_status = mock_enum
            return

        try:
            # Agent-related metrics
            self.agent_registrations = Counter(
                "arcp_agent_registrations_total",
                "Total number of agent registrations",
                ["status", "agent_type"],
            )

            self.agent_unregistrations = Counter(
                "arcp_agent_unregistrations_total",
                "Total number of agent unregistrations",
                ["status", "reason"],
            )

            self.agent_heartbeats = Counter(
                "arcp_agent_heartbeats_total",
                "Total number of agent heartbeats",
                ["status", "agent_id"],
            )

            self.active_agents = Gauge(
                "arcp_active_agents",
                "Number of currently active agents",
                ["agent_type"],
            )

            # Request metrics
            self.request_duration = Histogram(
                "arcp_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint", "status_code"],
                buckets=[
                    0.001,
                    0.005,
                    0.01,
                    0.025,
                    0.05,
                    0.1,
                    0.25,
                    0.5,
                    1.0,
                    2.5,
                    5.0,
                    10.0,
                ],
            )

            self.request_count = Counter(
                "arcp_requests_total",
                "Total number of HTTP requests",
                ["method", "endpoint", "status_code"],
            )

            # Storage metrics
            self.redis_operations = Counter(
                "arcp_redis_operations_total",
                "Total number of Redis operations",
                ["operation", "status"],
            )

            # WebSocket metrics
            self.websocket_connections = Gauge(
                "arcp_websocket_connections", "Number of active WebSocket connections"
            )

            # Vector search metrics
            self.vector_search_operations = Counter(
                "arcp_vector_search_operations_total",
                "Total number of vector search operations",
                ["status"],
            )

            # Authentication metrics
            self.auth_attempts = Counter(
                "arcp_auth_attempts_total",
                "Total number of authentication attempts",
                ["status", "auth_type"],
            )

            # System resource metrics (custom implementation)
            self.system_cpu_utilization = Gauge(
                "arcp_system_cpu_utilization_percent",
                "System CPU utilization percentage",
            )

            self.system_memory_utilization = Gauge(
                "arcp_system_memory_utilization_percent",
                "System memory utilization percentage",
            )

            self.system_disk_utilization = Gauge(
                "arcp_system_disk_utilization_percent",
                "System disk utilization percentage",
            )

            self.system_network_utilization = Gauge(
                "arcp_system_network_utilization_percent",
                "System network utilization percentage",
            )

            # Service information
            self.service_info = Info(
                "arcp_service", "Information about the ARCP service"
            )

            self.service_health_status = Enum(
                "arcp_service_health_status",
                "Current health status of the ARCP service",
                states=["healthy", "degraded", "unhealthy"],
            )

            # Set initial service information
            self.service_info.info(
                {
                    "version": config.SERVICE_VERSION,
                    "name": config.SERVICE_NAME,
                    "environment": getattr(config, "ENVIRONMENT", "unknown"),
                }
            )

            logger.info("Custom ARCP metrics initialized successfully")

        except ValueError as e:
            if "Duplicated timeseries" in str(e):
                logger.warning(
                    f"Metrics already registered, skipping initialization: {e}"
                )
                # Create mock metrics to prevent AttributeError
                mock_counter = type(
                    "Counter",
                    (),
                    {"inc": lambda s, *a, **k: None, "labels": lambda s, *a, **k: s},
                )()
                mock_histogram = type(
                    "Histogram",
                    (),
                    {
                        "time": lambda s: s,
                        "__enter__": lambda s: s,
                        "__exit__": lambda s, *a: None,
                        "observe": lambda s, *a: None,
                        "labels": lambda s, *a, **k: s,
                    },
                )()
                mock_gauge = type(
                    "Gauge",
                    (),
                    {
                        "set": lambda s, *a: None,
                        "inc": lambda s, *a: None,
                        "dec": lambda s, *a: None,
                        "labels": lambda s, *a, **k: s,
                    },
                )()
                mock_info = type("Info", (), {"info": lambda s, *a: None})()
                mock_enum = type("Enum", (), {"state": lambda s, *a: None})()

                self.agent_registrations = mock_counter
                self.agent_unregistrations = mock_counter
                self.agent_heartbeats = mock_counter
                self.active_agents = mock_gauge
                self.request_duration = mock_histogram
                self.request_count = mock_counter
                self.redis_operations = mock_counter
                self.websocket_connections = mock_gauge
                self.vector_search_operations = mock_counter
                self.auth_attempts = mock_counter
                self.system_cpu_utilization = mock_gauge
                self.system_memory_utilization = mock_gauge
                self.system_disk_utilization = mock_gauge
                self.system_network_utilization = mock_gauge
                self.service_info = mock_info
                self.service_health_status = mock_enum
            else:
                raise

    def is_prometheus_available(self) -> bool:
        """Check if Prometheus metrics are available."""
        return self._prometheus_available

    def is_psutil_available(self) -> bool:
        """Check if system resource metrics are available."""
        return self._psutil_available

    async def _calculate_cpu_utilization(self) -> float:
        """
        Calculate CPU utilization with Redis-cached smoothing over time.

        Returns:
            CPU utilization percentage (0-100)
        """
        if not self._psutil_available:
            return 0.0

        try:
            current_time = time.time()
            current_cpu = psutil.cpu_percent(interval=None)  # Non-blocking call

            # Try to get previous measurement from Redis or memory fallback
            previous_data = None
            redis_client = (
                self._redis_service.get_client() if self._redis_service else None
            )

            if redis_client:
                try:
                    cached_data = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: redis_client.get(self._cpu_cache_key)
                    )
                    if cached_data:
                        previous_data = json.loads(cached_data)
                except Exception as e:
                    logger.debug(f"Failed to get CPU cache from Redis: {e}")

            # Fallback to in-memory cache if Redis unavailable
            if previous_data is None and self._memory_cache["cpu"] is not None:
                previous_data = self._memory_cache["cpu"]

            # Calculate smoothed CPU if we have previous data
            cpu_utilization = current_cpu
            if previous_data:
                time_diff = current_time - previous_data["timestamp"]

                # Apply exponential smoothing if measurement is recent (within 60 seconds)
                if 0 < time_diff <= 60:
                    alpha = min(1.0, time_diff / 10.0)  # Smoothing factor based on time
                    cpu_utilization = (alpha * current_cpu) + (
                        (1 - alpha) * previous_data["cpu"]
                    )

            # Store current measurement in Redis and memory fallback
            current_data = {"timestamp": current_time, "cpu": cpu_utilization}

            # Store in Redis if available
            if redis_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.setex(
                            self._cpu_cache_key,
                            self._metrics_cache_ttl,
                            json.dumps(current_data),
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Failed to cache CPU data in Redis: {e}")

            # Always store in memory fallback
            self._memory_cache["cpu"] = current_data

            return round(cpu_utilization, 2)

        except Exception as e:
            logger.error(f"Error calculating CPU utilization: {e}")
            return 0.0

    async def _calculate_memory_utilization(self) -> float:
        """
        Calculate memory utilization with Redis-cached trend analysis.

        Returns:
            Memory utilization percentage (0-100)
        """
        if not self._psutil_available:
            return 0.0

        try:
            current_time = time.time()
            memory = psutil.virtual_memory()
            current_memory = memory.percent

            # Try to get previous measurements from Redis or memory fallback
            previous_data = None
            redis_client = (
                self._redis_service.get_client() if self._redis_service else None
            )

            if redis_client:
                try:
                    cached_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.get(self._memory_cache_key),
                    )
                    if cached_data:
                        previous_data = json.loads(cached_data)
                except Exception as e:
                    logger.debug(f"Failed to get memory cache from Redis: {e}")

            # Fallback to in-memory cache if Redis unavailable
            if previous_data is None and self._memory_cache["memory"] is not None:
                previous_data = self._memory_cache["memory"]

            # Calculate trend-adjusted memory if we have previous data
            memory_utilization = current_memory
            if previous_data:
                time_diff = current_time - previous_data["timestamp"]

                # Apply slight smoothing for memory to reduce noise
                if 0 < time_diff <= 120:  # Within 2 minutes
                    alpha = 0.7  # Higher alpha for less smoothing (memory changes are important)
                    memory_utilization = (alpha * current_memory) + (
                        (1 - alpha) * previous_data["memory"]
                    )

            # Store current measurement in Redis and memory fallback
            current_data = {
                "timestamp": current_time,
                "memory": memory_utilization,
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
            }

            # Store in Redis if available
            if redis_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.setex(
                            self._memory_cache_key,
                            self._metrics_cache_ttl,
                            json.dumps(current_data),
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Failed to cache memory data in Redis: {e}")

            # Always store in memory fallback
            self._memory_cache["memory"] = current_data

            return round(memory_utilization, 2)

        except Exception as e:
            logger.error(f"Error calculating memory utilization: {e}")
            return 0.0

    async def _calculate_network_utilization(self) -> float:
        """
        Calculate network utilization as a percentage of interface capacity.
        Uses Redis to store previous measurements for rate calculation.

        Returns:
            Network utilization percentage (0-100)
        """
        if not self._psutil_available:
            return 0.0

        try:
            current_time = time.time()

            # Get network I/O counters - try both aggregate and per-interface
            net_io = psutil.net_io_counters()
            current_bytes = 0

            if net_io is None:
                # Fallback: try per-interface counters (better for Windows)
                try:
                    net_io_per_nic = psutil.net_io_counters(pernic=True)
                    if net_io_per_nic:
                        # Sum active interfaces (skip loopback and VMware virtual adapters)
                        for (
                            interface_name,
                            interface_stats,
                        ) in net_io_per_nic.items():
                            # Skip virtual/loopback interfaces common on Windows
                            skip_interfaces = [
                                "loopback",
                                "vmware",
                                "virtualbox",
                                "hyper-v",
                                "teredo",
                                "isatap",
                                "local area connection",
                            ]

                            if any(
                                skip_name.lower() in interface_name.lower()
                                for skip_name in skip_interfaces
                            ):
                                continue

                            # Include active physical interfaces (Wi-Fi, Ethernet)
                            if (
                                interface_stats.bytes_sent > 0
                                or interface_stats.bytes_recv > 0
                            ):
                                current_bytes += (
                                    interface_stats.bytes_sent
                                    + interface_stats.bytes_recv
                                )
                                logger.debug(
                                    f"Network interface {interface_name}: {interface_stats.bytes_sent + interface_stats.bytes_recv} total bytes"
                                )
                except Exception as e:
                    logger.debug(f"Failed to get per-interface network stats: {e}")
                    return 0.0
            else:
                current_bytes = net_io.bytes_sent + net_io.bytes_recv

            if current_bytes == 0:
                logger.debug("No network activity detected")
                return 0.0

            # Try to get previous measurement from Redis or memory fallback
            previous_data = None
            redis_client = (
                self._redis_service.get_client() if self._redis_service else None
            )

            if redis_client:
                try:
                    cached_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.get(self._network_cache_key),
                    )
                    if cached_data:
                        previous_data = json.loads(cached_data)
                except Exception as e:
                    logger.debug(f"Failed to get network cache from Redis: {e}")

            # Fallback to in-memory cache if Redis unavailable
            if previous_data is None and self._memory_cache["network"] is not None:
                previous_data = self._memory_cache["network"]
                logger.debug("Using in-memory network cache fallback")

            # Calculate rate if we have previous data
            network_utilization = 0.0
            if previous_data:
                time_diff = current_time - previous_data["timestamp"]
                bytes_diff = current_bytes - previous_data["bytes"]

                if time_diff > 0 and bytes_diff >= 0:
                    # Calculate bytes per second
                    bytes_per_second = bytes_diff / time_diff

                    # Convert to Mbps (1 byte = 8 bits, 1 Mbps = 1,000,000 bits/s)
                    mbps = (bytes_per_second * 8) / 1_000_000

                    # Calculate utilization as percentage of configured interface capacity
                    network_utilization = min(
                        100.0, (mbps / self._interface_capacity_mbps) * 100
                    )

                    # Enhanced logging for debugging
                    logger.debug(
                        f"Network stats: {bytes_diff} bytes in {time_diff:.2f}s = {mbps:.4f} Mbps ({network_utilization:.2f}% of {self._interface_capacity_mbps} Mbps capacity)"
                    )
                else:
                    logger.debug(
                        f"Invalid network calculation: time_diff={time_diff}, bytes_diff={bytes_diff}"
                    )
            else:
                logger.debug("No previous network data available for rate calculation")

            # Store current measurement in Redis and memory fallback
            current_data = {"timestamp": current_time, "bytes": current_bytes}

            # Store in Redis if available
            if redis_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.setex(
                            self._network_cache_key,
                            self._metrics_cache_ttl,
                            json.dumps(current_data),
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Failed to cache network data in Redis: {e}")

            # Always store in memory fallback
            self._memory_cache["network"] = current_data

            return round(network_utilization, 2)

        except Exception as e:
            logger.error(f"Error calculating network utilization: {e}")
            return 0.0

    async def _calculate_disk_utilization(self) -> float:
        """
        Calculate disk utilization with Redis-cached I/O rate monitoring.

        Returns:
            Disk utilization percentage (0-100) based on space usage and I/O activity
        """
        if not self._psutil_available:
            return 0.0

        try:
            current_time = time.time()

            # Get disk usage (space)
            try:
                disk_usage = psutil.disk_usage("/")
                space_percent = disk_usage.percent
            except (OSError, FileNotFoundError):
                # Fallback for Windows - use C: drive
                try:
                    disk_usage = psutil.disk_usage("C:")
                    space_percent = disk_usage.percent
                except Exception:
                    space_percent = 0.0

            # Get disk I/O statistics
            try:
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    current_io_bytes = disk_io.read_bytes + disk_io.write_bytes
                    current_io_ops = disk_io.read_count + disk_io.write_count
                else:
                    current_io_bytes = 0
                    current_io_ops = 0
            except Exception:
                current_io_bytes = 0
                current_io_ops = 0

            # Try to get previous measurement from Redis or memory fallback
            previous_data = None
            redis_client = (
                self._redis_service.get_client() if self._redis_service else None
            )

            if redis_client:
                try:
                    cached_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.get(self._disk_cache_key),
                    )
                    if cached_data:
                        previous_data = json.loads(cached_data)
                except Exception as e:
                    logger.debug(f"Failed to get disk cache from Redis: {e}")

            # Fallback to in-memory cache if Redis unavailable
            if previous_data is None and self._memory_cache["disk"] is not None:
                previous_data = self._memory_cache["disk"]

            # Calculate I/O activity percentage
            io_activity_percent = 0.0
            if previous_data and current_io_bytes > 0:
                time_diff = current_time - previous_data["timestamp"]
                io_bytes_diff = current_io_bytes - previous_data.get("io_bytes", 0)
                io_ops_diff = current_io_ops - previous_data.get("io_ops", 0)

                if time_diff > 0 and io_bytes_diff >= 0:
                    # Calculate I/O rate (MB/s)
                    io_rate_mb_per_sec = (io_bytes_diff / time_diff) / (1024 * 1024)
                    ops_per_sec = io_ops_diff / time_diff

                    # Estimate I/O activity as percentage (assume 100 MB/s or 1000 IOPS = 100%)
                    io_rate_percent = min(100.0, (io_rate_mb_per_sec / 100.0) * 100)
                    ops_percent = min(100.0, (ops_per_sec / 1000.0) * 100)

                    # Take the higher of rate or ops as I/O activity
                    io_activity_percent = max(io_rate_percent, ops_percent)

            # Combine space usage (70%) and I/O activity (30%) for final utilization
            # Space usage is more important for storage utilization
            disk_utilization = (space_percent * 0.7) + (io_activity_percent * 0.3)

            # Store current measurement in Redis and memory fallback
            current_data = {
                "timestamp": current_time,
                "space_percent": space_percent,
                "io_bytes": current_io_bytes,
                "io_ops": current_io_ops,
                "io_activity": io_activity_percent,
                "free_gb": (
                    round(disk_usage.free / (1024**3), 2)
                    if "disk_usage" in locals()
                    else 0
                ),
                "used_gb": (
                    round(disk_usage.used / (1024**3), 2)
                    if "disk_usage" in locals()
                    else 0
                ),
            }

            # Store in Redis if available
            if redis_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: redis_client.setex(
                            self._disk_cache_key,
                            self._metrics_cache_ttl,
                            json.dumps(current_data),
                        ),
                    )
                except Exception as e:
                    logger.debug(f"Failed to cache disk data in Redis: {e}")

            # Always store in memory fallback
            self._memory_cache["disk"] = current_data

            return round(disk_utilization, 2)

        except Exception as e:
            logger.error(f"Error calculating disk utilization: {e}")
            return 0.0

    def get_prometheus_metrics(self) -> tuple[bytes, str]:
        """
        Get Prometheus metrics data.

        Returns:
            Tuple of (metrics_data, content_type)
        """
        if not self._prometheus_available:
            fallback = b"# prometheus-client not available\n"
            return fallback, "text/plain"

        try:
            data = generate_latest()
            return data, CONTENT_TYPE_LATEST
        except Exception as e:
            logger.error(f"Error generating Prometheus metrics: {e}")
            fallback = f"# metrics temporarily unavailable: {str(e)}\n".encode()
            return fallback, CONTENT_TYPE_LATEST

    async def get_resource_utilization(self) -> Dict[str, float]:
        """
        Get system resource utilization metrics.

        Returns:
            Dictionary containing CPU, memory, network, and storage metrics
        """
        if not self._psutil_available:
            return {"cpu": 0.0, "memory": 0.0, "network": 0.0, "storage": 0.0}

        try:
            # CPU usage (cached and smoothed)
            cpu_percent = await self._calculate_cpu_utilization()

            # Memory usage (cached and trend-adjusted)
            memory_percent = await self._calculate_memory_utilization()

            # Network utilization (properly calculated using Redis cache)
            network_percent = await self._calculate_network_utilization()

            # Disk utilization (space + I/O activity)
            disk_percent = await self._calculate_disk_utilization()

            # Update Prometheus gauges if available
            if self._prometheus_available:
                self.system_cpu_utilization.set(cpu_percent)
                self.system_memory_utilization.set(memory_percent)
                self.system_network_utilization.set(network_percent)
                self.system_disk_utilization.set(disk_percent)

            return {
                "cpu": round(cpu_percent, 2),
                "memory": round(memory_percent, 2),
                "network": round(network_percent, 2),
                "storage": round(disk_percent, 2),
            }

        except Exception as e:
            logger.error(f"Error getting resource utilization: {e}")
            return {"cpu": 0.0, "memory": 0.0, "network": 0.0, "storage": 0.0}

    def record_agent_registration(self, agent_type: str, status: str):
        """Record an agent registration event."""
        if self._prometheus_available:
            self.agent_registrations.labels(status=status, agent_type=agent_type).inc()

    def record_agent_unregistration(self, status: str, reason: str = "normal"):
        """Record an agent unregistration event."""
        if self._prometheus_available:
            self.agent_unregistrations.labels(status=status, reason=reason).inc()

    def record_agent_heartbeat(self, agent_id: str, status: str):
        """Record an agent heartbeat event."""
        if self._prometheus_available:
            self.agent_heartbeats.labels(status=status, agent_id=agent_id).inc()

    def update_active_agents_count(self, count: int, agent_type: str = "all"):
        """Update the count of active agents."""
        if self._prometheus_available:
            self.active_agents.labels(agent_type=agent_type).set(count)

    def record_http_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ):
        """Record an HTTP request with timing."""
        if self._prometheus_available:
            self.request_count.labels(
                method=method, endpoint=endpoint, status_code=str(status_code)
            ).inc()
            self.request_duration.labels(
                method=method, endpoint=endpoint, status_code=str(status_code)
            ).observe(duration)

    def record_redis_operation(self, operation: str, status: str):
        """Record a Redis operation."""
        if self._prometheus_available:
            self.redis_operations.labels(operation=operation, status=status).inc()

    def update_websocket_connections(self, count: int):
        """Update the count of WebSocket connections."""
        if self._prometheus_available:
            self.websocket_connections.set(count)

    def record_vector_search(self, status: str):
        """Record a vector search operation."""
        if self._prometheus_available:
            self.vector_search_operations.labels(status=status).inc()

    def record_auth_attempt(self, status: str, auth_type: str = "jwt"):
        """Record an authentication attempt."""
        if self._prometheus_available:
            self.auth_attempts.labels(status=status, auth_type=auth_type).inc()

    def update_service_health(self, status: str):
        """Update the service health status."""
        if self._prometheus_available and status in [
            "healthy",
            "degraded",
            "unhealthy",
        ]:
            self.service_health_status.state(status)

    def calculate_agent_metrics_summary(
        self, agent_metrics_list: List[Any]
    ) -> Dict[str, Any]:
        """
        Calculate summary metrics from a list of agent metrics.

        Args:
            agent_metrics_list: List of agent metrics objects

        Returns:
            Dictionary containing aggregated metrics
        """
        if not agent_metrics_list:
            return {
                "total_requests": 0,
                "avg_response_time": 0.0,
                "error_rate": 0.0,
                "agent_count": 0,
            }

        total_requests = 0
        total_response_time = 0.0
        total_errors = 0

        for metrics in agent_metrics_list:
            if hasattr(metrics, "dict"):
                metrics_dict = metrics.dict()
            else:
                metrics_dict = vars(metrics) if hasattr(metrics, "__dict__") else {}

            requests = metrics_dict.get("total_requests", 0) or 0
            response_time = (
                metrics_dict.get("avg_response_time", 0)
                or metrics_dict.get("average_response_time", 0)
                or 0
            )
            success_rate = metrics_dict.get("success_rate", 1.0) or 1.0

            total_requests += requests
            total_response_time += response_time * requests if requests > 0 else 0
            total_errors += requests * (1 - success_rate) if requests > 0 else 0

        # Calculate averages
        avg_response_time = (
            total_response_time / total_requests if total_requests > 0 else 0.0
        )
        error_rate = total_errors / total_requests if total_requests > 0 else 0.0

        return {
            "total_requests": total_requests,
            "avg_response_time": round(avg_response_time, 3),
            "error_rate": round(error_rate, 3),
            "agent_count": len(agent_metrics_list),
        }

    def get_prometheus_config(self) -> Dict[str, Any]:
        """Get Prometheus configuration."""
        try:
            return config.get_prometheus_config()
        except Exception:
            return {}

    def get_grafana_config(self) -> Dict[str, Any]:
        """Get Grafana configuration."""
        try:
            return config.get_grafana_config()
        except Exception:
            return {}

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the metrics service."""
        return {
            "prometheus_available": self._prometheus_available,
            "psutil_available": self._psutil_available,
            "prometheus_config": self.get_prometheus_config(),
            "grafana_config": self.get_grafana_config(),
        }


# Global metrics service instance - lazily initialized
_metrics_service_instance = None


def get_metrics_service() -> MetricsService:
    """Get the metrics service instance (singleton pattern)."""
    global _metrics_service_instance
    if _metrics_service_instance is None:
        _metrics_service_instance = MetricsService()
    return _metrics_service_instance


def reset_metrics_service():
    """Reset the metrics service instance (for testing)."""
    global _metrics_service_instance
    _metrics_service_instance = None


# For backward compatibility - create a module-level proxy
class _MetricsServiceProxy:
    """Proxy object that acts like the metrics service."""

    def __getattr__(self, name):
        return getattr(get_metrics_service(), name)

    def __call__(self):
        return get_metrics_service()


# This provides backward compatibility for direct access to metrics_service
metrics_service = _MetricsServiceProxy()
