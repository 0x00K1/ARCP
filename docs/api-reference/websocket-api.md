# WebSocket API Guide

ARCP provides real-time WebSocket APIs for live updates, agent monitoring, and interactive communication. This guide covers all WebSocket endpoints with practical examples.

## 🔌 WebSocket Endpoints

ARCP provides three types of WebSocket connections:

- **Public WebSocket** (`/public/ws`) - No authentication required
- **Agent WebSocket** (`/agents/ws`) - Requires **agent token**
- **Dashboard WebSocket** (`/dashboard/ws`) - Requires **admin credentials**

### Authentication Summary

| WebSocket Type | Authentication Method | Token Source |
|----------------|----------------------|--------------|
| Public | None | N/A |
| Agent | Agent Token | From agent registration flow |
| Dashboard | Admin Credentials | From admin login |

## 🌐 Public WebSocket

The public WebSocket provides real-time updates about the agent ecosystem without requiring authentication.

### Connection

```javascript
// JavaScript example
const ws = new WebSocket('ws://localhost:8001/public/ws');

ws.onopen = function(event) {
    console.log('Connected to public WebSocket');
    
    // Send ping to test connection
    ws.send('ping');
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
    
    // Handle different message types
    switch(message.type) {
        case 'welcome':
            console.log('Welcome message:', message.message);
            console.log('Available features:', message.features);
            break;
        case 'stats_update':
            console.log('System stats:', message.data);
            break;
        case 'discovery_data':
            console.log('Discovery data:', message.data);
            break;
        case 'agents_update':
            console.log('Agents update:', message.data);
            break;
        case 'pong':
            console.log('Pong received:', message.timestamp);
            break;
    }
};

ws.onclose = function(event) {
    console.log('WebSocket closed:', event.code, event.reason);
};

ws.onerror = function(error) {
    console.error('WebSocket error:', error);
};
```

### Python Client

```python
import asyncio
import json
from arcp import ARCPClient

async def public_websocket_example():
    client = ARCPClient("http://localhost:8001")
    
    print("Connecting to public WebSocket...")
    
    message_count = 0
    async for message in client.websocket_public():
        message_count += 1
        print(f"Message {message_count}: {message.get('type', 'unknown')}")
        
        # Handle different message types
        if message.get('type') == 'welcome':
            print(f"  Welcome: {message.get('message', '')}")
            print(f"  Features: {message.get('features', [])}")
            
        elif message.get('type') == 'stats_update':
            data = message.get('data', {})
            print(f"  System stats: {data.get('total_agents', 0)} agents")
            print(f"  Alive agents: {data.get('alive_agents', 0)}")
            
        elif message.get('type') == 'discovery_data':
            data = message.get('data', {})
            pagination = data.get('pagination', {})
            print(f"  Discovery: {pagination.get('total_agents', 0)} total agents")
            
        elif message.get('type') == 'agents_update':
            data = message.get('data', {})
            print(f"  Agents update: {data.get('total_count', 0)} agents")
            
        elif message.get('type') == 'pong':
            print(f"  Pong received at: {message.get('timestamp', '')}")
            
        # Stop after 10 messages
        if message_count >= 10:
            break
    
    print(f"Received {message_count} messages")

asyncio.run(public_websocket_example())
```

### Message Types

#### Welcome Message

The first message received when connecting to the public WebSocket:

```json
{
  "type": "welcome",
  "message": "Connected to ARCP Public API WebSocket",
  "features": ["agent_updates", "public_stats", "discovery_events", "paginated_discovery"],
  "commands": {
    "ping": "Send ping to check connection",
    "get_discovery": "Get agent discovery data with pagination"
  },
  "pagination": {
    "default_page_size": 30,
    "max_page_size": 100,
    "usage": "Send {type: 'get_discovery', page: 1, page_size: 30, agent_type: 'optional'}"
  }
}
```

#### Stats Update

```json
{
  "type": "stats_update",
  "timestamp": 1757269784.384039,
  "data": {
    "total_agents": 15,
    "alive_agents": 12,
    "dead_agents": 3,
    "agent_types_count": 3,
    "available_types": ["testing", "security", "monitoring"],
    "system_status": "operational"
  }
}
```

#### Discovery Data

```json
{
  "type": "discovery_data",
  "timestamp": 1757269754.2882402,
  "data": {
    "agents": [
      {
        "agent_id": "demo-agent-001",
        "name": "ARCP Demo Agent",
        "agent_type": "testing",
        "endpoint": "http://localhost:8010",
        "capabilities": ["echo", "compute", "status", "demo", "testing", "examples"],
        "context_brief": "A demonstration agent showing proper ARCP integration patterns.",
        "version": "1.0.0",
        "owner": "ARCP Examples",
        "public_key": "demo-public-key-for-testing-purposes-only-at-least-32-chars",
        "metadata": {
          "version": "1.0.0",
          "author": "ARCP Examples",
          "description": "A demonstration agent showing proper ARCP integration patterns.",
          "tags": ["demo", "testing", "example"],
          "deployment_mode": "internal",
          "demo_agent": true,
          "language": "python",
          "framework": "fastapi",
          "created_at": "2025-09-07T17:10:35.684352"
        },
        "communication_mode": "remote",
        "status": "alive",
        "last_seen": "2025-09-07 21:28:48.934468",
        "registered_at": "2025-09-07 20:10:37.497558"
      }
    ],
    "pagination": {
      "current_page": 1,
      "page_size": 5,
      "total_agents": 1,
      "total_pages": 1,
      "has_next": false,
      "has_previous": false,
      "next_page": null,
      "previous_page": null
    },
    "filters": {
      "agent_type": null
    }
  }
}
```

#### Agents Update

Sent when agent state changes occur (registration, unregistration, status updates):

```json
{
  "type": "agents_update",
  "timestamp": 1757270868.050447,
  "data": {
    "agents": [
      {
        "agent_id": "demo-agent-001",
        "name": "ARCP Demo Agent",
        "agent_type": "testing",
        "endpoint": "http://localhost:8010",
        "capabilities": ["echo", "compute", "status", "demo", "testing", "examples"],
        "status": "alive",
        "last_seen": "2025-09-07 21:28:48.934468",
        "registered_at": "2025-09-07 20:10:37.497558"
      }
    ],
    "total_count": 1
  }
}
```

## 🤖 Agent WebSocket

The agent WebSocket requires authentication and provides real-time updates for registered agents.

### Authentication Flow

```javascript
// JavaScript example with authentication
const ws = new WebSocket('ws://localhost:8001/agents/ws');

ws.onopen = function(event) {
    console.log('Connected to agent WebSocket');
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    if (message.type === 'auth_required') {
        console.log('Authentication required');
        
        // Send authentication token
        ws.send(JSON.stringify({
            token: 'your-jwt-token-here'
        }));
        
    } else if (message.type === 'auth_success') {
        console.log('Agent authentication successful');
        
    } else if (message.type === 'auth_error') {
        console.error('Authentication failed:', message.message);
        
    } else {
        // Handle other message types
        console.log('Agent message:', message);
    }
};
```

### Python Client

```python
import asyncio
from arcp import ARCPClient

async def agent_websocket_example():
    client = ARCPClient("http://localhost:8001")
    
    # Register the agent
    registration_response = await client.register_agent(
        agent_id="my-agent-001",
        name="My testing Agent",
        agent_type="testing",
        endpoint="http://localhost:8010",
        capabilities=["processing", "analysis"],
        context_brief="A testing agent for WebSocket demo",
        version="1.0.0",
        owner="Test User",
        public_key="test-public-key-that-is-at-least-32-characters-long-for-validation",
        communication_mode="remote",
        metadata={"environment": "test", "purpose": "websocket-demo"},
        agent_key="test-agent-001"
    )
    
    print(f"Agent registered successfully: {registration_response.agent_id}")
    
    print("Connecting to agent WebSocket...")
    
    message_count = 0
    async for message in client.websocket_agent():
        message_count += 1
        print(f"Agent message {message_count}: {message}")
        
        # Handle different message types - message might be a list or dict
        if isinstance(message, list):
            print(f"  Received agent list with {len(message)} agents")
            for agent in message:
                if isinstance(agent, dict) and 'agent_id' in agent:
                    print(f"    - Agent: {agent.get('agent_id')} ({agent.get('status', 'unknown')})")
        elif isinstance(message, dict):
            # Handle authentication and control messages
            if message.get('type') == 'auth_required':
                print(f"  Authentication required: {message.get('message')}")
                
            elif message.get('type') == 'auth_success':
                print(f"  Authentication successful: {message.get('message')}")
                
            elif message.get('type') == 'auth_error':
                print(f"  Authentication failed: {message.get('message')}")
                
            elif message.get('type') == 'pong':
                print(f"  Pong received at: {message.get('timestamp', '')}")
            
            else:
                print(f"  Other message type: {message.get('type', 'unknown')}")
            
        # Stop after 5 messages
        if message_count >= 5:
            break
    
    print(f"Received {message_count} agent messages")

asyncio.run(agent_websocket_example())
```

### Agent Message Types


#### Agent Data List

The agent WebSocket can return a list of agent data:

```json
[
  {
    "agent_id": "demo-agent-001",
    "name": "ARCP Demo Agent",
    "agent_type": "testing",
    "status": "alive",
    "capabilities": ["echo", "compute", "status", "demo", "testing", "examples"],
    "endpoint": "http://localhost:8010",
    "last_seen": "2025-01-07 07:07:02.592731"
  }
  ...
]
```

#### Authentication Messages

After connecting, the agent WebSocket first requires authentication:

```json
{
  "type": "auth_required",
  "message": "Send your authentication token"
}
```

Send your token:
```json
{
  "token": "your-jwt-token-here"
}
```

Success response:
```json
{
  "type": "auth_success",
  "message": "Authentication successful"
}
```

Error response:
```json
{
  "type": "auth_error",
  "message": "Invalid token"
}
```

## 📊 Dashboard WebSocket

The dashboard WebSocket provides real-time updates for the web dashboard interface.

### Connection

```javascript
// JavaScript example for dashboard
const ws = new WebSocket('ws://localhost:8001/dashboard/ws');

ws.onopen = function(event) {
    console.log('Connected to dashboard WebSocket');
    
    // Send authentication
    ws.send(JSON.stringify({
        type: 'auth',
        token: 'your-admin-jwt-token'
    }));
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    // Handle different dashboard frame types
    switch(message.type) {
        case 'monitoring':
            // System monitoring data (agents, performance metrics)
            updateMonitoringData(message.data);
            break;
        case 'health':
            // System health status and component health
            updateHealthStatus(message.data);
            break;
        case 'agents':
            // Agent information and status
            updateAgentsData(message.data);
            break;
        case 'logs':
            // System logs
            updateLogsDisplay(message.data);
            break;
        case 'alert':
            // System alerts and notifications
            handleAlerts(message.data);
            break;
        case 'pause_ack':
        case 'resume_ack':
        case 'refresh_ack':
            // Acknowledgment messages for client requests
            handleAcknowledgment(message);
            break;
        default:
            console.log('Unknown dashboard message type:', message.type);
    }
};
```

### Dashboard Message Types

The dashboard WebSocket sends structured frames with the following types:

#### Authentication

Required first message to authenticate with admin credentials:

```json
{
  "type": "auth",
  "token": "your-admin-jwt-token"
}
```

#### Monitoring Frame

System monitoring data sent at regular intervals:

```json
{
  "type": "monitoring",
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {
    "total_requests": 1500,
    "avg_response_time": 0.75,
    "error_rate": 0.02,
    "agent_count": 5,
    "resource_utilization": {
      "cpu": 5.2,
      "memory": 10.5,
      "network": 12.1,
      "storage": 45.8
    },
    "agent_metrics": [...]
  }
}
```

#### Health Frame

System health status and component health:

```json
{
  "type": "health",
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {
    "status": "healthy",
    "reason": "All systems operational",
    "components": {
      "storage": {
        "status": "healthy",
        "redis": "connected"
      },
      "agents": {
        "active": 5,
        "connectivity_ratio": 1.0,
        "status": "healthy",
        "total": 5
      },
      "ai_services": {
        "azure_openai": "available",
        "status": "healthy"
      }
    }
  }
}
```

#### Agents Frame

Current agent information and status:

```json
{
  "type": "agents", 
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {
    "agents": [
      "0" {
        "agent_id": "agent-001",
        "name": "Test Agent",
        "agent_type": "testing",
        "status": "alive",
        "capabilities": ["echo", "compute"],
        "endpoint": "http://localhost:8010",
        "last_seen": "2025-01-07T10:29:45Z",
        ...
      }
    ],
    "total_count": 5,
    "active_count": 5,
    "agent_types": {
      "testing": 3,
      "monitoring": 2
    },
    "status_summary": {
      "alive": 5,
      "dead": 0
    }
  }
}
```

#### Logs Frame

System logs and events:

```json
{
  "type": "logs",
  "timestamp": "2025-01-07T10:30:00Z", 
  "data": {
    "logs": [
      "0" {
        "agent_id": "demo-agent-001",
        "agent_type": "testing",
        "client_ip": "127.0.0.1",
        "event_type": "agent_login_success",
        "level": "INFO",
        "message": "Agent authenticated successfully: demo-agent-001 (testing)",
        "source": "auth",
        "timestamp": "2025-01-07T10:28:00Z"
      }
    ],
    "count": 25,
    "last_updated": "2025-01-07T10:30:00Z"
  }
}
```

#### Alert Frame

System alerts and notifications:

```json
{
  "type": "alert",
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {
    "alerts": [
      "0" {
        "id": "alert-001",
        "title": "High Response Time",
        "message": "High response time: 1.7ms (approaching critical threshold: 2000ms)",
        "severity": "warning",
        "type": "performance",
        "timestamp": "2025-01-07T10:30:00Z"
      }
    ]
  }
}
```

#### Client Request Messages

The dashboard WebSocket also handles various client requests:

```json
// Pause monitoring
{"type": "pause_monitoring"}

// Resume monitoring  
{"type": "resume_monitoring"}

// Request fresh data
{"type": "refresh_request"}

// Request agents data
{"type": "agents_request"}

// Clear logs
{"type": "clear_logs"}

// Clear alerts
{"type": "clear_alerts"}

// Add dashboard log
{
  "type": "dashboard_log",
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {
    "level": "SUCS",
    "message": "Security: PIN verification successful",
    "timestamp": "2025-01-07T10:30:00Z"
  }
}
```

#### Acknowledgment Messages

The dashboard sends acknowledgment responses:

```json
{
  "type": "pause_ack",
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {"status": "paused"}
}

{
  "type": "refresh_ack", 
  "timestamp": "2025-01-07T10:30:00Z",
  "data": {"status": "completed", "message": "Fresh data sent"}
}
```

## 🔧 WebSocket Configuration

### Ping/Pong Behavior

The WebSocket endpoints support both plain text and JSON format ping/pong:

- **Plain text ping**: Send `"ping"` → Receive `"pong"`
- **JSON ping**: Send `{"type": "ping"}` → Receive `{"type": "pong", "timestamp": 1234567890.123}`

The public WebSocket also sends a welcome message immediately upon connection with API information and available commands.

### Server Configuration

```bash
# WebSocket settings in .env
WEBSOCKET_INTERVAL=30                    # Update interval in seconds
WEBSOCKET_TIMEOUT=30                     # Connection timeout in seconds
WEBSOCKET_PING_INTERVAL=30               # Ping interval in seconds
WEBSOCKET_MAX_CONNECTIONS=100            # Maximum connections

# Dashboard WebSocket
DASHBOARD_WS_INTERVAL=5                  # Dashboard update interval
DASHBOARD_WS_TIMEOUT=30                  # Dashboard timeout
DASHBOARD_WS_PING_INTERVAL=30            # Dashboard ping interval
DASHBOARD_WS_MAX_CONNECTIONS=5           # Dashboard max connections

# Agent WebSocket
AGENT_WS_INTERVAL=5                      # Agent update interval
AGENT_WS_TIMEOUT=30                      # Agent timeout
AGENT_WS_PING_INTERVAL=30                # Agent ping interval
AGENT_WS_MAX_CONNECTIONS=100             # Agent max connections

# Public WebSocket
PUBLIC_WS_INTERVAL=30                    # Public update interval
PUBLIC_WS_TIMEOUT=30                     # Public timeout
PUBLIC_WS_PING_INTERVAL=30               # Public ping interval
PUBLIC_WS_MAX_CONNECTIONS=100            # Public max connections
```

## 🛠️ Advanced WebSocket Usage

### Custom WebSocket Client

```python
import asyncio
import json
import websockets
from typing import Dict, Any, Optional

class ARCPWebSocketClient:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.replace('http', 'ws')
        self.token = token
        self.websocket = None
        self.running = False
    
    async def connect_public(self):
        """Connect to public WebSocket"""
        url = f"{self.base_url}/public/ws"
        self.websocket = await websockets.connect(url)
        self.running = True
        
        # Send initial ping
        await self.websocket.send("ping")
        
        # Listen for messages
        async for message in self.websocket:
            if not self.running:
                break
            
            try:
                data = json.loads(message)
                await self.handle_message(data)
            except json.JSONDecodeError:
                # Handle non-JSON messages (like pong)
                if message == "pong":
                    print("Received pong")
    
    async def connect_agent(self):
        """Connect to agent WebSocket with authentication"""
        url = f"{self.base_url}/agents/ws"
        self.websocket = await websockets.connect(url)
        self.running = True
        
        # Wait for auth request
        auth_request = await self.websocket.recv()
        auth_data = json.loads(auth_request)
        
        if auth_data.get('type') == 'auth_required':
            # Send authentication token
            await self.websocket.send(json.dumps({
                'token': self.token
            }))
            
            # Wait for auth response
            auth_response = await self.websocket.recv()
            auth_result = json.loads(auth_response)
            
            if auth_result.get('type') == 'auth_success':
                print("Agent WebSocket authenticated")
            else:
                print(f"Authentication failed: {auth_result.get('message')}")
                return
        
        # Listen for messages
        async for message in self.websocket:
            if not self.running:
                break
            
            try:
                data = json.loads(message)
                await self.handle_message(data)
            except json.JSONDecodeError:
                if message == "ping":
                    await self.websocket.send("pong")
    
    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        message_type = message.get('type', 'unknown')
        
        if message_type == 'stats_update':
            await self.handle_stats_update(message.get('data', {}))
        elif message_type == 'agents_update':
            await self.handle_agents_update(message.get('data', {}))
        elif message_type == 'auth_required':
            await self.handle_auth_required(message)
        elif message_type == 'auth_success':
            await self.handle_auth_success(message)
        elif message_type == 'auth_error':
            await self.handle_auth_error(message)
        else:
            print(f"Unknown message type: {message_type}")
    
    async def handle_stats_update(self, data: Dict[str, Any]):
        """Handle stats update messages"""
        print(f"Stats update: {data.get('total_agents', 0)} agents")
        print(f"   Alive: {data.get('alive_agents', 0)}")
        print(f"   Dead: {data.get('dead_agents', 0)}")
    
    async def handle_agents_update(self, data: Dict[str, Any]):
        """Handle agents update messages"""
        print(f"Agents update: {data.get('total_count', 0)} agents")
    
    async def handle_auth_required(self, message: Dict[str, Any]):
        """Handle authentication required messages"""
        print(f"Authentication required: {message.get('message')}")
    
    async def handle_auth_success(self, message: Dict[str, Any]):
        """Handle authentication success messages"""
        print(f"Authentication successful: {message.get('message')}")
    
    async def handle_auth_error(self, message: Dict[str, Any]):
        """Handle authentication error messages"""
        print(f"Authentication failed: {message.get('message')}")
    
    async def send_message(self, message: Dict[str, Any]):
        """Send a message through the WebSocket"""
        if self.websocket and self.running:
            await self.websocket.send(json.dumps(message))
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        if self.websocket:
            await self.websocket.close()

# Usage
async def custom_websocket_example():
    client = ARCPWebSocketClient("http://localhost:8001")
    
    try:
        # Connect to public WebSocket
        await client.connect_public()
        
        # Keep running for 30 seconds
        await asyncio.sleep(30)
        
    finally:
        await client.disconnect()

asyncio.run(custom_websocket_example())
```

### WebSocket with Reconnection

```python
import asyncio
import json
import websockets
from typing import Optional, Dict, Any

class ReconnectingWebSocketClient:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.replace('http', 'ws')
        self.token = token
        self.websocket = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
    
    async def connect_with_reconnect(self):
        """Connect with automatic reconnection"""
        while self.running:
            try:
                await self.connect()
                await self.listen()
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
            except Exception as e:
                print(f"WebSocket error: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def connect(self):
        """Establish WebSocket connection"""
        self.websocket = await websockets.connect(self.base_url)
        print("WebSocket connected")
    
    async def listen(self):
        """Listen for messages"""
        async for message in self.websocket:
            if not self.running:
                break
            
            try:
                data = json.loads(message)
                await self.handle_message(data)
            except json.JSONDecodeError:
                if message == "ping":
                    await self.websocket.send("pong")
    
    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming messages"""
        print(f"Message: {message.get('type', 'unknown')}")
    
    def start(self):
        """Start the WebSocket client"""
        self.running = True
        return asyncio.create_task(self.connect_with_reconnect())
    
    def stop(self):
        """Stop the WebSocket client"""
        self.running = False
        if self.websocket:
            asyncio.create_task(self.websocket.close())

# Usage
async def reconnecting_example():
    client = ReconnectingWebSocketClient("ws://localhost:8001/public/ws")
    
    # Start client
    task = client.start()
    
    try:
        # Keep running for 2 minutes
        await asyncio.sleep(120)
    finally:
        client.stop()
        task.cancel()

asyncio.run(reconnecting_example())
```


## 🧪 Testing WebSocket Connections

### WebSocket Test Client

```python
import asyncio
import json
import websockets

class WebSocketTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.replace('http', 'ws')
        self.results = []
    
    async def test_public_websocket(self):
        """Test public WebSocket connection"""
        print("Testing public WebSocket...")
        
        try:
            async with websockets.connect(f"{self.base_url}/public/ws") as ws:
                ping_pong_success = False
                
                # Wait for messages
                message_count = 0
                async for message in ws:
                    message_count += 1
                    try:
                        data = json.loads(message)
                        print(f"Received message: {data.get('type', 'unknown')}")
                        self.results.append(("public_websocket", "message_received", "success"))
                    except json.JSONDecodeError:
                        print(f"Received non-JSON: {message}")
                        if message == "ping":
                            # Respond to server ping with pong
                            await ws.send("pong")
                            print("Responded to ping with pong")
                            ping_pong_success = True
                    
                    if message_count >= 3:
                        break
                
                if ping_pong_success:
                    print("Ping/pong successful")
                    self.results.append(("public_websocket", "ping_pong", "success"))
                else:
                    print("No ping received from server")
                    self.results.append(("public_websocket", "ping_pong", "failed"))
                
                print(f"Received {message_count} messages")
                
        except Exception as e:
            print(f"Public WebSocket test failed: {e}")
            self.results.append(("public_websocket", "connection", "failed"))
    
    async def test_agent_websocket(self, token: str):
        """Test agent WebSocket connection"""
        print("Testing agent WebSocket...")
        
        try:
            async with websockets.connect(f"{self.base_url}/agents/ws") as ws:
                # Wait for auth request
                auth_request = await ws.recv()
                auth_data = json.loads(auth_request)
                
                if auth_data.get('type') == 'auth_required':
                    # Send token
                    await ws.send(json.dumps({'token': token}))
                    
                    # Wait for auth response
                    auth_response = await ws.recv()
                    auth_result = json.loads(auth_response)
                    
                    if auth_result.get('type') == 'auth_success':
                        print("Agent WebSocket authentication successful")
                        self.results.append(("agent_websocket", "authentication", "success"))
                    else:
                        print("Agent WebSocket authentication failed")
                        self.results.append(("agent_websocket", "authentication", "failed"))
                        return
                
                # Wait for messages
                message_count = 0
                async for message in ws:
                    message_count += 1
                    try:
                        data = json.loads(message)
                        print(f"Received agent message: {data.get('type', 'unknown')}")
                        self.results.append(("agent_websocket", "message_received", "success"))
                    except json.JSONDecodeError:
                        if message == "ping":
                            await ws.send("pong")
                    
                    if message_count >= 3:
                        break
                
                print(f"Received {message_count} agent messages")
                
        except Exception as e:
            print(f"Agent WebSocket test failed: {e}")
            self.results.append(("agent_websocket", "connection", "failed"))
    
    def print_results(self):
        """Print test results"""
        print("\nWebSocket Test Results:")
        print("=" * 50)
        
        for test_type, test_name, result in self.results:
            print(f"{test_type}: {test_name} - {result}")

# Usage
async def test_websockets():
    tester = WebSocketTester("http://localhost:8001")
    
    # Test public WebSocket
    await tester.test_public_websocket()
    
    # Test agent WebSocket (requires valid token)
    # await tester.test_agent_websocket("your-jwt-token")
    
    # Print results
    tester.print_results()

asyncio.run(test_websockets())
```

## 🚀 Performance Optimization

### WebSocket Connection Pooling

```python
import asyncio
import websockets
from typing import List

class WebSocketPool:
    def __init__(self, base_url: str, pool_size: int = 5):
        self.base_url = base_url.replace('http', 'ws')
        self.pool_size = pool_size
        self.connections: List[websockets.WebSocketServerProtocol] = []
        self.available: asyncio.Queue = asyncio.Queue()
    
    async def initialize(self):
        """Initialize connection pool"""
        for _ in range(self.pool_size):
            ws = await websockets.connect(f"{self.base_url}/public/ws")
            self.connections.append(ws)
            await self.available.put(ws)
    
    async def get_connection(self):
        """Get an available connection from the pool"""
        return await self.available.get()
    
    async def return_connection(self, ws):
        """Return a connection to the pool"""
        await self.available.put(ws)
    
    async def close_all(self):
        """Close all connections"""
        for ws in self.connections:
            await ws.close()

# Usage
async def websocket_pool_example():
    pool = WebSocketPool("http://localhost:8001", pool_size=3)
    
    try:
        await pool.initialize()
        
        # Use connections from pool
        for i in range(5):
            ws = await pool.get_connection()
            try:
                await ws.send("ping")
                response = await ws.recv()
                print(f"Request {i+1}: {response}")
            finally:
                await pool.return_connection(ws)
    
    finally:
        await pool.close_all()

asyncio.run(websocket_pool_example())
```

## 🆘 Troubleshooting

### Common Issues

#### Connection Refused

```bash
# Check if ARCP server is running
curl http://localhost:8001/health

# Check WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==" -H "Sec-WebSocket-Version: 13" http://localhost:8001/public/ws
```

#### Authentication Errors

```python
# Check token validity
import asyncio
from arcp import ARCPClient

async def check_token():
    client = ARCPClient("http://localhost:8001")
    result = await client.validate_token("fewfwfewfewfew")
    print(f"Token valid: {result}")

asyncio.run(check_token())
```
#### Message Parsing Errors

```python
# Handle non-JSON messages gracefully
async def handle_message_safely(message: str):
    try:
        data = json.loads(message)
        return data
    except json.JSONDecodeError:
        # Handle non-JSON messages (like pong)
        if message == "pong":
            return {"type": "pong"}
        elif message == "ping":
            return {"type": "ping"}
        else:
            print(f"Unknown non-JSON message: {message}")
            return None
```


**Verification**: Ensure `total_agents = alive_agents + dead_agents` in all stats updates.

## 📚 Next Steps

Now that you understand WebSocket communication:

1. **[API Reference](../api-reference/rest-api.md)** - Complete API documentation
2. **[Agent Development Guide](../user-guide/agent-development.md)** - Build agents with WebSocket support
3. **[Client Library Guide](../user-guide/client-library.md)** - Use WebSocket in your applications

## 💡 Tips and Best Practices

1. **Handle reconnections** - Implement automatic reconnection logic
2. **Validate messages** - Always validate incoming WebSocket messages
3. **Use ping/pong** - Implement heartbeat to detect dead connections
4. **Handle errors gracefully** - Catch and handle WebSocket errors
5. **Limit connection count** - Respect server connection limits
6. **Use connection pooling** - For high-throughput applications
7. **Monitor performance** - Track WebSocket connection health
8. **Implement backoff** - Use exponential backoff for reconnections
9. **Test thoroughly** - Test WebSocket connections under various conditions
10. **Document message formats** - Document your WebSocket message protocols

Ready to explore the complete API? Check out the [API Reference](../api-reference/rest-api.md)!