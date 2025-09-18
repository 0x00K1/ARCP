"""
Unit tests for OpenAI service integration.

Tests the Azure OpenAI service wrapper for embedding generation and API calls.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.arcp.services.openai import OpenAIService


@pytest.mark.unit
class TestOpenAIService:
    """Test OpenAI service functionality."""

    def test_initialization_with_config(self):
        """Test OpenAI service initialization with configuration."""
        with patch("src.arcp.services.openai.config.get_azure_config") as mock_config:
            mock_config.return_value = {
                "api_key": "test-api-key",
                "azure_endpoint": "https://test.openai.azure.com/",
                "api_version": "2023-12-01-preview",
                "deployment": "text-embedding-ada-002",
            }
            service = OpenAIService()
            assert service.client is not None
            assert service.is_available()

    def test_initialization_without_config(self):
        """Test OpenAI service initialization without configuration."""
        with patch("src.arcp.services.openai.config.get_azure_config") as mock_config:
            mock_config.return_value = {
                "api_key": None,
                "azure_endpoint": None,
                "api_version": None,
                "deployment": None,
            }
            service = OpenAIService()
            assert service.client is None
            assert not service.is_available()

    def test_is_available_with_client(self):
        """Test availability check with valid client."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService()
            # Mock the client creation
            service.client = MagicMock()
            assert service.is_available()

    def test_is_available_without_client(self):
        """Test availability check without client."""
        service = OpenAIService()
        service.client = None
        assert not service.is_available()

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_embed_text_success(self, mock_azure_openai):
        """Test successful text embedding generation."""
        # Setup mock client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5])]
        mock_client.embeddings.create.return_value = mock_response
        mock_azure_openai.return_value = mock_client

        # Create service with mocked client
        with patch.dict(
            "os.environ",
            {
                "AZURE_API_KEY": "test-key",
                "AZURE_API_BASE": "https://test.openai.azure.com/",
                "AZURE_API_VERSION": "2023-12-01-preview",
                "AZURE_EMBEDDING_DEPLOYMENT": "test-deployment",
            },
        ):
            service = OpenAIService()
            service.client = mock_client

            # Test embedding generation
            result = service.embed_text("test text for embedding")

            assert result == [0.1, 0.2, 0.3, 0.4, 0.5]
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-ada-002",
                input=["test text for embedding"],
            )

    def test_embed_text_without_client(self):
        """Test embedding generation without client."""
        service = OpenAIService()
        service.client = None

        result = service.embed_text("test text")
        assert result is None

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_embed_text_api_error(self, mock_azure_openai):
        """Test embedding generation with API error."""
        # Setup mock client that raises exception
        mock_client = Mock()
        mock_client.embeddings.create.side_effect = Exception("API Error")
        mock_azure_openai.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService()
            service.client = mock_client

            result = service.embed_text("test text")
            assert result is None

    def test_get_status_available(self):
        """Test status when service is available."""
        with patch("src.arcp.services.openai.config.get_azure_config") as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "azure_endpoint": "https://test.openai.azure.com/",
                "api_version": "2023-12-01-preview",
                "deployment": "text-embedding-ada-002",
            }
            service = OpenAIService()
            service.client = MagicMock()

            status = service.get_status()

            assert status["status"] == "available"
            assert status["reason"] == "healthy"

    def test_get_status_unavailable(self):
        """Test status when service is unavailable."""
        service = OpenAIService()
        service.client = None

        status = service.get_status()

        assert status["status"] in [
            "not_configured",
            "unavailable",
            "initialization_failed",
        ]
        assert "reason" in status

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_embed_text_with_different_inputs(self, mock_azure_openai):
        """Test embedding generation with various input types."""
        # Setup mock client
        mock_client = Mock()

        # Different responses for different inputs
        def mock_create(model, input):
            input_text = input[0] if isinstance(input, list) else input
            if "short" in input_text:
                return Mock(data=[Mock(embedding=[0.1, 0.2])])
            elif "long" in input_text:
                return Mock(data=[Mock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6])])
            else:
                return Mock(data=[Mock(embedding=[0.5, 0.5, 0.5])])

        mock_client.embeddings.create.side_effect = mock_create
        mock_azure_openai.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
                "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
            },
        ):
            service = OpenAIService()
            service.client = mock_client

            # Test short text
            result_short = service.embed_text("short text")
            assert len(result_short) == 2
            assert result_short == [0.1, 0.2]

            # Test long text
            result_long = service.embed_text("long text with more content")
            assert len(result_long) == 6
            assert result_long == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

            # Test default
            result_default = service.embed_text("default text")
            assert result_default == [0.5, 0.5, 0.5]

    def test_embed_text_empty_input(self):
        """Test embedding generation with empty input."""
        service = OpenAIService()
        service.client = MagicMock()

        result = service.embed_text("")
        assert result == []

        result = service.embed_text(None)
        assert result == []

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_client_initialization_error(self, mock_azure_openai):
        """Test client initialization with invalid configuration."""
        mock_azure_openai.side_effect = Exception("Authentication failed")

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "invalid-key",
                "AZURE_OPENAI_ENDPOINT": "https://invalid.openai.azure.com/",
            },
        ):
            service = OpenAIService()
            assert service.client is None
            assert not service.is_available()

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_concurrent_embedding_requests(self, mock_azure_openai):
        """Test handling multiple concurrent embedding requests."""

        # Setup mock client
        mock_client = Mock()
        call_count = 0

        def mock_create(model, input):
            nonlocal call_count
            call_count += 1
            return Mock(data=[Mock(embedding=[0.1 * call_count, 0.2 * call_count])])

        mock_client.embeddings.create.side_effect = mock_create
        mock_azure_openai.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService()
            service.client = mock_client

            # Test multiple calls
            result1 = service.embed_text("text one")
            result2 = service.embed_text("text two")
            result3 = service.embed_text("text three")

            # Verify all calls were made and returned different embeddings
            assert result1 == [0.1, 0.2]
            assert result2 == [0.2, 0.4]
            assert len(result3) == 2
            assert abs(result3[0] - 0.3) < 0.0001
            assert abs(result3[1] - 0.6) < 0.0001
            assert call_count == 3

    def test_configuration_from_environment(self):
        """Test various environment variable configurations."""
        # Test with minimal config - should fail without required fields
        with patch("src.arcp.services.openai.config.get_azure_config") as mock_config:
            mock_config.return_value = {
                "api_key": "minimal-key",
                "azure_endpoint": None,  # Missing required field
                "api_version": None,  # Missing required field
                "deployment": None,
            }
            service = OpenAIService()
            assert service.client is None  # Should fail initialization
            assert not service.is_available()

        # Test with full config - should succeed
        with patch("src.arcp.services.openai.config.get_azure_config") as mock_config:
            mock_config.return_value = {
                "api_key": "full-key",
                "azure_endpoint": "https://custom.openai.azure.com/",
                "api_version": "2023-12-01-preview",
                "deployment": "custom-deployment",
            }
            service = OpenAIService()
            assert service.client is not None
            assert service.is_available()

    @patch("src.arcp.services.openai._AzureOpenAI")
    def test_embedding_dimension_consistency(self, mock_azure_openai):
        """Test that embeddings maintain consistent dimensions."""
        # Setup mock client with consistent embedding size
        mock_client = Mock()
        embedding_dim = 1536  # Standard dimension for text-embedding-ada-002

        def mock_create(model, input):
            return Mock(data=[Mock(embedding=[0.1] * embedding_dim)])

        mock_client.embeddings.create.side_effect = mock_create
        mock_azure_openai.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        ):
            service = OpenAIService()
            service.client = mock_client

            # Test multiple embeddings have consistent dimensions
            texts = [
                "Short text",
                "Medium length text with more words",
                "Very long text with many more words and complex sentences that should still produce consistent embedding dimensions",
            ]

            for text in texts:
                embedding = service.embed_text(text)
                assert embedding is not None
                assert len(embedding) == embedding_dim
                assert all(isinstance(val, (int, float)) for val in embedding)
