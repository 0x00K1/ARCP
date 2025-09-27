"""ARCP - Agent Registry & Control Protocol

A sophisticated agent orchestration protocol that provides centralized
service discovery, registration, communication, and control for distributed agent systems.
"""

__version__ = "2.0.3"
__author__ = "Muhannad"
__email__ = "01muhannad.a@gmail.com"
__license__ = "Apache-2.0"
__description__ = "Agent Registry & Control Protocol"
__url__ = "https://github.com/0x00K1/ARCP"

from .client import (
    AgentConnectionRequest,
    AgentInfo,
    AgentMetrics,
    AgentRegistration,
    AgentRequirements,
    ARCPClient,
    ARCPError,
    AuthenticationError,
    ConnectionError,
    RegistrationError,
    SearchError,
    SearchRequest,
    SearchResponse,
    ValidationError,
)

__all__ = [
    "__version__",
    "get_app",
    "ARCPClient",
    "ARCPError",
    "AuthenticationError",
    "RegistrationError",
    "SearchError",
    "ConnectionError",
    "ValidationError",
    "AgentRequirements",
    "AgentRegistration",
    "AgentMetrics",
    "AgentInfo",
    "SearchRequest",
    "SearchResponse",
    "AgentConnectionRequest",
]


def get_app():
    """Get the FastAPI application instance"""
    from .__main__ import app

    return app


def get_client(base_url: str, **kwargs) -> ARCPClient:
    """
    Create an ARCP client instance.

    Args:
        base_url: Base URL of the ARCP server
        **kwargs: Additional client configuration options

    Returns:
        Configured ARCPClient instance

    Example:
        >>> import arcp
        >>> client = arcp.get_client("https://arcp.example.com")
        >>> # Use client for agent operations
    """
    return ARCPClient(base_url, **kwargs)
