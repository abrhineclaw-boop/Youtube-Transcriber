"""Provider-agnostic AI interface.

Swapping from Claude to another provider means implementing a new adapter
that inherits from BaseAIProvider, not changing calling code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ModelConfig:
    model: str
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class AnalysisResult:
    """Response from an AI analysis call, including token usage."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class BaseAIProvider(ABC):
    """Abstract AI provider interface."""

    @abstractmethod
    async def analyze(self, prompt: str, text: str, config: ModelConfig | None = None) -> AnalysisResult:
        """Send a prompt + text to the AI and return the response with token usage."""
        ...

    @abstractmethod
    async def analyze_package(
        self,
        system_prompt: str,
        transcript_text: str,
        analysis_instructions: str,
        config: ModelConfig | None = None,
    ) -> AnalysisResult:
        """Run a bundled analysis package with prompt caching support.

        Structures the API call so the transcript is a cacheable prefix,
        reducing costs when multiple packages run on the same transcript.
        """
        ...
