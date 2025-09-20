# Monitoring and Observability Guide

This guide covers comprehensive monitoring and observability for ARCP production deployments using Prometheus, Grafana, and Jaeger.

## 📊 Monitoring Stack Overview

ARCP provides a complete monitoring stack:

- **Prometheus** - Metrics collection and storage
- **Grafana** - Metrics visualization and dashboards
- **Jaeger** - Distributed tracing
- **Redis Exporter** - Redis metrics
- **ARCP Metrics** - Application-specific metrics

> **💡 Tip**: For all authentication and metrics operations, we recommend using the **ARCP client library** (`from arcp import ARCPClient`) instead of direct HTTP requests. The client library handles authentication, token management, and provides convenient methods like `get_system_metrics()`, `login_admin()`, and `monitor_system()`.

## 🔐 Metrics Access & Authentication

**Important**: The ARCP metrics endpoint (`/metrics`) requires admin authentication for security.

### Admin Authentication Required

To access metrics, you must:

1. **Login as admin** using the `/auth/login` endpoint
2. **Include the JWT token** in the `Authorization: Bearer <token>` header  
3. **Include client fingerprint** in the `X-Client-Fingerprint` header

```python
import asyncio
from arcp import ARCPClient

async def get_metrics_with_arcp():
    # 1. Initialize ARCP client
    client = ARCPClient("http://localhost:8001")
    
    try:
        # 2. Login as admin (use your actual admin credentials)
        await client.login_admin("ARCP", "ARCP")  # Replace with your admin credentials
        
        # 3. Access metrics endpoint using the client
        metrics_data = await client.get_system_metrics()
        print(f"Metrics retrieved: {len(metrics_data)} bytes")
        return metrics_data
        
    finally:
        # 4. Clean up
        await client.close()

# Usage
asyncio.run(get_metrics_with_arcp())
```

### Setting Admin Credentials

Ensure your ARCP instance has admin credentials configured via environment variables:

```bash
# Required environment variables
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_secure_admin_password
```

**Security Note**: The metrics endpoint contains sensitive operational data and should only be accessible to authorized monitoring systems.

### Prometheus scraping without admin (recommended)

To let Prometheus scrape metrics without granting admin privileges, ARCP provides a dedicated token-protected endpoint:

- Admin-only: `/metrics`
- Prometheus-only: `/metrics/scrape` (requires a pre-shared bearer token)

Set a strong token in your environment and point Prometheus to `/metrics/scrape` with that token.

1) Configure the token

Place your token in `deployment/docker/.env`:

```bash
# deployment/docker/.env
METRICS_SCRAPE_TOKEN=your-long-random-token
```

2) How the provided Docker setup uses it

- The Prometheus container loads `deployment/docker/.env` and the entrypoint generates `/etc/prometheus/prometheus.yml` from a template.
- The `arcp` job in that template targets `/metrics/scrape` and injects the token as `bearer_token`.

Snippet (for reference):

```yaml
scrape_configs:
  - job_name: 'arcp'
    static_configs:
      - targets: ['arcp:8001']
    scrape_interval: 15s
    metrics_path: /metrics/scrape
    bearer_token: '<injected from env>'
```

3) If you manage Prometheus yourself

Just configure a job to hit `/metrics/scrape` and send the token:

```yaml
scrape_configs:
  - job_name: 'arcp'
    static_configs:
      - targets: ['your-arcp-host:8001']
    metrics_path: /metrics/scrape
    bearer_token: 'your-long-random-token'
```

4) Verify it works

- Prometheus Targets page should show the `arcp` job as UP.
- ARCP logs should show `GET /metrics/scrape` returning `200 OK` every scrape interval.

5) Security tips

- Keep `/metrics` admin-only; use `/metrics/scrape` for Prometheus.
- Rotate `METRICS_SCRAPE_TOKEN` if it ever leaks.
- Limit network exposure to ARCP from Prometheus only (e.g., compose network, firewall rules).
- Optionally enable IP allowlisting in ARCP and include your Prometheus IP range in `ALLOWED_IP_RANGES`.

## 🔍 ARCP Metrics

### Application Metrics

ARCP exposes Prometheus metrics at the `/metrics` endpoint (text format). **ARCP includes comprehensive custom metrics out-of-the-box**, providing 264+ ARCP-specific metrics covering agents, requests, system resources, and service health, in addition to the standard Python and process collectors from `prometheus_client`.

#### System Metrics

Standard collectors that are always present:

```prometheus
# Standard Python and process metrics
process_resident_memory_bytes 119771136.0
process_cpu_seconds_total 739.25
process_open_fds 27.0
python_info{implementation="CPython",major="3",minor="11",patchlevel="13",version="3.11.13"} 1.0
python_gc_objects_collected_total{generation="0"} 3717.0
```

#### Built-in Custom ARCP Metrics

ARCP automatically exposes comprehensive custom metrics including:

> **Note**: A typical ARCP instance exposes 264+ ARCP-specific metrics plus 16 standard Python/process metrics, totaling approximately 32KB of metrics data. This includes detailed breakdowns by endpoint, method, status code, agent type, and system resources.

#### Agent-Specific Metrics

These metrics are automatically tracked by ARCP:

```prometheus
# Agent registration metrics
arcp_agent_registrations_total{agent_type="testing",status="success"} 1
arcp_agent_registrations_total{agent_type="testing",status="error"} 1
arcp_active_agents{agent_type="all"} 1

# HTTP request metrics (automatic via middleware)
arcp_request_duration_seconds_bucket{endpoint="/health",method="GET",status_code="200",le="0.025"} 144
arcp_requests_total{endpoint="/health",method="GET",status_code="200"} 231
arcp_requests_total{endpoint="/metrics",method="GET",status_code="200"} 446

# System resource metrics
arcp_system_cpu_utilization_percent 2.19
arcp_system_memory_utilization_percent 42.8
arcp_system_disk_utilization_percent 1.53
arcp_system_network_utilization_percent 0.3

# Service health metrics
arcp_service_health_status{arcp_service_health_status="healthy"} 1
arcp_service_info{environment="development",name="ARCP",version="2.0.2"} 1
arcp_websocket_connections 0
```

### Custom Metrics

ARCP includes comprehensive custom metrics by default. You can still add additional custom metrics to your agents or services:

```python
"""
Simple ARCP Metrics Example

This example shows the basic usage of ARCP's built-in metrics system 
and how to add custom metrics to your agents.
"""

from prometheus_client import Counter, Histogram
import time
import asyncio

from arcp import ARCPClient
from arcp.services.metrics import metrics_service

# Add your own custom metrics for specific agent logic
CUSTOM_AGENT_REQUESTS = Counter(
    'my_agent_custom_requests_total', 
    'Custom agent requests', 
    ['operation']
)
CUSTOM_PROCESSING_TIME = Histogram(
    'my_agent_processing_duration_seconds', 
    'Custom processing time'
)

class MyAgent:
    def __init__(self):
        self.arcp_client = ARCPClient("http://localhost:8001")

    async def process_request(self):
        """Dummy processing method"""
        await asyncio.sleep(0.1)  # Simulate some processing
        return "processed"

    async def handle_request(self, operation: str):
        start_time = time.time()

        try:
            # Your request handling logic
            result = await self.process_request()

            # Record custom metrics (in addition to built-in ARCP metrics)
            CUSTOM_AGENT_REQUESTS.labels(operation=operation).inc()
            CUSTOM_PROCESSING_TIME.observe(time.time() - start_time)

            return result
        except Exception as e:
            CUSTOM_AGENT_REQUESTS.labels(operation=operation).inc()
            CUSTOM_PROCESSING_TIME.observe(time.time() - start_time)
            raise

async def main():
    """Main function to demonstrate metrics usage"""
    
    # 1. Access built-in ARCP metrics using the correct method
    print("1. Built-in ARCP Metrics:")
    prometheus_metrics, content_type = metrics_service.get_prometheus_metrics()
    
    print(f"   Content-Type: {content_type}")
    print(f"   Metrics size: {len(prometheus_metrics)} bytes")
    
    # Show sample of metrics
    metrics_text = prometheus_metrics.decode()
    arcp_lines = [line for line in metrics_text.split('\n') 
                  if 'arcp_' in line and not line.startswith('#')]
    print(f"   Built-in ARCP metrics found: {len(arcp_lines)}")
    print("   Sample metrics:")
    for line in arcp_lines[:3]:
        if line.strip():
            print(f"     {line}")
    print()
    
    # 2. Show current system resource utilization
    print("2. System Resource Utilization:")
    resource_util = await metrics_service.get_resource_utilization()
    for resource, value in resource_util.items():
        print(f"   {resource.capitalize()}: {value}%")
    print()
    
    # 3. Test custom agent functionality
    print("3. Testing Custom Agent Metrics:")
    agent = MyAgent()
    
    # Perform some operations
    operations = ["data_process", "user_query", "system_check"]
    
    for op in operations:
        print(f"   Processing {op}...")
        result = await agent.handle_request(op)
        print(f"   Result: {result}")
    
    print()
    
    # 4. Show metrics service status
    print("4. Metrics Service Status:")
    status = metrics_service.get_status()
    for key, value in status.items():
        if key in ['prometheus_available', 'psutil_available']:
            print(f"   {key}: {value}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 📈 Grafana Dashboards

### ARCP Overview Dashboard

Uses ARCP metrics that are available out-of-the-box.

```json
{
  "dashboard": {
    "id": null,
    "title": "ARCP Overview",
    "tags": ["arcp", "overview"],
    "timezone": "browser",
    "refresh": "5s",
    "panels": [
      {
        "id": 1,
        "title": "ARCP Server Status",
        "type": "stat",
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "arcp_service_health_status{arcp_service_health_status=\"healthy\"}",
            "legendFormat": "ARCP Server Health"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "green", "value": 1}
              ]
            }
          }
        }
      },
      {
        "id": 2,
        "title": "Process CPU (rate)",
        "type": "graph",
        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0},
        "targets": [
          {
            "expr": "arcp_system_cpu_utilization_percent",
            "legendFormat": "CPU Usage %"
          }
        ]
      },
      {
        "id": 3,
        "title": "Resident Memory",
        "type": "stat",
        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "arcp_system_memory_utilization_percent",
            "legendFormat": "Memory Usage %"
          }
        ]
      },
      {
        "id": 4,
        "title": "Open File Descriptors",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "arcp_active_agents",
            "legendFormat": "Active Agents"
          }
        ]
      },
      {
        "id": 5,
        "title": "Python GC Collections (rate)",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
          {
            "expr": "rate(arcp_requests_total[5m])",
            "legendFormat": "Request Rate"
          }
        ]
      },
      {
        "id": 6,
        "title": "WebSocket Connections",
        "type": "stat",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
        "targets": [
          {
            "expr": "arcp_websocket_connections",
            "legendFormat": "WebSocket Connections"
          }
        ]
      }
    ]
  }
}
```

### Agent Performance Dashboard

Uses ARCP agent and request metrics.

```json
{
  "dashboard": {
    "id": null,
    "title": "Agent Performance",
    "tags": ["arcp", "agents"],
    "timezone": "browser",
    "refresh": "10s",
    "panels": [
      {
        "id": 1,
        "title": "Agent Heartbeat Success Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "rate(arcp_agent_registrations_total{status=\"success\"}[5m])",
            "legendFormat": "{{agent_type}} Success Rate"
          },
          {
            "expr": "rate(arcp_agent_registrations_total{status=\"error\"}[5m])",
            "legendFormat": "{{agent_type}} Error Rate"
          }
        ]
      },
      {
        "id": 2,
        "title": "Agent Heartbeat Duration",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(arcp_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile request duration"
          },
          {
            "expr": "histogram_quantile(0.50, rate(arcp_request_duration_seconds_bucket[5m]))",
            "legendFormat": "50th percentile request duration"
          }
        ]
      },
      {
        "id": 3,
        "title": "Agent Metrics Updates",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "arcp_active_agents",
            "legendFormat": "Active Agents"
          },
          {
            "expr": "rate(arcp_requests_total[5m])",
            "legendFormat": "Request Rate"
          }
        ]
      },
      {
        "id": 4,
        "title": "Agent Registration Events",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
          {
            "expr": "rate(arcp_agent_registrations_total{status=\"success\"}[5m])",
            "legendFormat": "Agent Registrations"
          },
          {
            "expr": "arcp_websocket_connections",
            "legendFormat": "WebSocket Connections"
          }
        ]
      }
    ]
  }
}
```

### System Resources Dashboard

Uses ARCP system resource metrics alongside node exporter metrics.

```json
{
  "dashboard": {
    "id": null,
    "title": "System Resources",
    "tags": ["arcp", "system"],
    "timezone": "browser",
    "refresh": "5s",
    "panels": [
      {
        "id": 1,
        "title": "CPU Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "arcp_system_cpu_utilization_percent",
            "legendFormat": "ARCP CPU Usage"
          },
          {
            "expr": "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "legendFormat": "System CPU Usage {{instance}}"
          }
        ]
      },
      {
        "id": 2,
        "title": "Memory Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "arcp_system_memory_utilization_percent",
            "legendFormat": "ARCP Memory Usage"
          },
          {
            "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
            "legendFormat": "System Memory Usage {{instance}}"
          }
        ]
      },
      {
        "id": 3,
        "title": "Disk Usage",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "arcp_system_disk_utilization_percent",
            "legendFormat": "ARCP Disk Usage"
          },
          {
            "expr": "100 - ((node_filesystem_avail_bytes * 100) / node_filesystem_size_bytes)",
            "legendFormat": "System Disk Usage {{instance}} {{mountpoint}}"
          }
        ]
      },
      {
        "id": 4,
        "title": "Network I/O",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
          {
            "expr": "arcp_system_network_utilization_percent",
            "legendFormat": "ARCP Network Usage"
          },
          {
            "expr": "rate(node_network_receive_bytes_total[5m])",
            "legendFormat": "System {{instance}} {{device}} RX"
          },
          {
            "expr": "rate(node_network_transmit_bytes_total[5m])",
            "legendFormat": "System {{instance}} {{device}} TX"
          }
        ]
      }
    ]
  }
}
```

## 🔍 Distributed Tracing

### Jaeger Integration

ARCP can emit distributed tracing if enabled via environment variables. Set `TRACING_ENABLED=true` and configure `JAEGER_ENDPOINT` or `OTLP_ENDPOINT`. The codebase auto-instruments FastAPI, HTTPX, and Redis when tracing is enabled.

#### Viewing Traces

1. **Access Jaeger UI**: http://localhost:16686
2. **Search for traces** by service name, operation, or tags
3. **Analyze trace details** including timing and dependencies

#### Trace Examples

```python
# Example trace for agent registration
from opentelemetry import trace

from arcp import client

tracer = trace.get_tracer(__name__)

async def register_agent(agent_data):
    with tracer.start_as_current_span("register_agent") as span:
        span.set_attribute("agent_id", agent_data["agent_id"])
        span.set_attribute("agent_type", agent_data["agent_type"])
        
        # This will create child spans for Redis operations
        result = await client.ARCPClient.register_agent(agent_data)

        span.set_attribute("registration_success", True)
        return result
```

#### Custom Tracing

Add custom spans to your agents:

```python
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

# Instrument your agent
HTTPXClientInstrumentor().instrument()
RedisInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

class MyAgent:
    async def process_request(self, data):
        with tracer.start_as_current_span("process_request") as span:
            span.set_attribute("request_size", len(data))
            
            # Your processing logic
            result = await self.analyze_data(data)
            
            span.set_attribute("result_size", len(result))
            return result
```

## Prometheus Configuration

### Scraping ARCP Metrics

When configuring Prometheus to scrape ARCP metrics, you need to handle authentication. Here's the recommended approach:

#### Option 1: Using HTTP Basic Auth Proxy (Recommended)
Set up a proxy service that handles the JWT authentication and presents metrics via HTTP Basic Auth:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'arcp'
    static_configs:
      - targets: ['arcp-metrics-proxy:8080']
    basic_auth:
      username: 'prometheus'
      password: 'your-metrics-proxy-password'
    scrape_interval: 30s
    metrics_path: '/metrics'
```

#### Option 2: Using Bearer Token (Advanced)
If your Prometheus version supports it, you can use long-lived service tokens:

```yaml
# prometheus.yml  
scrape_configs:
  - job_name: 'arcp'
    static_configs:
      - targets: ['arcp:8001']
    authorization:
      type: Bearer
      credentials: 'your-long-lived-service-token'
    scrape_interval: 30s
    metrics_path: '/metrics'
    scheme: http
```

**Important**: The ARCP `/metrics` endpoint requires admin authentication. Ensure your monitoring setup includes proper credential management and consider implementing a metrics proxy for production environments.

### Metrics Proxy Example

For production, consider creating a simple metrics proxy:

```python
# metrics_proxy.py
import asyncio
from flask import Flask, Response
from arcp import ARCPClient
import os

app = Flask(__name__)

ARCP_BASE_URL = os.getenv('ARCP_BASE_URL', 'http://localhost:8001')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'ARCP')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'ARCP')

@app.route('/metrics')
def proxy_metrics():
    async def get_metrics():
        client = ARCPClient(ARCP_BASE_URL)
        try:
            await client.login_admin(ADMIN_USERNAME, ADMIN_PASSWORD)
            return await client.get_system_metrics()
        finally:
            await client.close()
    
    try:
        metrics_data = asyncio.run(get_metrics())
        return Response(metrics_data, mimetype='text/plain')
    except Exception as e:
        return Response(f'Metrics fetch failed: {e}', status=503)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 🚨 Alerting

### Prometheus Alert Rules

Create `deployment/prometheus/rules/arcp-alerts.yml` (these paths are not pre-created in the repo):

```yaml
groups:
  - name: arcp
    rules:
      # ARCP Server Down
      - alert: ARCPDown
        expr: up{job="arcp"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "ARCP server is down"
          description: "ARCP server has been down for more than 1 minute"

      # High Error Rate
      - alert: HighErrorRate
        expr: rate(arcp_requests_total{status_code=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors per second"

      # High Response Time
      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(arcp_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High response time"
          description: "95th percentile response time is {{ $value }} seconds"

      # Service Health Status
      - alert: ARCPServiceUnhealthy
        expr: arcp_service_health_status{arcp_service_health_status="unhealthy"} == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "ARCP service is unhealthy"
          description: "ARCP service health status is unhealthy"

      # Low Active Agents
      - alert: LowActiveAgents
        expr: arcp_active_agents < 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low number of active agents"
          description: "Only {{ $value }} agents are active"

      # Redis Down
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis is down"
          description: "Redis has been down for more than 1 minute"

      # High Redis Memory Usage
      - alert: HighRedisMemoryUsage
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High Redis memory usage"
          description: "Redis memory usage is {{ $value | humanizePercentage }}"

      # WebSocket Connection Limit
      - alert: WebSocketConnectionLimit
        expr: arcp_websocket_connections > 800
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "WebSocket connection limit approaching"
          description: "{{ $value }} WebSocket connections active"

      # High System Resource Usage
      - alert: HighSystemCPUUsage
        expr: arcp_system_cpu_utilization_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High system CPU usage"
          description: "System CPU usage is {{ $value }}%"

      - alert: HighSystemMemoryUsage
        expr: arcp_system_memory_utilization_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High system memory usage"
          description: "System memory usage is {{ $value }}%"
```

### Alertmanager Configuration

Create `deployment/prometheus/alertmanager.yml` (optional, not included by default):

```yaml
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@arcp.example.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
  - name: 'web.hook'
    webhook_configs:
      - url: 'http://localhost:5001/'

  - name: 'email'
    email_configs:
      - to: 'admin@arcp.example.com'
        subject: 'ARCP Alert: {{ .GroupLabels.alertname }}'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}

  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#arcp-alerts'
        title: 'ARCP Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
```

## 🔧 Monitoring Scripts

### Health Check Script

Create `health_check.py`:

```python
#!/usr/bin/env python3
"""
Health check script for ARCP monitoring.
Validates all monitoring endpoints and provides detailed status.
"""
import sys
import requests

def check_endpoint(url: str, name: str = "") -> bool:
    """Check if an endpoint is accessible."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print(f"{name or url}: OK ({response.status_code})")
            return True
        else:
            print(f"{name or url}: Failed ({response.status_code})")
            return False
    except requests.exceptions.RequestException as e:
        print(f"{name or url}: Connection failed - {e}")
        return False

def main():
    base_url = "http://localhost:8001"
    
    # Test essential ARCP endpoints (note: /metrics requires admin auth)
    endpoints = [
        (f"{base_url}/health", "Health Endpoint"),
        (f"{base_url}/", "Root Endpoint"),  
        (f"{base_url}/docs", "API Documentation"),
    ]
    
    results = []
    print("ARCP Health Check")
    print("=" * 30)
    
    for url, name in endpoints:
        results.append(check_endpoint(url, name))
    
    # Summary
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total) * 100
    
    print(f"\nSummary: {passed}/{total} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("Monitoring system is healthy!")
        sys.exit(0)
    else:
        print("Monitoring system has issues")
        sys.exit(1)
    
    if success_rate >= 80:
        print("Monitoring system is healthy!")
        sys.exit(0)
    else:
        print("Monitoring system has issues")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Metrics Collection Script

Create `collect_metrics.py`:

```python
#!/usr/bin/env python3
"""
Metrics collection script for ARCP monitoring.
Collects, parses, and analyzes ARCP metrics for validation and monitoring.
"""
import os
import json
import asyncio
from datetime import datetime
from arcp import ARCPClient

async def fetch_and_analyze_metrics_arcp(base_url: str):
    """Fetch metrics using ARCP client library and provide comprehensive analysis."""
    client = ARCPClient(base_url)
    
    try:
        # First, authenticate as admin
        print("1. Authenticating as admin...")
        await client.login_admin("ARCP", "ARCP")  # Use your actual admin credentials
        print("Admin authentication successful")
        
        # Fetch raw metrics with authentication
        print("2. Fetching metrics...")
        raw_metrics = await client.get_system_metrics()
        print(f"Metrics fetched successfully ({len(raw_metrics)} bytes)")
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"metrics_collection_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Save raw metrics
        with open(f"{output_dir}/raw_metrics.txt", 'w') as f:
            f.write(raw_metrics)
        
        # Analyze metrics
        print("3. Analyzing metrics...")
        lines = raw_metrics.split('\n')
        arcp_metrics = [line for line in lines if 'arcp_' in line and not line.startswith('#')]
        standard_metrics = [line for line in lines if any(prefix in line for prefix in ['process_', 'python_']) and not line.startswith('#')]
        
        # Create summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_metrics_lines': len([l for l in lines if l.strip() and not l.startswith('#')]),
            'arcp_specific_metrics': len(arcp_metrics),
            'standard_metrics': len(standard_metrics),
            'collection_successful': True
        }
        
        with open(f"{output_dir}/summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"Analysis complete:")
        print(f"  - Total metrics lines: {summary['total_metrics_lines']}")
        print(f"  - ARCP-specific metrics: {summary['arcp_specific_metrics']}")
        print(f"  - Standard metrics: {summary['standard_metrics']}")
        print(f"  - Output directory: {output_dir}")
        
        return True
        
    except Exception as e:
        print(f"Error collecting metrics: {e}")
        return False
    finally:
        await client.close()

def main():
    base_url = "http://localhost:8001"
    
    print("ARCP Metrics Collection")
    print("=" * 40)

    try:
        print("Using ARCP client library...")
        success = asyncio.run(fetch_and_analyze_metrics_arcp(base_url))
    except Exception as e:
        print(f"ARCP client failed ({e})")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
```

### Comprehensive Monitoring Validation Script

Create `validate_monitoring.py`:

```python
#!/usr/bin/env python3
"""
Comprehensive ARCP monitoring validation script.
Tests all monitoring components and provides detailed reporting.
"""
import sys
from urllib import request

class ARCPMonitoringValidator:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.results = []
    
    def validate_endpoints(self):
        """Test all monitoring endpoints."""
        endpoints = ["/health", "/metrics", "/dashboard", "/docs"]
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                with request.urlopen(url, timeout=10) as response:
                    success = response.status == 200
                    self.results.append(("Endpoint " + endpoint, success))
            except Exception:
                self.results.append(("Endpoint " + endpoint, False))
    
    def validate_metrics_content(self):
        """Validate metrics contain expected ARCP metrics."""
        try:
            url = f"{self.base_url}/metrics"
            with request.urlopen(url, timeout=10) as response:
                content = response.read().decode()
                
            expected = [
                "arcp_agent_registrations_total",
                "arcp_active_agents",
                "arcp_requests_total", 
                "arcp_system_cpu_utilization_percent"
            ]
            
            for metric in expected:
                found = metric in content
                self.results.append(("Metric " + metric, found))
                
        except Exception:
            self.results.append(("Metrics validation", False))
    
    def run_validation(self):
        """Run all validations and report results."""
        print("ARCP Monitoring Validation")
        print("=" * 50)
        
        self.validate_endpoints()
        self.validate_metrics_content()
        
        passed = sum(1 for _, success in self.results if success)
        total = len(self.results)
        
        print(f"\nResults: {passed}/{total} ({passed/total*100:.1f}%)")
        
        for test, success in self.results:
            print(f"{success} {test}")
        
        return 0 if passed >= total * 0.8 else 1

if __name__ == "__main__":
    validator = ARCPMonitoringValidator()
    sys.exit(validator.run_validation())
```

### Grafana Mobile App

1. **Install Grafana Mobile App** on your phone
2. **Configure connection** to your Grafana instance
3. **Set up alerts** for critical metrics
4. **View dashboards** on the go

### Custom Monitoring App

Create a simple monitoring app using the ARCP client library:

```python
import asyncio
from arcp import ARCPClient

class ARCPMonitor:
    def __init__(self, base_url: str, admin_username: str = "ARCP", admin_password: str = "ARCP"):
        self.client = ARCPClient(base_url)
        self.admin_username = admin_username
        self.admin_password = admin_password
        self._authenticated = False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def ensure_authenticated(self):
        """Ensure we're authenticated for admin operations"""
        if not self._authenticated:
            await self.client.login_admin(self.admin_username, self.admin_password)
            self._authenticated = True
    
    async def get_health(self):
        """Get ARCP health status (public endpoint)"""
        return await self.client.get_system_info()
    
    async def get_stats(self):
        """Get ARCP statistics (admin required)"""
        await self.ensure_authenticated()
        return await self.client.get_system_stats()
    
    async def get_metrics(self):
        """Get ARCP metrics (admin required)"""
        await self.ensure_authenticated()
        return await self.client.get_system_metrics()
    
    async def monitor(self, interval: int = 30, duration: int = None):
        """Continuous monitoring with ARCP client"""
        await self.ensure_authenticated()
        
        await self.client.monitor_system(
            interval=interval, 
            duration=duration,
            callback=self.metrics_callback
        )
    
    def metrics_callback(self, snapshot):
        """Callback for processing metrics snapshots"""
        print(f"\n[{snapshot.timestamp}] System Metrics:")
        
        # Extract key metrics
        cpu_util = snapshot.resource_utilization.get('cpu', 'N/A')
        memory_util = snapshot.resource_utilization.get('memory', 'N/A')
        
        print(f"  CPU: {cpu_util}%")
        print(f"  Memory: {memory_util}%")
        print(f"  Active Agents: {snapshot.agent_stats.get('total_agents', 0)}")

# Usage - Modern ARCP client approach
async def main():
    async with ARCPMonitor("http://localhost:8001") as monitor:
        # Get one-time status
        health = await monitor.get_health()
        print(f"System Status: {health.get('status', 'Unknown')}")
        
        # Start continuous monitoring
        await monitor.monitor(interval=30, duration=300)  # Monitor for 5 minutes

asyncio.run(main())
```

## 🚀 Performance Optimization

### Metrics Optimization

```python
from prometheus_client import Counter, Histogram, Gauge

# Use appropriate metric types
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration', buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0])
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')

# Batch metric updates
class MetricsBatcher:
    def __init__(self, batch_size=100):
        self.batch_size = batch_size
        self.batch = []
    
    def add_metric(self, metric, value, labels=None):
        self.batch.append((metric, value, labels))
        
        if len(self.batch) >= self.batch_size:
            self.flush()
    
    def flush(self):
        for metric, value, labels in self.batch:
            if labels:
                metric.labels(**labels).set(value)
            else:
                metric.set(value)
        self.batch.clear()
```

### Dashboard Optimization

```json
{
  "dashboard": {
    "refresh": "30s",  // Reduce refresh rate for better performance
    "time": {
      "from": "now-1h",  // Limit time range
      "to": "now"
    },
    "panels": [
      {
        "targets": [
          {
            "expr": "rate(arcp_http_requests_total[5m])",  // Use rate() for counters
            "interval": "1m"  // Set appropriate interval
          }
        ]
      }
    ]
  }
}
```

## 📚 Next Steps

Now that you have comprehensive monitoring:

1. **[API Reference](../api-reference/rest-api.md)** - Monitor API usage
2. **[Security Overview](../security/security-overview.md)** - Security best practices

## 💡 Monitoring Best Practices

1. **Secure metrics access** - Always use authentication for the `/metrics` endpoint
2. **Use metrics proxy** - Implement a proxy service for Prometheus scraping in production
3. **Set up alerts** - Configure alerts for critical metrics
4. **Monitor trends** - Watch for gradual changes, not just spikes
5. **Use appropriate time ranges** - Don't overload dashboards with too much data
6. **Regular maintenance** - Clean up old metrics and dashboards
7. **Document metrics** - Document what each metric means
8. **Test alerts** - Regularly test your alerting system
9. **Use log correlation** - Correlate metrics with logs for debugging
10. **Monitor dependencies** - Monitor external services and databases
11. **Validate monitoring setup** - Use the provided validation scripts regularly
12. **Secure admin credentials** - Use strong admin passwords and rotate them regularly

Ready to explore the API? Check out the [API Reference](../api-reference/rest-api.md)!