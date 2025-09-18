"""
ARCP Client Library - Comprehensive Python Client for ARCP (Agent Registry & Control Protocol)

This module provides a complete client interface for interacting with ARCP servers,
enabling external applications to register agents, discover services, perform semantic
searches, and manage agent lifecycles.

Features:
- Agent registration and management
- Semantic vector search
- Real-time WebSocket communication
- Authentication and session management
- Public API access for discovery
- Comprehensive error handling and retry logic
- Full async/await support

Example Usage:
    # Basic client usage
    client = ARCPClient("https://arcp.example.com")

    # Agent registration
    agent = await client.register_agent(
        agent_id="my-agent",
        name="My Agent",
        agent_type="analysis",
        endpoint="https://my-agent.com",
        capabilities=["data-analysis", "reporting"],
        context_brief="Performs data analysis and generates reports",
        agent_key="your-registration-key"
    )

    # Agent discovery
    agents = await client.discover_agents(agent_type="analysis")

    # Semantic search
    results = await client.search_agents("find agents that can analyze financial data")

    # WebSocket for real-time updates
    async with client.websocket() as ws:
        async for message in ws:
            print(f"Agent update: {message}")
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import websockets
from pydantic import ValidationError

from .core.exceptions import AgentRegistrationError, ARCPException, AuthenticationError
from .models.agent import (
    AgentConnectionRequest,
    AgentInfo,
    AgentMetrics,
    AgentRegistration,
    AgentRequirements,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """A snapshot of system metrics at a point in time"""

    timestamp: datetime
    prometheus_metrics: str
    agent_stats: Dict[str, Any]
    resource_utilization: Dict[str, float]

    def get_metric_value(self, metric_name: str) -> Optional[float]:
        """Extract a specific metric value from Prometheus data"""
        for line in self.prometheus_metrics.split("\n"):
            if line.startswith(metric_name) and " " in line:
                try:
                    return float(line.split()[-1])
                except (ValueError, IndexError):
                    continue
        return None


# Define client-specific exceptions that extend ARCP exceptions
class ARCPError(ARCPException):
    """Base exception for ARCP client errors"""

    pass


class RegistrationError(AgentRegistrationError):
    """Agent registration related errors"""

    pass


class SearchError(ARCPError):
    """Search operation related errors"""

    pass


class ConnectionError(ARCPError):
    """Connection related errors"""

    pass


class ARCPClient:
    """
    Comprehensive ARCP Client for agent registry and control operations.

    This client provides a complete interface for interacting with ARCP servers,
    including agent registration, discovery, search, and real-time communication.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        user_agent: str = "ARCPClient/2.0.0",
    ):
        """
        Initialize ARCP client.

        Args:
            base_url: Base URL of the ARCP server
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for failed requests
            retry_delay: Initial delay between retries
            max_retry_delay: Maximum delay between retries
            user_agent: User agent string for requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.max_retries = retry_attempts  # Alias for compatibility
        self.retry_delay = retry_delay
        self.max_retry_delay = max_retry_delay
        self.user_agent = user_agent

        # Authentication state
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._refresh_token: Optional[str] = None

        # Session management
        self._session_id: Optional[str] = None
        self._client_fingerprint: str = str(uuid.uuid4())

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def _ensure_client(self):
        """Ensure HTTP client is initialized"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": self.user_agent,
                    "X-Client-Fingerprint": self._client_fingerprint,
                },
            )

    async def close(self):
        """Close the client and cleanup resources"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_required: bool = True,
        public_api: bool = False,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic and error handling.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            auth_required: Whether authentication is required
            public_api: Whether this is a public API call

        Returns:
            Response JSON data

        Raises:
            ARCPError: On request failures
        """
        await self._ensure_client()

        # Build URL
        url = urljoin(self.base_url, endpoint.lstrip("/"))

        # Build headers
        req_headers = {}
        if headers:
            req_headers.update(headers)
        if auth_required and not public_api:
            req_headers.update(self._get_auth_headers())

        # Retry logic
        last_exception = None
        for attempt in range(self.retry_attempts + 1):
            try:
                if attempt > 0:
                    delay = min(
                        self.retry_delay * (2 ** (attempt - 1)),
                        self.max_retry_delay,
                    )
                    await asyncio.sleep(delay)

                response = await self._client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                    headers=req_headers,
                )

                # Handle HTTP errors
                if response.status_code == 401:
                    raise AuthenticationError(
                        "Authentication failed - invalid or expired token"
                    )
                elif response.status_code == 403:
                    raise AuthenticationError(
                        "Access forbidden - insufficient permissions"
                    )
                elif response.status_code == 404:
                    raise ARCPError(f"Endpoint not found: {endpoint}")
                elif response.status_code == 429:
                    raise ARCPError("Rate limit exceeded")
                elif response.status_code >= 500:
                    raise ConnectionError(f"Server error: {response.status_code}")
                elif response.status_code >= 400:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get(
                            "detail", f"HTTP {response.status_code}"
                        )
                    except (json.JSONDecodeError, ValueError):
                        error_msg = f"HTTP {response.status_code}"
                    raise ARCPError(f"Request failed: {error_msg}")

                # Parse response
                try:
                    return response.json()
                except json.JSONDecodeError:
                    if response.text:
                        return {"message": response.text}
                    return {}

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = ConnectionError(f"Connection failed: {e}")
                if attempt == self.retry_attempts:
                    break
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.retry_attempts + 1}): {e}"
                )

            except Exception as e:
                if isinstance(e, ARCPError):
                    raise
                last_exception = ARCPError(f"Unexpected error: {e}")
                break

        raise last_exception or ARCPError("Request failed after all retry attempts")

    # Authentication Methods

    async def login_admin(self, username: str, password: str) -> Dict[str, Any]:
        """
        Login as administrator.

        Args:
            username: Admin username
            password: Admin password

        Returns:
            Login response with token information

        Raises:
            AuthenticationError: On login failure
        """
        try:
            response = await self._request(
                "POST",
                "/auth/login",
                json_data={"username": username, "password": password},
                auth_required=False,
            )

            self._access_token = response.get("access_token")
            expires_in = response.get("expires_in", 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.info("Admin login successful")
            return response

        except Exception as e:
            raise AuthenticationError(f"Admin login failed: {e}")

    async def request_temp_token(
        self, agent_id: str, agent_type: str, agent_key: str
    ) -> str:
        """
        Request temporary token for agent registration.

        Args:
            agent_id: Agent identifier
            agent_type: Type of agent
            agent_key: Agent registration key

        Returns:
            Temporary access token

        Raises:
            AuthenticationError: On token request failure
        """
        try:
            response = await self._request(
                "POST",
                "/auth/agent/request_temp_token",
                json_data={
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "agent_key": agent_key,
                },
                auth_required=False,
            )

            temp_token = response.get("temp_token")
            if not temp_token:
                raise AuthenticationError("No temporary token received")

            self._access_token = temp_token
            expires_in = response.get("expires_in", 900)  # 15 minutes
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.info(f"Temporary token acquired for agent {agent_id}")
            return temp_token

        except Exception as e:
            raise AuthenticationError(f"Temporary token request failed: {e}")

    async def validate_token(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate JWT token.

        Args:
            token: Token to validate (uses current token if None)

        Returns:
            Token validation result

        Raises:
            AuthenticationError: On validation failure
        """
        try:
            token_to_validate = token or self._access_token
            if not token_to_validate:
                raise AuthenticationError("No token available for validation")

            response = await self._request(
                "GET",
                "/tokens/validate",
                headers={"Authorization": f"Bearer {token_to_validate}"},
                auth_required=False,
                public_api=True,
            )

            return response

        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {e}")

    # Agent Management Methods

    async def register_agent(
        self,
        agent_id: str,
        name: str,
        agent_type: str,
        endpoint: str,
        capabilities: List[str],
        context_brief: str,
        version: str,
        owner: str,
        public_key: str,
        communication_mode: str,
        metadata: Optional[Dict[str, Any]] = None,
        features: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        language_support: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        requirements: Optional[AgentRequirements] = None,
        policy_tags: Optional[List[str]] = None,
        agent_key: Optional[str] = None,
    ) -> AgentInfo:
        """
        Register a new agent with the ARCP server.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable agent name
            agent_type: Type/category of the agent
            endpoint: HTTP endpoint URL for the agent
            capabilities: List of agent capabilities
            context_brief: Brief description of agent's purpose
            version: Agent version
            owner: Agent owner/organization
            public_key: Public key for authentication
            communication_mode: Communication mode (remote, local, hybrid)
            metadata: Additional metadata for enhanced search
            features: High-level agent features
            max_tokens: Maximum tokens the agent can process
            language_support: Supported languages
            rate_limit: Maximum requests per minute
            requirements: Agent requirements specification
            policy_tags: Policy tags for governance
            agent_key: Agent registration key (if not already authenticated)

        Returns:
            Registered agent information

        Raises:
            RegistrationError: On registration failure
        """
        try:
            # Request temp token if not authenticated and agent_key provided
            if not self._access_token and agent_key:
                await self.request_temp_token(agent_id, agent_type, agent_key)

            # Prepare registration request
            request_data = AgentRegistration(
                agent_id=agent_id,
                name=name,
                agent_type=agent_type,
                endpoint=endpoint,
                capabilities=capabilities,
                context_brief=context_brief,
                version=version,
                owner=owner,
                public_key=public_key,
                communication_mode=communication_mode,
                metadata=metadata or {},
                features=features,
                max_tokens=max_tokens,
                language_support=language_support,
                rate_limit=rate_limit,
                requirements=requirements,
                policy_tags=policy_tags,
            )

            response = await self._request(
                "POST",
                "/agents/register",
                json_data=request_data.dict(exclude_none=True),
            )

            # Update token from registration response
            if "access_token" in response:
                self._access_token = response["access_token"]
                # Assume long-lived token for registered agents
                self._token_expires_at = datetime.now() + timedelta(days=30)

            logger.info(f"Agent {agent_id} registered successfully")

            # Return agent info (need to fetch it since registration returns minimal data)
            return await self.get_agent(agent_id)

        except ValidationError as e:
            raise RegistrationError(f"Invalid registration data: {e}")
        except Exception as e:
            raise RegistrationError(f"Agent registration failed: {e}")

    async def get_agent(self, agent_id: str, include_metrics: bool = True) -> AgentInfo:
        """
        Get detailed information about a specific agent.

        Args:
            agent_id: Agent identifier
            include_metrics: Whether to include performance metrics

        Returns:
            Agent information

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            response = await self._request(
                "GET",
                f"/agents/{agent_id}",
                params={"include_metrics": include_metrics},
            )

            return AgentInfo(**response)

        except Exception as e:
            raise ARCPError(f"Failed to get agent {agent_id}: {e}")

    async def list_agents(
        self,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        include_metrics: bool = False,
    ) -> List[AgentInfo]:
        """
        List agents with optional filtering.

        Args:
            agent_type: Filter by agent type
            status: Filter by status ('alive' or 'dead')
            capabilities: Filter by capabilities
            include_metrics: Whether to include performance metrics

        Returns:
            List of agent information

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            params = {"include_metrics": include_metrics}
            if agent_type:
                params["agent_type"] = agent_type
            if status:
                params["status"] = status
            if capabilities:
                params["capabilities"] = capabilities

            response = await self._request("GET", "/agents", params=params)

            return [AgentInfo(**agent) for agent in response]

        except Exception as e:
            raise ARCPError(f"Failed to list agents: {e}")

    async def update_heartbeat(self, agent_id: str) -> Dict[str, Any]:
        """
        Update agent heartbeat to indicate it's still alive.

        Args:
            agent_id: Agent identifier

        Returns:
            Heartbeat response

        Raises:
            ARCPError: On heartbeat failure
        """
        try:
            response = await self._request("POST", f"/agents/{agent_id}/heartbeat")

            logger.debug(f"Heartbeat updated for agent {agent_id}")
            return response

        except Exception as e:
            raise ARCPError(f"Failed to update heartbeat for {agent_id}: {e}")

    async def update_metrics(
        self, agent_id: str, metrics_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update agent performance metrics.

        Args:
            agent_id: Agent identifier
            metrics_data: Metrics data to update

        Returns:
            Update response

        Raises:
            ARCPError: On metrics update failure
        """
        try:
            response = await self._request(
                "POST", f"/agents/{agent_id}/metrics", json_data=metrics_data
            )

            logger.debug(f"Metrics updated for agent {agent_id}")
            return response

        except Exception as e:
            raise ARCPError(f"Failed to update metrics for {agent_id}: {e}")

    async def get_metrics(self, agent_id: str) -> AgentMetrics:
        """
        Get agent performance metrics.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent metrics

        Raises:
            ARCPError: On metrics retrieval failure
        """
        try:
            response = await self._request("GET", f"/agents/{agent_id}/metrics")

            return AgentMetrics(**response)

        except Exception as e:
            raise ARCPError(f"Failed to get metrics for {agent_id}: {e}")

    async def get_system_metrics(self) -> str:
        """
        Get system-wide Prometheus metrics (Admin only).

        Retrieves comprehensive system metrics including resource utilization,
        agent statistics, request metrics, and internal service health indicators.

        **Authentication**: Requires admin authentication via login_admin().

        Returns:
            Prometheus-formatted metrics data as string

        Raises:
            AuthenticationError: If not authenticated as admin
            ARCPError: On request failure
        """
        try:
            response = await self._request("GET", "/metrics")

            # The /metrics endpoint returns plain text, which _request wraps in {"message": text}
            if isinstance(response, dict) and "message" in response:
                return response["message"]
            elif isinstance(response, str):
                return response
            else:
                # Fallback: convert to string
                return str(response)

        except Exception as e:
            if "403" in str(e) or "Forbidden" in str(e):
                raise AuthenticationError(
                    "Admin authentication required for system metrics"
                )
            raise ARCPError(f"Failed to get system metrics: {e}")

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get system statistics and agent registry data (Admin only).

        Retrieves agent registry statistics, performance metrics, and
        system health indicators.

        **Authentication**: Requires admin authentication via login_admin().

        Returns:
            Dictionary containing:
            - registry_statistics: Agent counts, types, status
            - feature_statistics: Feature availability and usage
            - performance_metrics: System performance data

        Raises:
            AuthenticationError: If not authenticated as admin
            ARCPError: On request failure
        """
        try:
            return await self._request("GET", "/agents/stats")

        except Exception as e:
            if "403" in str(e) or "Forbidden" in str(e):
                raise AuthenticationError(
                    "Admin authentication required for system stats"
                )
            raise ARCPError(f"Failed to get system stats: {e}")

    async def get_resource_utilization(self) -> Dict[str, float]:
        """
        Get current system resource utilization (Admin only).

        Retrieves real-time system resource usage including CPU, memory,
        network, and disk utilization percentages.

        **Authentication**: Requires admin authentication via login_admin().

        Returns:
            Dictionary with utilization percentages:
            - cpu: CPU utilization percentage
            - memory: Memory utilization percentage
            - network: Network utilization percentage
            - disk: Disk utilization percentage

        Raises:
            AuthenticationError: If not authenticated as admin
            ARCPError: On request failure or parsing error
        """
        try:
            # Extract resource metrics from Prometheus data
            prometheus_data = await self.get_system_metrics()

            # Parse Prometheus metrics to extract resource utilization
            resource_metrics = {}

            for line in prometheus_data.split("\n"):
                if line.startswith("arcp_system_cpu_utilization_percent"):
                    resource_metrics["cpu"] = float(line.split()[-1])
                elif line.startswith("arcp_system_memory_utilization_percent"):
                    resource_metrics["memory"] = float(line.split()[-1])
                elif line.startswith("arcp_system_network_utilization_percent"):
                    resource_metrics["network"] = float(line.split()[-1])
                elif line.startswith("arcp_system_disk_utilization_percent"):
                    resource_metrics["disk"] = float(line.split()[-1])

            if not resource_metrics:
                raise ARCPError(
                    "Resource utilization metrics not found in system metrics"
                )

            return resource_metrics

        except AuthenticationError:
            raise
        except Exception as e:
            raise ARCPError(f"Failed to get resource utilization: {e}")

    async def get_metrics_snapshot(self) -> MetricsSnapshot:
        """
        Get a complete metrics snapshot at current time (Admin only).

        Gathers all metrics data concurrently for consistent snapshot timing.

        **Authentication**: Requires admin authentication via login_admin().

        Returns:
            MetricsSnapshot with all metrics data and timestamp

        Raises:
            AuthenticationError: If not authenticated as admin
            ARCPError: On request failure
        """
        try:
            # Gather all metrics concurrently for consistent snapshot
            prometheus_task = asyncio.create_task(self.get_system_metrics())
            stats_task = asyncio.create_task(self.get_system_stats())
            resources_task = asyncio.create_task(self.get_resource_utilization())

            prometheus_metrics, agent_stats, resource_utilization = (
                await asyncio.gather(prometheus_task, stats_task, resources_task)
            )

            return MetricsSnapshot(
                timestamp=datetime.now(),
                prometheus_metrics=prometheus_metrics,
                agent_stats=agent_stats,
                resource_utilization=resource_utilization,
            )

        except Exception as e:
            if isinstance(e, (AuthenticationError, ARCPError)):
                raise
            raise ARCPError(f"Failed to create metrics snapshot: {e}")

    async def monitor_system(
        self,
        interval: int = 30,
        callback: Optional[Callable[[MetricsSnapshot], None]] = None,
        duration: Optional[int] = None,
    ):
        """
        Continuous system monitoring with callback for metrics updates (Admin only).

        **Authentication**: Requires admin authentication via login_admin().

        Args:
            interval: Monitoring interval in seconds
            callback: Optional callback function for metrics snapshots
            duration: Optional monitoring duration in seconds (None for infinite)

        Raises:
            AuthenticationError: If not authenticated as admin
        """
        start_time = datetime.now()
        iteration = 0

        try:
            while True:
                iteration += 1

                try:
                    snapshot = await self.get_metrics_snapshot()

                    if callback:
                        callback(snapshot)
                    else:
                        # Default callback - print basic info
                        registry_stats = snapshot.agent_stats.get(
                            "registry_statistics", {}
                        )
                        print(
                            f"[{snapshot.timestamp.strftime('%H:%M:%S')}] "
                            f"CPU: {snapshot.resource_utilization.get('cpu', 0):>5.1f}% | "
                            f"Memory: {snapshot.resource_utilization.get('memory', 0):>5.1f}% | "
                            f"Agents: {registry_stats.get('alive_agents', 0):>2}"
                        )

                except Exception as e:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring error: {e}"
                    )

                # Check duration limit
                if (
                    duration
                    and (datetime.now() - start_time).total_seconds() >= duration
                ):
                    print(
                        f"\nMonitoring completed after {duration} seconds ({iteration} iterations)"
                    )
                    break

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print(f"\nMonitoring stopped by user after {iteration} iterations")
        except Exception as e:
            print(f"\nMonitoring failed: {e}")

    async def admin_health_check(self) -> Dict[str, Any]:
        """
        Perform a system health check using metrics data (Admin only).

        **Authentication**: Requires admin authentication via login_admin().

        Returns:
            Health status summary with checks for CPU, memory, and agent availability

        Raises:
            AuthenticationError: If not authenticated as admin
        """
        try:
            snapshot = await self.get_metrics_snapshot()
            registry_stats = snapshot.agent_stats.get("registry_statistics", {})

            # Define health thresholds
            cpu_threshold = 90.0
            memory_threshold = 95.0

            # Check system health
            cpu_usage = snapshot.resource_utilization.get("cpu", 0)
            memory_usage = snapshot.resource_utilization.get("memory", 0)
            alive_agents = registry_stats.get("alive_agents", 0)
            total_agents = registry_stats.get("total_agents", 0)

            health_status = {
                "status": "healthy",
                "timestamp": snapshot.timestamp.isoformat(),
                "checks": {
                    "cpu_usage": {
                        "value": cpu_usage,
                        "threshold": cpu_threshold,
                        "status": "ok" if cpu_usage < cpu_threshold else "warning",
                    },
                    "memory_usage": {
                        "value": memory_usage,
                        "threshold": memory_threshold,
                        "status": (
                            "ok" if memory_usage < memory_threshold else "critical"
                        ),
                    },
                    "agent_availability": {
                        "alive_agents": alive_agents,
                        "total_agents": total_agents,
                        "status": "ok" if alive_agents == total_agents else "warning",
                    },
                },
            }

            # Determine overall status
            if any(
                check["status"] == "critical"
                for check in health_status["checks"].values()
            ):
                health_status["status"] = "critical"
            elif any(
                check["status"] == "warning"
                for check in health_status["checks"].values()
            ):
                health_status["status"] = "warning"

            return health_status

        except Exception as e:
            if isinstance(e, (AuthenticationError, ARCPError)):
                raise
            return {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    async def export_metrics(self, format: str = "prometheus") -> str:
        """
        Export metrics in specified format (Admin only).

        **Authentication**: Requires admin authentication via login_admin().

        Args:
            format: Export format ('prometheus', 'json')

        Returns:
            Formatted metrics data

        Raises:
            AuthenticationError: If not authenticated as admin
            ValueError: If format is not supported
        """
        if format == "prometheus":
            return await self.get_system_metrics()
        elif format == "json":
            import json

            snapshot = await self.get_metrics_snapshot()
            return json.dumps(
                {
                    "timestamp": snapshot.timestamp.isoformat(),
                    "agent_stats": snapshot.agent_stats,
                    "resource_utilization": snapshot.resource_utilization,
                    "metrics_size": len(snapshot.prometheus_metrics),
                },
                indent=2,
            )
        else:
            raise ValueError(
                f"Unsupported format: {format}. Use 'prometheus' or 'json'"
            )

    async def unregister_agent(
        self, agent_id: str, agent_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unregister an agent from the registry.

        Args:
            agent_id: Agent identifier
            agent_key: Agent key for authentication if not already authenticated

        Returns:
            Unregistration response

        Raises:
            ARCPError: On unregistration failure
        """
        try:
            # Request temp token if not authenticated and agent_key provided
            if not self._access_token and agent_key:
                await self.request_temp_token(agent_id, "unknown", agent_key)

            response = await self._request("DELETE", f"/agents/{agent_id}")

            logger.info(f"Agent {agent_id} unregistered successfully")
            return response

        except Exception as e:
            raise ARCPError(f"Failed to unregister agent {agent_id}: {e}")

    # Search and Discovery Methods

    async def search_agents(
        self,
        query: str,
        top_k: int = 3,
        min_similarity: float = 0.5,
        capabilities: Optional[List[str]] = None,
        weighted: bool = False,
        agent_type: Optional[str] = None,
        public_api: bool = True,
    ) -> List[SearchResponse]:
        """
        Perform semantic search for agents using vector embeddings.

        Args:
            query: Search query text
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            capabilities: Filter by capabilities
            weighted: Weight results by reputation/metrics
            agent_type: Filter by agent type
            public_api: Use public API (default) or authenticated API

        Returns:
            List of search results

        Raises:
            SearchError: On search failure
        """
        try:
            request_data = SearchRequest(
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
                capabilities=capabilities,
                weighted=weighted,
                agent_type=agent_type,
            )

            endpoint = "/public/search" if public_api else "/agents/search"

            response = await self._request(
                "POST",
                endpoint,
                json_data=request_data.dict(exclude_none=True),
                auth_required=not public_api,
                public_api=public_api,
            )

            # Handle search response format
            if isinstance(response, dict) and "results" in response:
                results_data = response["results"]
            else:
                results_data = response

            return [SearchResponse(**result) for result in results_data]

        except ValidationError as e:
            raise SearchError(f"Invalid search parameters: {e}")
        except Exception as e:
            raise SearchError(f"Agent search failed: {e}")

    async def discover_agents(
        self,
        agent_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AgentInfo]:
        """
        Discover available agents using the public API.

        Args:
            agent_type: Filter by agent type
            capabilities: Filter by capabilities
            limit: Maximum number of agents to return
            offset: Number of agents to skip

        Returns:
            List of available agents

        Raises:
            ARCPError: On discovery failure
        """
        try:
            params = {"limit": limit, "offset": offset}
            if agent_type:
                params["agent_type"] = agent_type
            if capabilities:
                params["capabilities"] = capabilities

            response = await self._request(
                "GET",
                "/public/discover",
                params=params,
                auth_required=False,
                public_api=True,
            )

            # Handle paginated response format
            if isinstance(response, dict) and "agents" in response:
                agents_data = response["agents"]
            else:
                agents_data = response

            return [AgentInfo(**agent) for agent in agents_data]

        except Exception as e:
            raise ARCPError(f"Agent discovery failed: {e}")

    async def get_public_agent(self, agent_id: str) -> AgentInfo:
        """
        Get public agent information.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent information

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            response = await self._request(
                "GET",
                f"/public/agent/{agent_id}",
                auth_required=False,
                public_api=True,
            )

            return AgentInfo(**response)

        except Exception as e:
            raise ARCPError(f"Failed to get public agent {agent_id}: {e}")

    # Connection Methods

    async def request_agent_connection(
        self,
        agent_id: str,
        user_id: str,
        user_endpoint: str,
        display_name: str = "Anonymous User",
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Request connection to an agent for external users.

        Args:
            agent_id: Agent to connect to
            user_id: User requesting connection
            user_endpoint: User's endpoint for communication
            display_name: Display name for the user
            additional_info: Additional user information

        Returns:
            Connection response

        Raises:
            ARCPError: On connection request failure
        """
        try:
            request_data = AgentConnectionRequest(
                user_id=user_id,
                user_endpoint=user_endpoint,
                display_name=display_name,
                additional_info=additional_info or {},
            )

            response = await self._request(
                "POST",
                f"/public/connect/{agent_id}",
                json_data=request_data.dict(),
                auth_required=False,
                public_api=True,
            )

            logger.info(f"Connection requested to agent {agent_id} for user {user_id}")
            return response

        except ValidationError as e:
            raise ARCPError(f"Invalid connection request: {e}")
        except Exception as e:
            raise ARCPError(f"Connection request failed: {e}")

    # System Information Methods

    async def get_system_info(self) -> Dict[str, Any]:
        """
        Get public system information.

        Returns:
            System information and capabilities

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            response = await self._request(
                "GET",
                "/",  # Root endpoint provides system info
                auth_required=False,
                public_api=True,
            )

            return response

        except Exception as e:
            raise ARCPError(f"Failed to get system info: {e}")

    async def get_public_stats(self) -> Dict[str, Any]:
        """
        Get public ecosystem statistics.

        Returns:
            Public statistics

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            response = await self._request(
                "GET", "/public/stats", auth_required=False, public_api=True
            )

            return response

        except Exception as e:
            raise ARCPError(f"Failed to get public stats: {e}")

    async def get_allowed_agent_types(self) -> List[str]:
        """
        Get list of allowed agent types.

        Returns:
            List of allowed agent types

        Raises:
            ARCPError: On retrieval failure
        """
        try:
            response = await self._request(
                "GET",
                "/public/agent_types",
                auth_required=False,
                public_api=True,
            )

            return response.get("allowed_agent_types", [])

        except Exception as e:
            raise ARCPError(f"Failed to get allowed agent types: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the ARCP server.

        Returns:
            Health status information

        Raises:
            ARCPError: On health check failure
        """
        try:
            response = await self._request(
                "GET",
                "/health",  # Standard health endpoint
                auth_required=False,
                public_api=True,
            )

            return response

        except Exception as e:
            raise ARCPError(f"Health check failed: {e}")

    # WebSocket Methods

    async def websocket_public(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Connect to public WebSocket for real-time agent updates.

        Yields:
            WebSocket messages as dictionaries

        Raises:
            ConnectionError: On connection failure
        """
        try:
            # Parse WebSocket URL
            parsed = urlparse(self.base_url)
            ws_scheme = "wss" if parsed.scheme == "https" else "ws"
            ws_url = f"{ws_scheme}://{parsed.netloc}/public/ws"

            async with websockets.connect(ws_url) as websocket:
                logger.info("Connected to public WebSocket")

                # Request initial discovery data
                await websocket.send(
                    json.dumps({"type": "get_discovery", "page": 1, "page_size": 50})
                )

                async for message in websocket:
                    # Handle plain-text heartbeat messages from server
                    if isinstance(message, str):
                        m = message.strip().lower()
                        if m == "ping":
                            # Respond to server keepalive without yielding
                            try:
                                await websocket.send("pong")
                            except Exception:
                                pass
                            continue
                        if m == "pong":
                            # Ignore server pong
                            continue

                    # Attempt to parse JSON payloads
                    try:
                        data = json.loads(message)
                        yield data
                    except json.JSONDecodeError:
                        # Ignore non-JSON frames quietly
                        logger.debug(f"Received non-JSON frame on public WS: {message}")

        except Exception as e:
            raise ConnectionError(f"WebSocket connection failed: {e}")

    async def websocket_agent(
        self, token: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Connect to agent WebSocket for real-time updates.

        Args:
            token: Authentication token (uses current token if None)

        Yields:
            WebSocket messages as dictionaries

        Raises:
            ConnectionError: On connection failure
            AuthenticationError: On authentication failure
        """
        try:
            auth_token = token or self._access_token
            if not auth_token:
                raise AuthenticationError("No authentication token available")

            # Parse WebSocket URL
            parsed = urlparse(self.base_url)
            ws_scheme = "wss" if parsed.scheme == "https" else "ws"
            ws_url = f"{ws_scheme}://{parsed.netloc}/agents/ws"

            async with websockets.connect(ws_url) as websocket:
                logger.info("Connected to agent WebSocket")

                # Wait for auth request
                auth_request = await websocket.recv()
                auth_data = json.loads(auth_request)

                if auth_data.get("type") == "auth_required":
                    # Send authentication token
                    await websocket.send(json.dumps({"token": auth_token}))

                    # Wait for auth response
                    auth_response = await websocket.recv()
                    auth_result = json.loads(auth_response)

                    if auth_result.get("type") != "auth_success":
                        raise AuthenticationError("WebSocket authentication failed")

                    logger.info("WebSocket authentication successful")

                # Listen for messages
                async for message in websocket:
                    try:
                        if message == "ping":
                            await websocket.send("pong")
                            continue

                        data = json.loads(message)
                        yield data
                    except json.JSONDecodeError:
                        logger.warning(f"Received invalid JSON: {message}")

        except Exception as e:
            if isinstance(e, (AuthenticationError, ConnectionError)):
                raise
            raise ConnectionError(f"Agent WebSocket connection failed: {e}")

    # Utility Methods

    def is_authenticated(self) -> bool:
        """Check if client is currently authenticated"""
        return (
            self._access_token is not None
            and self._token_expires_at is not None
            and datetime.now() < self._token_expires_at
        )

    async def refresh_authentication(self) -> bool:
        """
        Attempt to refresh authentication token.

        Returns:
            True if refresh successful, False otherwise
        """
        try:
            if not self._access_token:
                return False

            response = await self._request(
                "POST",
                "/tokens/refresh",
                headers={"Authorization": f"Bearer {self._access_token}"},
                auth_required=False,
                public_api=True,
            )

            self._access_token = response.get("access_token")
            if self._access_token:
                # Assume 1 hour expiry for refreshed tokens
                self._token_expires_at = datetime.now() + timedelta(hours=1)
                logger.info("Authentication token refreshed successfully")
                return True

            return False

        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            return False

    async def start_heartbeat_task(
        self, agent_id: str, interval: float = 30.0
    ) -> asyncio.Task:
        """
        Start a background task to send periodic heartbeats.

        Args:
            agent_id: Agent identifier
            interval: Heartbeat interval in seconds

        Returns:
            Async task handle
        """

        async def heartbeat_loop():
            while True:
                try:
                    await self.update_heartbeat(agent_id)
                    await asyncio.sleep(interval)
                except Exception as e:
                    logger.error(f"Heartbeat failed for {agent_id}: {e}")
                    await asyncio.sleep(interval)

        task = asyncio.create_task(heartbeat_loop())
        logger.info(
            f"Started heartbeat task for agent {agent_id} (interval: {interval}s)"
        )
        return task


# Convenience functions for common use cases
async def get_system_health(
    base_url: str, username: str, password: str
) -> Dict[str, Any]:
    """
    Quick system health check.

    Args:
        base_url: ARCP server URL
        username: Admin username
        password: Admin password

    Returns:
        Health status summary
    """
    client = ARCPClient(base_url)
    await client.login_admin(username, password)
    return await client.admin_health_check()


async def monitor_system(
    base_url: str,
    username: str,
    password: str,
    interval: int = 30,
    duration: Optional[int] = None,
):
    """
    Start system monitoring with default callback.

    Args:
        base_url: ARCP server URL
        username: Admin username
        password: Admin password
        interval: Monitoring interval in seconds
        duration: Optional monitoring duration in seconds
    """
    client = ARCPClient(base_url)
    await client.login_admin(username, password)
    await client.monitor_system(interval=interval, duration=duration)


# Export main classes and exceptions
__all__ = [
    "ARCPClient",
    "MetricsSnapshot",
    "ARCPError",
    "AuthenticationError",
    "RegistrationError",
    "SearchError",
    "ConnectionError",
    "ValidationError",
    "AgentRequirements",
    "AgentRegistration",
    "AgentMetrics",
    "AgentInfo",
    "SearchRequest",
    "SearchResponse",
    "AgentConnectionRequest",
    "get_system_health",
    "monitor_system",
]
