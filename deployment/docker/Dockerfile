# syntax=docker/dockerfile:1.6
# =================================
# ARCP Production Dockerfile
# =================================

# Build arguments
ARG PYTHON_VERSION=3.11
ARG POETRY_VERSION=1.6.1
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG ARCP_VERSION=2.0.3
ARG ARCP_BUILD_DATE=2025-08-19
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DEBUG=false
ARG ARCP_LOGS_DIR=/app/logs
ARG ENVIRONMENT=production
ARG ARCP_DATA_DIR=/app/data
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
        tzdata && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

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
ARG TZ=UTC
ARG LOG_LEVEL=DEBUG

# Create application directory
WORKDIR /app

# Copy only necessary files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
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
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chmod -R 755 ${ARCP_LOGS_DIR}

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Ensure runtime directories exist and are writable
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
    ENVIRONMENT=${ENVIRONMENT} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check (port will be resolved at runtime)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${ARCP_PORT}/health || exit 1

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
ARG ENVIRONMENT=testing
ARG ARCP_DATA_DIR=/app/data
ARG TZ=UTC
ARG LOG_LEVEL=DEBUG

# Create application directory
WORKDIR /app

# Copy source code and test files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
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
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chmod -R 755 ${ARCP_LOGS_DIR}

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Set proper permissions for testing environment
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod -R 700 ${ARCP_DATA_DIR} && \
    chmod -R 777 ${ARCP_LOGS_DIR}

# Switch to non-root user
USER arcp

# Testing environment configuration
ENV PYTHONPATH=/app/src \
    ARCP_HOST=${ARCP_HOST} \
    ARCP_PORT=${ARCP_PORT} \
    ARCP_DEBUG=${ARCP_DEBUG} \
    ARCP_LOGS_DIR=${ARCP_LOGS_DIR} \
    ENVIRONMENT=${ENVIRONMENT} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check (port will be resolved at runtime)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${ARCP_PORT}/health || exit 1

# Default command for testing (can run tests or the application)
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
ARG ENVIRONMENT=production
ARG ARCP_DATA_DIR=/app/data
ARG TZ=UTC
ARG LOG_LEVEL=INFO

# Create application directory
WORKDIR /app

# Copy only necessary files
COPY --chown=arcp:arcp src/ ./src/
COPY --chown=arcp:arcp web/ ./web/
COPY --chown=arcp:arcp pyproject.toml ./
COPY --chown=arcp:arcp requirements.txt ./

# Install the application with retry (no timeout flag)
RUN set -e; \
    pip install "setuptools<81"; \
    poetry config installer.max-workers 10; \
    for i in 1 2 3; do \
      poetry install --only=main --no-root -n && break || sleep 5; \
    done; \
    # Fallback: ensure critical OpenTelemetry dependencies are installed \
    pip install deprecated wrapt thrift importlib-metadata || true; \
    rm -rf $POETRY_CACHE_DIR

# Ensure runtime directories exist and are writable
RUN mkdir -p ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chown -R arcp:arcp ${ARCP_DATA_DIR} ${ARCP_LOGS_DIR} && \
    chmod -R 755 ${ARCP_LOGS_DIR}

# Configure timezone (must be done as root before user switch)
ENV TZ=${TZ}
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone

# Security hardening
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod -R 700 ${ARCP_DATA_DIR} && \
    chmod -R 777 ${ARCP_LOGS_DIR}

# Switch to non-root user
USER arcp

# Set environment variables
ENV PYTHONPATH=/app/src \
    ARCP_HOST=${ARCP_HOST} \
    ARCP_PORT=${ARCP_PORT} \
    ARCP_DEBUG=${ARCP_DEBUG} \
    ARCP_LOGS_DIR=${ARCP_LOGS_DIR} \
    ENVIRONMENT=${ENVIRONMENT} \
    ARCP_DATA_DIR=${ARCP_DATA_DIR} \
    TZ=${TZ} \
    LOG_LEVEL=${LOG_LEVEL}

# Health check (port will be resolved at runtime)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${ARCP_PORT}/health || exit 1

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
CMD sh -c "python -m uvicorn arcp.__main__:app --host ${ARCP_HOST} --port ${ARCP_PORT} --workers 1"

# =================================
# Multi-arch build stage
# =================================
FROM production as final

# Re-declare ARGs needed for final stage
ARG ARCP_HOST=0.0.0.0
ARG ARCP_PORT=8001
ARG ARCP_DATA_DIR=/app/data
ARG LOG_LEVEL=INFO

# Copy health check script with correct permissions (no root escalation needed) privesca :)
COPY --chmod=0755 --chown=arcp:arcp <<EOF /usr/local/bin/health-check.sh
#!/bin/bash
set -e

# Check if the service is responding
if curl -f -s http://localhost:${ARCP_PORT}/health > /dev/null; then
    echo "Service is healthy"
    exit 0
else
    echo "Service is unhealthy"
    exit 1
fi
EOF

# Enhanced health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD /usr/local/bin/health-check.sh

# Volume for persistent data (will use runtime ARCP_DATA_DIR value)
VOLUME ["/app/data"]

# Signal handling
STOPSIGNAL SIGTERM

# Default command with proper signal handling
CMD sh -c "python -m uvicorn arcp.__main__:app --host ${ARCP_HOST} --port ${ARCP_PORT} --workers 1 --access-log --log-level ${LOG_LEVEL}"