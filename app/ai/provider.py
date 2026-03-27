"""Factory for creating the configured AI provider."""

from .base import BaseAIProvider
from .claude import ClaudeProvider
from ..config import settings


def get_ai_provider() -> BaseAIProvider:
    """Return the configured AI provider instance."""
    if settings.ai_provider == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unknown AI provider: {settings.ai_provider}")
