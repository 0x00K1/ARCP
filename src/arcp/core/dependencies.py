"""Dependencies for FastAPI endpoints"""

from .registry import AgentRegistry
from .registry import get_registry as _get_registry


def get_registry() -> AgentRegistry:
    """Get the singleton agent registry instance"""
    return _get_registry()
