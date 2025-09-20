"""
Unit tests for ARCP configuration module.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.arcp.core.config import ARCPConfig, config


@pytest.mark.unit
class TestARCPConfig:
    """Test cases for ARCPConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        # Clear JWT_SECRET to test default value, but provide required ALLOWED_AGENT_TYPES
        with patch.dict(os.environ, {"ALLOWED_AGENT_TYPES": "test,demo"}, clear=True):
            config_instance = ARCPConfig()

            # Test service defaults
            assert config_instance.SERVICE_NAME == "ARCP"
            assert config_instance.SERVICE_VERSION == "2.0.2"
            assert (
                config_instance.SERVICE_DESCRIPTION
                == "Agent Registry & Control Protocol"
            )

            # Test server defaults
            assert config_instance.HOST == "0.0.0.0"
            assert config_instance.PORT == 8001
            assert config_instance.DEBUG is False

            # Test agent defaults
            assert config_instance.AGENT_HEARTBEAT_TIMEOUT == 60
            assert config_instance.AGENT_CLEANUP_INTERVAL == 60

            # Note: JWT_SECRET should not have a default for security reasons
            assert config_instance.JWT_SECRET is None  # No default for security
            assert config_instance.JWT_ALGORITHM is None  # No default
            assert config_instance.JWT_EXPIRE_MINUTES is None  # No default

        # Test logging defaults
        assert config_instance.LOG_LEVEL == "INFO"
        assert "%(asctime)s" in config_instance.LOG_FORMAT

    @patch.dict(
        os.environ,
        {
            "ARCP_HOST": "localhost",
            "ARCP_PORT": "9000",
            "ARCP_DEBUG": "true",
            "JWT_SECRET": "test-secret",
            "ADMIN_USERNAME": "testadmin",
            "ADMIN_PASSWORD": "testpass",
        },
    )
    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        config_instance = ARCPConfig()

        assert config_instance.HOST == "localhost"
        assert config_instance.PORT == 9000
        assert config_instance.DEBUG is True
        assert config_instance.JWT_SECRET == "test-secret"
        assert config_instance.ADMIN_USERNAME == "testadmin"
        assert config_instance.ADMIN_PASSWORD == "testpass"

    def test_validate_required_config_missing(self):
        """Test validation with missing required configuration."""
        with patch.dict(os.environ, {"ALLOWED_AGENT_TYPES": "test,demo"}, clear=True):
            config_instance = ARCPConfig()
            missing = config_instance.validate_required_config()

            # Check for descriptive messages that include the field names
            admin_username_found = any("ADMIN_USERNAME" in msg for msg in missing)
            admin_password_found = any("ADMIN_PASSWORD" in msg for msg in missing)
            assert (
                admin_username_found
            ), f"ADMIN_USERNAME not found in missing config: {missing}"
            assert (
                admin_password_found
            ), f"ADMIN_PASSWORD not found in missing config: {missing}"

    @patch.dict(
        os.environ,
        {
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "password",
            "ENVIRONMENT": "development",
        },
    )
    def test_validate_required_config_present(self):
        """Test validation with required configuration present."""
        config_instance = ARCPConfig()
        missing = config_instance.validate_required_config()

        assert missing == []

    def test_validate_optional_config_missing(self):
        """Test validation of optional configuration when missing."""
        with patch.dict(os.environ, {"ALLOWED_AGENT_TYPES": "test,demo"}, clear=True):
            config_instance = ARCPConfig()
            optional_missing = config_instance.validate_optional_config()

            assert "azure" in optional_missing
            assert "redis" in optional_missing
            assert "AZURE_API_KEY" in optional_missing["azure"]
            assert "REDIS_HOST" in optional_missing["redis"]

    @patch.dict(
        os.environ,
        {
            "AZURE_API_KEY": "test-key",
            "AZURE_API_BASE": "https://test.openai.azure.com/",
            "AZURE_API_VERSION": "2023-12-01-preview",
            "AZURE_EMBEDDING_DEPLOYMENT": "text-embedding-ada-002",
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379",
            "REDIS_PASSWORD": "password",
            "REDIS_DB": "0",
            "REDIS_MAX_MEMORY": "256mb",
            "REDIS_HEALTH_CHECK_INTERVAL": "30",
            "REDIS_EXPORTER_PORT": "9121",
        },
    )
    def test_validate_optional_config_present(self):
        """Test validation of optional configuration when present."""
        config_instance = ARCPConfig()
        optional_missing = config_instance.validate_optional_config()

        assert optional_missing["azure"] == []
        assert optional_missing["redis"] == []

    def test_get_redis_config(self):
        """Test Redis configuration retrieval."""
        with patch.dict(
            os.environ,
            {
                "REDIS_HOST": "localhost",
                "REDIS_PORT": "6379",
                "REDIS_PASSWORD": "password",
                "REDIS_DB": "0",
            },
        ):
            config_instance = ARCPConfig()
            redis_config = config_instance.get_redis_config()

            assert redis_config["host"] == "localhost"
            assert redis_config["port"] == 6379
            assert redis_config["password"] == "password"
            assert redis_config["db"] == 0
            assert redis_config["decode_responses"] is False

    def test_get_redis_config_with_none_values(self):
        """Test Redis configuration with None values."""
        with patch.dict(os.environ, {"ALLOWED_AGENT_TYPES": "test,demo"}, clear=True):
            config_instance = ARCPConfig()
            redis_config = config_instance.get_redis_config()

            assert redis_config["host"] is None
            assert redis_config["port"] is None
            assert redis_config["password"] is None
            assert redis_config["db"] is None

    def test_get_azure_config(self):
        """Test Azure configuration retrieval."""
        with patch.dict(
            os.environ,
            {
                "AZURE_API_KEY": "test-key",
                "AZURE_API_BASE": "https://test.openai.azure.com/",
                "AZURE_API_VERSION": "2023-12-01-preview",
                "AZURE_EMBEDDING_DEPLOYMENT": "text-embedding-ada-002",
            },
        ):
            config_instance = ARCPConfig()
            azure_config = config_instance.get_azure_config()

            assert azure_config["api_key"] == "test-key"
            assert azure_config["azure_endpoint"] == "https://test.openai.azure.com/"
            assert azure_config["api_version"] == "2023-12-01-preview"
            assert azure_config["deployment"] == "text-embedding-ada-002"

    def test_get_azure_config_with_none_values(self):
        """Test Azure configuration with None values."""
        with patch.dict(os.environ, {"ALLOWED_AGENT_TYPES": "test,demo"}, clear=True):
            config_instance = ARCPConfig()
            azure_config = config_instance.get_azure_config()

            assert azure_config["api_key"] is None
            assert azure_config["azure_endpoint"] is None
            assert azure_config["api_version"] is None
            assert azure_config["deployment"] is None

    @patch("src.arcp.core.config.Path")
    def test_ensure_data_directory(self, mock_path):
        """Test data directory creation."""
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance

        config_instance = ARCPConfig()
        config_instance.ensure_data_directory()

        mock_path.assert_called_once_with(config_instance.DATA_DIRECTORY)
        mock_path_instance.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_integer_environment_variables(self):
        """Test integer environment variable parsing."""
        with patch.dict(
            os.environ,
            {
                "ARCP_PORT": "8080",
                "AGENT_HEARTBEAT_TIMEOUT": "120",
                "JWT_EXPIRE_MINUTES": "30",
            },
        ):
            config_instance = ARCPConfig()

            assert config_instance.PORT == 8080
            assert config_instance.AGENT_HEARTBEAT_TIMEOUT == 120
            assert config_instance.JWT_EXPIRE_MINUTES == 30

    def test_boolean_environment_variables(self):
        """Test boolean environment variable parsing."""
        # Test true values
        with patch.dict(os.environ, {"ARCP_DEBUG": "true"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is True

        with patch.dict(os.environ, {"ARCP_DEBUG": "True"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is True

        with patch.dict(os.environ, {"ARCP_DEBUG": "TRUE"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is True

        # Test false values
        with patch.dict(os.environ, {"ARCP_DEBUG": "false"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is False

        with patch.dict(os.environ, {"ARCP_DEBUG": "False"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is False

        with patch.dict(os.environ, {"ARCP_DEBUG": "anything"}):
            config_instance = ARCPConfig()
            assert config_instance.DEBUG is False

    def test_data_directory_path_construction(self):
        """Test data directory path construction."""
        with patch.dict(
            os.environ, {"ARCP_DATA_DIR": "/custom/data", "STATE_FILE": ""}, clear=False
        ):
            config_instance = ARCPConfig()

            assert config_instance.DATA_DIRECTORY == "/custom/data"
            expected_state_file = os.path.join("/custom/data", "registry_state.json")
            assert config_instance.STATE_FILE == expected_state_file

    def test_websocket_configuration(self):
        """Test WebSocket configuration."""
        with patch.dict(
            os.environ,
            {
                "WEBSOCKET_TIMEOUT": "60",
                "WEBSOCKET_PING_INTERVAL": "45",
                "WEBSOCKET_MAX_CONNECTIONS": "200",
            },
        ):
            config_instance = ARCPConfig()

            assert config_instance.WEBSOCKET_TIMEOUT == 60
            assert config_instance.WEBSOCKET_PING_INTERVAL == 45
            assert config_instance.WEBSOCKET_MAX_CONNECTIONS == 200

    def test_vector_search_configuration(self):
        """Test vector search configuration."""
        with patch.dict(
            os.environ,
            {
                "VECTOR_SEARCH_TOP_K": "20",
                "VECTOR_SEARCH_MIN_SIMILARITY": "0.8",
            },
        ):
            config_instance = ARCPConfig()

            assert config_instance.VECTOR_SEARCH_TOP_K == 20
            assert config_instance.VECTOR_SEARCH_MIN_SIMILARITY == 0.8

    def test_global_config_instance(self):
        """Test that global config instance exists."""
        assert config is not None
        assert isinstance(config, ARCPConfig)
        assert config.SERVICE_NAME == "ARCP"

    def test_log_format_configuration(self):
        """Test log format configuration."""
        with patch.dict(os.environ, {"LOG_FORMAT": "%(levelname)s - %(message)s"}):
            config_instance = ARCPConfig()

            assert config_instance.LOG_FORMAT == "%(levelname)s - %(message)s"

    def test_redis_health_check_interval(self):
        """Test Redis health check interval configuration."""
        with patch.dict(os.environ, {"REDIS_HEALTH_CHECK_INTERVAL": "60"}):
            config_instance = ARCPConfig()

            assert config_instance.REDIS_HEALTH_CHECK_INTERVAL == 60

    def test_session_timeout(self):
        """Test global session timeout configuration."""
        with patch.dict(os.environ, {"SESSION_TIMEOUT": "120"}):
            config_instance = ARCPConfig()
            assert config_instance.SESSION_TIMEOUT == 120

    def test_config_validation_edge_cases(self):
        """Test configuration validation edge cases."""
        # Test with empty strings
        with patch.dict(
            os.environ,
            {
                "AZURE_API_KEY": "",
                "REDIS_HOST": "",
                "ADMIN_USERNAME": "",
                "ADMIN_PASSWORD": "",
            },
        ):
            config_instance = ARCPConfig()

            # Empty strings should be treated as None/missing
            assert config_instance.AZURE_API_KEY == ""
            assert config_instance.REDIS_HOST == ""
            assert config_instance.ADMIN_USERNAME == ""
            assert config_instance.ADMIN_PASSWORD == ""

            # Validation should detect missing values
            missing = config_instance.validate_required_config()
            admin_username_found = any("ADMIN_USERNAME" in msg for msg in missing)
            admin_password_found = any("ADMIN_PASSWORD" in msg for msg in missing)
            assert (
                admin_username_found
            ), f"ADMIN_USERNAME not found in missing config: {missing}"
            assert (
                admin_password_found
            ), f"ADMIN_PASSWORD not found in missing config: {missing}"

            optional_missing = config_instance.validate_optional_config()
            assert "AZURE_API_KEY" in optional_missing["azure"]
            assert "REDIS_HOST" in optional_missing["redis"]
