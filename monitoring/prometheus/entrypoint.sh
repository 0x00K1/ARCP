#!/bin/sh
set -e

# Set default values for all needed variables
ARCP_PORT=${ARCP_PORT:-8001}
REDIS_EXPORTER_PORT=${REDIS_EXPORTER_PORT:-9121}
PROMETHEUS_PORT=${PROMETHEUS_PORT:-9090}
GRAFANA_PORT=${GRAFANA_PORT:-3000}
JAEGER_METRICS_PORT=${JAEGER_METRICS_PORT:-14269}
METRICS_SCRAPE_TOKEN=${METRICS_SCRAPE_TOKEN:-}

# Template file paths
TEMPLATE_FILE="/etc/prometheus/prometheus.yml.template"
CONFIG_FILE="/etc/prometheus/prometheus.yml"

echo "Generating Prometheus configuration..."
echo "ARCP_PORT=$ARCP_PORT"
echo "REDIS_EXPORTER_PORT=$REDIS_EXPORTER_PORT"
echo "PROMETHEUS_PORT=$PROMETHEUS_PORT"
echo "GRAFANA_PORT=$GRAFANA_PORT"
echo "JAEGER_METRICS_PORT=$JAEGER_METRICS_PORT"
echo "METRICS_SCRAPE_TOKEN is ${METRICS_SCRAPE_TOKEN:+set}"  # don't echo secret

# Generate config from template
sed -e "s|{{ARCP_PORT}}|$ARCP_PORT|g" \
    -e "s|{{REDIS_EXPORTER_PORT}}|$REDIS_EXPORTER_PORT|g" \
    -e "s|{{PROMETHEUS_PORT}}|$PROMETHEUS_PORT|g" \
    -e "s|{{GRAFANA_PORT}}|$GRAFANA_PORT|g" \
    -e "s|{{JAEGER_METRICS_PORT}}|$JAEGER_METRICS_PORT|g" \
    -e "s|{{METRICS_SCRAPE_TOKEN}}|${METRICS_SCRAPE_TOKEN}|g" \
    "$TEMPLATE_FILE" > "$CONFIG_FILE"

echo "Configuration generated successfully at $CONFIG_FILE"

# Start Prometheus with working flags
exec /bin/prometheus \
    --config.file=/etc/prometheus/prometheus.yml \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time=15d \
    --storage.tsdb.retention.size=2GB \
    --storage.tsdb.wal-compression \
    --web.enable-lifecycle