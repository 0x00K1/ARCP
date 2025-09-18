"""
Azure OpenAI service for ARCP.

This module provides a centralized interface for Azure OpenAI operations,
including embedding generation and client management.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    from openai import AzureOpenAI as _AzureOpenAI  # type: ignore
except ImportError:
    _AzureOpenAI = None

from ..core.config import config

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for Azure OpenAI operations."""

    def __init__(self):
        """Initialize the OpenAI service."""
        self.client: Optional[Any] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Azure OpenAI client."""
        azure_config = config.get_azure_config()

        if not _AzureOpenAI:
            logger.warning("OpenAI package not installed - OpenAI features unavailable")
            return

        if not all(azure_config.values()):
            logger.warning(
                "Azure OpenAI client not initialized - missing optional configuration"
            )
            return

        try:
            self.client = _AzureOpenAI(
                api_key=azure_config["api_key"],
                azure_endpoint=azure_config["azure_endpoint"],
                api_version=azure_config["api_version"],
            )
            logger.info("Azure OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI: {e}")
            self.client = None

    def is_available(self) -> bool:
        """Check if the OpenAI service is available."""
        return self.client is not None

    def get_client(self) -> Optional[Any]:
        """Get the Azure OpenAI client."""
        return self.client

    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        Generate embeddings for text using Azure OpenAI.

        Args:
            text: Text to generate embeddings for

        Returns:
            List of embeddings or None if unavailable
        """
        if not self.client:
            return None

        try:
            resp = self.client.embeddings.create(
                model=config.AZURE_EMBEDDING_DEPLOYMENT, input=[text]
            )
            vec = resp.data[0].embedding
            return list(vec)  # Return as list instead of numpy array
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the OpenAI service."""
        azure_config = config.get_azure_config()

        if not _AzureOpenAI:
            return {"status": "unavailable", "reason": "package_not_installed"}

        if not all(azure_config.values()):
            return {
                "status": "not_configured",
                "reason": "missing_configuration",
            }

        if self.client is None:
            return {
                "status": "initialization_failed",
                "reason": "client_failed_to_initialize",
            }

        return {"status": "available", "reason": "healthy"}


# Global OpenAI service instance
openai_service = OpenAIService()


def get_openai_client() -> Optional[Any]:
    """Get the Azure OpenAI client."""
    return openai_service.get_client()


def get_openai_service() -> OpenAIService:
    """Get the OpenAI service instance."""
    return openai_service
