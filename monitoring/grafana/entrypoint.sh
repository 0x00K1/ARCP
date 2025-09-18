#!/bin/bash

# Set default values if not provided
export PROMETHEUS_PORT=${PROMETHEUS_PORT:-9090}
export JAEGER_UI_PORT=${JAEGER_UI_PORT:-16686}
export REDIS_HOST=${REDIS_HOST:-redis}
export REDIS_PORT=${REDIS_PORT:-6379}
export REDIS_PASSWORD=${REDIS_PASSWORD:-}

echo "Setting up Grafana provisioning configuration..."

# Create writable provisioning directories
mkdir -p /tmp/grafana-provisioning/datasources
mkdir -p /tmp/grafana-provisioning/dashboards
mkdir -p /tmp/grafana-provisioning/plugins
mkdir -p /tmp/grafana-provisioning/alerting

# Copy static dashboard configuration
cp -r /etc/grafana/provisioning/dashboards/* /tmp/grafana-provisioning/dashboards/ 2>/dev/null || true

# Generate dynamic datasource configuration
cat << EOF > /tmp/grafana-provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:${PROMETHEUS_PORT}
    isDefault: true
    editable: true
    jsonData:
      httpMethod: POST
      timeInterval: 15s
      queryTimeout: 60s
      manageAlerts: true
      alertmanagerUid: null
      exemplarTraceIdDestinations:
        - name: trace_id
          datasourceUid: jaeger
          urlDisplayLabel: "View Trace"
    secureJsonData: {}
    version: 1

  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:${JAEGER_UI_PORT}
    uid: jaeger
    editable: true
    jsonData:
      tracesToLogs:
        datasourceUid: loki
        tags: ['service.name', 'service.instance.id']
        mappedTags: [{ key: 'service.name', value: 'service' }]
        mapTagNamesEnabled: true
        spanStartTimeShift: '1h'
        spanEndTimeShift: '1h'
        filterByTraceID: true
        filterBySpanID: true
    version: 1

  - name: Redis
    type: redis-datasource
    access: proxy
    url: redis://${REDIS_HOST}:${REDIS_PORT}
    uid: redis
    editable: true
    jsonData:
      client: standalone
      poolSize: 5
      timeout: 30
      pingInterval: 0
      pipelineWindow: 0
    secureJsonData:
      password: "${REDIS_PASSWORD}"
    version: 1
EOF

# Set Grafana to use our generated provisioning directory
export GF_PATHS_PROVISIONING=/tmp/grafana-provisioning

echo "Generated datasource configuration:"
echo "  Prometheus URL: http://prometheus:${PROMETHEUS_PORT}"
echo "  Jaeger URL: http://jaeger:${JAEGER_UI_PORT}"
echo "  Redis URL: redis://${REDIS_HOST}:${REDIS_PORT}"

# Start Grafana
exec /run.sh "$@"