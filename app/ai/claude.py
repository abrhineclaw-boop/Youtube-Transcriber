"""Claude API adapter for AI analysis."""

import logging
import anthropic
from .base import BaseAIProvider, AnalysisResult, ModelConfig
from ..config import settings

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseAIProvider):
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.default_config = ModelConfig(model=settings.claude_model)

    def _extract_text(self, message) -> str:
        """Extract text from a Claude API response, validating it's non-empty."""
        if not message.content:
            raise ValueError(
                f"Claude returned empty content (model={message.model}, "
                f"stop_reason={message.stop_reason})"
            )
        text = message.content[0].text
        if not text or not text.strip():
            raise ValueError(
                f"Claude returned empty text (model={message.model}, "
                f"stop_reason={message.stop_reason}, "
                f"input_tokens={message.usage.input_tokens}, "
                f"output_tokens={message.usage.output_tokens})"
            )
        if message.stop_reason == "max_tokens":
            logger.warning(
                f"Claude response was truncated (max_tokens hit, "
                f"output_tokens={message.usage.output_tokens})"
            )
        return text

    async def analyze(self, prompt: str, text: str, config: ModelConfig | None = None) -> AnalysisResult:
        cfg = config or self.default_config
        message = await self.client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\n---\n\nTRANSCRIPT:\n{text}",
                }
            ],
        )
        return AnalysisResult(
            text=self._extract_text(message),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def analyze_package(
        self,
        system_prompt: str,
        transcript_text: str,
        analysis_instructions: str,
        config: ModelConfig | None = None,
    ) -> AnalysisResult:
        """Run a bundled package with transcript as cacheable prefix."""
        cfg = config or self.default_config
        message = await self.client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"TRANSCRIPT:\n{transcript_text}",
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"\n\n---\n\nANALYSIS INSTRUCTIONS:\n{analysis_instructions}",
                        },
                    ],
                }
            ],
        )
        return AnalysisResult(
            text=self._extract_text(message),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
