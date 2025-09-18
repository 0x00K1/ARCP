# REST API Reference

ARCP provides a comprehensive REST API for agent management, discovery, and system monitoring. This reference covers all endpoints with detailed examples and response formats.

## 🔗 Base URL

All API endpoints are relative to the ARCP server base URL:

```
http://localhost:8001
```

## 🔐 Authentication

ARCP uses JWT (JSON Web Tokens) for authentication with additional security layers:

### Authentication Types

**Public Endpoints:** No authentication required - provide general system information.

**Agent Endpoints:** Require agent temporary tokens - agents must first request tokens using valid public keys.

**Admin Endpoints:** Require admin JWT tokens + PIN verification:
1. Login to obtain JWT token
2. Set admin PIN using `/auth/set_pin`
3. Verify PIN using `/auth/verify_pin` before accessing protected endpoints
4. Include `X-Client-Fingerprint` header for session binding

Include the token in the `Authorization` header:

```bash
Authorization: Bearer <your-jwt-token>
X-Client-Fingerprint: <unique-session-id>
```

### Getting a Token

```bash
# Admin login
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: your-fingerprint-123" \
  -d '{"username": "ARCP", "password": "ARCP"}'

# Response
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "agent_id": "user_ARCP"
}
```

### Admin PIN Requirements

For admin operations, a session PIN must be set and verified:

1. **Set PIN** (after login):
```bash
curl -X POST "http://localhost:8001/auth/set_pin" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -H "X-Client-Fingerprint: <fingerprint>" \
  -d '{"pin": "StrongPin123!"}'
```

2. **Verify PIN** (before admin operations):
```bash
curl -X POST "http://localhost:8001/auth/verify_pin" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -H "X-Client-Fingerprint: <fingerprint>" \
  -d '{"pin": "StrongPin123!"}'
```

**PIN Requirements:**
- Minimum 4 characters
- Maximum 32 characters
- Must contain letters and numbers
- Special characters allowed

## 📊 System Endpoints

### Health Check

Check if the ARCP server is running and healthy.

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-XX...",
  "version": "2.0.0",
  "uptime": "operational",
  "service": "ARCP Registry",
  "features": {
    "vector_search": true,
    "redis_storage": true,
    "metrics_tracking": true,
    "jwt_authentication": true,
    "websocket_broadcasts": true
  },
  "storage": {
    "redis": "connected",
    "backup_storage": "available"
  },
  "ai_services": {
    "azure_openai": "available",
    "embeddings": true
  },
  "agents": {
    "total_registered": 0,
    "alive_agents": 0,
    "dead_agents": 0,
    "agent_types": {},
    "embeddings_stored": 0
  },
  "performance": {
    "redis_connected": true
  }
}
```

**Example:**
```bash
curl http://localhost:8001/health
```

### Metrics (admin-only)

Prometheus-format metrics. Requires admin authentication.

```http
GET /metrics
```

Use admin JWT and session fingerprint headers.

```bash
curl -H "Authorization: Bearer <admin-jwt>" \
     -H "X-Client-Fingerprint: <fingerprint>" \
     http://localhost:8001/metrics
```

### Metrics Scrape (token)

Prometheus scraping endpoint protected by a pre-shared bearer token. Use this for Prometheus instead of `/metrics`.

```http
GET /metrics/scrape
```

Headers:

```
Authorization: Bearer <METRICS_SCRAPE_TOKEN>
```

Example Prometheus job:

```yaml
scrape_configs:
  - job_name: 'arcp'
    static_configs:
      - targets: ['arcp:8001']
    metrics_path: /metrics/scrape
    bearer_token: 'your-long-random-token'
```

### Additional Health Endpoints

For detailed health information, use these admin-only endpoints:

```http
GET /health/detailed
GET /health/config
GET /health/redis
GET /health/azure
```

**Note:** These endpoints require admin authentication and PIN verification.

## 🤖 Agent Management

### Register Agent

Register a new agent with the ARCP server.

```http
POST /agents/register
```

**Request Body:**
```json
{
  "agent_id": "my-agent-001",
  "name": "My testing Agent",
  "agent_type": "testing",
  "endpoint": "http://localhost:8080",
  "context_brief": "A testing agent for data processing and analysis",
  "capabilities": ["processing", "analysis"],
  "owner": "John Doe",
  "public_key": "test-public-key-123456789012345678901234567890",
  "metadata": {
    "version": "1.0.0",
    "author": "John Doe"
  },
  "version": "1.0.0",
  "communication_mode": "remote"
}
```

**Required Fields:**
- `agent_id` (string): Unique agent identifier
- `name` (string): Name of the agent (2-32 characters)
- `agent_type` (string): Type of agent (must be in allowed types)
- `endpoint` (string): Agent HTTP endpoint URL
- `context_brief` (string): Description of agent's domain expertise
- `capabilities` (array): List of specific capabilities
- `owner` (string): Entity that owns this agent
- `public_key` (string): Public key for authentication (min 32 characters)
- `metadata` (object): Additional agent metadata
- `version` (string): Version of the agent
- `communication_mode` (string): "remote", "local", or "hybrid"

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "status": "registered",
  "message": "Agent registered successfully",
  "timestamp": "2025-01-XX..."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <temp-token>" \
  -d '{
    "agent_id": "my-agent-001",
    "name": "My testing Agent",
    "agent_type": "testing",
    "endpoint": "http://localhost:8080",
    "context_brief": "A testing agent for data processing and analysis",
    "capabilities": ["processing", "analysis"],
    "owner": "John Doe",
    "public_key": "test-public-key-123456789012345678901234567890",
    "metadata": {
      "version": "1.0.0",
      "author": "John Doe"
    },
    "version": "1.0.0",
    "communication_mode": "remote"
  }'
```

### Get Agent

Retrieve information about a specific agent.

```http
GET /agents/{agent_id}
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "name": "My testing Agent",
  "agent_type": "testing",
  "capabilities": ["processing", "analysis"],
  "endpoint": "http://localhost:8080",
  "description": "A testing agent for data processing",
  "status": "alive",
  "last_seen": "2025-01-XX...",
  "registered_at": "2025-01-XX...",
  "metadata": {
    "version": "1.0.0",
    "author": "John Doe"
  }
}
```

**Example:**
```bash
curl http://localhost:8001/agents/my-agent-001
```

### List Agents

Get a paginated list of all registered agents.

```http
GET /agents
```

**Query Parameters:**
- `page` (integer, optional): Page number (default: 1)
- `page_size` (integer, optional): Number of agents per page (default: 50)
- `agent_type` (string, optional): Filter by agent type
- `status` (string, optional): Filter by status (alive/dead)
- `search` (string, optional): Search in agent name and description

**Response:**
```json
{
  "agents": [
    {
      "agent_id": "my-agent-001",
      "name": "My testing Agent",
      "agent_type": "testing",
      "capabilities": ["processing", "analysis"],
      "endpoint": "http://localhost:8080",
      "description": "A testing agent for data processing",
      "status": "alive",
      "last_seen": "2025-01-XX...",
      "registered_at": "2025-01-XX..."
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_agents": 15,
    "total_pages": 1
  }
}
```

**Example:**
```bash
# Get all agents
curl http://localhost:8001/agents

# Get agents with pagination
curl "http://localhost:8001/agents?page=1&page_size=10"

# Filter by agent type
curl "http://localhost:8001/agents?agent_type=testing"

# Search agents
curl "http://localhost:8001/agents?search=testing"
```

### Update Agent Heartbeat

Update the heartbeat for a specific agent.

```http
POST /agents/{agent_id}/heartbeat
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Request Body:**
```json
{
  "status": "alive",
  "metadata": {
    "cpu_usage": 45.2,
    "memory_usage": 67.8
  }
}
```

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "status": "alive",
  "last_seen": "2025-01-XX...",
  "message": "Heartbeat updated successfully"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/my-agent-001/heartbeat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "status": "alive",
    "metadata": {
      "cpu_usage": 45.2,
      "memory_usage": 67.8
    }
  }'
```

### Update Agent Metrics

Update metrics for a specific agent.

```http
POST /agents/{agent_id}/metrics
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Request Body:**
```json
{
  "metrics": {
    "requests_processed": 1250,
    "average_response_time": 0.15,
    "error_rate": 0.02,
    "cpu_usage": 45.2,
    "memory_usage": 67.8
  },
  "timestamp": "2025-01-XX..."
}
```

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "metrics_updated": true,
  "message": "Metrics updated successfully",
  "timestamp": "2025-01-XX..."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/my-agent-001/metrics" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "metrics": {
      "requests_processed": 1250,
      "average_response_time": 0.15,
      "error_rate": 0.02
    }
  }'
```

### Get Agent Metrics

Retrieve metrics for a specific agent.

```http
GET /agents/{agent_id}/metrics
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Query Parameters:**
- `start_time` (string, optional): Start time for metrics (ISO 8601)
- `end_time` (string, optional): End time for metrics (ISO 8601)
- `limit` (integer, optional): Maximum number of metrics to return (default: 100)

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "metrics": [
    {
      "timestamp": "2025-01-XX...",
      "metrics": {
        "requests_processed": 1250,
        "average_response_time": 0.15,
        "error_rate": 0.02,
        "cpu_usage": 45.2,
        "memory_usage": 67.8
      }
    }
  ],
  "pagination": {
    "total_metrics": 1,
    "limit": 100
  }
}
```

**Example:**
```bash
# Get all metrics
curl http://localhost:8001/agents/my-agent-001/metrics

# Get metrics with time range
curl "http://localhost:8001/agents/my-agent-001/metrics?start_time=2025-01-01T00:00:00Z&end_time=2025-01-02T00:00:00Z"

# Get limited metrics
curl "http://localhost:8001/agents/my-agent-001/metrics?limit=10"
```

### Report Agent Metrics (Performance)

Report agent performance metrics for reputation tracking.

```http
POST /agents/report-metrics/{agent_id}
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Query Parameters:**
- `response_time` (float, required): Response time in seconds
- `success` (boolean, optional): Whether the operation was successful (default: true)

**Headers Required:**
- `Authorization`: Bearer token

**Response:**
```json
{
  "status": "success",
  "message": "Metrics updated successfully",
  "current_metrics": {
    "success_rate": 0.987,
    "avg_response_time": 0.145,
    "total_requests": 1250,
    "reputation_score": 0.892,
    "last_active": "2025-01-XX..."
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/report-metrics/my-agent-001?response_time=0.15&success=true" \
  -H "Authorization: Bearer <agent-token>"
```

### Report Agent Metrics (Compatibility)

Compatibility endpoint for agent metrics reporting.

```http
POST /agents/{agent_id}/metrics/compat
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Query Parameters:**
- `response_time` (float, required): Response time in seconds
- `success` (boolean, optional): Whether the operation was successful (default: true)

**Headers Required:**
- `Authorization`: Bearer token

**Response:**
```json
{
  "status": "success",
  "message": "Metrics updated successfully",
  "current_metrics": {
    "success_rate": 0.987,
    "avg_response_time": 0.145,
    "total_requests": 1250,
    "reputation_score": 0.892,
    "last_active": "2025-01-XX..."
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/my-agent-001/metrics/compat?response_time=0.15&success=true" \
  -H "Authorization: Bearer <agent-token>"
```

### Unregister Agent

Unregister an agent from the ARCP server.

```http
DELETE /agents/{agent_id}
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "status": "unregistered",
  "message": "Agent unregistered successfully",
  "timestamp": "2025-01-XX..."
}
```

**Example:**
```bash
curl -X DELETE "http://localhost:8001/agents/my-agent-001" \
  -H "Authorization: Bearer <agent-token>"
```

## 🔍 Discovery and Search

### Semantic Search

Search for agents using natural language queries.

```http
POST /agents/search
```

**Request Body:**
```json
{
  "query": "Find agents that can process data and analyze information",
  "limit": 10,
  "threshold": 0.7
}
```

**Response:**
```json
{
  "query": "Find agents that can process data and analyze information",
  "results": [
    {
      "agent_id": "my-agent-001",
      "name": "My testing Agent",
      "agent_type": "testing",
      "capabilities": ["processing", "analysis"],
      "endpoint": "http://localhost:8080",
      "description": "A testing agent for data processing",
      "similarity_score": 0.95,
      "status": "alive"
    }
  ],
  "total_results": 1,
  "search_time": 0.15
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find agents that can process data and analyze information",
    "limit": 10
  }'
```

### Semantic Search (GET)

Search for agents using query parameters.

```http
GET /agents/search
```

**Query Parameters:**
- `query` (string, required): Search query text
- `top_k` (integer, optional): Number of results to return (default: 3, max: 100)
- `min_similarity` (float, optional): Minimum similarity score (default: 0.5)
- `capabilities` (array, optional): Filter by capabilities
- `weighted` (boolean, optional): Use weighted search (default: false)
- `agent_type` (string, optional): Filter by agent type

**Response:**
```json
[
  {
    "agent_id": "my-agent-001",
    "name": "My testing Agent",
    "agent_type": "testing",
    "capabilities": ["processing", "analysis"],
    "endpoint": "http://localhost:8080",
    "context_brief": "A testing agent for data processing",
    "similarity_score": 0.95,
    "status": "alive"
  }
]
```

**Example:**
```bash
# Basic search
curl "http://localhost:8001/agents/search?query=data%20processing" \
  -H "Authorization: Bearer <agent-token>"

# Advanced search with filters
curl "http://localhost:8001/agents/search?query=data%20processing&top_k=5&min_similarity=0.7&agent_type=testing" \
  -H "Authorization: Bearer <agent-token>"
```

### Public Discovery

Get publicly available agents (no authentication required).

```http
GET /public/discover
```

**Query Parameters:**
- `page` (integer, optional): Page number (default: 1)
- `limit` (integer, optional): Number of agents per page (default: 50, max: 100)
- `agent_type` (string, optional): Filter by agent type
- `search` (string, optional): Search in agent name and description
- `capabilities` (array, optional): Filter by capabilities
- `status` (string, optional): Filter by status (alive/dead)

**Response:**
```json
[
  {
    "agent_id": "my-agent-001",
    "name": "My testing Agent",
    "agent_type": "testing",
    "capabilities": ["processing", "analysis"],
    "endpoint": "http://localhost:8080",
    "context_brief": "A testing agent for data processing",
    "status": "alive",
    "last_heartbeat": "2025-01-XX...",
    "owner": "John Doe",
    "version": "1.0.0",
    "communication_mode": "remote"
  }
]
```

**Example:**
```bash
# Get all public agents
curl http://localhost:8001/public/discover

# Get public agents with pagination
curl "http://localhost:8001/public/discover?page=1&limit=10"

# Filter public agents by type
curl "http://localhost:8001/public/discover?agent_type=testing"

# Filter by status
curl "http://localhost:8001/public/discover?status=alive"
```

### Public System Information

Get public system information and API details.

```http
GET /public/info
```

**Response:**
```json
{
  "service": "ARCP (Agent Registry & Control Protocol)",
  "version": "2.0.0",
  "public_api": {
    "available": true,
    "endpoints": {
      "discover": "/public/discover - Discover available agents",
      "search": "/public/search - Search agents with semantic queries",
      "agent_details": "/public/agent/{agent_id} - Get detailed agent information",
      "connect": "/public/connect/{agent_id} - Request connection to an agent"
    }
  },
  "capabilities": {
    "vector_search": true,
    "real_time_updates": true,
    "agent_filtering": true,
    "pagination": true
  },
  "limits": {
    "discover_max_limit": 100,
    "search_max_limit": 50,
    "rate_limiting": "Applied per IP address"
  }
}
```

**Example:**
```bash
curl http://localhost:8001/public/info
```

### Public Statistics

Get public statistics about the registry.

```http
GET /public/stats
```

**Response:**
```json
{
  "total_agents": 15,
  "alive_agents": 12,
  "dead_agents": 3,
  "agent_types": {
    "testing": 8,
    "security": 4,
    "monitoring": 3
  },
  "capabilities": {
    "processing": 8,
    "analysis": 6,
    "monitoring": 4
  },
  "communication_modes": {
    "remote": 12,
    "local": 2,
    "hybrid": 1
  }
}
```

**Example:**
```bash
curl http://localhost:8001/public/stats
```

### Get Allowed Agent Types

Get the list of allowed agent types for registration.

```http
GET /public/agent_types
```

**Response:**
```json
{
  "allowed_types": [
    "security",
    "monitoring",
    "automation",
    "networking", 
    "testing"
  ],
  "descriptions": {
    "security": "Security scanning and analysis agents",
    "monitoring": "System and application monitoring agents",
    "automation": "Task automation agents",
    "networking": "Network management and communication agents",
    "testing": "Testing and validation agents"
  }
}
```

**Example:**
```bash
curl http://localhost:8001/public/agent_types
```

### Public Semantic Search

Search for public agents using natural language queries (no authentication required).

```http
POST /public/search
```

**Request Body:**
```json
{
  "query": "Find agents that can process data and analyze information",
  "top_k": 5,
  "min_similarity": 0.7,
  "capabilities": ["processing"],
  "agent_type": "testing"
}
```

**Response:**
```json
[
  {
    "agent_id": "my-agent-001",
    "name": "My testing Agent",
    "agent_type": "testing",
    "capabilities": ["processing", "analysis"],
    "endpoint": "http://localhost:8080",
    "context_brief": "A testing agent for data processing",
    "similarity_score": 0.95,
    "status": "alive",
    "owner": "John Doe",
    "version": "1.0.0"
  }
]
```

**Example:**
```bash
curl -X POST "http://localhost:8001/public/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find agents that can process data",
    "top_k": 5
  }'
```

### Get Public Agent

Get information about a specific public agent.

```http
GET /public/agent/{agent_id}
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Response:**
```json
{
  "agent_id": "my-agent-001",
  "name": "My testing Agent",
  "agent_type": "testing",
  "capabilities": ["processing", "analysis"],
  "endpoint": "http://localhost:8080",
  "description": "A testing agent for data processing",
  "status": "alive"
}
```

**Example:**
```bash
curl http://localhost:8001/public/agent/my-agent-001
```

## 🔗 Connection Management

### Request Agent Connection

Request a connection to a specific agent (Public endpoint).

```http
POST /public/connect/{agent_id}
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Request Body:**
```json
{
  "user_id": "client-001",
  "user_endpoint": "http://localhost:3000",
  "display_name": "My Client Application",
  "additional_info": {
    "priority": "high",
    "timeout": 300
  }
}
```

**Required Fields:**
- `user_id` (string): Unique identifier for the user
- `user_endpoint` (string): User's endpoint URL

**Optional Fields:**
- `display_name` (string): Display name for the user (default: "Anonymous User")
- `additional_info` (object): Additional information about the request

**Response:**
```json
{
  "connection_id": "conn-001",
  "agent_id": "my-agent-001",
  "requester_id": "client-001",
  "status": "pending",
  "message": "Connection request sent to agent",
  "timestamp": "2025-01-XX..."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/public/connect/my-agent-001" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "client-001",
    "user_endpoint": "http://localhost:3000",
    "display_name": "My Client Application"
  }'
```

### Notify Agent Connection

Notify an agent about a connection request (used by agents).

```http
POST /agents/{agent_id}/connection/notify
```

**Path Parameters:**
- `agent_id` (string): The unique identifier of the agent

**Request Body:**
```json
{
  "connection_id": "conn-001",
  "status": "accepted",
  "message": "Connection accepted",
  "metadata": {
    "session_id": "session-001",
    "expires_at": "2025-01-XX..."
  }
}
```

**Response:**
```json
{
  "connection_id": "conn-001",
  "status": "notified",
  "message": "Connection notification sent",
  "timestamp": "2025-01-XX..."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/agents/my-agent-001/connection/notify" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  -d '{
    "connection_id": "conn-001",
    "status": "accepted",
    "message": "Connection accepted"
  }'
```

## 🔐 Authentication Endpoints

### Admin Login

Authenticate as an admin user.

```http
POST /auth/login
```

**Request Body:**
```json
{
  "username": "ARCP",
  "password": "ARCP"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "username": "ARCP",
    "role": "admin"
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "ARCP",
    "password": "ARCP"
  }'
```

### Request Temporary Token

Request a temporary token for agent registration.

```http
POST /auth/agent/request_temp_token
```

**Headers Required:**
- `X-Client-Fingerprint`: Client fingerprint for session binding

**Request Body:**
```json
{
  "agent_id": "my-agent-001",
  "agent_type": "testing",
  "agent_key": "your-agent-registration-key"
}
```

**Response:**
```json
{
  "temp_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "message": "Temporary token issued. Use this token to complete agent registration."
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/auth/agent/request_temp_token" \
  -H "Content-Type: application/json" \
  -H "X-Client-Fingerprint: your-fingerprint-123" \
  -d '{
    "agent_id": "my-agent-001",
    "agent_type": "testing",
    "agent_key": "your-agent-registration-key"
  }'
```

### Admin Logout

Logout admin user and invalidate session.

```http
POST /auth/logout
```

**Headers Required:**
- `Authorization`: Bearer token
- `X-Client-Fingerprint`: Client fingerprint

**Response:**
```json
{
  "status": "success",
  "message": "Logged out successfully"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/auth/logout" \
  -H "Authorization: Bearer <admin-token>" \
  -H "X-Client-Fingerprint: your-fingerprint-123"
```

### Get PIN Status

Check if admin PIN is set.

```http
GET /auth/pin_status
```

**Headers Required:**
- `Authorization`: Bearer admin token

**Response:**
```json
{
  "pin_set": true,
  "pin_verified": false
}
```

**Example:**
```bash
curl http://localhost:8001/auth/pin_status \
  -H "Authorization: Bearer <admin-token>"
```

### Get Session Status

Get current session status and information.

```http
GET /auth/session_status
```

**Headers Required:**
- `Authorization`: Bearer token

**Response:**
```json
{
  "authenticated": true,
  "user_id": "ARCP",
  "role": "admin",
  "session_active": true,
  "expires_at": "2025-01-XX..."
}
```

**Example:**
```bash
curl http://localhost:8001/auth/session_status \
  -H "Authorization: Bearer <token>"
```

**Example:**
```bash
curl -X POST "http://localhost:8001/auth/temp-token" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "agent_id": "my-agent-001",
    "purpose": "agent_operations",
    "expires_in": 3600
  }'
```

**Example:**
```bash
curl http://localhost:8001/auth/session_status \
  -H "Authorization: Bearer <token>"
```

## 🎫 Token Management

### Mint Token

Create a new JWT token (Admin only).

```http
POST /tokens/mint
```

**Headers Required:**
- `Authorization`: Bearer admin token

**Request Body:**
```json
{
  "user_id": "service-user",
  "agent_id": "service-agent",
  "role": "agent",
  "scopes": ["agent:read", "agent:write"]
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "scopes": ["agent:read", "agent:write"]
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/tokens/mint" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "user_id": "service-user",
    "agent_id": "service-agent", 
    "role": "agent",
    "scopes": ["agent:read", "agent:write"]
  }'
```

### Validate Token

Validate a JWT token.

```http
POST /tokens/validate
```

**Request Body:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response:**
```json
{
  "valid": true,
  "expires_at": "2025-01-XX...",
  "user": {
    "user_id": "service-user",
    "role": "agent"
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/tokens/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }'
```

### Validate Token (GET)

Validate a JWT token via GET request.

```http
GET /tokens/validate
```

**Headers Required:**
- `Authorization`: Bearer token to validate

**Response:**
```json
{
  "valid": true,
  "expires_at": "2025-01-XX...",
  "user": {
    "user_id": "service-user",
    "role": "agent"
  }
}
```

**Example:**
```bash
curl http://localhost:8001/tokens/validate \
  -H "Authorization: Bearer <token-to-validate>"
```

### Refresh Token

Refresh an existing JWT token.

```http
POST /tokens/refresh
```

**Request Body:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/tokens/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }'
```

## 📊 Monitoring Endpoints

### Get Agent Registry Statistics

Get detailed statistics about the agent registry (Admin only).

```http
GET /agents/stats
```

**Authentication Required:** Admin token

**Response:**
```json
{
  "registry_statistics": {
    "total_agents": 15,
    "alive_agents": 12,
    "dead_agents": 3,
    "agent_types": {
      "testing": 8,
      "processing": 4,
      "monitoring": 3
    },
    "embeddings_available": 15,
    "redis_connected": true,
    "ai_client_available": true
  },
  "features": {
    "vector_search_enabled": true,
    "redis_storage_enabled": true,
    "metrics_tracking_enabled": true,
    "websocket_broadcasts_enabled": true
  },
  "performance": {
    "active_websocket_connections": 5,
    "vector_embeddings_stored": 15
  }
}
```

**Example:**
```bash
curl http://localhost:8001/agents/stats \
  -H "Authorization: Bearer <admin-token>"
```

### Get System Metrics (Prometheus)

Get system-level metrics and performance data in Prometheus format.

```http
GET /metrics
```

**Response:**
```
# HELP arcp_agents_total Total number of registered agents
# TYPE arcp_agents_total gauge
arcp_agents_total 15

# HELP arcp_agents_alive Number of alive agents
# TYPE arcp_agents_alive gauge
arcp_agents_alive 12

# HELP arcp_requests_total Total number of requests
# TYPE arcp_requests_total counter
arcp_requests_total 1250

# HELP arcp_response_time_seconds Average response time
# TYPE arcp_response_time_seconds histogram
arcp_response_time_seconds_sum 120.5
arcp_response_time_seconds_count 1000
```

**Example:**
```bash
curl http://localhost:8001/metrics
```

## 🚨 Error Responses

ARCP uses standard HTTP status codes and follows RFC 7807 for error responses.

### Error Response Format

ARCP uses RFC 7807 Problem Details format for error responses:

```json
{
  "type": "https://arcp.0x001.tech/problems/validation-failed",
  "title": "Request Validation Failed",
  "status": 422,
  "detail": "Input validation failed",
  "instance": "/agents/register",
  "timestamp": "2025-01-XX...",
  "validation_errors": "[{'type': 'missing', 'loc': ('body', 'agent_id'), 'msg': 'Field required'}]"
}
```

### Common Error Codes

| Status Code | Description | Common Causes |
|-------------|-------------|---------------|
| 400 | Bad Request | Invalid request body, missing required fields |
| 401 | Unauthorized | Missing or invalid authentication token |
| 403 | Forbidden | Insufficient permissions for the operation |
| 404 | Not Found | Agent or resource not found |
| 409 | Conflict | Agent already exists, duplicate registration |
| 422 | Unprocessable Entity | Validation errors, invalid data format |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server-side error, check logs |

### Example Error Responses

#### 400 Bad Request

```json
{
  "type": "https://arcp.example.com/errors/bad-request",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid request body",
  "instance": "/agents/register",
  "errors": [
    {
      "field": "agent_id",
      "message": "Agent ID is required"
    },
    {
      "field": "agent_type",
      "message": "Invalid agent type. Must be one of: testing, security, monitoring, test"
    }
  ],
  "timestamp": "2025-01-XX..."
}
```

#### 401 Unauthorized

```json
{
  "type": "https://arcp.example.com/errors/unauthorized",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication required",
  "instance": "/agents/register",
  "timestamp": "2025-01-XX..."
}
```

#### 404 Not Found

```json
{
  "type": "https://arcp.example.com/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Agent not found",
  "instance": "/agents/non-existent-agent",
  "timestamp": "2025-01-XX..."
}
```

#### 409 Conflict

```json
{
  "type": "https://arcp.example.com/errors/conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Agent already exists",
  "instance": "/agents/register",
  "timestamp": "2025-01-XX..."
}
```

#### 429 Too Many Requests

```json
{
  "type": "https://arcp.example.com/errors/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Rate limit exceeded",
  "instance": "/agents/register",
  "retry_after": 60,
  "timestamp": "2025-01-XX..."
}
```

## 🔧 Rate Limiting

ARCP implements rate limiting to prevent abuse and ensure fair usage.

### Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
X-RateLimit-Window: 3600
```

### Rate Limit Configuration

```bash
# Rate limiting settings in .env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600
RATE_LIMIT_BURST=10
```

## 📝 Request/Response Examples

### Complete Agent Registration Flow

```bash
# 1. Register agent
curl -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-001",
    "name": "My testing Agent",
    "agent_type": "testing",
    "capabilities": ["processing", "analysis"],
    "endpoint": "http://localhost:8080",
    "description": "A testing agent for data processing"
  }'

# Response
{
  "agent_id": "my-agent-001",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "status": "registered",
  "message": "Agent registered successfully",
  "timestamp": "2025-01-XX..."
}

# 2. Send heartbeat
curl -X POST "http://localhost:8001/agents/my-agent-001/heartbeat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -d '{
    "status": "alive",
    "metadata": {
      "cpu_usage": 45.2,
      "memory_usage": 67.8
    }
  }'

# 3. Update metrics
curl -X POST "http://localhost:8001/agents/my-agent-001/metrics" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -d '{
    "metrics": {
      "requests_processed": 1250,
      "average_response_time": 0.15,
      "error_rate": 0.02
    }
  }'

# 4. Get agent info
curl http://localhost:8001/agents/my-agent-001

# 5. Unregister agent
curl -X DELETE "http://localhost:8001/agents/my-agent-001" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

### Client Discovery Flow

```bash
# 1. Get system info
curl http://localhost:8001/system/info

# 2. Get allowed agent types
curl http://localhost:8001/system/agent-types

# 3. Discover public agents
curl "http://localhost:8001/public/agents?agent_type=testing"

# 4. Get specific agent
curl http://localhost:8001/public/agents/my-agent-001

# 5. Request connection
curl -X POST "http://localhost:8001/agents/my-agent-001/connection/request" \
  -H "Content-Type: application/json" \
  -d '{
    "requester_id": "client-001",
    "requester_name": "My Client Application",
    "purpose": "Data processing task"
  }'
```

## 🧪 Testing the API

### Using curl

```bash
# Test health endpoint
curl -i http://localhost:8001/health

# Test with authentication
curl -i -H "Authorization: Bearer <token>" http://localhost:8001/agents

# Test with query parameters
curl -i "http://localhost:8001/agents?page=1&page_size=10&agent_type=testing"

# Test POST with JSON
curl -i -X POST "http://localhost:8001/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test-agent", "name": "Test Agent", "agent_type": "test"}'
```

### Using Python requests

```python
import requests
import json

# Base URL
base_url = "http://localhost:8001"

# Test health
response = requests.get(f"{base_url}/health")
print(f"Health: {response.status_code} - {response.json()}")

# Test public system info
response = requests.get(f"{base_url}/public/info")
print(f"Public System Info: {response.status_code} - {response.json()}")

# Test agent registration (requires temp token first)
# First get temp token
temp_token_response = requests.post(
    f"{base_url}/auth/agent/request_temp_token",
    json={
        "agent_id": "test-agent-001",
        "agent_type": "testing",
        "agent_key": "test-agent-001"
    }
)
temp_token = temp_token_response.json().get("temp_token")

# Then register agent
agent_data = {
    "agent_id": "test-agent-001",
    "name": "Test Agent",
    "agent_type": "testing",
    "endpoint": "http://localhost:8080",
    "context_brief": "A test agent for API validation",
    "capabilities": ["testing"],
    "owner": "test-owner",
    "public_key": "test-public-key-123456789012345678901234567890",
    "metadata": {"version": "1.0.0"},
    "version": "1.0.0",
    "communication_mode": "remote"
}

response = requests.post(
    f"{base_url}/agents/register",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {temp_token}"
    },
    data=json.dumps(agent_data)
)

if response.status_code == 200:
    result = response.json()
    print(f"Agent registered: {result['agent_id']}")
    agent_token = result['access_token']
    
    # Test heartbeat
    response = requests.post(
        f"{base_url}/agents/{result['agent_id']}/heartbeat",
        headers={"Authorization": f"Bearer {agent_token}"}
    )
    
    print(f"Heartbeat: {response.status_code} - {response.json()}")
    
    # Test metrics update
    metrics_data = {
        "metrics": {
            "requests_processed": 100,
            "average_response_time": 0.15,
            "error_rate": 0.02
        }
    }
    
    response = requests.post(
        f"{base_url}/agents/{result['agent_id']}/metrics",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {agent_token}"
        },
        data=json.dumps(metrics_data)
    )
    
    print(f"Metrics: {response.status_code} - {response.json()}")
    
    # Test public discovery
    response = requests.get(f"{base_url}/public/discover")
    print(f"Public Discovery: {response.status_code} - Found {len(response.json())} agents")
    
    # Clean up - unregister agent
    response = requests.delete(
        f"{base_url}/agents/{result['agent_id']}",
        headers={"Authorization": f"Bearer {agent_token}"}
    )
    print(f"Cleanup: {response.status_code} - {response.json()}")
else:
    print(f"Registration failed: {response.status_code} - {response.text}")
```

## 🔌WebSocket Endpoints

ARCP provides WebSocket endpoints for real-time communication and updates.

### Agent WebSocket Connection

Real-time agent updates and communication.

```
WebSocket: /agents/ws
```

**Authentication Required:** Agent token via initial auth message

**Connection Flow:**
1. Connect to WebSocket endpoint
2. Server sends `auth_required` message
3. Client sends authentication token
4. Server validates and sends `auth_success`
5. Server sends initial agents list
6. Real-time updates are sent as agents change

**Example Authentication Message:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Example JavaScript Usage:**
```javascript
const ws = new WebSocket('ws://localhost:8001/agents/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'auth_required') {
    // Send authentication token
    ws.send(JSON.stringify({
      token: 'your-agent-token-here'
    }));
  } else if (data.type === 'auth_success') {
    console.log('Authentication successful');
  } else if (Array.isArray(data)) {
    // Agents list update
    console.log('Agents updated:', data);
  }
};

// Send ping to keep connection alive
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send('ping');
  }
}, 30000);
```

### Dashboard WebSocket Connection

Real-time dashboard updates (if dashboard WebSocket is available).

```
WebSocket: /dashboard/ws
```

### Public WebSocket Connection

Public real-time updates (if public WebSocket is available).

```
WebSocket: /public/ws
```

**Note:** WebSocket endpoints require proper authentication and support ping/pong for keepalive. For detailed WebSocket API documentation, see the [WebSocket API Reference](websocket-api.md).

## 📚 Next Steps

Now that you understand the REST API:

1. **[WebSocket API Reference](websocket-api.md)** - Real-time communication
2. **[Agent Development Guide](../user-guide/agent-development.md)** - Build agents that use this API
3. **[Client Library Guide](../user-guide/client-library.md)** - Use the Python client

## 💡 Tips and Best Practices

1. **Always handle errors** - Check HTTP status codes and error responses
2. **Use pagination** - For large datasets, use page and page_size parameters
3. **Implement retry logic** - Handle temporary failures gracefully
4. **Cache responses** - Cache system info and agent lists when appropriate
5. **Monitor rate limits** - Check rate limit headers and implement backoff
6. **Validate input** - Always validate data before sending requests
7. **Use HTTPS in production** - Always use secure connections
8. **Keep tokens secure** - Store JWT tokens securely and rotate them regularly
9. **Log API calls** - Log requests and responses for debugging
10. **Test thoroughly** - Test all endpoints with various scenarios

Ready to explore real-time communication? Check out the [WebSocket API Reference](websocket-api.md)!