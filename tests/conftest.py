"""
Test configuration and fixtures for ARCP test suite.

Provides common test utilities, fixtures, and configuration for the ARCP project.
"""

import asyncio
import os
import sys

# Set test environment variables BEFORE importing anything else
import tempfile
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

temp_dir = tempfile.gettempdir()

os.environ.update(
    {
        "ENVIRONMENT": "testing",
        "LOG_LEVEL": "WARNING",
        "DISABLE_REDIS": "true",
        "DISABLE_OPENAI": "true",
        "DISABLE_TRACING": "true",
        "JWT_SECRET": "test-jwt-secret-key-for-testing-only",
        "AGENT_CLEANUP_INTERVAL": "3600",  # 1 hour for tests
        "RATE_LIMIT_ENABLED": "false",  # Disable rate limiting in tests
        "WEBSOCKET_TIMEOUT": "5",  # Shorter timeout for tests
        # Use temp directories to avoid permission issues
        "ARCP_DATA_DIR": f"{temp_dir}/arcp_test_data",
        "ARCP_LOGS_DIR": f"{temp_dir}/arcp_test_logs",
        "STATE_FILE": f"{temp_dir}/arcp_test_data/registry_state.json",
        # Agent registration keys for testing
        "AGENT_KEYS": "test-registration-key-123,test-agent-key-456,test-security-key-789",
        # Azure OpenAI config for tests (even though OpenAI is disabled)
        "AZURE_EMBEDDING_DEPLOYMENT": "text-embedding-ada-002",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Add the src directory to Python path for imports
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from arcp.__main__ import app  # noqa: E402
from arcp.core.registry import AgentRegistry  # noqa: E402

# Import fixtures from fixtures directory
from tests.fixtures.agent_fixtures import *  # noqa: E402, F403, F401
from tests.fixtures.agent_fixtures import create_test_agent_registration  # noqa: E402
from tests.fixtures.auth_fixtures import (  # noqa: E402
    create_admin_token,
    create_valid_token,
)
from tests.fixtures.mock_services import *  # noqa: E402, F403, F401
from tests.fixtures.test_helpers import (  # noqa: E402
    AgentTestHelper,
    AuthTestHelper,
    ResponseValidator,
)

# ================================
# CORE APPLICATION FIXTURES
# ================================


@pytest.fixture
def test_client():
    """FastAPI test client fixture with optimizations for testing."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def async_test_client():
    """Async FastAPI test client for async operations."""
    from httpx import AsyncClient

    from src.arcp.__main__ import app

    async def _client():
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    return _client


# ================================
# PYTEST CONFIGURATION
# ================================


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "security: mark test as security test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "network: mark test as requiring network access")
    config.addinivalue_line("markers", "redis: mark test as requiring Redis")
    config.addinivalue_line("markers", "openai: mark test as requiring OpenAI API")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers and skip conditions."""
    for item in items:
        # Auto-mark tests based on directory
        test_path = str(item.fspath)

        if "/unit/" in test_path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in test_path:
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in test_path:
            item.add_marker(pytest.mark.e2e)
        elif "/performance/" in test_path:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
        elif "/security/" in test_path:
            item.add_marker(pytest.mark.security)

        # Mark performance tests as slow
        if "performance" in item.name.lower():
            item.add_marker(pytest.mark.slow)

        # Mark WebSocket tests appropriately
        if "websocket" in item.name.lower() or "ws" in item.name.lower():
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment before any tests run."""
    # Environment variables are already set at module level
    # This fixture exists for any additional setup/cleanup

    yield

    # Cleanup after all tests
    # Any global cleanup can go here


@pytest.fixture(autouse=True)
def cleanup_metrics():
    """Clean up metrics between tests to prevent registration conflicts."""
    from prometheus_client import REGISTRY

    # Clear the prometheus registry before each test to prevent conflicts
    collectors_to_remove = []
    for collector in list(REGISTRY._collector_to_names.keys()):
        # Only remove ARCP metrics, not built-in ones
        metric_names = REGISTRY._collector_to_names.get(collector, set())
        if any(name.startswith("arcp_") for name in metric_names):
            collectors_to_remove.append(collector)

    for collector in collectors_to_remove:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            # Already removed
            pass

    # Also reset the metrics service instance
    try:
        from src.arcp.services.metrics import reset_metrics_service

        reset_metrics_service()
    except ImportError:
        pass

    yield


# ================================
# LEGACY FIXTURE COMPATIBILITY
# ================================
# Keep some legacy fixtures for backward compatibility


@pytest.fixture
def sample_agent_request():
    """Legacy sample agent registration request fixture."""
    return create_test_agent_registration("test-agent-001", "testing")


# Legacy fixtures are imported from fixtures/ directory above

# ================================
# CORE REGISTRY FIXTURES
# ================================


@pytest.fixture
async def registry(mock_storage_adapter, mock_openai_client):
    """Clean agent registry fixture with mocked dependencies."""
    # Reset singleton to ensure clean state
    AgentRegistry._instance = None

    # Create a fresh registry instance
    registry = AgentRegistry()

    # Use the mock services from fixtures
    registry.storage = mock_storage_adapter
    registry.ai_client = mock_openai_client
    registry.openai_service = MagicMock()
    registry.openai_service.is_available = MagicMock(return_value=False)
    registry.openai_service.client = None

    # Clear any existing agents (use correct attribute names)
    registry.backup_agents = {}
    registry.backup_embeddings = {}
    registry.backup_metrics = {}
    registry.backup_info_hashes = {}
    registry.backup_agent_keys = {}

    yield registry

    # Cleanup
    registry.backup_agents.clear()
    registry.backup_embeddings.clear()
    registry.backup_metrics.clear()
    registry.backup_info_hashes.clear()
    registry.backup_agent_keys.clear()
    mock_storage_adapter.clear_all_data()
    mock_openai_client.clear_custom_embeddings()


@pytest.fixture
async def populated_registry(registry, multiple_agent_registrations):
    """Registry populated with test agents from fixtures."""
    # Register test agents
    for agent_registration in multiple_agent_registrations:
        await registry.register_agent(agent_registration)

    # Enable AI client for vector search tests
    registry.openai_service.is_available = MagicMock(return_value=True)
    registry.ai_client.set_available(True)

    yield registry


# ================================
# AUTHENTICATION & SECURITY FIXTURES
# ================================


@pytest.fixture
def jwt_token():
    """Sample JWT token for testing - uses helper from auth fixtures."""
    return create_valid_token("test-agent", "agent")


@pytest.fixture
def admin_token():
    """Admin JWT token for testing."""
    return create_admin_token("admin")


# ================================
# ASYNC & EVENT LOOP FIXTURES
# ================================


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def warn_about_leftover_tasks():
    """Warn about leftover async tasks at session end."""
    yield
    # At session end, warn if there are unclosed tasks
    try:
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        if tasks:
            warnings.warn(
                f"Found {len(tasks)} uncancelled async tasks at session end",
                RuntimeWarning,
            )
    except RuntimeError:
        # No event loop
        pass


# ================================
# CONFIGURATION & MOCKING FIXTURES
# ================================


@pytest.fixture
def mock_config():
    """Mock configuration for testing with improved defaults."""
    config_values = {
        "JWT_SECRET": "test-jwt-secret-key-for-testing-only",
        "JWT_ALGORITHM": "HS256",
        "JWT_EXPIRE_MINUTES": 60,
        "LOG_LEVEL": "WARNING",
        "LOG_FORMAT": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "AGENT_HEARTBEAT_TIMEOUT": 60,
        "AGENT_CLEANUP_INTERVAL": 3600,
        "REDIS_HEALTH_CHECK_INTERVAL": 30,
        "RATE_LIMIT_ENABLED": False,
        "WEBSOCKET_TIMEOUT": 5,
        "MAX_AGENTS_PER_PAGE": 20,
        "VECTOR_SEARCH_ENABLED": True,
        "AZURE_OPENAI_API_KEY": "test-openai-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "REDIS_DB": 0,
    }

    with patch.multiple("src.arcp.core.config.config", **config_values) as mock_config:
        yield mock_config


@pytest.fixture
def mock_logger():
    """Enhanced mock logger for testing."""
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.critical = MagicMock()
    logger.exception = MagicMock()

    # Add call tracking
    logger.call_count = {
        "debug": 0,
        "info": 0,
        "warning": 0,
        "error": 0,
        "critical": 0,
        "exception": 0,
    }

    def count_calls(level):
        def wrapper(*args, **kwargs):
            logger.call_count[level] += 1

        return wrapper

    for level in logger.call_count:
        getattr(logger, level).side_effect = count_calls(level)

    return logger


# Legacy mock storage - kept for backward compatibility
# Use mock_storage_adapter from fixtures for new tests
@pytest.fixture
def mock_storage():
    """Legacy mock storage adapter for testing."""
    storage = AsyncMock()
    storage.hget = AsyncMock(return_value=None)
    storage.hset = AsyncMock(return_value=1)
    storage.hgetall = AsyncMock(return_value={})
    storage.hkeys = AsyncMock(return_value=[])
    storage.hdel = AsyncMock(return_value=1)
    storage.exists = AsyncMock(return_value=False)
    storage.get = AsyncMock(return_value=None)
    storage.set = AsyncMock()
    storage.delete = AsyncMock(return_value=1)
    return storage


# ================================
# HELPER FIXTURES FOR COMMON PATTERNS
# ================================


@pytest.fixture
def auth_headers_admin():
    """Ready-to-use admin authentication headers."""
    token = create_admin_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_agent():
    """Ready-to-use agent authentication headers."""
    token = create_valid_token("test-agent", "agent")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def response_validator():
    """Response validator helper instance."""
    return ResponseValidator


@pytest.fixture
def agent_test_helper():
    """Agent test helper instance."""
    return AgentTestHelper


@pytest.fixture
def auth_test_helper():
    """Auth test helper instance."""
    return AuthTestHelper
