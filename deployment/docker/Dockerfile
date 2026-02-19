# syntax=docker/dockerfile:1.6
# =================================
# ARCP Production Dockerfile
# =================================

# Build arguments
ARG PYTHON_VERSION=3.11
ARG POETRY_VERSION=1.6.1
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG ARCP_VERSION=2.1.0
ARG ARCP_BUILD_DATE=2025-08-19
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DEBUG=false
ARG ARCP_LOGS_DIR=/app/logs
ARG ARCP_DATA_DIR=/app/data
ARG ARCP_TLS_CERT_DIR=/app/certs
ARG ARCP_TLS_CERT_FILENAME=server.crt
ARG ARCP_TLS_KEY_FILENAME=server.key
ARG ENVIRONMENT=production
ARG TZ=UTC
ARG LOG_LEVEL=INFO

# =================================
# Base stage - Common dependencies
# =================================
FROM python:${PYTHON_VERSION:-3.11}-slim-bookworm as base

# Re-declare args needed in this stage
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG POETRY_VERSION=1.6.1

# Install system dependencies and security updates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        tzdata \
        pkg-config \
        gcc \
        python3-dev \
        libtss2-dev && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Install Trivy for container scanning (v2.1.5)
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.58.0 && \
    trivy --version

# Create non-root user
RUN groupadd -r arcp --gid=${GROUP_ID} && \
    useradd --no-log-init -r -g arcp --uid=${USER_ID} --create-home --shell /bin/bash arcp

# Set up Python environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install Poetry
RUN pip install --no-cache-dir poetry==${POETRY_VERSION}

# =================================
# Dependencies stage
# =================================
FROM base as dependencies

# Copy dependency files (poetry.lock optional)
COPY pyproject.toml ./

# Install dependencies with retry logic (no timeout flag)
RUN set -e; \
    pip install --upgrade pip; \
    poetry config installer.max-workers 10; \
    for i in 1 2 3; do \
      poetry install --only=main --no-root -n && break || sleep 5; \
    done; \
    rm -rf $POETRY_CACHE_DIR

# =================================
# Development stage
# =================================
FROM dependencies as development

# Re-declare all required ARGs for development stage
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DEBUG=true
ARG ARCP_LOGS_DIR=/app/logs
ARG ENVIRONMENT=development
ARG ARCP_DATA_DIR=/app/data
ARG ARCP_TLS_CERT_DIR=/app/certs
ARG ARCP_TLS_CERT_FILENAME=server.crt
ARG ARCP_TLS_KEY_FILENAME=server.key
ARG TZ=UTC
ARG LOG_LEVEL=DEBUG

# Create application directory
WORKDIR /app

# Copy only necessary files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
COPY --chown=arcp:arcp config/ ./config/
COPY --chown=arcp:arcp pyproject.toml ./
COPY --chown=arcp:arcp requirements.txt ./

# Install development dependencies with retry (no timeout flag)
RUN set -e; \
    poetry config installer.max-workers 10; \
    for i in 1 2 3; do \
      poetry install --no-root -n && break || sleep 5; \
    done; \
    pip install deprecated wrapt thrift importlib-metadata || true; \
    rm -rf $POETRY_CACHE_DIR

# Ensure runtime directories exist and are writable
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache/trivy && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache && \
    chmod -R 755 ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} && \
    chmod -R 775 /home/arcp/.cache

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Set proper permissions
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod -R 700 ${ARCP_DATA_DIR} && \
    chmod -R 777 ${ARCP_LOGS_DIR}

# Switch to non-root user
USER arcp

# Development environment configuration
ENV PYTHONPATH=/app/src \
    ARCP_HOST=${ARCP_HOST} \
    ARCP_PORT=${ARCP_PORT} \
    ARCP_DEBUG=${ARCP_DEBUG} \
    ARCP_LOGS_DIR=${ARCP_LOGS_DIR} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    ARCP_TLS_CERT_DIR=${ARCP_TLS_CERT_DIR} \
    ENVIRONMENT=${ENVIRONMENT} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/health-check.sh

# Default command
CMD ["python", "-m", "arcp"]

# =================================
# Testing stage
# =================================
FROM dependencies as testing

# Re-declare all required ARGs for testing stage
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DEBUG=true
ARG ARCP_LOGS_DIR=/app/logs
ARG ARCP_DATA_DIR=/app/data
ARG ARCP_TLS_CERT_DIR=/app/certs
ARG ARCP_TLS_CERT_FILENAME=server.crt
ARG ARCP_TLS_KEY_FILENAME=server.key
ARG ENVIRONMENT=testing
ARG TZ=UTC
ARG LOG_LEVEL=DEBUG

# Create application directory
WORKDIR /app

# Copy source code and test files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
COPY --chown=arcp:arcp config/ ./config/
COPY --chown=arcp:arcp tests/ ./tests/
COPY --chown=arcp:arcp examples/ ./examples/
COPY --chown=arcp:arcp pyproject.toml ./
COPY --chown=arcp:arcp requirements.txt ./

# Install all dependencies including dev/test dependencies
RUN set -e; \
    poetry config installer.max-workers 10; \
    for i in 1 2 3; do \
      poetry install --no-root -n && break || sleep 5; \
    done; \
    rm -rf $POETRY_CACHE_DIR

# Ensure runtime directories exist and are writable
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache/trivy && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache && \
    chmod -R 775 ${ARCP_DATA_DIR} && \
    chmod -R 755 ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} && \
    chmod -R 775 /home/arcp/.cache

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Set proper permissions for testing environment
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod -R 775 ${ARCP_DATA_DIR} && \
    chmod -R 777 ${ARCP_LOGS_DIR}

# Switch to non-root user
USER arcp

# Testing environment configuration
ENV PYTHONPATH=/app/src \
    ARCP_HOST=${ARCP_HOST} \
    ARCP_PORT=${ARCP_PORT} \
    ARCP_DEBUG=${ARCP_DEBUG} \
    ARCP_LOGS_DIR=${ARCP_LOGS_DIR} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    ARCP_TLS_CERT_DIR=${ARCP_TLS_CERT_DIR} \
    ENVIRONMENT=${ENVIRONMENT} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/health-check.sh

# Default command for testing
CMD ["python", "-m", "arcp"]

# =================================
# Production stage
# =================================
FROM dependencies as production

# Re-declare all required ARGs for production stage
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DEBUG=false
ARG ARCP_LOGS_DIR=/app/logs
ARG ARCP_DATA_DIR=/app/data
ARG ARCP_TLS_CERT_DIR=/app/certs
ARG ARCP_TLS_CERT_FILENAME=server.crt
ARG ARCP_TLS_KEY_FILENAME=server.key
ARG ENVIRONMENT=production
ARG TZ=UTC
ARG LOG_LEVEL=INFO

# Create application directory
WORKDIR /app

# Copy only necessary files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
COPY --chown=arcp:arcp config/ ./config/
COPY --chown=arcp:arcp pyproject.toml ./
COPY --chown=arcp:arcp requirements.txt ./

# Install the application with retry (no timeout flag)
RUN set -e; \
    pip install "setuptools<81"; \
    poetry config installer.max-workers 10; \
    for i in 1 2 3; do \
      poetry install --only=main --no-root -n && break || sleep 5; \
    done; \
    # Install TPM support separately with fallback \
    pip install tpm2-pytss || echo "TPM support installation failed (optional)"; \
    # Fallback: ensure critical OpenTelemetry dependencies are installed \
    pip install deprecated wrapt thrift importlib-metadata || true; \
    rm -rf $POETRY_CACHE_DIR

# Ensure runtime directories exist and are writable
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache/trivy && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} /home/arcp/.cache && \
    chmod -R 775 ${ARCP_DATA_DIR} && \
    chmod -R 755 ${ARCP_LOGS_DIR} ${ARCP_TLS_CERT_DIR} && \
    chmod -R 775 /home/arcp/.cache

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Pre-download Trivy vulnerability database so scans don't need to download at runtime
ENV CONTAINER_TRIVY_CACHE_DIR=/home/arcp/.cache/trivy
RUN trivy image --download-db-only --cache-dir /home/arcp/.cache/trivy 2>/dev/null || \
    echo "Trivy DB pre-download skipped (will download on first scan)"
RUN chown -R arcp:arcp /home/arcp/.cache

# Security hardening
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod -R 775 ${ARCP_DATA_DIR} && \
    chmod -R 777 ${ARCP_LOGS_DIR}

# Switch to non-root user
USER arcp

# Set environment variables
ENV PYTHONPATH=/app/src \
    ARCP_HOST=${ARCP_HOST} \
    ARCP_PORT=${ARCP_PORT} \
    ARCP_DEBUG=${ARCP_DEBUG} \
    ARCP_LOGS_DIR=${ARCP_LOGS_DIR} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    ARCP_TLS_CERT_DIR=${ARCP_TLS_CERT_DIR} \
    ENVIRONMENT=${ENVIRONMENT} \
    TZ=${TZ} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/health-check.sh

# Add labels for metadata
LABEL org.opencontainers.image.title="ARCP" \
      org.opencontainers.image.description="Agent Registry & Control Protocol" \
      org.opencontainers.image.version=${ARCP_VERSION} \
      org.opencontainers.image.created=${ARCP_BUILD_DATE} \
      org.opencontainers.image.source="https://github.com/0x00K1/ARCP" \
      org.opencontainers.image.documentation="https://arcp.0x001.tech/docs" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="ARCP Team" \
      org.opencontainers.image.authors="Muhannad <01muhannad.a@gmail.com>" \
      maintainer="Muhannad <01muhannad.a@gmail.com>"

# Production command
CMD ["python", "-m", "arcp"]

# =================================
# Multi-arch build stage
# =================================
FROM production as final

# Re-declare ARGs needed for final stage
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DATA_DIR=/app/data
ARG ARCP_TLS_CERT_DIR=/app/certs
ARG ARCP_TLS_CERT_FILENAME=server.crt
ARG ARCP_TLS_KEY_FILENAME=server.key
ARG LOG_LEVEL=INFO

# Health check script
COPY --chmod=0755 --chown=arcp:arcp <<EOF /usr/local/bin/health-check.sh
#!/bin/bash
set -e
if [ "\${ARCP_TLS_ENABLED:-false}" = "true" ]; then
    curl -kf -s https://localhost:\${ARCP_PORT}/health > /dev/null
else
    curl -f -s http://localhost:\${ARCP_PORT}/health > /dev/null
fi
EOF

# Entrypoint script
COPY --chmod=0755 --chown=root:root <<EOF /usr/local/bin/docker-entrypoint.sh
#!/bin/bash
set -e

echo "[INFO] Starting ARCP container..."
echo "[INFO] Environment: \${ENVIRONMENT:-production}"
echo "[INFO] TLS Enabled: \${ARCP_TLS_ENABLED:-false}"

# Check data directory permissions
if [ -d "\${ARCP_DATA_DIR}" ]; then
    if ! touch \${ARCP_DATA_DIR}/.write_test 2>/dev/null; then
        echo "[WARN] \${ARCP_DATA_DIR} is not writable"
    else
        rm -f \${ARCP_DATA_DIR}/.write_test
        echo "[INFO] Data directory writable: \${ARCP_DATA_DIR}"
    fi
fi

# Validate TLS configuration
if [ "\${ARCP_TLS_ENABLED:-false}" = "true" ]; then
    echo "[INFO] TLS enabled - validating certificates"
    echo "[INFO] Certificate directory: \${ARCP_TLS_CERT_DIR}"
    echo "[INFO] Certificate filename: \${ARCP_TLS_CERT_FILENAME:-server.crt}"
    echo "[INFO] Key filename: \${ARCP_TLS_KEY_FILENAME:-server.key}"
    
    CERT_PATH="\${ARCP_TLS_CERT_DIR}/\${ARCP_TLS_CERT_FILENAME:-server.crt}"
    KEY_PATH="\${ARCP_TLS_CERT_DIR}/\${ARCP_TLS_KEY_FILENAME:-server.key}"
    
    echo "[INFO] Full certificate path: \${CERT_PATH}"
    echo "[INFO] Full key path: \${KEY_PATH}"
    
    if [ -f "\${CERT_PATH}" ] && [ -f "\${KEY_PATH}" ]; then
        echo "[INFO] TLS certificates found"
        echo "[INFO] Certificate file size: \$(ls -lh \${CERT_PATH} | awk '{print \$5}')"
        echo "[INFO] Key file size: \$(ls -lh \${KEY_PATH} | awk '{print \$5}')"
    else
        echo "[ERROR] TLS certificates not found:"
        echo "  Cert: \${CERT_PATH} (exists: \$([ -f \"\${CERT_PATH}\" ] && echo \"yes\" || echo \"no\"))"
        echo "  Key: \${KEY_PATH} (exists: \$([ -f \"\${KEY_PATH}\" ] && echo \"yes\" || echo \"no\"))"
        echo "[ERROR] Certificate directory contents:"
        ls -la "\${ARCP_TLS_CERT_DIR}/" || echo "  Directory not accessible"
        echo "[ERROR] Mount certificates to \${ARCP_TLS_CERT_DIR}/"
        exit 1
    fi
else
    echo "[INFO] TLS disabled - running HTTP only"
fi

echo "[INFO] Starting application..."
exec "\$@"
EOF

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD /usr/local/bin/health-check.sh

# Volume for persistent data
VOLUME ["/app/data"]

# Signal handling
STOPSIGNAL SIGTERM

# Entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command
CMD ["python", "-m", "arcp"]